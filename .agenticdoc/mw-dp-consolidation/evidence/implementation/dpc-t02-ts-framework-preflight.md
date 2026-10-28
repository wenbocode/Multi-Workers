# T02 实施前核对：TS 旧ID / 派发链缓存边界 / 框架签收 validator / human-H12 资格

- 任务卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-t02-ts-framework-preflight/task.md`（已读到实际 EOF，131 行）
- 卡源：`.agenticdoc/mw-dp-consolidation/tasks/T02-ts-framework-preflight.md`（已读到实际 EOF）
- 角色/类型：research（只读静态取证，本任务不写任何产品/框架源码）
- 唯一证据：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t02-ts-framework-preflight.md`
- 取证窗口：2026-10-26 09:07–09:35 (+08:00)，静态读码 + hash + rg 计数；未运行产品测试、未安装/重启、未 commit

## 结论

1. **TS 侧旧编号仍在生产链活跃，迁移未开始**：八入口（dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route）在源码中命中数为 0；25 个旧 ID 在 9 个 TS 生产文件中以“注册表键 / 工具 schema 枚举 / 运行时 policy 键 / 提示词 / UI 表单键 / 注释”存在。VC-003 主动旧引用=0 当前**不成立**，这是 T04–T16 的既定工作，不是本卡缺陷。
2. **派发链安全切换前置已定位**：源码树运行的 pi 直接加载 `src/extensions/agent-team-loop/index.ts`（builtin）；已安装/打包窗口加载编译产物 `agent-team-loop.js`（repo `dist`、项目 `.pi/extensions`、全局 `~/.pi/agent/extensions`，本机存在 2026-10-25 14:41:52 的全局 bundle）。**源码改动不会进入 bundle 窗口**，需 `mw build [--install]` 才会生效——该动作属禁止面。结论：八入口编码只能在源码树/隔离 fixture 中验证，bundle 窗口在另行批准前保持旧 ID 行为；不得用“文件已改”当运行已切换。
3. **框架签收 validator 的当前词表仍是 legacy**：`.agents/skills/agentic-task/scripts/advance_phase.py:41` 的 `DECISION_CONCLUSION_RE` 只接受 `continue|narrow|revoke`，`decide_signoff.CONCLUSIONS`（`packages/multi-workers/decide_signoff.py:83`）同源；dp-sign-key 的 `finalize|continue|user-confirm` 中 `finalize`/`user-confirm` 会被判为“缺机器行”（`advance_phase.py:342`），无法识别当前有效 finalize。另存在 `signoff: disable` 短路（`advance_phase.py:244`、`:322`，读 `.mw/decide.json`）——正是 AC-039 要求“不得以 disable 绕原必需签收”的待处置点。二者都必须在 T25 限定写面内改造，**本任务不写**。
4. **human/H12 资格目前不可证**：`answer_gate_confirmed` 的 `answered_by` 是自由文本审计串，CLI 默认值 `mw-cli@<host>`（`mw.py:9470`），无 TTY/进程/凭证校验；观察面 page token 无 per-DP 资格含义，role 只是“窗口结构性推导”而非认证（`decision-tool.ts:715` 读 card `type:`）。H12 熔断无恢复通道（复用 RQ14：清除=`auto-brake.md` 人工改写）。→ 凡依赖“已证 human/H12 授权才可编码”的项（AC-036/037/038/039 的恢复与签收资格部分）保持 blocked，缺口需设计/授权补面；**不得删刹车、不得自建授权**。
5. **AC-044 派发前缺口**：`task-dispatcher.ts` 无 vision/图像能力门（全文件无 `vision`/`image` 命中），`toolsForType` 对未知类型回落 `["read","write","edit","bash","find","grep","ls"]`（`worker-mode.ts:149,179-180`），`initiatorRoleFromWorkerTask` 词表只有 coding/research/review/unknown（`decision-tool.ts:724`）。现状下 `type: vision` 会被当作“未注册类型 + 全权力工具集”，即 VC-044 的 `coding_downgrades=0` 与“无图能力启动=0”目前无机制保证，必须在 T14 显式注册 + 加硬门；移除其他框架类型=0 仍须保住 `TOOL_ALLOWLISTS` 现有条目。

## 证据

### E1 基线/单 writer（框架特批两文件，只读保存）

命令：`git -C .agents/skills/agentic-task status --porcelain=v1`（rc=0）、`git -C .agents/skills/agentic-task diff --stat -- scripts/advance_phase.py scripts/test_advance_phase.py`（rc=0）、`Get-FileHash`/`File.ReadAllBytes` 计数、`git ls-files --error-unmatch`。

| 路径 | bytes | sha256 | EOL | 主仓 tracked | 框架 clone 状态 |
|---|---|---|---|---|---|
| `.agents/skills/agentic-task/scripts/advance_phase.py` | 40085 | `8958e5b7e76513b6403e838b063bf1412e7541c5f666521e5fde12faa1199952` | CRLF 904（LF 904，全为 CRLF 组成） | 否 | `M`（+287 行未提交） |
| `.agents/skills/agentic-task/scripts/test_advance_phase.py` | 27153 | `8d3c2604d184231202f9d8644e918be9abfe749d2824be679e32d3b9081358b8` | CRLF 575 | 否 | `M`（+12 行未提交） |
| `.agents/skills/agentic-task/core/scripts/advance_phase.py` | 40085 | 同上 sha256 | CRLF 904 | 否 | `M` |
| `.agents/skills/agentic-task/core/scripts/test_advance_phase.py` | 27153 | 同上 sha256 | CRLF 575 | 否 | `M` |
| `.agents/skills/agentic-task/claude/scripts/advance_phase.py` | 40085 | 同上 sha256 | CRLF 904 | 否 | `M` |
| `.agents/skills/agentic-task/claude/scripts/test_advance_phase.py` | 27153 | 同上 sha256 | CRLF 575 | 否 | `M` |
| `.claude/scripts/advance_phase.py`（镜像） | 40085 | 同上 sha256 | CRLF 904 | 否 | 非本 clone |
| `.claude/scripts/test_advance_phase.py`（镜像） | 27153 | 同上 sha256 | CRLF 575 | 否 | 非本 clone |

- 4 个目录 × 2 文件当前**字节相同**（`scripts/`、`core/scripts/`、`claude/scripts/`、`.claude/scripts/`），即“既有 diff”已同时落在所有副本；任何后续改动若不按此同步会产生 drift，但**设计只授权 `.agents/skills/agentic-task/scripts/` 两文件**，其余三处为只读。
- 既有 diff 内容（`git diff -- scripts/advance_phase.py`，只读保存要点）：新增 `DECISION_SIGNOFF_REL/DECISION_SIGNOFF_RULE_TARGET/DECISION_CONCLUSION_RE/DECISION_COUNTED_ROWS_RE/DECISION_ROWS_SHA_RE`（:35-43）；`GATES` 增 `decision_signoff` 规则（:107-121）；`_load_decide_signoff`、`_decision_signoff_disabled`、`_matches_key`、`_key_has_decide_rows`、`_decision_signoff_problems`（:215-377）；`check_gate` 分支（:463-466）；`find_mw_cli`/`maybe_write_decision_review`（:690-770）；done 前置 NOTE（:864-870 区）。`test_advance_phase.py` 既有 diff = 两处 fixture 增写 `evidence/review/sign-final.md`（`conclusion: continue`）。
- 单 writer 判定：`implementation-dag.json` 中 `dpc-t02-ts-framework-preflight.deps=[]`；两框架文件的 `product_write_face` 只出现在 `dpc-t25-framework-sign-gate`（`deps=[T11..T18,T24]`，DAG 行 1545-1559）。`.agenticdoc/_index.parallel` 中 `advance_phase` 命中 0 条 claim。→ 当前无并发 writer；T02 只读，框架写入归 T25。
- 主仓既有未提交 TS diff（必须保留/协调，不覆盖）：`git status --porcelain=v1 -- packages/coding-agent/src/extensions/agent-team-loop`（rc=0）显示 9 个 `M`：`index.ts`、`pm/decision-tool.ts`、`pm/pm-orchestrator.ts`、`pm/triage-client.ts`、`pm/ui-bridge.ts`、`shared/decide-registry.generated.ts`、`shared/dispatch-card.ts`、`worker/output-sections.ts`、`worker/worker-mode.ts`；7 个 `??`：`pm/decision-task-state.ts`、`pm/review-split-gate.ts`、`pm/review-split-plan.ts`、`shared/claim-extract.ts`、`shared/claim-pack.ts`、`shared/review-split.ts`、`shared/split-manifest.ts`。

### E2 盘点基线（TS 生产文件 hash，供 T04–T16 writer 交接）

命令：`File.ReadAllBytes` + SHA256 + CRLF 计数（rc=0）。全部 LF-only（crlf=0）。

| 文件（`packages/coding-agent/src/extensions/agent-team-loop/`） | bytes | sha256 |
|---|---|---|
| `index.ts` | 5908 | `db432cdc7248453c9579b0ae906748694fc8eab0a7d3ae98a56a0f7ca0a3ed5c` |
| `pm/decision-tool.ts` | 89846 | `3c1388f5ce8ee8d4336be7207083f918c70c6e681c089d62522a36fc671f9f9e` |
| `pm/pm-orchestrator.ts` | 123514 | `82f4e7de5d7304087c673662b5e26ccdc983a0ac188ea371ce832f2a3cbcd00c` |
| `pm/triage-client.ts` | 48631 | `70551a67c82bd463ee040267758d2d3a2d19ae3387d9329b9a6817581c651d58` |
| `pm/ui-bridge.ts` | 228859 | `c77017a29f9194c2c200d61be108de3dbacb00e799bc2c97062b44d1300180e9` |
| `pm/task-dispatcher.ts` | 22553 | `95be04ae586e7b48431070243fc53a39f6703a8919d41ef311bce59777762081` |
| `shared/decide-policy.ts` | 6516 | `572ff5fd2b005adb6c432b7f0b48c7a7059e51b7d4ab7b5a1ee236254c9cfd98` |
| `shared/decide-registry.generated.ts` | 30264 | `699719c2bf7e64cbb51866f8fda39784c6d0ee9b09d7762c9c49e5fbb30127e4` |
| `shared/xkey-gate-guard.ts` | 28452 | `3442ed197bb74b9bb7f02843924b59e1e7358ae5a9e077656bc53b108bd71366` |
| `shared/task-frontmatter.ts` | 8504 | `d0ad6d8dc8805416ff95ad632f17875cadb3a6b9aa8e968d16e3a888f3ec7cd1` |
| `worker/worker-mode.ts` | 250973 | `efc1d5fcc9c754b9d66773283414465f02a16137037b88e0a76f4f831675150a` |

### E3 旧 ID 在 TS 生产面的逐项分类（命令：`rg -o '\bdp(?:2[0-5]|1[0-9]|[1-9])(?:-…)?\b'`，rc=0）

| 文件:行 | 形态 | 分类（对迁移的含义） |
|---|---|---|
| `shared/decide-registry.generated.ts:3,36+` | `@generated ... do not edit`，`DECIDE_REGISTRY` 25 个键（dp1…dp25） | **活跃注册投影**；单一源=`packages/multi-workers/decide_registry.json`+`scripts/gen_decide_registry_ts.py`，只能再生成，不得手写第二合同 |
| `pm/decision-tool.ts:132-157` | `ASK_DECISION_DP_IDS` 25 条 `as const` | **活跃工具枚举源** |
| `pm/decision-tool.ts:1647-1650` | `DP_ENUM_SCHEMA = Type.Union(ASK_DECISION_DP_IDS.map(Type.Literal))` | **可提交枚举本身**（模型可传入的 dp 值），旧ID=25 可提交 |
| `pm/decision-tool.ts:169-175` | `ASK_DECISION_ENFORCED_STATE_DP_IDS=[dp1,dp2,dp3,dp25]` | 活跃前置校验分支 |
| `pm/decision-tool.ts:214` | `ASK_DECISION_PM_ONLY_DP_IDS=[dp2,dp25]` | 活跃角色拒绝分支 |
| `pm/decision-tool.ts:219-223` | `ASK_DECISION_MATERIAL_DP_IDS=[dp2,dp3,dp25]` | 活跃材料契约分支 |
| `pm/decision-tool.ts:226` / `:843` | `DP3_ID="dp3-worker-clarify"` / `DP25_ID="dp25-signoff-conclusion"` | 活跃路由常量（`dp===DP25_ID` 走同次签收路径 `:1238`） |
| `pm/triage-client.ts:77` | `DP1_ID="dp1-dispatch-type"` | 活跃派发决策 ID |
| `pm/triage-client.ts:424-430` | legacy 结构化字段表 `dp4/dp5/dp6/dp13` | 活跃 legacy 兼容分支（注释自认 debt） |
| `pm/triage-client.ts:157-160,277-285,1012` | `points.dp1.enabled` / `points.dp1.alert_on_disagreement` | **运行期 policy 键**（读活 `.mw/decide.json`），改名必须同步消费方，否则新键被忽略 |
| `pm/triage-client.ts:923` / `pm/ui-bridge.ts:563` | `DECIDE_REGISTRY[dpId]` 驱动字段/表单 | UI/表单由注册表键决定 → 换键即换可提交面（M09） |
| `pm/ui-bridge.ts` dp1 ×42（:262-400 区） | “dp1 state=material”/dispatch 消费/生命周期注释与标签 | 提示词+诊断串（非注册），随 M06 改名 |
| `worker/worker-mode.ts:5007,5655,5680,5702,5798` | `DP3_ID` 常量 + `validateDecisionMaterial(DP3_ID,…)` + `[DECIDE] dp=…` trace | 活跃生产调用（worker fire-and-forget 通道） |
| `worker/worker-mode.ts` dp3 ×34 / dp2 ×16 | 提示词/handling 候选/终态叙述 | 提示词面（M07） |
| `pm/pm-orchestrator.ts` dp2 ×20（`splitDecisionId` :882-885） | `<dp>:<trigger>` 解析、提示词、note | 活跃消费者+提示词（M06） |
| `shared/xkey-gate-guard.ts:303,377` | `dp25-signoff-conclusion` 签收 guard 注释/行来源 | 活跃跨key guard 语义引用 |
| `shared/decide-policy.ts:12-13`、`index.ts:91,98`、`pm-orchestrator.ts:814` | 纯注释（dp2/dp3/dp10） | 非活跃，随改随记 |

计数（`rg -o` 唯一 token，src 全域）：`dp1-dispatch-type`5、`dp2-checkpoint-split`7、`dp3-worker-clarify`6、`dp4-failure-handling`4、`dp5-test-triage`3、`dp6-qg-verdict`3、`dp7-gate-failure`2、`dp8-scope-change`2、`dp9-model-select`2、`dp10…dp24` 各 2、`dp25-signoff-conclusion`9；另 `dp1`61/`dp2`61/`dp3`54/`dp25`32 为短写（多为提示词与注释）。**八新名命中 0**（`rg dp-w-type|dp-pm-steer|dp-w-check-task|dp-QG|dp-gate-approve|dp-sign-key|dp-auto|dp-route packages/coding-agent/src` 无输出）。

### E4 派发链：真实解析面与缓存边界

- 源码树运行入口：`pi-test.sh` 用 `tsx packages/coding-agent/src/cli.ts`；`packages/coding-agent/src/main.ts:530` `const extensionFactories = [...builtInExtensions, …]`，而 `src/extensions/index.ts:2-8` 把 `agent-team-loop` 作为 builtin 直接 import **源码**。
- 已装/bundle 窗口：`mw_common.py:2943` `global_ext_dir()` = `$PI_CODING_AGENT_DIR/extensions` 或 `~/.pi/agent/extensions`；`mw.py:9971-9987` 定义 `dist/extensions/agent-team-loop.js` 构建产物与 `_EXT_SRC_REL`（esbuild 打包 `index.ts`）；`mw.py:10193` 安装为 `<agent_dir>/extensions/agent-team-loop.js`。
- 本机实测：`packages/multi-workers/dist/extensions/agent-team-loop.js` 1,471,556 B / 2026-10-25 14:41:52；`C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js` 同尺寸同秒（另存 `.bak-20261021`）；`src/extensions/agent-team-loop` 最新文件 mtime 2026-10-24 17:30。→ 产物不旧于当前源码，但**任何后续源码改动都必须 rebuild+install 才能进入 bundle 窗口**。
- 本窗身份（可证部分）：`env` 中 `PI_CODING_AGENT=true`、`PI_WORKER_TASK=…dpc-t02-ts-framework-preflight/task.md`、`PI_PROVIDER=timi`、`PI_MODEL=deepseek-v4.1-flash`；`PI_CODING_AGENT_DIR` 未设置 → 全局 ext 目录为默认 `~/.pi/agent/extensions`（该处存在 bundle）。
- 安全切换前置（写进 T04–T16 编码前置）：①只在源码树/`test/suite` faux 路径验证；②`dist`/全局 bundle/`.pi/extensions` 一律不写、不 install、不重启；③bundle 窗口继续按旧 ID 行为运行，不得宣称“已切换”；④改名若涉及运行期 policy 键（`points.dp1.*`），旧键读取必须与活 config 只读约束一致，不得改活 policy。

### E5 框架签收 validator 现状（只读，`advance_phase.py`）

| 位置 | 事实 | 缺口 |
|---|---|---|
| `:41` `DECISION_CONCLUSION_RE` | `(?m)^conclusion:\s*(continue|narrow|revoke)\s*$` | 无 `finalize`/`user-confirm`；`finalize` 直接命中 `:342` “缺机器行” |
| `:83`（`decide_signoff.py`）`CONCLUSIONS=("continue","narrow","revoke")` | 与框架正则同词表，`verdict()` 拒绝其它值（`:464`） | dp-sign-key 三选项无法表达；词表差异是迁移硬点 |
| `:309-377` `_decision_signoff_problems` | ①`signoff: disable` → `[]` ②该 key 无 `kind=decide` 行 → `[]` ③文件存在 ④`conclusion` 行 ⑤`counted_rows`/`rows_sha256` 必存 ⑥`collect()` 重算比 sha/行数 ⑦`continue` 跑 `verdict()` | 不区分“当前有效 finalize”；`:322` 的 disable 短路即 AC-039 要收紧的 legacy 绕行；`:363-375` 依赖 `packages/multi-workers` 可导入（找不到即硬失败） |
| `:463-466` `check_gate` 分支 | `decision_signoff` 无条件执行，适用性下沉 | 保留其余门禁语义（本卡不改） |
| `:696-770` `find_mw_cli`/`maybe_write_decision_review` | 推进后自动跑 `mw decide report --write`，失败仅 WARN | 不影响 done 判据（属既有行为，勿混入签收硬门改造） |
| `:864-870` done NOTE | `signoff=disable` 时打印“签收被显式关闭” | 显式 disable 合法性需 AC-039 裁决，不得默认保留 |
| `test_advance_phase.py` 既有 diff | 两个 fixture 写 `conclusion: continue` | 新词表正反例（finalize 有效 / continue-user-confirm 不代 done / disable 不绕行）尚不存在 |

### E6 human / H12 资格：当前机制可证 vs 缺口

| 面 | 可证的 | 不能证明的（缺口） |
|---|---|---|
| gate 人工答复 | `conductor.answer_gate_confirmed`（`conductor.py:7981-8020`）要求 `answered_by` 为非空串；`reject` 需 `confirm=True`；已答 gate fail-closed | `answered_by` 是自由文本；CLI 默认 `mw-cli@<host>`（`mw.py:9470,12316`）；无 TTY、无进程身份、无凭证 → **不证明 human** |
| 决策工具 role | `index.ts:93` worker 用 `initiatorRoleFromWorkerTask(PI_WORKER_TASK)`；`:102` PM 硬编码 `initiatorRole:"pm"`；`decision-tool.ts:715-725` 只读 card `type:` | 结构性≠认证：进程 env + 可读 card 即可自封角色；`type:` 非法值回落 `unknown` |
| 观察面 page token | 复用 RQ20（`evidence/research/design-observation-server-20261026.md:47-50`）：control token/page token 只作“能不能提交”，无 per-DP 资格；HTTP 侧校验精确 Host/Origin/`Sec-Fetch-Site` | Origin 布尔/TTY 只约束传输，不证明操作人；`Observation.actor_kind` 由 provider 侧硬写 `("human","user-explicit")` |
| H12 熔断恢复 | 复用 RQ14（`evidence/research/design-autopilot-effects-20261026.md:9,42,73-84`）：`auto-brake.md` 只让 `auto_decide_gates` 早退；`AUTO_RULE_BY_KIND` 无规则的 kind 结构上永不被自动链决定；`revoke_auto_decision` 不能撤熔断 | 现状**无恢复通道**：清除=人工改文件，无“原因消除证据+预授权+硬检查”三条件，无观察/再熔断规则 → H12 恢复编码 blocked |
| 结论 | role/写面/claim 的结构性检查存在且不可由模型参数绕过 | **human/H12 授权资格无机制证据**；需要新受控通道设计+明确人工授权，不能用 page token/自报 role/TTY/origin 布尔替代 |

### E7 本任务 changed-files / 命令 / rc

- changed-files：仅本文件 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t02-ts-framework-preflight.md`。未改任何源码/配置/框架文件；未创建第二报告或第二决策账本。
- 命令与 rc：`git status --porcelain=v1 -- packages/coding-agent/src/extensions/agent-team-loop` rc=0；`git -C .agents/skills/agentic-task status/diff/log` rc=0；`rg -o` 旧ID/新名计数 rc=0（无输出=0 命中，新名检索为“无输出”）；`Get-FileHash`/`File.ReadAllBytes` rc=0；`env` 读取 rc=0。未执行：任何 pytest/vitest/`mw` 写命令/`npm run check`/build/install/restart/commit。

## 残留与未验证

1. **未运行任何测试**：本卡是静态取证，未执行 `test_advance_phase.py`、Python 决策测试或 TS suite；E5/E6 的行号与语义来自读码，未用运行验证。
2. **未全文读**：`pm/pm-orchestrator.ts`(123514B)、`pm/ui-bridge.ts`(228859B)、`worker/worker-mode.ts`(250973B)、`pm/decision-tool.ts`(89846B) 只按 rg 命中行与相关区段读（明确覆盖范围=命中行+邻近函数）；`packages/multi-workers` Python 侧（decision_points/decision.py/mw.py 全文）不在本卡范围，仅引用 RQ 证据与定位行。**不把本报告当独立全仓审计。**
3. **测试/旧 key 面未盘**：`packages/coding-agent/test/**`、`packages/multi-workers/test_*.py`、`decide_cases/*.json`、`decide_book_template.json` 的旧ID引用（`rg -c` 显示 25 个 Python 文件含旧ID）未逐条分类——属 T01/T05 面；TS 测试文件未查。
4. **bundle 与运行窗口未验证**：未确认本窗是否同时加载了 builtin 源码与全局 bundle（重复注册行为未测）；未验证 `mw build` 后的实际 diff；未重启任何服务或 monitor。
5. **human/H12 缺口未消解**：无“受控人工通道”设计证据，故 AC-036/037/038/039 中依赖“已证授权/资格”的编码保持 blocked；本报告不复用 RQ 结论冒充当前源码审计（RQ14/RQ20 为转引）。
6. **未批准面**：若要触碰 `.claude/scripts`、`core/scripts`、`claude/scripts` 镜像、`dist`、全局 bundle、`.pi/extensions` 或运行期 policy 键接线，须先补 exact path/理由/最小补面并另批；本卡不做，也不以旧ID别名过渡。

## 上下文来源

- 卡与卡源：`.agenticdoc/mw-dp-consolidation/workers/dpc-t02-ts-framework-preflight/task.md`、`.agenticdoc/mw-dp-consolidation/tasks/T02-ts-framework-preflight.md`
- 目标/锁定/已批接口：`.agenticdoc/goal.md`、`.agenticdoc/mw-dp-consolidation/spec.md`（:6-7 最新命名、:26-33 六迁移/19退出映射、:61-63 dp7/dp20 归属、:86 命名修订）、`.agenticdoc/mw-dp-consolidation/design.md`（:134 词表差异、:216 M10 框架衔接、:842 写面批准）、`.agenticdoc/mw-dp-consolidation/design-write-scope.md`（§5 框架特批两文件、§6 禁止面、§7 单writer）
- 计划/依赖：`.agenticdoc/mw-dp-consolidation/plan.md:84`、`.agenticdoc/mw-dp-consolidation/implementation-dag.json`（T02 key/deps/evidence；T25 deps=[T11..T18,T24]）
- 批准：`.agenticdoc/mw-dp-consolidation/evidence/design-approval-20261026.md:15`（第 3 项框架特批面）
- 复用证据：`.agenticdoc/mw-dp-consolidation/evidence/research/design-pm-orchestration-20261026.md`（RQ15）、`evidence/research/design-worker-feasibility-20261026.md`（RQ16）、`evidence/research/design-ui-submission-chain-20261026.md:47-50`（RQ20 page token/role/Origin）、`evidence/research/design-autopilot-effects-20261026.md:9,42,73-84`（RQ14 H12 现状）、`evidence/h13-signoff-gate-link-confirmation.md:19`（旧词表 continue/narrow/revoke 不匹配 dp25 finalize）
- 源码：`packages/coding-agent/src/extensions/{index.ts,agent-team-loop/**}`（E2/E3/E4 所列）、`packages/coding-agent/src/main.ts:530`、`pi-test.sh`、`packages/multi-workers/mw.py:9971-9990,10193,9470,12316`、`packages/multi-workers/mw_common.py:2943,3329-3392`、`packages/multi-workers/decide_signoff.py:83,464,539`、`packages/multi-workers/autopilot/conductor.py:7981-8020`、`.agents/skills/agentic-task/scripts/advance_phase.py`（含既有 diff）
- 既有 diff 只读保存：`git -C .agents/skills/agentic-task diff -- scripts/advance_phase.py scripts/test_advance_phase.py`（本次未落盘副本，仅在本证据记录 stat/行锚点与 hash；如需逐字 diff 须 T25 重新生成）
