# T-01 — CLI 收敛：`mw decide sign` 只剩决策模型一条路

- type: coding
- owner key: mw-signoff-decide-only
- 派生自：`design.md` §3、`spec.md` AC-003/AC-004/AC-005/AC-006/AC-008

## 上下文

项目目标见 `.agenticdoc/goal.md`。签收凭据只表达"决策模型替代了人的判断"，因此 CLI 不允许调用方给出结论，也不允许"人签"路径存在。

必读证据（已落盘，不要重做研究）：

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-signoff-faces-20261022.md` —— `signed_via` 的全部读写点（15 文件 / 134 行）、删值后哪些测试会红、哪些常量不能删。
- `.agenticdoc/mw-signoff-decide-only/design.md` §3 —— 参数面与 `_decide_sign` 目标形态。

关键锚点：

- `packages/multi-workers/mw.py:3996` 起 `_decide_sign`；`:4049` `auto_flow`；`:4066` jev 覆盖；`:4072/:4077` `signed_via` 分支。
- `packages/multi-workers/mw.py:3835-3885` `_decide_sign_signed_via` / `_decide_sign_write` / `human_confirmed` 分支。
- `packages/multi-workers/mw.py:11730-11770` argparse（`--conclusion` `:11752`、`--auto` `:11756`、`--human-confirmed` `:11766`）。
- `packages/multi-workers/decide_signoff.py:100-103` 词表；`:671-692` `write_signoff`；`:523/:568` `render`。
- `packages/multi-workers/decision_history.py:713` 读面词表（**不改**）。

## 要求

1. 删除 `auto-llm` / `cli` / `tui` 三张脸：`_decide_sign` 只保留 `auto_conclusion()` 一条路径。jev 返回 `None` 时 **exit 0、不写文件**、输出一行 `decision model unavailable (<reason>); sign-off not required`。
2. 删除 `--conclusion` 与 `--human-confirmed` 两个参数；`--auto` / `--disable` 保留：`--disable` 持久化后照旧 exit 0；`--auto` 持久化 `signoff=auto` 后**必须继续签收**（现在 `if code != 0 or conclusion is None: return code` 会提前返回，导致窗口 `sign --key k --auto` 只写配置不签收）。不带模式标志的裸 `sign --key k` 保持自动流程（按配置的 `signoff`）。
3. `--dry-run` 必须在 `auto_conclusion()` **之前**分支：零模型调用、零档案写入、零文件写入，返回 `{"ok", "verdicts": {"continue"|"narrow"|"revoke": {ok, problems}}, "facts", "path": null}`（现在 dry-run 在模型调用之后，jev 可用时既花调用又追加 dp25 行，JSON 里还没有 `verdicts`）。`--allow-empty` 只影响 `continue` 那一项。
4. `write_signoff(project_dir, key, text)`：删除 `allow_agent_session`、`signed_via` 参数与 agent-session 拒绝分支。**`AGENT_SESSION_ENV_VARS` 常量必须保留**（`mw.py:1854` 模块级初始化 `_DP_AGENT_ENV_VARS`，删了整个 CLI 导入失败）。
5. 写面词表收窄为 `SIGNED_VIA_VALUES = ("auto-decide",)`，删除 `AUTO_SIGNED_VIA`；`render()` 仍写 `signed_via: auto-decide` 一行。**读面不动**：`decision_history.py` 保持接受四个值。
6. 删除 `mw.py::_decide_sign_signed_via`（唯一调用点 `test_decide_signoff.py:681`，测试由 T-04 处理）。
7. 同步更新 `mw.py` 内 `decide sign` 的 `help` 文案与 `--json` 输出字段（不再有 `signed_via` 分支说明）。

## 写入允许面

- `packages/multi-workers/mw.py`
- `packages/multi-workers/decide_signoff.py`

## 写入禁止面

- `packages/multi-workers/decision_history.py`（读面词表必须保留四个值）
- `packages/multi-workers/test_*.py`（由 T-04 负责）
- `.agents/skills/agentic-task/**`（由 T-02 负责）
- `packages/coding-agent/**`（由 T-03 负责）
- `dist/**`、`docs/**`、`*.md`（本次不改文档）

## 验收命令

```bash
python -c "import sys; sys.path.insert(0,'packages/multi-workers'); import mw, decide_signoff; print(decide_signoff.SIGNED_VIA_VALUES)"
python packages/multi-workers/mw.py decide sign --help
```

`--help` 输出中不得出现 `--conclusion` / `--human-confirmed`；`SIGNED_VIA_VALUES` 必须是 `('auto-decide',)`。
另外实跑一次只读的 dry-run（本仓库任意 key）：

```bash
python packages/multi-workers/mw.py decide sign --key mw-signoff-decide-only --dry-run --json
```

必须 exit 0、输出含 `verdicts`、且 `_autopilot/decisions.jsonl` 行数与 `evidence/review/sign-final.md` mtime 都不变。
不要求跑测试（T-04 会按新语义重写测试）；但不得引入语法/导入错误。

## 改动历史

| date | change |
| --- | --- |
| 2026-10-22 | 卡片创建 |
