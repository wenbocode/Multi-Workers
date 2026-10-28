# achieved.md —— claim-driven-review 目标结算

对照对象：`spec.md` §0「预期收益」三条 + §3 AC-001…AC-008。
数据来源：`.agenticdoc/**/workers/*/trace.log`（`[END] tools=` / `[CLAIMS]` / `[MODEL_FALLBACK]`）
+ `~/.mw/usage/runs.jsonl` 的 `start.session_id` → pi 会话 `usage`（join 率 99.79%，口径见
`claim-driven-review-orchestration/evidence/research/spec-rq3-metrics-baseline-20261022.md` §2）。
复算脚本：`.mw/runs/probe-goal-benefit.py`。

## 1. 预期收益逐条判定

| # | spec §0 的原话 | 实测 | 判定 |
|---|---|---|---|
| B1 | 单 review 单元取数次数 159 → ≤60 | 基线 **52**（n=32，max 98）→ 断言卡 **16**（n=3：13 / 16 / 23） | **达成**（-69%）；基线 159 这个数在语料里**复现不出来**，见 §4 |
| B2 | 死亡上下文 214k → ≤120k | 基线 final ctx **110,666**（max **253,273**）→ 断言卡 **35,782**（max **41,377**） | **达成**（中位 -68%，峰值 -84%） |
| B3 | review 因超窗进入降级链次数归零 | 断言卡 run 上 `[MODEL_FALLBACK]` / `model unavailable` = **0**；全库 review 类命中 5 处，全部在断言卡之前 | **达成**（新路径零命中） |
| B4 | `tokens_per_closed_claim` 可作跨 key 可比指标 | 恒 `n/a`；`mw stats --key claim-driven-review` 的 `rows with claims = 0` | **未达成**（wiring，非归因：launcher `end` 不写 `claims`） |

实测明细（join 后）：

```
claims  cdr-t07f   tools=16 exit=0 final_ctx= 24,442 out=14,510 claims=(5,5)
claims  cdr-t07e   tools=23 exit=2 final_ctx= 41,377 out=28,628 claims=(5,5)
claims  cdr-t07b   tools=13 exit=2 final_ctx= 35,782 out= 2,946 claims=(5,2)
pre     median(32) tools=52        final_ctx=110,666
pre     max         tools=98       final_ctx=253,273   (ds-qg-review-2, exit=2)
```

这也是本 key 的核心主张（「成本与断言数绑定」）第一次拿到真数：**同一个仓库、同类型任务，
把"读工程"换成"判断言"之后，工具调用中位 -69%、上下文峰值 -84%**。

## 2. AC 判定（详见 verify.md）

| AC | 结论 |
|---|---|
| AC-001 claims 块契约 + 派发期校验 | 达成 |
| AC-002 结算七列表 + 覆盖判据 + `exit 2` | 达成 |
| AC-003 预算承载 `min(30, 6n)` / `min(393216, 65536n)` | 达成（T-08 修正公式后） |
| AC-004 `triage → 扇出 → merge` + 20-claim 4+1 | **未达成**（转 `claim-driven-review-orchestration`） |
| AC-005 度量 + `n/a` 降级 | 部分（(b) 达成；(a) 依赖 AC-004） |
| AC-006 advisory 默认 + 开关同名同义 | 部分（开关达成；对照样本不足，转新 key 按"有功效声明的看门狗"重写） |
| AC-007 零回归 | 达成（无 claims 卡逐字节不变；旧预算默认值未动） |
| AC-008 六条反绕过 + 负例 | 达成（⑥ 判据经实测替换） |

## 3. 端到端证据

`evidence/t07-e2e-results-20261022.md`：同一张 5-claim 卡三轮，`caps 5 → 30`，
`closed 2 → 5`、`exit 2 → 0`，最终 `claims=5 closed=5 unverified=0 fetches=13 exit=0`。

## 4. 已发现但不属本 key 交付面的缺陷（留给后续）

1. **"159"这个基线数字复现不出来**：语料里 review 类的 `tools=` 中位 52、max 98；
   `[TOOL]` 事件计数与 `tools=` 也不是 1:1（`ds-qg-review-2`：`[TOOL]`=236 vs `tools=`=98）。
   §0 当时把两种计数器混用了。**结论不受影响**（同一计数器下 -69%），但基线必须标口径。
2. **B4 的断点在 launcher，不在 token**：`end` 事件键集
   `{event,exit,reconciled,run_id,status,ts,wall_s}` 不含 `claims`（`launcher.py:320`），
   `usage.py:1021` 无从读取。修它是 `claim-driven-review-orchestration` 的 AC-010c。
3. **超时不可用 exit 码识别**：`exit=1` + trace `[TIMEOUT]`，全库无 `124`。
   任何"按 exit 分布"的统计先按 trace 标记分类。

## 5. 系统行为变化

**派发侧（PM）**
- 带 `<!-- mw-claims: v1 -->` 块的卡：解析出 claims 后，`read_scope` 自动并入每条 claim 的 `定位`（去 span/去 `#id`），
  `l2_read_file_cap/l2_read_byte_cap` 改由 `min(30, 6×n)` / `min(393216, 65536×n)` 推导，
  回执行多一行 `[claims] advisory claims=N caps=A/B warnings=[...]`；`claims=0(unparsed)` 不再静默。
- 不带 claims 块的卡：输出与 HEAD **逐字节相同**（462 B 锁死），无新增字段。
- `MW_CLAIM_GATE` 默认 `advisory`：结构性 gap 只进 warnings；`enforce` 才拒绝，且拒绝零副作用。

**worker 侧**
- 读面配额口径变化：`grep`/`find`/`ls` **与 `read` 共用调用次数配额**（字节只对 `read` 计）。
  这是全仓行为变化，影响所有声明了 `l2_read_*` 的角色，不只 review。
- 结算多一组 gap token（`claim:<id>:missing|verdict|evidence|reason|carried-from` 等 12 个），
  与既有 recovery gap 合并进 `ok` 折叠；缺失时复用一次性 self-check steer，仍缺则 `exit 2`。
- 终态新增 `[CLAIMS] <iso> claims=… closed=… partial=… unverified=… fetches=…` 独立行
  （绝不扩 `[END]`）与 `run.json.claims` 子对象；无 claims 块的 run 两者都不写。

**度量侧**
- `usage.py` 增 `parse_claims_line` / `claims_metrics` / per-run 报表列；不可归因时输出 `n/a` + `attributable=false`。
- `status-model.ts` 增 `ClaimMetricsView` / `keyClaims` / 面板行。
- **已知缺口**：launcher 的 `end` 事件不写 `claims`（`launcher.py:320`），所以 `mw stats` 的 claims 列仍为 0、
  `tokens_per_closed_claim` 恒 `n/a`。修它在新 key（AC-010c）。

**文档**：`packages/coding-agent/README.md`、`packages/multi-workers/README.md` 各增 claims 一节；
两个 `CHANGELOG.md` 的 `[Unreleased]` 已记 Added/Changed。

## 6. 遗留

| 遗留项 | 去向 |
|---|---|
| AC-004 编排（`triage → 扇出 → merge`、20-claim 的 4+1 实跑） | 新 key `claim-driven-review-orchestration` |
| AC-005(a) 两种拆法并排比较（需 arm 级聚合） | 同上 |
| AC-006 advisory 前后基线（改写为有功效声明的看门狗） | 同上 |
| B4 `tokens_per_closed_claim` 恒 `n/a` | 同上 AC-010c（launcher `end` 补 `claims`，改动面小） |
| `mw.py stats --detail --json` 仍写 HTML 副作用（`mw.py:10381`） | 记入 `_pitfalls.md`，单独立小修 |
| spec §0「159」基线口径混用（实测中位 52 / max 98） | 记入 `_pitfalls.md` |
| `.agenticdoc/_scratch/*.mine.ts`、`Python/`（嵌装 CPython，5k+ 文件） | 接受不处理（非本 key 创建，待用户定） |

## 7. 结论

预期收益 3/4 达成且数字可复算，第 4 条（头号成本指标）因台账 wiring 未通而恒为 `n/a`。
AC-004（编排）未达成，与 AC-005(a) 的对照比较、AC-006 的基线样本一起移交
`claim-driven-review-orchestration`，不在本 key 的 done 结论里算达成。
