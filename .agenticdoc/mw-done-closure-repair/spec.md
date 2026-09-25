# Spec: mw-done-closure-repair

> Key: mw-done-closure-repair
> 创建时间: 2026-09-24T16:30:00+08:00
> 状态: confirmed（AC 已锁定）

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（存量项目，无 status 行但三段有真内容，视为已确立）

- 对齐：服务于 goal「mw 后台服务（Python）：LLM 代理 + 任务调度器」中 autopilot conductor 的端到端可用性——verify→done 边界不再因结案词表缺口锁死，PM Agent 管理的 key 可无人工介入闭环，支撑「多个 Worker Agent 并行开发同一项目」的交付终点。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不修改 pi 核心——源码改动限于 packages/multi-workers/（autopilot/ 源码 + 包根测试文件，仓内惯例），另加仓库根 .gitignore 一行 marker 忽略项
  - GC-2: 文件锁并发控制——marker 写/读/删在 `.mw/key-{key}.lock` 下，写入用临时文件 + `os.replace` 原子改名
  - GC-3: Worker 工具白名单按任务类型——reviewer 维持只读（read/find/grep/ls），不为其加 write
  - GC-4: pm-state.md 只经 `advance_phase.py` 语义——本 key 不新增 pm-state 写路径（`_append_pass_line` 现状不动）
- 冲突：无
- 预期收益：autopilot 模式下 verify→done 无人工介入闭环。量化判定（done 时在 achieved.md 对照）：FeatureMigrator Stage 2/3 的 9 个待跑 key 每 key 的人工收口次数从 ≥1 降为 0（同类缺口）；标准模板安装工程 4/4 命中率的缺口消除（AC-001/AC-008 机器判定）。

## §1 功能概述

### 1.1 目标
修复 autopilot conductor 的 done 收口契约缺口：工程 done 门禁要求的结案文书词表（标准模板：`系统行为变化`/`遗留`）与 L3 输出词表（`## Achieved`）不一致，导致 verify→done 恒 gate-blocked、key 连续 5 次失败后 stalled、除人工介入无出路。修复 = 两处改动：
1. **失败原文回流 L3 回路**：advance verify→done 失败（class=gate-blocked，失败行涉及 achieved.md）时，把门禁失败原文逐行附入下一轮 L3 dispatch 的 prompt（词表唯一来源 = 失败原文，框架零硬编码）；
2. **内容寻址坏稿声明（marker）**：事务在 per-key 锁下写 `.mw-achieved-baddraft.json`（绑定被拒稿 sha256 + 失败行）；覆盖 achieved.md 需三条件全真（marker 存在 ∧ 哈希一致 ∧ 失败行涉及 achieved.md），否则维持现状不覆盖。

### 1.2 技术栈 / 语言
Python（`packages/multi-workers/autopilot/`，pytest 测试）。

### 1.3 核心用户场景
1. 场景 A（自动闭环）：autopilot 推 key 至 verify→done，工程 done 门禁词表与 L3 输出不一致 → 第一次 advance 失败 → 失败原文驱动 l3-a{N+1} 重写结案节 → 事务覆盖坏稿 → advance exit=0 → done，全程零人工。
2. 场景 B（人工修稿保护）：advance 失败后人/PM 按工程词表重写 achieved.md → 下 tick marker 哈希失配 → 事务不覆盖 → advance 直接通过。
3. 场景 C（预算兜底）：L3 连续预算轮次仍不合规 → stalled（人工兜底，现状语义不变）。
4. 场景 D（非结案类失败）：gate 失败行不含 achieved.md（如 evidence 缺失无生产者）→ 不烧 L3 轮，走既有 stalled 路径。

### 1.4 范围说明（不做什么）
- 不包含：`advance_phase.py --check` / `check_gate` 只读 CLI 入口（R2 内核，升级路径，归 R3 产品面）
- 不包含：新 dispatch 类型 / 新 loop 家族（closure-repair worker 方案已否决，见 research A3）
- 不包含：§42.3 归档面缺口（L3 两节写进 report.md、output.md 只有模板时误判 below）——另立小 key
- 不包含：pm-state PASS / QG report 转写路径改动（D-108 现状不动）
- 不包含：stalled gate 审批消费语义（`4e874f5cc` 已交付，本 key 仅回归锁定）
- 不包含：`_l3_prompt` 首轮预防性注入工程规则（无只读入口可读，属 R3 契约面）

## §2 业务约束

### 2.1 平台 / 环境
`packages/multi-workers/autopilot/`（conductor.py 为主）；被驱动工程 = 任意安装 AgenticTask 标准模板的项目；Windows/Linux 双环境（pytest 现有夹具规范）。

### 2.2 并发与一致性
- marker 写/读/删全部在 `.mw/key-{key}.lock` 内（`acquire_conductor_lock` 协议）；写入临时文件 + `os.replace`（P-003）
- timeline 事件语义不变（`advance`/`config`/`dispatch`/`stalled`/`gate-*`）
- marker 失效方向恒为"不覆盖"（哈希失配/缺失/崩溃窗口），对校验时刻已存在的稿件永不误覆盖（校验与 os.replace 之间的毫秒级外部并发写窗除外——与现状同型的既有竞态，接受风险）

### 2.3 安全约束
- 工程词表字面量不进框架代码（`packages/multi-workers/` 源码 rg 扫描 0 命中；唯一来源 = advance 失败原文）
- 判定不代写：QG report / pm-state PASS 转写路径不动；achieved.md 内容 = L3 `## Achieved` 节逐字转写（零内容加工）
- reprompt prompt 不得指示 reviewer 修改任何判定（PASS/FAIL/VC 行）

### 2.4 集成依赖
- `advance.advance` 子进程 stderr 的 gate 失败行（`NO MATCH:`/`MISSING:`/`TOO SMALL:` 前缀，模板 `check_gate` 产出）
- `_classify_advance_failure` 的 gate-blocked 分类（现成）
- loop/attempt frontmatter 预算机制（`state.py`，现成）

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-25T11:16:40+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在安装标准 AgenticTask 模板（done 门禁要求 achieved.md 含字面量「系统行为变化」「遗留」）的 fixture 工程中，conductor 以 autopilot 循环驱动单 key 至 L3 meets 后，该 key 达到 phase=DONE，且全程 stalled gate 文件创建数为 0、gate-answered 事件数为 0 |
| AC-002 | 在 AC-001 场景中，gate 失败原文至少 1 行（含缺失字面量）逐字出现在随后派发的 L3 reprompt 任务 prompt 中，且该 prompt 全文 = reprompt 固定基底（既有 `_l3_prompt` + closure.py 固定指示常量，均框架自有文案、不含工程词表字面量、受 VC-003 扫描约束）+ 从 advance stderr 提取的失败行逐字列表，无其他内容；`rg` 扫描 `packages/multi-workers/autopilot/` 源码目录对「系统行为变化」「行为影响」「未了事项」命中 0 次 [REVISED @ 2026-09-25 二次：评审 MAJOR-1——原二组分等式与 D-002 三组分实现矛盾，收敛为"固定基底+失败行"两分式，指示文案钉为模块常量（dcr-review 发现 1，方案 b）] |
| AC-003 | 在 achieved.md 存在且 ≥200B 的条件下，仅当 marker 文件存在、`marker.sha256 == sha256(当前 achieved.md)`、且 marker 记录的 gate 失败行（marker.failures）含 "achieved.md" 三条件全真时事务覆盖该文件；任一条件为假时 achieved.md 字节内容不变 [REVISED @ 2026-09-25："本次 gate 失败行"无时间锚（step-2 判定先于 advance），钉为 marker 记录的失败行（dcr-review NIT-6）] |
| AC-004 | 在 advance verify→done 因 achieved.md 词表 gate-blocked 失败后，外部按工程词表重写 achieved.md 的条件下，事务此后不覆盖该稿（字节不变）且 reprompt 轮收敛后 verify→done advance exit=0 [REVISED @ 2026-09-25："下一 tick"与 in-flight 现实不符——失败当 tick 即派 reprompt，后续 tick 被守卫拦截（dcr-review NIT-8）] |
| AC-005 | 在 L3 reprompt 连续 round_budget + resume_credits 轮仍不合规的条件下，key 标记 stalled，且 l3 家族 dispatch 总数 ≤ l3_limit（含首轮，不随 tick 增长） [REVISED @ 2026-09-25：上界收紧——派发前 used < l3_limit 检查使总dispatch恰好以 attempt=l3_limit 封顶（dcr-review NIT-9）] |
| AC-006 | 在 gate 失败行全部不含 "achieved.md" 的条件下，l3 家族 dispatch 计数不变（无 reprompt），key 走既有 stalled 路径（连续 advance_stall_ticks 次失败后 mark_stalled） |
| AC-007 | 在 l3 reprompt worker 行状态为 in-flight 的条件下，该 key 在后续 tick 中 advance 事件新增数为 0 |
| AC-008 | 在第二套合成工程词表（fixture done 门禁要求字面量「行为影响」与「未了事项」，与标准模板不同且在 `packages/multi-workers/autopilot/` 源码目录零命中）的条件下，同样 0 stalled gate、0 gate-answered、phase=DONE [REVISED @ 2026-09-25：合成词表由 Impact/Follow-ups 改为框架源码零命中字面量，避免自然词项假阳性] |
| AC-009 | 在 30 个 tick 的混合场景中，同一 gate id 的 gate-answered 事件至多出现 1 次，且 gates 目录文件数增量 ≤ 活跃 key 数 |
| AC-010 | 在事务覆盖 achieved.md 后，其字节内容与源 l3-a{N}/output.md 的 `## Achieved` 节逐字一致（允许至多 1 个尾部换行差异） |
| AC-011 | 在事务覆盖成功或 verify→done advance exit=0 后，marker 文件不存在；同一被拒内容重复 gate 失败时 marker 保持单文件（内容原地更新而非新增） |

## §4 风险与未决项

- 风险：L3 reviewer 对失败原文的遵循度是 LLM 行为——由 l3 预算封顶 + stalled 兜底（AC-005），失败退化路径不劣于现状
- 风险：advance stderr 失败行格式随模板演进漂移——分类失败时退化为现状（不 reprompt，stalled 兜底），不比现状差
- 风险：marker sidecar 文件出现在 key 目录（`.agenticdoc/<key>/.mw-achieved-baddraft.json`，点前缀；现有 Python/TS 扫描面零命中，见 research design-marker-mechanics F-10）。git 可见性勘误（2026-09-25）：`.gitignore` 仅排除 `.agenticdoc/**/workers/`、`_workers*`、`.mw/`、`*.lock` 运行时子集，marker 路径未被忽略——plan 需显式决策加 `.gitignore` 忽略行或接受 untracked 噪音
- 待确认：无（设计已与用户 3 轮收敛并确认 marker 方案）
- 已决：失败行"涉及 achieved.md"的判定 = 失败行含字面量 `achieved.md`（通用，不引词表）

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产
- `_md_section` / `_done_transaction` 逐字转写管线（conductor.py）
- `_classify_advance_failure` 的 gate-blocked 分类（现成，无需扩展）
- loop/attempt frontmatter 预算机制（state.py）与 l3 前缀 in-flight 守卫（`_verify_loop`，现成）
- per-key 锁协议（`acquire_conductor_lock(key-{key})` + `mw_common.release_lock`，`_append_pass_line` 示范）
- 既有 pytest 夹具（`test_autopilot_conductor_exec.py` 的 done-transaction / meets 用例族，AC 测试可直接扩展）
- timeline `advance`/`config` 事件与 `_advance_failure_streak` streak 语义（dispatch 事件打断 streak）

### 需规避坑点
- P-009（失败只记一行自由文本、无预算无门禁 = 无界空转）：本 key 即补齐 done-blocked 的预算化闭环；reprompt 必须受 l3 预算封顶（AC-005）
- P-003（`open(p, "w")` 先截断后求值）：marker 写入用临时文件 + `os.replace` 原子改名
- P-001（PowerShell 文本管道损坏 UTF-8/BOM）：所有 .md 与 marker 写入走 write 工具或 Python utf-8 路径，不经 PowerShell 文本管道
- gate 重放/洪泛（2026-09-24 FeatureMigrator 事故，`4e874f5cc` 修复）：marker 与 reprompt 均不得引入新的每 tick 文件增长（AC-009/AC-011）
- timeline 有界尾部（400 事件/512KiB）不可作为守卫判定依据——marker 落盘的动机（research A3）
