# -*- coding: utf-8 -*-
"""策略 YAML 读取器。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
STRATEGY_DIR = BASE_DIR / "strategies"
STRATEGY_DIR.mkdir(parents=True, exist_ok=True)


def _require_yaml():
    try:
        import yaml  # type: ignore
        return yaml
    except Exception as exc:
        raise RuntimeError(
            "缺少 PyYAML 依赖。请执行：pip install pyyaml -i https://pypi.tuna.tsinghua.edu.cn/simple"
        ) from exc


def list_strategy_files() -> list[Path]:
    return sorted(STRATEGY_DIR.glob("*.yaml"))


def load_strategy(path_or_id: str | Path) -> dict[str, Any]:
    yaml = _require_yaml()
    p = Path(path_or_id)
    if not p.exists():
        p = STRATEGY_DIR / f"{path_or_id}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"策略文件不存在：{p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    data["_file"] = str(p)
    return data


def list_strategies() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in list_strategy_files():
        try:
            s = load_strategy(p)
            sid = str(s.get("strategy_id") or p.stem)
            name = str(s.get("strategy_name") or sid)
            out[sid] = name
        except Exception:
            out[p.stem] = p.stem
    return out
