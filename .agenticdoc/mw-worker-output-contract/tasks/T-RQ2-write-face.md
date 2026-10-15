# T-RQ2: 写面分层与 worker_file 放宽的全部改动点（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（含 Key Constraints 的「工具白名单按任务类型：coding（read/write/edit/bash）、review（read/find/grep/ls）、research（read/find/grep/ls/bash）」）。
- 本 key 的 spec：`.agenticdoc/mw-worker-output-contract/spec.md` —— 相关条目 §1.4（不收「给角色加 write」）、§1.5 P2、§1.6 S4、§3 AC-006/AC-007、§2.3 安全约束。
- 已知起点坐标（**只是起点**）：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts:42`（`WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/`）、同文件 `:63`（`file name not allowed`）、`:82`（`appendWriteFileEvent(path.join(taskDir, "trace.log"), …)`）、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:723`（默认写面 = `taskDir + <key>/evidence/**`，由 `write_scope:` 收窄）、同文件 `:1604-1660`（`checkBashWriteScopeTarget` 与 `allowedLabel`）。
- 背景事实（已复核）：research/review 角色**没有** `write` 工具（`[TOOL_ERR] … write Tool write not found` 在另一 key 的 3 个 worker trace 里各 1 次）；`worker_file` 只认 3 个 basename 且强制任务目录 ⇒ 卡片声明的唯一产物路径（`<key>/evidence/research/*.md`）对它们**不可达**，只能靠壳层写（4 例成功、1 例退回任务目录由 PM 提升，两处 41,612 B / sha `8E4B5A418D99512B`）。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、全量 `./test.sh`。

## 要求

1. **角色工具集的决定处**：`type`（coding/review/research/vision/…）到实际可用工具列表的映射在何处定义、如何在运行时注册（含 `.mw/dispatch.yml` 只声明了什么、role 默认表在哪、`worker_file` 对哪些 type 注册）。逐条 `文件:行号`。
2. **`worker_file` 的完整实现与调用点**：工具注册、参数校验、写盘路径拼接、trace 事件、错误文案；以及任务目录与该工具的关系（`taskDir` 从哪来）。
3. **壳层写面全貌**：`checkBashWriteScopeTarget` 的判定顺序（deny 列表 → 默认面 → `write_scope:` 收窄）、`allow-unknown` 的语义与条件、`[WRITE_SCOPE]` trace 行格式、`write_scope:` 任务头的解析处。
4. **改动点清单（本 RQ 的核心交付）**：为达成「`worker_file` 接受 `<key>/evidence/**` 下的相对路径、同时保持任务目录内 basename 白名单与越界 fail-closed」，列出**全部**需要改的位置：函数与行号、需要新增/修改的校验、trace 事件（是否需要区分写入域）、以及会受影响的其他调用点。**只列位置与语义，不写实现代码。**
5. **反向对照与越界用例**：现有测试中涉及 `worker_file` / basename 白名单 / 写面的用例清单（文件 + 用例名 + 断言要点）；并给出「越界必须失败」的候选用例清单（`../..`、其他 key 路径、仓库源码路径、绝对路径、`evidence` 之外的同级目录）。
6. **错误文案链**：`Tool write not found` 这类「工具不在本角色工具面」的文案生成处（逐条 `文件:行号`），以及 `worker_file` 描述文本中列出 basename 白名单的位置（AC-007 要改的就是这两处）。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq2-write-face-20261014.md`

用 `bash` + Python heredoc 直接写该路径；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为 PM 回读兜底。

## 交付格式

- `## 0. 结论先行`（≤6 条）→ `## 1…N` 逐问作答（第 4 问必须是**可直接转成 tasks 的改动点清单**）→ `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；检索/计数给实测命令 + 输出；未找到写「未找到（命令 + 输出）」，禁止推测补齐。
- 末尾一行 `[VERIFY] <数值> …`；声明工具与方法边界。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
