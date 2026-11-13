"""Bathroom Kindle dashboard server. Runs on your own always-on machine, exposed via Tailscale
Funnel. Every route requires a bearer token -- see
~/.config/kindle_dashboard/config.json.
"""

import hmac
import json
import os
from datetime import datetime

import requests
from flask import Flask, abort, request, send_file

from render import INTERVALS_BASE_URL, load_intervals_config, load_kd_config, render_dashboard

app = Flask(__name__)

DASHBOARD_PATH = "/tmp/kindle_dashboard.png"


def _check_auth():
    cfg = load_kd_config()
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        abort(401)
    token = auth[len("Bearer "):]
    if not hmac.compare_digest(token, cfg["bearer_token"]):
        abort(401)


@app.route("/dashboard.png")
def dashboard():
    _check_auth()
    render_dashboard(DASHBOARD_PATH)
    return send_file(DASHBOARD_PATH, mimetype="image/png")


@app.route("/weight", methods=["POST"])
def weight():
    _check_auth()
    body = request.get_json(force=True)
    value = float(body["value"])
    now = datetime.now()
    timestamp = body.get("timestamp") or now.isoformat()
    date = timestamp[:10]

    # Source of truth for the dashboard chart: every reading, full
    # timestamp, multiple/day expected. Append-only.
    cfg = load_kd_config()
    log_path = cfg["weight_log_path"]
    entries = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            entries = json.load(f)
    entries.append({"timestamp": timestamp, "value": value})
    with open(log_path, "w") as f:
        json.dump(entries, f, indent=2)

    # Secondary write-through: intervals.icu only holds one value per
    # date, so this just keeps the day's LATEST reading there for your
    # other tools (training-brief.py etc.) -- not the dashboard's source.
    icu_cfg = load_intervals_config()
    athlete_id = icu_cfg["athlete_id"]
    api_key = icu_cfg["api_key"]
    auth = ("API_KEY", api_key)

    # Read-modify-write: fetch whatever already exists for this date (HRV,
    # sleep, resting HR from the Garmin sync) and merge weight in, rather
    # than trusting an unconfirmed assumption about whether intervals.icu's
    # PUT is a partial or full-record update.
    get_url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/wellness/{date}"
    existing = requests.get(get_url, auth=auth, timeout=10)
    record = existing.json() if existing.ok else {}
    record["weight"] = value

    put_url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/wellness/{date}"
    resp = requests.put(put_url, json=record, auth=auth, timeout=10)
    resp.raise_for_status()

    return {"ok": True, "timestamp": timestamp, "weight": value}


@app.route("/mood", methods=["POST"])
def mood():
    _check_auth()
    body = request.get_json(force=True)
    value = float(body["value"])
    if not (0.5 <= value <= 5.0) or (value * 2) != int(value * 2):
        abort(400, "mood value must be 0.5-5.0 in half-star steps")
    date = body.get("date") or datetime.now().strftime("%Y-%m-%d")

    cfg = load_kd_config()
    log_path = cfg["mood_log_path"]
    entries = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            entries = json.load(f)
    entries = [e for e in entries if e["date"] != date]  # one entry per day
    entries.append({"date": date, "value": value})
    with open(log_path, "w") as f:
        json.dump(entries, f, indent=2)

    return {"ok": True, "date": date, "mood": value}


if __name__ == "__main__":
    cfg = load_kd_config()
    app.run(host="127.0.0.1", port=cfg["port"])
