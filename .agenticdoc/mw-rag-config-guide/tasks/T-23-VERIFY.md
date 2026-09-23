# Task T-23: 独立验证（第三方视角）

## 元信息
- Stage: 3
- 依赖: T-21、T-22 全部完成（含 PM 直执的 T-21B/T-21C 修正）
- 风险等级: 中（重型验证；注意输出预算与落盘）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-207, AC-201~AC-206 复核]
- vc_refs: [VC-201, VC-202, VC-203, VC-204, VC-205, VC-206, VC-207, VC-208, VC-209, VC-210]
- pattern_refs: []

## 当前实现状态（**以实跑为准**，不要照抄本文件的描述）

T-21 交付 `mw rag init` 后，PM 做了一次行为修正（T-21B/T-21C），现状是：

- `mw rag init --project <dir>` **默认写三个文件**：`.mw/rag-servers.yml`、`target.yml` 的 `rag:` 段、
  **`.mw/rag-roots.json`**（内容 `_README` 数组 + `"engine": "."`），且 `path_roots_file` **默认激活**。
- `--no-roots` 才不写 roots 文件，并把 `path_roots_file` 写成注释行（不允许激活字段指向不存在的文件）。
- `--with-roots` **已不存在**（T-22 派发时任务书里的旧名，手册已按新 CLI 对齐）。
- 手册 `docs/rag-config-guide.md` 的三个模板块必须逐字等于 `mw rag init --print` 输出（`test_rag_docs.py` 字节 parity）。

## 交付物

`.agenticdoc/mw-rag-config-guide/evidence/verify-run-2026-09-22.md`（**唯一允许写的文件**；其余只读）

落盘协议：先 `write` 骨架（§0~§7 标题 + 结论占位），再每节一次 `edit` 填充（防流中断）。建议 ≤ 300 行。

## 必须做

### 1) 命令与实测

1. `cd packages/multi-workers && python -m pytest test_rag_init.py test_rag_docs.py -q -s`（逐条记 `[VERIFY]` 原文）
2. 同一命令**再加环境变量** `PYTHONIOENCODING=utf-8` 跑一遍（本机中文输出的常见设置）——必须同样全绿；
   若有失败，属测试自身的编码脆弱性，如实记录文件/行号与报错（T-22 曾报告过一处，PM 已修 subprocess 的 `encoding`）。
3. `python -m pytest -q`（记 passed / deselected / 失败项）
4. 真跑路径（临时目录 + `MW_RAG_SERVERS_HOME` 指向临时目录，**绝不碰真实 HOME**）：
   `rag init` → `rag list` → 再 `rag init`（应 exit 1）→ `rag list --json` → `rag probe` → `rag audit`；
   记录每条命令的 exit code 与关键 stdout。**额外**：确认默认生成的 `rag-roots.json` 存在、`engine` 为 `.`。
5. 手册可执行性抽查：从手册里**逐字复制**四类示例中的至少两类（mcp-only 与 both），写进临时项目，
   `load_rag_config` / `mw rag list` 必须无 error（证明"复制粘贴即用"不是空话）；若失败，如实记录并指出是手册还是实现的问题。
6. `git diff --stat` 与 `git status --porcelain`（确认没有意外改动；fixtures/golden/`test_autopilot_l0.py` 零 diff）。
7. 仓根 `npm run check`（exit code）。

### 2) 三条反例试验（**必须做**，逐条记录「改了什么 / 看到什么红 / 还原方式 / sha256 是否复原」）

- **反例 A（手册-实现 parity 真的钉住）**：改 `rag_templates.py` 里模板的一个字符（例如把 `transport: mcp` 的注释改一个字）
  → `test_rag_docs.py` 的 `VC-206` **必须变红**；还原 + sha256 自检。
- **反例 B（字段覆盖真的钉住）**：把手册字段表里的 `capabilities.chat` 改成 `capabilities.chats`
  → `VC-205` **必须变红**；还原 + 自检。
- **反例 C（默认零影响真的钉住）**：把 `render_target_rag_template` 的默认 `enabled: []` 改成 `enabled: [example]`
  → `VC-201` 中「`mw rag list` 显示 `enabled: (none)`」**必须变红**；还原 + 自检。

> 若某条反例**不变红**，说明该断言是装饰：在报告里如实降级该 VC 的证据强度并写明原因（不得含糊）。

### 3) 散文准确性抽查（**新增，重点**）

模板块有字节锁，但**散文段落没有锁**。PM 已经在这轮里发现过两处散文与实现不符
（§6 的 `via=mcp|c...` 截断、§3.4 把"未知 role"写成 `unverified` 而不是 `missing`）。
所以必须**独立**再抽查一遍：自己挑**至少 8 条**手册里的可证伪断言（例如：某字段的默认值、某条报错原文、
某个退出码、某个 signature 的字段集合、`sync` 写到哪个路径、`--no-roots` 的后果、`enabled` 缺省语义、
`roles` 比 `phases` 多接受哪两个键），逐条与代码/实跑对照，列表给出「断言 | 依据(file:line 或命令) | 结论(符合/不符)」。
不符合的**不要改代码或手册**——写进报告并给 `file:line`。

### 4) 逐 VC 表

每行给：断言摘要 | 发射位置 `file:line` | **实测行原文** | 证据强度（强/弱/装饰）。
VC-201~VC-210 全部要有行；缺失的必须显式写「未覆盖 + 原因」。

### 5) 归属与限制

- 失败项逐条归属：本 key 缺陷 / 本机环境（Windows 基线）/ 其它会话。
- 如实写「未做」：真实 RAG 服务联调（占位 URL 不连）、`mw serve` 重启后的端到端 worker 跑（本任务只验证配置面）、
  手册的中文排版细节、`--machine` 在真实 HOME 上的行为（刻意在临时 `MW_RAG_SERVERS_HOME` 下测）。

## 验收

- 报告含 §0 复现命令表、§1 VC 汇总表、§2 逐 VC 明细、§3 反例试验记录、§4 散文准确性抽查、
  §5 零回归与改动面、§6 手册可执行性抽查、§7 未覆盖与限制。
- 每个 `[VERIFY]` 行都能在报告里找到对应命令。
- 除该报告外未改任何文件；未 commit。
