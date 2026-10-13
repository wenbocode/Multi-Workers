# plan.md — mw-autopilot-gate-alarm-liveness

- Key: `mw-autopilot-gate-alarm-liveness`｜Phase: PLAN｜Baseline: `cc9a46a1a`
- 设计依据：`design.md`（§1 两级主闸与四种阻塞形状 / §2 D1–D10 / §3 接口契约 / §4 改动面 / §5 验证策略 / §7 开放项）
- 需求依据：`spec.md` AC-001…AC-016、P-01–P-08、§7 已复现事实、§8 裁定 D-009…D-015
- 证据依据：`evidence/research/` 下 spec-rq1..rq4 + design-drq1..drq4（共 8 份，全部终态）

## 1 目标与验收主线

本 key 的一条主线 = **让"派发为什么停"可回答且能自动放行的就自动放行**：

1. **可见**：stage 主闸 + 每个 pending gate 恒可见（含抑制原因），不依赖事件（AC-001/003/016）。
2. **不静默**：提醒按 key 抑制、不可解析不抑制、发射走双通道、cap 降级为打断次数（AC-002/004/010）。
3. **能自动就自动**：`stage-close` 有确定性证据即自动放行，缺证据回落并显示缺失项（AC-015，D-014/D-011 中档）。
4. **无人值守也推进**：conductor 合成 claim 接管无 owner 的 key（AC-014 路线①，D-013）。
5. **自身不漂移**：serve 身份 `code_digest` + 4+1 新鲜进程侧入口（AC-005/006）。
6. **判据不炸**：`blocker_class` 序外注册 + fail-closed 反事实测试（AC-007/012）。
7. **回收契约不再量错对象**（AC-013，C-36）。

## 2 并行性分析（派发前必做）

| 写入面（主要文件） | 任务 | 冲突 |
|---|---|---|
| `autopilot/conductor.py` | T-11、T-12、T-14、T-16 | **单文件多任务 ⇒ 串行** |
| `autopilot/gates.py` | T-14 | 与 T-11/12/16 不同文件，但 T-14 同时读 conductor ⇒ 串行化到 T-11/12 之后 |
| `mw.py` | T-13 | 独立 ⇒ 可与 conductor 串行链并行 |
| TS `autopilot/monitor.ts` + `status-model.ts` | T-10、T-14(TS 侧)、T-16(呈现) | 需串行 |
| TS `pm/pm-orchestrator.ts` | T-10 | 同上 |
| TS `shared/change-ledger.ts` | T-17 | 独立 ⇒ 可并行 |
| 测试文件 | 各自任务自带 | 同名测试文件冲突时串行 |
| `serve.meta`/`mw-runner.ts` | T-13 | 唯一写入方 = T-13 |

**批次计划**（同批内文件不重叠）：

- **批 1（并行 3）**：T-10（TS 状态面）+ T-11（Python 抑制/双通道）+ T-13（mw.py 漂移身份）—— 文件不相交。
- **批 2（并行 3）**：T-12（stage-close 自动放行，conductor.py）+ T-17（ledger 角色分流,TS）+ T-15（re-attest/confirm，gates 侧小改 + 新消费者）—— 注意 T-15 与 T-12 都碰 conductor ⇒ 若同批则 T-15 只写非 conductor 文件。
- **批 3（串行）**：T-14（`blocker_class` 序外注册，跨 Py/TS 三读面）—— 依赖 T-11/T-12 对 conductor 的改动落定。
- **批 4（串行）**：T-16（合成 claim，conductor.py 深处 + `_index.parallel` 语义）。
- **批 5**：T-18（对抗式 QG + 运行期验证）→ T-19（收口文档 + pm-state PASS + changelog）。

> 说明：T-14/T-16 放在后面不是优先级低，而是**它们改的是"整队列 fail-closed"面**，必须在同文件的前序改动稳定后再动，否则一次错改会让 console/doctor/conductor 一起坏（DRQ-1 已量化 blast radius）。

## 3 实现卡清单

| 卡 | 任务键 | type | 覆盖 AC | 交付物 | 验收命令（自证） |
|---|---|---|---|---|---|
| T-10 | `mwgal-t10-state-surface` | coding | AC-001/003/010/016 | monitor 常驻 pending 行 + stage 主闸行 + 六值原因 + drop 序修正 + `GateView` 不破坏 + `blocked_on_human` per-key（TS 三处之一） | `node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts test/suite/mwgal-t10-state-surface.test.ts` |
| T-11 | `mwgal-t11-reminder-suppression` | coding | AC-002/004/010 | per-key 抑制 + 不可解析不抑制 + 被抑制留痕 + 双通道发射 + cap 降级 + `blocked_on_human` 另两处同批 | `python -m pytest test_autopilot_gate_schema_v2.py test_mwgal_t11_suppression.py -q`（或 `node ...` 视包而定） |
| T-12 | `mwgal-t12-stage-close-auto-approve` | coding | AC-015（D-014/D-011 中档） | stage-close 自动放行 + 回落可见 + `answered_by=conductor-auto:<rule_id>` 留痕（含 48h 兜底不重复的回归） | 定向 pytest |
| T-13 | `mwgal-t13-serve-drift-identity` | coding | AC-005/006 | `serve.meta` 身份（commit/dirty/`code_digest`/`schema`）+ 采集前置 + 4+1 入口 + skip 集加 `test` | 定向 pytest + TS 定向 vitest |
| T-14 | `mwgal-t14-blocker-class-registration` | coding | AC-007/012 | 序外标量注册（7 登记点）+ 三读面 + 缺省 `None`→判定层 `judgment` + fail-closed 五形态测试 | 定向 pytest + vitest（含 `test_autopilot_gates.py` 的 40 名序断言不变） |
| T-15 | `mwgal-t15-reattest-and-confirm` | coding | AC-008/009 | re-attest（新 gate + `context_refs: reattest-of:<id>`）+ reject 二次确认 + 文档措辞校正 | 定向 pytest |
| T-16 | `mwgal-t16-claim-ownership` | coding | AC-014（D-013 路线①） | 合成 claim-id 生命周期/续期/失效回收 + 人工移交 + `_index.parallel` 呈现 | 定向 pytest + 无接管会话集成 |
| T-17 | `mwgal-t17-ledger-role-aware` | coding | AC-013（C-36a/b/c） | 角色分流 + taskDir 外交付物覆盖 + 未展开变量 `malformed` | `node ... --run test/suite/mwgal-t17-ledger-role-aware.test.ts` + 假阳性语料回归 |
| T-18 | `mwgal-t18-adversarial-qg` | review | 全部 AC | 对抗式质量门：AC 逐条对账、反例构造、运行期证据核对 | read-only（无写入面） |
| T-19 | `mwgal-t19-closeout` | coding | — | `achieved.md`（`## 系统行为变化` + `## 遗留`）+ `evidence/quality-gate-report-*.md` + `pm-state.md` PASS 行 + changelog | `npm run check` + 定向测试 |

## 4 全局约束（每张卡都必须写进卡面）

- **不新增 config 键**（AC-011）；`gate_reminder_max` 语义变化须 TS/Python 同步 + parity 测试绿。
- **不改判据、只改夹具数据**（P-03）。
- **不动被锁死的 `GateView`**（`autopilot-console.test.ts:384-389` 精确 `toEqual`）。
- **TS 第 3 解析面不得静默忽略新字段**（DRQ-1 已量化）。
- **`npm run check` 只在全部 worker 终态后统一跑**（避免与 worker 并发）；每张卡用自己的定向测试自证。
- **复核纪律**：字节可信；**行号不得用于定位**，一律用字符串锚（P-07）。
- **卡面必须逐字写出交付物所需的 H2 段名**（P-08）。
- **运营边界**：JCodingAss / FeatureMigrator 只读，不修现场（用户裁定）。

## 5 收口判据

- 全部卡终态 + PM 逐条复核（字节/锚点/定向测试），QC 主判据：
  - 定向测试全绿 + `npm run check` exit 0 + 零非预期差异；
  - **运行期证据**：无接管会话下派发仍发生（AC-014）；`stage-close` 自动放行占比 > 0 且回落项显示缺失（AC-015）；状态面可见 stage 主闸（AC-016）；
  - `achieved.md` + `evidence/quality-gate-report-<date>.md` + `pm-state.md` 含 PASS；
  - changelog（`packages/*/CHANGELOG.md` 的 `[Unreleased]`）。
- **不在本 key**：EPERM/队列单写入方/`run.json` 唯一权威（另立 key）；C-33（测试写死产物哈希，登记）。
