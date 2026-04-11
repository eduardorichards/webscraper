from flask import Flask, render_template, request, jsonify
from utils.sqlite_storage import SQLiteStorage

app = Flask(__name__)


@app.route("/")
def index():
    min_score = float(request.args.get("min_score", 0))

    storage = SQLiteStorage()
    jobs = storage.get_job_summary(min_score=min_score, unique=True)
    stats = storage.get_analysis_stats()
    blacklisted = storage.get_blacklisted_companies()

    return render_template("index.html", jobs=jobs, stats=stats,
                           min_score=min_score, blacklisted=blacklisted)


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
    app.run(host="0.0.0.0", port=5000, debug=False)
