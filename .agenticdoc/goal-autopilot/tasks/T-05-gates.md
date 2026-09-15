# Task T-05: gates.py（人工门禁文件协议）

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker-t05-gates
- ac_refs: [AC-003, AC-024]
- vc_refs: [VC-005, VC-026]
- pattern_refs: []

## 描述
新文件 `packages/multi-workers/autopilot/gates.py`（D-105）。

- 目录：`.agenticdoc/_autopilot/gates/gate-{seq:04d}.md`；目录扫描即队列
- **seq 分配**：conductor 是唯一 gate 创建者（TS 只回答）；gates.lock 下 seq = max(现存 gate id)+1；重启重扫目录取 max，无并发冲突
- frontmatter 全字段：`id / kind(stage-confirm|stage-close|stalled|budget-exhausted|goal-change) / stage / key / created_at / created_by(conductor) / question / context_refs[] / status(pending|approved|rejected) / answered_at / answered_by(窗口 claimId) / note`
- 正文 = 人可读问题 + 上下文摘要
- 接口：
  - `create(kind, question, context_refs, stage=None, key=None)` → gate 文件（在调用方传入的锁策略下）
  - `parse(path)` → 结构化对象（frontmatter 损坏 → 显式异常，调用方 skip + timeline config 事件）
  - `enumerate()` → 全部 gate（含 pending 过滤辅助）
  - 回答写入由 TS 侧 `/autopilot gate` 承担（T-15），Python 侧只读消费
- 人工可手改文件回答（review B5 语义：回答以文件为准）

## 输入
- 依赖文件: 无
- 依赖 Task: T-02（包结构）
- AC 约束:
  > AC-003: 在 stage 内全部 key 到达终态（done 或人工裁决关闭）的条件下，conductor 在 1 个轮询间隔内生成 stage 闭环 dossier（含各 key L3 裁决与证据引用）并创建下一 stage 人工门禁文件，且在回答前对下一 stage 的派发行数为 0
  > AC-024: 在 stage 门禁被 reject 的条件下，roadmap-writer 重新提案一次（计入其回合预算）；再次 reject 后 conductor 停止自动提案并等待人工直接编辑 `_roadmap.md`；在 stalled 门禁被 reject 的条件下，该 key 按遗留问题路径关闭（achieved.md 草稿保留），不阻塞 stage 闭环
- 设计约束:
  > D-105: gate 文件 schema 全文（5 kind / 12 frontmatter 字段；PM 勘误 2026-09-10：原写 13 为计数笔误，§4.1 枚举清单实为 12，worker 按枚举清单实现并经 PM 验收确认）

## 预期产出
- `packages/multi-workers/autopilot/gates.py`
- `packages/multi-workers/test_autopilot_gates.py`：
  - create 分配 seq = max+1（含重启重扫语义：预置 gate-0003 后新建 → 0004）
  - parse round-trip 全字段（含 context_refs 列表）
  - enumerate + pending 过滤
  - 损坏 frontmatter → 显式异常（不静默吞）
  - 5 kind 全枚举渲染
- 验证方式: `[VERIFY]` 行输出；VC-005/VC-026 的流程断言在 T-11 conductor 测试，本 task 验协议层
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 11:41 | 新增 `autopilot/gates.py`（create/parse/enumerate/pending_gates/Gate/GateFormatError；YAML 子集 frontmatter 解析，原子写 + LF）+ `test_autopilot_gates.py`；`python -m pytest test_autopilot_gates.py -v` 38 passed；[VERIFY] VC-005 ×7 / VC-026 ×3 | 协议层全绿。注：任务书/设计标题写「13 frontmatter 字段」但 D-105 §4.1 枚举清单为 12 字段（id/kind/stage/key/created_at/created_by/question/context_refs/status/answered_at/answered_by/note），按枚举清单实现 12 并由测试锁定 |
| 2 | 2026-09-10 12:05 | PM 验收：亲跑 test_autopilot_gates.py 38 passed + [VERIFY] 行 ×10 复核；git status 无散落文件；代码走查（seq 重扫语义/无锁设计/GateFormatError 显式异常/id↔文件名一致性检查/ISO 时间戳校验含 Z 形式均符合任务书）；裁决字段疑点：design §4.1 枚举 12 字段为权威，任务书 13 为 PM 计数笔误已勘正 | 验收通过；T-11/T-15 依赖的 schema 锁定为 12 字段 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | 测试代码错误（索引硬编码） | test_autopilot_gates.py:_preset_gate | duplicate frontmatter field 'status' (line 12)（helpers 按行号替换 status 行，撞上 context_refs 第二项；改为按前缀替换后全绿）| 已修复 |

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
