# achieved — claim-driven-review-orchestration

- 判决：**负结果（negative result）**。散文 review 的拆分**不成立**；交付的代码保留、默认关闭。
- 依据：`evidence/m1-verdict-20261022.md`、`evidence/m1-exit-probe-20261022.md`、
  `evidence/quality-gate-report-20261022.md`

## 结论一句话

让真实 review（散文 brief / QG findings）自动拆成可并行子卡，这一设想在本项目语料上被证伪：
两张路径各自都能产出 claim，但产出的全是「逐条人判」，机检率为 0，拆完还要 6.2 倍读预算。

## 系统行为变化

1. **新增三档开关 `MW_REVIEW_SPLIT`（默认 `off`）**
   - 解析在 TS `shared/review-split.ts` 与 Python `autopilot/review_split.py`（CLI 与 conductor 共用），
     优先级 `env > .mw/review-split.json > default`，诊断串两边逐字一致（共用 20 例表
     `test/suite/fixtures/review-split-cases.json`）。
   - `mw review-split status|set` 可读写；坏 JSON 会显式报 `invalid=config-invalid-json`，
     不再静默降级成 `off`。
2. **新增五块可复用零件**（都只被 `off` 之外的路径调用，`off` 逐字节不变）
   - `shared/claim-extract.ts`：从 findings / AC 行 / diff hunk / 反模式命中提 claims；
     反证条件规则：机器类可派生**具体**反证，人判类必须上游提供，缺则计数 `extract:falsifier-missing`。
   - `shared/claim-pack.ts`：簇原子装箱（父子链 + 共享定位同簇；`Σ预算(manual=2) ≤ 8`；≤5 槽；
     每单元 ≥1 条机检 claim，否则 `split:unit-infeasible`）。
   - `shared/split-manifest.ts`：manifest 构建 + 篡改检测；sha 用 **EOL 归一化**，与 task.md 头
     `card_sha256` 逐位可比（母卡被改可发现）。
   - `pm/review-split-plan.ts`：组合器，产出 `[review-split] mode= units= claims= cap= capSum=
     inflation= l0= fals= l1=` 回执行与 manifest；纯函数、幂等、不抛异常。
   - `pm/review-split-gate.ts` + `ui-bridge.ts` 两处 ≤6 行插入：`plan` 档在**写 task.md 之前**短路，
     只落 `evidence/split/review-<task>-manifest.json`，零 task 目录、零队列行（实测文件系统验证）。
3. **两条不可逆的设计结论**（写进契约，后续不得绕开）
   - **反证条件不得模板化**：给 manual claim 自动生成"判据不成立"是同义反复，能过相似度检查但语义为空；
     缺就计数，不许编。
   - **拆分必须路径无关**：所有定位先规范成 `basename:line`，否则同一张卡会因 `spec.md:42` /
     `.agenticdoc/x/spec.md:42` 的写法差异拆出不同单元数（实测 8 vs 12）。

## 实测数字

| 输入 | 结果 |
|---|---|
| 带 claims 块的卡（`T-07a`，5 条） | `units=1 claims=5 inflation=1.00 l0=5/5 l1=ok` |
| `T-QG-evidence-closure`（散文，13→16 AC） | `units=12 claims=34 fals=34 inflation=6.20`，**12/12 单元 `manual-only`** |
| `QG-review-2` | `units=1 claims=30 inflation=1.00`，机检 0 |
| `signoff/QG-review` | `units=1 claims=25 l0=5/6`，机检 0 |
| `T-18-adversarial-qg` | `units=2 claims=3 l0=2/15` |
| E2 实验（≤12 读） | 它会提的 claim 73.3% 真机检；卡的真实交付物（逐条判 AC）**0/39** |

## 副产品：review 卡在派发前就已过期

PM 复核 E2 worker 的声称，五条全部成立：

- `index.ts:61`（空行）→ 注册实际在 `:80`
- `worktree-junction-guard.ts:180`（别的分支）→ `pi.on("tool_call")` 在 `:215`
- `diff-model-catalog.mjs:161`（console.error）→ 拦截在 `:257`
- 卡覆盖 AC-001..013，`spec.md` 已有 AC-001..016
- vitest 基数 `23+9` vs `achieved.md` 的 `46（33+13）`

现有三层（派发门禁 / 执行期 / 结算期）没有一层会因此变红 —— 这是 P-025 类假证据的入口，
也是本轮唯一"投入产出为正"的发现。

## 遗留

| 项 | 去向 |
|---|---|
| 散文 review 拆分不成立 | **本 key 结案结论**；冷却两周（D-025），期内不得以补丁为由重启 |
| 「坐标清扫」候选能力（`[coord-sweep] cited= ok= drift= stale-scope=`） | **待用户决定是否立新 key**；本轮只产出证据，不实现 |
| M2（merge 门禁）/ M3（`on` 档）/ M4（度量） | 未做，随 M1 判决撤销 |
| `claim-pack.ts` 按 `判据` token 聚簇未做 basename 规范化 | 记入 `.agenticdoc/_pitfalls.md`（同 key 内不修） |
| `canonicalizeLocator` 会并簇同名跨目录文件 | 已知取舍，接受 |
| 段落型 ask 无长度上限 | 观测项（实测最长约 400 字符，未致 gap） |
| 单元 `.tmp` 无并发后缀 | 接受（同 taskKey 并发写属误用） |
| `dist/**` 仍是 12:29 前的产物，`plan` 档未安装到运行时 | 需 `mw build --install --allow-dirty` 才在真实会话生效；因默认 `off`，不急 |
