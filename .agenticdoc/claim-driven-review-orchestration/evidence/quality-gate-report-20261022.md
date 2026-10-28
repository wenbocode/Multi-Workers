# 质量门报告：claim-driven-review-orchestration（negative result）

- 日期：2026-10-22
- 范围：**narrow** —— 审计本 key 交付的 6 个模块与 2 个测试套件（代码正确性与边界），
  **不**把「功能目标未达成」当作代码缺陷；功能判决见 `evidence/m1-verdict-20261022.md`。
- 审计者：PM（自审；本 key 无独立 review worker，因 E2 实验已耗尽预算且不拆卡）

## 结论

`QG: PASS（scope=narrow）| 交付 6 模块 + 8 测试文件，116 TS + 58 Python 全绿 | 功能判决：NOT ACHIEVED`

即：**交付的代码是对的、可复现的、默认关闭的**；**功能假设被证伪**（散文 review 不拆）。
两者必须分开记账，不能因为代码绿了就说功能成立。

## 1. 交付清单与各自证据

| 模块 | 职责 | 测试 | PM 复跑 |
|---|---|---|---|
| `shared/review-split.ts` | 三档开关解析（env > config > default） | `review-split-mode.test.ts` 29 | ✅ 29 |
| `pm/review-split-plan.ts` | 组合器：清单 → 装箱 → manifest → 回执行 | `review-split-plan.test.ts` 28 | ✅ 28 |
| `pm/review-split-gate.ts` | `plan` 档门禁：写 manifest、零派发 | `review-split-gate.test.ts` 13 | ✅ 13 |
| `shared/claim-extract.ts` | E1 提取（findings/acRows/diffHunks/反模式） | `claim-extract.test.ts` 18 | ✅ 18 |
| `shared/claim-pack.ts` | 簇原子装箱（父子/共享定位/预算/机检底线） | `claim-pack.test.ts` 11 | ✅ 11 |
| `shared/split-manifest.ts` | manifest 构建 + 篡改检测（EOL 归一化 sha） | `split-manifest.test.ts` 17 | ✅ 17 |
| `autopilot/review_split.py` + `mw.py` | Python 侧解析（CLI 与 conductor 共用） | `test_review_split_parity.py` 51 + `test_review_split_cli.py` 7 | ✅ 58 |

复跑命令与结果（PM 独立执行）：

```
vitest 6 files  → Tests 116 passed (116)
pytest 2 files  → 58 passed in 4.97s
```

## 2. AC 对账（spec §3/§5）

| AC | 判定 | 依据 |
|---|---|---|
| AC-E1 结构化提取 | ⚠️ 部分 | 四个来源都实现、`claimsGaps` 其余规则全过；但 `falsifier` 对 findings/acRows/manual 必须上游提供，缺则计数（`extract:falsifier-missing`），故「产出必过 claimsGaps」按字面无法达成 → 已在 spec 改为新口径 |
| AC-E2 散文提取 | ❌ 未达成 | 实验证明：坐标层机检 73.3%，判定层 0/39；`manualCap` 使忠实编码不可能（`evidence/m1-verdict-20261022.md` §1/§2） |
| AC-E3 范围切保底 | ➖ 未实施 | 未走到 E3（E1/E2 都未过） |
| AC-E4 L0 保真 | ✅ | brief↔claim 映射与 `l0= mapped/asks` 落地；不变式在所有分支成立（含 no-source） |
| AC-E5 阶段 0 计费 | ➖ 未验 | 无对照臂运行 |
| AC-001 拆分信号 | ✅ | `[review-split] mode= units= claims= cap= capSum= inflation= l0= fals= l1=` |
| AC-002 manifest 完整性 | ✅ | `verifySplitManifest` 五种 gap + 篡改测试 |
| AC-003 簇原子性 | ✅ | `split:orphan-child`、共享定位聚簇 |
| AC-004 拆分确定性 | ✅ | 两种 `acIndex` 拼法 → `units`/`ids`/`receipt` 逐字节相同 |
| AC-005 子卡可回读 | ✅ | 单元卡七列表可被 `parseClaimsBlock` 回读 |
| AC-S1/S1b 默认 off | ✅ | 无 env 无 config → `off`；坏 JSON → `invalid=config-invalid-json` |
| AC-S2 plan 零副作用 | ✅ | 临时项目实测：只有 `evidence/split/*.json`，无 `workers/`、无队列文件 |
| AC-S3 判据口径 | ⚠️ | `l1` 只计结构性 gap、`fals=` 单列已实现；未做对照臂统计 |
| AC-006…AC-012（on 档/merge/度量） | ➖ 未做 | M2/M3/M4 因 M1 判决暂停 |

## 3. 质量门问题清单

| ID | 问题 | 状态 | 处置 |
|---|---|---|---|
| Q-1 | `claim-pack.ts` 按 `判据` token 聚簇，未做 basename 规范化（定位已规范化，判据未） | 已知残留 | 记入 `achieved.md` 遗留；不在本 key 修（`get`判据里的路径来自母卡，母卡路径写法不受我们控制） |
| Q-2 | `canonicalizeLocator` 会把同名跨目录文件并成一簇 | 已知取舍 | 卡的明确取舍（宁可少拆一个单元，不要把一个簇撕两半） |
| Q-3 | 段落型 ask 无长度上限 | 已知残留 | 观测：最长段落约 400 字符，未造成 gap；留观测项 |
| Q-4 | `plan` 只在 `type: review` 生效，其他类型静默 | 设计 | 见 D-024 |
| Q-5 | 单元 `.tmp` 名未加并发后缀 | 已知残留 | 同一 taskKey 并发写同一 manifest 属误用；未加锁 |
| Q-6 | `mw.py --json` 的 `invalid` 与 `invalid_env` 同值 | 设计 | 文本输出去重，JSON 两个字段都在 |
| Q-7 | 文档已改：`design.md` §2.3 改 camelCase + EOL sha 口径 | 已修 | PM 直接改并过 mermaid 校验 |

## 4. 反假证据抽查（P-025 类）

本 key 自己的交付里，抽查了 3 条"已通过"声称：

1. **「`plan` 零副作用」**：不看断言，直接看文件系统 —— 临时项目跑完 `tree=[".agenticdoc",".mw"]`，
   `workers/`、`workers.parallel`、`workers.serial` 全部不存在。✅
2. **「sha 与 `card_sha256` 同口径」**：`cardDigest(CRLF file)` 与 `manifest.parentSha256` 逐位相等，
   且等于 Python `sha256_eol_normalized` 的结果。✅
3. **「116 + 58 全绿」**：PM 独立复跑，不是引用 worker 报告。✅

## 5. 判决说明

- 代码质量：PASS（narrow）。6 个模块都有独立测试、纯函数边界清楚、默认关闭、零副作用可验。
- 功能目标：**NOT ACHIEVED**。本轮的科学产出是「散文 review 不该拆」这个结论，
  以及「review 卡坐标会过期」这个副产品发现。两者都写进 `achieved.md`。
- 不得因为本报告是 PASS 就认为拆分成立 —— 两者是不同的问题，见 `evidence/m1-verdict-20261022.md`。
