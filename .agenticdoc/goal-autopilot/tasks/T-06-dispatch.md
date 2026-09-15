# Task T-06: dispatch.py（typed 注册表 + 派发协议）

## 基本信息
- Stage: 1
- 代码状态: 代码完成（autopilot/dispatch.py）
- 验证状态: 验证通过（test_autopilot_dispatch.py 10 passed，[VERIFY] VC-023 ×7；S1 全量 261 passed 零回归）
- 负责 Agent: PM 窗口（WENBOZHOU-PC4:8420，用户指令直执）
- ac_refs: [AC-021]
- vc_refs: [VC-023]
- pattern_refs: []

## 描述
新文件 `packages/multi-workers/autopilot/dispatch.py`（D-107 / D-111 / D-104）。

**typed 注册表（conductor 侧 Python 表）**：
| type | 工具集 | 说明 |
|------|--------|------|
| roadmap-writer | read/write/edit/find/grep/ls | 写 `_roadmap.md` 提案 |
| phase-writer | coding 级全集（read/write/edit/bash/find/grep/ls） | 补证/生成 artifact |
| verifier | review 级（read/find/grep/ls）+ 强制 read_scope | L2 门禁裁决 |
| reviewer | review 级（read/find/grep/ls） | L3 终局裁决 |
| repair | coding 级全集 | L3 below 后修复 |
- 每类型 → 工具集 → cli/provider 映射；**未注册 type → 拒绝派发**：0 行 + timeline type-rejected 事件（不回退全量工具集，GC-8）
- 该表与 TS 侧 `TOOL_ALLOWLISTS` 新条目构成双侧注册表，**per-type 工具集必须精确相等**（T-17 奇偶测试锁定）

**task.md 模板渲染**（worker 协议增量，向后兼容）：
- frontmatter：`type` / `model` / `origin: conductor`（conductor 派发必带）/ `loop: <loop-id>`（必带）/ `attempt: N` / `read_scope:`（verifier 必带，YAML 列表，项目根相对前缀）
- 写入 `{key}/workers/<task>/task.md`

**队列行写入**：
- 队列 taskKey = `ap-{key}-{stem}`（`ap-` 前缀全局唯一，手动任务不可能撞名）
- `.mw/workers.lock`（O_CREAT|O_EXCL）内写行，复用 `mw_common.serialize_entry`（8 列含 model 空串）
- 读回校验：写后回读行存在且列数正确

## 输入
- 依赖文件: `mw_common.py`（serialize_entry / 锁模式）、`_workers.parallel` 现网格式
- 依赖 Task: T-02（包结构）、T-04（timeline 追加接口，type-rejected 事件）
- AC 约束:
  > AC-021: 在 autopilot 派发路径上，roadmap-writer（含 write，需写 `_roadmap.md` 提案）/ L2 verifier（review 级：read/find/grep/ls）/ L3 review（review 级）/ repair（coding 级）各类型均有显式工具白名单条目；对未注册 type 的派发请求，conductor 拒绝派发（行数 0）并记录时间线，不回退全量工具集
- 设计约束:
  > D-107: 双侧注册表 + 奇偶测试 + worker fail-closed；手动路径 fallback 保留（GC-8 明文）
  > D-111: task 身份 = stem；队列键 ap-{key}-{stem}
  > D-104: origin: conductor 标记（TS 侧跳过在 T-14）

## 预期产出
- `packages/multi-workers/autopilot/dispatch.py`
- `packages/multi-workers/test_autopilot_dispatch.py`：
  - 5 类型查表正确（工具集/cli 映射）
  - 未注册 type → 0 行 + type-rejected 事件（VC-023 conductor 侧）
  - task.md 渲染含 origin/loop/attempt/read_scope 全字段；verifier 缺 read_scope → 拒绝
  - 队列行写入（锁内）+ 读回校验；ap- 前缀命名
- 验证方式: `[VERIFY] VC-023: unknown_rows=0 ...`（conductor 侧部分；奇偶与 worker 侧在 T-14/T-17）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 13:40-14:00 | 读 D-107 注册表 + TS TOOL_ALLOWLISTS 现状 + design §4.1 task.md 模板 + mw_common 锁/序列化 → 实现 dispatch.py：REGISTRY（5 类型：工具集/cli/provider/read_scope 要求）、render_task_md（origin/loop/attempt/read_scope 全字段）、dispatch（task.md 先写→锁内追加队列行→读回校验；未知 type/verifier 缺 scope → 0 行 + timeline type-rejected；成功时 timeline dispatch 事件）+ test_autopilot_dispatch.py 10 用例 | 10 passed；[VERIFY] VC-023 ×7；S1 全量 261 passed 零回归 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 设计取舍备注
- 派发事务非原子是有意设计（D-102）：task.md 先写、队列行后写，中间崩溃留下的孤儿形态由每 tick 和解（同 loop 同 attempt 重插不新耗预算）——与 T-07 find_orphans 闭环
- 成功时也写 timeline dispatch 事件（任务书只要求 type-rejected）：AC-017 要求每次派发有时间线痕迹，单点写入比 conductor 补写更不易遗漏
- timeline 参数可选：dispatch 本体不依赖时间线存活（§9 容错同源）；_scratch owner 派发的 key 字段自动落 '-' 哨兵
- registry_snapshot() 导出供 T-17 奇偶测试与 TS TOOL_ALLOWLISTS 锁定精确相等；cli=pi/provider=''（默认路由）为 5 类型统一选择，claude-cli 仍属手动路径

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
