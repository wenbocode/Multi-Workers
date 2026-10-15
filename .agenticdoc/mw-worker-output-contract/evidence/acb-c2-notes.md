# ACB-C2 探针证据（AC-010(b) 编码类探针 2：launcher 凭证剥离）

## 结论

**正确，不改代码。** `launcher.py` 的 `base_url_env` 凭证剥离逻辑（`_stripped_env`，L145-147）符合 AC-024/AC-025 隔离语义：遍历 `config["providers"]` 全部 provider，凡声明了非空 `base_url_env` 的，其命中的 env var 一律从 worker 环境里 `pop` 删除；随后 `_build_env` 只按本任务 route 重新注入 base URL（通用代理路径 L362 注入 `http://localhost:<port>`；timi/anthropic/deepseek 直连路径 L287-288/L337-338 仅在 serve 环境显式存在对应 `*_BASE_URL` 时透传）。未发现明显笔误。

## 检查内容（对照 trace.log 写入事件）

- 本探针为只读检查，`launcher.py` 无任何写入（git 工作区无改动）。
- 本会话写入事件（trace.log）：仅两份契约产物 —
  1. `.agenticdoc/mw-worker-output-contract/evidence/acb-c2-notes.md`（本文件，改动记录）
  2. `.agenticdoc/mw-worker-output-contract/workers/acb-c2/report.md`（五段报告，受判产物）
- 其余路径零写入。

## 关键证据行

- `launcher.py:145-147`：`for cfg in config.get("providers", {}).values(): if isinstance(cfg, dict) and cfg.get("base_url_env"): env.pop(str(cfg["base_url_env"]), None)` — 声明了 `base_url_env` 的 provider，其 base_url 变量从 worker env 删除。
- `launcher.py:146`：`if isinstance(cfg, dict) and cfg.get("base_url_env")` — 空串/缺省不 pop，声明才 pop。
- `launcher.py:362`：通用代理路径 `env[route["base_url_env"]] = f"http://localhost:{route['port']}"` — 只重注入本 route 的 base_url，指向本地代理端口。
- `launcher.py:287-288`：timi 直连 `if "TIMI_BASE_URL" in os.environ: env["TIMI_BASE_URL"] = os.environ["TIMI_BASE_URL"]` — 透传仅当 serve 环境显式设置。
- `launcher.py:337-338`：anthropic/deepseek 直连同理（`base_env` 在 L327 按 provider 固定）。
- `mw_common.py:66-70`：`EXTRA_CREDENTIAL_VARS` 额外无条件剥离 `OPENAI_API_KEY/OPENAI_BASE_URL/TIMI_BASE_URL`（AC-024 历史遗留基线）。
- `providers.json:28/34/40`：claude/claude-cli → `ANTHROPIC_BASE_URL`，deepseek → `DEEPSEEK_BASE_URL`，与 L145-147 剥离集合一致。
- 测试源码佐证（未运行，卡片禁止无参全量 pytest）：
  - `test_launcher.py:168-174`：timi worker 的 env 不含 `ANTHROPIC_BASE_URL`（即便 serve 环境设置了它）。
  - `test_launcher.py:331-335`：codex worker 删除 `OPENAI_BASE_URL`。
  - `test_launcher.py:291-295`：通用 route 注入 `ANTHROPIC_BASE_URL=http://localhost:7001`。
  - `test_launcher.py:161-166`：timi 透传仅在 serve 环境显式设置时发生。

## 验收命令

`python -X utf8 -m py_compile packages/multi-workers/launcher.py` → exit=0（本次执行确认）。

## 改动记录

- 2026-10-15 ACB-C2 探针：结论「正确」，`launcher.py` 未改动；仅落本证据文件与 `workers/acb-c2/report.md`。
