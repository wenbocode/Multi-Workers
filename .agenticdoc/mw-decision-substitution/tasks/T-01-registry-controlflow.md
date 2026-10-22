# T-01 dp 注册表 + 配置表读侧 + `decide_for` 控制流

- key: mw-decision-substitution · type: coding · phase TASKS
- timeout: 40
- 依据: spec.md rev3（AC-001/002/005/011）+ design.md D-001..D-004、D-019、D-022 + plan.md §1

## 上下文

- 配置表 `.mw/decide-points.json` 是唯一授权来源；P2 默认开，P1/P0 默认关；`mode ∈ {auto,suggest}`。
- 24 个 dp 的 id/tier 见 `spec.md` §4（id 与 tier 一律照抄，禁改名）。
- 底座可复用：`packages/multi-workers/decision.py:402-417`（`_encode_state`）、`:644-660`（`_resolve_backend` 之前可短路）、`:111-134`（响应形状）、`:88-99`（REASON_CODES）。
- 8 层降级与热重载方案见 `evidence/research/design-registry-config-20261019.md` Q3/Q4。

## 要求

1. 新建 `packages/multi-workers/decision_points.py`：
   - `DecisionPoint` 冻结 dataclass，字段照 design §2.1（9+1）。
   - 24 项 `DP_REGISTRY`（照 spec §4 的 id 与 tier；P2 `default_enabled=True`）。
   - import 期校验 fail-loud：id 重复 / tier 非法 / P0 缺 `p0_consequences` / P2 缺 `executor`。
2. 配置表读侧：
   - `load_points_config(project_dir) -> PointsConfig`，实现 8 层降级（design §2.2 L0..L7），任何异常都不得抛出到调用方。
   - 进程内缓存键 = `(st_mtime_ns, st_size)`；同秒改动必须能被识别（测试里用 `os.utime(ns=...)`）。
3. `decide_for(dp_id, trigger, project_dir)` 按 design §2.3 的 11 步实现；第 2 步（disabled）必须在 `_encode_state` / backend 解析之前返回。
4. 每次决策按要求写一行档案（调用 `decide_archive`；若该模块尚不存在，先只定义接口调用点并用 `try/except ImportError` 降级为"不写档案但记日志"，并在报告里说明）。
5. 新建 `packages/multi-workers/test_decision_points.py`：覆盖注册表完整性（24 项、id 唯一、P0 有 consequences）、8 层降级各一例、热重载同秒改动、`decide_for` 的 11 步分支（用 FakeBackend 断言 `calls == 0`）。

## 交付格式

- 实现按上列写入允许面落地；报告四段：结论 / 证据（命令 + 输出摘要）/ 残留与未验证 / 改动文件清单。
- 每处关键实现附 `path:line`；关闭态未证明前不得声称完成。
- 遇到契约不足：停手并在报告"残留"里写明，禁止自行改契约。

## 种子

- goal 锚点: `.agenticdoc/goal.md`（文件驱动的去中心化协调 / 项目级目标对齐）
- 代码锚点: `packages/multi-workers/decision.py:402-417`
- 代码锚点: `packages/multi-workers/decision.py:644-660`

## 写入允许面

- `packages/multi-workers/decision_points.py`（新建）
- `packages/multi-workers/test_decision_points.py`（新建）

## 写入禁止面

- 除上列文件外的一切文件（含其它包的源码、其它 key 目录、`_pitfalls.md`、`_project_log.md`）
- 禁止 `git add` / `git commit` / `git checkout` / `git stash` / `git clean`
- 禁止修改 `packages/ai/src/models.generated.ts`、禁止跑 `npm run build`、禁止跑完整 vitest 套件（用 `./test.sh` 或指定测试文件）

## 验收命令

```bash
cd packages/multi-workers && python -m pytest test_decision_points.py -q
python -c "import sys; sys.path.insert(0,r'packages/multi-workers'); import decision_points as d; print(len(d.DP_REGISTRY))"   # 期望 24
```

## 改动历史

- 2026-10-20 创建
