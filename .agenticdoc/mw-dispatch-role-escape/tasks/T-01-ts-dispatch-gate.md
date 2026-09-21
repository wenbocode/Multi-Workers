# T-01 TS 派发门禁（type / model_reason / 校验 / 回显）

- 依赖: 无（首个任务）
- 覆盖: AC-001 ~ AC-008、AC-010；VC-001 ~ VC-008、VC-010
- 设计: D-001 ~ D-007、D-009、D-010

## 改动文件

1. `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts`
   - `DISPATCHABLE_TYPES = ["coding","review","research"]`；
   - `DISPATCH_ROLE_BY_TYPE`（镜像 `mw_common.TASK_TYPE_TO_ROLE`，未命中 → `coding`）；
   - `readRoleModel(cwd, role)`（泛化自 `readMainModelConfig`，后者保留为 `main` 包装）；
   - `validateModelValue(registry, cli, taskProvider, value)` 纯函数（D-004）。
2. `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
   - `dispatch_worker`：新增 `type` / `model_reason` 参数、校验与 reason 门、frontmatter 渲染、
     修正回显文案（D-007）；
   - `/worker`：新增 `--type` / `--reason`，复用同一渲染与校验（USAGE 同步）；
   - `runMwModelCommand` set 分支前置校验（D-010，runner 不被调用）。
3. `packages/coding-agent/test/extensions/agent-team-loop.test.ts`：VC-001~VC-008、VC-010。

## 实现要点

- 拒绝路径必须在 `fs.mkdirSync` 之前（无半成品）。
- 校验顺序：type 合法 → owner key/docs gate → role 解析（dispatch.yml 读取）→ reason 门 →
  模型值校验 → 落盘 + 队列 upsert（保持既有 docs gate 顺序不倒退）。
- reason 折叠换行为单空格；空串等同缺失。
- frontmatter 顺序：`type:` → `model:`（若写）→ `model-reason:`（若写）。
- 省略 `type` 时保持原推导；省略 `model` 时不读 reason 门、不校验模型值（AC-010）。

## 完成判据

- 新增用例全绿；原 `dispatch_worker` 相关用例（owner-key / MW-001 / MW-002 / docs gate）全绿；
- 不传新参数时的 task.md 内容与改动前逐字节一致（VC-010 断言）。
