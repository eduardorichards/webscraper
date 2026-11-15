import math

from flask import Flask, render_template, request, jsonify, url_for
from config import env
from utils.sqlite_storage import SQLiteStorage

app = Flask(__name__)

DAYS_OPTIONS = {"7", "14", "30", "all"}
PER_PAGE_OPTIONS = list(env.PER_PAGE_CHOICES)


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


@app.template_global()
def index_url(query_args, **overrides):
    """URL for the index page keeping current params, with some overridden."""
    args = {**query_args, **overrides}
    return url_for("index", **{k: v for k, v in args.items() if v != ""})


@app.route("/")
def index():
    try:
        min_score = max(0.0, float(request.args.get("min_score", 0)))
    except ValueError:
        min_score = 0.0
    if not math.isfinite(min_score):
        min_score = 0.0

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
    apply_raw = request.args.get("apply", "")
    if apply_raw not in SQLiteStorage.APPLY_FILTERS:
        apply_raw = ""

    # Checkbox is paired with a hidden "0" input, so the last value wins;
    # absent entirely (first visit) → hide by default.
    hide_values = request.args.getlist("hide_blacklisted")
    hide_blacklisted = hide_values[-1] == "1" if hide_values else True

    sort = request.args.get("sort", SQLiteStorage.DEFAULT_SORT)
    direction = request.args.get("dir", SQLiteStorage.DEFAULT_DIRECTION)
    if sort not in SQLiteStorage.SORT_COLUMNS or direction not in SQLiteStorage.SORT_DIRECTIONS:
        sort, direction = SQLiteStorage.DEFAULT_SORT, SQLiteStorage.DEFAULT_DIRECTION

    filters = dict(min_score=min_score, unique=True, days=days,
                   location=location or None, hours=hours,
                   hide_blacklisted=hide_blacklisted,
                   apply_type=apply_raw or None)

    storage = SQLiteStorage()
    total = storage.count_job_summary(**filters)
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    jobs = storage.get_job_summary(page=page, per_page=per_page, sort=sort,
                                   direction=direction, **filters)
    stats = storage.get_analysis_stats()
    blacklisted = storage.get_blacklisted_companies()

    start = (page - 1) * per_page + 1 if jobs else 0
    end = start + len(jobs) - 1 if jobs else 0

    # Normalized params used to build sort/pagination links
    query_args = {
        "min_score": min_score,
        "days": days_raw,
        "location": location,
        "hours": hours if hours is not None else "",
        "hide_blacklisted": "1" if hide_blacklisted else "0",
        "apply": apply_raw,
        "per_page": per_page,
        "sort": sort,
        "dir": direction,
        "page": page,
    }

    return render_template("index.html", jobs=jobs, stats=stats,
                           min_score=min_score, blacklisted=blacklisted,
                           days=days_raw, location=location, hours=hours,
                           hide_blacklisted=hide_blacklisted, apply=apply_raw,
                           per_page=per_page, per_page_options=PER_PAGE_OPTIONS,
                           sort=sort, direction=direction,
                           page=page, total=total, total_pages=total_pages,
                           start=start, end=end, query_args=query_args)


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


if __name__ == "__main__":
    env.check_web_settings({"FLASK_DEBUG": env.FLASK_DEBUG, "HOST": env.HOST})
    app.run(host=env.HOST, port=env.PORT, debug=env.FLASK_DEBUG)
