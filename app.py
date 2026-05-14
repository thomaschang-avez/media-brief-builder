"""
app.py — MEDIA BRIEF BUILDER
Flask webhook. Accepts POST /brief with JSON body, returns 202 immediately,
runs the pipeline in a background thread. Slack DM is sent on completion.

Run locally: python3 app.py
Production:  gunicorn app:app (Railway)
"""

import os
import sys
import threading
sys.path.insert(0, os.path.dirname(__file__))


def _bootstrap_adc():
    """On Railway, write DRIVE_ADC_BASE64 to the standard gcloud ADC path
    so any google library that reads ADC implicitly finds valid credentials."""
    b64 = os.environ.get("DRIVE_ADC_BASE64")
    if not b64:
        return
    import base64
    adc_dir = os.path.expanduser("~/.config/gcloud")
    os.makedirs(adc_dir, exist_ok=True)
    adc_path = os.path.join(adc_dir, "application_default_credentials.json")
    with open(adc_path, "wb") as f:
        f.write(base64.b64decode(b64))


_bootstrap_adc()

from flask import Flask, request, jsonify
from config import BriefRequest, BRIEF_TYPES, SLACK_BOT_TOKEN
from crew import run_brief

app = Flask(__name__)

# Required fields — every submission must include these.
REQUIRED_FIELDS = [
    "client_name",
    "exec_name",
    "reporter_url",
    "brief_type",
    "interview_date",
    "interview_time",
    "virtual_or_inperson",
    "topic",
    "on_record",
    "staffed",
    "submitter_email",
]

# All optional BriefRequest fields. Any field in the JSON body that matches
# one of these is passed through. Unknown keys are silently ignored so the
# Apps Script schema can evolve without breaking this endpoint.
OPTIONAL_FIELDS = [
    "location_or_link",
    "staffer_name",
    "additional_context",
    "host_name",
    "show_links",
    "expected_topics",
    "show_name",
    "recent_episodes_url",
    "arrival_time",
    "hit_time",
    "segment_length",
    "prior_appearance_urls",
    "client_logo_url",
    "reporter_headshot_url",
]


def _run_in_background(brief_request: BriefRequest) -> None:
    """Run the brief pipeline in a background thread.

    run_brief() already sends Slack DMs on success, qa_failed, and known
    errors. This wrapper catches any unexpected exception that escapes
    run_brief() and sends a crash DM to the submitter so no failure is silent.
    """
    try:
        run_brief(brief_request)
    except Exception as exc:
        try:
            from slack_sdk import WebClient
            client = WebClient(token=SLACK_BOT_TOKEN)
            msg = (
                f"Brief generation crashed unexpectedly for "
                f"*{brief_request.client_name} x {brief_request.exec_name}*.\n"
                f"Error: `{type(exc).__name__}: {exc}`\n"
                f"Please check the error logs or contact your system administrator."
            )
            client.chat_postMessage(
                channel=brief_request.submitter_slack_id,
                text=msg,
            )
        except Exception:
            pass


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/brief", methods=["POST"])
def brief():
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"status": "error", "error": "Request body must be JSON"}), 400

    # Validate required fields
    missing = [f for f in REQUIRED_FIELDS if not body.get(f)]
    if missing:
        return jsonify({
            "status": "error",
            "error": f"Missing required fields: {', '.join(missing)}",
        }), 400

    # Validate brief_type
    brief_type = body["brief_type"]
    if brief_type not in BRIEF_TYPES:
        return jsonify({
            "status": "error",
            "error": f"Invalid brief_type '{brief_type}'. Must be one of: {', '.join(BRIEF_TYPES)}",
        }), 400

    # Build kwargs — required fields first, then any optional fields present in body
    kwargs = {f: body[f] for f in REQUIRED_FIELDS}
    for f in OPTIONAL_FIELDS:
        if f in body:
            kwargs[f] = body[f]

    brief_request = BriefRequest(**kwargs)

    thread = threading.Thread(
        target=_run_in_background,
        args=(brief_request,),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "status": "accepted",
        "message": "Brief is being generated. You will receive a Slack DM when it is ready.",
    }), 202


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
