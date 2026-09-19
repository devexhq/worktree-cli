# tests/harness/catalog.py
"""Shared test harness for writing a real, indexed catalog blueprint to disk."""

from __future__ import annotations

from pathlib import Path

import yaml

from worktree.core.catalog.services.inventory import ensure_catalog_dirs, scan_and_index_catalog


def write_runnable_blueprint(
    workspace: Path,
    *,
    key: str,
    steps: list[dict[str, object]],
    timeout_seconds: int = 60,
) -> None:
    """Write a minimal blueprint YAML under .worktree/catalog/blueprints/ and index it into the catalog DB."""
    catalog_dir = ensure_catalog_dirs(workspace)
    blueprint_path = catalog_dir / "blueprints" / f"{key}.yml"
    payload = {
        "version": "1.0",
        "name": key,
        "id": key,
        "description": f"Test blueprint '{key}'.",
        "timeout_seconds": timeout_seconds,
        "steps": steps,
    }
    blueprint_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    scan_and_index_catalog(path=workspace)
