# Achieved: mw-decision-substitution

jev 从「决策底座」变成**能替换中低风险人工决策的执行面**：24 个决策点抽象为 dp，授权收敛到一张配置表，
每次决策留痕、每 phase 出报告、每 key 收尾强制人工签收。

## 交付面

- **注册表与执行面**（Python）：`packages/multi-workers/decision_points.py`（24 项 dp：id/tier/默认值/问题集/
  输入构造/执行器；`decide_for` 11 步控制流；8 层读侧降级；`(mtime,size)` 热重载）；
  `decide_archive.py`（4 类档案行 `decide|override|settle|authority-change` + `prev_sha` 链 + 幂等 + fold）。
- **指令面**：`mw decide dp {list,show,on,off,set,refresh,check,apply}`、`mw decide run`、`mw decide report`
  （Wilson 95% 下界）；`mw decide run` 强制走 `decide_for`（D-036 单一权威）。
- **TS 接线**：dp1 派发（`pm/triage-client.ts` + `pm/ui-bridge.ts` 结构化 state + `decision:` 头行 + settle 关联）、
  dp2 收窄（`pm/pm-orchestrator.ts` 写 `steer-dp2.md`，worker 侧消费 + marker 幂等 + PM 侧终态回退告警）、
  dp3 澄清（`worker/worker-mode.ts` 三切：3a 提问 / 3b 采纳答案 / 3c 本地复用）、`ask_decision` 工具
  （`pm/decision-tool.ts`）。
- **门禁**：phase 末自动报告、done 前强制签收（`evidence/review/sign-final.md` + `conclusion:` 机器行）、
  签收写守卫（write/edit/bash/**worker_file** 四通道拒绝 agent 自签）。
- **文档**：`docs/decision-substitution.md`（31.4KB）、`packages/multi-workers/README.md` 决策替换小节、两包 CHANGELOG。

## 系统行为变化

| 面 | 变化 | 影响 |
| --- | --- | --- |
| worker | dp3 命中时自主澄清（3a 提问 / 3b 采纳档案答案 / 3c 复用本会话已表态），答案以 `[mw dp3-answer]` steer 回灌 | 原本要上抛人等的 `needs-clarification` 里 P2 档部分不再产生人工墙钟 |
| PM | checkpoint 命中 dp2 时自动评估收窄并写 `steer-dp2.md`；`auto` 只允许 `narrow`，拆/直执一律回退人 | PM 不再为「要不要收窄」中断一轮；危险选项仍需人 |
| 派发 | dp1 走结构化 state（≤2000B、注册表全量必填集），建议以 `decision:` 头行写入 task.md，settle 六态回写档案 | 派发类型建议可审计；分歧样本**不再**计为采纳（QG MINOR-1 修复） |
| 授权 | `.mw/decide-points.json` 是唯一权威；P2 默认开、P1/P0 需人显式配置；P0 打开需 `--i-understand-p0` + `authority-change(by=human:p0-confirm)` + 签收必列 | 开关永远由人执行，LLM 只能建议（DS-9/DS-12） |
| worker 工具面 | 新增 `ask_decision`（worker 分支注册，全角色追加）：只透传子进程 `decision_id/mode/acted/escalated_reason`；dp1/dp2/dp3 缺必填字段时零 spawn 返回 `input-incomplete` + `missing_fields` | 工具不再镜像配置表、不再伪造 id/acted（QG MAJOR-1/2 修复） |
| 架构约束 | TS 三处配置表镜像收敛：非对象行 → off、坏 `note`/`tier`/`enabled` → off（与 Python L2/L3/L5 对齐）；根因缓存与「Python 权威、TS 仅短路」注释契约 | 行损坏不再白付一次子进程；降级语义与 Python 一致（QG MAJOR-3 修复） |
| 安全 | 签收写守卫覆盖 `worker_file`（writeless 角色唯一写通道），`sign-final.md` 两落位拒绝并落 `[DECISION_SIGNOFF]` trace | 被派发的 worker 不能再自签满足 done 门禁（QG MAJOR-4 修复） |
| dp3 服务边界 | 子进程未报 `mode`（或非法）→ 视为不可用并上抛人，**不回退**本地配置；3c 本地复用仍用本地 `policy.mode`（零 spawn，无子进程可问） | 消费侧不能再从本地镜像推出 `auto` 并注入 steer（QG MAJOR-3 残留，FIX-E） |
| 签收守卫粒度 | 只认 `evidence/sign-final.md` 与 `evidence/review/sign-final.md`，按**首个** `evidence` 段判定 | 深层产物 `evidence/research/evidence/sign-final.md` 不再被误拒（QG MAJOR-4 残留，FIX-E） |
| 守卫通道一致 | write、edit、bash、`worker_file` 四通道共用**同一份**落位判定（不再分叉） | 同一文件名在四个通道不再出现相反判定（QG-2B 残留，FIX-F） |
| 监控 | `shared/heartbeat.ts` 的 `[START]` 清空上一尝试的 `[END]/exitCode` | 模型重试/fallback 后 `up` 不再恒 `0s`，运行中的任务不再残留旧 `exitCode=3`（mini-spec `mw-heartbeat-attempt-reset`） |

## 验证

- 全量 Python：`8 failed, 2729 passed, 10 deselected`（失败数与基线一致，通过数较基线 +241）
- 本 key 9 个 TS 套件：**192 passed**（dp2-narrow 33 / dp3-answer 21 / decision-tool 23 / triage-client-state 31 /
  decision-association 36 / decision-signoff 12 / xkey-gate-guard-coverage 13 / triage-dispatch 21 / heartbeat-progress 2）
- `npx tsgo --noEmit` rc=0；`biome check`（改动文件）rc=0
- QG 复审一轮：`evidence/quality-gate-report-20261020.md`（PASS-WITH-FINDINGS，AC 12 covered / 3 partial / 0 missing）；
  4 条 major 已由 FIX-A/B/C 修复并 PM 独立复跑，2 条 minor（MINOR-1/MINOR-5）由 FIX-D 修复
- QG 复审二轮（拆窄卡，同一配置模型 `timi/gpt-6.1-sol` 跑完）：
  `evidence/quality-gate-report-20261020c.md` 判 MAJOR-1、MINOR-5 **关闭**、MAJOR-2 **部分关闭**（必填字段集合逐项对齐，
  但 dp1/dp2/dp3 经工具恒 `input-incomplete`）；`evidence/quality-gate-report-20261020d.md` 判 **NOT-CLOSED**
  （`worker-mode.ts:4933` mode 回退、`xkey-gate-guard.ts:383` 深路径误拒），两条已由 FIX-E 收口并经 PM 复跑
  （dp3-answer 21 / xkey-gate-guard-coverage 12 / decision-signoff 11 = 44 passed）；AC 矩阵维持 12/3/0
- QG 复审二轮宽卡重跑：`evidence/quality-gate-report-20261020b.md` 判 **PASS**（一轮 6 条发现 6/6 关闭、
  修复批次无新 D-036 违约/fail-open/跨层漂移）；其两条新残留（写通道落位不对称、doc §3 采纳条件表述不完整）
  已由 FIX-F 收口（四通道两落位一致拒、doc §3 补分歧闸），union 终态 **192 passed**
- 度量基线复核：人工轮次 **93.222 min / 中位 13.600 min**（复现 spec 的 93.3/13.6）
- 全量验证记录：`evidence/runs/verify-mw-decision-substitution-20261020.md`

## 遗留

| 项 | 现状 | 去向 |
| --- | --- | --- |
| AC-003 / AC-004 partial | 机制与测试齐，但本仓从未真实启用（无 `.mw/decide-points.json`、无真实 run） | 立新 key：真实启用一次端到端 + 人工轮次对比（需凭据与 `mw build --install`） |
| L5 真派发路径未验 | TS 改动未进 bundle；`mwds-t23-cutover-recheck` 的 bundle sha 期望失败即其后果 | 同上，`mw build --install` 后补测 |
| `ask_decision` 不能回答 dp1/dp2/dp3 | 三者必填 state 在工具入参里无来源，现为诚实的 `input-incomplete` + `missing_fields`（零 spawn） | 立新 key：给工具加结构化 state 入参（改 LLM 面契约） |
| `trigger` 仅审计用 | 同 dp + 同 owner key 的第二次 ask 复用同一 `decision_id` → `duplicate-replay` | 立新 key：把 `trigger_id` 放进 state（改外发内容与 digest） |
| 档案 `acted` 恒 false | 三个已接线 dp 的执行器都未挂（无 `intent=act` 调用点）；消费侧 `acted=1` 只在 trace 与 `decision:` 头行 | 已写入 `docs/decision-substitution.md` §3 诚实说明；**接受不处理** |
| dp3 3c 本地复用零档案行、legacy `mw decide run` 不落档案行 | 断链已知 | 已写入 `docs/decision-substitution.md` §7 边界清单；**接受不处理** |
| MINOR-7（dp1 关闭态仍 spawn）、MINOR-9（`questions_version` 无跨层执行校验） | 只多付一次子进程 / 漂移不炸但静默 | **接受不处理**（记入本表）；若做，落 `mw decide dp` 后续卡 |
| dp2 `Dp2Authorization.mode` 移除 | 收窄式 API 变更，全仓仅 `dp2-narrow.test.ts` 引用 | 已随 FIX-B 同步，无需迁移 |
| 签收未完成 | done 门禁要求人在 agent 会话外写 `evidence/review/sign-final.md`（`conclusion:` 机器行） | **待人执行**；PM/agent 无权写（守卫四通道拒绝） |
