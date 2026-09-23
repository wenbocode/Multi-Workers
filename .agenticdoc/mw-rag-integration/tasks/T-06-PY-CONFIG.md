# Task T-06-PY-CONFIG: Python 侧 RAG 配置解析 / 渲染 / token env 名集 / 跨平台路径

## 基本信息
- Stage: 4
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型，Python stdlib + 既有 PyYAML）
- ac_refs: [AC-002, AC-009]
- vc_refs: [VC-024, VC-013]
- pattern_refs: []

## 描述

### 源码

在 `packages/multi-workers/mw_common.py` 新增一节（照既有 "Dispatch model config" 一节 196-243 的形状写：函数内 `import yaml  # PyYAML: implicit dep …`，`(value, error)` 返回约定，**配置问题永不阻断派发**）：

```python
def rag_servers_path(project_root: pathlib.Path) -> pathlib.Path:      # <root>/.mw/rag-servers.yml
def machine_rag_servers_path(env: Mapping[str, str] | None = None) -> pathlib.Path | None
def load_rag_config(project_root: pathlib.Path) -> tuple[dict, str | None]
def rag_token_env_names(config: dict) -> set[str]
def render_rag_block(config: dict, task_meta: dict) -> str | None
def rag_fingerprint(config: dict, enabled: list[str] | None = None) -> str
```

要点（**与 TS 侧语义逐条对齐**，这是两侧 parity 的一部分）：
- **机器级路径（D-013）**：`MW_RAG_SERVERS_FILE`（整文件覆盖，测试钩子）→ `MW_RAG_SERVERS_HOME` + `/.agents/rag-servers.yml` → `HOME` → `USERPROFILE`；均缺失/不存在 → `None`（该层视为空，**不创建**）。
- **项目级**：`project_root/.mw/rag-servers.yml`；`target.yml` 的 `rag:` 段（`project_root/.agenticdoc/target.yml`，沿用既有 `yaml.safe_load` 读法）提供 `enabled`/`defaultServer`/`roles`/`phases`/`budgets`。
- **逐字段合并（D-003）**：按 server 名对齐；标量/嵌套 dict 逐键覆盖；**数组整体替换**；`None` = 显式删除字段；`origin` 逐字段标注（`machine`/`project`）。
- **校验**（返回 error 字符串，不抛）：`enabled` 引用未定义 server、mcp 无 url、skill 无 `cli_entry`、顶层未知键。错误消息含 server 名与可见列表。
- **`rag_token_env_names(config)`**：返回配置中所有 `mcp.token_env` 名（**只返回 env 名集合，绝不返回值**），供 launcher 剥离与注入使用（T-07）。
- **`render_rag_block(config, task_meta)`**：`config["enabled"]` 为空 → `None`（**一个字节都不写**）；否则返回与 TS `renderRagBlock` **逐字节一致**的块（含 `<!-- mw-rag: v1 -->` marker、可用服务、必需角色/阶段、默认 server/source、rewrite 默认、chat 预算、累计时间预算、引用语法一行、`fingerprint=<sha256>`）。源文件：`packages/multi-workers/test/fixtures/rag-block.golden.md`（由本任务产出并被 TS 侧断言）。
- **`rag_fingerprint`**：`hashlib.sha256` over 规范化 JSON（与 TS 的 canonical JSON 约定一致：键排序、无空白、`ensure_ascii=False`、浮点/整数归一）；范围同 design D-009（仅启用集静态字段 + `path_roots` 文件内容摘要 + 解析结果 + 预算；排除探活/未启用 server）。

### 测试

新增 `packages/multi-workers/test_rag_config.py`（`unittest`，照 `test_autopilot_config.py` 风格；用 `tempfile.TemporaryDirectory` + `MW_RAG_SERVERS_FILE` 注入机器层）：

- **合并矩阵（VC-024）**：机器层 A 全字段 + 项目层仅覆盖 `mcp.url` → `url` 为项目值、`token_env`/`timeout_ms`/`capabilities`/`sources` 继承、`origin` 逐字段；`sources: []` 清空；`skill: null` 删除；机器层 B 不受影响；**同一 fixture 在 TS 侧（T-01 测试）产出同一结论**（两侧断言用的输入 fixture 保持同形）。
- **token 名集（VC-013）**：`rag_token_env_names` 只含 env 名；断言返回值中**不含**任何形如 `SECRET…` 的值（测试同时把 env 值设为 `SECRET123` 并断言渲染块与错误消息里 `SECRET123` 命中 0）。
- **渲染 golden**：对固定 fixture 生成 `test/fixtures/rag-block.golden.md`；断言二次运行逐字节相等（幂等）；`enabled: []` → 返回 `None` 且**未创建任何文件**。
- **路径解析（D-013）**：`MW_RAG_SERVERS_FILE` 优先于 `MW_RAG_SERVERS_HOME`；`HOME` vs `USERPROFILE` 分别 stubbed（`unittest.mock.patch.dict(os.environ, …)`）时可解析；目录不存在 → `None` 且不创建目录。
- **指纹**：改 `mcp.url` → 变；改 path_roots 文件内容 → 变；改未启用 server → 不变；`MW_RAG_SERVERS_FILE` 不变时两次调用相等。

### 注意

- 只用 stdlib；`yaml` 走**函数内 import**（与 `load_dispatch_config` 一致，既避免顶层硬依赖又复用既有隐式依赖）。**不新增 pip 依赖**。
- 键命名：配置 YAML 用 snake_case（`token_env`/`timeout_ms`/`path_roots_file`/`cli_entry`），TS 侧读同一份 YAML 时做 camelCase 映射——两侧映射表必须在测试里各有一份显式断言，防止漂移。
- 本任务**不改** `autopilot/dispatch.py`（rag 块注入在 T-07）、**不改** `REGISTRY`（T-09）。
- 测试运行：`packages/multi-workers` 下 `python -m pytest test_rag_config.py -q`。

## 完成判定

- `test_rag_config.py` 全绿，输出含 `[VERIFY] VC-024`、`[VERIFY] VC-013`。
- `test/fixtures/rag-block.golden.md` 生成并与二次渲染逐字节一致。
- 既有 `test_autopilot_config.py` / `test_mw_*.py` 零修改通过。
