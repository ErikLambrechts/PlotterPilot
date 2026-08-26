from __future__ import annotations

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
    def __init__(self, host: str, port: int):
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
        self.state.message = ""

    def disconnect(self):
        self.state.connected = False
        self.state.state = "Disconnected"

    def send(self, command: str):
        if not self.state.connected:
            raise RuntimeError("Machine is not connected")

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

        try:
            text = self.send("?")

            for line in text.splitlines():
                line = line.strip()

                if not line.startswith("<"):
                    continue

                fields = line[1:].rstrip(">").split("|")

                if fields:
                    self.state.state = fields[0]

                for field in fields[1:]:
                    if field.startswith("MPos:"):
                        values = field[5:].split(",")

                        if len(values) >= 3:
                            self.state.x = float(values[0])
                            self.state.y = float(values[1])
                            self.state.z = float(values[2])

                    elif field.startswith("FS:"):
                        values = field[3:].split(",")

                        if values:
                            self.state.feed = float(values[0])

                        if len(values) > 1:
                            self.state.spindle = float(values[1])

        except Exception as exc:
            self.state.message = str(exc)
            self.disconnect()
            self.state.state = "Connection lost"

    def jog(self, x=0, y=0, z=0):
        parts = []

        if x:
            parts.append(f"X{x:g}")

        if y:
            parts.append(f"Y{y:g}")

        if z:
            parts.append(f"Z{z:g}")

        if parts:
            self.send(
                "$J=G91 G21 F2000 " + " ".join(parts)
            )

    def home(self, axis=None):
        self.send("$H" if axis is None else f"$H{axis}")

    def zero(self, axis=None):
        if axis is None:
            self.send("G10 L20 P1 X0 Y0 Z0")
        else:
            self.send(f"G10 L20 P1 {axis}0")

    def move_to(self, x, y, z=None):
        if z is None:
            z = self.state.z

        self.send(
            f"G90 G21 G0 X{x:g} Y{y:g} Z{z:g}"
        )
