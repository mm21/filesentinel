"""
Implementation of configuration.
"""

from typing import Self

from pydantic import BaseModel


class ConfigModel(BaseModel):

    recovery_pct: int = 10
    """
    Redundancy target size in percent.

    Maps to par2 -r option.
    """

    @classmethod
    def from_yaml(cls, Path) -> Self: ...
