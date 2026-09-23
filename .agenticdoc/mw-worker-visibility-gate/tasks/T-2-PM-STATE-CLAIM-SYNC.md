# Task T-2: pm-state Claim-Id 同步写入器（新模块）

## 元信息
- Stage: 1（波形 1，可与 T-1 并行）
- 依赖: 无
- 风险: 中（写 pm-state.md，写错会抹掉 7 段模板）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-010, AC-011]
- vc_refs: [VC-010, VC-011]
- 文件面（唯一）：新建 `packages/coding-agent/src/extensions/agent-team-loop/shared/pm-state-claim.ts`、新建 `packages/coding-agent/test/extensions/agent-team-loop-pm-state-claim.test.ts`

## 背景（实测）

- 框架 7 段模板（`advance_phase.py` 生成）：`# PM State: <key>` + `## 1. Snapshot` … `## 7. Process Log`，Snapshot 内含 `- Key:`/`- Claim-Id:`/`- Phase:`/`- Next Action:`/`- Started:`/`- Updated:`。
- **本仓三个 key 的 `pm-state.md` 实测全部为 CRLF**（`\r\n` 计数 = 行数，LF-only = 0）→ 同步必须探测并原样保留换行（P-010 同类：换行翻转会造成整文件 diff）。
- TS 侧**不要**复用 `pm/state-manager.ts` 的 `StateManager.write()`：它整体重写成旧 3 段模板（`## Section 1: Snapshot` + `## Notes`），会抹掉 7 段模板与证据区。
- 框架侧 `update_index.py` 的 stub 只在新文件时创建（`Key`/`Claim-Id`/`Phase: init`）；`advance_phase.py` 升级模板时保留 `- Claim-Id:`。因此"文件存在但缺 `- Claim-Id:`"只在文件被手改损伤时出现 → 此时**不写、不重建**，只回 reason。
- 权威事实源：`_index.parallel` 的 Claim 列（`shared/implementation-gate.ts:229` 用它判 live claim）；pm-state 的 `- Claim-Id:` 是同值的镜像。

## 交付物

1. 新建 `shared/pm-state-claim.ts`：

```ts
export interface PmStateClaimSyncResult { ok: boolean; reason?: string; }
/** 把 {agenticdocRoot}/{key}/pm-state.md 的 '- Claim-Id:' 一行替换为 claimId（单行原地替换）。 */
export function syncPmStateClaimId(agenticdocRoot: string, key: string, claimId: string): PmStateClaimSyncResult;
```

要求：
- 读**字节**（`fs.readFileSync(file)`）→ 探测主导换行 `\r\n`（存在即用 `\r\n`，否则 `\n`）→ 用 `^- Claim-Id:[^\r\n]*`（`m` 标志，`count=1`）替换该行内容（保留行尾换行与其余字节**逐字节不变**）→ 原子写（同目录 `<file>.tmp` + `fs.renameSync`）。
- 失败分支（都返回 `{ok:false, reason}`，**绝不创建/重写文件**）：文件不存在 → `reason: "pm-state.md missing"`；存在但无 `- Claim-Id:` 行 → `reason: "pm-state.md has no '- Claim-Id:' line"`。
- 成功 → `{ok:true}`。
- 纯同步函数（无 async、无 spawn、无网络）；不得 `throw`。

2. 新增测试 `test/extensions/agent-team-loop-pm-state-claim.test.ts`（临时目录 `os.tmpdir()`）：
   - VC-010 半侧：写入一份**CRLF** 的 7 段模板样本 → 同步 → 断言 (a) 该行值等于新值；(b) `\r\n` 数不变且 LF-only 计数仍为 0；(c) `## ` 二级标题数不变；(d) `- Updated:` 行数不变；(e) 其余字节与样本**除该行外**逐字节相等（用替换前后两个 Buffer 比较，只允许该行差异）。
   - LF 变体：LF 文件同步后仍是纯 LF（LF-only 计数不变、`\r\n` = 0）。
   - VC-011 半侧：文件缺 `- Claim-Id:` 行 → 返回 `ok=false` 且文件**逐字节未变**（比较前后 Buffer 相等）；文件不存在 → `ok=false` 且**未创建文件**（`fs.existsSync` false）。
   - `[VERIFY]` 行用 `process.stdout.write("…\n")`，字段取自实测：如 `[VERIFY] VC-010: claim_ids_equal=true headings=7 updated_lines=1`、`[VERIFY] VC-011: claim_ok=false warnings=1 pm_state_untouched=true`（`pm_state_untouched` 用"前后 Buffer 相等"的实测布尔值）。

## 约束

- 只新建上述两个文件；**不改** `pm/state-manager.ts`、不改 `pm/ui-bridge.ts`（T-3 负责接线）、不改 `dist/**`、不改 Python、不改 `test/extensions/agent-team-loop.test.ts`。
- TS 只用可擦除语法；无 `any`；无 inline `import()`。
- 不 commit；不运行 `mw build`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-pm-state-claim.test.ts
cd H:/git/Multi-Workers && npm run check
git status --short
```

## 报告要求

最终消息给出：改动文件、用例计数、每条 `[VERIFY]` 行原文、CRLF/LF 两种变体的字节级实测数字、以及任何偏离 design 的实现细节。
