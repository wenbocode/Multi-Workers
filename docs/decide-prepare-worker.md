# decide_prepare worker（决策本填写角色）

## 定位

`type: decide_prepare` 是唯一「只写决策本、不改代码」的 worker 类型（mw-decision-substitution W8
引入，W10 由 `decision` 改名，**不留别名**：`type: decision` 现在是未知类型、`models.decision` 是未知 role）。

适用：某个 dp（决策点）的结论可以由「读配置 + 收证据 + 按注册表逐字段填本」机械得出时，把这件事整体
交给它；PM 不自己推理字段内容，只发本与裁决。

## 工具面

- 白名单：`read` / `find` / `grep` / `ls` / `bash`（无 `write` / `edit`）。
- 写入只能走窄通道 `worker_file`（见下）。
- `bash` 被收窄到只读子集：`mw decide book check`、`mw decide book new`（`--out` 必须落在
  `evidence/books/**`，无 `--out` 只打印）、`git diff|status|log`、`rg`、`cat`、`ls`、`head`、`tail`、`wc`；
  重定向、`rm`/`sed -i`/`git commit` 一类改写、串联写入一律拒绝。
- 固定提示词（`DECISION_TYPE_PROMPT`）注入每一轮 system prompt：先 `book new` 建骨架，按字段
  description 从证据填值（`notes.evidence` 每条给 `path:line` 或命令原文），最后 `book check` 直到通过；
  不改阈值、不填预期答案、不改 `packages/` 代码。

## 写面

- 类型默认收窄为 `<key>/workers/<task_key>/evidence/books/**`；卡片声明更宽的 `## 写入允许面` 时以卡片为准，
  并在 task.md 记一行 `narrowed_by:`（放宽可见，不静默）。
- 运行时 `worker_file` 只接受 `evidence/books/<file>` 或 `.agenticdoc/<key>/evidence/books/<file>`；
  `report.md`、`<key>/evidence/**` 的其它位置、`..` 越界全部拒绝。

## 四项判据（缺一即拒，零副作用）

卡片派发段必须齐全：

| 条目 | 含义 |
| --- | --- |
| `- dp: <dp-id>` | 要填的决策点；必须在 `decide_registry.json` 里定义 `required_state_fields`（否则「先给该 dp 定义必填字段」） |
| `- 证据来源: ...` | 证据入口（文件:行 / 命令），worker 只从这里取证 |
| `- 分支后果: ...` | 每条分支做错的后果，防止 worker 自行发明判据 |
| `- allow-send: yes|no` | 发送权限，缺省 `no` |

判据码稳定不变：`missing-item:<item>` / `dp-required-state-fields-missing:<dp>` /
`book-send-refused`（外加 `card-missing` / `dp-unknown:<dp>` / `invalid-item:allow-send`）。
离线自检：`python -m autopilot.dispatch check --card <card> [--book <book>] [--json]`
（exit 0 通过 / 2 拒绝 / 1 用法错误）。

## `allow-send` 语义

- `no`（缺省）：worker 只能跑 `mw decide book check`；`decide run|ask --book` 一律拒绝，发送由 PM 做。
- `yes`：worker 可执行 `decide run|ask --book` 自己发送（服务侧 gate 仍然照常生效）。
- 只认显式 `yes`；`yes` 以外的任何值（含缺失、拼错）都是关闭态。

## 模型

`.mw/dispatch.yml` 的 `models.decide_prepare`（或 `mw model set decide_prepare <prefix/model>`）单独指定；
未配置时回退 `models.coding`；`dispatch_worker` 的 `model` 覆盖仍优先（task.md 记 `model-reason`）。
本仓库配置：`decide_prepare: timi/gpt-6.1-sol`。

## 真实例子

```markdown
## 派发参数

- dp: dp3-worker-clarify
- 证据来源: .mw/decide.json:3 + `mw decide book new dp3-worker-clarify`
- 分支后果: 误判会把需要澄清的任务直接执行
- allow-send: no
```

派发后：`<key>/workers/<task_key>/evidence/books/dp3-worker-clarify-book.json` 过
`mw decide book check`（exit 0），task.md 的「决策本参数」段写全 dp / 证据来源 / 分支后果 /
allow-send / book 路径 / `narrowed_by`；trace.log 只应出现 `book new` 与 `book check`，不出现 `decide run/ask`。

## 与 decision book 的关系

决策本是 `mw decide book new|check` 那套 schema v2 文件（字段来自 dp 的 `required_state_fields`）。
`decide_prepare` 只负责把本填对、过检、交回；**要不要发、发出去之后怎么用**仍是 PM/决策服务的职责。
dp 的注册表、发送 gate 与档案逻辑属于既有 `decision.py` / `decide_signoff.py` / `decision_points.py`，
本角色不改它们。
