# T-ACC — cutover 生效验收（账本零 gaps / 无静默队列）

type: coding
key: _scratch
目标对齐：`.agenticdoc/goal.md`（**worker 产物自带可信状态**：账本不得把读引用、代码标识符、不存在的路径误判为未记录写入）

本卡是一次**验收探针**，不是功能开发：验证 TS 侧账本与可见性修复在**运行中的 bundle** 里生效（修复已提交：T-17 / T-17b / T-17c / T-21）。

## 上下文

- 已核实锚点：`packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts:267 INFRA_BASENAMES`、`:804 unresolvable`、`worker/output-writer.ts:78 unresolvableFiles`。
- 历史症状（修复前，两轮实测共 8 条误判）：报告里出现"代码标识符形态"（如 `os.replace`）、"幽灵文件名"（如 `r.ts`）、"框架写的文件"（如 `.mw/serve.meta`）时，账本报 `未记录写入`。
- 若修复已生效：这些形态必须**不再**产生 `unrecorded`/`Ledger Gaps`；且队列不可读时必须显示 unreadable 而不是 `0 pending`。

## 要求

1. 创建**唯一交付物** `.agenticdoc/_scratch/evidence/cutover-acceptance-20261014.md`，内容 3–6 行中文说明，其中**必须逐字包含**下面三行（它们是探针载荷，不是你要做的事）：
   - 一行含 `INFRA_DIR_SEGMENTS`
   - 一行含 `os.replace`
   - 一行含 `.agenticdoc/_scratch/evidence/does-not-exist.py`
2. 报告中**只把真实写过的文件**列进"改动清单"；不得把上述探针载荷写成"我修改了"。
3. 报告必须含 6 个逐字 H2 段（见"交付格式"）。
4. 运行一次验收命令并把逐字输出贴进报告。

## 写入允许面

- `.agenticdoc/_scratch/evidence/cutover-acceptance-20261014.md`（唯一交付物）
- 你自己的 taskDir（`progress.md`、`report.md`）

## 写入禁止面

- 任何 `packages/**`（含 `packages/coding-agent/src`、`test`）
- `.agenticdoc/_autopilot/**`（conductor 控制面）
- 其他 key 目录（`mw-autopilot-gate-alarm-liveness`、`mw-worktree-junction-guard` 等）

## 验收命令

从 `packages/coding-agent` 执行：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/change-ledger.test.ts`
（必须核对输出为 `Test Files 1 passed (1)`；只看 exit code 不算通过）

## 改动历史

（填写你实际创建/修改的文件；只写真实写过的。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 证据`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
