- type: coding
- key: mw-decision-substitution
- 目标锚点: `.agenticdoc/goal.md`（jev 替换中低风险决策，PM 并行管理 worker）；本卡是"配置即契约"的落地：dp 的要求在 `decide_registry.json`，代码只负责按配置把字段内容填出来
- 上游: `spec.md` §14 AC-018、AC-019、AC-021、AC-022、`design.md` §8 D-055..D-060、`packages/multi-workers/decide_registry.json`（schema 2，24 dp）

## 上下文

决策本是 `decide` 接口的输入；dp 的要求在 `decide_registry.json`（每 dp 的 `required_state_fields` + `questions_version` + `contextSlots`）。现入口 `mw decide ask`/`decide run`（`mw.py:947` 附近 + `_AskDecisionClient`）只吃 `--state-file`/`--state`，没有骨架生成、没有封闭键集合校验。`decision.py:817 _validate_input` 的校验在进程内、失败码 `input-incomplete`/`input-oversize`；`mw decide sign`（`mw.py:2855/2872`）是「先验后写」的现成范式，本卡照它做「先验后发」。W4 已导出对象化字段，W6 会引入 `decision_context.py` 与 `shared/decide-registry.generated.ts`。

## 要求

1) 新建 `packages/multi-workers/decision_book.py`：
   - `scaffold_book(dp_id) -> dict`：按注册表生成骨架——`state` 的键与顺序 == `required_state_fields`，值为类型占位符（string→`<string: <description>>`、integer→`-1`、number→`-1.0`、boolean→`false`、array→`[]`、object→`{}`），`questions_version` 预填注册表值，`notes.evidence` 为每个必填字段生成同名 `<待填: path:line 或命令原文>` 条目，`context` 只含该 dp 的 `contextSlots`；
   - `load_book(path)`：JSON 可解析、顶层键 ⊆ `{schema_version, decision_point, state, context, notes}`、`schema_version==2`；
   - `check_book(book) -> list[Issue]`：七个失败码 `book-schema`/`book-state`/`book-placeholder`/`book-context`/`book-evidence`/`book-budget`/`book-secret`；`book-state` 必须是**封闭集合**判定（缺必填、类型不符、**多出注册表没有的键**三种都要报），规则复用 `REQUIRED_STATE_FIELDS`+type 表+`_estimate_tokens`+`_redact`；`book-evidence` 校验 `notes.evidence` 里每个 `path:line` 可解析（文件存在、行号 ≤ 行数、路径在仓库内）。
2) CLI：`mw decide book new <dp-id> [--out FILE] [--json]`（默认打印到 stdout，不写文件除非给 `--out`）、`mw decide book check <file> [--json] [--project DIR]`（失败 exit 2，全过 exit 0，只报告不修）。
3) `mw decide ask`/`decide run` 新增 `--book <file>`：先 `check_book`，失败 → 打印失败表 + exit 2（零 HTTP）；成功 → 用 book 的 `state`/`context` 发请求，档案写 `book_path` + `file_sha256` + `notes.evidence`。
4) `decide_book_template.json` 改为 `book new` 的**真实输出示例**（dp3 + dp6 各一份，占位符原样保留，不放真实数据）。
5) README：新增一节「写决策本」——先 `book new <dp>`，按 `description` 填值，`notes.evidence` 每条给 `path:line`，`book check` 过了再 `--book` 发送；写明封闭键集合与「只写输入不写预期答案」。
6) 测试 `test_decision_book.py` ≥26 例：骨架键集合==注册表（24 dp 全跑）、占位符未替换报 `book-placeholder`、多余键报 `book-state`、缺必填、类型不符、未知 context 槽、证据行号越界、超 32k/64k、疑似 key、合法全过、`--json` 结构、`--book` 失败零 HTTP、`--book` 成功落 book_path+sha256；`test_decide_cli.py` 加 `--book`/`book new` 参数解析 3 例。

## 写入允许面

- packages/multi-workers/decision_book.py
- packages/multi-workers/decide_book_template.json
- packages/multi-workers/test_decision_book.py
- packages/multi-workers/mw.py
- packages/multi-workers/test_decide_cli.py
- packages/multi-workers/README.md

## 写入禁止面

- `.mw/decide-points.json`、`.mw/decide.json`（运行时配置，严禁改；测试只写 tmp 目录）
- `.agenticdoc/**`（除 `workers/<task_key>/`）、`docs/**`、`packages/ai/**`、`packages/multi-workers/decision.py`
- git 写、`npm run check`、`npm run build`、`mw build --install`、全量 pytest、真实网络（`--live`/`decide run`/`decide ask`）

## 运行约束（OOM 教训，必须遵守）

- 禁止整文件读 `mw.py`（1 万行）/`worker-mode.ts`（5 千行）/`decision_points.py`（2 千行）：每次 read 只用 `offset`/`limit`，单次 ≤ 120 行且只围绕卡片锚点。
- 单个命令 stdout ≤ 30 行；长输出先落盘到 `workers/<task_key>/` 再读尾部。
- write-first：先落实现再跑验收；`rg` 必须带目录限定（`-g`）。
- 动手前先在 `report.md` 写一段 ≤10 行的计划，避免长时间无内部输出。

## 验收命令

cd packages/multi-workers
python -m pytest -q test_decision_book.py test_decide_cli.py test_decide_dp_cli.py test_decision_points.py
python mw.py decide book new dp3-worker-clarify --project H:/git/Multi-Workers
python mw.py decide book check decide_book_template.json --project H:/git/Multi-Workers

## 交付格式

`report.md` 五节：结论（每条验收命令的 stdout 原文 ≤30 行）/ 证据（文件:行）/ 残留与未验证 / 上下文来源（goal.md mtime + 读过的 `path:line`）/ 改动清单。禁止只写"已验证"。

## 改动历史

- 2026-10-21 创建（PM）；同日按用户澄清修订为"由 `decide_registry.json` 驱动"

