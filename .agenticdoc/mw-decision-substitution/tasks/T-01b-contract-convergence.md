# T-01b 契约收敛：escalated_reason 单一词表 + 步 8 语义 + 重复触发

- key: mw-decision-substitution · type: coding · phase EXECUTE
- timeout: 30
- 依据: T-01 残留 1/3/5/6 的 PM 裁定（design D-029..D-033）

## 上下文

T-01 落地了 `decision_points.py`（56 测试绿），T-03 落地了 `decide_archive.py`（47 测试绿）。二者对 `escalated_reason` 用了两套词表，`decision_points` 用映射表桥接（`disabled→unavailable`、`input-incomplete→input-invalid`）。该映射会**隐藏真实原因**，且步 8 的"`confidence_source != api` 一律上抛"会让 P2 自动决策**永远不生效**（B2 后端返回的就是 `model-self-report`）。

## 要求

1. **统一词表**（以 `decision_points.ESCALATED_REASONS` 为准）：
   `{disabled, unavailable, input-incomplete, input-oversize, low-confidence, over-authority, p0}`。
   把 `decide_archive._ESCALATED_REASONS` 扩成同一集合；保留 `input-invalid` 仅为读取旧行兼容（接受但不再产出），并在注释里写明。
2. 删除 `decision_points._ARCHIVE_ESCALATED_REASONS` 映射表，档案写入直接透传原值。
3. **步 8 语义改为**：
   - `confidence_source == "api"` → 用 `confidence` 与阈值（默认 0.7）比较，低于阈值 `escalate("low-confidence")`；
   - `confidence_source != "api"` → **忽略 confidence 值**（不门控、不上抛），按配置正常执行；
   - `answer` 为空/缺必需 qid/值非法 → `escalate("low-confidence")`（无法给出可用答案才算失败）。
   理由：唯配置论（DS-9）下"能不能自动"由配置决定，不由模型自报的置信度决定；否则 P2 永远不生效。
4. **重复触发**：`decide_for` 调 `append_decide` 时传 `duplicate="existing"`（重放语义），并把结果标注 `note=duplicate-replay`；不抛异常、不新增 escalate 值。
5. 更新 `test_decision_points.py`：
   - 词表一致性断言（两个模块的集合相同，除 `input-invalid` legacy）；
   - 步 8 两分支各一例（api 低置信上抛 / model-self-report 低置信照常执行）；
   - 重复触发重放一例（返回既有行、不新增行、档案尺寸不变）。
6. 同步更新 `test_decide_archive.py` 中依赖旧词表的断言（如有）。

## 交付格式

- 报告四段：结论 / 证据（pytest 输出摘要）/ 残留与未验证 / 改动文件清单。
- 关键改动附 `path:line`；两模块词表一致性要有断言，不靠肉眼。
- 契约不足时停手写进残留，禁止自行改契约。

## 种子

- goal 锚点: `.agenticdoc/goal.md`（文件驱动的去中心化协调 / 项目级目标对齐）
- 代码锚点: `packages/multi-workers/decision_points.py:88`（ESCALATED_REASONS）
- 代码锚点: `packages/multi-workers/decide_archive.py:48`（_ESCALATED_REASONS）
- 代码锚点: `packages/multi-workers/decision_points.py:95`（待删除的映射表）

## 写入允许面

- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/decide_archive.py`（仅 `_ESCALATED_REASONS` 与相关注释/校验）
- `packages/multi-workers/test_decision_points.py`
- `packages/multi-workers/test_decide_archive.py`

## 写入禁止面

- 其它任何文件（含 `mw.py`、TS 侧、其它 key 目录）
- 禁止 `git add/commit/checkout/stash/clean`、禁止 `npm run build`

## 验收命令

```bash
cd packages/multi-workers && python -m pytest test_decision_points.py test_decide_archive.py -q
```

期望：全绿（≥103 passed）。

## 改动历史

- 2026-10-20 创建（T-01 残留裁定）
