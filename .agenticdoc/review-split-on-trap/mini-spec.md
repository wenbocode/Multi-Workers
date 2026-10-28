# mini-spec: `mw review-split set on` 静默无效（trivial-fix fast path）

- 日期：2026-10-22
- 类型：一行级修复 + 测试/文档同步（无新功能）
- 来源：`claim-driven-review-orchestration` 结案后 PM 自查发现

## 问题

`MW_REVIEW_SPLIT` 的三档是 `off|plan|on`，但 `on` 档从未接线（M3 随 M1 判决撤销）：
`pm/review-split-gate.ts` 第一行 `mode !== "plan" → return null`。
于是 `mw review-split set on` **接受**这个值并写入 `.mw/review-split.json`，
用户以为开了拆分，实际行为与 `off` 一模一样 —— 静默无效。

## 修法（最小面）

1. `packages/multi-workers/autopilot/review_split.py`
   - 新增 `REVIEW_SPLIT_WIRED_MODES = ("off", "plan")` 与 `is_review_split_wired(mode) -> bool`。
   - `set_review_split` 对未接线值抛 `ValueError`，消息含 `not wired` 与原因。
     解析侧（`resolve_review_split`）**不变**：卡里已经写了 `on` 的仍读得出来，由 `status` 报警。
2. `packages/multi-workers/mw.py`
   - `_review_split_set` 把 `ValueError` 的消息原样打印（原来固定打 "invalid mode"，会掩盖原因）。
   - `status`（文本与 `--json`）增加 `wired: true|false`；`false` 时文本追加 ` wired=no`。
3. 测试 `packages/multi-workers/test_review_split_cli.py`
   - `set on` → exit 2、stderr 含 `not wired`、且**不创建** `.mw/review-split.json`。
   - `status --json` → 含 `wired` 字段；config 写成 `on` 时 `wired=false`（文本同时含 `wired=no`）。
   - `set plan/off` 仍然成功且 `wired=true`。
4. `packages/multi-workers/CHANGELOG.md` → `## [Unreleased] / ### Changed` 一条。

## 不做

- 不改 TS 侧 `resolveReviewSplit`（`on` 仍是合法值，语义层保留给未来接线）。
- 不改 `fixtures/review-split-cases.json`（那是解析平价表，`wired` 属 CLI 展示层）。
- 不实现 `on` 档。

## 验收

```
cd packages/multi-workers
python -X utf8 -m pytest test_review_split_cli.py test_review_split_parity.py -q
```
期望：全绿（原 58 + 新增用例）。

## 实施结果（2026-10-22）

- `autopilot/review_split.py`：新增 `REVIEW_SPLIT_WIRED_MODES = ("off","plan")` 与
  `is_review_split_wired()`；`set_review_split("on")` 抛 `ValueError`（消息含 `not wired` + 原因），
  校验仍在任何文件操作之前（`.mw/` 不会出现）。
- `mw.py`：`_review_split_set` 原样打印模块的 `ValueError` 消息；`_review_split_resolve` 增加 `wired`；
  `status` 文本在未接线时追加 ` wired=no`。
- 测试：新增 `test_set_on_is_refused_as_unwired`、`test_status_flags_a_preexisting_on_config`；
  `--json` 断言补 `wired`；`set` 参数化从 `REVIEW_SPLIT_MODES` 改为 `REVIEW_SPLIT_WIRED_MODES`。
- `packages/multi-workers/CHANGELOG.md`：`[Unreleased] / ### Changed` 一条。
- 未改：TS 解析器、`fixtures/review-split-cases.json`（解析平价表）、`on` 档实现。

### 验证（实跑）

```
pytest test_review_split_cli.py test_review_split_parity.py -q  → 59 passed
vitest review-split-mode.test.ts                                → 29 passed
py_compile review_split.py mw.py                                → 0

mw review-split set on   → exit 2
  mw review-split: mode 'on' is not wired (only off|plan have an implementation;
  the `on` tier was cancelled with the M1 verdict of `claim-driven-review-orchestration`)
（临时项目里 .mw/ 未创建）

config 里已有 {"v":1,"mode":"on"} 时：
  review-split: mode=on source=config config=… wired=no
  {"mode":"on",…,"wired":false}
```
