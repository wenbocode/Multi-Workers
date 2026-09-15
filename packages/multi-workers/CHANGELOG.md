# Changelog

## [Unreleased]

### Added

- Added dual-workspace support: `.agenticdoc/target.yml` (`mode: dual` with `game`/`engine` roots; `mw target set --game <p> [--engine <p>] [--vcs <t>] [--uproject <p>]`, `mw target clear`, `mw target show`; env `MW_TARGET_GAME`/`MW_TARGET_ENGINE` overrides, priority env > target.yml > single) separates the control workspace (framework coordination files) from the target project — workers spawn with cwd at the game root while every coordination path stays anchored to the control workspace. Includes the Python config layer (`mw_common.load_target_config`, `discover_uproject`, `render_toolchain_command`) with fail-closed validation and a TS/Py shared parity fixture suite (`test/fixtures/target-config-cases/`).
- Added `deny_globs` injection to conductor dispatch (`autopilot/dispatch.py`): task.md frontmatter defaults from target.yml's `ignore.deny_globs` (any mode), an explicit per-task list wins; dual mode expands relative `read_scope` entries against the game root and appends the control root (authorization to read the profile), while single mode passes scope through unchanged. An unusable target.yml rejects the dispatch fail-closed (`target-config-unusable`, new `target-config-rejected` timeline event) instead of queueing an un-injected task.
- Added dual-mode spawn to `launcher.py`: worker cwd is the game root in dual mode (resolved per spawn, so `mw target set`/`clear` take effect on the next spawn without a serve restart) and the control workspace otherwise; broken target.yml refuses the spawn with a per-task worker.log record. List args, no shell, and absolute `PI_WORKER_TASK` are unchanged.
- Added `mw doctor` target-workspace checks: PyYAML availability, target.yml validity, dual-root existence, `{uproject}` discovery, and toolchain probing persisted to `.mw/toolchain.json` (machine-local cache, probed-at freshness against the yml mtime).
