from pathlib import Path

import yaml

from filekeeper import ConfigModel


def test_defaults_when_missing(tmp_path: Path):
    cfg = ConfigModel.from_yaml(tmp_path / "nope.yaml")
    assert cfg.recovery_pct == 10


def test_loads_overrides(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({"recovery_pct": 25, "ignore_globs": ["*.tmp"]}))
    cfg = ConfigModel.from_yaml(p)
    assert cfg.recovery_pct == 25
    assert cfg.ignore_globs == ["*.tmp"]
