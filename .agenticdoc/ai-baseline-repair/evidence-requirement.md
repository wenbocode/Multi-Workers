# Evidence Requirement: ai-baseline-repair

> Key: ai-baseline-repair
> 生成: 2026-09-10（design 阶段）
> spec 指纹（canonical 管道：`grep -oE 'AC-[0-9]{3}' spec.md | sort -u | sha1sum | cut -c1-12`，git-bash 实算于 2026-09-10 19:33，spec 锁定时）: **541028221b8a**
>
> ac_fingerprint: 541028221b8a（机器可读；quality gate Step 1 前置校验用）

## AC → VC → 证据要求

| AC | VC | 证据（quality gate 提交形态） |
|---|---|---|
| AC-001 cloudflare TS2353 修复（保功能） | VC-004 | 命令输出（三 API 注册仍在）+ diff 注记 |
| AC-002 model ID 映射替换 | VC-005 | 映射表 + catalog 核对脚本输出 |
| AC-003 cross-api 8 处类型面修复 | VC-006 | diff 审阅注记（无断言删除） |
| AC-004 tool-choice + TS1294 | VC-001 | tsgo 输出（含于 26→0） |
| AC-005 tsgo 零错 + check 全绿 | VC-001/002 | 两条命令完整输出 |
| AC-006 ai 套件零失败 | VC-003 | vitest 输出 + 预存 8 失败逐个留痕（修复/同根自愈说明） |
| AC-007 第二层归因报告 | VC-007 | evidence/runs/attribution-2026-09-10.md（A/B/C 分类+计数+建议表+用户决策区） |
| AC-008 预防约定落文档 | VC-008 | packages/ai 文档 diff |
| GC-A4 修复面最小化 | VC-009 | biome 输出 + diff 范围核对清单 |

## 免测/降级说明

- 无。全部 AC 有可执行验证路径（CI 语义靠本地命令复现：tsgo / npm run check / vitest）。
- 凭证门控的 describe 块（CLOUDFLARE/OPENAI 等）本地多跳过——类型级正确性由 tsgo 保证，与现状 CI 行为一致，不另做降级。
