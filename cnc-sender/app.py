from __future__ import annotations

import threading
import time
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request

from machine import Machine


BASE_DIR = Path(__file__).resolve().parent

with open(
    BASE_DIR / "config.yaml",
    "r",
    encoding="utf-8",
) as f:
    config = yaml.safe_load(f) or {}


machine = Machine(config)

app = Flask(__name__)


@app.get("/")
def index():
    return render_template(
        "index.html",
        machine_name=machine.name,
    )


@app.get("/api/status")
def api_status():
    # Ask FluidNC for a fresh realtime status report.
    machine.request_status()

    return jsonify(
        machine.status()
    )


@app.post("/api/connect")
def api_connect():
    try:
        machine.connect()

        return jsonify(
            machine.status()
        )

    except Exception as exc:
        return jsonify({
            "error": str(exc),
            **machine.status(),
        }), 500


@app.post("/api/disconnect")
def api_disconnect():
    machine.disconnect()

    return jsonify(
        machine.status()
    )


@app.post("/api/jog")
def api_jog():
    data = request.get_json(
        force=True
    )

    try:
        axis = str(
            data["axis"]
        )

        distance = float(
            data["distance"]
        )

        machine.jog(
            axis,
            distance,
        )

        return jsonify(
            machine.status()
        )

    except Exception as exc:
        return jsonify({
            "error": str(exc),
            **machine.status(),
        }), 400


@app.post("/api/move")
def api_move():
    data = request.get_json(
        force=True
    )

    try:
        x = float(
            data["x"]
        )

        y = float(
            data["y"]
        )

        machine.move_to(
            x,
            y,
        )

        return jsonify(
            machine.status()
        )

    except Exception as exc:
        return jsonify({
            "error": str(exc),
            **machine.status(),
        }), 400


@app.post("/api/home")
def api_home():
    data = request.get_json(
        force=True
    )

    try:
        axis = str(
            data.get(
                "axis",
                "ALL",
            )
        )

        machine.home(axis)

        return jsonify(
            machine.status()
        )

    except Exception as exc:
        return jsonify({
            "error": str(exc),
            **machine.status(),
        }), 400


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False,
    )
