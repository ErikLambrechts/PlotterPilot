import math
import re
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QThread,
    QTimer,
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
    QFileDialog,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


"""
PlotPilot module extracted from plotpilot.py.

This module is intentionally conservative.
The first refactor keeps the existing implementation intact.
"""

class MachinePanel(QFrame):
    stateChanged = Signal()

    def __init__(self, machine):
        super().__init__()

        self.profiles = profiles or []

        self.machine = machine
        self.worker = None

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel("<b>Machine</b>")
        )

        connection = QGroupBox("Connection")
        connection_layout = QVBoxLayout(connection)

        row = QHBoxLayout()
        row.addWidget(QLabel("Host"))

        self.host = QLineEdit(
            machine.host
        )

        row.addWidget(self.host)
        connection_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Port"))

        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(machine.port)

        row.addWidget(self.port)
        connection_layout.addLayout(row)

        layout.addWidget(connection)

        self.connect_button = QPushButton(
            "Connect"
        )

        self.connect_button.clicked.connect(
            self.toggle
        )

        layout.addWidget(
            self.connect_button
        )

        self.status = QLabel(
            "Disconnected"
        )

        layout.addWidget(
            self.status
        )

        self.position = QLabel(
            "X: --\nY: --\nZ: --"
        )

        layout.addWidget(
            self.position
        )

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
        self.step.setValue(10)
        self.step.setDecimals(2)

        row.addWidget(self.step)

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
        profiles=None
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

                QMessageBox.warning(
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

        self.jobs = jobs
        self.workspace = workspace
        self.preview = preview
        self.profiles = profiles or []
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

        print(
            "=== RUNTIME JobPropertiesPanel.build ==="
        )
        print(
            "job:",
            self.job,
        )
        print(
            "job.source_type:",
            repr(
                getattr(
                    self.job,
                    "source_type",
                    None,
                )
            ),
        )
        print(
            "job.name:",
            repr(
                getattr(
                    self.job,
                    "name",
                    None,
                )
            ),
        )
        print(
            "job.source:",
            repr(
                getattr(
                    self.job,
                    "source",
                    None,
                )
            ),
        )
        print(
            "self.profiles:",
            [
                getattr(p, "name", repr(p))
                for p in self.profiles
            ],
        )
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

        # A conversion profile is available whenever the current
        # job represents an SVG source. Different parts of PlotPilot
        # may identify the source using source_type or the source
        # filename, so accept both representations.
        source_path = getattr(
            job,
            "source",
            None,
        )

        source_name = str(
            getattr(
                job,
                "name",
                "",
            )
        ).lower()

        source_file = str(
            source_path or ""
        ).lower()

        is_svg = (
            source_type.endswith("svg")
            or source_name.endswith(".svg")
            or source_file.endswith(".svg")
        )

        print(
            "JobPropertiesPanel SVG detection:",
            {
                "source_type": source_type,
                "name": source_name,
                "source": source_file,
                "is_svg": is_svg,
                "profiles": [
                    profile.name
                    for profile in self.profiles
                ],
            }
        )

        print(
            "=== RUNTIME SVG CONVERSION CHECK ==="
        )
        print(
            "is_svg:",
            is_svg,
        )
        print(
            "profiles:",
            [
                getattr(p, "name", repr(p))
                for p in self.profiles
            ],
        )

        if is_svg:
            conversion = QGroupBox(
                "SVG → G-code"
            )

            conversion_layout = QVBoxLayout(
                conversion
            )

            profile_row = QHBoxLayout()

            profile_row.addWidget(
                QLabel("Profile")
            )

            self.profile_combo = QComboBox()

            current_profile = getattr(
                self.job,
                "conversion_profile",
                None,
            )

            selected_index = -1

            for index, profile in enumerate(
                self.profiles
            ):
                self.profile_combo.addItem(
                    profile.name,
                    profile,
                )

                if profile.name == current_profile:
                    selected_index = index

            print(
                "MachinePanel conversion profiles:",
                [profile.name for profile in self.profiles],
            )

            print(
                "=== RUNTIME PROFILE COMBO ==="
            )
            print(
                "combo count:",
                self.profile_combo.count(),
            )
            print(
                "combo items:",
                [
                    self.profile_combo.itemText(i)
                    for i in range(
                        self.profile_combo.count()
                    )
                ],
            )


            if selected_index >= 0:
                self.profile_combo.setCurrentIndex(
                    selected_index
                )

            self.profile_combo.currentIndexChanged.connect(
                self.profile_changed
            )

            profile_row.addWidget(
                self.profile_combo
            )

            conversion_layout.addLayout(
                profile_row
            )

            params = QWidget()
            params_layout = QVBoxLayout(
                params
            )

            self.parameter_widgets = {}

            def rebuild_parameters():
                while params_layout.count():
                    item = params_layout.takeAt(0)

                    widget = item.widget()

                    if widget:
                        widget.deleteLater()

                profile = (
                    self.profile_combo.currentData()
                    if self.profile_combo.count()
                    else None
                )

                parameters = getattr(
                    profile,
                    "parameters",
                    [],
                )

                # Conversion profiles discovered from .sh --json
                # expose parameters as ProfileParameter objects.
                # Normalize them here so the UI does not care whether
                # the profile manager uses objects or dictionaries.
                normalized_parameters = []

                if isinstance(parameters, dict):
                    for name, specification in parameters.items():
                        if isinstance(specification, dict):
                            normalized_parameters.append(
                                (
                                    str(name),
                                    specification,
                                )
                            )
                        else:
                            normalized_parameters.append(
                                (
                                    str(name),
                                    {
                                        "type": "string",
                                        "default": specification,
                                    },
                                )
                            )

                elif isinstance(parameters, list):
                    for parameter in parameters:
                        name = getattr(
                            parameter,
                            "name",
                            None,
                        )

                        if not name:
                            continue

                        normalized_parameters.append(
                            (
                                str(name),
                                {
                                    "type": getattr(
                                        parameter,
                                        "type",
                                        "string",
                                    ),
                                    "default": getattr(
                                        parameter,
                                        "default",
                                        None,
                                    ),
                                    "description": getattr(
                                        parameter,
                                        "description",
                                        "",
                                    ),
                                    "minimum": getattr(
                                        parameter,
                                        "minimum",
                                        None,
                                    ),
                                    "maximum": getattr(
                                        parameter,
                                        "maximum",
                                        None,
                                    ),
                                    "options": getattr(
                                        parameter,
                                        "options",
                                        [],
                                    ),
                                },
                            )
                        )

                self.parameter_widgets.clear()

                for name, specification in normalized_parameters:
                    row = QHBoxLayout()

                    row.addWidget(
                        QLabel(str(name))
                    )

                    value = specification.get(
                        "default"
                    )

                    parameter_type = str(
                        specification.get(
                            "type",
                            "string",
                        )
                    ).lower()

                    if parameter_type == "boolean":
                        value = bool(value)

                    elif parameter_type == "number":
                        try:
                            value = float(
                                1.0 if value is None else value
                            )
                        except (TypeError, ValueError):
                            value = 1.0

                    elif parameter_type == "integer":
                        try:
                            value = int(
                                0 if value is None else value
                            )
                        except (TypeError, ValueError):
                            value = 0

                    elif value is None:
                        value = ""

                    if parameter_type == "boolean":
                        widget = QCheckBox()
                        widget.setChecked(value)

                    elif parameter_type == "integer":
                        widget = QSpinBox()

                        if isinstance(
                            specification,
                            dict,
                        ):
                            if specification.get("minimum") is not None:
                                widget.setMinimum(
                                    int(
                                        specification[
                                            "minimum"
                                        ]
                                    )
                                )

                            if specification.get("maximum") is not None:
                                widget.setMaximum(
                                    int(
                                        specification[
                                            "maximum"
                                        ]
                                    )
                                )

                        widget.setValue(value)

                    elif parameter_type == "number":
                        widget = QDoubleSpinBox()

                        if isinstance(
                            specification,
                            dict,
                        ):
                            if specification.get("minimum") is not None:
                                widget.setMinimum(
                                    float(
                                        specification[
                                            "minimum"
                                        ]
                                    )
                                )

                            if specification.get("maximum") is not None:
                                widget.setMaximum(
                                    float(
                                        specification[
                                            "maximum"
                                        ]
                                    )
                                )

                        widget.setValue(value)

                    else:
                        choices = specification.get(
                            "options",
                            specification.get(
                                "choices",
                                [],
                            ),
                        )

                        if choices:
                            widget = QComboBox()
                            widget.addItems(
                                [
                                    str(choice)
                                    for choice in choices
                                ]
                            )

                            if value is not None:
                                current = widget.findText(
                                    str(value)
                                )

                                if current >= 0:
                                    widget.setCurrentIndex(
                                        current
                                    )
                        else:
                            widget = QLineEdit(
                                "" if value is None
                                else str(value)
                            )

                    self.parameter_widgets[
                        str(name)
                    ] = widget

                    row.addWidget(
                        widget
                    )

                    params_layout.addLayout(
                        row
                    )

            self.profile_combo.currentIndexChanged.connect(
                lambda _index: rebuild_parameters()
            )

            conversion_layout.addWidget(
                params
            )

            rebuild_parameters()

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
            self.preview.show_travel
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

    def profile_changed(self, index):
        if not self.job:
            return

        profile = self.profile_combo.itemData(
            index
        )

        if profile is None:
            self.job.conversion_profile = None
            self.job.conversion_parameters = {}
        else:
            self.job.conversion_profile = (
                profile.name
            )

            parameters = getattr(
                profile,
                "parameters",
                [],
            )

            values = {}

            for name, widget in getattr(
                self,
                "parameter_widgets",
                {},
            ).items():
                try:
                    if isinstance(
                        widget,
                        QCheckBox,
                    ):
                        values[name] = (
                            widget.isChecked()
                        )

                    elif isinstance(
                        widget,
                        QComboBox,
                    ):
                        values[name] = (
                            widget.currentText()
                        )

                    elif isinstance(
                        widget,
                        QSpinBox,
                    ):
                        values[name] = (
                            widget.value()
                        )

                    elif isinstance(
                        widget,
                        QDoubleSpinBox,
                    ):
                        values[name] = (
                            widget.value()
                        )

                    elif isinstance(
                        widget,
                        QLineEdit,
                    ):
                        values[name] = (
                            widget.text()
                        )

                except RuntimeError:
                    pass

            self.job.conversion_parameters = values

        self.changed.emit()

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
        self.preview.preview_limit = value
        self.workspace.update()

    def preview_drawing_changed(self, value):
        self.preview.show_drawing = value
        self.workspace.update()

    def preview_travel_changed(self, value):
        self.preview.show_travel = value
        self.workspace.update()

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

        try:
            if hasattr(
                self.jobs,
                "convert_svg",
            ):
                new_job = self.jobs.convert_svg(
                    self.job,
                    profile,
                    parameters,
                )

            else:
                raise RuntimeError(
                    "JobManager does not provide convert_svg()"
                )

            self.converted.emit(
                new_job.id
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Conversion failed",
                str(exc),
            )

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
                QMessageBox.critical(
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
            QMessageBox.critical(
                self,
                "Save failed",
                str(exc),
            )



class MainWindow(QMainWindow):

    def __init__(
        self,
        config,
    ):

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

        # ----------------------------------------------------
        # Panels
        # ----------------------------------------------------

        self.machine_panel = (
            MachinePanel(
                self.machine,
                profiles=self.profiles,
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

            QMessageBox.warning(
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
