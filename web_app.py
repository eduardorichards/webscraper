from flask import Flask, render_template, request
from utils.sqlite_storage import SQLiteStorage

app = Flask(__name__)


@app.route("/")
def index():
    unique = request.args.get("unique", "1") == "1"
    min_score = float(request.args.get("min_score", 0))

    storage = SQLiteStorage()
    jobs = storage.get_job_summary(min_score=min_score, unique=unique)
    stats = storage.get_analysis_stats()

    return render_template("index.html", jobs=jobs, stats=stats,
                           unique=unique, min_score=min_score)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
