# T-10 Python 能力探针（`pi --list-models` 快照）

- key: mw-vision-role · 波 1 · 独占写面：`packages/multi-workers/mw_common.py`（探针段，新建；邻 `:1276` 的 seam 风格）、`packages/multi-workers/test_common.py`（新增用例）
- ac_refs: AC-010, AC-013 · vc_refs: VC-010, VC-013
- 依赖: T-01（同文件串行于表段） · 预估: 60-90min

## 目标

提供唯一的 Python 侧能力判据，供 `mw model set`（T-11）、`mw model show`/`doctor`（T-12）共用。

## 契约（逐字遵守）

```python
MODEL_PROBE_TIMEOUT_S = 3.0   # spec §2.2 上限 ≤5s；doctor 自承诺 <5s，故取 3s（实测 0.8-0.96s）

def model_capabilities(values: Sequence[str], *, which=None, run=None) -> dict[str, str]:
    """One `pi --list-models` snapshot -> {value: "yes"|"no"|"unknown"}. Memoized; never raises."""

def model_images(value: str, *, which=None, run=None) -> str:
    """Single-value convenience wrapper."""
```

- 子进程范式照抄：`launcher.py:444-459` 的 `shutil.which` 解析（**禁用**裸 `["pi", ...]`，Windows 会 WinError 2）+ `mw.py:4244-4251 _run_capture` 风格（`capture_output=True, text=True, encoding="utf-8", timeout=...`）+ `except (OSError, subprocess.TimeoutExpired) -> None`（参考 `mw_common.py:1621-1627` 的 fail-open 惯例）
- 命令形态：一次**全量** `pi --list-models`（31 行 / 0.86s）建 `{(provider, model): images}`；单值调用可复用同一快照
- provider 映射用现成 `MODEL_PREFIX_TO_PI_PROVIDER`（`mw_common.py:124-130`）；`parse_model_value`（`:259-265`）返回空前缀 ⇒ `unknown`
- 解析规则：数据行 = `split()` 恰 6 token 且 `tokens[2]/tokens[3]` 匹配 `^\d+(\.\d+)?[KM]$`、`tokens[4]/tokens[5] ∈ {yes,no}`；再要求 `tokens[0] == provider and tokens[1] == model_id` **精确相等**（模糊匹配会返回多行）
- worker 环境下 `pi` 会先输出 `[worker] start ...` 噪声行 ⇒ **按 token 形状过滤，不按行号**
- `unknown` 覆盖：`which→None` / `OSError` / `TimeoutExpired` / `rc != 0` / 无任何数据行 / 0 命中 / CLI 前缀（`codex_cli`/`claude_cli`）/ 裸 id
- **缺失 ⇒ `unknown`（不是 `no`）**：`--list-models` 只列已认证 provider
- 进程内记忆化（module-level dict）；**不新增缓存文件**

## 步骤

1. 实现探针（含 `which=None, run=None` 注入 seam，风格同 `ensure_pi_shell_path(..., detect=None)` `:1276-1281`）。
2. `test_common.py` 新增三分支用例（`monkeypatch` seam）：which→None ⇒ unknown；fake run 返回含 `... yes` 表 ⇒ yes；返回 `... no` ⇒ no；fake run 抛 `TimeoutExpired` ⇒ unknown；伪造 `[worker] start ...` 前置行 ⇒ 仍能解析。
3. 真实探针自检（本机有 `pi`）：`model_images("timi/deepseek-v4-flash-vision-exp") == "yes"`、`model_images("timi/glm-5.3") == "no"`、`model_images("nope/x") == "unknown"`。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_common.py -q -s
python -c "import mw_common as m; print(m.model_images('timi/deepseek-v4-flash-vision-exp'), m.model_images('timi/glm-5.3'), m.model_images('nope/x'))"
```

## 证据格式

`[VERIFY] VC-013: probe_yes=yes probe_no=no probe_unknown=unknown`（`print(..., flush=True)`）

## 非空洞对照

把"0 命中"归成 `"no"` ⇒ 未认证 provider 的模型会被误拒（T-11 的 fail-open 用例红）；去掉 `shutil.which` 直接用 `["pi"]` ⇒ Windows 下全部落 unknown（真实探针自检红）。

## 交付

`mw_common.py` 探针段 + `test_common.py` 用例 + 原始输出。
