# Research: Python 侧模型视觉能力探针最小契约（DESIGN RQ-D2）

## TL;DR
- P1（解析既有 `pi --list-models`，不动 pi 核心）**可行且已实测**：`shutil.which("pi")` → `...\npm\pi.CMD`；带/不带 pattern 均 rc=0、0.80–0.96s；六列表 `provider model context max-out thinking images`，列间 2 空格填充、宽度动态、无 `?`/`-` 占位；按 (provider, model) 两列精确相等取值即可消除模糊匹配多行。
- 建议：在 `mw_common.py` 加**进程内记忆化的一次性快照探针**（一次 `pi --list-models` 全量建 map，而非每角色一次子进程），返回 `"yes"|"no"|"unknown"`，由 `cmd_model`（`mw.py:3136`）与 `_doctor_dispatch`（`mw_common.py:1256`）共用；不可用一律 `unknown` + skip，绝不阻塞。
- 探针只落在 `mw model set/show`、`mw doctor` 三个**一次性命令**上，不在 `mw serve` 常驻热路径（`doctor_report` 仅 `mw.py:518/4515` 调用）→ `/mw restart` 后常驻进程零影响。
- `--force` 插在 `model_set_p`（`mw.py:5127`，`action="store_true"`）；"仅 vision 生效"的校验放命令层 `cmd_model` set 分支（`mw.py:3143`），不放 argparse。

## 决策问题
- Q1 Python 侧调用外部 CLI 的既有范式（参数、超时、Windows creationflags、编码、非零 rc）。
- Q2 探针命令形态与解析规则（which 结果、列名/列宽、占位符、模糊多行时的精确取值）+ 真实输出证据。
- Q3 探针放哪、三个调用点如何共用、缓存范式、超时预算与 fail-open 返回值定义。
- Q4 `mw model set --force` 的 argparse 插入点与"仅 vision 生效"的校验层。
- Q5 测试如何 monkeypatch `shutil.which` / `subprocess.run` 覆盖 yes/no/unknown（现有先例）。
- Q6 探针耗时/失败率对 `/mw restart` 后常驻进程的影响（是否热路径）。

## 调研方法与出处
- 只读源码全文/邻域：`mw.py`、`mw_common.py`、`launcher.py`、`autopilot/{dispatch,conductor}.py`、`cli/list-models.ts`、`pm/ui-bridge.ts`；测试：`test_dispatch_models.py`、`test_launcher.py`、`test_common.py`、`test_autopilot_config.py`、`test_serve_doctor.py`、`test_doctor_autopilot.py`、`test_mw_bootstrap.py`。
- 本地无副作用命令（未发 LLM 调用、未打印任何凭证值）：`shutil.which("pi")`、`pi --version`、`pi --list-models [pattern]`、`python` 解析验证。
- 参考：`spec-capability-gate-hooks-20260926.md`（RQ-2 F3：Python 侧无能力数据源）、`spec-vision-io-and-candidates-20260926.md`（RQ-4 F4：目录来源）。

## 发现

### Q1 既有 CLI 调用范式（`file:line`）
- 解析可执行：`launcher.py:444-459` `_resolve_cli`——Windows `subprocess` shell=False 只补 `.exe`，必须用 `shutil.which` 拿 `.CMD`；`_spawn` 先把 `cmd[0]` 换成解析结果（`launcher.py:948-949`）。**探针必须照此，禁止直接 `["pi", ...]`。**
- 短探测首选：`mw.py:4244-4251` `_run_capture`：`subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout)`，`except (OSError, subprocess.TimeoutExpired) -> None`。同文件 `:4429-4432`/`:4450` 已有 `shutil.which("pi")` + `_run_capture([pi_bin,"--version"])` 先例。
- 短探测 + fail-open：`mw_common.py:1621-1627` `port_owner_pids`：`subprocess.run(cmd, capture_output=True, text=True, timeout=5)`，`except (OSError, subprocess.SubprocessError) -> []`——5s 预算与"失败返回空"的现成范式。
- 其它：`mw.py:3573-3579` `_git`（capture/text，无 timeout）；`mw.py:1016` `shell=True`（反面样例，勿用）。
- `creationflags`：仅 `Popen` 有先例（`launcher.py:964-965`、`mw.py:275`、`mw.py:436`），`subprocess.run` 全仓无先例。`mw` 命令在既有控制台内运行，子进程继承控制台，不弹新窗；若实测有闪窗再补 `subprocess.CREATE_NO_WINDOW`（需与既有 `# type: ignore[attr-defined]` 写法一致）。
- 非零 rc 无统一封装，惯例是调用方判定（`mw.py:4054-4056`）；探针应把 `rc != 0` 归入 `unknown` 而不抛错。

### Q2 探针命令与解析规则（含原始输出）
```
$ python -c "import shutil; print(shutil.which('pi'))"
C:\Users\wenbozhou\AppData\Roaming\npm\pi.CMD            # 注意 .CMD；pi --version = 0.83.0

$ pi --list-models timi deepseek-v4-flash-vision-exp     # 0.80s, rc=0
provider  model                         context  max-out  thinking  images
timi      deepseek-v4-flash-vision-exp  200K     64K      no        yes

$ pi --list-models glm-5.3                               # 0.88s, rc=0（模糊：4 行 / 2 provider）
provider       model              context  max-out  thinking  images
timi           glm-5.3            200K     64K      no        no
timi           glm-5.3-flash      200K     64K      no        no
zai-coding-cn  glm-5.3            1M       131.1K   yes       no
zai-coding-cn  glm-5.3-flash      1M       131.1K   yes       yes

$ pi --list-models zzz-nope                              # rc=0
No models matching "zzz-nope"

$ pi --list-models                                       # 0.86s, rc=0, 31 条数据行（timi 23 + zai-coding-cn 8）
```
- 列定义与顺序来自 `packages/coding-agent/src/cli/list-models.ts:65-72`；宽度按列动态计算（`:75-89`）、`.join("  ")` 两空格（`:91-99`）；`thinking`/`images` 只有 `yes|no`（无 `?`/`-`）。
- **噪声行**：worker 环境（`PI_WORKER_TASK` 已设）下 `pi` 会先输出一行 `[worker] start task=... type=... phases=...`（扩展 stdout）。解析器不得假定表头在第 0 行。
- 解析规则（建议）：数据行 = 按空白 split 恰为 6 token，且 `tokens[2]`/`tokens[3]` 匹配 `^\d+(\.\d+)?[KM]$`、`tokens[4]`/`tokens[5]` ∈ `{yes,no}`；再要求 `tokens[0] == provider and tokens[1] == model_id` 精确相等。模糊匹配返回的多行由此自动过滤。
- provider 取值：`prefix` → `MODEL_PREFIX_TO_PI_PROVIDER`（`mw_common.py:124-130`，`zai→zai-coding-cn`、`claude→anthropic`、`codex→openai-codex`）；`codex_cli`/`claude_cli`（`:131-133`）与裸 id（`parse_model_value` `:259-265` 返回空前缀）→ `unknown`。
- `--list-models` 只列**已认证 provider**（实测全量仅 timi/zai-coding-cn；`deepseek`/`anthropic` 行不存在）→ 未认证或前缀不可映到 pi provider 时"行缺失"= `unknown`，不是 `no`。
- 建议命令形态：**一次 `pi --list-models` 全量快照**建 `{(provider, model): images}`（0.86s，覆盖 doctor 全部角色），单值调用可用 `pi --list-models "<provider> <id>"` 兜底；两者解析同一函数。输出仅含 provider/model/数字能力，无凭证。

### Q3 放置 / 共用 / 缓存 / 超时 / fail-open
- 放置：`mw_common.py`（`_doctor_dispatch` 已在此，`mw.py` 以 `mw_common.` 调用）。调用点：`cmd_model` set（`mw.py:3139-3159`，写配置前判定）、`cmd_model` show（`mw.py:3219-3233` 每角色追加 `images=`）、`_doctor_dispatch`（`mw_common.py:1256-1272` 每角色 `images`）与 `format_doctor_text`（`mw_common.py:2298-2308` 的 `dispatch:` 行）。
- 缓存：spec §2.2 只要求同进程记忆化 → module-level dict 足够（一次快照即缓存）；跨进程（`model show` 与 `doctor` 是两个进程）若要复用，照搬 `.mw/toolchain.json` 范式：`toolchain_probe_path`（`mw_common.py:3215-3217`）+ fingerprint + `probed_at_epoch >= yml_mtime` 判新鲜（`:3420-3449`）。**本期建议不新增缓存文件**，仅进程内记忆化。
- 超时预算：`MODEL_PROBE_TIMEOUT_S = 5.0`（spec §2.2 上限；实测 0.80–0.96s）。一次快照 → 每命令最多一次子进程、最坏 5s，不叠加。
- fail-open 精确定义：返回 `"yes"`/`"no"` **仅当**精确命中一行；`"unknown"` 覆盖：`which("pi") is None`、`OSError`/`TimeoutExpired`、`rc != 0`、stdout 无任何可解析数据行、0 命中、CLI 前缀、裸 id。doctor 把 `unknown` 渲染为 skip 行（非 issue 非 error、退出码 0）；`mw model set` 的 `unknown` 打印一行 skip 并 rc=0 写入。

### Q4 `--force` 插入点与校验层
- 插入点：`mw.py:5127-5132` `model_set_p`，加 `model_set_p.add_argument("--force", action="store_true", help="...")`（同仓 `--force` 风格：`mw.py:5190`、`:5207`）。
- 校验层：命令层 `cmd_model` 的 set 分支（`mw.py:3143-3152`，紧跟现有 role/prefix 校验）：`if getattr(args, "force", False) and role != "vision": 报错 rc=1`（AC-013 允许"报错或忽略并回显"，取报错以保证确定性）。
- 不建议依赖 argparse 做"按 role 条件校验"：role 是位置参数，argparse 层无廉价条件钩子，且探针判定本身在命令层。注意 `test_dispatch_models.py:423-425` 的 `_model_args` 直接构造 Namespace，新增 flag 后需补 `force=False`（或用 `getattr` 兜底，二者取一）。

### Q5 测试注入点（三分支：yes/no/unknown）
- 推荐给探针留注入 seam，同仓先例 `ensure_pi_shell_path(..., detect=None)`（`mw_common.py:1276-1281`，"injectable for cross-platform tests"）：`model_capabilities(..., which=None, run=None)`，None 时回落 `shutil.which`/`subprocess.run`。
- `shutil.which` patch 先例：`test_launcher.py:439`（which→`C:\npm\codex.CMD`）、`test_common.py:215/270/280`（which→None）、`test_serve_doctor.py:96`（fixture 强制 None）。
- `subprocess.run` patch 先例：`test_autopilot_config.py:384-390`（`real_run = subprocess.run` + spy + `monkeypatch.setattr(adv.subprocess, "run", spy)`）。
- 更高层注入先例：`test_doctor_autopilot.py:322-328`、`test_mw_bootstrap.py:90-91` patch `mw._run_capture`；建议探针单测直接 patch seam，避免真实 spawn pi。
- fixture 建议：which→None = unknown；run 返回伪造 stdout（`... yes`/`... no`）= yes/no；run 抛 `TimeoutExpired` = unknown。

### Q6 热路径影响
- `doctor_report` 仅被 `mw.py:518`（`cmd_doctor`）与 `mw.py:4515`（bootstrap step 8）调用；`mw serve`/launcher/conductor/dispatch 全仓零引用 `doctor_report` 或 `pi --list-models`（grep 无命中）。
- PM 的 `/mw doctor` 与 `/mw model show|set` 都是用户命令（`pm/ui-bridge.ts:1983/2029/2133-2139`），不在派发链（`planDispatchFrontmatter` 用 TS registry，不走 Python 探针）。
- 结论：`/mw restart` 后常驻进程（proxy/launcher/conductor）不触发探针；成本只落在三个一次性命令，单次 ≤5s、实测 ~0.9s；`mw doctor` 因一次快照仍是单次子进程。

## 结论 → 决策映射
- 建议实现（`packages/multi-workers/mw_common.py`）：
```python
MODEL_PROBE_TIMEOUT_S = 5.0  # spec §2.2 上限；实测 0.8-0.96s

def model_capabilities(values: Sequence[str]) -> dict[str, str]:
    """One `pi --list-models` snapshot -> {value: "yes"|"no"|"unknown"}.
    Memoized per process; never raises; fail-open on which/timeout/rc/parse miss."""

def model_images(value: str) -> str:
    """Convenience single-value wrapper: 'timi/glm-5.3' -> "yes"|"no"|"unknown"."""
```
- AC-010：`_doctor_dispatch` 每角色加 `images`；`no` → issue（消息含 `mw model set vision`），`yes` → ok，`unknown` → skip（非 issue/error，rc=0）。
- AC-013：`cmd_model` set 对 `role == "vision"` 且非 `--force` 时调用 `model_images`；`no` → rc≠0 且不写盘，`yes`/`unknown` → 写盘（unknown 打 skip 行）。
- AC-015：`mw model show` 每角色行加 `images=`；探针不可用时 `unknown`，命令 rc=0。
- 复用 Q1 范式（`shutil.which` 解析 + `_run_capture` 风格 `subprocess.run` + `except (OSError, TimeoutExpired)`），不新增 provider/凭证面（GC-5），不动 pi 核心（GC-2）。

[VERIFY] `shutil.which("pi")` 在 Windows 返回 `.CMD` 全路径（本次 `...\npm\pi.CMD`）；直接 `["pi","--list-models"]` 会 WinError 2，必须用 which 结果（先例 `launcher.py:444-459`）
[VERIFY] `pi --list-models <pattern>` rc=0 且耗时为 0.80-0.96s；全量 31 行（timi 23 + zai-coding-cn 8）；`deepseek`/`anthropic` 行不存在（只列已认证 provider）
[VERIFY] worker 环境变量 `PI_WORKER_TASK` 存在时 `pi --list-models` 会先打印一行 `[worker] start ...`，解析必须按 token 形状过滤而非固定行号/表头位置
[VERIFY] `_doctor_dispatch` 只经 `doctor_report` 被 `mw.py:518` 与 `mw.py:4515` 调用；`mw serve`/launcher/conductor 不调用，探针不在常驻热路径
[VERIFY] `test_dispatch_models.py:423` 的 `_model_args` 直接构造 argparse.Namespace，新增 `--force` 后不补 `force=` 会 AttributeError（除非实现用 getattr 兜底）