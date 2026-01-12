"""Flask control panel for Predictipulse."""

import json
import os
import time
from typing import Any, Dict, Iterable

from flask import Flask, Response, jsonify, render_template, request

from config_manager import ConfigManager
from predictipulse_engine import PredictipulseEngine

app = Flask(__name__)


# Custom Jinja filter for timestamps
@app.template_filter("timestamp_fmt")
def timestamp_fmt(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))

# Initialize configuration and engine
config_manager = ConfigManager()
config = config_manager.load()
demo_mode = os.environ.get("DEMO_MODE", "false").lower() == "true"
engine = PredictipulseEngine(config=config, demo_mode=demo_mode)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------
def sse_format(data: str) -> str:
    return f"data: {data}\n\n"


def stream_logs() -> Iterable[str]:
    while True:
        log = engine.next_log(timeout=1.0)
        if log:
            yield sse_format(json.dumps({"log": log}))


def stream_opportunities() -> Iterable[str]:
    while True:
        opp = engine.next_opportunity(timeout=1.0)
        if opp:
            yield sse_format(json.dumps(opp))


def stream_trades() -> Iterable[str]:
    while True:
        trade = engine.next_trade(timeout=1.0)
        if trade:
            yield sse_format(json.dumps(trade))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    stats = engine.get_stats()
    return render_template(
        "index.html",
        config=config_manager.load(),
        running=engine.is_running(),
        stats=stats,
        trades=engine.get_recent_trades(20),
    )


@app.route("/api/start", methods=["POST"])
def api_start():
    engine.start()
    return jsonify({"running": True, "stats": engine.get_stats()})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    engine.stop()
    return jsonify({"running": False, "stats": engine.get_stats()})


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "running": engine.is_running(),
        "config": engine.get_config(),
        "stats": engine.get_stats(),
    })


@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify(engine.get_stats())


@app.route("/api/uplink", methods=["POST"])
def api_uplink():
    """Check Kalshi API connection status."""
    try:
        result = engine.check_kalshi_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({"connected": False, "error": str(e)})


@app.route("/api/trades", methods=["GET"])
def api_trades():
    return jsonify(engine.get_recent_trades(50))


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify(config_manager.load())
    data: Dict[str, Any] = request.get_json(force=True) or {}
    config_manager.save(data)
    engine.update_config(data)
    return jsonify({"ok": True, "config": engine.get_config()})


@app.route("/stream/logs")
def api_stream_logs():
    return Response(
        stream_logs(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.route("/stream/opportunities")
def api_stream_opportunities():
    return Response(
        stream_opportunities(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.route("/stream/trades")
def api_stream_trades():
    return Response(
        stream_trades(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True, use_reloader=False)
