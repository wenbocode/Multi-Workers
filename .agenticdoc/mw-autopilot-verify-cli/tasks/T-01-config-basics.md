# T-01 config.py 基础（13 键 / 去缓存短路 / 补默认键 / ensure_ascii=False）

- AC: AC-001, AC-003, AC-006, AC-012 · VC: VC-003, VC-016 · 波次: 1
- 写面（**只碰这两个文件**）：`packages/multi-workers/autopilot/config.py`、`packages/multi-workers/test_autopilot_config.py`

## 契约（plan.md §2.1/§2.2，逐字遵守）

- `DEFAULT_CONFIG["xkey_verify_cwd"] = ""`（第 13 键，顺序 = DEFAULT_CONFIG 序；docstring 字段表同步）。
- `load_config(project_root) -> dict`：**校验作用于原始 data**，返回 `{**default_config(), **data}`（部分文件不再产生 KeyError）。
- `cached_load(project_root) -> dict`：= `load_config` + `json` 往返深拷贝；**删除 stat 短路与 `_CACHE`**。
- `invalidate_cache()`：保留名字，语义 = no-op（避免动其它测试）。
- `save_config(project_root, cfg) -> Path`：`json.dumps(indent=2, ensure_ascii=False) + "\n"`，tmp+replace 原子。
- `xkey_verify_cwd` 在 schema 层只校验"字符串"，**根名合法性留给解析期**（动态根名无法静态枚举）。

## 步骤

1. 新增第 13 键 + 类型登记（若无现成字符串类别，新增登记表并保持 `validate_config` 对未知键 fail-closed 不变）。
2. `load_config` 合并默认值（校验顺序不变：先校验原始 data，再合并）。
3. `cached_load` 去短路；删 `_CACHE` 与 `save_config` 里的 pop；`invalidate_cache` no-op。
4. `save_config` 改 `ensure_ascii=False`。
5. 测试：重写 `test_mtime_cache_invalidation`（**去掉 `os.utime` 依赖**，改"同字节长度裸字节写 + 不清缓存 ⇒ 必须读到新值"）；新增"partial 文件读取补全 13 键"用例；新增"写入含非 ASCII 命令后文件为 UTF-8 原样"用例。

## 验证（必须有实物输出）

- `python -m pytest -q test_autopilot_config.py` 全绿。
- **非空洞对照**：临时把 `cached_load` 改回 stat 短路 ⇒ 新用例必须**红**（记录该反证输出，证明用例有效）。
- `[VERIFY]` 行：13 键计数、同长度改写拾取、partial 补全、非 ASCII 字节。
