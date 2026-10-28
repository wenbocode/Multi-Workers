# verify — claim-driven-review-orchestration

- 判决口径：**本 key 的目标是"验证散文 review 能否被拆"，不是"把拆分做出来"**。
  因此 AC 达成为「已核实的事实」，未达成为「被证伪的假设」，两者都是本 key 的产出。
- 证据文件：`evidence/m1-verdict-20261022.md`、`evidence/m1-exit-probe-20261022.md`、
  `evidence/quality-gate-report-20261022.md`

## 1. 交付物核对（代码）

| 交付 | 存在 | 测试 | PM 复跑 |
|---|---|---|---|
| `shared/review-split.ts` | ✅ | `review-split-mode.test.ts` | 29 passed |
| `pm/review-split-plan.ts` | ✅ | `review-split-plan.test.ts` | 28 passed |
| `pm/review-split-gate.ts` + `ui-bridge.ts` 两处插入 | ✅ | `review-split-gate.test.ts` | 13 passed |
| `shared/claim-extract.ts` | ✅ | `claim-extract.test.ts` | 18 passed |
| `shared/claim-pack.ts` | ✅ | `claim-pack.test.ts` | 11 passed |
| `shared/split-manifest.ts` | ✅ | `split-manifest.test.ts` | 17 passed |
| `autopilot/review_split.py` + `mw.py` 薄封装 | ✅ | `test_review_split_parity.py` + `test_review_split_cli.py` | 58 passed |

合计：**vitest 116 / pytest 58**，均 PM 独立复跑（命令见质量门报告 §1）。

## 2. AC 逐条（对照 spec §3/§5）

| AC | 状态 | 证据 |
|---|---|---|
| AC-E1 结构化提取 | ⚠️ 达成（口径已修订） | 四来源齐全；`falsifier` 规则改为"机器类派生具体反证 / 人判类必需否则计数"，spec 已同步 |
| AC-E2 散文提取 | ❌ **证伪** | 判定层机检 0/39；`manualCap=4` 使忠实编码不可能 |
| AC-E3 范围切保底 | ➖ 未走到 | E1/E2 均未过 |
| AC-E4 L0 保真 | ✅ | `l0=mapped/asks` + 不变式在所有分支成立（含 no-source） |
| AC-E5 阶段 0 计费 | ➖ 未验 | 无对照臂 |
| AC-001 拆分信号 | ✅ | 回执行九个字段 |
| AC-002 manifest 完整性 | ✅ | 五种 gap + 篡改测试 |
| AC-003 簇原子性 | ✅ | `split:orphan-child` / 共享定位同簇 |
| AC-004 拆分确定性 | ✅ | 两种拼法 → `units`/`ids`/`receipt` 逐字节相同 |
| AC-005 子卡可回读 | ✅ | 七列表可被 `parseClaimsBlock` 回读 |
| AC-S1/S1b 默认 off / 坏配置可见 | ✅ | `invalid=config-invalid-json` |
| AC-S2 plan 零副作用 | ✅ | 文件系统实测：无 `workers/`、无队列文件 |
| AC-S3 判据口径 | ⚠️ | `fals=` 单列、`l1` 只计结构性 gap 已实现；未做对照臂 |
| AC-006…AC-012（on/merge/度量） | ➖ 撤销 | 随 M1 判决 |

## 3. 三条硬结论（可被后续任务直接引用）

1. **不要把散文 QG 卡拆成 claims 单元**：拆了 6.2 倍读预算，机检率仍为 0（`evidence/m1-verdict-20261022.md`）。
2. **claims 契约的适用边界**：`manualCap = min(4, ceil(n/3))` 使"逐条判 N 条 AC"的卡不可忠实编码；
   claims 驱动只适合"断言可机检"的评审。
3. **review 卡的坐标会过期，且现有三层无人报警**：5 条硬漂移 + AC 范围过期（同文件 §3）。

## 4. 未验证 / 未做

- 未测 A 类（变更对账）review 的拆分效果 —— A 类机检天然成立（diff hunk 可枚举），本判决只否定审计卡。
- `on` 档从未接线（M3 撤销），`merge` 门禁与度量（M2/M4）未实现。
- `dist/**` 未重建，`plan` 档尚未进运行时（默认 `off`，不影响现有行为）。

## 5. 收口建议

按负结果结案：保留代码（默认 `off`）、记录结论、冷却两周。
「坐标清扫」作为候选能力**留给用户决定是否立新 key**，不在本 key 内实现。
