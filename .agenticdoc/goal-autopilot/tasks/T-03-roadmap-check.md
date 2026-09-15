# Task T-03: roadmap.py + roadmap_check.py（roadmap 解析与校验）

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker-t03-roadmap
- ac_refs: [AC-001]
- vc_refs: [VC-001, VC-002]
- pattern_refs: []

## 描述
新文件 `packages/multi-workers/autopilot/roadmap.py` + `autopilot/roadmap_check.py`。

**roadmap.py**（D-105 schema）：
- 解析 `.agenticdoc/_autopilot/_roadmap.md`：
  - 头部 `generated_at` / `goal_mtime`
  - `## Stage N: <标题>` 节：`goal`（必填非空）、`status`（pending|approved|running|closed|closed-human|halted）、`key-status` 行（`<key>=<running|done|stalled|closed-legacy>` 逗号分隔）、`### Keys` 表（key / role / depends_on）
- 解析失败 → 显式异常（调用方 conductor 跳过 tick + timeline 记 config 事件）
- 提供 stage 枚举、key 依赖图、key-status 读写辅助（conductor 只改 status/key-status 行，`.mw/roadmap.lock` 下原子重写由调用方组合）

**roadmap_check.py**（AC-001 独立校验 CLI）：
- `python autopilot/roadmap_check.py [--project <dir>]` → exit 0/1 + stderr 缺失项
- 校验规则：每 stage 含 ≥1 key 行、goal 非空、依赖声明合法（指向同 stage 内或前序 stage 的 key）、key-status 行的 key 集与 Keys 表一致
- 独立可执行（不依赖 conductor 运行）

## 输入
- 依赖文件: 无外部依赖（纯解析 + 校验）
- 依赖 Task: T-02（包结构已建）
- AC 约束:
  > AC-001: 在 goal 已确立且 autopilot 已启用的项目上，roadmap 生成流程完成后，`_roadmap.md` 中每个 stage 节均包含 key 清单（≥1 个 key）、key 间依赖声明、阶段目标三要素，roadmap 校验脚本对全部 stage 校验 exit 0
- 设计约束:
  > D-105: roadmap schema 全文（含 status 枚举与 key-status 行格式）
  > spec §5 坑点: 管道分隔文件解析 trailing-space/空行必须 filter

## 预期产出
- `packages/multi-workers/autopilot/roadmap.py`
- `packages/multi-workers/autopilot/roadmap_check.py`
- `packages/multi-workers/test_autopilot_roadmap.py`：
  - 三要素齐全样例 exit 0（VC-001）
  - 缺依赖 / goal 为空 / key-status 集不一致样例 → exit 1 且 stderr 含缺失项（VC-001）
  - 单 key stage、跨 stage 依赖（合法）、依赖指向后序 stage（非法）边界
  - 解析器对 status 枚举/key-status 逗号分隔/trailing-space 的容错
- 验证方式: 测试断言输出 `[VERIFY] VC-001: roadmap_check_exit=0` 等行
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10T03:51:12Z | 新增 autopilot/roadmap.py（D-105 解析/校验/依赖图/status+key-status 纯文本更新辅助，不持锁不写盘）+ autopilot/roadmap_check.py（独立校验 CLI，exit 0/1 + stderr 缺失项）+ test_autopilot_roadmap.py（32 测试，含 [VERIFY] VC-001 埋点 18 行）；关键语义：key-status 行缺省视为合法（新提案零状态）、一旦存在要求键集与 Keys 表全等；依赖合法 = 同 stage 或前序 stage（后序非法）；补齐自依赖/环检测与跨 stage 重复 key 报错 | `python -m pytest test_autopilot_roadmap.py -v` → 32 passed；全套件 `python -m pytest -q` → 217 passed, 1 deselected（e2e_real），零回归；CLI 直跑/`-m`/缺文件三种调用路径人工验证 |
| 2 | 2026-09-10 12:40 | PM 验收：亲跑 32 passed 复核；代码走查（schema/枚举/管道容错/纯文本变换 CRLF 保留/无锁设计均合规）；key-status 缺省=合法新提案的语义决策确认采纳（T-11 conductor 激活 stage 时需初始化全部 key 条目，已在 docstring 锁定） | 验收通过 |
### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
