# T-18 补齐 VC-003 / VC-007 的缺证（`[VERIFY]` 行从未产出）

- key: mw-vision-role · 波 4.5 · 独占写面：`packages/multi-workers/test_dispatch_models.py`、`packages/coding-agent/test/extensions/agent-team-loop-vision-gate.test.ts`
- ac_refs: AC-003、AC-007 · vc_refs: VC-003、VC-007
- 依赖: T-01（`vision` 角色注册）、T-06（门禁放行路径）· 预估: 40-60min

## 缺陷（T-14 报出，PM 已复核）

`evidence-requirement.md` 要求在两条 VC 上取到**逐字**证据，但全仓 grep 不到：

| VC | 要求证据（`evidence-requirement.md`） | 现状 |
|----|--------------------------------------|------|
| VC-003 | `[VERIFY] VC-003: source=config:vision task_override=task` | grep 0 —— 无任何直接断言 `resolve_dispatch_model(cli="pi", task_type="vision")` 的单测 |
| VC-007 | `[VERIFY] VC-007: queue_delta=1 images_line=yes order_ok=true` | grep 0 —— T-06 只产出了 VC-006/VC-008 行；放行路径的**头部行序**从未被断言 |

（注意：`VC-003`/`VC-007` 这两个编号在**其他 key** 的测试里已被占用（goal-autopilot 的 closure/effective-config 等），含义完全不同——不要把那些命中当成本 key 的证据。）

## 契约

### A. VC-003（写入 `test_dispatch_models.py`，只追加）

- 建 hermetic 临时工程（沿用本文件既有 `_project(...)`/`_emit_verify(...)` 范式），`.mw/dispatch.yml` 里配 `vision: timi/deepseek-v4-flash-vision-exp`。
- 断言 ①：`task_type="vision"` 且 task.md **无** `model:` ⇒ 解析结果为 `("timi/deepseek-v4-flash-vision-exp", "config:vision")`（按 `mw_common.resolve_dispatch_model` 的**真实**签名调用；先读源码确认真实参数名，不要照抄本卡的示意写法）。
- 断言 ②：task.md 带 `model: timi/glm-5.3` ⇒ 解析结果为 `("timi/glm-5.3", "task")`（任务级覆盖优先）。
- 产出 `[VERIFY] VC-003: source=config:vision task_override=task`（`_emit_verify`）。
- 非空洞对照：把临时 `dispatch.yml` 里的 `vision` 键去掉 ⇒ 断言 ① 必须失败（贴失败输出后改回）。

### B. VC-007（写入 `test/extensions/agent-team-loop-vision-gate.test.ts`，只追加）

- 走**放行**路径：`images: yes`（或描述命中图片路径）+ 模型能看图 ⇒ 断言四件事：
  1. 派发 `ok: true`，目录被创建、task.md 落盘；
  2. `_workers.parallel` **新增恰好 1 行**（`queue_delta=1`，沿用该文件既有的队列读取 helper）；
  3. task.md 中存在**整行**匹配 `^images: yes$`（不是子串包含——用 `split("\n").includes("images: yes")` 一类，防止 `images: yes-ish` 混过）；
  4. 头部行序严格：`indexOf("type:") < indexOf("phase:") < indexOf("images:") < indexOf("model:")`（缺行时判定失败）。
- 产出 `[VERIFY] VC-007: queue_delta=1 images_line=yes order_ok=true`。
- 非空洞对照（两条，各贴输出后改回）：① 把 `ui-bridge` 写入侧的行序临时改成 `images` 在 `phase` 之前 ⇒ `order_ok` 断言必须红；② 把放行条件临时改成拒绝 ⇒ `queue_delta=1` 与 `ok:true` 断言必须红。

## 硬约束

- 两个测试文件都只**追加**自己的用例，不 reformat、不改既有断言（`agent-team-loop-vision-gate.test.ts` 是 T-06 的交付，`test_dispatch_models.py` 已被 T-01/T-11/T-12/T-15 改过）。
- **不改**任何 `packages/**/src/**` 源码（本卡只补证据；若你发现源码真有缺陷，写进 output 上报 PM，不要自行改）。
- 不 commit、不 `git add`；不跑全量 vitest；`npx biome check` 不加 `--write`；erasable TS、无 inline import；`print(..., flush=True)` + pytest `-s`；TS 证据用 `process.stdout.write`。
- **禁止用 PowerShell `Get-Content/Set-Content` 改文件**（用 `edit`）。

## 验收（真实执行，贴原始输出）

```bash
cd packages/multi-workers
python -m pytest test_dispatch_models.py -q -s
cd ../../packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-vision-gate.test.ts
npx biome check --error-on-warnings test/extensions/agent-team-loop-vision-gate.test.ts
```

## 交付

两个文件的追加 diff + 原始输出（含 `[VERIFY] VC-003` / `[VERIFY] VC-007` 行）+ 三条对照的失败输出 + 改回后的全绿输出。
