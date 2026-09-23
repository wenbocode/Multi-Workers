# Task T-08-PY-CLI: `mw rag list|probe|sync` + doctor rag 段 + skill 源文件

## 基本信息
- Stage: 4
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型）
- ac_refs: [AC-017]
- vc_refs: [VC-023]
- pattern_refs: []

## 描述

### 源码

1. 新增 `packages/multi-workers/skills/mw-rag/SKILL.md`（**方法论单一来源**，D-012；带 frontmatter `name: mw-rag` / `description: …`，照 `.agents/skills/agentic-task/SKILL.md` 的 frontmatter 形状）。内容（简洁，不写实现细节）：
   - §何时用：任务类型 → 允许的 RAG 工具映射（coding/review/verifier/research = 六个检索工具；`rag-research` 额外可用 `rag_chat`）。
   - §调用纪律（3 条，与 TS `guidelines.ts` 同一套措辞）：先 `rag_symbol`/`rag_graph` 精确定位再 `rag_search` 泛检索；引用必须使用工具返回的 `citation` 原文（不得自行拼接）；"用了 RAG" = 结论落盘并带可核对引用。
   - §引用格式：`server:source:file_path:line`，以及 `local_path`/`exists`/`snapshot_warning` 的含义与"`exists=false` 时不得当作已验证事实"。
   - §调研文档格式（AC-014 的标准）：`.agenticdoc/<key>/rag/<server>-<slug>.md`，六个固定小节标题：`## 查询`、`## 结论`、`## 引用`、`## 未解决`、`## 快照`、`## 影响面`。
   - §降级与反模式：服务不可用只降级不阻断（`rag-unavailable`）；`rag_search` 的 `multi_rounds`/`auto_rewrite` 会让结果不可从证据重放（review 强验证只能用 `rag_graph`/`rag_impact`）；不要凭记忆写文件路径。

2. `packages/multi-workers/mw.py`
   - argparse：`rag` 子命令（照 :3407 起的既有形状），含 `list`（`--project` 必填、`--json`）、`probe`（`--project`、`--json`）、`sync`（`--project`）。`rag audit` 由 T-10 添加（本任务预留子解析器结构，避免两次重构：`rag_sub` 变量，T-10 只加一行）。
   - `_cmd_rag_list`：打印逐字段合并结果 + `origin` 标注 + 启用集；`--json` 输出机器可读结构。
   - `_cmd_rag_probe`：对启用集逐个探活（每个 5s 超时，`allowlist` 之外的服务不探），输出 `reachable` 与能力校正结果；失败不退出非 0（探活是诊断）。
   - `_cmd_rag_sync`：`config["enabled"]` 非空 → 把 `packages/multi-workers/skills/mw-rag/SKILL.md` 内容写到 `<project>/.pi/skills/mw-rag.md`（**临时文件 + `os.replace`**，保证字节一致与原子性；目录不存在则创建 `.pi/skills`）；`enabled` 为空 → 若目标文件存在则删除，否则不动；**不删除 `.pi/skills` 下其它任何文件**。输出已安装/已移除/无需变更 + sha256。
   - doctor：新增 `_doctor_rag(project_dir) -> dict`（照 `mw_common._doctor_dispatch`（:557）形状）并在 doctor 输出中加 `rag` 段：启用服务、探活结论、指纹、skill 安装状态（不存在/已安装且一致/已安装但内容漂移）。

3. 探活的 Python 实现用 stdlib（`urllib.request` 或 `http.client`）：`initialize` → 取 `Mcp-Session-Id` → `list_sources`；**不引入任何依赖**。

### 测试

新增 `packages/multi-workers/test_rag_cli.py`（`unittest`；用 `tempfile` 建项目目录 + `MW_RAG_SERVERS_FILE` 注入机器层；探活用 `http.server` 或 `unittest.mock` 打桩）：

- **list（AC-002 的 CLI 面）**：`--json` 输出含启用集、逐字段 `origin`、继承自机器层的字段；无配置 → 空启用集且退出 0。
- **skill 同步（VC-023）**：启用项目 `sync` → `<project>/.pi/skills/mw-rag.md` 存在且 `hashlib.sha256` 与源文件相等；再次 `sync` → 内容不变（幂等）；`enabled=[]` 项目 `sync` → 文件被移除；未启用且原文件不存在 → 无报错、无新建；断言 `.pi/skills/` 下其它文件未被触碰。
- **sync 不动会话**：断言 `sync` 是唯一写 skill 的入口（代码层：`grep` 断言扩展源码中不含对 `.pi/skills/mw-rag.md` 的写入——用测试固化，防止未来"顺手安装"）。
- **probe**：打桩可达/不可达两种情形 → 输出 `reachable` 正确、超时上限 5s（用假时钟或短超时参数）；不可达不抛异常、退出码 0。
- **doctor**：doctor 输出含 `rag` 段四项（启用/探活/指纹/skill 状态）。

### 注意

- skill 源路径解析：`<mw 包目录>/skills/mw-rag/SKILL.md`（`pathlib.Path(__file__).parent`），不要依赖 cwd。
- 目标路径是 pi 的项目级 skill 位置（`docs/skills.md:30` 确认 `.pi/skills/` 下根 `.md` 即独立 skill）；`.pi/skills/mw-rag.md` 不在受保护配置集合内，但**只有显式 `mw rag sync` 才写**（D-014）。
- 测试运行：`packages/multi-workers` 下 `python -m pytest test_rag_cli.py -q`。

## 完成判定

- `test_rag_cli.py` 全绿，输出含 `[VERIFY] VC-023`（`sync_installed=true sha_match=true`；`activate_no_write` 由 T-04 的 VC-001 断言补全）。
- 既有 `test_serve_doctor.py` / `test_mw_*.py` 零修改通过（doctor 段为**新增**，不改既有段的文本）。
