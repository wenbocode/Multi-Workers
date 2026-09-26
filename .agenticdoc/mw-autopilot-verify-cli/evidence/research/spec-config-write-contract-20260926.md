# RQ-2 证据：autopilot 项目配置（`_autopilot/config.json`）的读写契约与拾取语义

- key：`mw-autopilot-verify-cli`（spec 期 RQ-2）
- 日期：2026-09-26 · 执行者：worker `spec-rq2-config-write-contract`
- 性质：只读调研；唯一写面 = 本文件
- 环境：Windows NTFS · Python 3.14.3（MSC v.1944）· Node v24.19.0
- 关联 AC：AC-001/002/003/004/005/006/008

## 0. 结论速览

| # | 问题 | 结论 | 决定性依据 |
|---|---|---|---|
| 1 | `config.py` 语义 | 默认字典叫 `DEFAULT_CONFIG`（**没有 `DEFAULTS`**）；未知字段 fail-closed；`cached_load` 缓存键 = 解析路径 → `(st_mtime_ns, st_size)` | `config.py:44`、`:91-93`、`:166` |
| 2 | 谁在写 config.json | 生产环境**只有 TS console**（`autopilot enable/disable/pause/resume`）；Python conductor 只读、`mw init/setup/bootstrap` 不建；测试手写 | `console.ts:287,339`→`status-model.ts:234`；`mw.py` 零写入点 |
| 3 | 写后免重启拾取 | 结构上成立（conductor 每 tick 重新 `cached_load`，且 `enabled` 每 1s 复查）；**但 AC-002 的“mtime+size 失效”判据不健全**：外部同字节长度写入落在同一 `mtime_ns` 刻度时被静默忽略（实测 300 次里 100 次 stale） | `conductor.py:169,2036,3975`；`mw.py:161`；本节 §3 实测 |
| 4 | `xkey_verify_cmd` 空 | **不抛异常**；结构化 fail-closed：ticket → `verify_failed` + `escalation.md` + timeline `xkey-verify-failed`，且 `verify_failed` 属终端态、永不再入 | `conductor.py:3463-3468`、`3334-3369`、`3042/3044-3047`、`3636` |
| 5 | TS 镜像逐字段一致? | **不完全一致**：字段集/范围/未知字段一致；差异 = ①整值浮点 `4.0`（Python 拒 / TS 收）②partial 文件（Python 不合并默认 → tick error / TS 合并）③写盘规范化与非 ASCII 转义 | §5 差异表 |
| 6 | 新增键同步清单 | Python 4 处 + TS 6 处 + 消费点 + 文档；漏改任一侧 ⇒ 含新键的 config 直接被判非法（fail-closed） | §6 |
| 7 | AC-002/006/008 可机械判定? | 002 现判据不可靠、006 需差分类测试、008 当前无实现；§7 给可判定替代判据 | §7 |

## 1. `packages/multi-workers/autopilot/config.py` 完整语义

### 1.1 字段与默认（`DEFAULT_CONFIG`，`config.py:44-57`）

| 字段 | 类型 | 默认 | 范围/约束 | 行 |
|---|---|---|---|---|
| `enabled` | bool | false | — | 45 |
| `paused` | bool | false | — | 46 |
| `poll_interval_sec` | int | 4 | 1..5 | 47 / `:63` |
| `max_parallel_keys` | int | 2 | ≥2 | 48 / `:64` |
| `round_budget` | int | 2 | ≥1 | 49 / `:65` |
| `worker_timeout_min` | int | 30 | ≥1 | 50 / `:66` |
| `l2_read_file_cap` | int | 8 | ≥1 | 51 / `:67` |
| `l2_read_byte_cap` | int | 65536 | ≥1 | 52 / `:68` |
| `advance_stall_ticks` | int | 5 | 1..50 | 53 / `:69` |
| `xkey_repair` | bool | false | — | 54 |
| `xkey_verify_cmd` | list[str] | [] | 非空字符串列表 | 55 / `:61` |
| `xkey_verify_timeout_s` | int | 1800 | ≥1 | 56 / `:70` |

共 12 键。`default_config()`（`:81-83`）返回深拷贝（`json.loads(json.dumps(...))`），调用方可自由改。

### 1.2 `validate_config`（`config.py:86-119`）

- 根必须 JSON object：`:88-89` → `ConfigError("config root must be a JSON object")`。
- **未知字段 fail-closed 的确切位置：`config.py:91-93`**（`unknown = sorted(set(cfg) - set(DEFAULT_CONFIG))`，`:93` 追加 `unknown field(s): <逗号列表>`），最终由 `:118-119` 抛出 `ConfigError("invalid _autopilot/config.json: " + "; ".join(errors))`。错误信息一次性列出**所有**违规字段，不是首个。
- bool 字段：`:94-96`，要求 `isinstance(..., bool)`；JSON `1`/`"yes"` 均拒。
- list 字段：`:97-106`，必须是 list 且每项为**非空字符串**；空 list 合法，全空白字符串 `"  "` 也合法（无 trim）。
- int 字段：`:107-117`；`:111` 显式先拒 `bool`（bool 是 int 子类），再 `not isinstance(value, int)` → 于是 **JSON 的 `4.0`（float）被拒**（见 §5 差异）。
- 实测（本机）：
  - `{"cwd": "x"}` → `invalid _autopilot/config.json: unknown field(s): cwd`
  - `{"round_budget": 4.0}` → `round_budget: expected integer, got 4.0`
  - `{"round_budget": true}` → `round_budget: expected integer, got True`
  - `{"xkey_verify_cmd": []}` → OK；`{"xkey_verify_cmd": ["  "]}` → OK

### 1.3 `load_config`（`config.py:122-133`）

- 文件不存在：`:126-127` 返回 `default_config()`，**零足迹**（实测：调用后 `<root>/.agenticdoc` 仍不存在）。
- 读取/JSON 错：`:128-131` → `ConfigError("cannot read <path>: ...")`。
- `:132` `validate_config(data)`；**`:133` 直接返回原始解析对象，不与默认值合并**。
- 后果（实测）：`{"enabled": true}` 这样的 partial 文件通过了校验，但 `load_config` 只返回 `{"enabled": True}`；消费方取 `cfg["paused"]` 抛 `KeyError`。

### 1.4 `cached_load`（`config.py:150-170`）

- 缓存表：`_CACHE: dict[str, tuple[int, int, dict] | None] = {}`（`:73-74`），**进程内模块级**。
- 缓存键：`key = str(path.resolve())`（`:158`）→ 每项目一条。
- stat 失败（不存在）：`:161-164`，把 `_CACHE[key]` 置 `None` 后返回默认值。
- 命中判据：`:166` `cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size` → 命中则返回缓存 dict 的深拷贝（`:167`）。
- 失效/回填：`:168-170` 走 `load_config` 并把 `(st_mtime_ns, st_size, cfg)` 写入；`save_config` 在**同进程**内 `_CACHE.pop(...)`（`:146`）；`invalidate_cache()` 清空全部（`:173-175`）。
- 返回的是防御性深拷贝（`:167`/`:170`），调用方改返回值不会污染缓存（已有测试 `test_autopilot_config.py:130-133` 覆盖）。

## 2. 谁在写 `<root>/.agenticdoc/_autopilot/config.json`

**生产写入者只有一个：TS 侧 console。**
- `/autopilot enable|disable` → `console.ts:287` `saveConfig(projectDir, {...cfg.config, enabled})`；`/autopilot pause|resume` → `console.ts:339`。二者最终落到 `status-model.ts:234 saveConfig`（原子 tmp+rename，`:251-259`）。
- Python `autopilot/config.py:save_config` 在 `packages/multi-workers` 内**没有任何生产调用者**：全仓 grep 只命中 `config.py` 自身与测试（`test_autopilot_config.py`、`test_autopilot_conductor*.py`、`test_autopilot_e2e.py` 等）。
- conductor **只读不自建**：`conductor.py:169`（orchestrate 每 tick）、`:2036`（tick 的 enabled 门）、`:1874`+`:3975`（advance 结果 / serve 轮询），全部 `config.cached_load`，无 `save_config`。
- `mw init / setup / bootstrap` 不创建它：`mw.py` 对 `_autopilot` 零出现（只 `mw.py:41-42` import config/conductor 用于 `serve` 的 `enabled` 判定 `mw.py:161`）。
- 目录/文件由首次写产生：`save_config` 的 `path.parent.mkdir(parents=True, exist_ok=True)`（`config.py:142`）或 gate/timeline 等写者。**文件不存在 = 全默认且零足迹**（`load_config:126-127`，实测确认）。
- 本次 key 的 `mw autopilot verify set` 将是**第一个 Python 生产写入者**；因此必须复用 `save_config` 的原子写 + 全量字段（不能依赖 `load_config` 回写，后者对 partial 文件返回残缺 dict，见 §1.3/§5）。

## 3. 写后 conductor 能否免重启拾取（AC-002 决定性）

### 3.1 结构证据：每 tick 都会重新读

- `tick()` 每次进入先 `config.cached_load(project_root)`（`conductor.py:2036`）判 `enabled/paused`；随后 `orchestrate()` 内部再次 `cached_load`（`:169`）。新命令在下一次 tick（默认 4s，`poll_interval_sec`；最小 0.1s）即进入 `cfg`，`_xkey_run_verify`（`:3460`）读取的就是它。
- `mw serve` 的主循环每步 `_conductor_supervise_step` 读 `cached_load`（`mw.py:161`）决定启停 conductor；配置里的 `enabled` 翻转无需重启 serve。
- 唯一可能“读不到”的原因是 `cached_load` 缓存未失效（下述）。

### 3.2 实测 A：正常外部写（尺寸变化）能被拾取

```
1. cached_load(缺失) round_budget = 2 ; .agenticdoc created? False
2. save_config 后 cached_load = 3
3. 外部同字节长度目标写（实际被 write_text 的 CRLF 转义放大 14B）: mtime_ns delta = 1029200 | size delta = 14
   cached_load after same-size write = 4 (expect 4)   ← 拾取成功
```

### 3.3 实测 B（**关键**）：同字节长度 + 同 mtime_ns 的外部写会 stale

用 LF 字节写入（`write_bytes`，不经 newline 转义）保持字节长度恒定，连续 300 次改写同一字段并在每次后调用 `cached_load`：

```
300 same-size LF rewrites: stale reads = 100 | consecutive writes with identical mtime_ns = 100
STALE at iter 5 want 6 got 5 mtime_ns 1790403017604333300
STALE at iter 7 want 8 got 7 mtime_ns 1790403017605341200
STALE at iter 8 want 9 got 7 mtime_ns 1790403017605341200   ← 与上一次写入同一 mtime_ns
```

同一台机、30 次快速同长写的 `st_mtime_ns` 增量样本：

```
[516100, 0, 515600, 0, 0, 513400, 0, 0, 505200, 0, 507800, 0, 0, 512800, 0, 0, 0, 0, 1002900, 0, 0, 0, 0, 1000100, 0, ...]
min delta = 0 | distinct = [0, 505200, 507800, 512800, 513400, 515600, 516100, 1000100, 1002900]
```

结论：本机 `st_mtime_ns` 的可分辨刻度约 0.5–1 ms，**相邻两次写完全可能共享同一个 `mtime_ns`**。此时若字节长度也相同，`:166` 判据命中 → 返回旧 dict。实测 stale 次数与“相邻写 mtime_ns 相同”次数精确相等（100 = 100）。

### 3.4 对 AC-002 的裁决

- “不需要重启”本身成立（§3.1）；**但 spec 里写的判据“`cached_load` 以 mtime+size 失效”不是可靠判据**：
  1. 它是**充分性强、必要性弱**：尺寸变化必失效；尺寸不变时依赖 mtime 提升，而 mtime 提升在同刻度内不保证。
  2. `save_config` 的 `_CACHE.pop`（`config.py:146`）只作用于**写进程自身**；`mw autopilot verify set` 是独立进程，conductor 进程的 `_CACHE` 不会被它清。既有测试 `test_autopilot_config.py:120-128` 特意用“不同尺寸 + `os.utime(+10s)`”来绕开这个坑——说明该风险已被作者知悉，但**契约没有写进 AC**。
  3. 高风险场景：连续两次 `mw autopilot verify set`（幂等重跑，同尺寸）、`set` 紧接 `clear`、两个 CLI 并发写、或测试里“写→读→立即改写”。
- 建议：AC-002 增加“同字节长度外部写也必须被拾取”的强制项，并要求实现侧二者之一：(a) `mw autopilot verify set` 写完后显式把 mtime 推到可分辨刻度之外（如 `os.utime(path, ns=(t+2_000_000, ...))`）**且** conductor 侧保留 mtime+size；(b) `cached_load` 命中时加一个**廉价内容指纹**（如文件前若干字节的哈希或整文件大小+sha256），或干脆每次 tick 读文件（<1 KB、4s 一次，成本可忽略）。仅靠现状，AC-002 的“机械可验证”会得到非确定性结论。

## 4. `xkey_verify_cmd` / `xkey_verify_timeout_s` 消费点与空命令确切行为

### 4.1 消费点

| 位置 | 作用 |
|---|---|
| `conductor.py:2579-2580` | 建 ticket 时把 `cmd`/`timeout` 快照进 `verification` 字段（`list(cfg.get("xkey_verify_cmd", []))` / `int(cfg.get("xkey_verify_timeout_s", 1800))`） |
| `conductor.py:3448` | `def _xkey_run_verify(...)` |
| `conductor.py:3460` | `verify_cmd = [str(part) for part in (cfg.get("xkey_verify_cmd") or [])]` |
| `conductor.py:3461` | `timeout_s = _xkey_int(cfg.get("xkey_verify_timeout_s"), 1800)` |
| `conductor.py:3463-3468` | `if not verify_cmd:` → `_xkey_verify_failed(..., "xkey_verify_cmd is empty (cannot prove green)")` → `return None` |
| `conductor.py:3470-3472` | 否则 `xkey.run_verification(verify_cmd, cwd=root, run_dir=..., timeout=timeout_s)` |
| `xkey.py:1284-1285` | `run_verification` 内部对空 list 另有一道 `raise XKeyFormatError("verification command must be a non-empty list")`（因 `:3463` 已挡，正常路径不会触发） |

> 注意：`cwd` **硬编码为 `root = str(project_root)`**（`conductor.py:3459`），不可配置——这正是本 key “cwd 语义”要新增的键。

### 4.2 空命令：不抛异常，结构化 fail-closed

`_xkey_run_verify` 在 `:3463` 走 `_xkey_verify_failed`（`conductor.py:3334-3369`），然后 `:3468 return None`。**没有任何 raise**。该函数体做的事：

- `:3348` 从 run_dir 的 `pre-apply.bak` 字节还原目标文件（`_xkey_restore`）；无 bak 时返回 `(False, "")`；
- `:3356-3364` 设置 `ticket["verify"] = { red_before, red_after: null, restored, restored_sha256, expected_file_sha256, restore_sha_ok, stdout_path: null, detail: "xkey_verify_cmd is empty (cannot prove green)", failed_at }`，**`:3358` `ticket["status"] = "verify_failed"`**，`:3359` `xkey.ticket_write`；
- `:3361-3364` 有 `dedup_key` 时 `ledger_append(..., "verify_failed", ...)`；
- `:3365` `_xkey_escalation_write(...)` 写 `<project>/.agenticdoc/_autopilot/xkey/evidence/<request_id>/escalation.md`；
- `:3366-3369` timeline 追加 `xkey-verify-failed`。

调用侧：`_xkey_apply_one` 在 `:3470` 附近调用 `_xkey_run_verify`，`verify is None` 时 `:3471-3472 return`；上层 `_xkey_apply_stage` 的 per-ticket `try/except`（`conductor.py:3754-3762`）**不参与**（无异常），tick 也不受影响。

**工单后续状态：不再重入。**`_XKEY_APPLY_ENTRIES = {approved, applied, verified}`（`conductor.py:3042`），`_XKEY_TERMINAL_STATUSES` 含 `verify_failed`（`:3044-3047`）；`_xkey_apply_one:3635-3639` 先用 `status not in _XKEY_APPLY_ENTRIES` 过滤、再用 ledger 终端行过滤。因此空命令后工单永久停在 `verify_failed`，`xkey-authorize` gate 仍是 pending，**只有人工预配 verify 命令并重置工单才可能推进**。

实测（本机，直接调用 `conductor._xkey_run_verify`，cfg 为 `{"xkey_verify_cmd": []}`）：

```
B. empty cmd -> return = None
   ticket status = verify_failed
   ticket.verify = {"red_before": 1, "red_after": null, "restored": false, "restored_sha256": "",
                    "expected_file_sha256": "aa", "restore_sha_ok": false, "stdout_path": null,
                    "detail": "xkey_verify_cmd is empty (cannot prove green)",
                    "failed_at": "2026-09-26T06:10:32Z"}
   escalation = # XKey escalation req1 ... - status: verify_failed |
                - detail: xkey_verify_cmd is empty (cannot prove green) | ...
   timeline evs = ['xkey-verify-failed']
   timeline details = ['req1 xkey_verify_cmd is empty (cannot prove green); restored=False sha_ok=False']
   ticket file exists = True  (.agenticdoc/_autopilot/xkey/tickets/xkey-req1.md)
```

### 4.3 `mw doctor` 现状（对 AC-008）

`mw.py:499 cmd_doctor` 只拼 `doctor_report` + `report["conductor"]`（`:4609`-ish，本文件实测 `mw.py:510-513`）+ `report["rag"]`。**没有任何 autopilot/xkey 配置检查**：`xkey_repair=true` 且 verify 命令为空时，doctor 不报错、timeline 也只在**工单真的走到 S4 之后**才有 `xkey-verify-failed`（无修复提示）。因此 AC-008 的“启用前自检告警”当前**零实现**。

## 5. TS 侧 `status-model.ts` 的读取/校验 vs Python（逐字段差异）

### 5.1 一致的部分

- 路径：`configPath`（`status-model.ts:56`）与 `config_path`（`config.py:77-78`）同为 `<root>/.agenticdoc/_autopilot/config.json`。
- 字段集 12 键、默认值、`BOOL_FIELDS`、`LIST_FIELDS`、`INT_RANGES` 逐字段相同：`:112`/`:115`/`:118-127` ↔ `config.py:60`/`:61`/`:62-71`。
- 根类型检查 `:135-137` ↔ `config.py:88-89`（错误文案逐字相同）。
- 未知字段 fail-closed：`:139-143` ↔ `config.py:91-93`（文案相同）。
- bool/list 语义、int 范围、错误前缀 `invalid _autopilot/config.json: ` 相同。
- 缺文件 → 默认 + 零足迹：`status-model.ts:184` ↔ `config.py:126-127`（TS 测试 `autopilot-console.test.ts:793-801`）。
- 原子写形状：tmp + rename，`\n` 结尾，indent 2（`:251-259` ↔ `config.py:141-146`）。

### 5.2 差异（必须记录，AC-006 会踩）

| # | 差异 | Python | TS | 影响 |
|---|---|---|---|---|
| D1 | 整值浮点 | `4.0` **拒**（`config.py:111` `not isinstance(value, int)`；实测报 `expected integer, got 4.0`） | `4.0` **收**（`status-model.ts:210-211` `Number.isInteger(4)` 为真；实测 `validateConfigData({round_budget:4.0}) === []`） | 同一份字节 payload，两侧校验结论不同 ⇒ “两侧同时通过”不是逐字段等价 |
| D2 | partial 文件读取 | `load_config` 返回原始 dict（`config.py:133`），缺键不补 | `readConfig` 逐字段回退默认并返回完整 12 键（`status-model.ts:197-227`） | 实测 `{"enabled":true}`：TS `readConfig` → `{enabled:true, round_budget:2,...}` OK；Python `load_config` → 只有 `enabled`，`tick()` 取 `cfg["paused"]` 抛 `KeyError` → tick 返回 `"error"`（broad except `conductor.py:2093-2095`） |
| D3 | 写盘规范化 | 写调用方给什么就写什么（`config.py:144` `json.dumps(cfg, indent=2)`），顺序 = dict 顺序，可含缺键 | 强制重建为 DEFAULT_CONFIG 顺序的 12 键（`status-model.ts:237-250`） | “幂等零 diff”取决于写入方；CLI 必须显式按 `DEFAULT_CONFIG` 顺序写全量字段 |
| D4 | 非 ASCII 转义 | `json.dumps` 默认 `ensure_ascii=True` → `"\u6d4b\u8bd5"` | `JSON.stringify` → 原样 UTF-8 `"测试"` | 实测同一 config：TS 337B vs Python 343B，**字节不相同**。含中文路径/参数的 verify_cmd 会让跨侧“零 diff”失败 |
| D5 | 错误值格式 | `repr`（`'yes'` / `True`） | `JSON.stringify`（`"yes"` / `true`） | 仅文案，不影响判定 |
| D6 | 大整数/精度 | 任意精度 int | `Number.isInteger` 受 IEEE754 限制（>2^53 丢精度，`Infinity` 不可由 JSON 产生） | 极端值语义分歧，实际范围 1..65536 不受影响 |

### 5.3 无跨语言一致性测试

没有测试同时加载两侧字段表做对照：Python 侧只有 `test_autopilot_config.py`（自身字段），TS 侧只有 `autopilot-console.test.ts:766-802` / `autopilot-monitor.test.ts:1043-1046`（自身字段）。上一 key 的同步靠 `T-04b` 任务人工“逐字镜像”（`.agenticdoc/xkey-repair-mechanism/tasks/T-04b-ts-config-mirror.md`）。⇒ 新增键时没有机器判据兜底。

## 6. 新增一个键（例：`cwd`）时必须同步改的具体位置

### Python（`packages/multi-workers/autopilot/config.py`）

1. 模块 docstring 字段表（`:11-28`）——文档一致性。
2. `DEFAULT_CONFIG`（`:44-57`）新增键 + 默认。
3. 类型登记：bool → `_BOOL_FIELDS`（`:60`）；字符串列表 → `_LIST_FIELDS`（`:61`）；整数 → `_INT_RANGES`（`:62-71`）。**不在任何列表里的新键 = 仅“存在性”检查，无类型/范围校验**（`validate_config` 只对登记字段做类型检查）。
4. 消费点：若 `cwd` 参与 verify，改 `conductor.py:3459`（`cwd=root` 硬编码）与 `:2579-2580`（ticket 快照）；若参与层级解析，改 `config_path`/`load_config` 或新增解析函数。

### TS（`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`）

5. 头注释 `12 fields`（`:18`）。
6. `AutopilotConfig` interface（`:67-88`）——加类型字段。
7. `DEFAULT_CONFIG`（`:90-103`）——加默认值。
8. `BOOL_FIELDS` / `LIST_FIELDS` / `INT_RANGES`（`:112-127`）——加登记。
9. `readConfig`：`boolOf`/`intOf`/`listOf` 的联合类型（`:198-212`）+ `merged` 对象（`:213-226`）——**缺 `merged` 字段会被 tsgo 编译报错**（interface 要求全字段），这是 TS 侧的编译期护栏；但 `DEFAULT_CONFIG`/登记表是运行时数据，**编译器不查**。
10. `saveConfig` 的 `ordered`（`:237-250`）——同样受 interface 编译期约束。
11. 若键要暴露到状态：`StatusConfigView`（`:325-330`）与 `deriveStatusModel`（`:503-508`）可选。

### 漏改后果

- **漏改 TS 字段集（6/7/8）**：`validateConfigData` 把新键判为 `unknown field(s)`（`:139-143`），`readConfig` 返回 `ok:false` → `/autopilot status` 直接 fail-closed（`autopilot-console.test.ts:1050-1057` 同型）。这正是 `T-04b` 记录的历史故障模式。
- **漏改 Python 字段集（2/3）**：`validate_config:91-93` 抛 `ConfigError`；`tick` 走 broad except → 返回 `"error"` + timeline `config: tick error: ConfigError(...)`（本机实测：`{"enabled": true, "cwd": "x"}` → tick `"error"`，timeline 有 `tick error: ConfigError('invalid _autopilot/config.json: unknown field(s): cwd')`）。autopilot 整体停摆（每 tick error），但进程不崩。
- **只改 Python 不改 TS（或反之）**：项目一旦写入新键，**另一侧完全不可用**（conductor 或 console 其一），且没有任何跨侧测试会红。

## 7. AC-002 / AC-006 / AC-008 的可机械判定性

### AC-002（拾取）

- 现判据“`cached_load` 失效判据：mtime+size 变化”**不可作为验收判据**：它描述了实现细节且不完备（§3.3 实测 stale），测试会非确定性（本机 1/3 概率假红/假绿）。
- 可判定替代：
  - **AC-002a（行为判据，推荐主判据）**：在**同一 conductor 进程**里连续两次 `tick()`；两次之间由**另一个进程**（或直接文件写）写入同字节长度的不同 verify 命令，**不使用 `os.utime`、不清 `_CACHE`**；断言第二次 tick 产生/使用的是新命令（例如把新命令写成会留下可观测侧效的 fixture：`["python","-c","..."]` 写一个标记文件），且 tick 返回值仍为 `"ok"`。
  - **AC-002b（缓存判据，若选内容指纹方案）**：`cached_load` 在“同 size + 同 mtime_ns”两次不同内容之间必须返回新内容。当前实现会失败——这正好是修复的机器判据。
  - 若选“写侧推 mtime”方案，则 AC-002b 改为：`mw autopilot verify set` 之后，新文件的 `st_mtime_ns` 与写入前缓存值的差 ≥ 1e6 ns（可测）。注意这只是把风险后移，仍建议 AC-002a 作为端到端判据。

### AC-006（两侧校验不放宽）

- “同时通过 validate_config 与 validateConfigData”对**单个 payload** 可判定，但“不放宽”不可判定。
- 可判定替代：**差分类真值表**——定义 payload 语料（合法 12 键全量；缺键 partial；未知键；bool 当 int；`4.0`；`4.5`；范围上下界；空/非空/空串 list），对每个 payload 断言 `python_ok == ts_ok`。当前 `4.0` 会红（D1）⇒ 必须先统一语义（建议 Python 接受整值 float，或 TS 拒绝，二者择一并写进 D-110）。
- 追加**字节一致性**判据（覆盖 D3/D4）：同一 config 先由 Python `save_config` 写、再由 TS `saveConfig` 覆盖（或相反），断言两次文件字节相同（可用 ASCII 与非 ASCII 两组）。“幂等零 diff”（AC-001）应建立在这条之上。

### AC-008（防呆告警）

- 现描述“`mw doctor` 与 timeline 给出明确告警（含修复提示）”可判定，但**当前必然为假**（§4.3：doctor 无检查；timeline 只有事后 `xkey-verify-failed`，且无修复提示）。
- 可判定替代：
  - 定义“有效 verify 命令为空” = 层级解析后 `len(effective_verify_cmd) == 0`（含 cwd/占位展开后的最终 argv）。
  - **doctor 判据**：fixture `{enabled:true, xkey_repair:true, xkey_verify_cmd:[]}` 跑 `mw doctor --json`，断言存在机器字段（建议 `report["autopilot"]["xkey_verify_missing"] == true` 或 `issues[]` 中 code 为 `xkey-verify-cmd-empty`），且文本输出含修复命令串（如 `mw autopilot verify set`）——两者都可 grep。
  - **timeline 判据**：首次满足条件的那一 tick 追加一条事件（建议 `ev="config"`，detail 含 `xkey_repair` 与 `xkey_verify_cmd` 关键字），且**状态未变时不重复追加**（去重），断言事件计数 == 1。
  - 边界：`xkey_repair=false` 或命令非空 → 断言 doctor 无该告警、timeline 无该事件（防误报）。

## 8. 复现命令与脚本

环境：`cd H:\git\Multi-Workers\packages\multi-workers`（Python 需 `sys.path` 加包目录）。

- §3.2/§3.3 探针（`%TEMP%\rq2_probe.py` / `rq2_probe2.py`）：核心片段

```python
# 同尺寸 + 同 mtime_ns 的 stale 复现
from autopilot import config as cfg
path = cfg.config_path(root)          # 已由 save_config 写入 round_budget=1
raw1 = path.read_text(encoding="utf-8")
variants = [raw1.replace('"round_budget": 1', '"round_budget": %d' % d) for d in range(1, 10)]
for i in range(300):
    path.write_bytes(variants[i % 9].encode("utf-8"))   # LF 字节，长度恒定
    got = cfg.cached_load(root)["round_budget"]
    # got 在 ~1/3 的迭代里等于上一轮旧值（stale）
```

- §4 空命令探针（`%TEMP%\rq2_probe5.py`）：构造 `ConductorState` + `conductor._xkey()`，用 `{"xkey_verify_cmd": []}` 调 `conductor._xkey_run_verify(...)`；观察 `ticket["status"]`、`escalation.md`、`timeline.jsonl`。
- §5 TS 侧：`cd packages/coding-agent`，`node --input-type=module -e "import {validateConfigData} from './src/extensions/agent-team-loop/autopilot/status-model.ts'; ..."`（Node 24 原生 type stripping）。
- 字节一致性：分别用 Python `save_config` 与 TS `saveConfig` 写含 `["pytest","测试"]` 的 config，比对文件字节（实测 `byte-identical: False | ts len 337 py len 343`）。

## 9. 对 spec 的直接影响（供 PM 定稿）

1. **AC-002 必须重写**（§3.4/§7）：现判据不可靠。要么加内容指纹，要么写侧推 mtime + 行为判据。
2. **AC-006 必须补差分类测试**（§5.2/§7）：现状 `4.0` 两侧不一致；“不放宽”需重述为“真值表逐 payload 一致 + 字节一致”。
3. **AC-008 是从零实现**（§4.3）：doctor 检查项与 timeline 事件都要新建；“有效解析为空”的定义要显式写（层级 + 占位展开之后）。
4. **CLI 写盘规格**：必须 `default_config()` → 覆盖目标键 → `save_config`（不得用 `load_config` 回写，partial 会退化），字段顺序取 `DEFAULT_CONFIG` 顺序；若允许非 ASCII 命令，需决定 Python 侧是否改用 `ensure_ascii=False` 以取得跨侧字节一致。
5. **`cwd` 新键**：Python 需动 `config.py` 4 处 + `conductor.py:3459/2579`；TS 需动 `status-model.ts` 6 处；两侧漏一即整体 fail-closed（§6）。