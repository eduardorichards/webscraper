import math
import re
from datetime import date, datetime

from flask import Flask, render_template, request, jsonify, url_for
from config import env
from config.keyword_settings import DEFAULT_KEYWORDS
from utils.sqlite_storage import SQLiteStorage

app = Flask(__name__)

DAYS_OPTIONS = {"7", "14", "30", "all"}
DAYS_LABELS = {"7": "Last 7 days", "14": "Last 14 days", "30": "Last 30 days",
               "all": "All time"}
PER_PAGE_OPTIONS = list(env.PER_PAGE_CHOICES)
APPLY_LABELS = {"easy_apply": "Easy Apply", "external": "External", "unknown": "Unknown"}
APPLIED_LABELS = {"hide": "Hide applied", "only": "Only applied", "all": "All"}
DEFAULT_APPLIED = "hide"
# Keyword filter options: the configured keywords, in config order
KEYWORD_OPTIONS = list(dict.fromkeys(DEFAULT_KEYWORDS))
MAX_SEARCH_LENGTH = 100
MAX_LIST_VALUES = 20
MAX_NOTES_LENGTH = 2000
# (min score, badge class), highest first; below the last one → "low".
# From the score distribution of ~100k scored jobs (2026-11-14 local copy):
# median 10, p75 25, p90 47.
SCORE_BADGE_THRESHOLDS = ((50, "strong"), (25, "good"), (10, "fair"))


def _int_arg(name, default, min_value=None, max_value=None):
    """Read an int query param; invalid or out-of-range values → default."""
    try:
        value = int(request.args.get(name, ""))
    except ValueError:
        return default
    if min_value is not None and value < min_value:
        return default
    if max_value is not None and value > max_value:
        return default
    return value


def _float_arg(name, default, min_value=0.0, max_value=None):
    """Read a float query param; invalid, non-finite or out-of-range → default."""
    try:
        value = float(request.args.get(name, ""))
    except ValueError:
        return default
    if not math.isfinite(value) or value < min_value:
        return default
    if max_value is not None and value > max_value:
        return default
    return value


def _list_arg(name, allowed=None):
    """Read a repeated query param: stripped, non-empty, deduplicated, capped."""
    values = []
    for value in request.args.getlist(name):
        value = value.strip()
        if value and value not in values and (allowed is None or value in allowed):
            values.append(value)
    return values[:MAX_LIST_VALUES]


def _checkbox_arg(name, default=True):
    """Read a checkbox paired with a hidden "0" input: the last value wins.

    Absent entirely (first visit) → default.
    """
    values = request.args.getlist(name)
    return values[-1] == "1" if values else default


def _num(value):
    """Short display for a float filter value: 10.0 → "10", 2.5 → "2.5"."""
    return "%g" % value


@app.template_global()
def index_url(query_args, **overrides):
    """URL for the index page keeping current params, with some overridden."""
    args = {**query_args, **overrides}
    return url_for("index", **{k: v for k, v in args.items() if v not in ("", [], None)})


@app.template_global()
def score_badge(score):
    """Badge class suffix for a weighted score (see SCORE_BADGE_THRESHOLDS)."""
    if score is None:
        return "low"
    for threshold, name in SCORE_BADGE_THRESHOLDS:
        if score >= threshold:
            return name
    return "low"


@app.template_global()
def applicants_label(job):
    """"<25" / ">200" / exact count / "-".

    A historical 25 without qualifier was stored for "Be among the first 25",
    so it is shown as "<25" too.
    """
    count = job.get("applicant_count")
    qualifier = job.get("applicant_count_qualifier")
    if count is None:
        return "-"
    if qualifier == "under" or (count == 25 and qualifier is None):
        return "<%d" % count
    if qualifier == "over":
        return ">%d" % count
    return str(count)


def _active_filter_chips(query_args, defaults):
    """[(label, url)] for every filter that differs from its default; each
    url resets that one filter (or removes one value of a list filter)."""
    chips = []
    reset = dict(page=1)

    def add(label, **overrides):
        chips.append((label, index_url(query_args, **reset, **overrides)))

    if query_args["q"]:
        add('Search: "%s"' % query_args["q"], q="")
    if query_args["days"] != defaults["days"]:
        add(DAYS_LABELS[query_args["days"]], days=defaults["days"])
    if query_args["hours"] != "":
        add("Last %s hours" % query_args["hours"], hours="")
    if query_args["location"]:
        add("Location: %s" % query_args["location"], location="")
    if query_args["min_score"]:
        add("Score ≥ %s" % _num(query_args["min_score"]), min_score="")
    if query_args["max_score"] != "":
        add("Score ≤ %s" % _num(query_args["max_score"]), max_score="")
    if query_args["min_match"] != "":
        add("Match ≥ %s%%" % _num(query_args["min_match"]), min_match="")
    for value in query_args["emp"]:
        add("Employment: %s" % value, emp=[v for v in query_args["emp"] if v != value])
    for value in query_args["kw"]:
        add("Keyword: %s" % value, kw=[v for v in query_args["kw"] if v != value])
    if query_args["apply"]:
        add("Apply: %s" % APPLY_LABELS[query_args["apply"]], apply="")
    if query_args["under25"] == "1":
        add("Under 25 applicants", under25="0")
    if query_args["applied"] != defaults["applied"]:
        add("Applied: %s" % APPLIED_LABELS[query_args["applied"]],
            applied=defaults["applied"])
    for name, label in (("hide_blacklisted", "Blacklisted shown"),
                        ("hide_aggregators", "Aggregators shown"),
                        ("hide_above_level", "Above my level shown")):
        if query_args[name] == "0":
            add(label, **{name: "1"})
    return chips


@app.route("/")
def index():
    min_score = _float_arg("min_score", 0.0)
    max_score = _float_arg("max_score", None)
    min_match = _float_arg("min_match", None, max_value=100.0)

    days_raw = request.args.get("days", "7")
    if days_raw not in DAYS_OPTIONS:
        days_raw = "7"
    days = None if days_raw == "all" else int(days_raw)

    page = _int_arg("page", 1, min_value=1)
    per_page = _int_arg("per_page", env.DEFAULT_PER_PAGE)
    if per_page not in PER_PAGE_OPTIONS:
        per_page = env.DEFAULT_PER_PAGE
    hours = _int_arg("hours", None, min_value=1, max_value=24 * 365 * 10)
    location = request.args.get("location", "").strip()
    search = request.args.get("q", "").strip()[:MAX_SEARCH_LENGTH]
    apply_raw = request.args.get("apply", "")
    if apply_raw not in SQLiteStorage.APPLY_FILTERS:
        apply_raw = ""
    applied = request.args.get("applied", DEFAULT_APPLIED)
    if applied not in SQLiteStorage.APPLIED_FILTERS:
        applied = DEFAULT_APPLIED
    employment_types = _list_arg("emp")
    keywords = _list_arg("kw", allowed=KEYWORD_OPTIONS)

    hide_blacklisted = _checkbox_arg("hide_blacklisted")
    hide_aggregators = _checkbox_arg("hide_aggregators")
    hide_above_level = _checkbox_arg("hide_above_level")
    under_25 = _checkbox_arg("under25", default=False)

    sort = request.args.get("sort", SQLiteStorage.DEFAULT_SORT)
    direction = request.args.get("dir", SQLiteStorage.DEFAULT_DIRECTION)
    if sort not in SQLiteStorage.SORT_COLUMNS or direction not in SQLiteStorage.SORT_DIRECTIONS:
        sort, direction = SQLiteStorage.DEFAULT_SORT, SQLiteStorage.DEFAULT_DIRECTION

    filters = dict(min_score=min_score, max_score=max_score, min_match=min_match,
                   days=days, location=location or None, hours=hours,
                   search=search or None, employment_types=employment_types,
                   keywords=keywords, under_25=under_25, applied=applied,
                   hide_blacklisted=hide_blacklisted,
                   apply_type=apply_raw or None,
                   hide_aggregators=hide_aggregators,
                   hide_above_level=hide_above_level)

    storage = SQLiteStorage()
    total = storage.count_job_summary(unique=True, **filters)
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    jobs = storage.get_job_summary(unique=True, page=page, per_page=per_page,
                                   sort=sort, direction=direction, **filters)
    snippets = storage.get_description_snippets([j["linkedin_job_id"] for j in jobs])
    applications = storage.get_application_status(jobs)
    stats = storage.get_analysis_stats()
    blacklisted = storage.get_blacklisted_companies()
    employment_options = storage.get_employment_types()

    start = (page - 1) * per_page + 1 if jobs else 0
    end = start + len(jobs) - 1 if jobs else 0

    # Normalized params used to build sort/pagination/chip links
    query_args = {
        "q": search,
        "min_score": min_score,
        "max_score": max_score if max_score is not None else "",
        "min_match": min_match if min_match is not None else "",
        "days": days_raw,
        "location": location,
        "hours": hours if hours is not None else "",
        "emp": employment_types,
        "kw": keywords,
        "under25": "1" if under_25 else "0",
        "applied": applied,
        "hide_blacklisted": "1" if hide_blacklisted else "0",
        "hide_aggregators": "1" if hide_aggregators else "0",
        "hide_above_level": "1" if hide_above_level else "0",
        "apply": apply_raw,
        "per_page": per_page,
        "sort": sort,
        "dir": direction,
        "page": page,
    }
    chips = _active_filter_chips(query_args, {"days": "7", "applied": DEFAULT_APPLIED})
    clear_url = url_for("index", sort=sort, dir=direction, per_page=per_page)

    return render_template("index.html", jobs=jobs, stats=stats,
                           snippets=snippets, applications=applications,
                           min_score=min_score, max_score=max_score,
                           min_match=min_match, search=search,
                           blacklisted=blacklisted,
                           days=days_raw, location=location, hours=hours,
                           hide_blacklisted=hide_blacklisted, apply=apply_raw,
                           hide_aggregators=hide_aggregators,
                           hide_above_level=hide_above_level,
                           under_25=under_25, applied=applied,
                           applied_labels=APPLIED_LABELS,
                           employment_types=employment_types,
                           employment_options=employment_options,
                           keywords=keywords, keyword_options=KEYWORD_OPTIONS,
                           above_levels=SQLiteStorage.ABOVE_TARGET_LEVELS,
                           per_page=per_page, per_page_options=PER_PAGE_OPTIONS,
                           sort=sort, direction=direction,
                           page=page, total=total, total_pages=total_pages,
                           start=start, end=end, query_args=query_args,
                           chips=chips, clear_url=clear_url, num=_num)


@app.route("/api/blacklist", methods=["GET"])
def api_blacklist_list():
    storage = SQLiteStorage()
    return jsonify(storage.get_blacklisted_companies())


@app.route("/api/blacklist", methods=["POST"])
def api_blacklist_add():
    data = request.get_json(silent=True) or {}
    company = (data.get("company") or "").strip()
    if not company:
        return jsonify({"error": "company required"}), 400
    storage = SQLiteStorage()
    storage.add_blacklisted_company(company)
    return jsonify({"status": "ok", "company": company})


@app.route("/api/blacklist", methods=["DELETE"])
def api_blacklist_remove():
    data = request.get_json(silent=True) or {}
    company = (data.get("company") or "").strip()
    if not company:
        return jsonify({"error": "company required"}), 400
    storage = SQLiteStorage()
    storage.remove_blacklisted_company(company)
    return jsonify({"status": "ok", "company": company})


def _application_job_id(data):
    """Validated linkedin_job_id from a JSON body, or (None, error response)."""
    job_id = str(data.get("linkedin_job_id") or "").strip()
    if not re.fullmatch(r"[0-9]+", job_id):
        return None, (jsonify({"error": "linkedin_job_id required"}), 400)
    return job_id, None


@app.route("/api/applications", methods=["GET"])
def api_applications_list():
    storage = SQLiteStorage()
    return jsonify(storage.get_applications())


@app.route("/api/applications", methods=["POST"])
def api_applications_save():
    """Mark a job as applied, or update its date/notes."""
    data = request.get_json(silent=True) or {}
    job_id, error = _application_job_id(data)
    if error:
        return error
    applied_on = str(data.get("applied_on") or "").strip() or date.today().isoformat()
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", applied_on):
            raise ValueError
        datetime.strptime(applied_on, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "applied_on must be YYYY-MM-DD"}), 400
    notes = str(data.get("notes") or "").strip()
    if len(notes) > MAX_NOTES_LENGTH:
        return jsonify({"error": "notes too long (max %d)" % MAX_NOTES_LENGTH}), 400
    storage = SQLiteStorage()
    if not storage.job_post_exists(job_id):
        return jsonify({"error": "unknown job"}), 404
    storage.save_application(job_id, applied_on, notes or None)
    return jsonify({"status": "ok", "linkedin_job_id": job_id,
                    "applied_on": applied_on, "notes": notes or None})


@app.route("/api/applications", methods=["DELETE"])
def api_applications_remove():
    data = request.get_json(silent=True) or {}
    job_id, error = _application_job_id(data)
    if error:
        return error
    storage = SQLiteStorage()
    storage.remove_application(job_id)
    return jsonify({"status": "ok", "linkedin_job_id": job_id})


SHORTLIST_DEFAULTS = {"since": "2h", "min_score": 29.0, "limit": 10, "apply": "external"}
SHORTLIST_MAX_LIMIT = 100
SHORTLIST_MAX_SINCE_HOURS = 24 * 365
SHORTLIST_APPLY_OPTIONS = ("external", "easy_apply", "all")
SHORTLIST_FIELDS = ("linkedin_job_id", "title", "company", "location", "date_time",
                    "weighted_score", "match_percentage", "matched_keywords",
                    "seniority_level", "employment_type", "apply_type",
                    "applicant_count", "applicant_count_qualifier")
JOB_URL_TEMPLATE = "https://www.linkedin.com/jobs/view/{}/"


def _parse_since(value):
    """'2h' / '3d' → (normalized value, days, hours); ValueError if invalid."""
    value = value.strip().lower()
    match = re.fullmatch(r"(\d+)([hd])", value)
    if not match:
        raise ValueError("use <N>h or <N>d, e.g. 2h or 3d")
    amount, unit = int(match.group(1)), match.group(2)
    hours = amount * 24 if unit == "d" else amount
    if amount < 1 or hours > SHORTLIST_MAX_SINCE_HOURS:
        raise ValueError("must be between 1h and %dd" % (SHORTLIST_MAX_SINCE_HOURS // 24))
    if unit == "d":
        return "%dd" % amount, amount, None
    return "%dh" % amount, None, amount


def _shortlist_item(job):
    item = {field: job.get(field) for field in SHORTLIST_FIELDS}
    keywords = item["matched_keywords"] or ""
    item["matched_keywords"] = [kw.strip() for kw in keywords.split(",") if kw.strip()]
    item["job_url"] = JOB_URL_TEMPLATE.format(job["linkedin_job_id"])
    return item


@app.route("/api/shortlist", methods=["GET"])
def api_shortlist():
    """Best jobs to apply to right now: recent, high-scoring, not applied."""
    params = dict(SHORTLIST_DEFAULTS)
    invalid = {}
    _, days, hours = _parse_since(SHORTLIST_DEFAULTS["since"])

    since_raw = request.args.get("since", "").strip()
    if since_raw:
        try:
            params["since"], days, hours = _parse_since(since_raw)
        except ValueError as e:
            invalid["since"] = str(e)

    min_score_raw = request.args.get("min_score", "").strip()
    if min_score_raw:
        try:
            min_score = float(min_score_raw)
            if not math.isfinite(min_score) or min_score < 0:
                raise ValueError
            params["min_score"] = min_score
        except ValueError:
            invalid["min_score"] = "must be a number >= 0"

    limit_raw = request.args.get("limit", "").strip()
    if limit_raw:
        try:
            limit = int(limit_raw)
            if not 1 <= limit <= SHORTLIST_MAX_LIMIT:
                raise ValueError
            params["limit"] = limit
        except ValueError:
            invalid["limit"] = "must be an integer between 1 and %d" % SHORTLIST_MAX_LIMIT

    apply_raw = request.args.get("apply", "").strip()
    if apply_raw:
        if apply_raw in SHORTLIST_APPLY_OPTIONS:
            params["apply"] = apply_raw
        else:
            invalid["apply"] = "must be one of: %s" % ", ".join(SHORTLIST_APPLY_OPTIONS)

    if invalid:
        return jsonify({"error": "invalid parameters", "invalid": invalid}), 400

    filters = dict(min_score=params["min_score"], days=days, hours=hours,
                   apply_type=None if params["apply"] == "all" else params["apply"],
                   hide_blacklisted=True, hide_aggregators=True,
                   hide_above_level=True, applied="hide")
    storage = SQLiteStorage()
    total = storage.count_job_summary(unique=True, **filters)
    jobs = storage.get_job_summary(unique=True, page=1, per_page=params["limit"],
                                   sort="weighted_score", direction="desc", **filters)
    items = [_shortlist_item(job) for job in jobs]
    return jsonify({"params": params, "total": total, "count": len(items),
                    "jobs": items})


if __name__ == "__main__":
    env.check_web_settings({"FLASK_DEBUG": env.FLASK_DEBUG, "HOST": env.HOST})
    app.run(host=env.HOST, port=env.PORT, debug=env.FLASK_DEBUG)
