# T-W-D2 — 运行期写面闸扩到全角色的插入点（RQ-D2）

- type: research
- key: mw-write-face-guard
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-write-face-guard/evidence/research/design-runtime-guard-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（多 Worker 共享同一工作树而不互相破坏）。
- 总问题：**运行期"越界写"今天只对 `research`+bash 生效；扩到全可写角色要插在哪、判什么、怎么不误拦？**
- 已坐实事实（可引用，但必须自己复看确认）：
  - 现状：写面运行期消费只有一处 —— `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:719`（"A role with `bash` but no `write`/`edit` (today: `research` only) can bypass" 注释段起）的 bash 写面守卫；其安装条件是 `worker-mode.ts:2203`（`isShellRole(meta.type) && isWritelessRole(meta.type)`）。
  - 载体解析端：`worker/worker-mode.ts:440`（`write_scope:` 头解析）、`:322`（`writeScope?: string[]` 字段）、`:434-465`（一列/块两种形式的解析）。
  - `worker_file` 的 basename 白名单在 `worker/worker-file-tool.ts`；`read_scope` 只挂读（`worker/read-scope.ts:167 checkReadScopeCall`），不拦写。
  - `implementation-gate` 被 `PI_WORKER_TASK` 放行（spec 证据 `spec-write-face-sources-20261014.md`）。
  - bash 写目标词法已有两处实现可参考：`packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts` 的 target 侧 lexer（重定向/tee/cp/mv/rm/sed -i 操作数），以及 worker 侧 bash 写面守卫（`worker-mode.ts:719` 起）。
  - 控制面误拦的一手实例（必须在设计里避免）：`evidence/research/spec-write-face-safety-20261014.md` §7.8（`xkey-gate-guard` 因"命令文本引用 `_autopilot` + 含写动词"误拦文档内容），以及 `spec-write-face-sources-20261014.md` 的 E3（`pattern=redirect target=--glob`，repro `Write-Output a <term> --glob x`）。
- 允许并鼓励自行扩大取证范围（全仓只读，含 `dist/`、其它 key、`.mw/`）。

## 要求

1. **现有 research 分支的完整形状**：`file:line` + 原文，覆盖：闸装在哪（工具工厂/hook）、读什么输入（命令字符串？工具名？）、怎么写拒绝（throw？返回？`[TOOL_ERR]` 行？）、trace 落什么行、白名单/默认面是什么。逐条。
2. **插入点候选（≥3）**：把闸从"研究+bash"扩到"全角色 + write/edit/bash/worker_file"的候选位置，每个给：覆盖到的工具面、漏掉的路径（例：`python -c` 内联写、预写脚本、`find -delete`）、是否需要 worker 读自身 task.md（是否已有缓存）、首个失败模式。
3. **bash 写目标词法归属**：判定应该复用 `shared/implementation-gate.ts` 的 lexer、还是新增写面专用词法？给出两者的差异（该 lexer 的目标是"仓库代码路径"，写面闸的目标是"该 worker 的声明面"），并明确**必须避免的假阻形态**（同 上下文里两条实例），给出至少 5 条反例向量（引号内路径、heredoc 内容、`--glob` 之类的旗标操作数、变量拼接、管道到文件）。
4. **deny 优先与默认面**：给出运行期默认面（taskDir + `<key>/evidence` + `progress.md`/`report.md`）与 deny 面的判定顺序，并说明 `research` 角色的既有行为是否被**逐字保持**（向后兼容与否由 spec 决定，但必须给出"今天的行为"与"新行为"的差异表）。
5. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件: `.agenticdoc/mw-write-face-guard/evidence/research/design-runtime-guard-20261014.md`（结论先行 + 现状逐条 + 候选表 + 词法归属 + 反例向量 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印（例：现有守卫覆盖的角色/工具矩阵计数）。
