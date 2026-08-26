from __future__ import annotations

import threading

import requests


class MachineState:
    def __init__(self):
        self.connected = False
        self.state = "Disconnected"
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.feed = 0.0
        self.spindle = 0.0
        self.message = ""


class FluidNC:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.state = MachineState()
        self.session = requests.Session()

    @property
    def base_url(self):
        return f"http://{self.host}:{self.port}"

    def connect(self):
        response = self.session.get(
            self.base_url + "/",
            timeout=3,
        )
        response.raise_for_status()

        self.state.connected = True
        self.state.state = "Connected"

        self.poll()

    def disconnect(self):
        self.state.connected = False
        self.state.state = "Disconnected"

    def command(self, command):
        if not self.state.connected:
            raise RuntimeError(
                "Machine is not connected"
            )

        response = self.session.get(
            self.base_url + "/command",
            params={"cmd": command},
            timeout=5,
        )

        response.raise_for_status()
        return response.text

    def poll(self):
        if not self.state.connected:
            return

        response = self.session.get(
            self.base_url + "/command",
            params={"cmd": "?"},
            timeout=2,
        )

        response.raise_for_status()
        self.parse_status(response.text)

    def parse_status(self, text):
        for line in text.splitlines():
            line = line.strip()

            if not (
                line.startswith("<")
                and line.endswith(">")
            ):
                continue

            fields = line[1:-1].split("|")

            if not fields:
                continue

            self.state.state = fields[0]

            for field in fields[1:]:
                if field.startswith("MPos:"):
                    values = field[5:].split(",")

                    if len(values) >= 3:
                        try:
                            self.state.x = float(values[0])
                            self.state.y = float(values[1])
                            self.state.z = float(values[2])
                        except ValueError:
                            pass

                elif field.startswith("FS:"):
                    values = field[3:].split(",")

                    try:
                        if values:
                            self.state.feed = float(values[0])

                        if len(values) > 1:
                            self.state.spindle = float(values[1])
                    except ValueError:
                        pass

    def jog(self, x=0, y=0, z=0):
        parts = []

        if x:
            parts.append(f"X{x:g}")

        if y:
            parts.append(f"Y{y:g}")

        if z:
            parts.append(f"Z{z:g}")

        if parts:
            self.command(
                "$J=G91 G21 F2000 "
                + " ".join(parts)
            )

    def home(self, axis=None):
        self.command(
            "$H" if axis is None else f"$H{axis}"
        )

    def zero(self):
        self.command(
            "G10 L20 P1 X0 Y0 Z0"
        )

    def move_to(self, x, y, z):
        self.command(
            f"G90 G21 G0 X{x:g} Y{y:g} Z{z:g}"
        )
