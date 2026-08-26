import math
import re
from pathlib import Path

from PySide6.QtCore import (
    QPointF,
    QRectF,
    Qt,
    Signal,
)

from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPen,
)

from PySide6.QtWidgets import QWidget


"""
PlotPilot module extracted from plotpilot.py.

This module is intentionally conservative.
The first refactor keeps the existing implementation intact.
"""

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
