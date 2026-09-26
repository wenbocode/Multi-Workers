# T-03 mw_common 新增面（render_argv + doctor 段 + dist 锚点 helper）

- AC: AC-008, AC-013, AC-014, AC-009 · VC: VC-008, VC-014, VC-009(helper 部分) · 波次: 1
- 写面：`packages/multi-workers/mw_common.py` + **新建** `test_common_render_argv.py`、`test_doctor_autopilot.py`

## 契约（plan.md §2.1/§2.2）

```python
def render_argv(cmd: list[str], config: dict) -> list[str]
def workspace_root(config: dict) -> str     # partition->partition_root, dual->game_root, single/legacy->control_root
def _doctor_autopilot(project_dir) -> dict
def repo_bundle_anchor() -> dict            # {"stale": bool|None, "detail": str}
def sourcemap_drift() -> dict
```

- `render_argv` 语义：元素 `fullmatch(_TOKEN_RE)` ⇒ 整元素替换；**含占位但非整元素（`{partition}/tests`、`a{b}`）⇒ fail-closed**（错误文本含原元素，形状照 `mw_common.py:2908-2914`）；未定义/未配置占位 ⇒ fail-closed（kind `missing-field`，不新增 kind）；字面量原样。
- token 集合：该 mode 根 token **+ `{control}`**（仅 verify argv；**不进 toolchain token 集**）。
- **只抽**"partition 已定义 token 名列表构造器"（从 `:2909` 的内联 `defined` 提出，错误文本逐字不变）；**`render_toolchain_command` 一行不改**。
- doctor 段：`_doctor_autopilot` 在 `doctor_report` 注册 → `_doctor_issues` 产出 **issue**（`xkey_repair=true` 且有效 argv 为空 ⇒ 翻 healthy）→ `format_doctor_text` 加行（含修复命令 `mw autopilot verify set`）；两条报告路径（doctor/bootstrap）都要看得到。
- 锚点 helper：kind 集合锚定 `GATE_KINDS = [` 赋值处；guard 用**限定串** `xkey-gate-guard: blocked` / `[XKEY_GATE]`（裸串会命中路径注释与 `MW_XKEY_GATE_ROOT`）。

## 验证

- `python -m pytest -q test_common_target_config.py test_common_render_argv.py test_doctor_autopilot.py` 全绿（**parity 集必须绿**，证明 toolchain 未变）。
- 负例：嵌入占位、未定义占位、"仅注释路径"的假产物 fixture（证明限定串有效）。
- `[VERIFY]` 行：render_argv 真值、doctor issue 触发/不触发、锚点在陈旧 fixture 上为 stale。
