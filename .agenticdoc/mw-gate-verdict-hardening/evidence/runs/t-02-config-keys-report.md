# T-02 三个配置键注册 — 回执

- 卡: `.agenticdoc/mw-gate-verdict-hardening/tasks/T-02-config-keys.md`
- key: `mw-gate-verdict-hardening`（phase=EXECUTE）
- 基线: `git rev-parse --short HEAD` = `776b82d7f`；开工前 `git status --porcelain -- packages/multi-workers/autopilot/config.py` = ` M packages/multi-workers/autopilot/config.py`（T-18 的 14→17 三键已未提交落地，本卡在其上加三键）
- 结论: **完成**。`DEFAULT_CONFIG` 17 → **20**，`_INT_RANGES` 三键齐备且值域逐字符合契约；T-18 三键默认值/值域零改动。

## 1. 生产改动（写面 `packages/multi-workers/autopilot/config.py`）

| 位置 | 内容 |
|---|---|
| `config.py:50-60` | docstring 新增三键字段说明（默认 + 值域 + 理由） |
| `config.py:95` | `"l3_abort_retry_limit": 1` |
| `config.py:96` | `"gate_reminder_after_min": 30` |
| `config.py:97` | `"gate_reminder_max": 2` |
| `config.py:119` | `_INT_RANGES["l3_abort_retry_limit"] = (0, 10)` |
| `config.py:120` | `_INT_RANGES["gate_reminder_after_min"] = (1, 1440)` |
| `config.py:121` | `_INT_RANGES["gate_reminder_max"] = (1, 2)` |
| `config.py:188` | docstring `complete 17-key view` → `complete 20-key view` |

契约核对（逐字）：

| 键 | 默认 | 值域 | 状态 |
|---|---|---|---|
| `l3_abort_retry_limit` | 1 | (0, 10) | 一致 |
| `gate_reminder_after_min` | 30 | (1, 1440) | 一致（上限 24h，早于 doctor 24h/72h 文本） |
| `gate_reminder_max` | 2 | (1, 2) | 一致（封在 1..2，只能调低不能抬高） |

三键均**不进** `EFFECTIVE_KEYS`（断言见 `test_t02_key_bounds_are_exact`）。
T-18 三键未被改动：`launcher_max_workers=8 (1,64)`、`dispatch_max_per_scan=3 (1,64)`、`queue_alarm_delta=50 (10,10000)`。

## 2. [VERIFY]（命令原文 + 真实输出）

### 2.1

```
cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_config.py -q -p no:randomly
```

```
.........................................                                [100%]
41 passed in 2.52s
```

（基线同文件为 `34 passed`，新增 7 条用例：3 单键 accept + 3 越界 reject + 1 值域锁定。）

### 2.2

```
cd packages/multi-workers && python -X utf8 -c "from autopilot import config; assert len(config.DEFAULT_CONFIG)==20, len(config.DEFAULT_CONFIG); assert config._INT_RANGES['gate_reminder_max']==(1,2); print('ok', len(config.DEFAULT_CONFIG))"
```

```
ok 20
```

## 3. 非空洞对照

### 3.1 三条越界 reject（必须被拒）

写入 `test_autopilot_config.py`：

- `test_t02_key_out_of_range_rejected[l3_abort_retry_limit-11-1-bounds0]`（`test_autopilot_config.py:200`）
- `test_t02_key_out_of_range_rejected[gate_reminder_after_min-0-30-bounds1]`
- `test_t02_key_out_of_range_rejected[gate_reminder_max-3-2-bounds2]`

判据：`pytest.raises(cfg.ConfigError)` 且错误文本点名该键；并断言 `cfg.DEFAULT_CONFIG[key] == 默认值`（"被拒 ⇒ 默认值仍是权威值"）。项目层配置按契约是 fail-closed（`config.py:169-174` docstring + `test_invalid_never_falls_back_to_defaults`），所以"回落默认值"在本层等价于"非法值被 `ConfigError` 拒绝、不写入任何生效视图"，不会出现静默填默认。

### 3.2 三条单键 accept（必须生效）

写入 `test_autopilot_config.py:171-197`：`test_t02_key_single_payload_accepted`，参数化三键。

- payload 只写一个键（如 `{"gate_reminder_max": 2}`）；
- `load_config` 返回 `== {key: value}`（无默认填充）；
- `ec.load_effective` 里 `values[key] == value` 且 `origins[key] == "project"`，其余键仍为 default；
- `len(eff.values) == 20`。

### 3.3 摘掉 `_INT_RANGES` 对应行 ⇒ 命名用例转红（实跑）

控制脚本：`%TEMP%/t02-controls.py`（跑完已删除；逻辑 = 逐键删行 → 跑命名用例 → 按基线 sha 还原）。基线/还原 sha 均为 `0f7ffa113b5ae16aee78e32ba852d4de2511826a84ec2b4c2c3b45c69f0d932a`。

```
config.py baseline sha256 = 0f7ffa113b5ae16aee78e32ba852d4de2511826a84ec2b4c2c3b45c69f0d932a

==============================================================================
CONTROL: removed _INT_RANGES['l3_abort_retry_limit'] -> "l3_abort_retry_limit": (0, 10),
         pytest -k 'test_t02_key_out_of_range_rejected and l3_abort_retry_limit'
==============================================================================
>       with pytest.raises(cfg.ConfigError) as excinfo:
E       Failed: DID NOT RAISE <class 'autopilot.config.ConfigError'>
test_autopilot_config.py:210: Failed
FAILED test_autopilot_config.py::test_t02_key_out_of_range_rejected[l3_abort_retry_limit-11-1-bounds0]
1 failed, 40 deselected in 0.14s
[control exit=1]

==============================================================================
CONTROL: removed _INT_RANGES['gate_reminder_after_min'] -> "gate_reminder_after_min": (1, 1440),
         pytest -k 'test_t02_key_out_of_range_rejected and gate_reminder_after_min'
==============================================================================
>       with pytest.raises(cfg.ConfigError) as excinfo:
E       Failed: DID NOT RAISE <class 'autopilot.config.ConfigError'>
test_autopilot_config.py:210: Failed
FAILED test_autopilot_config.py::test_t02_key_out_of_range_rejected[gate_reminder_after_min-0-30-bounds1]
1 failed, 40 deselected in 0.12s
[control exit=1]

==============================================================================
CONTROL: removed _INT_RANGES['gate_reminder_max'] -> "gate_reminder_max": (1, 2),
         pytest -k 'test_t02_key_out_of_range_rejected and gate_reminder_max'
==============================================================================
>       with pytest.raises(cfg.ConfigError) as excinfo:
E       Failed: DID NOT RAISE <class 'autopilot.config.ConfigError'>
test_autopilot_config.py:210: Failed
FAILED test_autopilot_config.py::test_t02_key_out_of_range_rejected[gate_reminder_max-3-2-bounds2]
1 failed, 40 deselected in 0.12s
[control exit=1]

config.py restored sha256 = 0f7ffa113b5ae16aee78e32ba852d4de2511826a84ec2b4c2c3b45c69f0d932a
RESTORE OK
```

结论：三条越界用例各自直接读取 `_INT_RANGES`（不是自抄一份常量），摘行即红。

## 4. 计数锁更新（最小必要，逐处点名）

| 文件:行 | 旧 | 新 |
|---|---|---|
| `test_autopilot_config.py:112`（函数名）/ `:118` | `test_default_config_has_17_keys_in_order` / `== 17` | `..._20_...` / `== 20`，尾部位置锁改为 `[-1..-9]` |
| `test_autopilot_config.py:153-154` | `== 17` / `== 17` | `== 20` / `== 20` |
| `test_autopilot_effective_config.py:74` | `== 17` | `== 20` |
| `test_autopilot_effective_config.py:184` | `partial_project_keys=17` | `=20` |
| `test_autopilot_effective_config.py:195` | `all 17 keys` | `all 20 keys` |
| `test_autopilot_effective_config.py:205` | `complete 17-key view` | `complete 20-key view` |
| `test_autopilot_effective_config.py:209` | `== 17` | `== 20` |
| `test_autopilot_effective_config.py:364` | `all 17 keys` | `all 20 keys` |
| `test_autopilot_effective_config.py:386` | `project_keys=17` | `=20` |
| `test_autopilot_effective_config.py:605` | `all 17 keys` | `all 20 keys` |
| `test_mw_autopilot_cli.py:123` | `len(stored) == 17` | `== 20` |
| `test_autopilot_gate_schema_v2.py:352` | `list(cfg.DEFAULT_CONFIG)[-4] == "auto_gate_mode"` | `[-7] ==`（T-02 三键追加后尾部再移 3） |

旁路冻结哈希（直接受影响，跟随 T-18/D-031 先例重冻）：`test_autopilot_readcap_injection.py:998-1006` 的 `_GOLDEN_REGRESSION_SHA256["test_autopilot_config.py"]` 由 `c7c16802904ee29a230e39ceee705c5757b29ed5d4b53b9fd463fe94ace7c600` 重冻为 `27b222b9d166325b536a27c01f106b9304d360ecfab451bbe8082324fd973f40`，并补注释说明 T-02 的 17→20 + 新增 accept/reject 用例。断言强度不变（仍为 byte-exact）。

相关回归（实跑）：

```
python -X utf8 -m pytest test_autopilot_effective_config.py test_mw_autopilot_cli.py test_autopilot_gate_schema_v2.py -q -p no:randomly
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 3.02s
```

```
python -X utf8 -m pytest test_autopilot_readcap_injection.py -q -p no:randomly
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - AssertionError: assert '219ed8090210...e9bd66bc8610a' == '6be60fe5ae42...0769643c91469'
1 failed, 16 passed in 0.28s
```

仅剩的 `test_baseline_left_end_bound` 是**基线既有失败**（`evidence/runs/verify-baseline.md:27` 已记录：配置锚点漂移，只读文件 sha 与冻结副本不一致，与 dispatch/queue 无关），非本卡引入。

## 5. 交接与未越界说明

- **未触碰**（按硬规则）：`test/fixtures/autopilot-config-corpus.json`（T-14 写面）、`test_autopilot_config_parity.py`（T-14 写面，冻结语料 + sha）、`status-model.ts`（T-05 写面）、任何 TS 文件。
- **T-14 交接**：`test_autopilot_config_parity.py` 因本卡 17→20 现为红（`3 failed`：`test_p2_crosslang_bytes`/`test_p3_crossread_idempotence`/`test_p6_partial_single_key`，断言位置 `:423` Python effective_keys 与 `:426` TS merged keys，均为 `17` 字面）。这属于 T-14 的写面：需补 3 条单键 accept + 3 条越界 reject 到冻结语料、并把两侧计数锁与语料 sha 一起重冻。本卡未单方面改动。
- **T-05 交接**：`status-model.ts` 的 TS 3 键镜像仍未落（当前为 T-18 的 17 键），parity TS 侧 `:426` 依赖它。
- **未 commit、未 `git add -A`、未 stash/reset/clean、未 kill 进程、未动队列文件。**

## 6. 改动文件清单

- `packages/multi-workers/autopilot/config.py`
- `packages/multi-workers/test_autopilot_config.py`
- `packages/multi-workers/test_autopilot_effective_config.py`
- `packages/multi-workers/test_mw_autopilot_cli.py`
- `packages/multi-workers/test_autopilot_gate_schema_v2.py`
- `packages/multi-workers/test_autopilot_readcap_injection.py`（仅 golden sha 重冻 + 注释）
