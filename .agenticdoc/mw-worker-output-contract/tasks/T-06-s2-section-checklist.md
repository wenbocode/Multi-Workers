# T-06 · S2 契约段清单注入（生产者侧，Python）：`_envelope_card_body` 渲染 `## 交付段契约（本角色）`

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「项目级目标对齐」「phase 门禁」）——worker 在开工前就必须知道本角色的输出契约段，否则只能事后被 `exit=2` 拦下。
- 现状：`task.md` 由 `packages/multi-workers/autopilot/dispatch.py` 生成；`_envelope_card_body`（`autopilot/dispatch.py:602`）渲染卡信封区（`## 上下文` / `## 要求` / `## 交付格式`）。本角色契约段清单**尚未**注入 ⇒ worker 靠猜。
- 设计落点（`design.md` §4.4，逐字照办）：清单 = `recoverySectionsFor(type)` 渲染成 `## 交付段契约（本角色）`，由**生产者**注入：`autopilot/dispatch.py::_envelope_card_body` + `pm/ui-bridge.ts::renderCardSeedSections`（TS 侧归 T-05，门控 `card is not None`）。worker 侧**只审计不改 task.md**（改写会推高 mtime 撞 `launcher._envelope_enforced` 分支）。
- 为什么必须有 S2（DR2 量化）：116 例翻转里 **32 例与机械段无关**（S3 完全无效），只有 S2 能救；S3 单独只救回 6 例。
- AC-003 判据：`task.md` 含本角色契约段清单（每段给出**可复制的** `## <段名>`）；在 ≥2 个真实任务（research / review 各 1）的 `task.md` 中可见，命中 2/2。
- AC-002 判据：settle 回读文本包含**全部**缺失段的准确名称（不出现与事实不符的段名）。本卡是 AC-002 的**前置**半边（清单来源），判定侧在 T-05。
- 语料锚点：段别名表与类型拆分在 `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts` 的 `RECOVERY_SECTIONS`（`worker/output-sections.ts:30`）与 `RECOVERY_TYPE_SECTIONS`（`worker/output-sections.ts:34`）。**Python 侧不得自造别名表**：必须与 TS 表同源（见要求 3）。

## 写入允许面

- `packages/multi-workers/autopilot/dispatch.py`
- `packages/multi-workers/test_mwoc_s2_sections.py`（新建 pytest）

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/autopilot/*.py` 除 `dispatch.py` 外全部只读；`packages/coding-agent/**`（TS 侧注入归 T-05）只读；`packages/multi-workers/test_autopilot_dispatch.py` 等既有 pytest 只读（不许改既有断言来迁就新段）。**禁止 `npm run check`**（本卡是 Python）；**禁止**跑全量 pytest（只跑本卡新文件 + 受影响的既有 dispatch 套件）。

## 要求

1. **注入位置**：`_envelope_card_body` 内，门控 `card is not None`；段标题固定 `## 交付段契约（本角色）`，内容逐段给出**可复制**的 `## <段名>`（含 `## 上下文来源`）。
2. **类型分流**：按卡面 `type:` 取该角色的段清单（research / review / coding 各不相同）；`vision` / `rag-research` 这类无契约段角色**不注入**该节（不要硬塞空段名）。
3. **单一真源**：段名与别名只能来自 TS 侧 `worker/output-sections.ts` 的 `RECOVERY_SECTIONS` / `RECOVERY_TYPE_SECTIONS`。Python 侧读取方式二选一（给出理由）：(a) 从该 TS 文件解析常量并断言与本地表逐字一致；(b) 在 Python 侧建表 + 新增 parity 测试（照 `test_task_type_parity.py` 的模式）断言与 TS 逐字一致。**禁止**让两处自由漂移。
4. **幂等**：同一卡重复渲染不产生重复节；已有 `## 交付段契约（本角色）` 时不追加。
5. **不破坏既有信封门禁**：注入后 `task.md` 仍须通过 `launcher.has_canonical_envelope` / `dispatch-card.ts::readEnvelope`（`## ` 标题族识别）；`card_path:` / `card_sha256:` 头部行不变。**不得**通过修改门禁来让新节通过。
6. **AC-003 机械验收**：新增 pytest 至少覆盖 (a) research 卡渲染出 `## 交付段契约（本角色）` 且含 research 段名；(b) review 卡同理；(c) 无契约段角色不注入；(d) 幂等。并在证据里给出**两个真实任务**（research / review 各 1）的 `task.md` 片段与命中计数 2/2 —— 真实任务指本 key 交付后实跑的 worker（若 T-06 先于 T-08 完成，用 `dispatch.py` 的真实调用路径生成到临时目录并在 `残留与未验证` 声明「待 T-08 实跑复核」）。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令 + 原始输出**：pytest 条数与结果、2 个真实/模拟 `task.md` 的注入片段、parity 测试结果（若选 (b)）、既有 dispatch 套件的条数与结果。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers
python -X utf8 -m pytest -q packages/multi-workers/test_mwoc_s2_sections.py
python -X utf8 -m pytest -q packages/multi-workers/test_autopilot_dispatch.py packages/multi-workers/test_task_type_parity.py
git diff --stat -- packages/multi-workers
```

## 改动历史

- 2026-10-14 design 阶段 DR2 结论：S2 是 32/116 例的唯一承载机制；清单必须由生产者注入（worker 侧不改 `task.md`，避免撞 `launcher._envelope_enforced`）。
- 既有 `_envelope_card_body`（`autopilot/dispatch.py:602`）与 `render_task_md`（`autopilot/dispatch.py:755`）为本卡的两个相关入口；TS 侧对应 `renderCardSeedSections` 归 T-05。
