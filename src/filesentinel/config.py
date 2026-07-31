"""
Implementation of configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field


class ConfigModel(BaseModel):
    """
    User-editable configuration loaded from `config.yaml`.
    """

    recovery_pct: int = 10
    """
    Redundancy target size in percent.

    Maps to par2 `-r` option.
    """

    ignore_globs: list[str] = Field(default_factory=list)
    """
    Additional glob patterns (relative to archive root) to ignore during scan.
    """

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        """
        Load config from a YAML file.

        Returns defaults if the file is missing.
        """
        if not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
