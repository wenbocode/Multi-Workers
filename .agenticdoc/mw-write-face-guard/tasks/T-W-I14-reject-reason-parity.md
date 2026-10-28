# T-W-I14 · 拒绝分支 `reason` 串两通道对齐（AC-007 最严读法的最后缺口）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 两条派发通道（conductor / PM）对同一写面输入必须给出**同一判定**。B1/B3 已证明 `ok` / `code` / `overlap-with:<task_key>` / `sample` / `serial-only` 五个字段 **410 次对照零分歧**（`plan.md` §7.8）；本卡收口**唯一剩下的字段**：拒绝分支的人可见 `reason` 串。
- **缺口（PM 读码发现，W-12 的对照字段不含 `reason` 故未被发现）**：
  - Python `packages/multi-workers/autopilot/dispatch.py:1169`：`reason = f"{parsed.code}: {parsed.detail}"`，而 `Refused.detail` 携 `entry '<raw>'`（非法条目）/ `present-but-empty write_face head`（空头）——构造点见 `packages/multi-workers/autopilot/write_face.py:654`、`:668`、`:674`、`:685`。
  - TS `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`（`writeFaceVerdict` 的 `parsed.kind === "rejected"` 分支）：只回 `reason: parsed.code`，`detail: \`${taskKey}: ${parsed.code}\``。根因：TS 算子 `shared/write-face.ts:134`/`:514` 的 `rejected` 变体**只带 `code`**，不带被拒条目。
  - 后果：同一非法输入的审计 detail（经 W-13 的 `writeFaceRefusalDetail` → `.agenticdoc/_autopilot/auto-decisions.jsonl` 的 `kind:"write-face-refusal"` 行）在两通道不同；人排查时看到的拒绝原因粒度不同。
- **裁定与 AC**: `spec.md` AC-007（两通道同判定）；`design.md` D-111（拒绝优先级与顺序无关）、D-008（拒绝形状：稳定 code + `overlap-with` + 样例）；语料 **只锁 `kind`（+可选的 `code`），从不锁 `reason` 正文**（同 V59/V60 的既有裁定），故本卡只加字段、不改判据。
- **定位锚点**: `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts:134`（`WriteFaceParseResult` 的 `rejected` 变体）、`:514`（`NormalizeResult` 同名变体）、`:524`/`:539`/`:543`（rejected 构造点）、`packages/multi-workers/autopilot/write_face.py:654/668/674/685`（Python 侧 detail 构造，语义基准）、`packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`（`writeFaceVerdict` 的 rejected 分支）、`packages/coding-agent/test/suite/write-face.test.ts`（算子套件，当前 109 passed）、`packages/coding-agent/test/suite/write-face-pm-gate.test.ts`（PM 闸套件，当前 22 passed）、`packages/multi-workers/test/test_write_face_e2e.py`（B3 装置，可读参考）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`
- `packages/coding-agent/test/suite/write-face.test.ts`
- `packages/coding-agent/test/suite/write-face-pm-gate.test.ts`

## 写入禁止面

其余一切路径，特别地：`packages/multi-workers/**`（Python 侧是**语义基准**，只读，不得为了"对齐"去改它）、`worker/**`、`pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`、`autopilot/**`、其它测试文件。**禁止 `npm run check`**（P-017）；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **TS 算子做加法**：给 `rejected` 变体加一个**可选** `detail` 字段（保持 `code` 语义不变），并在 rejected 构造点填上与 Python **同源**的 detail：
   - 空头 ⇒ `present-but-empty write_face head`（对齐 `write_face.py:654/674`）；
   - 逐条目被拒 ⇒ `entry '<raw>'`（`<raw>` 是该条目的原始文本，对齐 `write_face.py:668/685`）。
   保留原始条目文本，不要在算子内部做"对齐用"的格式转换（渲染/展示由调用方负责）。
2. **`reason` 组装对齐**：PM 侧 rejected 分支改为 `reason: \`${code}: ${detail}\``（与 `dispatch.py:1169` 同构），`detail` 字段仍保留现有 `<taskKey>: …` 形态；当算子未提供 detail（旧行为/未覆盖路径）时退回 `code`，**不得**产生 `"code: undefined"`。
3. **不改变既有判定**：`kind`/`code` 的产出逻辑与优先级（D-111 顺序无关）**零变化**；语料驱动的既有断言不得改判据。
4. **测试（加法，不得放宽既有断言）**：
   - `write-face.test.ts`：给算子层加 rejected detail 的断言（空头 / 非法条目 / 逃逸条目 / outside-base 各至少一条），并断言既有 109 条不回归。
   - `write-face-pm-gate.test.ts`：加"同一非法输入 PM 与 Python 的 `reason` **逐字节相等**"的对照（复用 W-08 的只读 Python 子进程手法：把同一 head 文本喂给 `dispatch._write_face_verdict`，只读 import，不改 Python 文件），至少覆盖 2 类拒绝（空头 + 非法条目）。
   - **引号边界必须显式覆盖**：Python 的 `detail` 用 `{raw!r}`（`repr`），条目内含单引号时 Python 会改用双引号包裹。若你无法用简单规则完全对齐 `repr` 的引号选择，**不要**伪造对齐：把该边界写成"已知有界差异"的显式断言（在测试里断言两侧**除引号风格外**一致），并在 `残留与未验证` 里给出该边界的原始输出与理由。
5. `git diff --stat` 收尾时只应含允许面四个文件。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑的原始命令与原始输出**：两侧 `reason` 对照表（同 head 文本，PM vs Python，逐字节）、`write-face` 与 `write-face-pm-gate` 两个套件的条数（基线 109 / 22）、引号边界的原始输出（若存在差异）。若出现 `## 路径形态（warn）`/`## Ledger Malformed` 段，说明它来自 `worker/output-writer.ts` 的形态检查，**不影响判定**。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face.test.ts test/suite/write-face-pm-gate.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face-e2e.test.ts test/suite/mwds-t03-bash-write-scope.test.ts
npx tsgo --noEmit
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest test/test_write_face_e2e.py test_write_face.py test/test_write_face_dispatch.py -q
```

（Python 侧必须全绿：本卡**不应**改动 Python，若你的改动让它变红，说明你改错了地方。）

## 改动历史

- 2026-10-14 B1/B3 已证两通道的 `ok`/`code`/`overlap-with`/`sample`/`serial-only` 五字段 410 次对照零分歧（`plan.md` §7.8）；W-13 已让 PM 拒绝落审计行（`kind:"write-face-refusal"`, detail = `<task_key>: <reason>`）。
- 2026-10-14 PM 读码发现：rejected 分支的 `reason` 串两通道不等（TS 算子不带被拒条目文本），本卡收口；`shared/write-face.ts` 由 W-02/W-05 交付、语料锁定，本次只做**加法**。

## 硬约束

- 不跑 `npm run check`（P-017）；不跑无文件参数的全量 vitest（P-032）。
- 不改 Python 侧（语义基准只读）；不改判定逻辑与优先级；既有断言只许加不许放宽。
- 不为了"看起来一致"而伪造 `repr` 对齐——做不到就显式记为有界差异并给出原始输出。
