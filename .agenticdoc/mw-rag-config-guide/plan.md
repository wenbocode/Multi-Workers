# Plan: mw-rag-config-guide

## 目标

交付 `mw rag init`（零交互、生成可改模板）+ 逐字段配置手册，并用 parity 测试把手册与校验器/CLI 输出钉在一起。

## 阶段划分

| Stage | 内容 | 退出条件 |
|---|---|---|
| 1 | 命令与模板（T-21）：`rag_templates.py` + `mw.py` 的 `rag init` + `test_rag_init.py` | 模板被 `load_rag_config` 真解析；AC-201/202/203 绿；`[VERIFY]` 实测行落盘 |
| 2 | 文档（T-22）：`docs/rag-config-guide.md` 手册 + README 指向 + CHANGELOG + 手册 parity 测试 | AC-204/205/206 绿；`--print` 与手册 fenced 块字节一致 |
| 3 | 验证（T-23）：独立验证报告（含反例：改字段不改手册 → parity 红） | AC-207 绿；`evidence/verify-run-*.md` 落盘 |

## 任务表

| ID | Stage | 内容 | ac_refs | vc_refs | 依赖 |
|---|---|---|---|---|---|
| T-21 | 1 | `mw rag init` + 模板常量 + 测试（含零写入/幂等/零交互/字段覆盖） | AC-201, AC-202, AC-203, AC-204(部分) | VC-201, VC-202, VC-203, VC-204, VC-205, VC-207, VC-208 | 无 |
| T-22 | 2 | 手册 `docs/rag-config-guide.md`（逐字段 + 四类示例 + 命令/验证/坑）+ README 指向 + 两包 CHANGELOG + 手册 parity 测试 | AC-204, AC-205, AC-206 | VC-205, VC-206, VC-209 | T-21（需 `--print` 真实输出） |
| T-23 | 3 | 独立验证：全套件 + 三条反例（改模板不改手册 / 删手册字段 / 模板默认启用）+ 报告 | AC-207 | VC-201~VC-210 | T-21, T-22 |

## 并行与所有权

- T-21 与 T-22 **不并行**：手册必须引用 T-21 的真实 `--print` 输出（否则就是手抄，正是 D-201 要避免的）。
- T-21 拥有：`rag_templates.py`、`mw.py`（仅 `_cmd_rag_init` 与 argparse 段）、`test_rag_init.py`。
- T-22 拥有：`docs/rag-config-guide.md`、`README.md`（RAG 段加一行指向）、两包 `CHANGELOG.md`、`test_rag_docs.py`。
- T-23 只读，只写自己的报告文件。

## 风险

| 风险 | 缓解 |
|---|---|
| 追加 `rag:` 段毁掉 `target.yml` 其它内容 | 只在无 `rag:` 键时文本追加；测试断言其它段字节不变（VC-203 的目录树快照 + 段级 sha） |
| 模板里出现校验器不接受的字段 | VC-205 双向断言（校验器集合 ⊆ 模板；模板键 ⊆ 手册字段表） |
| 手册与 CLI 输出漂移 | VC-206 字节 parity；T-23 反例（改模板不改手册必须变红） |
| 命令在无 stdin 环境挂起 | VC-204 用 `stdin=DEVNULL` 跑真进程 |
| 误写用户 HOME | 测试全程用 `MW_RAG_SERVERS_HOME` 指向临时目录（VC-207） |
