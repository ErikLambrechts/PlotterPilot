from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import (
    QPointF,
    Qt,
    QThread,
    Signal,
    QRectF,
)
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
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
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .models import JobSourceType
from .preview import gcode_segments
from .profiles import ProfileManager


def fmt_time(seconds):
    seconds = max(0, int(seconds))

    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    if hours:
        return f"{hours}h {minutes:02d}m"

    if minutes:
        return f"{minutes}m {seconds:02d}s"

    return f"{seconds}s"


class Worker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function):
        super().__init__()
        self.function = function

    def run(self):
        try:
            self.succeeded.emit(
                self.function()
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class Collapsible(QFrame):
    def __init__(self, title, widget, expanded=False):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.button = QPushButton()
        self.button.setCheckable(True)
        self.button.setChecked(expanded)

        self.widget = widget

        self.button.clicked.connect(
            self.update
        )

        layout.addWidget(self.button)
        layout.addWidget(widget)

        self.update()

    def update(self):
        expanded = self.button.isChecked()

        self.widget.setVisible(expanded)

        title = self.button.text()
        title = title.lstrip("▶▼ ")

        self.button.setText(
            ("▼ " if expanded else "▶ ")
            + title
        )


class WorkspaceView(QWidget):
    selected = Signal(str)
    moved = Signal(str)

    def __init__(self, workspace, jobs):
        super().__init__()

        self.workspace = workspace
        self.jobs = jobs

        self.zoom = 1.0
        self.pan_x = 80.0
        self.pan_y = 80.0

        self.machine_x = 0
        self.machine_y = 0

        self.selected_id = None

        self.panning = False
        self.pan_start = QPointF()
        self.pan_origin = (0, 0)

        self.dragging = False
        self.drag_id = None

        self.setMinimumSize(500, 500)
        self.setFocusPolicy(Qt.StrongFocus)

    def world_to_screen(self, x, y):
        # Machine coordinates have Y pointing upwards.
        return (
            self.pan_x + x * self.zoom,
            self.pan_y
            + (self.workspace.height - y)
            * self.zoom,
        )

    def screen_to_world(self, p):
        x = (
            p.x() - self.pan_x
        ) / self.zoom

        y = self.workspace.height - (
            p.y() - self.pan_y
        ) / self.zoom

        return x, y

    def set_selected(self, job_id):
        self.selected_id = job_id
        self.update()

    def set_machine_position(self, x, y):
        self.machine_x = x
        self.machine_y = y
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.panning = True
            self.pan_start = event.position()
            self.pan_origin = (
                self.pan_x,
                self.pan_y,
            )
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton:
            x, y = self.screen_to_world(
                event.position()
            )

            for job in reversed(self.jobs.jobs):
                if not job.active or not job.visible:
                    continue

                if self.hit(job, x, y):
                    self.selected_id = job.id
                    self.dragging = True
                    self.drag_id = job.id
                    self.drag_offset = (
                        x - job.transform.offset_x,
                        y - job.transform.offset_y,
                    )
                    self.selected.emit(job.id)
                    self.update()
                    return

    def mouseMoveEvent(self, event):
        if self.panning:
            delta = (
                event.position()
                - self.pan_start
            )

            self.pan_x = (
                self.pan_origin[0]
                + delta.x()
            )

            self.pan_y = (
                self.pan_origin[1]
                + delta.y()
            )

            self.update()
            return

        if self.dragging:
            job = self.jobs.get(self.drag_id)

            if job:
                x, y = self.screen_to_world(
                    event.position()
                )

                job.transform.offset_x = (
                    x - self.drag_offset[0]
                )

                job.transform.offset_y = (
                    y - self.drag_offset[1]
                )

                self.moved.emit(job.id)
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)

        elif event.button() == Qt.LeftButton:
            self.dragging = False
            self.drag_id = None

    def wheelEvent(self, event):
        old_zoom = self.zoom

        factor = (
            1.15
            if event.angleDelta().y() > 0
            else 1 / 1.15
        )

        self.zoom = max(
            0.05,
            min(20.0, self.zoom * factor),
        )

        mouse = event.position()

        wx, wy = self.screen_to_world(mouse)

        self.pan_x = (
            mouse.x()
            - wx * self.zoom
        )

        self.pan_y = (
            mouse.y()
            - (
                self.workspace.height - wy
            ) * self.zoom
        )

        self.update()

    def hit(self, job, x, y):
        width = 120 * job.transform.scale
        height = 80 * job.transform.scale

        ox = job.transform.offset_x
        oy = job.transform.offset_y

        return (
            ox <= x <= ox + width
            and
            oy - height <= y <= oy
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.Antialiasing
        )

        painter.fillRect(
            self.rect(),
            QColor("#e7e9ec"),
        )

        rect = QRectF(
            self.pan_x,
            self.pan_y,
            self.workspace.width * self.zoom,
            self.workspace.height * self.zoom,
        )

        painter.setPen(
            QPen(QColor("#65707c"), 2)
        )
        painter.setBrush(
            QColor("#f8f9fa")
        )
        painter.drawRect(rect)

        for anchor in self.workspace.anchors:
            x, y = self.world_to_screen(
                anchor.x,
                anchor.y,
            )

            painter.setPen(
                QPen(QColor("#6b7280"), 1)
            )

            painter.drawLine(
                x - 7, y, x + 7, y
            )
            painter.drawLine(
                x, y - 7, x, y + 7
            )

            painter.drawText(
                x + 9,
                y - 8,
                anchor.name,
            )

        for job in self.jobs.jobs:
            if not job.active or not job.visible:
                continue

            x, y = self.world_to_screen(
                job.transform.offset_x,
                job.transform.offset_y,
            )

            if job.source_type == JobSourceType.GCODE:
                self.paint_gcode(
                    painter,
                    job,
                )
                continue

            width = 120 * job.transform.scale
            height = 80 * job.transform.scale

            color = (
                QColor("#d7e8f8")
                if job.id == self.selected_id
                else QColor("#dce7df")
            )

            painter.setPen(
                QPen(QColor("#4b5563"), 2)
            )
            painter.setBrush(color)

            painter.drawRect(
                QRectF(
                    x,
                    y - height * self.zoom,
                    width * self.zoom,
                    height * self.zoom,
                )
            )

            painter.setPen(
                QColor("#263238")
            )

            painter.drawText(
                x + 6,
                y - height * self.zoom / 2,
                job.name,
            )

        mx, my = self.world_to_screen(
            self.machine_x,
            self.machine_y,
        )

        painter.setPen(
            QPen(QColor("#c62828"), 2)
        )

        painter.drawEllipse(
            QPointF(mx, my),
            7,
            7,
        )

        painter.drawLine(
            mx - 12, my,
            mx + 12, my,
        )

        painter.drawLine(
            mx, my - 12,
            mx, my + 12,
        )

    def paint_gcode(self, painter, job):
        if not job.gcode:
            return

        segments = gcode_segments(
            job.gcode,
            job.preview_limit,
        )

        ox = job.transform.offset_x
        oy = job.transform.offset_y

        for segment in segments:
            x1 = ox + segment.x1
            y1 = oy + segment.y1
            x2 = ox + segment.x2
            y2 = oy + segment.y2

            sx1, sy1 = self.world_to_screen(
                x1, y1
            )
            sx2, sy2 = self.world_to_screen(
                x2, y2
            )

            if segment.drawing:
                pen = QPen(
                    QColor("#2563a8"),
                    max(1, self.zoom * 1.2),
                )
            else:
                pen = QPen(
                    QColor("#9ca3af"),
                    1,
                    Qt.DashLine,
                )

            painter.setPen(pen)
            painter.drawLine(
                sx1,
                sy1,
                sx2,
                sy2,
            )


class MachinePanel(QFrame):
    def __init__(self, machine):
        super().__init__()

        self.machine = machine
        self.worker = None

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel("<b>Machine</b>")
        )

        group = QGroupBox("Connection")
        group_layout = QVBoxLayout(group)

        row = QHBoxLayout()
        row.addWidget(QLabel("Host"))

        self.host = QLineEdit(machine.host)
        row.addWidget(self.host)

        group_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Port"))

        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(machine.port)

        row.addWidget(self.port)
        group_layout.addLayout(row)

        layout.addWidget(group)

        self.button = QPushButton("Connect")
        self.button.clicked.connect(self.toggle)
        layout.addWidget(self.button)

        self.status = QLabel("Disconnected")
        layout.addWidget(self.status)

        self.position = QLabel(
            "X: --\nY: --\nZ: --"
        )
        layout.addWidget(self.position)

        layout.addWidget(
            QLabel("<b>Jog</b>")
        )

        self.step = QDoubleSpinBox()
        self.step.setRange(0.01, 10000)
        self.step.setValue(10)
        self.step.setDecimals(2)

        row = QHBoxLayout()
        row.addWidget(QLabel("Step"))
        row.addWidget(self.step)
        layout.addLayout(row)

        def jog(x, y, z):
            if not self.machine.state.connected:
                return

            try:
                self.machine.jog(x, y, z)
            except Exception as exc:
                self.status.setText(
                    f"Error: {exc}"
                )

        row = QHBoxLayout()
        button = QPushButton("↑")
        button.clicked.connect(
            lambda: jog(
                0,
                self.step.value(),
                0,
            )
        )
        row.addStretch()
        row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)

        row = QHBoxLayout()

        button = QPushButton("←")
        button.clicked.connect(
            lambda: jog(
                -self.step.value(),
                0,
                0,
            )
        )
        row.addWidget(button)

        row.addStretch()

        button = QPushButton("→")
        button.clicked.connect(
            lambda: jog(
                self.step.value(),
                0,
                0,
            )
        )
        row.addWidget(button)

        layout.addLayout(row)

        row = QHBoxLayout()
        button = QPushButton("↓")
        button.clicked.connect(
            lambda: jog(
                0,
                -self.step.value(),
                0,
            )
        )

        row.addStretch()
        row.addWidget(button)
        row.addStretch()

        layout.addLayout(row)

        row = QHBoxLayout()

        zp = QPushButton("Z+")
        zp.clicked.connect(
            lambda: jog(
                0,
                0,
                self.step.value(),
            )
        )

        zm = QPushButton("Z-")
        zm.clicked.connect(
            lambda: jog(
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
                lambda checked=False, a=axis:
                self.home(a)
            )

            layout.addWidget(button)

        home = QPushButton("Home All")
        home.clicked.connect(
            lambda: self.home(None)
        )

        layout.addWidget(home)

        zero = QPushButton("Set Zero")
        zero.clicked.connect(self.zero)
        layout.addWidget(zero)

        layout.addStretch()

    def toggle(self):
        if self.machine.state.connected:
            self.machine.disconnect()
            self.button.setText("Connect")
            self.status.setText("Disconnected")
            return

        self.machine.host = (
            self.host.text().strip()
        )

        self.machine.port = self.port.value()

        if not self.machine.host:
            self.status.setText(
                "Enter a host"
            )
            return

        self.button.setEnabled(False)
        self.status.setText(
            "Connecting..."
        )

        self.worker = Worker(
            self.machine.connect
        )

        self.worker.succeeded.connect(
            self.connected
        )

        self.worker.failed.connect(
            self.failed
        )

        self.worker.finished.connect(
            lambda:
            self.button.setEnabled(True)
        )

        self.worker.start()

    def connected(self, _):
        self.button.setText("Disconnect")
        self.status.setText("Connected")

    def failed(self, message):
        self.machine.disconnect()
        self.button.setText("Connect")
        self.status.setText(
            f"Connection failed: {message}"
        )

    def home(self, axis):
        try:
            self.machine.home(axis)
        except Exception as exc:
            self.status.setText(
                f"Error: {exc}"
            )

    def zero(self):
        try:
            self.machine.zero()
        except Exception as exc:
            self.status.setText(
                f"Error: {exc}"
            )

    def update_state(self):
        state = self.machine.state

        self.position.setText(
            f"X: {state.x:.3f}\n"
            f"Y: {state.y:.3f}\n"
            f"Z: {state.z:.3f}\n"
            f"F: {state.feed:.0f}"
        )


class JobList(QFrame):
    selected = Signal(str)
    changed = Signal()

    def __init__(self, jobs):
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

        layout.addWidget(self.list)

        remove = QPushButton("Remove")
        remove.clicked.connect(
            self.remove
        )

        layout.addWidget(remove)

    def refresh(self, selected=None):
        self.list.blockSignals(True)
        self.list.clear()

        for job in self.jobs.jobs:
            item = QListWidgetItem()

            text = job.name

            if (
                job.source_type
                == JobSourceType.GCODE
                and job.stats
            ):
                text += (
                    f"  ·  "
                    f"{fmt_time(job.stats.estimated_seconds)}"
                )

            item.setText(text)
            item.setData(
                Qt.UserRole,
                job.id,
            )

            item.setCheckState(
                Qt.Checked
                if job.active
                else Qt.Unchecked
            )

            self.list.addItem(item)

            if job.id == selected:
                self.list.setCurrentItem(item)

        self.list.blockSignals(False)

    def selection_changed(self, current, previous):
        if current:
            self.selected.emit(
                current.data(Qt.UserRole)
            )
        else:
            self.selected.emit("")

    def add_file(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Job",
            "",
            "Plotter Files (*.svg *.gcode *.nc *.ngc)",
        )

        for filename in files:
            try:
                self.jobs.add_file(
                    Path(filename)
                )
            except Exception as exc:
                print(exc)

        self.changed.emit()

    def remove(self):
        item = self.list.currentItem()

        if not item:
            return

        self.jobs.remove(
            item.data(Qt.UserRole)
        )

        self.changed.emit()


class JobProperties(QFrame):
    changed = Signal()
    converted = Signal(str)

    def __init__(
        self,
        jobs,
        workspace,
        profiles,
    ):
        super().__init__()

        self.jobs = jobs
        self.workspace = workspace
        self.profiles = profiles

        self.job = None

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel("<b>Job Properties</b>")
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        self.content_layout = QVBoxLayout(
            content
        )

        scroll.setWidget(content)
        layout.addWidget(scroll)

        self.build_empty()

    def clear(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

    def build_empty(self):
        self.clear()

        self.content_layout.addWidget(
            QLabel(
                "Select a job."
            )
        )

        self.content_layout.addStretch()

    def set_job(self, job_id):
        self.job = self.jobs.get(job_id)

        if not self.job:
            self.build_empty()
            return

        self.build()

    def build(self):
        job = self.job

        self.clear()

        file_group = QGroupBox("File")
        file_layout = QVBoxLayout(file_group)

        file_layout.addWidget(
            QLabel(job.name)
        )

        if job.source_type == JobSourceType.GCODE:
            save = QPushButton("Save G-code")
            save.clicked.connect(
                self.save_gcode
            )
            file_layout.addWidget(save)

        self.content_layout.addWidget(
            file_group
        )

        if job.source_type == JobSourceType.SVG:
            self.build_conversion()
        else:
            self.build_gcode_settings()

        self.build_placement()
        self.build_transform()

        if job.source_type == JobSourceType.GCODE:
            self.build_statistics()

        self.content_layout.addStretch()

    def build_conversion(self):
        job = self.job

        group = QGroupBox("Conversion")
        layout = QVBoxLayout(group)

        self.profile = QComboBox()

        for profile in self.profiles.profiles:
            self.profile.addItem(
                profile.name,
                profile,
            )

        layout.addWidget(
            QLabel("Profile")
        )
        layout.addWidget(self.profile)

        parameter_widget = QWidget()
        parameter_layout = QVBoxLayout(
            parameter_widget
        )

        self.parameter_widgets = {}

        def rebuild(index):
            while parameter_layout.count():
                item = parameter_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            self.parameter_widgets.clear()

            profile = self.profile.currentData()

            if not profile:
                return

            for parameter in profile.parameters:
                row = QHBoxLayout()

                row.addWidget(
                    QLabel(
                        parameter.description
                        or parameter.name
                    )
                )

                if parameter.type == "boolean":
                    widget = QCheckBox()
                    widget.setChecked(
                        bool(parameter.default)
                    )

                elif parameter.type == "integer":
                    widget = QSpinBox()
                    widget.setRange(
                        int(parameter.minimum or -1000000),
                        int(parameter.maximum or 1000000),
                    )
                    widget.setValue(
                        int(parameter.default or 0)
                    )

                elif parameter.type == "number":
                    widget = QDoubleSpinBox()
                    widget.setRange(
                        float(
                            parameter.minimum
                            if parameter.minimum is not None
                            else -1000000
                        ),
                        float(
                            parameter.maximum
                            if parameter.maximum is not None
                            else 1000000
                        ),
                    )
                    widget.setDecimals(4)
                    widget.setValue(
                        float(parameter.default or 0)
                    )

                elif parameter.type == "choice":
                    widget = QComboBox()

                    for choice in parameter.choices:
                        widget.addItem(choice)

                    if parameter.default in parameter.choices:
                        widget.setCurrentText(
                            parameter.default
                        )

                else:
                    widget = QLineEdit(
                        "" if parameter.default is None
                        else str(parameter.default)
                    )

                self.parameter_widgets[
                    parameter.name
                ] = widget

                row.addWidget(widget)
                parameter_layout.addLayout(row)

        self.profile.currentIndexChanged.connect(
            rebuild
        )

        rebuild(0)

        collapsed = Collapsible(
            "Parameters",
            parameter_widget,
            expanded=False,
        )

        layout.addWidget(collapsed)

        convert = QPushButton(
            "Convert to G-code"
        )

        convert.clicked.connect(
            self.convert
        )

        layout.addWidget(convert)

        self.content_layout.addWidget(group)

    def build_gcode_settings(self):
        job = self.job

        group = QGroupBox("Preview")
        layout = QVBoxLayout(group)

        self.preview_limit = QSpinBox()
        self.preview_limit.setRange(
            1000,
            10000000,
        )
        self.preview_limit.setValue(
            job.preview_limit
        )

        self.preview_limit.valueChanged.connect(
            self.preview_changed
        )

        row = QHBoxLayout()
        row.addWidget(
            QLabel("Max instructions")
        )
        row.addWidget(
            self.preview_limit
        )

        layout.addLayout(row)

        self.preview_mode = QComboBox()

        self.preview_mode.addItems([
            "Auto",
            "Full",
            "Simplified",
        ])

        self.preview_mode.setCurrentText(
            job.preview_mode.title()
        )

        self.preview_mode.currentTextChanged.connect(
            self.preview_changed
        )

        row = QHBoxLayout()
        row.addWidget(
            QLabel("Mode")
        )
        row.addWidget(
            self.preview_mode
        )

        layout.addLayout(row)

        self.content_layout.addWidget(group)

    def build_placement(self):
        job = self.job

        group = QGroupBox("Placement")
        layout = QVBoxLayout(group)

        self.origin = QComboBox()

        self.origin.addItem(
            "Machine Origin",
            "machine",
        )

        for anchor in self.workspace.anchors:
            self.origin.addItem(
                anchor.name,
                anchor.name,
            )

        index = self.origin.findData(
            job.origin
        )

        if index >= 0:
            self.origin.setCurrentIndex(index)

        self.origin.currentIndexChanged.connect(
            self.placement_changed
        )

        layout.addWidget(
            QLabel("Origin")
        )
        layout.addWidget(self.origin)

        self.repeat = QCheckBox(
            "Repeat on anchors"
        )

        self.repeat.setChecked(
            job.repeat_anchors
        )

        self.repeat.toggled.connect(
            self.placement_changed
        )

        layout.addWidget(self.repeat)

        self.anchor_checks = []

        for anchor in self.workspace.anchors:
            check = QCheckBox(anchor.name)

            check.setChecked(
                anchor.name
                in job.repeated_anchors
            )

            check.setVisible(
                job.repeat_anchors
            )

            check.toggled.connect(
                self.placement_changed
            )

            self.anchor_checks.append(
                (anchor.name, check)
            )

            layout.addWidget(check)

        self.content_layout.addWidget(group)

    def build_transform(self):
        job = self.job

        group = QGroupBox("Transform")
        layout = QVBoxLayout(group)

        self.x = self.number(
            "X offset",
            job.transform.offset_x,
        )

        self.y = self.number(
            "Y offset",
            job.transform.offset_y,
        )

        self.z = self.number(
            "Z offset",
            job.transform.offset_z,
        )

        self.scale = self.number(
            "Scale",
            job.transform.scale,
            minimum=0.001,
            maximum=1000,
            decimals=4,
        )

        self.rotation = self.number(
            "Rotation",
            job.transform.rotation,
            minimum=-360,
            maximum=360,
        )

        for widget, spin in (
            self.x,
            self.y,
            self.z,
            self.scale,
            self.rotation,
        ):
            spin.valueChanged.connect(
                self.transform_changed
            )
            layout.addWidget(widget)

        self.flip_x = QCheckBox("Flip X")
        self.flip_y = QCheckBox("Flip Y")

        self.flip_x.setChecked(
            job.transform.flip_x
        )

        self.flip_y.setChecked(
            job.transform.flip_y
        )

        self.flip_x.toggled.connect(
            self.transform_changed
        )

        self.flip_y.toggled.connect(
            self.transform_changed
        )

        layout.addWidget(self.flip_x)
        layout.addWidget(self.flip_y)

        self.content_layout.addWidget(group)

    def build_statistics(self):
        stats = self.job.stats

        if not stats:
            return

        group = QGroupBox("Statistics")
        layout = QVBoxLayout(group)

        layout.addWidget(
            QLabel(
                f"Total time: "
                f"{fmt_time(stats.estimated_seconds)}"
            )
        )

        layout.addWidget(
            QLabel(
                f"Drawing distance: "
                f"{stats.drawing_distance:.1f} mm"
            )
        )

        layout.addWidget(
            QLabel(
                f"Travel distance: "
                f"{stats.travel_distance:.1f} mm"
            )
        )

        layout.addWidget(
            QLabel(
                f"Drawing moves: "
                f"{stats.drawing_moves}"
            )
        )

        layout.addWidget(
            QLabel(
                f"Travel moves: "
                f"{stats.travel_moves}"
            )
        )

        self.content_layout.addWidget(group)

    def number(
        self,
        label,
        value,
        minimum=-1000000,
        maximum=1000000,
        decimals=2,
    ):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel(label))

        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)

        layout.addWidget(spin)

        return row, spin

    def placement_changed(self):
        if not self.job:
            return

        self.job.origin = (
            self.origin.currentData()
        )

        self.job.repeat_anchors = (
            self.repeat.isChecked()
        )

        self.job.repeated_anchors = [
            name
            for name, check
            in self.anchor_checks
            if check.isChecked()
        ]

        for _, check in self.anchor_checks:
            check.setVisible(
                self.job.repeat_anchors
            )

        self.changed.emit()

    def transform_changed(self):
        if not self.job:
            return

        self.job.transform.offset_x = (
            self.x[1].value()
        )

        self.job.transform.offset_y = (
            self.y[1].value()
        )

        self.job.transform.offset_z = (
            self.z[1].value()
        )

        self.job.transform.scale = (
            self.scale[1].value()
        )

        self.job.transform.rotation = (
            self.rotation[1].value()
        )

        self.job.transform.flip_x = (
            self.flip_x.isChecked()
        )

        self.job.transform.flip_y = (
            self.flip_y.isChecked()
        )

        self.changed.emit()

    def preview_changed(self):
        if not self.job:
            return

        self.job.preview_limit = (
            self.preview_limit.value()
        )

        self.job.preview_mode = (
            self.preview_mode.currentText().lower()
        )

        self.changed.emit()

    def convert(self):
        if not self.job:
            return

        profile = self.profile.currentData()

        if not profile:
            return

        parameters = {}

        for name, widget in (
            self.parameter_widgets.items()
        ):
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()

            elif isinstance(widget, QComboBox):
                value = widget.currentText()

            elif isinstance(
                widget,
                (
                    QSpinBox,
                    QDoubleSpinBox,
                ),
            ):
                value = widget.value()

            else:
                value = widget.text()

            parameters[name] = value

        output = Path(
            tempfile.mktemp(
                prefix="plotpilot-",
                suffix=".gcode",
            )
        )

        command = [
            str(profile.path),
            "--input",
            str(self.job.source),
            "--output",
            str(output),
        ]

        for name, value in parameters.items():
            if isinstance(value, bool):
                if value:
                    command.append(
                        f"--{name}"
                    )
            else:
                command.extend([
                    f"--{name}",
                    str(value),
                ])

        try:
            subprocess.run(
                command,
                check=True,
                timeout=300,
            )

            self.converted.emit(
                str(output)
            )

        except Exception as exc:
            self.status_message(
                f"Conversion failed: {exc}"
            )

    def status_message(self, text):
        print(text)

    def save_gcode(self):
        if not self.job or not self.job.gcode:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save G-code",
            self.job.name,
            "G-code (*.gcode *.nc *.ngc)",
        )

        if not filename:
            return

        Path(filename).write_text(
            self.job.gcode,
            encoding="utf-8",
        )


class MainWindow(QMainWindow):
    def __init__(
        self,
        config,
    ):
        super().__init__()

        self.setWindowTitle("PlotPilot")
        self.resize(1500, 850)

        self.machine = __import__(
            "plotpilot.machine",
            fromlist=["FluidNC"],
        ).FluidNC(
            config.host,
            config.port,
        )

        from .jobs import JobManager

        self.jobs = JobManager()

        self.profiles = ProfileManager(
            config.profiles
        )

        self.profiles.discover()

        self.machine_panel = MachinePanel(
            self.machine
        )

        self.job_list = JobList(
            self.jobs
        )

        self.workspace = WorkspaceView(
            config.workspace,
            self.jobs,
        )

        self.properties = JobProperties(
            self.jobs,
            config.workspace,
            self.profiles,
        )

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(
            self.machine_panel
        )
        left_layout.addWidget(
            self.job_list
        )

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.workspace)
        splitter.addWidget(self.properties)

        splitter.setSizes([
            300,
            900,
            360,
        ])

        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)

        self.job_list.selected.connect(
            self.select_job
        )

        self.job_list.changed.connect(
            self.refresh
        )

        self.workspace.selected.connect(
            self.select_job
        )

        self.workspace.moved.connect(
            lambda _: self.refresh_workspace()
        )

        self.properties.changed.connect(
            self.refresh_workspace
        )

        self.properties.converted.connect(
            self.conversion_finished
        )

        from PySide6.QtCore import QTimer

        self.timer = QTimer(self)
        self.timer.timeout.connect(
            self.update_machine
        )
        self.timer.start(250)

        self.job_list.refresh()

    def refresh_workspace(self):
        self.workspace.update()

    def refresh(self):
        selected = (
            self.properties.job.id
            if self.properties.job
            else None
        )

        self.job_list.refresh(selected)
        self.workspace.update()

    def select_job(self, job_id):
        self.workspace.set_selected(
            job_id or None
        )

        self.properties.set_job(
            job_id
        )

        self.job_list.refresh(
            job_id or None
        )

    def conversion_finished(self, output):
        source = self.properties.job

        if not source:
            return

        output_path = Path(output)

        job = self.jobs.create_gcode_job(
            source,
            output_path,
            self.properties.profile.currentData().name,
            {
                name: (
                    widget.isChecked()
                    if isinstance(
                        widget,
                        QCheckBox,
                    )
                    else (
                        widget.currentText()
                        if isinstance(
                            widget,
                            QComboBox,
                        )
                        else (
                            widget.value()
                            if isinstance(
                                widget,
                                (
                                    QSpinBox,
                                    QDoubleSpinBox,
                                ),
                            )
                            else widget.text()
                        )
                    )
                )
                for name, widget
                in self.properties.parameter_widgets.items()
            },
        )

        self.select_job(job.id)
        self.refresh()

    def update_machine(self):
        if self.machine.state.connected:
            try:
                self.machine.poll()
            except Exception as exc:
                self.machine.disconnect()
                self.machine_panel.status.setText(
                    f"Connection lost: {exc}"
                )
                self.machine_panel.button.setText(
                    "Connect"
                )

        state = self.machine.state

        self.machine_panel.update_state()

        self.workspace.set_machine_position(
            state.x,
            state.y,
        )

    def keyPressEvent(self, event):
        focused = QApplication.focusWidget()

        if isinstance(
            focused,
            (
                QLineEdit,
                QSpinBox,
                QDoubleSpinBox,
            ),
        ):
            super().keyPressEvent(event)
            return

        step = self.machine_panel.step.value()

        if event.key() == Qt.Key_Left:
            self.machine.jog(-step, 0, 0)

        elif event.key() == Qt.Key_Right:
            self.machine.jog(step, 0, 0)

        elif event.key() == Qt.Key_Up:
            self.machine.jog(0, step, 0)

        elif event.key() == Qt.Key_Down:
            self.machine.jog(0, -step, 0)

        else:
            super().keyPressEvent(event)


def run(config):
    from PySide6.QtWidgets import QApplication

    app = QApplication([])

    app.setStyle("Fusion")

    window = MainWindow(config)
    window.show()

    return app.exec()
