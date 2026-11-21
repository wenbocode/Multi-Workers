"""Require an explicit workspace choice before dispatch, without changing queries."""

from __future__ import annotations

import pathlib
from collections.abc import Mapping

import mw_common


def load_dispatch_target_config(
    control_root: pathlib.Path | str,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Resolve target config and refuse the implicit single/default fallback.

    A missing file cannot establish whether the project is intentionally single
    or lost a dual/partition config. Complete environment activation remains an
    explicit choice; ordinary queries keep using ``load_target_config``.
    """
    config = mw_common.load_target_config(control_root, env=env)
    if config["source"] == "default":
        path = mw_common.target_yml_path(config["control_root"])
        raise mw_common.TargetConfigError(
            "invalid-config",
            f"target-config-required: control root={config['control_root']}; "
            f"config={path}; mode={config['mode']} source={config['source']}. "
            "Dispatch requires an explicit workspace mode: set active: single only "
            "for a single workspace, or configure active: dual with dual.game, or "
            "active: partition with partition.parent and partition.partition; "
            "complete MW_TARGET_GAME or MW_PARTITION_PARENT/MW_PARTITION_ROOT "
            "environment activation is also accepted.",
        )
    return config
