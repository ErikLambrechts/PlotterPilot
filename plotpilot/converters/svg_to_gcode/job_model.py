"""
Plotbot editable job model.

This is the canonical representation of a prepared job.

The important architectural rule is:

    Job JSON is the source of truth.

Generated SVG, vpype output and G-code are derived artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import copy
import json
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Transform:
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(
            x=float(data.get("x", 0)),
            y=float(data.get("y", 0)),
            scale_x=float(data.get("scale_x", data.get("scale", 1))),
            scale_y=float(data.get("scale_y", data.get("scale", 1))),
            rotation=float(data.get("rotation", 0)),
        )


@dataclass
class Artwork:
    id: str
    type: str

    # SVG source
    source: str | None = None

    # Text properties
    text: str | None = None
    font: str | None = None
    font_size: float = 20.0
    bold: bool = False

    # Rendering
    fill: str = "none"
    stroke: str = "black"
    stroke_width: float = 1.0

    transform: Transform = field(default_factory=Transform)

    # Arbitrary future properties.
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        result = asdict(self)
        result["transform"] = self.transform.to_dict()
        return result

    @classmethod
    def from_dict(cls, data):
        obj = cls(
            id=data.get("id") or new_id(),
            type=data.get("type", "svg"),
            source=data.get("source"),
            text=data.get("text"),
            font=data.get("font"),
            font_size=float(data.get("font_size", 20)),
            bold=bool(data.get("bold", False)),
            fill=data.get("fill", "none"),
            stroke=data.get("stroke", "black"),
            stroke_width=float(data.get("stroke_width", 1)),
            properties=copy.deepcopy(data.get("properties", {})),
        )

        obj.transform = Transform.from_dict(
            data.get("transform", {})
        )

        return obj


@dataclass
class ProcessingStep:
    operation: str
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(
            operation=data["operation"],
            enabled=bool(data.get("enabled", True)),
            parameters=copy.deepcopy(
                data.get("parameters", {})
            ),
        )


@dataclass
class Page:
    preset: str = "A4"
    orientation: str = "portrait"
    width: float = 210.0
    height: float = 297.0
    margin: float = 10.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(
            preset=data.get("preset", "A4"),
            orientation=data.get("orientation", "portrait"),
            width=float(data.get("width", 210)),
            height=float(data.get("height", 297)),
            margin=float(data.get("margin", 10)),
        )


@dataclass
class Job:
    id: str = field(default_factory=new_id)
    name: str = "Untitled job"

    version: int = 1

    page: Page = field(default_factory=Page)

    artworks: list[Artwork] = field(default_factory=list)

    processing: list[ProcessingStep] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "version": self.version,
            "id": self.id,
            "name": self.name,
            "page": self.page.to_dict(),
            "artworks": [
                artwork.to_dict()
                for artwork in self.artworks
            ],
            "processing": [
                step.to_dict()
                for step in self.processing
            ],
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("id") or new_id(),
            name=data.get("name", "Untitled job"),
            version=int(data.get("version", 1)),
            page=Page.from_dict(data.get("page", {})),
            artworks=[
                Artwork.from_dict(item)
                for item in data.get("artworks", [])
            ],
            processing=[
                ProcessingStep.from_dict(item)
                for item in data.get("processing", [])
            ],
            metadata=copy.deepcopy(
                data.get("metadata", {})
            ),
        )

    def add_artwork(self, artwork: Artwork):
        self.artworks.append(artwork)

    def remove_artwork(self, artwork_id: str):
        self.artworks = [
            item
            for item in self.artworks
            if item.id != artwork_id
        ]

    def find_artwork(self, artwork_id: str):
        for artwork in self.artworks:
            if artwork.id == artwork_id:
                return artwork
        return None

    def clone(self):
        return Job.from_dict(self.to_dict())

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                self.to_dict(),
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path):
        data = json.loads(
            Path(path).read_text(
                encoding="utf-8"
            )
        )
        return cls.from_dict(data)


def create_default_job():
    return Job()


if __name__ == "__main__":
    job = create_default_job()
    print(json.dumps(
        job.to_dict(),
        indent=2,
    ))
