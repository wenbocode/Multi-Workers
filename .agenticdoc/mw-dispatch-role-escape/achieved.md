# achieved: mw-dispatch-role-escape

> 结案日期: 2026-09-20 / 交付: 派工契约补齐（type 可达 + 覆盖留痕 + 值校验）

## 系统行为变化

- **`dispatch_worker` 工具**：新增 `type: coding|review|research` 与 `model_reason` 参数；省略 type 时保持原 cli 推导；
  结果文本改为回显真实 `type`/`role`/模型层来源（旧文本把 cli 当 type 打印）。非法 type、缺理由的覆盖、
  无法解析的模型 id 均在**建目录之前**拒绝。
- **`/worker` 命令**：新增 `--type` / `--reason`，与工具共用同一 frontmatter 规划器与校验；
  notify 回显 type/role/模型层。
- **模型覆盖契约**：与 `.mw/dispatch.yml` 该 role 默认值不同的显式 `model` 必须带理由，理由落盘为
  task.md 的 `model-reason: <单行>`；与默认值相同的请求不再 pin（不写 `model:` 行，配置保持唯一事实来源）。
- **模型 id 校验**：pi 路由下，显式值与「本次生效的 role 默认值」都会对照 pi 模型表校验；不存在则拒绝
  派发（避免 pi 把它静默当作 custom model id 发请求）。`codex_cli/`/`claude_cli/`、非 pi 任务、
  registry 缺失、registry 无该 provider 均跳过。`/mw model set`（pi 窗口）在写入前同样校验前缀值。
- **BOM 容错**：`.mw/dispatch.yml` 的 UTF-8 BOM 不再让 TS 侧读不到 role（PyYAML 本来就容忍 BOM，
  此前 TS/Python 结论相反 → 覆盖门静默失效）。`readRoleModel` 读取后剥离首个 U+FEFF，双侧测试锁定。
- **launcher 观测**：task.md 显式 `model:` 偏离配置 role 默认值时，launcher.log 在既有
  `source=task` 行后追加 `model-override task=<X> config:<role>=<Y>`；解析顺序与派发行为不变。
- **影响面**：所有经 PM 窗口派工的 worker（type/白名单/模型来源可审计）；配置文件由
  `mw model set` 写入的用户不受影响（schema 未变）。已重建并安装 bundle + coding-agent dist，
  旧窗口需重启 pi 才加载新 bundle。

## 验收证据

- agent-team-loop.test.ts：168/168（新增 10，原 158 零回归）
- multi-workers pytest：692 passed / 0 failed / 9 deselected(e2e)
- `npm run check`：biome 0 修复、tsgo 0 error、shrinkwrap/install-lock 一致
- 安装后 bundle 的 live smoke（临时项目，`type: review`）：拒绝无理由覆盖、接受带理由覆盖并落盘、
  无 model 时回显 `dispatch.yml review=timi/gpt-5.6-sol`；worker trace `type=review` + review 白名单；
  launcher.log 出现 override 证据行
- **`/worker` 命令路径 live 证据（2026-09-21）**：RPC 模式真实 pi 进程代跑全 8 用例通过
  （详见 `evidence/runs/manual-test-worker-command-2026-09-20.md` 结果表 +
  `evidence/runs/rpc-driver-2026-09-21.log`）——原欠债 Q-AC-003 / Q-VC-002 关闭，
  质检报告更新为 25 ✅ / 1 ⚠️ / 0 ❌
- 详见 `evidence/runs/run-2026-09-20.md`、`evidence/quality-gate-report-2026-09-20.md`（25 ✅ / 1 ⚠️ / 0 ❌，2026-09-21 补记后）

## 遗留

1. ~~**`/worker` 命令路径仅单测覆盖（L1）**~~ → **已闭环（2026-09-21）**：RPC 模式
   （`pi --mode rpc`，extension command 可经 `prompt` 执行）代跑全 8 用例通过，
   live 证据落盘。附带发现 F-1：`/worker` 不支持带引号多词 `--reason`（会吞掉后续 `--key`），
   多词理由需连字符或改用工具路径 —— 后续改进候选。
2. **非 pi 窗口直接调用 `mw.py model set` 无 id 校验**（Python 侧无模型表，设计 D-004 明确边界）：
   主路径（`/mw model set` + 派发期）已覆盖。彻底覆盖需引入模型表 artifact → 建议立新 key（若用户在意）。
3. **E2Feature 侧配置修正未由本 key 执行**：`review: timi/gpt-5.6.sol` 应改为 `timi/gpt-5.6-sol`
   （用户已选方案 A）。去向：用户在 E2Feature 窗口执行 `/mw model set review timi/gpt-5.6-sol`。
4. **task.md 契约新增键**：`model-reason:` 已确认与 launcher/worker 两侧正则不冲突；若后续加入更多
   元数据键，需沿用同一「键名不与 `^model:`/`^type:` 前缀冲突」原则 —— 记入 `_pitfalls.md`。
