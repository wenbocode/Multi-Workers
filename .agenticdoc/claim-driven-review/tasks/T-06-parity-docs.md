# T-06: 平价锁 + 文档 + CHANGELOG（coding）

- Key: claim-driven-review
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「文件驱动的去中心化协调」；跨语言常量必须单源，否则两侧漂移）。
- 设计依据：`design.md` §2.3（单源常量表）、§8（测试设计）。
- 上游事实：
  - 同仓已有“7 值闭集 + 单源”先例与漂移教训：`packages/multi-workers/decision_points.py:111-120`（`ESCALATED_REASONS`，同模块注释记录了归档侧另写一份即漂移）。
  - T-17 平价锁的既有形态：`packages/multi-workers/test_autopilot_l0.py:233-263`（逐类 order-exact）。
  - changelog 规则：只改 `## [Unreleased]`，不碰已发布版本段。
- 依赖：T-01（TS 常量）、T-03（Python 常量）已合入。若实际导出名与本文不符，以实际为准并在 `output.md` 记录差异。

## 要求

1. 新增 `packages/multi-workers/test_claim_parity.py`：
   - 从 `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts` 用正则抽取 `CLAIM_TYPES` / `UNVERIFIED_REASONS` / `CLAIM_GATE_DEFAULT` / `CLAIM_BUDGET` 的字面量，与 `autopilot/dispatch.py` 的同名常量逐项、逐序比较（`CLAIM_TYPES` 与 `UNVERIFIED_REASONS` 必须顺序一致）。
   - 断言 `CLAIM_BUDGET` 五个键的数值完全相等（`perClaim/callCap/hardCap/claimByteCap/byteCapMax`）。
   - 断言 `MW_CLAIM_GATE` 环境变量名在两侧源码中各出现恰好一次（防止一侧改名）。
2. 文档：
   - `packages/coding-agent/README.md` 的派发卡小节：加「claims 块」一段（七列表、四类、`cmd` 类必须由 PM 预执行落盘 `evidence/claims/<file>#<id>`、manual 上限与双倍记账）与「断言裁决」七列表的产出要求。
   - `packages/multi-workers/README.md`：加 conductor 侧的 caps 推导式（`min(30,Σ预算)` / `min(393216,65536×n)`）与 `MW_CLAIM_GATE` 说明。
   - 两处都要写清"advisory 是默认，enforce 需显式开启"。
3. CHANGELOG（只改 `## [Unreleased]`，追加到既有子节）：
   - `packages/coding-agent/CHANGELOG.md`：`### Added` 一条（claims 块契约 + 断言裁决覆盖判据 + `[CLAIMS]` 证据行），`### Changed` 一条（PM 手工派发现在会渲染 `read_scope` 与 caps）。
   - `packages/multi-workers/CHANGELOG.md`：`### Added` 一条（conductor 的 claims 解析与 caps 推导、`tokens_per_closed_claim` 度量）。
   - 用词与既有条目一致（不长于 3 行，不提内部 key 名）。
4. 不新增依赖；不改任何既有测试断言。

## 写入允许面

- `packages/multi-workers/test_claim_parity.py`
- `packages/coding-agent/README.md`
- `packages/multi-workers/README.md`
- `packages/coding-agent/CHANGELOG.md`
- `packages/multi-workers/CHANGELOG.md`

## 写入禁止面

- 任何 `src/**`、`autopilot/**`、`test/**`（除新建的 `test_claim_parity.py`）、`dist/**`

## 验收命令

```
cd packages/multi-workers
python -m pytest test_claim_parity.py -q
cd ../..
npm run check
```

两条都必须 0 fail / 0 诊断。

## 改动历史

- 2026-10-21 创建（无既有改动）

## 交付格式

`output.md` 四段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。证据段给：平价测试的 4 组比较结果、两处 README 的锚点小节路径、CHANGELOG 的实际插入位置。残留段写明未覆盖的文档面（如 `docs/`）。
