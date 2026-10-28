# T-W-I12 · 端到端双通道对拍 + AC-005 反证（B3，纯测试面）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 本 key 的核心主张是"同一时刻同 key 同文件多写者对 = 0"，且这个 0 必须由**两条派发通道**（conductor / PM）给出**同一判定**。B1 已让两通道同形（`packages/multi-workers/autopilot/dispatch.py:1118` `_write_face_verdict` ↔ `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts:404` `writeFaceVerdict`），B2 已让运行期真的拦（`worker/worker-mode.ts`，D-115 后 `write_face:` 为权威载体）。本卡提供**收口证据**：不是各自单测，而是同一输入过两条通道后的逐字段对照 + 反证。
- **为什么必须端到端而非只跑单测**：语料只锁算子（`kind`/`sample_globfree`），两通道的分歧历史上出现在**判定形状**（拒绝码 / `overlap-with` / 样例路径 / 在飞集合口径）与**外部等价性**（base 口径、大小写模式、终态集合）上——这些只有把两侧的真实入口放在同一装置里跑才会暴露。前一轮 PM 差分（`evidence/PM-parity-differential-20261014.md`）就抓到过一个**装置缺陷**：两侧 base 不等会制造 4 个假不一致，必须显式对齐。
- **裁定与 AC**: `spec.md` AC-005（同 key 同文件多写者 = 0）、AC-007（两通道同判定）、AC-013（假阻族）；`design.md` D-111（先证冲突）、D-112（逗号无条件分隔）、D-115（载体收敛）。
- **定位锚点（只读参考）**: `packages/multi-workers/autopilot/dispatch.py:1118`（conductor 判定入口）、`:1022`（卡面抽取）、`:1055`（渲染）、`packages/multi-workers/autopilot/write_face.py`（算子）、`packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts:404`（PM 判定入口）、`:291`（`dispatchTask`）、`packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts:190`/`:225`（队列读 / 锁内写）、`packages/coding-agent/test/suite/write-face-pm-gate.test.ts`（既有的 PM↔Python 只读对照写法，可参考不可改）、`packages/multi-workers/test/test_write_face_dispatch.py`（conductor 侧既有套件，可参考不可改）。
- **可复用装置（只读）**: `.agenticdoc/_scratch/evidence/wf-parity-diff-20261014.py`（600 随机向量的差分装置，含 `WF_DIFF_BASE` 显式对齐 base 的教训）、`wf-pos-matrix-20261014.py`（定位矩阵）。
- **语料（只读）**: `packages/multi-workers/test/fixtures/write-face-corpus.json`（`counts={parse:23, overlap:59}`，LF 归一化 `sha256=b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62`；Windows 磁盘为 CRLF ⇒ 20126 B）。

## 写入允许面

- `packages/coding-agent/test/suite/write-face-e2e.test.ts`（新建）
- `packages/multi-workers/test/test_write_face_e2e.py`（新建）

## 写入禁止面

其余一切路径，**特别是任何生产代码**：`autopilot/**`、`pm/**`、`worker/**`、`shared/**`、`packages/multi-workers/**`（除上述新建测试文件）全部只读；其它既有测试文件只读（不得改 `write-face-pm-gate.test.ts` / `test_write_face_dispatch.py` / `test_write_face.py` / `write-face-runtime.test.ts` 等）。**禁止 `npm run check`**（P-017）；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **① 同语料双通道逐字段对照**：在同一装置里，对语料（`parse` + `overlap` 两侧）构造**同一条在飞上下文 + 同一批候选写面**，分别喂给 conductor 入口（`dispatch._write_face_verdict`，只读 import，不写 Python 文件）与 PM 入口（`dispatchTask` / 其判定函数），逐字段比较 `code` / `overlap-with:<task_key>` / 样例路径 / `serial-only` 与否。**必须显式对齐 base 与大小写模式**（把上一轮那个"base 不等制造假不一致"的坑写进证据：给出对齐前后计数）。
2. **② AC-005 反证**：构造"同一时刻、同 key、同文件"场景，断言经两条通道判定后**多写者对 = 0**：在飞快照（队列 + task.md 的 `write_face:` 字段）重算一遍，与派发实际结果一致；反例要能真的复现（例如人为绕过闸门时该数量 > 0，说明检测器有效——即"检测器不自证"）。
3. **③ AC-013 假阻双向对照**：真写族必须拦（面外文件、`..` 逃逸、仓外绝对路径、目录目标越界），假写族必须放行（`Write-Output a <term> --glob x` 家族、here-string 载荷、只读命令），并在证据里给出**逐条判定表**（两侧各一列）。
4. **装置等价性声明**：测试里必须显式写出两侧等价前置（base = 仓库根、大小写 = 平台判定 `os.name == "nt"` / `process.platform === "win32"`、终态集合各自单一源），任何无法等价的项要在 `残留与未验证` 里点名。
5. 每个断言带理由注释（对应 AC/D 编号）。测试**不得跳过**（禁 `skip`/`todo`/`it.only`）；不得因环境差异而条件性跳过——平台差异用显式断言表达（本机 win32）。
6. `git diff --stat` 收尾时只应出现这两个新文件（工作区其它 session 的改动不算）。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑的原始命令与原始输出**：两侧套件条数、逐字段对照表（含对齐前后的不一致计数）、AC-005 反证的原始计数、AC-013 双向逐条判定表。若出现 `## 路径形态（warn）`/`## Ledger Malformed` 段，说明它来自 `worker/output-writer.ts` 的形态检查，**不影响判定**。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face-e2e.test.ts
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest test/test_write_face_e2e.py -q
```

（两侧**都要**跑；只在一边跑出绿不算完成。）

## 改动历史

- 2026-10-14 B1 收口（conductor + PM 两通道同形）、B2 收口（运行期闸门 + D-115 载体收敛：`write_face:` 权威、`write_scope:` 仅 writeless、双载体不等取交集）。本卡是 B3 的收口证据。
- 2026-10-14 PM 已知的既有无关红（**不要修，报基线即可**）：`test/extensions/agent-team-loop-worker-file-tool.test.ts` 2 条（`trace.log` 污染）、`test/suite/mwds-t02-write-intent.test.ts` 1 条（别 key task book 语料漂移）、`test/suite/mwds-t23-cutover-recheck.test.ts` 1 条（别 session 的 dist bundle sha）；Python 侧 `test/test_write_face.py` 与 `test/test_write_face_dispatch.py` 当前全绿（130 / 29）。

## 硬约束

- 不跑 `npm run check`（P-017）；不跑无文件参数的全量 vitest（P-032）。
- 只新建上述两个测试文件，**不改任何生产代码**；发现生产代码有缺陷，写进 `残留与未验证` 并给出可复现命令，交给 PM 派卡修。
- 两侧测试都必须真的断言，不得用"打印即通过"的写法。
