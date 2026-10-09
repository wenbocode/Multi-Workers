# T-12 能力可见面（`mw model show` / `mw doctor` 三态列）

- key: mw-vision-role · 波 3 · 独占写面：`packages/multi-workers/mw_common.py`（doctor 段）、`mw.py`（show 段）、`.../agent-team-loop/shared/mw-runner.ts`、`.../agent-team-loop/pm/ui-bridge.ts`（doctor 渲染段）、`test_dispatch_models.py`、`test_serve_doctor.py`、`agent-team-loop.test.ts`
- ac_refs: AC-010, AC-015 · vc_refs: VC-010, VC-015
- 依赖: T-10, T-11, T-13（`ui-bridge.ts` 串行链末端） · 预估: 90-120min

## 数据流顺序（唯一合法顺序，不得跳步）

1. `mw_common.py:1265-1273` JSON `dispatch` 段加能力字段（**真源**；TS 渲染器只读 `report.dispatch`）
2. `mw_common.py:2298-2308` Python 文本行加 `images=`
3. `pm/ui-bridge.ts:1755-1766` TS 渲染加 `images=`
4. `mw.py:3210-3235` `model show` 每角色行加 ` images=<v>`

## 契约（逐字遵守）

- 格式：`role=value images=<yes|no|unknown>`（行内列，D-011 方案 A）；`model show` 行尾追加 ` images=<v>`（未配置行追加在 `[source]` 之后）
- 角色遍历顺序不变（`mw model show` 用 `DISPATCH_ROLES`；doctor Python 用 `sorted(models.items())`）
- `_doctor_dispatch` **只在 `models` 非空且无 `error`** 时探测并写字段：缺文件路径仍必须只返回 `{"exists": False}`（`test_dispatch_models.py:473` 是字典**精确相等**断言）
- 三态语义（AC-010）：
  - `images=no` ⇒ 落 **suggestions**（消息含 `mw model set vision`），**不得**落 `issues`（否则 `summary.healthy` → 退出码 1，违反 AC-010）
  - `images=yes` ⇒ ok
  - `images=unknown`（探针不可用/角色未配置）⇒ skip 行，非 issue 非 error
  - 三种情形 `mw doctor` 退出码 **均 0**
- `shared/mw-runner.ts:380-385` 的 `DoctorJson.dispatch` 加**可选**能力字段（不改既有字段）
- **必须同步**：`agent-team-loop.test.ts:5029-5031` 的接合处子串（`派发模型: coding=timi/glm-5.3; 窗口模型 ...`）改为含 `images=` 的新期望 —— 仅更新渲染期望，**不放宽断言**

## 步骤

1. Python JSON 段 + 文本行；`model show` 行。
2. TS 类型 + 渲染。
3. 测试：Python 侧 in-process 三支（`monkeypatch.setattr(mw_common, "model_images", ...)` 后调 `mw_common.doctor_report(...)`，形态同 `test_dispatch_models.py:471-495`）+ 断言三支 `rc=0`；`test_serve_doctor.py` 子进程只覆盖 skip 支；TS 侧 `formatDoctorReport` 渲染用例 + 重冻 `:5029-5031`。
4. `[VERIFY]` 用 `process.stdout.write`（TS）/ `flush=True`（Python）。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_dispatch_models.py test_serve_doctor.py -q -s
cd ../../packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
npx biome check --error-on-warnings src/extensions/agent-team-loop
```

## 证据格式

`[VERIFY] VC-010: doctor_rc=0 states=suggestion,ok,skip` · `[VERIFY] VC-015: show_images=yes/no/unknown rc=0`

## 非空洞对照

把能力不匹配改落 `issues` ⇒ 三支 `rc=0` 断言中的 no 支红；缺文件时多写一个键 ⇒ `test_dispatch_models.py:473` 红。

## 交付

5 处源码 + 3 个测试文件 + 原始输出。重冻 diff 需在 output 中给出。
