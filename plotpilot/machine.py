import threading
from PySide6.QtCore import QThread, Signal


"""
PlotPilot module extracted from plotpilot.py.

This module is intentionally conservative.
The first refactor keeps the existing implementation intact.
"""

class FluidNCController:

    def __init__(
        self,
        host,
        port,
    ):

        self.host = host
        self.port = port

        self.state = MachineState()

        self.session = requests.Session()

        self._lock = threading.Lock()

    @property
    def base_url(self):
        return (
            f"http://{self.host}:{self.port}"
        )

    def connect(self):

        response = self.session.get(
            self.base_url + "/",
            timeout=3,
        )

        response.raise_for_status()

        with self._lock:
            self.state.connected = True
            self.state.state = "Connected"
            self.state.message = ""

    def disconnect(self):

        with self._lock:
            self.state.connected = False
            self.state.state = "Disconnected"

    def send_command(
        self,
        command,
    ):

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

    def poll_status(self):

        if not self.state.connected:
            return

        try:

            response = self.session.get(
                self.base_url + "/command",
                params={"cmd": "?"},
                timeout=2,
            )

            response.raise_for_status()

            self.parse_status(
                response.text
            )

        except Exception as exc:

            self.state.message = str(exc)
            self.state.connected = False
            self.state.state = (
                "Connection lost"
            )

    def parse_status(self, text):

        for raw in text.splitlines():

            line = raw.strip()

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
                            self.state.x = float(
                                values[0]
                            )
                            self.state.y = float(
                                values[1]
                            )
                            self.state.z = float(
                                values[2]
                            )
                        except ValueError:
                            pass

                elif field.startswith("FS:"):

                    values = field[3:].split(",")

                    try:

                        if values:
                            self.state.feed = float(
                                values[0]
                            )

                        if len(values) > 1:
                            self.state.spindle = float(
                                values[1]
                            )

                    except ValueError:
                        pass

    def jog(
        self,
        x=0,
        y=0,
        z=0,
    ):

        parts = []

        if x:
            parts.append(
                f"X{x:g}"
            )

        if y:
            parts.append(
                f"Y{y:g}"
            )

        if z:
            parts.append(
                f"Z{z:g}"
            )

        if not parts:
            return

        self.send_command(
            "$J=G91 G21 F2000 "
            + " ".join(parts)
        )

    def home(self, axis=None):

        if axis is None:
            command = "$H"
        else:
            command = f"$H{axis}"

        self.send_command(command)

    def set_zero(self):

        self.send_command(
            "G10 L20 P1 X0 Y0 Z0"
        )

    def move_to(
        self,
        x,
        y,
        z,
    ):

        self.send_command(
            f"G90 G21 G0 "
            f"X{x:g} "
            f"Y{y:g} "
            f"Z{z:g}"
        )



class ConnectWorker(QThread):

    succeeded = Signal()
    failed = Signal(str)

    def __init__(
        self,
        machine,
    ):
        super().__init__()
        self.machine = machine

    def run(self):

        try:
            self.machine.connect()
            self.succeeded.emit()

        except Exception as exc:
            self.failed.emit(
                str(exc)
            )
