# T-09 manifest sha 与卡摘要对齐（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1（只读规划器）
- type: coding
- 依赖：T-07（`shared/split-manifest.ts`）done

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（文件驱动协调：协调状态靠文件自证，不靠进程记忆）。
- T-07 交付时自己上报了一条残留：`sha256Hex` 是**原始 UTF-8** 摘要，而派发卡的 `card_sha256`
  用的是 **EOL 归一化**摘要——实现见
  `packages/coding-agent/src/extensions/agent-team-loop/shared/card-digest.ts:2`（`sha256EolNormalizedBytes`）。
  两者口径不同意味着 manifest 的 `parentSha256` **无法与 task.md 头部的 `card_sha256` 对照**，
  sha 链就形同虚设（母卡被改过也发现不了）。
- 另：`design.md` §2.3 的样本用了 snake_case，而卡钉的是 camelCase —— 已由 PM 改文档为 camelCase，
  本卡只需保持实现与之一致，不要改名。

## 要求

改 `packages/coding-agent/src/extensions/agent-team-loop/shared/split-manifest.ts`：

1. 摘要函数改为 **EOL 归一化**口径：直接复用 `card-digest.ts` 的
   `sha256EolNormalizedBytes(new Uint8Array(Buffer.from(text, "utf8")))`（或在本地用
   `text.replace(/\r\n/g, "\n")` 后对 UTF-8 字节求 sha256，必须与 `cardDigest()` 结果一致）。
   导出名保持 `sha256Hex`（调用方不感知），文档注释写明"EOL-normalized, same口径 as card_sha256"。
2. `parentSha256` / `units[*].sha256` / `selfSha256` 全部改用该口径。
3. 不改字段名、不改 `verifySplitManifest` 的 gap 文案、不改序列化格式。
4. 新增测试（在 `test/suite/split-manifest.test.ts`）：
   - 把一段带 `\r\n` 的卡文本写入临时文件，`cardDigest(tmpPath)` 必须**等于**
     `buildSplitManifest({parentText: 同一段 CRLF 文本}).parentSha256`；
   - 同一文本换成 `\n` 结尾，得到**相同**的 `parentSha256`（EOL 不影响）；
   - 内容差一个字符 → sha 不同。

## 交付格式

- 改 `shared/split-manifest.ts` + `test/suite/split-manifest.test.ts`（原 14 条保留，新增 3 条）。
- 报告 `report.md` 四段；`## 证据` 里贴出 `cardDigest` 与 `parentSha256` 相等的实际断言输出。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/split-manifest.ts`
- `packages/coding-agent/test/suite/split-manifest.test.ts`

## 写入禁止面

- `shared/card-digest.ts`、`shared/claim-extract.ts`（另一 worker 在写）、其他 `packages/**`、
  `.mw/**`、`.agenticdoc/**`、`dist/**`

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/split-manifest.test.ts`（≥17 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡：T-07 上报的原始 sha × 卡摘要 EOL 归一化口径不一致 | `card-digest.ts:2`、T-07 report 残留 |
