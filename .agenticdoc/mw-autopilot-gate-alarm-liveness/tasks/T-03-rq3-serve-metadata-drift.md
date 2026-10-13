# T-03 — RQ-3｜serve/conductor 启动元数据与代码漂移检测的最小改动面

type: research
phase: spec
key: mw-autopilot-gate-alarm-liveness
唯一证据文件: .agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/spec-rq3-serve-metadata-drift-20261013.md

## 上下文（种子，不是上界）

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守 ⇒ "我跑的是不是当前代码"必须可自证，而不是靠人记得重启）。
- 已核实事实：
  - conductor 是 serve 的**第三子进程**，`mw serve` 的 1 秒监督循环负责 spawn/terminate（`packages/multi-workers/mw.py:140-198`；`D-101`）；`:5` 的 serve 文档串；`:49` `_CONDUCTOR_PY`；`:231` `conductor_log`；`:372-374` "a dead conductor does NOT stop serve"。
  - `/mw restart` = 扩展侧 `restartSequence`（`packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:298/:324`）；TS 侧已有 **serve 陈旧检测**：`shared/mw-runner.ts:195+`（"Serve staleness detection + restart"）与 `autopilot/console.ts:611/:629`（stale serve ⇒ 自动重启 + 提示 `/mw restart`，注释指明 conductor 约 1 秒后 spawn）。
  - 本 key 的上游事故：Py 侧进程一直活着但**继续跑旧代码**（E2Feature 2 天零派发，靠人工修文档救回）⇒ 缺的是 Python 侧自证与告警。
- 允许自行扩大取证（全仓只读；`H:\git\E2Feature\.mw\` 下的真实 meta/pid/log）；给上下文来源清单。

## 要求

1. 给出 **`serve.meta` 的真实现状**：谁写、写哪些字段、路径、读写点（`path:line`）；`mw_common` 里的 meta/心跳读写函数；`.mw/` 下各文件的角色（pid、beat、log、meta）。
2. 回答：serve/conductor 启动时**能拿到什么版本信息**（git commit？`vcs`？`_framework_version`？bundle 哈希？`serve.meta.code_dir` 指向源码目录意味着什么），以及"采集 commit 的最小可靠方式"（考虑：工作区可能是 dirty、可能有多个 worktree、Windows 无 git bash）。
3. TS 侧 stale-serve 检测的**判据是什么**（比对 mtime？内容哈希？commit？）、它在 Python 侧是否已有等价物；两者若并存，如何避免双重告警。
4. 给出 **AC-005 的最小改动面清单**（写入点、比对点、告警点、限频键、要改的测试文件），并标注哪些改动会被"各项目重启 serve 才生效"这一事实限制。
5. 只读；唯一允许写的是本卡声明的证据文件。

## 交付格式

结论先行＋逐条 `path:line` 判据＋真实 meta/日志片段＋最小改动面清单（表）＋上下文来源清单＋未覆盖面声明。
