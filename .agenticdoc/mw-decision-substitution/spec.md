# Spec — 用 jev 替换中低风险的人工决策（mw-decision-substitution）

> Key: mw-decision-substitution · 相位: SPEC（定稿 rev2，RQ-1..RQ-5 已回填 + 2026-10-16 用户四条新裁定）· deps: `mw-jev-provider-integration`（DONE，决策底座）

## 0. Goal Alignment（目标对齐）

**goal.md 要点**：在 pi coding agent 之上构建 Agent Team 协作框架，PM Agent 管理多个 Worker 并行开发；`goal.md` 为项目级目标锚点。

**本 key 的贡献**：框架的真实瓶颈不是"agent 不会做"，而是"**agent 停下来等人**"。实测：`mw-jev-provider-integration` 期间 5 条人工消息间隔合计 **≈93.3 分钟**（中位 13.6 min）；worker 运行 **17.4%（42/242）以 `needs-clarification` 结束**；`[CHECKPOINT]` mid/high **60 条**。本 key 把所有"会等人"的位置抽象成 **dp（decision point）**，用一张**由人掌控的配置表**决定哪些 dp 由 jev 直接决策，其余照旧上抛人。

**预期收益（done 时量化）**：
1. 最高频点（`needs-clarification` 17.4%）中"事实可查/已表态复用"两类的人工轮次降到 0；checkpoint（60 条）中可机器判定的部分不再产生人工等待。
2. 人工阻塞墙钟从实测中位 13.6 min 降到决策延迟（B2 实测 ≈5.1s）。
3. 每次自动决策可 review：`decision_id` → 输入指纹 → 答案 → 是否生效 → 结果 → 人是否推翻。
4. 授权完全由配置表决定（唯配置论），人可随时用指令或直接改文件开/关单个 dp，改完即生效无需重启。
5. 失效安全：未开启 / 不可用 / 低置信 / 输入字段缺失 → 一律上抛人，无默认动作。

## 1. 问题陈述（RQ-1 实测）

| 现状事实 | 数据 | 来源 |
| --- | --- | --- |
| 决策点总数 | **24 个**（任务卡 14 + 自查 10） | `evidence/research/spec-decision-inventory-20261016.md` §Q1 |
| 最高频 | `needs-clarification` 42/242 = **17.4%** | `worker/worker-mode.ts:2681` |
| 次高频 | `[CHECKPOINT]` mid/high **60 条** | `pm/pm-orchestrator.ts:1658-1690` |
| 单次最贵 | autopilot 6 类人工门（整 stage 停摆） | `autopilot/gates.py:82` |
| 已接入 jev | **1 个**（DP-1 分诊），本仓 `triage-decisions.jsonl` 不存在 → 实际零调用 | 底座文档 §2.5 |

## 2. 范围

**In scope**
- **dp 注册表**（代码侧）：24 个 dp 各注册一次，所有决策点统一走 `decide_for(dp_id, trigger)`，禁止 ad-hoc 调用。
- **配置表**（项目侧）`.mw/decide-points.json`：唯一的授权来源，人可指令修改或直接改文件，改完即生效。
- 三档默认值：**P2 默认开**，P1/P0 默认关，需显式配置打开。
- `mw decide dp` 指令族：`list / show / on / off / set / refresh / check`。
- 决策档案 `decisions.jsonl`（4 类行 + 哈希链）+ 结果关联（dp1 通道全量）。
- phase 末自动 review 报告 + done 强制签收（复用现成 gate 规则）。
- 卡点建议通道：LLM 可**建议**打开/关闭某 dp，但写配置的永远是人。
- 结构化决策输入（≤2KB）+ 三级脱敏。

**Out of scope**
- shadow 模式（用户选 B：不做；advisory 样本标 `non-blind`，不作门控）。
- 机器自动改配置（降级改为"报告 + 人一条命令"，见 §7.3）。
- dp2+ 的注入与自动结算（MVP 只做 dp1 通道，其余 `settled_by=human`）。
- 与 `auto-decisions.jsonl` 跨文件对账、哈希链 doctor 面化、P1 自动晋升。

## 3. 用户裁定

| 编号 | 内容 |
| --- | --- |
| DS-1 | 三档：`disable` / `enable` / `advance` 作为**默认预设**（P2 / P2 / P2+指定 P1）；实际生效只看配置表。 |
| DS-2 | phase 末自动 review 报告；key 收尾强制签收（`continue`/`narrow`/`revoke` + `promote:`/`demote:`）。 |
| DS-3 | 不替代 pi 破坏性确认（技术上可行，政策推迟）。 |
| DS-4 | 失败/低置信/输入缺失 → 一律上抛人，**禁止默认动作**。 |
| DS-5 | 新起 key，底座保留 DONE。 |
| **DS-6** | **不做 shadow（B 方案）**：advisory 数据被锚定污染，不作晋升依据；晋升由签收人工驱动。 |
| **DS-7** | 回灌通道 = 工具返回值；伪造 user 消息禁止；拦截点 = `tool_call` 钩子；**`context` 钩子禁放同步决策**。 |
| **DS-8** | 实现顺序按频次×成本：dp3 → dp2 → dp1 生效化 → dp5/dp7（需先补结构化输入）。 |
| **DS-9（新）** | **唯配置论**：配置表是唯一授权权威；P2 默认开、P1/P0 默认关；LLM 只能**建议**，开关永远由人执行；机器代码不得内置"绕过配置"的旁路。 |
| **DS-10（新）** | **dp 抽象进代码**：每个 dp 在注册表有唯一项（id/tier/默认值/问题集/输入构造/执行器），调用点只允许引用 dp id。 |
| **DS-11（新）** | **dp 可刷新**：`mw decide dp refresh` 从注册表同步配置表（只增不删、保留已有开关值、孤儿行标 orphaned）；配置改动**无需重启**即生效（按 mtime 重读）。 |
| **DS-12** | **P0 可被配置打开，但要过三道门槛**（用户裁定 "按推荐"）：`mw decide dp on dp8 ... --i-understand-p0` 二次确认；写 `kind=authority-change` 行（`by=human:p0-confirm`）；收尾签收必须列出所有已开启的 P0 项。**不保留不可见代码硬拒**——否则"唯配置论"不成立（表不是真相）。 |
| **DS-13** | **配置表加 `mode` 列**：`auto`（答案生效）/ `suggest`（只落档 + 展示建议，`acted=false`）。默认 `auto`；建议 P1 首次开启先 `suggest` 跑一个 phase 再转 `auto`（用一列代替 shadow，零额外机制）。 |

## 4. dp 注册表（24 点，含落位）

判据（四问全过才能自动）：① 可逆（一次重派内可撤回，无外部副作用）② 机器可判（答案全在文件里）③ 局部（不外溢）④ 无代价承诺（不花钱/不动凭据/不发外部消息/不删他人工作）。

| id | 决策点 | 位置 | 等人物 | 档 | 默认 | 频次证据 |
| --- | --- | --- | --- | --- | --- | --- |
| dp1-dispatch-type | 派发 type/角色/范围 | `pm/ui-bridge.ts:1257` | A+B | P2 | on | 每次派发（已接，零调用） |
| dp2-checkpoint-split | checkpoint 拆/收/直执 | `pm/pm-orchestrator.ts:1658` | B | P2 | on | 60 条 mid/high |
| dp3-worker-clarify | worker 澄清（**三切**见下） | `worker/worker-mode.ts:2681` | B+D | P2 | on | **42/242 = 17.4%** |
| dp4-failure-handling | 失败处置 | PM 回读 | B | P1 | off | 偶发，错一次=一个 phase |
| dp5-test-triage | 测试失败归类 | `AGENTS.md:35` | A | P2 | on | 每 key 收尾（**缺 CI 基线字段**） |
| dp6-qg-verdict | QG 结论处置 | `quality-gate.md:172` | C | P1 | off | 每 QG |
| dp7-gate-failure | 相位门禁失败 | `advance_phase.py:191` | A | P2 | on | 高频但需结构化输出 |
| dp8-scope-change | 变更范围 | `AGENTS.md:25` | A→C | **P0** | off | 偶发 |
| dp9-model-select | 模型/降级选择 | `launcher.py:424` | 已自动 | P2 | on | 已委派先例 |
| dp10-dependency | 依赖升级 | `AGENTS.md:44` | C | P1 | off | lockfile 变更 |
| dp11-credential | 凭据/权限 | `decision_backends.py:137` | C | **P0** | off | 启动期 |
| dp12-destructive | 破坏性操作 | `mw.py:7151`、`runner.ts:237` | C | **P0** | off | fail-closed |
| dp13-commit-release | 提交 / 发布 / 版本号 | `AGENTS.md:40,130` | C+A | **P0** | off | 每次收尾 |
| dp14-rule-conflict | 用户指令 vs 规则 | `AGENTS.md:166` | A→C | **P0** | off | 偶发 |
| dp15-autopilot-gate | 6 类人工门 | `autopilot/gates.py:82` | **C** | **P0** | off | 本仓 0 次（单次最贵） |
| dp16-goal | goal 确立/变更 | `goal.md:39` | C | **P0** | off | 每项目/变更 |
| dp17-spec-lock | spec/AC 锁定 | `requirements.md:380` | C | P1 | off | 每 key |
| dp18-claim | key 抢占冲突 | `pm/ui-bridge.ts:415` | A→C | P1 | off | 偶发 |
| dp19-foreign-write | 越面写预授权 | `worker/worker-mode.ts:2986` | A | **P0** | off | 偶发 |
| dp20-stage-close | stage 闭环 | `conductor.py:1330` | C | **P0** | off | 每 stage |
| dp21-refine | project-refine 升级 | `project-refine.md:64` | C | P2 | on | 偶发 |
| dp22-debug-plan | debug 方案确认 | `debug.md:113` | C | P2 | on | 每 debug |
| dp23-snapshot | memory 快照 | `pm-mind.md:225` | C | P2 | on | 偶发 |
| dp24-pi-trust | pi core 交互 | `core/project-trust.ts:33` | C | **P0** | off | 启动期 |

**落位数**：P2 = 9（dp1/2/3/5/7/9/21/22/23，默认开）；P1 = 5（dp4/6/10/17/18，默认关）；P0 = 10（dp8/11/12/13/14/15/16/19/20/24，默认关）。共 24。

`dp13` 取 **P0**（T-01 裁定）：发布/版本号有不可逆外部副作用，commit 子决策随之并入人工（若将来想放 commit，另立 `dp13b-commit`，不拆分本 id）。

### 4.1 dp3 三切（17.4% 的收益就在这里）

| 子类 | 特征 | 处置 |
| --- | --- | --- |
| **dp3a 事实可查** | 答案在代码/文档/配置里（接口位置、测试命令、字段名） | 自动：jev 读证据自答 → 作为 steer 注入，worker 继续跑 |
| **dp3b 意图需人** | 需要产品/优先级/口径判断 | **必须人**：jev 只做预消化（散乱问题 → 一个带选项的结构化问题），省思考不替代人 |
| **dp3c 已表态复用** | 同类问题在 card/会话/文档里已答过 | 自动：命中并引用原话作为依据，附出处 |

## 5. 配置表与执行面

### 5.1 配置表 `.mw/decide-points.json`（唯一授权来源）

```json
{
  "version": 1,
  "updated_at": "2026-10-16T12:00:00Z",
  "updated_by": "human",
  "points": {
    "dp3-worker-clarify":  { "tier": "P2", "enabled": true,  "mode": "auto", "note": "" },
    "dp4-failure-handling":{ "tier": "P1", "enabled": false, "mode": "auto", "note": "2026-10-20 signoff 关闭" }
  }
}
```

规则（全部可测）：
- **读侧 fail-soft**：文件缺失 → 用注册表默认值（P2 on / P1,P0 off）；行格式坏 → 该 dp 视为 `enabled=false` + doctor warning，**绝不因配置崩溃 worker**；未知 dp（注册表已删）→ 保留行并标 `orphaned`，不静默删除（决策档案引用它）。
- **热生效**：每次决策前按 mtime 重读，人手改文件后无需任何命令、无需重启。
- **CLI**：`mw decide dp list|show|on|off|set|refresh|check`；`set` 白名单字段 `tier|enabled|mode|note`，非法值 exit 2。
- **refresh**：注册表 → 配置表单向同步：新增缺失行（用默认值）、不动已有行、标出 orphaned、输出 added/kept/orphaned 计数；幂等（连跑两次第二次 added=0）。
- **`mode`**：`auto` = 答案直接生效（`acted=true`）；`suggest` = 只落档案 + 展示建议，不执行（`acted=false`，行为等价于未开启但对人可见）；默认 `auto`。
- **P0 门槛（DS-12）**：`dp on <P0-dp>` 必须带 `--i-understand-p0`，否则 exit 2 并列出该 dp 的不可逆后果；成功后面向档案追写 `kind=authority-change`（`by=human:p0-confirm`）；`dp list` 对已开 P0 行打 `P0-ON` 标记。
- 与 `.mw/decide.json` 分工：后者管**传输**（backend/凭据/预算/超时），本文件管**授权**，互不写入。

### 5.2 代码侧 dp 抽象（DS-10）

```python
# packages/multi-workers/decision_points.py（唯一注册表，Python 侧为权威）
DP_REGISTRY = (
    DecisionPoint(id="dp3-worker-clarify", tier="P2", default_enabled=True,
                  questions=..., build_state=..., executor=...),
    ...
)
def decide_for(dp_id: str, trigger: Trigger, project_dir: Path) -> DecisionResult:
    """所有决策点的唯一入口：查注册表 → 查配置表 → 上抛或执行。"""
```
- 调用点只允许 `decide_for(dp_id, ...)`；`mw decide run --dp <id>` 未知 id → exit 2。
- TS 侧只持 dp id 字符串常量；测试断言"TS 常量 ⊆ 注册表 id 集合"（防漂移）。
- 未在注册表的 id 一律拒绝：新增决策点必须先注册（含问题集与输入构造），否则无法调用。

### 5.3 执行面（RQ-2）

| 接触面 | 机制 | 锚点 |
| --- | --- | --- |
| 决策调用 | `ask_decision` 工具，答案作为**工具返回值**回灌 | 全审计 |
| 拦截 | 扩展 `tool_call` 钩子（`{block:true, reason}`），headless 生效 | `agent-session.ts:480` → `agent-loop.ts:636-641` |
| 人手检测 | `input` 事件 `source: interactive/rpc/extension` | `extensions/types.ts:830-831` |
| 禁区 | `context` 钩子（每 LLM 调用必跑） | RQ-2 Q6 |
| worker 侧 | 同一扩展；在 `needs-clarification` 判定链之前插入 | `agent_settled:3824` → exit 2 → `:2681` |

### 5.4 输入契约（RQ-4）

- 结构化 canonical JSON **≤2 000 B**（现状 16 000 B 截断文本）；`state_digest = sha256(_encode_state(state))[:16]`。
- 三级敏感度：**L0** 枚举/计数可外发 · **L1** 摘要/脱敏 · **L2 凭据/用户原话/绝对路径/代码：永不外发**。
- **唯一出口** `pm/triage-client.ts:273`；`decision.py:378-387` 的 `_redact` **当前不覆盖 state**，设计必须在此堵住。
- 必需字段缺失 → TS 侧拒发（`input-incomplete`）+ 上抛人；Python 侧 `DecisionInputError` exit 2。
- 兼容：`isinstance(state, str)` 走旧分支。

## 6. 决策档案与结果关联（RQ-3）

### 6.1 `decisions.jsonl`（append-only，4 类行）

`kind ∈ {decide, override, settle, authority-change}`（后者记录配置表变动）；按 `decision_id` 合并读。

最小字段集：`seq / prev_sha / kind / decision_id / ts / dp / key / task_key / state_digest / questions_version / available / reason / answer / authority / escalated_reason / acted / actual_action / outcome`；可选：`mode / model / transport / attempts / latency_ms / confidence / confidence_source / cost_tokens / note`。

- `decision_id = "<dp>:<trigger_id>"`；`trigger_id` = `task_key`（dp1）/ `task_key#ckpt<N>`（dp2）/ `ts`（无任务上下文）。
- 幂等：同一 `trigger_id` 只允许一行 `kind=decide`；冲突即上抛人。
- 四层 append-only：无 update 路径 / `prev_sha` 哈希链 / `mw_common.acquire_lock` 单写者 / 撤销用负行。
- 与 11 字段传输证据行**并存不升级**。

### 6.2 结果关联（dp1 通道全量）

`decision:` 头行注入 task.md（`pm/ui-bridge.ts:writeDispatchTaskMd:2282`）→ PM 回收终态时追加 `settle` 行。**仅当 `acted=true` 时注入**（`mode=suggest` 不注入，否则 settle 会错记到未生效建议）：

| worker 终态 | outcome |
| --- | --- |
| `done`（exit 0 + 契约段齐） | `ok` |
| 人工 revert / supersedes 重派 | `rollback` |
| `failed`（exit 1） | `rework`（计入返工，**不计推翻率**） |
| exit 3 / `model_exhausted` | `inconclusive`（**不进分母**） |
| `needs-clarification` | 保持 `pending`，转人 |
| `lost` | `pending` + `note=lost` |

无法自动关联（显式登记）：PM 本地决策（`task_key=null`）、长时延（dp10）、复合归因（`note=composite`）、worker 内部 tool_call、跨 key 外溢。

## 7. review、度量与配置演进

### 7.1 phase 末报告（自动）

`<key>/evidence/review/decision-review-<phase>-<yyyymmdd-hhmm>.md`：概览计数 / 判据表（**参考**，不作门控）/ 逐决策清单 / **分歧样例**（每条一段：jev 答 X、人做 Y、理由）/ **候选调整**（机器汇总一行：`suggest: enable dp4` / `suggest: disable dp5, N=12 override=3`）/ 无法关联项。

`N（去重 settle，剔 inconclusive）< 5` 时强制写"数据不足，不结论"。

### 7.2 收尾强制签收（复用现成 gate）

`GATES["done"]` 加两条**现成** check_type（D5 实测：`content_match` 对含 `*` 的路径恒 False，因 `full_path.is_file()`；故签收文件用**固定名** `sign-final.md`）：

```python
("evidence/review/sign-final.md", "glob_has_files", 1, "收尾前必须有决策签收记录"),
("evidence/review/sign-final.md", "content_match", r"^conclusion:\\s*(continue|narrow|revoke)\\s*$",
 "签收必须含机器行 conclusion: continue|narrow|revoke（列 0、单行）"),
```

签收文件可含 `promote:` / `demote:` / `p0-open:` 行；PM 不能写签收文件（`tool_call` 写守卫覆盖 `evidence/review/sign-final.md` 与 `.mw/decide-points.json`），`mw decide dp apply <file>` 在 agent 会话内（`PI_CODING_AGENT`/`AI_AGENT`/`PI_WORKER_TASK`）拒绝执行。

### 7.3 配置演进（人主导，机器零写配置）

- 触发信号：报告里的 `suggest:` 行 + 自动统计（30 条滑窗 `override_rate>0.15`、`rollback_rate>0.10`、连续 3 条 `rework`、24h 内同向 override ≥2）。
- **机器只建议不执行**：超阈值时报告高亮 + doctor 提示 `suggest: disable dpX (override 0.18)`；人执行 `mw decide dp off dpX`（一条命令，写 `kind=authority-change` 行）。
- **卡点建议**（用户裁定 3）：LLM 遇到卡点时可建议"打开某 dp"，**只能建议**；建议进报告/对话，不写配置。
- P1 首次打开建议路径（若 OPEN-2 采纳 `mode`）：`enabled=true, mode=suggest` → 跑满一个 phase 看分歧样例 → 人再转 `auto`。
- 度量：人工轮次/墙钟从 pi 会话 JSONL 离线统计（`session-manager.ts:29-35,474-480`），基线 93.3 min / 中位 13.6 min；三比率（一致率/推翻率/回滚率）仅作报告参考。`confidence_source != api` 时 confidence **不参与门控**。

## 8. 验收标准（AC）

- **AC-001 配置表是唯一权威**：文件缺失 → 默认（P2 on / P1,P0 off）；坏行 → 该 dp 关 + doctor warning 且不崩；改文件后**下一次决策即生效**（无重启）；`disable` 等价于全关且逐字节零扰动。
- **AC-002 默认值与档位**：注册表 24 项与配置表可对账；P2 默认 on、P1/P0 默认关；`tier` 与 `enabled` 冲突时以 `enabled` 为准并有 warning；**P0 开启必须带 `--i-understand-p0`**（无 flag 则 exit 2 且配置不变），成功后档案有 `authority-change(by=human:p0-confirm)` 行，`dp list` 显示 `P0-ON`。
- **AC-003 最高频点闭环**：dp3a/dp3c 由 jev 自答并注入 steer，不再产生人工轮次；dp3b 只预消化为结构化问题。验收：真实 run 事件 + 档案行 + 人工轮次计数对比。
- **AC-004 P2 自动生效**：至少 dp2/dp3/dp9 三点 `enabled=true` 下答案直接生效，留痕 `acted=true` + `actual_action`。
- **AC-005 失效安全**：未开启 / 不可用 / 低置信 / 输入缺失 四条路径全部上抛人（`escalated_reason` 四值各有用例）；grep 证明无默认动作分支。
- **AC-006 决策档案**：4 类行、无 update 路径、`prev_sha` 链可校验、`decision_id` 幂等（同 task_key 重复写即拒）；旧 11 字段行仍可读。
- **AC-007 结果关联**：dp1 通道 6 种终态映射 + `inconclusive` 剔除，真实样本可查；无法关联 5 类显式登记。
- **AC-008 phase 末报告**：自动生成；`N<5` 强制"数据不足"；含分歧样例与 `suggest:` 行；`inconclusive` 不进分母。
- **AC-009 收尾强签收**：缺签收文件时 done 门禁 fail；三种 `conclusion` 各产生 `authority-change` 行；**签收必须列出当前已开启的 P0 项**（漏列则门禁提示）；PM 不能写签收文件、不能在 agent 会话内执行 `dp apply`。
- **AC-010 机器零写配置**：全仓 grep 证明没有代码路径修改 `decide-points.json`（`refresh` 只增缺失行、不动 enabled；`dp on/off/set` 仅人执行）。
- **AC-011 dp 抽象完整性**：每个决策点有唯一注册项；所有调用点走 `decide_for(dp_id)`；TS 常量 ⊆ 注册表；未知 dp id 被拒。
- **AC-012 dp refresh**：从注册表补齐缺失行、保留已有开关值、标 orphaned、幂等（第二次 added=0）；orphaned 行不被删除。
- **AC-013 结构化输入与脱敏**：≤2KB canonical JSON；三级敏感度；L2 字段有测试证明不外发；旧字符串输入兼容。
- **AC-014 不改派发语义**：除已开启 dp 外，jev 开/关下 type/角色/模型完全相同；开启项可回退且留痕。
- **AC-015 `mode` 语义**：`mode=suggest` 时答案落档（`kind=decide`，`acted=false`）且不改变任何执行行为；`dp set <dp> mode=suggest` → `auto` 后下一次决策即生效；建议内容只进报告/回执，不注入 steer。

## 9. 调研结论索引

| RQ | 证据文件 | 关键结论 |
| --- | --- | --- |
| RQ-1 | `spec-decision-inventory-20261016.md`（29.5KB） | 24 点表；NC 17.4%；`auto_gate_mode` 三件套先例 |
| RQ-2 | `spec-pi-interaction-surface-20261016.md`（20.8KB） | `tool_call` 可拦；工具返回值回灌；`context` 禁区 |
| RQ-3 | `spec-authority-audit-model-20261016.md`（26.4KB） | 档案 4 类行；结算映射；gate 只加两条现成规则 |
| RQ-4 | `spec-structured-input-contract-20261016.md`（22KB） | ≤2KB schema；三级脱敏；`_redact` 不覆盖 state |
| RQ-5 | `spec-decision-metrics-20261016.md`（16.3KB） | 会话 JSONL 可测；93.3 min 基线；6 埋点 |

## 10. 风险与回退

| 风险 | 回退 |
| --- | --- |
| 自动决策误判导致返工 | 默认只开 P2（全部可逆）+ 报告 `suggest` + 人一条命令关闭 |
| 人把 P0 打开后出事（若 OPEN-1 取"可开"） | 二次确认 + 强制留痕 + 收尾签收必列；建议 P0 永留 off |
| 配置被手改坏 | fail-soft（该 dp 关 + doctor warning），不崩 worker；`dp check` 预检 |
| 签收被 PM 代签 | 写禁止面 + `dp apply` 拒绝 agent 会话 + 门禁要求文件 |
| 结果关联失真 | 只对 dp1 自动结算，其余 `settled_by=human`；报告标置信 |
| 输入泄露 | 三级脱敏 + 唯一出口 + L2 测试 |
| 配置表与注册表漂移 | `dp refresh` + `dp check` + TS/注册表一致性测试 |

## 11. 遗留（推后项）

shadow（用户已选不做）· P1 自动晋升 · dp2+ 注入与结算 · 与 `auto-decisions.jsonl` 对账 · 哈希链 doctor 面化 · 破坏性确认替换（DS-3）· conductor 13 个派发点挂点 C · dp5/dp7 的结构化输入缺口 · P0 开启后的即时熔断（当前只有报告 `suggest`）。

## 12. 可复用资产（直接继承，不重写）

| 资产 | 位置 | 复用方式 |
| --- | --- | --- |
| 决策客户端与三后端 | `packages/multi-workers/decision.py`（`DecisionClient.decide`）、`decision_backends.py`（B1/B2/B3） | 原样调用；`decide_for` 在其上包一层配置表查表 + 档案落盘 |
| 证据行 11 字段 | `decision.py:121-134`、`_append_evidence:945-961` | 并存不改；新档案行冗余携带同名字段 |
| state 规范化与 digest | `_encode_state:402-417`、`_serialize_state` | 直接复用，保证传输与档案同一指纹（勿另写实现） |
| 脱敏 | `_redact:378-387` | 复用但**需补 state 分支**（现在只覆盖 response） |
| 配置读取/写入协议 | `mw.py:_decide_write_config:772-792`（锁 + tmp + `os.replace`）、`mw_common.acquire_lock:2369-2384` | 配置表写入沿用同一协议 |
| CLI 骨架 | `mw.py:_decide_run:794`、`cmd_decide:953`、`_DECIDE_SET_KEYS:672` | 新 `dp` 子命令沿用参数风格与 exit 码约定（0 成功 / 2 参数非法） |
| TS 调用层 | `pm/triage-client.ts`（`readDecidePolicy:132`、spawn args:169、20s 硬超时） | 改成按 dp id 传参；超时与异常→`available=false` 保留 |
| 派发挂点 | `pm/ui-bridge.ts:planDispatchFrontmatter:1257`（state 组装 `:1429-1436`） | dp1 生效化与 `decision:` 头行注入点 |
| 门禁规则引擎 | `advance_phase.py:GATES:69-95`、`check_gate:191-289`、`content_match:220-227` | 签收门禁只加两条现成规则，不写新 check_type |
| 闸门先例（闸门语义） | `conductor.py:6520-6580`（`auto_gate_mode off/shadow/live`）、`7650-7703`（负行撤销） | "默认关 + 只增行 + 负行撤销" 照搬 |
| 会话度量 | pi 会话 JSONL（`session-manager.ts:29-35,474-480`） | 人工轮次/墙钟离线统计，不改代码 |
| 坑点库 | `.agenticdoc/_pitfalls.md` P-041..049 | P-046（写面守卫裸斜杠）、P-047（pm-state 不可整文件重写）、P-048（worker_file 路径）直接适用 |

## 13. 需规避坑点（调研实测，非推测）

| 坑 | 后果 | 规避 |
| --- | --- | --- |
| **pi 无逐工具确认门，headless UI fail-closed** | 用 `ui.confirm` 做决策入口在生产（print/rpc）环境下恒为 false，静默失败 | 只走 `tool_call` 钩子 + 工具返回值；禁止依赖 UI 对话框 |
| **`context` 钩子每次 LLM 调用都跑** | 在钩子里做决策会多倍放大延迟/花费，且可能递归 | 同步决策永不挂 `context`；只在 `ask_decision` 工具 / 门控后的 `tool_call` / PM 派发点三处 |
| **伪造 user 消息** | session 条目不留 source，污染"人已表态"检测，事后无法分辨 | 答案只从**工具返回值**回灌；系统注入仅限长期政策 |
| **`_redact` 不覆盖 state** | 代码片段/绝对路径/凭据可能已随 state 外发 | 唯一出口前强制三层脱敏；L2 字段有负向测试 |
| **行号会漂移**（已发生：`ui-bridge.ts:241-247` → 真是 `:1429-1436`） | 文档/spec 引用失效，后来者按错位置改代码 | 锚点写"函数名 + 行号"，设计阶段前复核一次；改动后同步 |
| **`runner.error_kind` / rollback 字段不存在** | dp5/dp10 的"现成输入"是假设，照写会拿不到数据 | 先在 RQ-4 表里标 `不存在`，要求的字段进设计任务而不是假设可得 |
| **配置表被手改坏** | worker 崩溃或全项目静默停止决策 | 读侧 fail-soft（坏行→关 + doctor warn），禁止因配置异常抛到 worker 主链 |
| **PM 代签 / 自己开权限** | 授权体系自证自用，等于无授权 | 签收文件进写禁止面；`dp apply` 在 agent 会话内拒执行；机器零写配置（AC-010） |
| **锚定污染（shadow 为何被否）** | PM 看到建议必然趋同，一致率虚高→用假数据晋升 | 不拿 advisory 数据做门控；要观察期就用 `mode=suggest`（人明知是观察）| 
| **一次性把 P1 全开** | 一类点失败拖垮整个档位 | 按 dp 粒度开关；P1 首次开启建议 `suggest` 跑一个 phase |
| **多个 worker 同写一份配置/档案** | 行覆盖、seq 重复、哈希链断裂 | 单写者 + `acquire_lock`；档案只 append（无 update 路径） |
| **dp 注册表与 TS 常量漂移** | TS 传了注册表不存在的 id → 静默降级为“无人决策” | 未知 id exit 2（大声失败）；CI 测试断言 TS 常量 ⊆ 注册表 |
| **Windows/PS 环境** | 中文输出 GBK 崩、`&&` 不支持 | 输出落盘再读；显式 `encoding="utf-8"`；不写 `&&` |
## 14. 增补 AC（2026-10-21 第二轮，用户裁定 A + 三条新需求）

### AC-016 per-dp 策略旋钮（用户裁定 A）

`.mw/decide-points.json` 的每一行除 `tier/enabled/mode/note` 外，可再覆盖三个策略项：

| 键 | 类型 | 合法域 | 缺省（内置常量即当前值） |
| --- | --- | --- | --- |
| `min_confidence` | number | `0 <= x <= 1` | dp3 = 0.7（`DP3_MIN_CONFIDENCE`）、dp1 = 0.7、dp2 = 0.7 |
| `max_questions` | integer | `1 <= n <= 8` | 全局 `decide.json.max_questions`（8） |
| `timeout_s` | integer | `1 <= n <= 300` | 全局 `decide.json.timeout_s`（20） |

- 生效值 = per-dp 覆盖 > 全局 `decide.json` > 内置常量；解析顺序在 TS 与 Python 必须逐字一致（同一份文件、同一套缺省），由 parity 测试锁死。
- 非法值 fail-soft：回落到下一层并记 `doctor` warn，**不得**抛到 worker 主链（继承 AC-013 的 fail-soft 语义）。
- `mw decide dp check` / `dp show` 必须打印每行的**生效值**（不是原始值），让"我配了但没生效"当场可见。
- 档案行必须回显本次决策用到的 `policy`（`min_confidence`/`max_questions`/`timeout_s` 的生效值），事后能复原"为什么它被 escalate"。
- 明确不做：per-dp `transport`（与唯一传输决策 FIX-L/N 冲突）、per-dp `model`（会打穿签收门禁的 engine 三元组），两者仍全局。

### AC-017 上下文正确传入 decide model

`state` 除结构化事实外，可携带一个 `context` 对象，把工程环境里"模型判断需要、但推导不出来"的文本传进去：

| 槽位 | 内容 | 单槽上限 | 生产者 |
| --- | --- | --- | --- |
| `context.task_excerpt` | 派发卡 `上下文`/`要求` 的摘录 | 1200 字符 | dp1 |
| `context.change_summary` | `git diff --stat` 或改动文件清单（相对路径 + 行数） | 800 字符 | dp2 / dp3 |
| `context.artifact_status` | 交付物存在性清单 `[{path, exists, bytes?}]` | 24 条 | dp2 |
| `context.error_excerpt` | 门禁/测试失败的尾部输出 | 1500 字符 | dp4 / dp6 / dp7 |
| `context.candidate_snippets` | dp3 本地候选中命中行的原文 `[{id, path, line, text}]` | 5 条 × 200 字符 | dp3 |

- 每个槽位必须带 `source`（`path:line` 或命令），且进 `state_digest`；无来源的上下文不得外发。
- 截断策略：单槽超限取**头 60% + 尾 40%**并插入 `…truncated N chars…`；`context` 总长 ≤ 4000 字符，超出按槽位优先级（error > candidate > change > task > artifact）逐个砍到下限。
- 脱敏：沿用 `decision._redact` 三层（凭据/绝对路径/超长串），`candidate_snippets` 额外做"命中行首个 200 字符"裁剪。
- `context` 是**可选**的：缺了不判 `input-incomplete`；但 `dp verify` 要报告每个 dp"当前会填哪些槽位、哪些为空"，让空洞可见。
- 传输仍只有 `{model,state,questions}` 三键（`context` 在 `state` 内），不新增线上字段。

### AC-018 决策本（decision book）书写规范

当 `ask_decision` 判 `input-incomplete`、或该 dp 尚未接线、或 PM 需要一次可复核的离线决策时，调用方必须写一份**决策本**，而不是在对话里口头描述：

- 位置：`.agenticdoc/<key>/evidence/books/<dp-id>-<slug>.json`（PM 用 `.agenticdoc/_autopilot/books/`）。
- 格式：`{schema_version: 2, decision_point, state, context?, notes}`；`state` 必须含该 dp 的**全部** `required_state_fields`。
- 硬规则：
  1. 每个数值/枚举必须来自真实证据，并在 `notes.evidence` 里给 `path:line` 或命令原文；
  2. 禁止占位符（`TBD`/`TODO`/`xxx`/空串）；
  3. `questions` 不允许在决策本里覆盖（题面归注册表）；
  4. 一本一决策，不得把多个 dp 塞进一个文件；
  5. 决策本只写"输入"，不写"我预期的答案"（避免污染）。
- worker 与 PM 的分工：worker 只能在自己的 key 目录下写；PM 负责 dp2/dp6 类跨任务决策；两者都必须先过 AC-019 的验收才能提交。

### AC-019 决策本验收（book check）

新增 `mw decide book check <file> [--json]`，逐项给 pass/fail 与定位，退出码 0（全过）/ 2（有失败）：

| 检查 | 失败码 |
| --- | --- |
| JSON 可解析、`schema_version == 2`、`decision_point` 存在于注册表 | `book-schema` |
| `required_state_fields` 逐条存在且类型匹配（object/string/integer/number/boolean/array） | `book-state` |
| 占位符扫描、空串、`null` 必填 | `book-placeholder` |
| `context` 槽位合法（未知槽位、超长、无 `source`） | `book-context` |
| 证据引用 `path:line` 可解析（文件存在、行号 ≤ 行数） | `book-evidence` |
| token/字节预算（复用 `_estimate_tokens` 与 AC-005 的闸） | `book-budget` |
| 凭据/PII 正则扫描（复用 `_redact` 的检测面） | `book-secret` |

`mw decide ask/run` 新增 `--book <file>`：先跑同一套检查，任一失败**拒绝发送**（零 HTTP），并在 stderr 打印失败表。检查器只报告，不自动修（禁止静默补字段）。

### AC-020 三条需求的可验证面

- per-dp 旋钮：改 `.mw/decide-points.json` 一行即改变门控结果，无需重建 bundle；有 TS↔Python parity 测试。
- 上下文：给定一份真实工程快照，`dp3` 的请求体里能看到 `candidate_snippets` 的原文与 `source`；关掉上下文后请求仍合法。
- 决策本：给一份缺字段的决策本，`book check` 必须指出缺哪条并 exit 2；给一份合法的，`--book` 能真发到 jev 并落档案（`book_path` + sha256）。
### AC-021 决策本由配置生成，不由人猜（2026-10-21 修订，用户澄清）

澄清的契约：**dp 的要求在 `decide_registry.json` 里，决策本是 `decide` 接口的输入，PM/worker 的职责是"按配置把每个字段的内容填出来"，而不是自己决定有哪些字段。**

- `mw decide book new <dp-id> [--out FILE]`：从 `decide_registry.json` 该 dp 的 `required_state_fields` 生成骨架——键集合与顺序完全由配置决定，每个键带 `type` 与 `description`（来自 `STATE_FIELD_DESCRIPTIONS`）作为填写提示，`questions_version` 预填为注册表值，值一律置为**类型占位符**（`"<string: …>"`/`0`/`[]`/`false`），并在 `notes.evidence` 生成同名待填条目。
- 校验的键集合是**封闭**的：`book check` 同时判"缺必填"与"多出注册表没有的键"（两个失败方向）。state 里除 `required_state_fields` 与 AC-017 的 `context` 外不得有其它键。
- `context` 槽位同样由配置侧声明（`CONTEXT_SLOTS` + 该 dp 的 `context_slots` 白名单），生成骨架时只为该 dp 允许的槽位留位。
- 因此"PM/worker 会不会写错"从"靠人记规范"变成"结构化约束 + 生成器 + 验收器"三件套：配置定义字段 → 生成器给骨架 → 验收器判缺失/多余/类型/证据。
- 契约漂移必须可见：`decide_registry.json` 变更后，骨架与校验立即跟随（同一份 `registry_snapshot()`），TS 侧的字段清单也由配置生成（见 AC-022）。

### AC-022 TS 侧字段清单由配置生成

三个已接线 dp 的 state 目前由 TS 硬编码键名（`ui-bridge.ts`/`pm-orchestrator.ts`/`worker-mode.ts`）。改为：

- 新增生成脚本 `packages/multi-workers/scripts/gen_decide_registry_ts.py`，从 `registry_snapshot()` 产出
  `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`（导出 `DECIDE_REGISTRY`：
  每 dp 的 `requiredStateFields` 名/类型、`questionsVersion`、`contextSlots`）。
- TS 生产者用它做**写入前自检**：构造完 state 后断言"键集合 == 配置要求"，缺/多都在开发期炸（不是运行期静默）。
- 漂移测试：Python 侧重跑生成器并与磁盘文件逐字节比较（与 `decide_registry.json` 同款锁）；TS 侧 `tsgo` 保证类型。
- 生成物必须带"do not edit"头，且允许随配置一起提交（与 `models.generated.ts` 同约定）。

---

## 15. 修订 2（2026-10-21 用户裁定）：签收交给决策模型 + worker 改名

> 触发：用户提出"签收把流程卡住了，本意是减少跟人的交互，任务做完后人 review 就行"。
> 裁定 D：**让 decide 模型去签收**，人可用 `mw decide sign --auto|--disable` 控制，缺省 `auto`。

### 15.1 验收标准

| 编号 | 验收标准 | 判据 |
| --- | --- | --- |
| AC-023 | 签收模式是配置项：`.mw/decide.json` 新增 `signoff`，取值 `auto`\|`disable`，缺省 `auto`；`mw decide sign --auto` / `--disable` 持久化该值 | 改后文件里出现该键；`mw decide show --json` 回显；非法值 `mw decide sign` exit 2 且不写文件 |
| AC-024 | `auto` 的判定顺序：`signoff=disable` → 不签；否则 decide 已配置 **且** `dp25-signoff-conclusion` enabled → **jev 出结论**；否则 → **agent LLM 推断**（`--conclusion` 传入）；两条路径都落 `signed_via`（`auto-decide` / `auto-llm`） | 三种模式下各跑一次，检查 `sign-final.md` 的 `signed_via` 与 `authority-change` 行 `by=signoff:auto-*` |
| AC-025 | `signoff=disable` 时 `mw decide sign` 不写文件（打印已禁用），`done` 门禁**不要求** `sign-final.md`，输出 note 后通过 | `check_gate(key,"done")` 在 disable 下返回 True |
| AC-026 | 自动签收允许在 agent 会话内执行：`signed_via=auto-decide\|auto-llm` 绕过 `write_signoff` 的 agent 会话拒绝；人签路径（`cli`/`tui`）拒绝逻辑保持不变 | agent 会话内跑 `mw decide sign` 成功；`--human-confirmed` 语义不变 |
| AC-027 | 新增注册决策点 `dp25-signoff-conclusion`（P1 / default auto / executor unwired）：state 由 `decide_signoff.collect()` 的事实**确定性组装**，question 为 choice `continue\|narrow\|revoke`；置信不足或不可用 → 回落 LLM 路径并记 `decide_fallback: <reason>` | 注册表 25 项；`dp check`/`dp verify` 覆盖 dp25；`sign-final.md` 有 `decide_fallback` 行 |
| AC-028 | worker 类型 `decision` 改名 `decide_prepare`：类型/角色/词表/工具白名单/镜像/文档一致改名（不留别名）；角色模型独立可配（`.mw/dispatch.yml` `models.decide_prepare`），可被 `dispatch_worker.model` 覆盖 | `DISPATCH_ROLES` 含 `decide_prepare` 且不含 `decision`；`mw model set decide_prepare <model>` 生效；派发一次 `type: decide_prepare` 卡片被正确路由 |

### 15.2 明确不做

- 不再要求人在 agent 会话外签收（人签能力保留，非强制）。
- 不做 `signoff` 的第三态（如 `manual`）：`cli`/`tui` 人签是**显式传 `--conclusion`** 时的自然行为。
- 不引入新的传输或模型：签收决策点复用唯一传输 `timi-decisions` / `jev-latest`。
