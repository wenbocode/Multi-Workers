# T-02 effective_config.py（机器级层 + 层级 merge + origin）

- AC: AC-007 · VC: VC-007 · 波次: 1（与 T-03/T-04 并行；与 T-01 有依赖但写面不重叠）
- 写面：**新建** `packages/multi-workers/autopilot/effective_config.py` + `packages/multi-workers/test_autopilot_effective_config.py`

## 契约（plan.md §2.1/§2.2）

```python
EFFECTIVE_KEYS = ("xkey_verify_cmd", "xkey_verify_cwd")     # 2026-09-26 修订：由四键收窄为两键
EMPTY_VALUE = {"xkey_verify_cmd": [], "xkey_verify_cwd": ""}  # 空值即未决定
ORIGINS = ("project", "machine", "default")
def machine_config_path(env=None) -> pathlib.Path | None
def load_effective(project_root, env=None) -> EffectiveConfig   # .values / .origins / .diagnostics / .machine_path
```

- 机器层路径：`MW_AUTOPILOT_FILE`（整文件硬覆盖；**设定但文件缺失 ⇒ 层空，不回落 HOME**）→ `MW_AUTOPILOT_HOME` → `HOME` → `USERPROFILE`，各自拼 `/.agents/autopilot-defaults.json`；不存在 ⇒ `None`，**不建目录**。
- 机器层格式 = JSON；覆盖域 = `EFFECTIVE_KEYS`（**仅 cmd + cwd**）；**越域键 ⇒ diagnostics 告警并忽略**。
- 逐键规则：项目侧值非空 ⇒ `project`；项目侧空/缺失且机器侧非空 ⇒ `machine`；两层均空/缺失 ⇒ `default`（值取内置默认）。
- 错误策略：机器层 **fail-soft**（未知键告警忽略 / 类型错丢弃该字段 / 整份坏 ⇒ 该层为空 + 告警）；项目层 **fail-closed**（`load_config` 抛 `ConfigError` 原样上抛）。
- `values` 恒 13 键全量；`origins` 每键 ∈ ORIGINS；机器侧 `null` ⇒ 空操作（≡ 缺失）；项目侧 `null` ⇒ 类型错（fail-closed，`validate_config` 拒 `null`）。
- 只读：**不得创建任何目录**（尤其 `.mw/`）。

## 步骤

1. 实现上述接口（依赖 `autopilot.config`，不修改它）。
2. 12 条真值表用例（覆盖/缺失/非法/未知键 × value+origin+diagnostics 断言）：env 隔离用 `mock.patch.dict(os.environ, ..., clear=True)`。
3. 一条消费侧断言：`conductor.tick()` 在机器层提供命令时返回 `"ok"`（证明解析结果真被用上，非只验函数返回值）。

## 验证

- `python -m pytest -q test_autopilot_effective_config.py` 全绿。
- **非空洞对照**：把机器层错误策略临时改成 fail-closed ⇒ 对应用例必须红。
- `[VERIFY]` 行：机器层文件路径解析、逐字段 origin、fail-soft diagnostics、只读零足迹。
