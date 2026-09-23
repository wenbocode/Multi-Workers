# Achieved: mw-rag-config-guide

## 需求（用户原话要点）

1. RAG/MCP 配置的**详细手册**：每个配置文件都有可直接复制粘贴修改即用的示例，**每个字段都要有注释说明**（例如 `sources` 是干什么的）。
2. **一条命令快速创建**这些配置文件：无输入时按示例写成模板，让用户改。

## 交付物

| 文件 | 说明 |
|---|---|
| `packages/multi-workers/rag_templates.py`（新，282 行） | 三份模板文本的唯一来源（`render_servers_template` / `render_target_rag_template` / `ROOTS_TEMPLATE`）；无 I/O、无 `input()` |
| `packages/multi-workers/mw.py`（改） | `mw rag init` 子命令 + 参数（`--server/--url/--token-env/--transport/--enable/--machine/--only-machine/--no-roots/--force/--dry-run/--print`）；文本级追加/替换 `rag:` 段（绝不 YAML round-trip） |
| `packages/multi-workers/docs/rag-config-guide.md`（新，519 行 / 31.8 KB） | 配置手册：① 3 分钟上手 ② 三个文件的角色与优先级 ③ **逐字段表 25 行 × 4 列**（是什么/取值与默认/举例/写错的后果） ④ 四类可复制示例 ⑤ 命令与退出码 ⑥ 五层成功判据 ⑦ 失败 signature ⑧ 已知坑 ⑨ FAQ；附录两个模板块逐字取自 `--print` |
| `packages/multi-workers/test_rag_init.py`（新，12 测试） | `init` 行为：零交互、拒绝/`--force`、`--dry-run`/`--print` 纯读、字段覆盖、机器层、roots 默认可用、`--no-roots` |
| `packages/multi-workers/test_rag_docs.py`（新，5 测试） | 文档侧：手册字段表 == 校验器字段集、示例 YAML 真能被接受、roots 语义、**模板块字节 parity**、报错文本诚实性 |
| `packages/multi-workers/README.md`（+1 行） / 两包 `CHANGELOG.md`（`[Unreleased]/Added`） | 指向手册 |

## 命令

```bash
python mw.py rag init --project <dir>                    # 写三份带注释模板（默认 enabled: []，不探活）
python mw.py rag init --project <dir> --enable --server overcode --url http://localhost:8100/mcp/ --token-env OVERCODE_MCP_TOKEN
python mw.py rag init --project <dir> --no-roots          # 跳过 .mw/rag-roots.json 并注释该字段
python mw.py rag init --project <dir> --machine|--only-machine   # 机器层（显式请求才写）
python mw.py rag init --project <dir> --dry-run|--print  # 零写入，exit 0
```

退出码：`0` 成功（含 `--dry-run`/`--print`）/ `1` 拒绝或失败 / `2` 用法错误。

## 系统行为变化

1. **新增 `mw rag init`**：零交互生成三份带逐字段注释的模板；默认 `enabled: []`（占位服务不会被探活、不会注入任何 worker）。
2. **默认同时写 `.mw/rag-roots.json`**（`_README` 说明 + `"engine": "."` = 项目根）并激活 `path_roots_file` → 单仓场景开箱即可做磁盘核对（端到端实测 `citations=1 missing=0 unverified=0 audit_exit=0`）；`--no-roots` 才跳过并把该字段写成注释（不允许激活字段指向不存在的文件，D-209/D-210）。
3. **`target.yml` 的 `rag:` 段只在缺该顶层键时文本级追加**，`--force` 也只整段替换 `rag:`，其它段与注释原样保留（T-23 实测验证）。
4. **拒绝覆盖**：已存在的 servers 文件 / 已有 `rag:` 段 / 已存在的 roots 文件，未给 `--force` 一律 exit 1 且零写入。
5. **手册与实现用字节 parity 绑定**：手册模板块必须等于 `mw rag init --print` 输出，字段表必须等于校验器接受的字段集，否则测试变红（三条反例已证明可证伪）。
6. **文档驱动的两处修正**：手册散文与实现不符时以**实现**为准（`rag-unavailable` 的 `kind` 补全 `tool`/`capability`；`skill.dir` 的 TS 侧限制如实标注）。
7. **测试编码健壮性**：`test_rag_init.py` 的 subprocess 显式 `encoding="utf-8"`，本机 `PYTHONIOENCODING=utf-8` 下不再假红。

## 证据

- `evidence/verify-run-2026-09-22.md`（T-23 独立验证，110 行）：基线复现 + 三条反例（全红 + sha256 复原）+ 17 条散文抽查 + 四类示例可执行性 + 未覆盖项。
- `evidence/quality-gate-report-2026-09-23.md`（本报告）：20 充分 / 3 ⚠️ / 0 ❌。
- 14 条 `[VERIFY]` 行（见 T-23 报告 §0），默认编码与 `PYTHONIOENCODING=utf-8` 下逐字相同。

## 零回归

- `python -m pytest -q` = **839 passed, 9 deselected**；`npm run check` exit 0（biome 1080 files, `No fixes applied`）。
- `test/fixtures/*`、`test_autopilot_l0.py` 零 diff；未改 `rag/*.ts`、未改 `mw_common.py` 语义、未触真实 HOME。

## 遗留

- **R-1**：`skill.dir` 跨语言不一致（Python 收 `null`/缺省，TS `requireString` 要求非空）——建议 TS 改 `optionalString`，需在 coding-agent 侧改动 + 测试。
- **R-2**：pi 窗口内无 `/mw rag ...`，`/mw doctor` 不渲染已在 JSON 里的 `report.rag`（候选新 key）。
- **R-3**：真实 RAG 服务联调（本机 `127.0.0.1:8100/mcp/` 存活、无认证挑战，但未带 token 走完整工具调用）。
- **R-4**：`--machine` 在真实 HOME 的行为未验。
- **R-5**：手册散文没有结构性防漂移（模板块/字段表/3 条报错串有锁）。
