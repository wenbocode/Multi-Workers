# Achieved: mw-jev-provider-integration

> 一句话：给 mw 加了**可选、默认关闭**的决策服务（`mw decide`，三传输后端 + 预算/重试/fail-soft/证据行），并把第一个决策点 **DP-1 派发前分诊** 接到 PM 派发路径上，产出旁路建议 + 回执呈现 + ledger 留痕，不改写任何派发决策。

- key: mw-jev-provider-integration · 相位: EXECUTE → VERIFY → done
- 日期: 2026-10-16 · 类型: 功能新增（Python 决策客户端 + 传输后端 + CLI + doctor 行 + TS 接入）

## 交付物

| 层 | 文件 | 内容 |
| --- | --- | --- |
| Python 客户端 | `packages/multi-workers/decision.py`（974 行，新） | 契约/校验/预算/重试退避/fail-soft/证据行/`FakeBackend`；`DecisionConfig` 从 `.mw/decide.json` fail-soft 读取 |
| Python 传输 | `packages/multi-workers/decision_backends.py`（895 行，新） | B2 `llm-transitional`（默认，`/v1/messages` + 强制 `submit_decision` 工具调用）、B1 `llmproxy-anthropic`（`entry-unavailable`）、B3 `direct-systemone`（保留位）、`probe_matrix` |
| CLI | `packages/multi-workers/mw.py`（+344，纯新增） | `mw decide <run\|probe\|show\|set>`；嵌套 argparse；`--json` 机器出口；`set` P-003 原子写；`set --json` 与 `show` 同为 `<redacted>` |
| 运维面 | `packages/multi-workers/mw_common.py`（+107，纯新增） | `_doctor_decide` + 条件渲染 `triage:` 行（zero-perturbation，未配置输出逐字节不变，信息行不进 issues） |
| TS 接入 | `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`（新）+ `ui-bridge.ts` + `pm-orchestrator.ts` | DP-1 挂在 `planDispatchFrontmatter`（两个 PM 入口共用）；复用 `mw-runner` 无窗 spawn + `-X utf8`；建议进派发回执；`triage-suggestion`/`triage-unavailable` notice kind；仅"建议≠派发类型"时 `deliverPmAlert` |
| 测试 | `test_decide.py` / `test_decide_backends.py` / `test_decide_cli.py`（新）+ `test/suite/triage-dispatch.test.ts`（新） | 131 Python + 21 TS，全 hermetic |
| 文档 | `packages/multi-workers/README.md`、两侧 `CHANGELOG.md`、`.agenticdoc/mw-jev-provider-integration/docs/jev-integration-flow-and-usage.md` | 决策服务小节（配置/命令/fail-soft/置信度硬规则/doctor/覆盖面与数据流/**建议被谁消费**）、`[Unreleased] > ### Added` 条目；**正式全链路文档**：输入→输出→执行→结果四段 + 四象限 + 凭据链 + L1–L5 测试矩阵 |
| 证据 | `evidence/`（spec 三束 + design 四束 + 线上探针 + 端到端验证 + QG 报告） | 见 `pm-state.md` §3 证据账 |

## 系统行为变化

- **默认零行为变化**：未创建 `<project>/.mw/decide.json` 的项目——不发网络调用、不 spawn 子进程、不写证据文件、不投 notice、doctor 输出逐字节不变、派发回执逐字节不变（TS 侧真断言，`triage-dispatch.test.ts`）。
- **显式启用后新增的能力**：
  1. `mw decide run|probe|show|set`（CLI = API，`--json` 机读出口；成功与 `available=false` 都 exit 0，参数非法 exit 2）。
  2. DP-1 派发前分诊：在 PM 派发（`dispatch_worker` / `/worker`）前同步产出 `triage_type` + `triage_risk` **旁路建议**（硬超时 20s，可配），进派发回执；建议与派发类型不一致时唤醒 PM 一次；每次调用写一行结构化证据到 `.agenticdoc/_autopilot/triage-decisions.jsonl`（Python 单写）。
  3. `mw doctor` 新增 `triage:` 信息行；`mw doctor --json` 新增 `decide` section。
- **明确不改的**：派发的 type/角色/模型、watchdog/checkpoint 策略、模型目录/前缀/路由/凭据值域、`timi.json` 的 jev 标注；`confidence_source != api` 时置信度不得进入任何门控（只作弱排序）。
- **影响面**：`packages/multi-workers`（新增 5 文件 + 2 文件纯新增行）；`packages/coding-agent` 扩展的 PM 侧（新增 1 文件 + 2 文件局部改动）；对既有 key/其它窗口零写入面交叠（提交走索引级重建时验证）。

## 验收结论

- **端到端跑通（目标①）**：`mw decide run` 真实调用 B2 成功——`available=true`、`transport=llm-transitional`、`model=glm-5.3-flashx`、`attempts=1`；PM 独立复跑一次 `latency_ms=5148`，`triage_type=review(0.9)` / `triage_risk=1`。`probe` 复现 D-1 两锚点（jev `@/v1/messages`=429、`@/responses`=200 upstream-error）。
- **接口友好（目标②）**：一次调用 JSON 进 JSON 出；不可用绝不阻断且机器可读 `reason` 区分 8 类；PM 三处可见（回执 / ledger / doctor）；覆盖面如实声明 2/15。
- **质量门（第一轮，T-05b）**：`evidence/quality-gate-report-20261016.md` → **PASS，0 blockers / 0 majors / 4 minors / 5 notes**；4 条 minor（README 披露、`set --json` 明文 key、自证式断言、评审未跑命令）**全部处置完毕**（前三项已修，第四项由 PM 直执重跑闭合）。
- **质量门（第二轮全量复审，T-06，用户指令）**：`evidence/quality-gate-report-20261016-recheck.md` → **PASS，0 blockers / 0 majors / 2 minors / 8 notes**；10 项 QG 验收 + 5 项代码 review 全部达标。关键核实：AC-009「逐字节等价」在 TS/Python 两侧均为真断言；AC-011 的 M3 修法已建立真不变量（后端改名即测试红）；B1 七个 return 点全部 `available=False`（无成功出口）；TS 硬超时经 `spawnSync` 真杀子进程；`deliverPmAlert` 仅在类型不一致且未静音时触发。两条 minor 处置：m2（评审无 shell）= PM 重跑闭合；**m1（design D-002 的「校验错误回喂重发」缺失）= 已修**（T-07，判定为必修：`temperature: 0` 使客户端重试必然复现同一非法输出，回喂是唯一有效纠错机会）。
- **回归**：`packages/multi-workers` pytest `8 failed / 2488 passed`，8 条与既有 Windows/环境基线逐条相同（零新增）；`npm run check` 本 key 文件 0 error/warning/info（唯一 finding 属他窗 `mwoc-*` 文件）。

## 遗留

| 遗留项 | 去向 |
| --- | --- |
| **D-1 上游阻塞**：timiai/llmproxy 未暴露承载 `state`+`questions` 的决策入口（决策形状路径穷举 20+ 全 404；jev `@/v1/messages` 持续 429；`/responses` 报 typesafe `Unmapped LLM provider`） | **上游问题单**（`spec.md` §4 D-1 五问）交 llmproxy 维护方；解除后 B1 由 `entry-unavailable` 切换为可用（实现位已留） |
| **覆盖面 2/15**：conductor 的 13 个自动派发点（`dispatch.py` 侧）未接入 DP-1 | **立新 key**（挂点 C 锚点已在 design D-006 写死：`dispatch.py` REGISTRY 之后、`workers.lock` 临界区之前） |
| B1/B3 未实机验证；`box` 问题类型未跑真实链路；`mode: async` 配置位未交付；TS 面板未逐字同步 doctor 行 | 记入本节；随上游/后续波次处理 |
| **回喂多轮消息形状未实机验证**（T-07 残留）：hermetic 测试只覆盖 fake transport；真实 llmproxy 对 `user → assistant(tool_use) → user(tool_result, is_error)` 多轮形状是否接受未证 | 记入本节；配合 D-1 上游沟通时一并确认 |
| `BackendOutcome.detail` 计算后被丢弃：失败时 CLI/证据行只有 `reason` 枚举，无可读诊断 | 接受为已知边界（补进响应会动 design D-003 的「固定 8 键」契约）；排障靠 `reason` 8 类 + `mw decide probe` |
| `mw decide set api_key=<值>` 的值进 argv（进程列表可见）；README 只写了「不推荐写盘」 | **待用户裁定**；可选改进 = 支持从 stdin 读值 |
| 真实 `runDecideMw`（TS 侧真正 spawn 的函数）零直接测试覆盖（测试桩替在 seam 上） | 有意为之（避免真实子进程）；spawn 参数错误只能人工核对 |
| `decide_evidence_path` 在 `decision.py` 与 `mw_common.py` 各实现一份 | 接受为已知重复（客户端写 / doctor 读，合并会引入跨模块依赖） |
| 本 key 未提交 git（工作区改动） | 等用户指令后按文件清单分离提交；混合文件走索引级重建 |
| 框架缺陷候选：写面守卫把「动词+斜杠」散文判成路径 `/`（P-046）；`worker_file` 传绝对路径无自愈提示（P-048） | 已记 `_pitfalls.md`；是否立项由用户决定 |
