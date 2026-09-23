# Task T-07-PY-INJECT: launcher env 注入/剥离 + 指纹撕裂 + conductor rag 块注入

## 基本信息
- Stage: 4
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: worker（`coding` 类型）
- ac_refs: [AC-003, AC-009]
- vc_refs: [VC-022]
- pattern_refs: []

## 描述

### 源码

1. `packages/multi-workers/launcher.py`
   - `_stripped_env(config)`（:90-103）增加：先剥离**全部**配置声明的 RAG token env 名（`mw_common.rag_token_env_names(rag_cfg)`），再加既有的 provider 凭据剥离——保持它仍是"生产代码唯一的 `env.pop` 点"（ref-verify 已证；不要新增第二个剥离位置）。
   - 新增 `inject_rag_env(env, entry, project_dir) -> None`：在 `_spawn` 的 `env = _build_env(effective, config)`（:829）之后**作为 post-step** 调用（`_build_env` 有 5 个早返回分支 + 末尾通用代理返回，共 6 个返回路径，post-step 一次覆盖，不改任何分支）。语义：
     - 逐启用 server，若其自定义 `token_env` 名在 `os.environ` 中有值 → 注入该 env（**值只从 serve 进程环境取，绝不写入 task.md / 日志 / trace**）；
     - 注入指向本地/远端 RAG 的少量非敏感配置（如 `MW_RAG_ENABLED` = 逗号分隔启用集），**不含任何 token 值**；
     - 未启用 → 不注入任何变量（未启用 worker 的 env 与改造前逐项相同）。
     - 同样在 :891 的第二处 `_build_env`（打印/预检路径）后调用，保证两条路径一致。
   - 新增 `check_rag_tear(entry, project_dir) -> None`：读 task.md 的 `<!-- mw-rag: v1 -->` 块内 `fingerprint=<sha>`，用 `mw_common.rag_fingerprint(...)` 重算并比对；不一致 → raise `RuntimeError("config torn (rag): ...")`（照 `_check_config_tear`（:647-671）的形状与消息风格），由 `_spawn` 既有的 per-task 错误处理标记任务 failed 并落 `[LAUNCHER]` 证据。**无 rag 块 → 直接返回**（未启用路径零行为变化）。调用点：`_spawn` 内 `_check_config_tear(entry, target_config)`（:826）之后。
   - 语义边界（D-009）：只比静态配置（启用集 server 的 url/token_env 名/skill 路径/path_roots 内容摘要/预算/解析结果）；**服务重启、探活状态变化、未启用 server 改动都不算撕裂**。

2. `packages/multi-workers/autopilot/dispatch.py`
   - `render_task_md`（:105 区，生产侧唯一 task.md 生成器）在既有 profile 块之后追加 `mw_common.render_rag_block(config, task_meta)` 的返回值（`None` 则不追加）；同一锚点、同一 marker，重复渲染幂等（marker 整体替换）。
   - 保持 `/mw` 与 conductor 两条路径注入同一文本（golden 对齐）。

### 测试

新增 `packages/multi-workers/test_rag_launcher.py`：

- **env 注入（AC-009）**：构造启用 A（`token_env: OVERCODE_MCP_TOKEN`）的配置 + `os.environ` 中有该值 → `inject_rag_env` 后 env 含该名；`MW_RAG_ENABLED` 只含启用集；**断言不含其它未启用 server 的 token env 名**（凭证隔离，GC）。
- **剥离**：`_stripped_env` 对含全部 provider 凭据 + RAG token env 的入参 → 输出既不含 provider 凭据也不含 RAG token env 名；未启用 RAG 时输出与改造前一致（golden 快照）。
- **撕裂正反例（VC-022）**：以 fixture 配置渲染 task.md → `check_rag_tear` 通过；把配置里的 `mcp.url` 改掉（或改 path_roots 文件内容）→ 抛 `RuntimeError` 且消息含 `config torn (rag)`；只改**未启用** server 的字段、或翻转探活/健康字段 → 通过。
- **无块兼容**：task.md 无 rag 块 → `check_rag_tear` 直接返回、`inject_rag_env` 不注入 RAG 变量。
- **dispatch 注入**：`render_task_md` 对启用配置产出与 `test/fixtures/rag-block.golden.md` 中该块**逐字节一致**；连续两次渲染结果相同（幂等）。

### 注意

- **T-06 交接细节（必须遵守）**：`render_rag_block` 返回的块**无尾换行**；追加到 task.md 时用 `content.rstrip() + "\n\n" + block + "\n"`；`load_rag_config` 已在 load 时算好 `path_roots_digest` 并已进指纹，`check_rag_tear` 直接用 `mw_common.rag_fingerprint`，不要另算一套；golden 为 `test/fixtures/rag-block.golden.md`（347 B）。
- 不要在 6 个 `_build_env` 返回分支里各加一段注入代码（重复且必漏）；只加 post-step。
- token 值绝不出现在 task.md / trace / worker.log / argv（`inject_rag_env` 只写 env；argv 由既有 `_starter_prompt` 机制保证不含任务体）。
- 测试运行：`packages/multi-workers` 下 `python -m pytest test_rag_launcher.py -q`。

## 完成判定

- `test_rag_launcher.py` 全绿，输出含 `[VERIFY] VC-022`（`torn_refused=true unrelated_change_ok=true health_excluded=true`）。
- 既有 `test_autopilot_config.py` / `test_partition_dispatch.py` / launcher 相关用例零修改通过。
