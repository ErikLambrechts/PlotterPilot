"""Minimal FluidNC TCP client with realtime status parsing."""

from __future__ import annotations

import re
import socket
import threading
from typing import Callable, Optional


StatusCallback = Callable[[dict], None]


class FluidNC:
    """
    Small FluidNC TCP client.

    FluidNC normally exposes a serial-style TCP connection on port 23.

    Realtime status is requested with:

        ?

    and returned in a form similar to:

        <Idle|MPos:10.000,20.000,0.000|FS:0,0>

    The reader thread continuously consumes incoming controller data,
    allowing status responses to be processed without blocking the Flask
    application.
    """

    STATUS_RE = re.compile(r"<([^>]*)>")

    def __init__(
        self,
        host: str,
        port: int = 23,
        timeout: float = 3.0,
        status_callback: Optional[StatusCallback] = None,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout

        self.status_callback = status_callback

        self._socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_reader = threading.Event()

        self.connected = False
        self.last_error: Optional[str] = None

        self.status_data: dict = {}

    def connect(self) -> None:
        self.disconnect()

        try:
            sock = socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout,
            )

            # Don't use a persistent socket timeout for the reader.
            # The reader should wait for controller data.
            sock.settimeout(1.0)

            self._socket = sock
            self.connected = True
            self.last_error = None
            self._stop_reader.clear()

            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                name="fluidnc-reader",
                daemon=True,
            )

            self._reader_thread.start()

        except OSError as exc:
            self.connected = False
            self.last_error = str(exc)
            raise

    def disconnect(self) -> None:
        self._stop_reader.set()
        self.connected = False

        sock = self._socket
        self._socket = None

        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

            try:
                sock.close()
            except OSError:
                pass

        thread = self._reader_thread

        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=1.0)

        self._reader_thread = None

    def send(self, command: str) -> None:
        if not self.connected or self._socket is None:
            raise RuntimeError("Not connected to FluidNC")

        command = command.strip()

        if not command:
            return

        data = (command + "\n").encode("ascii")

        with self._lock:
            try:
                self._socket.sendall(data)
            except OSError as exc:
                self.connected = False
                self.last_error = str(exc)
                raise

    def realtime(self, character: str) -> None:
        """
        Send a FluidNC realtime command.

        '?' requests a controller status report.
        """

        if not self.connected or self._socket is None:
            raise RuntimeError("Not connected to FluidNC")

        with self._lock:
            try:
                self._socket.sendall(character.encode("ascii"))
            except OSError as exc:
                self.connected = False
                self.last_error = str(exc)
                raise

    def request_status(self) -> None:
        """
        Request current FluidNC status.

        '?' is a realtime command and does not need a newline.
        """

        self.realtime("?")

    def get_status(self) -> dict:
        return dict(self.status_data)

    def _reader_loop(self) -> None:
        buffer = b""

        while not self._stop_reader.is_set():
            sock = self._socket

            if sock is None:
                break

            try:
                chunk = sock.recv(4096)

                if not chunk:
                    self.connected = False
                    break

                buffer += chunk

                # FluidNC status reports are enclosed in <...>.
                while b"<" in buffer and b">" in buffer:
                    start = buffer.find(b"<")
                    end = buffer.find(b">", start)

                    if end < 0:
                        # Wait for the remainder.
                        if start > 0:
                            buffer = buffer[start:]
                        break

                    raw = buffer[start:end + 1]
                    buffer = buffer[end + 1:]

                    try:
                        text = raw.decode(
                            "ascii",
                            errors="replace",
                        )
                        status = self.parse_status(text)

                        if status:
                            self.status_data = status

                            if self.status_callback:
                                try:
                                    self.status_callback(status)
                                except Exception:
                                    pass

                    except Exception:
                        # Never allow malformed controller output to kill
                        # the reader thread.
                        continue

            except socket.timeout:
                continue

            except OSError as exc:
                if not self._stop_reader.is_set():
                    self.last_error = str(exc)

                self.connected = False
                break

    @classmethod
    def parse_status(cls, text: str) -> dict:
        """
        Parse a FluidNC/Grbl-style status response.

        Example:

            <Idle|MPos:10.000,20.000,0.000|FS:3000,0>

        Returns:

            {
                "state": "Idle",
                "machine_position": {
                    "x": 10.0,
                    "y": 20.0,
                    "z": 0.0
                },
                "feed": 3000.0,
                "spindle": 0.0
            }
        """

        match = cls.STATUS_RE.search(text)

        if not match:
            return {}

        body = match.group(1)
        fields = body.split("|")

        if not fields:
            return {}

        result = {
            "state": fields[0],
        }

        for field in fields[1:]:
            if ":" not in field:
                continue

            key, value = field.split(":", 1)

            if key == "MPos":
                values = value.split(",")

                if len(values) >= 3:
                    try:
                        result["machine_position"] = {
                            "x": float(values[0]),
                            "y": float(values[1]),
                            "z": float(values[2]),
                        }
                    except ValueError:
                        pass

            elif key == "WPos":
                values = value.split(",")

                if len(values) >= 3:
                    try:
                        result["work_position"] = {
                            "x": float(values[0]),
                            "y": float(values[1]),
                            "z": float(values[2]),
                        }
                    except ValueError:
                        pass

            elif key == "FS":
                values = value.split(",")

                if len(values) >= 2:
                    try:
                        result["feed"] = float(values[0])
                        result["spindle"] = float(values[1])
                    except ValueError:
                        pass

            elif key == "F":
                try:
                    result["feed"] = float(value)
                except ValueError:
                    pass

        return result

    def close(self) -> None:
        self.disconnect()
