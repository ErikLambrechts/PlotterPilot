#!/usr/bin/env python3

from __future__ import annotations

import json
import logging
import math
import re
import socket
import subprocess
from datetime import datetime, timedelta
import sys

import os
import signal
import subprocess
import tempfile
import threading
import time
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import requests

from PySide6.QtCore import (
    QPointF,
    QRectF,
    QThread,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
)
try:
    from .state_store import StateStore
except ImportError:
    from state_store import StateStore


# ============================================================
# Configuration
# ============================================================

CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "default.json"
)


@dataclass
class Anchor:
    name: str
    x: float
    y: float


@dataclass
class Workspace:
    width: float
    height: float
    depth: float = 0.0
    anchors: list[Anchor] = field(default_factory=list)

    # Preview settings shared with Job Properties.
    preview_limit: int = 20000
    show_drawing: bool = True
    show_travel: bool = True


@dataclass
class ConversionProfile:
    name: str
    command: str
    description: str = ""
    input_type: str | None = None
    output_type: str | None = None
    parameters: dict = field(default_factory=dict)


@dataclass
class MachineConfig:
    host: str
    port: int
    workspace: Workspace
    log_level: str = "INFO"
    profiles: list[ConversionProfile] = field(
        default_factory=list
    )


logger = logging.getLogger(__name__)
state_store = StateStore()


def show_warning(parent, title, message):
    logger.warning(
        "%s: %s",
        title,
        message,
    )
    QMessageBox.warning(
        parent,
        title,
        str(message),
    )


def show_critical(parent, title, message):
    logger.error(
        "%s: %s",
        title,
        message,
    )
    QMessageBox.critical(
        parent,
        title,
        str(message),
    )


def profile_command(
    profile: Path | str,
    *args: str,
) -> list[str]:
    profile_path = Path(profile)

    if profile_path.suffix.lower() == ".py":
        return [sys.executable, str(profile_path), *args]
    if profile_path.suffix.lower() == ".sh":
        return ["bash", str(profile_path), *args]

    return [str(profile_path), *args]


def load_config(path: Path) -> MachineConfig:
    """
    Load PlotPilot configuration.

    The loader deliberately accepts a few equivalent representations
    so that configuration files remain easy to edit by hand.

    Supported anchors:

        "anchors": [
            {"name": "A", "x": 0, "y": 0},
            {"name": "B", "x": 100, "y": 100}
        ]

    and:

        "anchors": {
            "A": {"x": 0, "y": 0},
            "B": {"x": 100, "y": 100}
        }

    Profiles are passed through by the rest of the application and are
    therefore not interpreted here.
    """

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(
            f"Configuration root must be an object: {path}"
        )

    machine = data.get("machine")

    if machine is None:
        raise ValueError(
            "Configuration is missing 'machine'."
        )

    if not isinstance(machine, dict):
        raise ValueError(
            "'machine' must be an object."
        )

    workspace_data = machine.get("workspace", {})

    if not isinstance(workspace_data, dict):
        raise ValueError(
            "'machine.workspace' must be an object."
        )

    def as_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def as_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    # --------------------------------------------------------
    # Anchors
    # --------------------------------------------------------

    anchors = []

    raw_anchors = workspace_data.get("anchors", [])

    if isinstance(raw_anchors, dict):
        # Mapping form:
        #
        # anchors:
        #   home:
        #     x: 0
        #     y: 0
        #
        for name, raw in raw_anchors.items():

            if not isinstance(raw, dict):
                continue

            anchors.append(
                Anchor(
                    name=str(raw.get("name", name)),
                    x=as_float(raw.get("x", 0)),
                    y=as_float(raw.get("y", 0)),
                )
            )

    elif isinstance(raw_anchors, list):
        # List form:
        #
        # anchors:
        #   - name: home
        #     x: 0
        #     y: 0
        #
        for raw in raw_anchors:

            # Ignore malformed/string entries instead of crashing
            # the whole application.
            if not isinstance(raw, dict):
                continue

            name = raw.get("name")

            if name is None:
                continue

            anchors.append(
                Anchor(
                    name=str(name),
                    x=as_float(raw.get("x", 0)),
                    y=as_float(raw.get("y", 0)),
                )
            )

    # --------------------------------------------------------
    # Machine connection
    # --------------------------------------------------------

    host = machine.get("host", "192.168.4.1")
    port = machine.get("port", 80)
    log_level = str(
        machine.get("log_level", "INFO")
    )

    # --------------------------------------------------------
    # --------------------------------------------------------
    # Conversion profiles
    # --------------------------------------------------------
    #
    # Profiles are executable shell scripts.
    #
    # Their metadata is obtained through:
    #
    #     <profile>.sh --json
    #
    # --------------------------------------------------------

    profiles = []

    configured_profiles = machine.get(
        "conversion_profiles",
        "config/conversion_profiles",
    )
    profile_directory = Path(
        str(configured_profiles)
    )

    if not profile_directory.is_absolute():
        profile_directory = (
            path.parent.parent
            / profile_directory
        ).resolve()

    print(
        "RUNTIME PROFILE DISCOVERY: directory =",
        profile_directory,
        flush=True,
    )

    if not profile_directory.is_dir():
        print(
            "RUNTIME PROFILE DISCOVERY: directory missing",
            flush=True,
        )
    else:
        for command in sorted(
            profile_directory.iterdir()
        ):
            if not command.is_file():
                continue

            suffix = command.suffix.lower()

            if suffix not in {".sh", ".py"} and not os.access(
                command,
                os.X_OK,
            ):
                continue
            try:
                result = subprocess.run(
                    profile_command(
                        command,
                        "--json",
                    ),
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode != 0:
                    raise RuntimeError(
                        result.stderr.strip()
                        or result.stdout.strip()
                        or (
                            "profile --json failed "
                            f"({result.returncode})"
                        )
                    )

                metadata = json.loads(
                    result.stdout
                )

                if not isinstance(
                    metadata,
                    dict,
                ):
                    print(
                        "RUNTIME PROFILE DISCOVERY:"
                        " invalid metadata",
                        command,
                        flush=True,
                    )
                    continue

                parameters = metadata.get(
                    "parameters",
                    {},
                )

                if not isinstance(
                    parameters,
                    dict,
                ):
                    parameters = {}

                name = metadata.get(
                    "name"
                )

                if not name:
                    name = command.stem.replace(
                        "_",
                        "-",
                    )

                profile = ConversionProfile(
                    name=str(name),
                    command=str(command),
                    description=str(
                        metadata.get(
                            "description",
                            "",
                        )
                    ),
                    input_type=(
                        str(
                            metadata.get(
                                "input",
                                {},
                            ).get("type")
                        )
                        if isinstance(
                            metadata.get("input"),
                            dict,
                        )
                        and metadata.get(
                            "input",
                            {},
                        ).get("type")
                        is not None
                        else None
                    ),
                    output_type=(
                        str(
                            metadata.get(
                                "output",
                                {},
                            ).get("type")
                        )
                        if isinstance(
                            metadata.get("output"),
                            dict,
                        )
                        and metadata.get(
                            "output",
                            {},
                        ).get("type")
                        is not None
                        else None
                    ),
                    parameters=parameters,
                )

                profiles.append(
                    profile
                )

                print(
                    "RUNTIME PROFILE DISCOVERY:"
                    " loaded",
                    profile.name,
                    flush=True,
                )

            except Exception as exc:
                print(
                    "WARNING: failed to load conversion "
                    "profile",
                    command,
                    ":",
                    exc,
                    file=sys.stderr,
                    flush=True,
                )

    print(
        "RUNTIME PROFILE DISCOVERY: total =",
        len(profiles),
        flush=True,
    )

    return MachineConfig(
        host=str(host),
        port=as_int(port, 80),
        workspace=Workspace(
            width=as_float(
                workspace_data.get("width", 300),
                300,
            ),
            height=as_float(
                workspace_data.get("height", 300),
                300,
            ),
            depth=as_float(
                workspace_data.get("depth", 0),
                0,
            ),
            anchors=anchors,
        ),
        log_level=log_level,
        profiles=profiles,
    )



# ============================================================
# Jobs
# ============================================================

class JobSourceType(str, Enum):
    SVG = "svg"
    GCODE = "gcode"
    DUMMY = "dummy"


@dataclass
class Transform:
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    scale: float = 1.0
    rotation: float = 0.0
    flip_x: bool = False
    flip_y: bool = False

    flip_x_keep_bbox: bool = False
    flip_y_keep_bbox: bool = False


@dataclass
class Job:
    name: str
    source: Path
    source_type: JobSourceType

    id: str = field(
        default_factory=lambda: str(
            uuid.uuid4()
        )
    )

    active: bool = True
    visible: bool = True

    origin: str = "machine"

    transform: Transform = field(
        default_factory=Transform
    )

    repeated_anchors: list[str] = field(
        default_factory=list
    )

    gcode: str | None = None

    source_svg_id: str | None = None
    generated_from_svg: bool = False

    conversion_profile: str | None = None
    conversion_parameters: dict = field(
        default_factory=dict
    )
    pipeline_steps: list[dict] = field(
        default_factory=list
    )

    preview_limit: int = 15000

    stats: dict = field(
        default_factory=dict
    )


class JobManager:

    def __init__(self):
        self.jobs: list[Job] = []

    def add_file(self, path: Path) -> Job:
        suffix = path.suffix.lower()

        if suffix == ".svg":
            source_type = JobSourceType.SVG

        elif suffix in (
            ".gcode",
            ".nc",
            ".ngc",
        ):
            source_type = JobSourceType.GCODE

        else:
            raise ValueError(
                f"Unsupported file type: {suffix}"
            )

        job = Job(
            name=path.name,
            source=path,
            source_type=source_type,
        )

        if source_type == JobSourceType.GCODE:
            job.gcode = path.read_text(
                encoding="utf-8"
            )
            job.stats = analyze_gcode(
                job.gcode
            )

        self.jobs.append(job)

        return job

    def add_dummy(self, name="Dummy job") -> Job:
        job = Job(
            name=name,
            source=Path("dummy.job"),
            source_type=JobSourceType.DUMMY,
            active=False,
        )
        self.jobs.append(job)
        return job

    def create_generated_gcode(
        self,
        source_svg: Job,
        gcode: str,
        profile: str,
        parameters: dict,
    ) -> Job:

        job = Job(
            name=(
                Path(
                    source_svg.name
                ).stem
                + ".gcode"
            ),
            source=Path(
                source_svg.name
            ).with_suffix(".gcode"),
            source_type=JobSourceType.GCODE,
        )

        job.gcode = gcode
        job.source_svg_id = source_svg.id
        job.generated_from_svg = True
        job.conversion_profile = profile
        job.conversion_parameters = dict(
            parameters
        )

        job.transform = Transform(
            offset_x=source_svg.transform.offset_x,
            offset_y=source_svg.transform.offset_y,
            offset_z=source_svg.transform.offset_z,
            scale=source_svg.transform.scale,
            rotation=source_svg.transform.rotation,
            flip_x=source_svg.transform.flip_x,
            flip_y=source_svg.transform.flip_y,
        )

        job.origin = source_svg.origin
        job.repeated_anchors = list(
            source_svg.repeated_anchors
        )

        job.stats = analyze_gcode(
            gcode
        )

        source_svg.active = False
        source_svg.visible = False

        self.jobs.append(job)

        return job

    def get(self, job_id):
        return next(
            (
                j
                for j in self.jobs
                if j.id == job_id
            ),
            None,
        )

    def remove(self, job_id):
        self.jobs = [
            j
            for j in self.jobs
            if j.id != job_id
        ]


# ============================================================
# SVG preview
# ============================================================

def parse_svg_paths(path: Path):
    """
    Lightweight SVG preview.

    Supports:
      <line>
      <polyline>
      <polygon>
      simple path M/L commands

    This intentionally does not attempt to be a complete SVG
    renderer. Conversion remains the responsibility of vpype.
    """

    try:
        import xml.etree.ElementTree as ET

        root = ET.parse(path).getroot()
    except Exception:
        return []

    result = []

    def tag(element):
        return element.tag.split("}")[-1].lower()

    for element in root.iter():

        name = tag(element)

        if name == "line":
            try:
                x1 = float(element.attrib.get("x1", 0))
                y1 = float(element.attrib.get("y1", 0))
                x2 = float(element.attrib.get("x2", 0))
                y2 = float(element.attrib.get("y2", 0))

                result.append(
                    [
                        (x1, y1),
                        (x2, y2),
                    ]
                )
            except ValueError:
                pass

        elif name in ("polyline", "polygon"):
            points = []

            raw = element.attrib.get(
                "points",
                "",
            )

            values = re.findall(
                r"[-+]?(?:\d*\.)?\d+",
                raw,
            )

            for i in range(0, len(values) - 1, 2):
                points.append(
                    (
                        float(values[i]),
                        float(values[i + 1]),
                    )
                )

            if len(points) >= 2:
                result.append(points)

        elif name == "path":

            d = element.attrib.get(
                "d",
                "",
            )

            commands = re.findall(
                r"([ML])\s*"
                r"([-+]?(?:\d*\.)?\d+)"
                r"(?:\s*,?\s*)"
                r"([-+]?(?:\d*\.)?\d+)",
                d,
                flags=re.I,
            )

            points = []

            for command, x, y in commands:
                try:
                    points.append(
                        (
                            float(x),
                            float(y),
                        )
                    )
                except ValueError:
                    pass

            if len(points) >= 2:
                result.append(points)

    return result


# ============================================================
# G-code analysis
# ============================================================

def analyze_gcode(gcode: str):

    x = 0.0
    y = 0.0
    z = 0.0

    feed = 1000.0

    absolute = True

    draw_distance = 0.0
    travel_distance = 0.0
    up_distance = 0.0
    down_distance = 0.0

    total_time = 0.0
    instruction_count = 0

    segments = []

    for raw in gcode.splitlines():

        line = raw.split(";")[0].strip()

        if not line:
            continue

        instruction_count += 1

        upper = line.upper()

        if "G90" in upper:
            absolute = True

        if "G91" in upper:
            absolute = False

        def get_axis(axis):
            match = re.search(
                rf"\b{axis}"
                r"([-+]?(?:\d*\.)?\d+)",
                upper,
            )

            if not match:
                return None

            try:
                return float(
                    match.group(1)
                )
            except ValueError:
                return None

        new_feed = get_axis("F")

        if (
            new_feed is not None
            and new_feed > 0
        ):
            feed = new_feed

        old = (x, y, z)

        vx = get_axis("X")
        vy = get_axis("Y")
        vz = get_axis("Z")

        if absolute:

            if vx is not None:
                x = vx

            if vy is not None:
                y = vy

            if vz is not None:
                z = vz

        else:

            if vx is not None:
                x += vx

            if vy is not None:
                y += vy

            if vz is not None:
                z += vz

        new = (x, y, z)

        distance = math.sqrt(
            (new[0] - old[0]) ** 2
            + (new[1] - old[1]) ** 2
            + (new[2] - old[2]) ** 2
        )

        if distance <= 0:
            continue

        drawing = (
            z <= 0
            and (
                "G1" in upper
                or "G2" in upper
                or "G3" in upper
            )
        )

        if drawing:
            draw_distance += distance
            kind = "draw"
        else:
            travel_distance += distance
            kind = "travel"

        if old[2] > 0 and z <= 0:
            down_distance += abs(
                z - old[2]
            )

        if old[2] <= 0 and z > 0:
            up_distance += abs(
                z - old[2]
            )

        if feed > 0:
            total_time += (
                distance / feed * 60
            )

        segments.append(
            (
                old[0],
                old[1],
                new[0],
                new[1],
                kind,
            )
        )

    return {
        "time": total_time,
        "draw_distance": draw_distance,
        "travel_distance": travel_distance,
        "up_distance": up_distance,
        "down_distance": down_distance,
        "lines": instruction_count,
        "segments": segments,
    }


def format_duration(seconds):

    seconds = max(
        0,
        int(seconds),
    )

    hours, remainder = divmod(
        seconds,
        3600,
    )

    minutes, seconds = divmod(
        remainder,
        60,
    )

    if hours:
        return (
            f"{hours}h "
            f"{minutes:02d}m"
        )

    if minutes:
        return (
            f"{minutes}m "
            f"{seconds:02d}s"
        )

    return f"{seconds}s"


# ============================================================
# FluidNC
# ============================================================

def metrics(self, job):
        """
        Calculate simple G-code metrics.

        Drawing moves are distinguished from travel moves using
        the same Z/M3/M5 interpretation as the preview.
        """

        gcode = getattr(
            job,
            "gcode",
            None,
        )

        if not gcode:
            try:
                gcode = Path(
                    job.source
                ).read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception:
                return {
                    "time": 0.0,
                    "draw_distance": 0.0,
                    "travel_distance": 0.0,
                }

        x = 0.0
        y = 0.0
        z = 0.0

        absolute = True
        drawing = False

        draw_distance = 0.0
        travel_distance = 0.0
        total_time = 0.0

        feed = 2000.0

        for raw in gcode.splitlines():
            line = raw.split(";")[0].strip()

            if not line:
                continue

            upper = line.upper()

            if "G90" in upper:
                absolute = True

            if "G91" in upper:
                absolute = False

            if re.search(r"\bM3\b", upper):
                drawing = True

            if re.search(r"\bM5\b", upper):
                drawing = False

            f = re.search(
                r"\bF([-+]?\d*\.?\d+)",
                upper,
            )

            if f:
                try:
                    feed = max(
                        1.0,
                        float(f.group(1)),
                    )
                except ValueError:
                    pass

            z_match = re.search(
                r"\bZ([-+]?\d*\.?\d+)",
                upper,
            )

            if z_match:
                try:
                    z = float(
                        z_match.group(1)
                    )

                    drawing = z < 0
                except ValueError:
                    pass

            old_x = x
            old_y = y

            xm = re.search(
                r"\bX([-+]?\d*\.?\d+)",
                upper,
            )

            ym = re.search(
                r"\bY([-+]?\d*\.?\d+)",
                upper,
            )

            if xm:
                value = float(xm.group(1))
                x = (
                    old_x + value
                    if not absolute
                    else value
                )

            if ym:
                value = float(ym.group(1))
                y = (
                    old_y + value
                    if not absolute
                    else value
                )

            distance = math.hypot(
                x - old_x,
                y - old_y,
            )

            if distance <= 0:
                continue

            if drawing:
                draw_distance += distance
            else:
                travel_distance += distance

            # Feed is mm/min.
            total_time += (
                distance / feed * 60.0
            )

        return {
            "time": total_time,
            "draw_distance": draw_distance,
            "travel_distance": travel_distance,
        }
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
        self.socket = None
        self.transport = "http"

        self._lock = threading.Lock()

    @property
    def base_url(self):
        return (
            f"http://{self.host}:{self.port}"
        )

    def connect(self):
        with self._lock:
            if self.socket is not None:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            self.state.connected = False
            self.state.state = "Disconnected"

            http_error = None

            try:
                response = self.session.get(
                    self.base_url + "/",
                    timeout=3,
                )
                response.raise_for_status()
                self.transport = "http"
            except Exception as exc:
                http_error = exc

                ports = [self.port]

                if self.port != 23:
                    ports.append(23)

                socket_error = None

                for port in ports:
                    try:
                        sock = socket.create_connection(
                            (self.host, int(port)),
                            timeout=5,
                        )
                        sock.settimeout(5)
                        self.socket = sock
                        self.port = int(port)
                        self.transport = "socket"

                        try:
                            sock.recv(4096)
                        except socket.timeout:
                            pass

                        break
                    except Exception as sock_exc:
                        socket_error = sock_exc

                if self.transport != "socket":
                    raise RuntimeError(
                        "HTTP connection failed "
                        f"({http_error}); socket connection failed "
                        f"({socket_error})"
                    ) from socket_error

            self.state.connected = True
            self.state.state = "Connected"
            self.state.message = ""

    def disconnect(self):
        with self._lock:
            if self.socket is not None:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None

            self.state.connected = False
            self.state.state = "Disconnected"

    def send_command(
        self,
        command,
    ):
        with self._lock:
            if not self.state.connected:
                raise RuntimeError(
                    "Machine is not connected"
                )

            if self.transport == "socket":
                if self.socket is None:
                    raise RuntimeError(
                        "Socket connection is not available"
                    )

                self.socket.sendall(
                    (command.strip() + "\n").encode()
                )

                chunks = []

                while True:
                    data = self.socket.recv(4096)

                    if not data:
                        raise ConnectionError(
                            "Connection closed by FluidNC"
                        )

                    text = data.decode(
                        errors="replace"
                    )
                    chunks.append(text)

                    lower = text.lower()

                    if "ok" in lower:
                        break

                    if (
                        "error:" in lower
                        or "alarm:" in lower
                    ):
                        raise RuntimeError(
                            "".join(chunks).strip()
                        )

                return "".join(chunks)

            response = self.session.get(
                self.base_url + "/command",
                params={"cmd": command},
                timeout=5,
            )

            response.raise_for_status()

            return response.text

    def poll_status(self):
        with self._lock:
            if not self.state.connected:
                return

            try:
                if self.transport == "socket":
                    if self.socket is None:
                        raise RuntimeError(
                            "Socket connection is not available"
                        )

                    self.socket.sendall(b"?")
                    text = self.socket.recv(4096).decode(
                        errors="replace"
                    )
                else:
                    response = self.session.get(
                        self.base_url + "/command",
                        params={"cmd": "?"},
                        timeout=2,
                    )

                    response.raise_for_status()
                    text = response.text

                self.parse_status(text)

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


# ============================================================
# Connection worker
# ============================================================

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


class PollWorker(QThread):

    updated = Signal()
    failed = Signal(str)

    def __init__(
        self,
        machine,
    ):
        super().__init__()
        self.machine = machine

    def run(self):

        try:
            self.machine.poll_status()
            self.updated.emit()

        except Exception as exc:
            self.failed.emit(
                str(exc)
            )


# ============================================================
# Workspace view
# ============================================================


class WorkspaceView(QWidget):
    """
    Workspace preview.

    Responsibilities:
      - workspace rendering
      - SVG/G-code preview
      - job selection
      - job dragging
      - machine position
      - anchor placement
      - fit-to-workspace / fit-to-jobs
      - bounded preview rendering
    """

    jobSelected = Signal(str)
    jobMoved = Signal(str, float, float)
    moveMachineRequested = Signal(float, float)

    def __init__(self, workspace, jobs):
        super().__init__()

        self.workspace = workspace
        self.jobs = jobs

        self.zoom = 1.0
        self.pan_x = 50.0
        self.pan_y = 50.0

        self.machine_x = 0.0
        self.machine_y = 0.0

        self.selected_job_id = None

        self.panning = False
        self.pan_start = QPointF()
        self.pan_origin_x = 0.0
        self.pan_origin_y = 0.0

        self.dragging_job = False
        self.drag_job_id = None
        self.drag_offset_x = 0.0
        self.drag_offset_y = 0.0

        self.preview_limit = 20000
        self.show_travel = True
        self.show_drawing = True

        self.setMinimumSize(500, 500)
        self.setFocusPolicy(Qt.StrongFocus)

    # --------------------------------------------------------
    # Coordinates
    # --------------------------------------------------------

    def world_to_screen(self, x, y):
        return (
            self.pan_x + x * self.zoom,
            self.pan_y
            + (self.workspace.height - y) * self.zoom,
        )

    def screen_to_world(self, point):
        x = (point.x() - self.pan_x) / self.zoom

        y = self.workspace.height - (
            point.y() - self.pan_y
        ) / self.zoom

        return x, y

    # --------------------------------------------------------
    # View controls
    # --------------------------------------------------------

    def fit_workspace(self):
        margin = 50.0

        available_w = max(
            100.0,
            self.width() - 2 * margin,
        )

        available_h = max(
            100.0,
            self.height() - 2 * margin,
        )

        if self.workspace.width <= 0:
            return

        if self.workspace.height <= 0:
            return

        self.zoom = min(
            available_w / self.workspace.width,
            available_h / self.workspace.height,
        )

        self.zoom = max(
            0.05,
            min(20.0, self.zoom),
        )

        self.pan_x = (
            self.width()
            - self.workspace.width * self.zoom
        ) / 2

        self.pan_y = (
            self.height()
            - self.workspace.height * self.zoom
        ) / 2

        self.update()

    def _job_bounds(self):
        bounds = []

        for job in self.jobs.jobs:
            if not getattr(job, "active", True):
                continue

            geometry = self._job_geometry(job)

            for x, y in geometry:
                bounds.append((x, y))

        return bounds

    def fit_jobs(self):
        points = self._job_bounds()

        if not points:
            self.fit_workspace()
            return

        min_x = min(p[0] for p in points)
        max_x = max(p[0] for p in points)
        min_y = min(p[1] for p in points)
        max_y = max(p[1] for p in points)

        width = max(1.0, max_x - min_x)
        height = max(1.0, max_y - min_y)

        margin = 60.0

        available_w = max(
            100.0,
            self.width() - 2 * margin,
        )

        available_h = max(
            100.0,
            self.height() - 2 * margin,
        )

        self.zoom = min(
            available_w / width,
            available_h / height,
        )

        self.zoom = max(
            0.05,
            min(20.0, self.zoom),
        )

        self.pan_x = (
            self.width() / 2
            - ((min_x + max_x) / 2) * self.zoom
        )

        self.pan_y = (
            self.height() / 2
            - (
                self.workspace.height
                - ((min_y + max_y) / 2)
            ) * self.zoom
        )

        self.update()

    # --------------------------------------------------------
    # Selection
    # --------------------------------------------------------

    def set_selected_job(self, job_id):
        self.selected_job_id = job_id
        self.update()

    # compatibility with newer versions
    set_selected = set_selected_job

    # --------------------------------------------------------
    # Machine
    # --------------------------------------------------------

    def set_machine_position(self, x, y):
        self.machine_x = x
        self.machine_y = y
        self.update()

    # --------------------------------------------------------
    # Job geometry
    # --------------------------------------------------------

    def _parse_gcode(self, job):
        """
        Parse a bounded amount of G-code into line segments.

        Each tuple is:

            (x1, y1, x2, y2, drawing)

        drawing=True means the pen/tool is down.
        """

        gcode = getattr(job, "gcode", None)

        if not gcode:
            try:
                gcode = Path(job.source).read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception:
                return []

        lines = gcode.splitlines()

        if len(lines) > self.preview_limit:
            lines = lines[:self.preview_limit]

        x = 0.0
        y = 0.0
        z = 0.0

        absolute = True
        drawing = False

        segments = []

        for line in lines:
            line = line.strip()

            if not line:
                continue

            if line.startswith(";"):
                continue

            command = line.split(";")[0].strip()

            upper = command.upper()

            if "G90" in upper:
                absolute = True

            if "G91" in upper:
                absolute = False

            if re.search(r"\bM3\b", upper):
                drawing = True

            if re.search(r"\bM5\b", upper):
                drawing = False

            # Common plotter convention:
            # Z below zero = drawing.
            z_match = re.search(
                r"\bZ([-+]?\d*\.?\d+)",
                upper,
            )

            if z_match:
                try:
                    new_z = float(z_match.group(1))
                    drawing = new_z < 0
                    z = new_z
                except ValueError:
                    pass

            x_match = re.search(
                r"\bX([-+]?\d*\.?\d+)",
                upper,
            )

            y_match = re.search(
                r"\bY([-+]?\d*\.?\d+)",
                upper,
            )

            new_x = x
            new_y = y

            try:
                if x_match:
                    value = float(x_match.group(1))
                    new_x = (
                        x + value
                        if not absolute
                        else value
                    )

                if y_match:
                    value = float(y_match.group(1))
                    new_y = (
                        y + value
                        if not absolute
                        else value
                    )
            except ValueError:
                continue

            if (
                new_x != x
                or new_y != y
            ):
                segments.append(
                    (
                        x,
                        y,
                        new_x,
                        new_y,
                        drawing,
                    )
                )

            x = new_x
            y = new_y

        return segments

    def _svg_geometry(self, job):
        """
        Best-effort SVG preview.

        Uses svgpathtools when installed.  If it isn't installed,
        the preview falls back gracefully instead of breaking the UI.
        """

        try:
            from svgpathtools import svg2paths
        except ImportError:
            return []

        try:
            paths, _ = svg2paths(str(job.source))
        except Exception:
            return []

        result = []

        for path in paths:
            try:
                points = []

                for segment in path:
                    steps = max(
                        2,
                        min(
                            40,
                            int(abs(segment.length()) / 5) + 2,
                        ),
                    )

                    for i in range(steps):
                        t = i / (steps - 1)
                        p = segment.point(t)

                        points.append(
                            (float(p.real), float(-p.imag))
                        )

                for a, b in zip(
                    points,
                    points[1:],
                ):
                    result.append(
                        (
                            a[0],
                            a[1],
                            b[0],
                            b[1],
                            True,
                        )
                    )

            except Exception:
                continue

        return result

    def _base_geometry(self, job):
        source_type = getattr(
            job,
            "source_type",
            None,
        )

        if str(source_type).lower().endswith("svg"):
            return self._svg_geometry(job)

        return self._parse_gcode(job)

    def _transform_point(self, job, x, y):
        transform = getattr(
            job,
            "transform",
            None,
        )

        if transform is None:
            return x, y

        scale = getattr(
            transform,
            "scale",
            1.0,
        )

        rotation = math.radians(
            getattr(
                transform,
                "rotation",
                0.0,
            )
        )

        flip_x = getattr(
            transform,
            "flip_x",
            False,
        )

        flip_y = getattr(
            transform,
            "flip_y",
            False,
        )

        if flip_x:
            x = -x

        if flip_y:
            y = -y

        x *= scale
        y *= scale

        cos_a = math.cos(rotation)
        sin_a = math.sin(rotation)

        rx = (
            x * cos_a
            - y * sin_a
        )

        ry = (
            x * sin_a
            + y * cos_a
        )

        return (
            rx + getattr(
                transform,
                "offset_x",
                0.0,
            ),
            ry + getattr(
                transform,
                "offset_y",
                0.0,
            ),
        )

    def _anchor_offset(self, job):
        """
        Return the additional offset for the selected origin.

        Machine origin:
            no offset.

        Named anchor:
            job is positioned relative to that anchor.

        Repeated anchors:
            additional copies are generated at each anchor.
        """

        origin = getattr(
            job,
            "origin",
            "machine",
        )

        if origin in (None, "", "machine"):
            return 0.0, 0.0

        for anchor in self.workspace.anchors:
            if anchor.name == origin:
                return anchor.x, anchor.y

        return 0.0, 0.0

    def _job_geometry(self, job):
        base = self._base_geometry(job)

        if not base:
            return []

        ox, oy = self._anchor_offset(job)

        transformed = []

        for x1, y1, x2, y2, drawing in base:
            a = self._transform_point(
                job,
                x1,
                y1,
            )

            b = self._transform_point(
                job,
                x2,
                y2,
            )

            transformed.append(
                (
                    a[0] + ox,
                    a[1] + oy,
                    b[0] + ox,
                    b[1] + oy,
                    drawing,
                )
            )

        # Repeated anchors are additional copies.
        repeated = getattr(
            job,
            "repeated_anchors",
            [],
        )

        if not repeated:
            return transformed

        result = list(transformed)

        for anchor in self.workspace.anchors:
            if anchor.name not in repeated:
                continue

            for x1, y1, x2, y2, drawing in transformed:
                result.append(
                    (
                        x1
                        - ox
                        + anchor.x,
                        y1
                        - oy
                        + anchor.y,
                        x2
                        - ox
                        + anchor.x,
                        y2
                        - oy
                        + anchor.y,
                        drawing,
                    )
                )

        return result

    # --------------------------------------------------------
    # Hit testing
    # --------------------------------------------------------

    def job_hit(self, job, x, y):
        geometry = self._job_geometry(job)

        if not geometry:
            width = 120.0 * getattr(
                job.transform,
                "scale",
                1.0,
            )

            height = 80.0 * getattr(
                job.transform,
                "scale",
                1.0,
            )

            ox = job.transform.offset_x
            oy = job.transform.offset_y

            return (
                ox <= x <= ox + width
                and
                oy - height <= y <= oy
            )

        min_x = min(
            min(a[0], a[2])
            for a in geometry
        )

        max_x = max(
            max(a[0], a[2])
            for a in geometry
        )

        min_y = min(
            min(a[1], a[3])
            for a in geometry
        )

        max_y = max(
            max(a[1], a[3])
            for a in geometry
        )

        tolerance = max(
            2.0,
            8.0 / self.zoom,
        )

        return (
            min_x - tolerance <= x <= max_x + tolerance
            and
            min_y - tolerance <= y <= max_y + tolerance
        )

    # --------------------------------------------------------
    # Mouse
    # --------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.panning = True
            self.pan_start = event.position()
            self.pan_origin_x = self.pan_x
            self.pan_origin_y = self.pan_y
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            x, y = self.screen_to_world(
                event.position()
            )

            if event.modifiers() & Qt.ControlModifier:
                self.moveMachineRequested.emit(
                    x,
                    y,
                )
                event.accept()
                return

            for job in reversed(self.jobs.jobs):
                if not getattr(
                    job,
                    "active",
                    True,
                ):
                    continue

                if self.job_hit(job, x, y):
                    self.selected_job_id = job.id

                    self.dragging_job = True
                    self.drag_job_id = job.id

                    self.drag_offset_x = (
                        x
                        - job.transform.offset_x
                    )

                    self.drag_offset_y = (
                        y
                        - job.transform.offset_y
                    )

                    self.jobSelected.emit(job.id)
                    self.update()

                    event.accept()
                    return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.panning:
            delta = (
                event.position()
                - self.pan_start
            )

            self.pan_x = (
                self.pan_origin_x
                + delta.x()
            )

            self.pan_y = (
                self.pan_origin_y
                + delta.y()
            )

            self.update()
            event.accept()
            return

        if self.dragging_job and self.drag_job_id:
            job = self.jobs.get(
                self.drag_job_id
            )

            if job:
                x, y = self.screen_to_world(
                    event.position()
                )

                job.transform.offset_x = (
                    x - self.drag_offset_x
                )

                job.transform.offset_y = (
                    y - self.drag_offset_y
                )

                self.jobMoved.emit(
                    job.id,
                    job.transform.offset_x,
                    job.transform.offset_y,
                )

                self.update()

                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            if self.dragging_job:
                self.dragging_job = False
                self.drag_job_id = None
                self.update()
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        old_zoom = self.zoom

        factor = (
            1.15
            if event.angleDelta().y() > 0
            else 1 / 1.15
        )

        self.zoom = max(
            0.05,
            min(
                20.0,
                self.zoom * factor,
            ),
        )

        mouse = event.position()

        world_before = (
            (
                mouse.x() - self.pan_x
            ) / old_zoom,
            self.workspace.height
            - (
                mouse.y() - self.pan_y
            ) / old_zoom,
        )

        self.pan_x = (
            mouse.x()
            - world_before[0] * self.zoom
        )

        self.pan_y = (
            mouse.y()
            - (
                self.workspace.height
                - world_before[1]
            ) * self.zoom
        )

        self.update()

    # --------------------------------------------------------
    # Paint
    # --------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)

        try:

            painter.setRenderHint(
                QPainter.Antialiasing
            )

            painter.fillRect(
                self.rect(),
                QColor("#f1f3f5"),
            )

            # Workspace
            left, top = self.world_to_screen(0, self.workspace.height)

            rect = QRectF(
                left,
                top,
                self.workspace.width * self.zoom,
                self.workspace.height * self.zoom,
            )

            painter.setPen(
                QPen(
                    QColor("#8b9298"),
                    2,
                )
            )

            painter.setBrush(
                QBrush(
                    QColor("#ffffff")
                )
            )

            painter.drawRect(rect)

            # Anchors
            for anchor in self.workspace.anchors:
                ax, ay = self.world_to_screen(
                    anchor.x,
                    anchor.y,
                )

                painter.setPen(
                    QPen(
                        QColor("#70777d"),
                        1,
                    )
                )

                painter.drawLine(
                    ax - 7,
                    ay,
                    ax + 7,
                    ay,
                )

                painter.drawLine(
                    ax,
                    ay - 7,
                    ax,
                    ay + 7,
                )

                painter.drawText(
                    ax + 10,
                    ay - 8,
                    anchor.name,
                )

            # Jobs
            for job in self.jobs.jobs:
                if not getattr(
                    job,
                    "active",
                    True,
                ):
                    continue

                geometry = self._job_geometry(job)

                if geometry:
                    for x1, y1, x2, y2, drawing in geometry:
                        if drawing:
                            if not self.show_drawing:
                                continue

                            pen = QPen(
                                QColor("#216e39"),
                                max(
                                    1.0,
                                    min(
                                        4.0,
                                        self.zoom * 0.7,
                                    ),
                                ),
                            )
                        else:
                            if not self.show_travel:
                                continue

                            pen = QPen(
                                QColor("#aab0b5"),
                                1,
                                Qt.DashLine,
                            )

                        if job.id == self.selected_job_id:
                            pen.setWidthF(
                                max(
                                    2.0,
                                    self.zoom * 0.9,
                                )
                            )

                        painter.setPen(pen)

                        sx1, sy1 = self.world_to_screen(
                            x1,
                            y1,
                        )

                        sx2, sy2 = self.world_to_screen(
                            x2,
                            y2,
                        )

                        painter.drawLine(
                            sx1,
                            sy1,
                            sx2,
                            sy2,
                        )

                else:
                    # Safe fallback when geometry isn't available.
                    x, y = self.world_to_screen(
                        job.transform.offset_x,
                        job.transform.offset_y,
                    )

                    width = (
                        120
                        * getattr(
                            job.transform,
                            "scale",
                            1.0,
                        )
                        * self.zoom
                    )

                    height = (
                        80
                        * getattr(
                            job.transform,
                            "scale",
                            1.0,
                        )
                        * self.zoom
                    )

                    painter.setPen(
                        QPen(
                            QColor("#555b61")
                            if job.id != self.selected_job_id
                            else QColor("#1f4e79"),
                            2,
                        )
                    )

                    painter.setBrush(
                        QBrush(
                            QColor("#e7edf2")
                        )
                    )

                    painter.drawRect(
                        QRectF(
                            x,
                            y - height,
                            width,
                            height,
                        )
                    )

                # Job label
                if geometry:
                    points = []

                    for x1, y1, x2, y2, _ in geometry:
                        points.extend(
                            [(x1, y1), (x2, y2)]
                        )

                    if points:
                        lx = min(p[0] for p in points)
                        ly = max(p[1] for p in points)

                        sx, sy = self.world_to_screen(
                            lx,
                            ly,
                        )

                        painter.setPen(
                            QColor("#343a40")
                        )

                        painter.drawText(
                            sx + 4,
                            sy - 4,
                            job.name,
                        )

            # Machine position
            mx, my = self.world_to_screen(
                self.machine_x,
                self.machine_y,
            )

            painter.setPen(
                QPen(
                    QColor("#c92a2a"),
                    2,
                )
            )

            painter.setBrush(Qt.NoBrush)

            painter.drawEllipse(
                QPointF(mx, my),
                7,
                7,
            )

            painter.drawLine(
                mx - 12,
                my,
                mx + 12,
                my,
            )

            painter.drawLine(
                mx,
                my - 12,
                mx,
                my + 12,
            )

        finally:
            if painter.isActive():
                painter.end()

class CollapsibleSection(QFrame):

    def __init__(
        self,
        title,
        content,
        expanded=False,
    ):

        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        layout.setSpacing(0)

        self.button = QPushButton()

        self.button.setCheckable(True)
        self.button.setChecked(
            expanded
        )

        self.title = title
        self.content = content

        self.button.clicked.connect(
            self.update_state
        )

        layout.addWidget(
            self.button
        )

        layout.addWidget(
            content
        )

        self.update_state()

    def update_state(self):

        expanded = (
            self.button.isChecked()
        )

        self.content.setVisible(
            expanded
        )

        self.button.setText(
            (
                "▼ "
                if expanded
                else "▶ "
            )
            + self.title
        )


# ============================================================
# Machine panel
# ============================================================


class MachinePanel(QFrame):
    stateChanged = Signal()

    def __init__(self, machine):
        super().__init__()

        self.machine = machine
        self.worker = None
        saved_host = state_store.get(
            "machine.host",
            machine.host,
        )
        saved_port = state_store.get(
            "machine.port",
            machine.port,
        )
        saved_step = state_store.get(
            "machine.jog_step",
            10.0,
        )

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel("<b>Machine</b>")
        )

        status_row = QHBoxLayout()
        self.connection_indicator = QLabel("●")
        self.connection_indicator.setFixedWidth(14)
        status_row.addWidget(
            self.connection_indicator
        )

        self.status = QLabel(
            "Disconnected"
        )
        status_row.addWidget(self.status)
        status_row.addStretch()
        layout.addLayout(status_row)

        connection = QGroupBox("Connection")
        connection_layout = QVBoxLayout(connection)

        row = QHBoxLayout()
        row.addWidget(QLabel("Host"))

        self.host = QLineEdit(
            str(saved_host)
        )
        self.host.editingFinished.connect(
            self.persist_settings
        )

        row.addWidget(self.host)
        connection_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Port"))

        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        try:
            self.port.setValue(int(saved_port))
        except (TypeError, ValueError):
            self.port.setValue(machine.port)
        self.port.valueChanged.connect(
            self.persist_settings
        )

        row.addWidget(self.port)
        connection_layout.addLayout(row)

        layout.addWidget(
            CollapsibleSection(
                "Connection settings",
                connection,
                expanded=False,
            )
        )

        self.connect_button = QPushButton(
            "Connect"
        )

        self.connect_button.clicked.connect(
            self.toggle
        )

        layout.addWidget(
            self.connect_button
        )

        self.position = QLabel(
            "X: --\nY: --\nZ: --"
        )

        layout.addWidget(
            self.position
        )

        command_row = QHBoxLayout()
        self.gcode_input = QLineEdit()
        self.gcode_input.setPlaceholderText(
            "Send G-code command"
        )
        send_gcode = QPushButton("Send")
        send_gcode.clicked.connect(
            self.send_gcode_command
        )
        self.gcode_input.returnPressed.connect(
            self.send_gcode_command
        )
        command_row.addWidget(self.gcode_input)
        command_row.addWidget(send_gcode)
        layout.addLayout(command_row)

        layout.addWidget(
            QLabel("<b>Jog</b>")
        )

        row = QHBoxLayout()
        row.addWidget(QLabel("Step"))

        self.step = QDoubleSpinBox()
        self.step.setRange(
            0.01,
            10000,
        )
        try:
            self.step.setValue(float(saved_step))
        except (TypeError, ValueError):
            self.step.setValue(10)
        self.step.setDecimals(2)
        self.step.valueChanged.connect(
            self.persist_settings
        )

        row.addWidget(self.step)

        self.step_preset = QComboBox()
        for value in (
            0.01,
            0.05,
            0.1,
            0.5,
            1,
            5,
            10,
            50,
            100,
            500,
            1000,
        ):
            self.step_preset.addItem(
                f"{value:g}",
                float(value),
            )
        self.step_preset.currentIndexChanged.connect(
            self.select_step_preset
        )
        row.addWidget(
            QLabel("Preset")
        )
        row.addWidget(self.step_preset)
        self.sync_step_preset()

        layout.addLayout(row)

        def jog(x, y, z):
            try:
                self.machine.jog(x, y, z)
            except Exception as exc:
                self.status.setText(
                    f"Error: {exc}"
                )

        row = QHBoxLayout()

        up = QPushButton("↑")
        up.clicked.connect(
            lambda:
            jog(
                0,
                self.step.value(),
                0,
            )
        )

        row.addStretch()
        row.addWidget(up)
        row.addStretch()

        layout.addLayout(row)

        row = QHBoxLayout()

        left = QPushButton("←")
        right = QPushButton("→")

        left.clicked.connect(
            lambda:
            jog(
                -self.step.value(),
                0,
                0,
            )
        )

        right.clicked.connect(
            lambda:
            jog(
                self.step.value(),
                0,
                0,
            )
        )

        row.addWidget(left)
        row.addStretch()
        row.addWidget(right)

        layout.addLayout(row)

        row = QHBoxLayout()

        down = QPushButton("↓")

        down.clicked.connect(
            lambda:
            jog(
                0,
                -self.step.value(),
                0,
            )
        )

        row.addStretch()
        row.addWidget(down)
        row.addStretch()

        layout.addLayout(row)

        row = QHBoxLayout()

        zp = QPushButton("Z+")
        zm = QPushButton("Z-")

        zp.clicked.connect(
            lambda:
            jog(
                0,
                0,
                self.step.value(),
            )
        )

        zm.clicked.connect(
            lambda:
            jog(
                0,
                0,
                -self.step.value(),
            )
        )

        row.addWidget(zp)
        row.addWidget(zm)

        layout.addLayout(row)

        for axis in ("X", "Y", "Z"):
            button = QPushButton(
                f"Home {axis}"
            )

            button.clicked.connect(
                lambda checked=False,
                a=axis:
                self.home(a)
            )

            layout.addWidget(button)

        home = QPushButton(
            "Home All"
        )

        home.clicked.connect(
            lambda:
            self.home(None)
        )

        layout.addWidget(home)

        zero = QPushButton(
            "Set Zero"
        )

        zero.clicked.connect(
            self.set_zero
        )

        layout.addWidget(zero)

        layout.addStretch()

    def toggle(self):
        if self.worker is not None:
            if self.worker.isRunning():
                return

        if self.machine.state.connected:
            self.machine.disconnect()

            self.connect_button.setText(
                "Connect"
            )

            self.status.setText(
                "Disconnected"
            )

            self.stateChanged.emit()
            return

        host = self.host.text().strip()

        if not host:
            self.status.setText(
                "Enter a host"
            )
            return

        self.machine.host = host
        self.machine.port = self.port.value()
        self.persist_settings()

        self.connect_button.setEnabled(False)
        self.status.setText(
            "Connecting..."
        )

        self.worker = ConnectWorker(
            self.machine
        )

        self.worker.succeeded.connect(
            self.connected
        )

        self.worker.failed.connect(
            self.failed
        )

        self.worker.finished.connect(
            self.connection_finished
        )

        self.worker.start()

    def connected(self):
        self.machine.state.connected = True

        self.connect_button.setText(
            "Disconnect"
        )

        self.status.setText(
            "Connected"
        )

        self.stateChanged.emit()

    def failed(self, message):
        self.machine.disconnect()

        self.connect_button.setText(
            "Connect"
        )

        self.status.setText(
            f"Connection failed: {message}"
        )

        show_warning(
            self,
            "Connection failed",
            str(message),
        )

        self.stateChanged.emit()

    def connection_finished(self):
        self.connect_button.setEnabled(True)

        worker = self.worker

        if worker is not None:
            worker.deleteLater()

        self.worker = None

    def home(self, axis):
        try:
            self.machine.home(axis)
        except Exception as exc:
            self.status.setText(
                f"Error: {exc}"
            )

    def set_zero(self):
        try:
            if hasattr(
                self.machine,
                "set_zero",
            ):
                self.machine.set_zero()

            elif hasattr(
                self.machine,
                "zero",
            ):
                self.machine.zero()

        except Exception as exc:
            self.status.setText(
                f"Error: {exc}"
            )

    def send_gcode_command(self):
        command = self.gcode_input.text().strip()

        if not command:
            return

        try:
            response = self.machine.send_command(
                command
            )
            if response:
                self.status.setText(
                    response.strip()
                )
            self.gcode_input.clear()
        except Exception as exc:
            show_warning(
                self,
                "Command failed",
                str(exc),
            )

    def persist_settings(self, *_args):
        state_store.set(
            "machine.host",
            self.host.text().strip(),
        )
        state_store.set(
            "machine.port",
            self.port.value(),
        )
        state_store.set(
            "machine.jog_step",
            self.step.value(),
        )
        self.sync_step_preset()

    def select_step_preset(self, index):
        value = self.step_preset.itemData(index)
        if value is None:
            return
        self.step.blockSignals(True)
        self.step.setValue(float(value))
        self.step.blockSignals(False)
        self.persist_settings()

    def sync_step_preset(self):
        value = self.step.value()
        index = -1
        for i in range(self.step_preset.count()):
            candidate = self.step_preset.itemData(i)
            if candidate is None:
                continue
            if abs(float(candidate) - float(value)) < 1e-9:
                index = i
                break
        self.step_preset.blockSignals(True)
        if index >= 0:
            self.step_preset.setCurrentIndex(index)
        else:
            self.step_preset.setCurrentIndex(-1)
        self.step_preset.blockSignals(False)

    def update_state(self):
        """Refresh the machine status without performing I/O."""

        state = self.machine.state

        connected = bool(
            getattr(state, "connected", False)
        )

        if connected:
            state_text = getattr(
                state,
                "state",
                "Connected",
            )

            self.status.setText(
                str(state_text)
            )

            x = getattr(state, "x", 0.0)
            y = getattr(state, "y", 0.0)
            z = getattr(state, "z", 0.0)

            try:
                self.position.setText(
                    f"X: {float(x):.3f}\n"
                    f"Y: {float(y):.3f}\n"
                    f"Z: {float(z):.3f}"
                )
            except (TypeError, ValueError):
                self.position.setText(
                    f"X: {x}\n"
                    f"Y: {y}\n"
                    f"Z: {z}"
                )

            self.connect_button.setText(
                "Disconnect"
            )
            self.connection_indicator.setStyleSheet(
                "color: #2f9e44;"
            )

        else:
            self.status.setText(
                str(
                    getattr(
                        state,
                        "state",
                        "Disconnected",
                    )
                )
            )

            self.position.setText(
                "X: --\n"
                "Y: --\n"
                "Z: --"
            )

            self.connect_button.setText(
                "Connect"
            )
            state_text = str(
                getattr(
                    state,
                    "state",
                    "Disconnected",
                )
            ).lower()
            color = "#868e96"
            if "failed" in state_text or "lost" in state_text or "error" in state_text:
                color = "#c92a2a"
            self.connection_indicator.setStyleSheet(
                f"color: {color};"
            )

class JobListPanel(QFrame):
    changed = Signal()
    selected = Signal(str)

    def __init__(
        self,
        jobs,
    ):

        super().__init__()

        self.jobs = jobs

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel("<b>Jobs</b>")
        )

        add = QPushButton(
            "Add SVG / G-code"
        )

        add.clicked.connect(
            self.add_file
        )

        layout.addWidget(add)

        add_dummy = QPushButton(
            "Add Dummy Job"
        )
        add_dummy.clicked.connect(
            self.add_dummy
        )
        layout.addWidget(add_dummy)

        self.list = QListWidget()

        self.list.currentItemChanged.connect(
            self.selection_changed
        )

        layout.addWidget(
            self.list
        )

        remove = QPushButton(
            "Remove"
        )

        remove.clicked.connect(
            self.remove
        )

        layout.addWidget(remove)

    def refresh(
        self,
        selected_id=None,
    ):

        self.list.blockSignals(
            True
        )

        self.list.clear()

        selected_item = None

        for job in self.jobs.jobs:

            item = QListWidgetItem()

            item.setData(
                Qt.UserRole,
                job.id,
            )

            suffix = ""

            if (
                job.source_type
                == JobSourceType.GCODE
                and job.stats
            ):

                suffix = (
                    "  ·  "
                    + format_duration(
                        job.stats.get(
                            "time",
                            0,
                        )
                    )
                )

            text = (
                job.name
                + suffix
            )

            if (
                not job.active
                or not job.visible
            ):

                text = (
                    "○ "
                    + text
                )

            else:

                text = (
                    "● "
                    + text
                )

            item.setText(text)

            item.setCheckState(
                Qt.Checked
                if job.active
                else Qt.Unchecked
            )

            self.list.addItem(item)

            if job.id == selected_id:
                selected_item = item

        if selected_item:

            self.list.setCurrentItem(
                selected_item
            )

        self.list.blockSignals(
            False
        )

    def selection_changed(
        self,
        current,
        previous,
    ):

        if current is None:

            self.selected.emit("")

            return

        self.selected.emit(
            current.data(
                Qt.UserRole
            )
        )

    def add_file(self):

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Job",
            "",
            (
                "Plotter files "
                "(*.svg *.gcode *.nc *.ngc)"
            ),
        )

        selected_id = None

        for filename in files:

            try:
                job = self.jobs.add_file(
                    Path(filename)
                )
                selected_id = job.id

            except Exception as exc:

                show_warning(
                    self,
                    "Cannot add file",
                    str(exc),
                )

        self.changed.emit()

        if selected_id:
            self.refresh(selected_id)
            self.selected.emit(selected_id)

    def remove(self):

        item = (
            self.list.currentItem()
        )

        if item is None:
            return

        self.jobs.remove(
            item.data(
                Qt.UserRole
            )
        )

        self.changed.emit()

    def add_dummy(self):
        job = self.jobs.add_dummy()
        self.changed.emit()
        self.refresh(job.id)
        self.selected.emit(job.id)


# ============================================================
# Job properties
# ============================================================


class PipelineDialog(QDialog):

    def __init__(
        self,
        parent,
        profiles,
        source_type,
        initial_steps=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add pipeline")
        self.resize(700, 500)

        self.profiles = profiles
        self.source_type = source_type
        self.steps = list(initial_steps or [])

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.profile_combo = QComboBox()

        for profile in self.profiles:
            self.profile_combo.addItem(
                profile.name,
                profile.name,
            )

        add_step = QPushButton("Add step")
        add_step.clicked.connect(self.add_step)
        remove_step = QPushButton("Remove step")
        remove_step.clicked.connect(
            self.remove_step
        )

        top.addWidget(QLabel("Profile"))
        top.addWidget(self.profile_combo)
        top.addWidget(add_step)
        top.addWidget(remove_step)
        layout.addLayout(top)

        body = QHBoxLayout()
        self.step_list = QListWidget()
        self.step_list.currentRowChanged.connect(
            self.select_step
        )
        body.addWidget(self.step_list, 2)

        self.parameters_group = QGroupBox(
            "Step parameters"
        )
        self.parameters_layout = QVBoxLayout(
            self.parameters_group
        )
        body.addWidget(self.parameters_group, 3)
        layout.addLayout(body)

        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok
            | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh_steps()

    def add_step(self):
        profile_name = self.profile_combo.currentData()
        profile = self._profile(profile_name)

        if profile is None:
            return

        params = {}

        for name, spec in profile.parameters.items():
            if isinstance(spec, dict):
                params[name] = spec.get("default")
            else:
                params[name] = spec

        self.steps.append(
            {
                "profile": profile.name,
                "parameters": params,
            }
        )

        self.refresh_steps()
        self.step_list.setCurrentRow(
            self.step_list.count() - 1
        )

    def remove_step(self):
        row = self.step_list.currentRow()

        if row < 0:
            return

        self.steps.pop(row)
        self.refresh_steps()

    def select_step(self, row):
        while self.parameters_layout.count():
            item = self.parameters_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if row < 0 or row >= len(self.steps):
            self.parameters_layout.addStretch()
            return

        step = self.steps[row]
        profile = self._profile(step.get("profile"))

        if profile is None:
            self.parameters_layout.addStretch()
            return

        for name, spec in profile.parameters.items():
            value = step.get("parameters", {}).get(
                name
            )

            if isinstance(spec, dict):
                if value is None:
                    value = spec.get("default")
                p_type = str(
                    spec.get("type", "string")
                ).lower()
                options = spec.get("options", [])
            else:
                p_type = "string"
                options = []

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(
                0,
                0,
                0,
                0,
            )
            row_layout.addWidget(QLabel(str(name)))

            if p_type == "boolean":
                editor = QCheckBox()
                editor.setChecked(
                    str(value).strip().lower() in {
                        "1",
                        "true",
                        "yes",
                        "on",
                    }
                    if not isinstance(value, bool)
                    else value
                )
                editor.toggled.connect(
                    lambda checked, n=name, r=row:
                    self._set_param(r, n, checked)
                )
            elif options:
                editor = QComboBox()
                editor.addItems(
                    [str(o) for o in options]
                )
                if value is not None:
                    idx = editor.findText(str(value))
                    if idx >= 0:
                        editor.setCurrentIndex(idx)
                editor.currentTextChanged.connect(
                    lambda text, n=name, r=row:
                    self._set_param(r, n, text)
                )
            elif p_type == "number":
                editor = QDoubleSpinBox()
                editor.setRange(-1_000_000, 1_000_000)
                editor.setDecimals(4)
                try:
                    editor.setValue(float(value))
                except Exception:
                    editor.setValue(0.0)
                editor.valueChanged.connect(
                    lambda v, n=name, r=row:
                    self._set_param(r, n, v)
                )
            elif p_type == "integer":
                editor = QSpinBox()
                editor.setRange(-1_000_000, 1_000_000)
                try:
                    editor.setValue(int(value))
                except Exception:
                    editor.setValue(0)
                editor.valueChanged.connect(
                    lambda v, n=name, r=row:
                    self._set_param(r, n, v)
                )
            else:
                editor = QLineEdit(
                    "" if value is None else str(value)
                )
                editor.textChanged.connect(
                    lambda text, n=name, r=row:
                    self._set_param(r, n, text)
                )

            row_layout.addWidget(editor)
            self.parameters_layout.addWidget(row_widget)

        self.parameters_layout.addStretch()

    def _set_param(
        self,
        row,
        name,
        value,
    ):
        if row < 0 or row >= len(self.steps):
            return

        self.steps[row].setdefault(
            "parameters",
            {},
        )[name] = value

    def _profile(self, name):
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None

    def refresh_steps(self):
        self.step_list.clear()

        for index, step in enumerate(self.steps, start=1):
            profile = self._profile(
                step.get("profile")
            )
            if profile is None:
                text = f"{index}. {step.get('profile', '?')}"
            else:
                text = (
                    f"{index}. {profile.name} "
                    f"({profile.input_type or '?'} → {profile.output_type or '?'})"
                )
            self.step_list.addItem(text)

        self.preview.setText(self._pipeline_preview())
        self.select_step(self.step_list.currentRow())

    def _pipeline_preview(self):
        stage = self.source_type
        parts = [stage]
        warnings = []

        for step in self.steps:
            profile = self._profile(
                step.get("profile")
            )

            if profile is None:
                warnings.append(
                    f"Unknown profile: {step.get('profile')}"
                )
                continue

            expected = profile.input_type
            if expected and expected != "none" and expected != stage:
                warnings.append(
                    f"{profile.name} expects {expected} but current stage is {stage}"
                )

            stage = profile.output_type or stage
            parts.append(stage)

        summary = " → ".join(parts)

        if warnings:
            summary += "\n⚠ " + "\n⚠ ".join(warnings)

        return summary

    def result_steps(self):
        return [dict(step) for step in self.steps]


class JobPropertiesPanel(QFrame):
    changed = Signal()
    converted = Signal(str)

    def __init__(

        self,
        jobs,
        workspace,
        profiles=None,
        preview=None,
    ):
        super().__init__()
        print(
            "RUNTIME PROFILE TRACE: PANEL INIT",
            "class=",
            type(self).__name__,
            "profiles=",
            [getattr(p, "name", repr(p)) for p in getattr(self, "profiles", [])],
            flush=True,
        )

        self.jobs = jobs
        self.workspace = workspace
        self.profiles = profiles or []
        self.preview = preview
        self.job = None

        layout = QVBoxLayout(self)

        title = QLabel("<b>Job Properties</b>")
        layout.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(
            self.content
        )

        self.scroll.setWidget(
            self.content
        )

        layout.addWidget(self.scroll)

        self.build_empty()

    def clear_layout(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)

            widget = item.widget()

            if widget:
                widget.deleteLater()

    def build_empty(self):
        self.clear_layout()

        self.content_layout.addWidget(
            QLabel(
                "Select a job to edit its properties."
            )
        )

        self.content_layout.addStretch()

    def set_job(self, job_id):
        self.job = self.jobs.get(job_id)

        if self.job is None:
            self.build_empty()
            return

        self.build()

    def _metric(self, name, value):
        row = QHBoxLayout()

        row.addWidget(
            QLabel(name)
        )

        label = QLabel(value)
        label.setAlignment(
            Qt.AlignRight
            | Qt.AlignVCenter
        )

        row.addWidget(label)

        wrapper = QWidget()
        wrapper.setLayout(row)

        return wrapper

    def _job_metrics(self, job):
        if hasattr(self.jobs, "metrics"):
            try:
                return self.jobs.metrics(job)
            except Exception:
                pass

        return {
            "time": getattr(
                job,
                "estimated_time",
                0.0,
            ),
            "draw_distance": getattr(
                job,
                "drawing_distance",
                0.0,
            ),
            "travel_distance": getattr(
                job,
                "travel_distance",
                0.0,
            ),
        }

    def _format_time(self, seconds):
        try:
            seconds = float(seconds)
        except Exception:
            seconds = 0

        if seconds < 60:
            return f"{seconds:.1f} s"

        minutes = int(seconds // 60)
        remaining = int(seconds % 60)

        if minutes < 60:
            return f"{minutes}m {remaining:02d}s"

        hours = minutes // 60
        minutes %= 60

        return f"{hours}h {minutes:02d}m"

    def build(self):
        job = self.job

        if job is None:
            self.build_empty()
            return

        self.clear_layout()

        # ----------------------------------------------------
        # File
        # ----------------------------------------------------

        file_group = QGroupBox("File")
        file_layout = QVBoxLayout(file_group)

        file_layout.addWidget(
            QLabel(job.name)
        )

        source_svg_id = getattr(
            job,
            "source_svg_id",
            None,
        )

        if source_svg_id:
            source = self.jobs.get(source_svg_id)

            if source:
                file_layout.addWidget(
                    QLabel(
                        f"Generated from SVG: {source.name}"
                    )
                )

        self.content_layout.addWidget(
            file_group
        )

        # ----------------------------------------------------
        # G-code
        # ----------------------------------------------------

        is_gcode = (
            str(
                getattr(
                    job,
                    "source_type",
                    "",
                )
            ).lower().endswith("gcode")
        )

        if is_gcode:
            save = QPushButton(
                "Save G-code..."
            )

            save.clicked.connect(
                self.save_gcode
            )

            self.content_layout.addWidget(save)

        # ----------------------------------------------------
        # Active
        # ----------------------------------------------------

        active = QCheckBox("Active")
        active.setChecked(
            getattr(
                job,
                "active",
                True,
            )
        )

        active.toggled.connect(
            self.update_active
        )

        self.content_layout.addWidget(active)

        # ----------------------------------------------------
        # Conversion
        # ----------------------------------------------------

        source_type = str(
            getattr(
                job,
                "source_type",
                "",
            )
        ).lower()

        print(
            "RUNTIME PROFILE TRACE: SVG condition",
            repr(source_type),
            source_type.endswith("svg"),
            flush=True,
        )

        is_svg = source_type.endswith("svg")
        is_dummy = source_type.endswith("dummy")

        if is_svg or is_dummy:
            conversion = QGroupBox(
                "Pipeline"
            )

            conversion_layout = QVBoxLayout(
                conversion
            )

            profile_row = QHBoxLayout()

            profile_row.addWidget(
                QLabel("Profile")
            )

            self.profile_combo = QComboBox()

            if is_svg:
                input_type = "svg"
            else:
                input_type = "none"

            for profile in self.profiles:
                name = getattr(
                    profile,
                    "name",
                    str(profile),
                )
                profile_input = str(
                    getattr(
                        profile,
                        "input_type",
                        "",
                    )
                    or ""
                ).lower()
                if (
                    profile_input
                    and profile_input
                    not in {input_type, "none"}
                ):
                    continue

                self.profile_combo.addItem(
                    name,
                    profile,
                )

            print(
                "RUNTIME PROFILE TRACE: final combo",
                "count=",
                self.profile_combo.count(),
                "items=",
                [
                    self.profile_combo.itemText(i)
                    for i in range(self.profile_combo.count())
                ],
                flush=True,
            )

            profile_row.addWidget(
                self.profile_combo
            )

            if is_svg:
                conversion_layout.addLayout(
                    profile_row
                )

            params = QWidget()
            params_layout = QVBoxLayout(params)

            params_layout.addWidget(
                QLabel(
                    "Conversion parameters"
                )
            )

            # Profile systems from earlier versions may expose
            # a parameter dictionary.  Show editable values where
            # possible without requiring a specific profile class.
            self.parameter_widgets = {}
            self.parameter_specs = {}

            def rebuild_parameters():
                while params_layout.count():
                    item = params_layout.takeAt(0)
                    widget = item.widget()

                    if widget:
                        widget.deleteLater()

                profile = self.profile_combo.currentData()

                parameters = getattr(
                    profile,
                    "parameters",
                    {},
                )

                if callable(parameters):
                    try:
                        parameters = parameters()
                    except Exception:
                        parameters = {}

                if not isinstance(parameters, dict):
                    parameters = {}

                self.parameter_widgets.clear()
                self.parameter_specs.clear()

                for name, specification in parameters.items():
                    row = QHBoxLayout()

                    row.addWidget(
                        QLabel(str(name))
                    )

                    spec_type = (
                        str(
                            specification.get(
                                "type",
                                "string",
                            )
                        ).lower()
                        if isinstance(
                            specification,
                            dict,
                        )
                        else "string"
                    )

                    value = (
                        specification.get("default")
                        if isinstance(
                            specification,
                            dict,
                        )
                        else specification
                    )

                    if spec_type == "boolean":
                        widget = QCheckBox()
                        widget.setChecked(
                            self._coerce_bool(value)
                        )

                    elif spec_type in {
                        "number",
                        "integer",
                    }:
                        widget = QDoubleSpinBox()
                        widget.setRange(
                            -1000000,
                            1000000,
                        )
                        widget.setDecimals(4)
                        try:
                            widget.setValue(
                                float(value)
                            )
                        except (
                            TypeError,
                            ValueError,
                        ):
                            widget.setValue(0.0)

                    else:
                        widget = QLineEdit(
                            "" if value is None
                            else str(value)
                        )

                    row.addWidget(widget)

                    wrapper = QWidget()
                    wrapper.setLayout(row)

                    params_layout.addWidget(
                        wrapper
                    )

                    self.parameter_widgets[name] = widget
                    if isinstance(
                        specification,
                        dict,
                    ):
                        self.parameter_specs[
                            str(name)
                        ] = dict(specification)
                    else:
                        self.parameter_specs[
                            str(name)
                        ] = {
                            "type": "string"
                        }

                params_layout.addStretch()

            if is_svg:
                rebuild_parameters()

                self.profile_combo.currentIndexChanged.connect(
                    rebuild_parameters
                )

                collapsible = CollapsibleSection(
                    "Conversion parameters",
                    params,
                    expanded=False,
                )

                conversion_layout.addWidget(
                    collapsible
                )

                convert = QPushButton(
                    "Convert to G-code"
                )

                convert.clicked.connect(
                    self.convert_to_gcode
                )

                conversion_layout.addWidget(
                    convert
                )
            else:
                info = QLabel(
                    "Dummy jobs start without input.\n"
                    "Use a pipeline that can generate output."
                )
                conversion_layout.addWidget(info)
                convert = QPushButton(
                    "Run pipeline to G-code"
                )
                convert.clicked.connect(
                    self.convert_to_gcode
                )
                conversion_layout.addWidget(convert)

            pipeline = QPushButton(
                "Edit pipeline"
                if getattr(
                    job,
                    "pipeline_steps",
                    [],
                )
                else "Add pipeline"
            )
            pipeline.clicked.connect(
                self.configure_pipeline
            )
            conversion_layout.addWidget(
                pipeline
            )

            self.pipeline_summary = QLabel(
                self.pipeline_text(job)
            )
            self.pipeline_summary.setWordWrap(True)
            conversion_layout.addWidget(
                self.pipeline_summary
            )

            self.content_layout.addWidget(
                conversion
            )

        # ----------------------------------------------------
        # Placement
        # ----------------------------------------------------

        placement = QGroupBox(
            "Placement"
        )

        placement_layout = QVBoxLayout(
            placement
        )

        self.origin_checks = []

        # Machine origin is explicitly represented as one of
        # the placement options and is selected by default.
        machine_check = QCheckBox(
            "Machine Origin"
        )

        machine_check.setChecked(
            getattr(
                job,
                "origin",
                "machine",
            ) == "machine"
        )

        machine_check.toggled.connect(
            lambda checked:
            self.origin_toggled(
                "machine",
                checked,
            )
        )

        placement_layout.addWidget(
            machine_check
        )

        self.origin_checks.append(
            ("machine", machine_check)
        )

        for anchor in self.workspace.anchors:
            check = QCheckBox(anchor.name)

            check.setChecked(
                getattr(
                    job,
                    "origin",
                    "machine",
                ) == anchor.name
            )

            check.toggled.connect(
                lambda checked,
                name=anchor.name:
                self.origin_toggled(
                    name,
                    checked,
                )
            )

            placement_layout.addWidget(check)

            self.origin_checks.append(
                (
                    anchor.name,
                    check,
                )
            )

        select_row = QHBoxLayout()

        select_all = QPushButton(
            "Select all"
        )

        deselect_all = QPushButton(
            "Deselect all"
        )

        select_all.clicked.connect(
            lambda:
            self.set_all_anchors(True)
        )

        deselect_all.clicked.connect(
            lambda:
            self.set_all_anchors(False)
        )

        select_row.addWidget(select_all)
        select_row.addWidget(deselect_all)

        placement_layout.addLayout(
            select_row
        )

        self.content_layout.addWidget(
            placement
        )

        # ----------------------------------------------------
        # Transform
        # ----------------------------------------------------

        transform = QGroupBox(
            "Transform"
        )

        transform_layout = QVBoxLayout(
            transform
        )

        self.offset_x = self.number(
            "Offset X",
            job.transform.offset_x,
            self.update_offset,
        )

        self.offset_y = self.number(
            "Offset Y",
            job.transform.offset_y,
            self.update_offset,
        )

        self.offset_z = self.number(
            "Offset Z",
            job.transform.offset_z,
            self.update_offset,
        )

        transform_layout.addWidget(
            self.offset_x[0]
        )

        transform_layout.addWidget(
            self.offset_y[0]
        )

        transform_layout.addWidget(
            self.offset_z[0]
        )

        self.scale = self.number(
            "Scale",
            job.transform.scale,
            self.update_scale,
            minimum=0.001,
            maximum=1000,
            decimals=4,
        )

        self.rotation = self.number(
            "Rotation",
            job.transform.rotation,
            self.update_rotation,
            minimum=-360,
            maximum=360,
        )

        transform_layout.addWidget(
            self.scale[0]
        )

        transform_layout.addWidget(
            self.rotation[0]
        )

        transform_layout.addWidget(
            self.make_flip(
                "Flip X",
                job.transform.flip_x,
                self.update_flip_x,
            )
        )

        transform_layout.addWidget(
            self.make_flip(
                "Flip Y",
                job.transform.flip_y,
                self.update_flip_y,
            )
        )

        # New variants: flip geometry while preserving its
        # bounding-box position.
        transform_layout.addWidget(
            self.make_flip(
                "Flip X — keep bounding box",
                getattr(
                    job.transform,
                    "flip_x_keep_bbox",
                    False,
                ),
                self.update_flip_x_keep_bbox,
            )
        )

        transform_layout.addWidget(
            self.make_flip(
                "Flip Y — keep bounding box",
                getattr(
                    job.transform,
                    "flip_y_keep_bbox",
                    False,
                ),
                self.update_flip_y_keep_bbox,
            )
        )

        self.content_layout.addWidget(
            transform
        )

        # ----------------------------------------------------
        # Preview
        # ----------------------------------------------------

        preview = QGroupBox(
            "Preview"
        )

        preview_layout = QVBoxLayout(
            preview
        )

        limit_row = QHBoxLayout()

        limit_row.addWidget(
            QLabel("Instruction limit")
        )

        self.preview_limit = QSpinBox()
        self.preview_limit.setRange(
            100,
            1000000,
        )

        self.preview_limit.setValue(
            getattr(
                self.workspace,
                "preview_limit",
                20000,
            )
        )

        self.preview_limit.valueChanged.connect(
            self.preview_limit_changed
        )

        limit_row.addWidget(
            self.preview_limit
        )

        preview_layout.addLayout(
            limit_row
        )

        drawing = QCheckBox(
            "Show drawing moves"
        )

        drawing.setChecked(
            getattr(
                self.workspace,
                "show_drawing",
                True,
            )
        )

        drawing.toggled.connect(
            self.preview_drawing_changed
        )

        travel = QCheckBox(
            "Show travel moves"
        )

        travel.setChecked(
            self.workspace.show_travel
        )

        travel.toggled.connect(
            self.preview_travel_changed
        )

        preview_layout.addWidget(drawing)
        preview_layout.addWidget(travel)

        self.content_layout.addWidget(
            preview
        )

        # ----------------------------------------------------
        # Metrics
        # ----------------------------------------------------

        metrics = QGroupBox(
            "G-code information"
        )

        metrics_layout = QVBoxLayout(
            metrics
        )

        data = self._job_metrics(job)

        metrics_layout.addWidget(
            self._metric(
                "Total time",
                self._format_time(
                    data.get("time", 0)
                ),
            )
        )

        metrics_layout.addWidget(
            self._metric(
                "Drawing distance",
                f"{data.get('draw_distance', 0):.1f} mm",
            )
        )

        metrics_layout.addWidget(
            self._metric(
                "Travel distance",
                f"{data.get('travel_distance', 0):.1f} mm",
            )
        )

        self.content_layout.addWidget(
            metrics
        )

        self.content_layout.addStretch()

    # --------------------------------------------------------
    # Controls
    # --------------------------------------------------------

    def number(
        self,
        label,
        value,
        callback,
        minimum=-100000,
        maximum=100000,
        decimals=2,
    ):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(
            QLabel(label)
        )

        spin = QDoubleSpinBox()
        spin.setRange(
            minimum,
            maximum,
        )
        spin.setDecimals(decimals)
        spin.setValue(value)

        spin.valueChanged.connect(callback)

        layout.addWidget(spin)

        return row, spin

    def make_flip(
        self,
        label,
        checked,
        callback,
    ):
        check = QCheckBox(label)
        check.setChecked(checked)
        check.toggled.connect(callback)
        return check

    def update_active(self, value):
        if self.job:
            self.job.active = value
            self.changed.emit()

    def origin_toggled(self, name, checked):
        if not self.job or not checked:
            return

        for other_name, check in self.origin_checks:
            if other_name != name:
                check.blockSignals(True)
                check.setChecked(False)
                check.blockSignals(False)

        self.job.origin = name

        self.changed.emit()

    def set_all_anchors(self, enabled):
        """
        Selecting all anchors means machine origin plus every
        anchor is enabled as a repeated placement.

        Machine origin remains the primary origin.
        """

        if not self.job:
            return

        machine = self.origin_checks[0][1]

        machine.blockSignals(True)
        machine.setChecked(True)
        machine.blockSignals(False)

        self.job.origin = "machine"

        names = []

        for name, check in self.origin_checks[1:]:
            check.blockSignals(True)
            check.setChecked(enabled)
            check.blockSignals(False)

            if enabled:
                names.append(name)

        self.job.repeated_anchors = names

        self.changed.emit()

    def update_offset(self):
        if self.job:
            self.job.transform.offset_x = (
                self.offset_x[1].value()
            )

            self.job.transform.offset_y = (
                self.offset_y[1].value()
            )

            self.job.transform.offset_z = (
                self.offset_z[1].value()
            )

            self.changed.emit()

    def update_scale(self):
        if self.job:
            self.job.transform.scale = (
                self.scale[1].value()
            )
            self.changed.emit()

    def update_rotation(self):
        if self.job:
            self.job.transform.rotation = (
                self.rotation[1].value()
            )
            self.changed.emit()

    def update_flip_x(self, value):
        if self.job:
            self.job.transform.flip_x = value
            self.changed.emit()

    def update_flip_y(self, value):
        if self.job:
            self.job.transform.flip_y = value
            self.changed.emit()

    def update_flip_x_keep_bbox(self, value):
        if self.job:
            self.job.transform.flip_x_keep_bbox = value
            self.changed.emit()

    def update_flip_y_keep_bbox(self, value):
        if self.job:
            self.job.transform.flip_y_keep_bbox = value
            self.changed.emit()

    def preview_limit_changed(self, value):
        self.workspace.preview_limit = value
        state_store.set(
            "preview.limit",
            int(value),
        )
        if self.preview is not None:
            self.preview.preview_limit = value
            self.preview.update()

    def preview_drawing_changed(self, value):
        self.workspace.show_drawing = value
        state_store.set(
            "preview.show_drawing",
            bool(value),
        )
        if self.preview is not None:
            self.preview.show_drawing = value
            self.preview.update()

    def preview_travel_changed(self, value):
        self.workspace.show_travel = value
        state_store.set(
            "preview.show_travel",
            bool(value),
        )
        if self.preview is not None:
            self.preview.show_travel = value
            self.preview.update()

    def _profile_by_name(self, name):
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None

    def _coerce_bool(self, value) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _append_parameter_args(
        self,
        command,
        profile,
        parameters,
    ):
        profile_parameters = getattr(
            profile,
            "parameters",
            {},
        )
        if not isinstance(profile_parameters, dict):
            profile_parameters = {}

        for name, value in parameters.items():
            if value is None:
                continue

            option = f"--{name}"

            specification = profile_parameters.get(
                name,
                {},
            )
            parameter_type = (
                str(
                    specification.get(
                        "type",
                        "",
                    )
                ).lower()
                if isinstance(
                    specification,
                    dict,
                )
                else ""
            )

            if parameter_type == "boolean":
                if self._coerce_bool(value):
                    command.append(option)
                continue

            if isinstance(value, bool):
                if value:
                    command.append(option)
                continue

            command.extend(
                [
                    option,
                    str(value),
                ]
            )

    def pipeline_text(self, job):
        steps = getattr(job, "pipeline_steps", [])

        if not steps:
            return "Pipeline: none"

        source_type = str(
            getattr(
                getattr(job, "source_type", None),
                "value",
                getattr(job, "source_type", ""),
            )
        ).lower()

        parts = [source_type]

        for step in steps:
            profile = self._profile_by_name(
                step.get("profile")
            )
            if profile is None:
                parts.append("?")
                continue
            parts.append(profile.output_type or "?")

        return "Pipeline: " + " → ".join(parts)

    def configure_pipeline(self):
        if not self.job:
            return

        source_type = str(
            getattr(
                getattr(self.job, "source_type", None),
                "value",
                getattr(self.job, "source_type", ""),
            )
        ).lower()

        dialog = PipelineDialog(
            self,
            self.profiles,
            source_type,
            getattr(self.job, "pipeline_steps", []),
        )

        if dialog.exec() != QDialog.Accepted:
            return

        self.job.pipeline_steps = dialog.result_steps()

        if hasattr(self, "pipeline_summary"):
            self.pipeline_summary.setText(
                self.pipeline_text(self.job)
            )

        self.changed.emit()

    # --------------------------------------------------------
    # Conversion / save
    # --------------------------------------------------------

    def _parameters(self):
        result = {}

        for name, widget in getattr(
            self,
            "parameter_widgets",
            {},
        ).items():
            if isinstance(widget, QCheckBox):
                result[name] = widget.isChecked()

            elif isinstance(widget, QDoubleSpinBox):
                result[name] = widget.value()

            elif isinstance(widget, QSpinBox):
                result[name] = widget.value()

            elif isinstance(widget, QComboBox):
                result[name] = widget.currentText()

            elif isinstance(widget, QLineEdit):
                result[name] = widget.text()

        return result

    def convert_to_gcode(self):
        if not self.job:
            return

        if not hasattr(self, "profile_combo"):
            return

        profile = self.profile_combo.currentData()

        if profile is None:
            return

        parameters = self._parameters()
        steps = list(
            getattr(self.job, "pipeline_steps", [])
        )

        if not steps:
            steps = [
                {
                    "profile": profile.name,
                    "parameters": parameters,
                }
            ]

        current_type = str(
            getattr(
                getattr(self.job, "source_type", None),
                "value",
                getattr(self.job, "source_type", ""),
            )
        ).lower()
        current_path = (
            Path(self.job.source)
            if str(
                getattr(
                    getattr(self.job, "source_type", None),
                    "value",
                    getattr(self.job, "source_type", ""),
                )
            ).lower() != "dummy"
            else None
        )
        gcode = ""
        temp_paths = []

        try:
            for index, step in enumerate(steps):
                step_profile = self._profile_by_name(
                    step.get("profile")
                )

                if step_profile is None:
                    raise RuntimeError(
                        f"Unknown profile in pipeline: {step.get('profile')}"
                    )

                expected = str(
                    step_profile.input_type or ""
                ).lower()

                if expected and expected != "none" and expected != current_type:
                    raise RuntimeError(
                        f"Profile '{step_profile.name}' expects '{expected}', got '{current_type}'"
                    )

                command = profile_command(
                    step_profile.command
                )

                if expected != "none":
                    if current_path is None:
                        raise RuntimeError(
                            f"Profile '{step_profile.name}' requires input but no stage input is available"
                        )
                    command.extend(
                        [
                            "--input",
                            str(current_path),
                        ]
                    )

                command.extend(
                    [
                        "--output",
                        "-",
                    ]
                )

                self._append_parameter_args(
                    command,
                    step_profile,
                    step.get(
                        "parameters",
                        {},
                    ),
                )

                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    error = (
                        result.stderr.strip()
                        or result.stdout.strip()
                        or (
                            "Conversion profile exited "
                            f"with code {result.returncode}"
                        )
                    )
                    raise RuntimeError(error)

                output = result.stdout

                if not output.strip():
                    raise RuntimeError(
                        f"Profile '{step_profile.name}' produced no output"
                    )

                output_type = str(
                    step_profile.output_type or ""
                ).lower()

                if not output_type:
                    output_type = (
                        "gcode"
                        if index == len(steps) - 1
                        else current_type
                    )

                if output_type == "svg":
                    temp = tempfile.NamedTemporaryFile(
                        suffix=".svg",
                        delete=False,
                    )
                    temp.write(
                        output.encode("utf-8")
                    )
                    temp.close()
                    temp_paths.append(temp.name)
                    current_path = Path(temp.name)
                    current_type = "svg"
                    continue

                if output_type == "gcode":
                    gcode = output
                    current_type = "gcode"

                    if index < len(steps) - 1:
                        temp = tempfile.NamedTemporaryFile(
                            suffix=".gcode",
                            delete=False,
                        )
                        temp.write(
                            output.encode("utf-8")
                        )
                        temp.close()
                        temp_paths.append(temp.name)
                        current_path = Path(temp.name)
                    continue

                raise RuntimeError(
                    f"Unsupported profile output type: {output_type}"
                )

            if current_type != "gcode" or not gcode.strip():
                raise RuntimeError(
                    "Pipeline must end with G-code output"
                )

            new_job = self.jobs.create_generated_gcode(
                self.job,
                gcode,
                steps[-1].get("profile", profile.name),
                steps[-1].get(
                    "parameters",
                    {},
                ),
            )

            self.converted.emit(
                new_job.id
            )

        except Exception as exc:
            show_critical(
                self,
                "Conversion failed",
                str(exc),
            )
        finally:
            for temp_path in temp_paths:
                try:
                    Path(temp_path).unlink()
                except OSError:
                    pass

    def save_gcode(self):
        if not self.job:
            return

        gcode = getattr(
            self.job,
            "gcode",
            None,
        )

        if not gcode:
            try:
                gcode = Path(
                    self.job.source
                ).read_text(
                    encoding="utf-8"
                )
            except Exception as exc:
                show_critical(
                    self,
                    "Save failed",
                    str(exc),
                )
                return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save G-code",
            self.job.name,
            "G-code (*.gcode *.nc *.ngc);;All files (*)",
        )

        if not filename:
            return

        try:
            Path(filename).write_text(
                gcode,
                encoding="utf-8",
            )

            self.job.source = Path(filename)
            self.job.name = Path(filename).name

        except Exception as exc:
            show_critical(
                self,
                "Save failed",
                str(exc),
            )

class MainWindow(QMainWindow):

    def __init__(
        self,
        config,
    ):

        print("RUNTIME PROFILE TRACE: MAINWINDOW INIT", flush=True)
        print("  config.profiles:", [getattr(p, "name", repr(p)) for p in getattr(config, "profiles", [])], flush=True)
        super().__init__()

        self.setWindowTitle(
            "PlotPilot"
        )

        self.resize(
            1500,
            900,
        )

        self.machine = (
            FluidNCController(
                config.host,
                config.port,
            )
        )

        self.workspace_config = (
            config.workspace
        )

        self.profiles = (
            config.profiles
        )

        self.jobs = JobManager()
        self.poll_worker = None

        # ----------------------------------------------------
        # Panels
        # ----------------------------------------------------

        self.machine_panel = (
            MachinePanel(
                self.machine
            )
        )

        self.job_list = (
            JobListPanel(
                self.jobs
            )
        )

        self.workspace = (
            WorkspaceView(
                config.workspace,
                self.jobs,
            )
        )
        self.workspace.preview_limit = int(
            state_store.get(
                "preview.limit",
                self.workspace.preview_limit,
            )
        )
        self.workspace.show_drawing = bool(
            state_store.get(
                "preview.show_drawing",
                self.workspace.show_drawing,
            )
        )
        self.workspace.show_travel = bool(
            state_store.get(
                "preview.show_travel",
                self.workspace.show_travel,
            )
        )

        print(
            "RUNTIME PROFILE TRACE: BEFORE PROPERTY PANEL",
            "self.profiles=",
            [getattr(p, "name", repr(p)) for p in self.profiles],
            flush=True,
        )

        self.properties = (
            JobPropertiesPanel(
                self.jobs,
                config.workspace,
                self.profiles,
                self.workspace,
            )
        )

        # ----------------------------------------------------
        # Layout
        # ----------------------------------------------------

        left = QWidget()

        left_layout = QVBoxLayout(
            left
        )

        left_layout.addWidget(
            self.machine_panel
        )

        left_layout.addWidget(
            self.job_list
        )

        splitter = QSplitter(
            Qt.Horizontal
        )

        splitter.addWidget(left)
        splitter.addWidget(
            self.workspace
        )
        splitter.addWidget(
            self.properties
        )

        splitter.setSizes(
            [
                300,
                900,
                350,
            ]
        )

        splitter.setStretchFactor(
            0,
            0,
        )

        splitter.setStretchFactor(
            1,
            1,
        )

        splitter.setStretchFactor(
            2,
            0,
        )

        self.setCentralWidget(
            splitter
        )

        # ----------------------------------------------------
        # Signals
        # ----------------------------------------------------

        self.job_list.selected.connect(
            self.select_job
        )

        self.job_list.changed.connect(
            self.refresh
        )

        self.workspace.jobSelected.connect(
            self.select_job
        )

        self.workspace.jobMoved.connect(
            self.workspace_job_moved
        )

        self.workspace.moveMachineRequested.connect(
            self.move_machine
        )

        self.properties.changed.connect(
            self.refresh
        )

        self.properties.converted.connect(
            self.conversion_finished
        )

        # ----------------------------------------------------
        # Status polling
        # ----------------------------------------------------

        self.timer = QTimer(self)

        self.timer.setInterval(
            250
        )

        self.timer.timeout.connect(
            self.update_machine
        )

        self.timer.start()

        self.job_list.refresh()

    def refresh(self):

        selected = None

        if self.properties.job:

            selected = (
                self.properties.job.id
            )

        self.workspace.update()

        self.job_list.refresh(
            selected
        )

    def select_job(
        self,
        job_id,
    ):

        if not job_id:
            return

        self.workspace.set_selected(
            job_id
        )

        self.properties.set_job(
            job_id
        )

    def workspace_job_moved(
        self,
        job_id,
    ):

        if (
            self.properties.job
            and self.properties.job.id
            == job_id
        ):

            self.properties.set_job(
                job_id
            )

        self.workspace.update()

    def conversion_finished(
        self,
        job_id,
    ):

        # Automatically select the new G-code job.

        self.job_list.refresh(
            job_id
        )

        self.select_job(
            job_id
        )

        self.workspace.update()

    def move_machine(
        self,
        x,
        y,
    ):

        if not self.machine.state.connected:
            return

        try:

            self.machine.move_to(
                x,
                y,
                self.machine.state.z,
            )

        except Exception as exc:

            show_warning(
                self,
                "Machine move failed",
                str(exc),
            )

    def update_machine(self):

        self.machine_panel.update_state()

        if (
            not self.machine.state.connected
        ):
            return

        # Do not block the GUI thread.

        if (
            self.poll_worker is not None
            and self.poll_worker.isRunning()
        ):
            return

        self.poll_worker = (
            PollWorker(
                self.machine
            )
        )

        self.poll_worker.updated.connect(
            self.machine_updated
        )

        self.poll_worker.failed.connect(
            self.machine_poll_failed
        )

        self.poll_worker.start()

    def machine_updated(self):

        state = self.machine.state

        self.workspace.set_machine_position(
            state.x,
            state.y,
        )

        self.machine_panel.update_state()

    def machine_poll_failed(
        self,
        message,
    ):

        self.machine.state.message = message

        self.machine_panel.update_state()


# ============================================================
# Default profiles
# ============================================================

def ensure_default_config():

    path = CONFIG_PATH

    if path.exists():
        return

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = {
        "machine": {
            "host": "fluidnc.local",
            "port": 80,
            "workspace": {
                "width": 300,
                "height": 200,
                "depth": 0,
                "anchors": [
                    {
                        "name": "A",
                        "x": 0,
                        "y": 0,
                    },
                    {
                        "name": "B",
                        "x": 150,
                        "y": 0,
                    },
                    {
                        "name": "C",
                        "x": 300,
                        "y": 0,
                    },
                ],
            },
            "profiles": [],
        }
    }

    path.write_text(
        json.dumps(
            data,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# Temporary conversion files
# ============================================================

PLOTPILOT_TEMP_DIR = Path(
    '/home/erik/Projects/plotter/PlotterPilot/plotpilot/.tmp'
)

PLOTPILOT_TEMP_MAX_AGE_DAYS = 7


def cleanup_conversion_temp():
    PLOTPILOT_TEMP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cutoff = (
        datetime.now().timestamp()
        - (
            PLOTPILOT_TEMP_MAX_AGE_DAYS
            * 24
            * 60
            * 60
        )
    )

    for item in PLOTPILOT_TEMP_DIR.iterdir():
        try:
            if item.stat().st_mtime < cutoff:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    import shutil
                    shutil.rmtree(item)
        except Exception as exc:
            print(
                "WARNING: failed to clean temporary file "
                f"{item}: {exc}",
                file=sys.stderr,
            )


# ============================================================
# Application
# ============================================================


def main():
    print("RUNTIME MAIN: entered", flush=True)
    project_dir = (
        Path(__file__).resolve().parent
    )

    config_path = (
        project_dir
        / "config"
        / "default.json"
    )

    if not config_path.exists():
        print(
            f"Configuration not found: {config_path}",
            file=sys.stderr,
        )

        return 1

    config = load_config(
        config_path
    )
    logging.basicConfig(
        level=getattr(
            logging,
            str(config.log_level).upper(),
            logging.INFO,
        ),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cleanup_conversion_temp()
    print("RUNTIME MAIN: config loaded", flush=True)

    app = QApplication(
        sys.argv
    )

    # --------------------------------------------------------
    # Clean, readable light palette.
    # --------------------------------------------------------

    palette = QPalette()

    palette.setColor(
        QPalette.Window,
        QColor("#f4f5f6"),
    )

    palette.setColor(
        QPalette.WindowText,
        QColor("#202428"),
    )

    palette.setColor(
        QPalette.Base,
        QColor("#ffffff"),
    )

    palette.setColor(
        QPalette.AlternateBase,
        QColor("#eef0f2"),
    )

    palette.setColor(
        QPalette.Text,
        QColor("#202428"),
    )

    palette.setColor(
        QPalette.Button,
        QColor("#e4e7ea"),
    )

    palette.setColor(
        QPalette.ButtonText,
        QColor("#202428"),
    )

    palette.setColor(
        QPalette.Highlight,
        QColor("#3b78b4"),
    )

    palette.setColor(
        QPalette.HighlightedText,
        QColor("#ffffff"),
    )

    app.setPalette(palette)

    app.setStyleSheet(
        """
        QWidget {
            color: #202428;
        }

        QGroupBox {
            font-weight: 600;
            border: 1px solid #c7ccd1;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }

        QPushButton {
            padding: 5px 9px;
            border: 1px solid #b9bec3;
            border-radius: 4px;
            background: #e4e7ea;
        }

        QPushButton:hover {
            background: #d9dde1;
        }

        QPushButton:disabled {
            color: #8a9095;
        }

        QLineEdit,
        QSpinBox,
        QDoubleSpinBox,
        QComboBox {
            background: #ffffff;
            border: 1px solid #b9bec3;
            border-radius: 4px;
            padding: 3px;
        }

        QListWidget {
            background: #ffffff;
            border: 1px solid #c7ccd1;
        }

        QScrollArea {
            border: none;
        }
        """
    )

    window = MainWindow(
        config
    )
    print("RUNTIME MAIN: window created", flush=True)

    window.show()
    print("RUNTIME MAIN: window shown", flush=True)

    # --------------------------------------------------------
    # Ctrl+C / terminal shutdown.
    #
    # Python normally doesn't deliver SIGINT reliably while Qt
    # owns the event loop.  Wake the Qt loop explicitly.
    # --------------------------------------------------------

    def handle_sigint(signum, frame):
        app.quit()

    signal.signal(
        signal.SIGINT,
        handle_sigint,
    )

    # Keep Python processing signals while Qt is idle.
    signal_timer = QTimer()

    signal_timer.setInterval(250)

    signal_timer.timeout.connect(
        lambda: None
    )

    signal_timer.start()

    print("RUNTIME MAIN: entering Qt event loop", flush=True)
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(
        main()
    )



    def closeEvent(self, event):
        """Stop timers/workers before closing the GUI."""

        timer = getattr(self, "timer", None)

        if timer is not None:
            timer.stop()

        panel = getattr(
            self,
            "machine_panel",
            None,
        )

        worker = (
            getattr(panel, "worker", None)
            if panel is not None
            else None
        )

        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.quit()

            if not worker.wait(1000):
                # The worker is performing controller I/O.
                # Do not block application shutdown indefinitely.
                pass

        try:
            if self.machine.state.connected:
                self.machine.disconnect()
        except Exception:
            pass

        event.accept()
