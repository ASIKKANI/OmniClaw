"""
server.py — OmniClaw Web Server.

Serves the web UI and streams orchestrator events via SSE.

Endpoints:
  GET  /            — Serve index.html
  GET  /api/run     — Start orchestrator for a goal (SSE stream)
  POST /api/skip    — Stop current task
  POST /api/stop    — Stop everything
"""

import json
import os
import threading

from dotenv import load_dotenv
from flask import Flask, Response, request, send_from_directory

import orchestrator

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")

_skip = threading.Event()
_abort = threading.Event()


class StopChecker:
    """Wrap skip/abort events for the orchestrator."""
    def __init__(self, skip_event, abort_event):
        self._skip = skip_event
        self._abort = abort_event

    def __call__(self):
        return self._skip.is_set() or self._abort.is_set()

    def _clear(self):
        self._skip.clear()


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/run")
def run():
    goal = request.args.get("goal", "").strip()
    if not goal:
        return Response("Missing 'goal'", status=400)

    _skip.clear()
    _abort.clear()

    checker = StopChecker(_skip, _abort)

    def generate():
        for event in orchestrator.run_stream(goal, should_stop=checker):
            if _abort.is_set():
                yield "data: " + json.dumps({"type": "stopped", "message": "Stopped by user."}) + "\n\n"
                return
            yield "data: " + json.dumps(event) + "\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/skip", methods=["POST"])
def skip():
    """Skip current task."""
    _skip.set()
    return Response(json.dumps({"ok": True, "action": "skip"}), mimetype="application/json")


@app.route("/api/stop", methods=["POST"])
def stop():
    """Stop everything."""
    _skip.set()
    _abort.set()
    return Response(json.dumps({"ok": True, "action": "stop"}), mimetype="application/json")


if __name__ == "__main__":
    api_key = os.getenv("LLAMA_API_KEY") or os.getenv("NVIDIA_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("❌ No API key found. Set LLAMA_API_KEY or NVIDIA_API_KEY in .env")
        exit(1)

    print("\n🦀 OmniClaw Web Server")
    print("   Open http://localhost:5000 in your browser\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
