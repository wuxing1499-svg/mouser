"""Mouser configuration data model.

Source: plan/mouser 阶段 4 step 24
Design: spec/mouser "Core entities" — Config entity.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

ScreenPosition = Literal["left", "right", "top", "bottom"]
"""Linear screen position relative to the server. v1 does not support grid layouts."""

Mode = Literal["server", "client"]
"""Daemon mode. `deskflow-core --server` or `--client`."""


@dataclass
class ScreenConfig:
    """One remote screen in the layout."""

    host: str
    position: ScreenPosition

    def __post_init__(self) -> None:
        valid: tuple[str, ...] = ("left", "right", "top", "bottom")
        if self.position not in valid:
            raise ValueError(f"position must be one of {valid}, got {self.position!r}")


@dataclass
class MouserConfig:
    """Top-level mouser configuration.

    Serialized as JSON. Path resolution across platforms is handled by
    `load_default_path()` using `platformdirs`; this module only handles
    read/write of a given path.
    """

    mode: Mode = "server"
    port: int = 24800
    local_host: str = ""
    screens: list[ScreenConfig] = field(default_factory=list)

    def save(self, path: Path) -> None:
        """Write config to `path` as JSON (UTF-8, pretty-printed)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "MouserConfig":
        """Read config from `path`. Missing file returns defaults."""
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        screens = [ScreenConfig(**s) for s in raw.get("screens", [])]
        return cls(
            mode=raw["mode"],
            port=raw["port"],
            local_host=raw["local_host"],
            screens=screens,
        )
