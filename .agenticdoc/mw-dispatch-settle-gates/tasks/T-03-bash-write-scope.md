# T-03 — AC-005b：`research` 的 bash 写面收窄（`write_scope` 消费端）

- key: `mw-dispatch-settle-gates`｜AC: **AC-005b**｜VC: **VC-020…VC-024**｜波次 **1**｜链 2（`worker-mode.ts`）首卡
- 角色: coding
- **唯一允许改的路径**：① `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`；② 新建 `packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`；③ 自身目录 `report.md`
- 上游：`plan.md §4` 契约 **C1/C2/C3**；`design.md` §4.3（拦截表）；`spec.md` AC-005b

## 现状（以符号名为准）
- 运行期守卫已有 `pi.on("tool_call")`（约 `:944`）→ `checkReadScopeCall`（约 `:955`），**只对 read/ls/find/grep 生效**。
- 因此 `research`（allowlist 含 `bash`，`worker-mode.ts:66`）可经 bash 写**仓库任意位置**（缺口 R23）。
- 目录口径：`agenticdocRoot` = `.agenticdoc/<key>/workers`（约 `:391`），`trueAgenticdocRoot` = `.agenticdoc/<key>`（约 `:393`），`taskDir`（约 `:717`）；worker 的 cwd = 项目根。
- 审计行范式已有：`appendReadScopeTraceLine`（约 `:513`）、`appendStartPidLine`（约 `:467`）。

## 必须实现（P1 档：已知写模式 + 路径判据；失败模式 = 漏放）
1. **触发条件**：`isShellRole(type) && isWritelessRole(type)`（C3，唯一能力来源）。当前命中集 = `{research}`。`coding`/`phase-writer`/`repair`/`roadmap-writer`/`vision` **零影响**；`review`/`verifier`/`reviewer`/`rag-research` 无 bash ⇒ 不进入本判据。
2. **允许写的目录**（解析后的绝对路径判定，`path.resolve` 相对 cwd）：`<trueAgenticdocRoot>/workers/<taskKey>/**` 与 `<trueAgenticdocRoot>/evidence/**`；若 task.md 带 `write_scope:` 行（C1），以该行为准**取交集**（`write_scope` 不得放宽到拒绝清单）。
3. **拒绝清单（绝对优先）**：`<trueAgenticdocRoot>/pm-state.md`、`<trueAgenticdocRoot>/workers/_workers*`、`<项目根>/.agenticdoc/_index.parallel`、其他 key 的整个目录、`packages/**`、`.git/**`。
4. **已知写模式提取目标路径**（至少覆盖）：重定向 `>`/`>>`、`tee`、`cp`/`mv`/`rm`/`mkdir`/`touch`/`truncate`、`sed -i`、`git checkout|apply|clean`、`curl -o`/`wget -O`、PowerShell `Set-Content`/`Out-File`/`New-Item`/`Remove-Item`、`python`/`node` 一行脚本中的**字符串字面量路径**。
5. **越界处理**：`return {block: true, message: <含允许目录与后果的说明>}` + 一条 `trace.log` 审计行（复用既有 append 范式，格式自定但必须含 `write-scope`、被拦命令摘要、判定原因）。
6. **不拦**：纯读命令（`rg`/`grep`/`ls`/`find`/`cat`/`git status|log|diff`/`python` 只读脚本）与**无法归类**的命令 ⇒ 放行，且**不得**产生审计噪声行（无法归类只在 `worker.log` 记一条 debug 或干脆不记，但不得写 `trace.log` 噪音）。
7. 不得与 read-scope 判据互相吞并：read-scope 行为逐字不变（`test/suite` 既有 read-scope 用例必须仍绿）。

## 反向用例（必须真跑并贴输出）
- (a) 写 `pm-state.md` ⇒ block + 审计行；(b) 写 `workers/_workers.parallel` ⇒ block；(c) 写 `.agenticdoc/_index.parallel` ⇒ block；(d) 写其他 key 目录 ⇒ block；(e) 写 `packages/**` 或 `.git/**` ⇒ block。
- (f) 写自身 taskDir / `<key>/evidence/**` ⇒ 放行；(g) 纯读命令组（≥6 条）全部放行；(h) 无法归类命令放行。
- (i) `coding`/`repair`/`vision` 角色：同样命令**全部放行**（零影响）。

## 对照协议（`plan.md §5`）
A 摘除 bash 分支 ⇒ (a)~(e) 转红；B 反转默认（无法归类即 block）⇒ (g)/(h) 转红（证明 P1 选择的是漏放而非误拦）；C 移除拒绝清单中的 `pm-state.md` ⇒ (a) 转红。每组贴 sha256 → 逆改 → 红 → 还原 → 绿。

## 证据
```
[VERIFY] VC-020: denied=5 (pm-state,_workers,_index,other-key,packages/git) audit_lines=5
[VERIFY] VC-021: own_taskdir=allow key_evidence=allow
[VERIFY] VC-022: readonly_cmds=6 all_allowed=true
[VERIFY] VC-023: write_scope_rendered_by_same_renderer=true empty_case=no_line
[VERIFY] VC-024: coding_like_roles_affected=0
```
命令：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts`

## 禁止
不改 `pm/ui-bridge.ts`（渲染端由 T-02 负责，本卡只消费 `write_scope` 行）；不改 `pm-orchestrator.ts` / `output-writer.ts`；不改大测试文件 `test/extensions/agent-team-loop.test.ts`；不 build；不 commit；不跑全量套件 / `npm run check`。
