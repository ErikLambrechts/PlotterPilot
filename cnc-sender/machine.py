"""Machine abstraction for Plotbot."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from fluidnc import FluidNC


@dataclass
class Position:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Machine:
    def __init__(self, config: dict):
        machine_config = config.get("machine", {})
        connection_config = config.get("connection", {})
        jog_config = config.get("jog", {})

        self.name = machine_config.get(
            "name",
            "Plotbot",
        )

        self.width = float(
            machine_config.get("width", 300)
        )

        self.height = float(
            machine_config.get("height", 200)
        )

        self.z_min = float(
            machine_config.get("z_min", -5)
        )

        self.z_max = float(
            machine_config.get("z_max", 20)
        )

        self.host = connection_config.get(
            "host",
            "plotbot.local",
        )

        self.port = int(
            connection_config.get("port", 23)
        )

        self.timeout = float(
            connection_config.get("timeout", 3)
        )

        self.jog_steps = jog_config.get(
            "steps",
            [0.1, 1, 10, 50],
        )

        self.default_step = float(
            jog_config.get(
                "default_step",
                1,
            )
        )

        self.position = Position()

        self.state = "Disconnected"
        self.last_error: Optional[str] = None
        self.last_command: Optional[str] = None

        self.feed = 0.0
        self.spindle = 0.0

        self._lock = threading.Lock()

        self.fluidnc = FluidNC(
            self.host,
            self.port,
            self.timeout,
            status_callback=self._on_status,
        )

    @property
    def connected(self) -> bool:
        return self.fluidnc.connected

    def connect(self) -> None:
        with self._lock:
            self.state = "Connecting"
            self.last_error = None

        try:
            self.fluidnc.connect()

            with self._lock:
                self.state = "Connected"

            # Immediately request the real controller position.
            self.fluidnc.request_status()

        except Exception as exc:
            with self._lock:
                self.state = "Error"
                self.last_error = str(exc)

            raise

    def disconnect(self) -> None:
        self.fluidnc.disconnect()

        with self._lock:
            self.state = "Disconnected"

    def _on_status(self, status: dict) -> None:
        """
        Called by FluidNC whenever a realtime status report
        is received from the controller.
        """

        with self._lock:
            controller_state = status.get("state")

            if controller_state:
                self.state = controller_state

            machine_position = status.get(
                "machine_position"
            )

            if machine_position:
                self.position = Position(
                    x=machine_position["x"],
                    y=machine_position["y"],
                    z=machine_position["z"],
                )

            if "feed" in status:
                self.feed = status["feed"]

            if "spindle" in status:
                self.spindle = status["spindle"]

            self.last_error = None

    def send_gcode(self, command: str) -> None:
        if not self.connected:
            raise RuntimeError(
                "Machine is not connected"
            )

        command = command.strip()

        if not command:
            return

        self.fluidnc.send(command)

        with self._lock:
            self.last_command = command

    def jog(
        self,
        axis: str,
        distance: float,
    ) -> None:
        axis = axis.upper()

        if axis not in {"X", "Y", "Z"}:
            raise ValueError("Invalid axis")

        distance = float(distance)

        # FluidNC jog command.
        #
        # G91 = incremental positioning
        # G21 = millimetres
        #
        # F3000 is deliberately conservative for a plotter.
        command = (
            f"$J=G91 G21 "
            f"{axis}{distance:g} "
            f"F3000"
        )

        self.send_gcode(command)

    def move_to(
        self,
        x: float,
        y: float,
    ) -> None:
        x = float(x)
        y = float(y)

        x = max(
            0,
            min(self.width, x),
        )

        y = max(
            0,
            min(self.height, y),
        )

        self.send_gcode(
            f"G90 G21 G0 "
            f"X{x:.3f} "
            f"Y{y:.3f}"
        )

    def home(self, axis: str) -> None:
        axis = axis.upper()

        if axis == "X":
            self.send_gcode("$HX")

        elif axis == "Y":
            self.send_gcode("$HY")

        elif axis in {"XY", "ALL"}:
            self.send_gcode("$H")

        else:
            raise ValueError(
                "Invalid homing axis"
            )

    def request_status(self) -> None:
        if not self.connected:
            return

        try:
            self.fluidnc.request_status()
        except Exception as exc:
            with self._lock:
                self.state = "Error"
                self.last_error = str(exc)

    def status(self) -> dict:
        with self._lock:
            return {
                "connected": self.connected,

                "state": self.state,

                "host": self.host,

                "port": self.port,

                "position": {
                    "x": self.position.x,
                    "y": self.position.y,
                    "z": self.position.z,
                },

                "machine": {
                    "name": self.name,
                    "width": self.width,
                    "height": self.height,
                    "z_min": self.z_min,
                    "z_max": self.z_max,
                },

                "feed": self.feed,

                "spindle": self.spindle,

                "last_command": self.last_command,

                "last_error": self.last_error,

                "controller_status":
                    self.fluidnc.get_status(),
            }
