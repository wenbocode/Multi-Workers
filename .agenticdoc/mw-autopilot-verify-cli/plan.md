# Plan: mw-autopilot-verify-cli

- key: `mw-autopilot-verify-cli` · design 已定稿（D-001…D-014）· 14 AC / 16 VC
- 基线：`b0a30bc12`

## 1. 并行度分析（按**文件边界**切写面）

同一文件同一时刻只允许一个写者。据此分波：

| 波 | 任务 | 写面（互不重叠） |
|---|---|---|
| **波 1** | T-01 `config.py` 基础（新增键/去缓存短路/补默认键/`ensure_ascii=False`） | `autopilot/config.py` + `test_autopilot_config.py` |
| | T-02 `effective_config.py` 新模块（机器层 + merge + origin） | `autopilot/effective_config.py`(新) + `test_autopilot_effective_config.py`(新) |
| | T-03 `mw_common.py` 新增面（`render_argv` + `_doctor_autopilot` + dist 锚点 helper） | `mw_common.py` + `test_common_render_argv.py`(新) + `test_doctor_autopilot.py`(新) |
| | T-04 TS 侧（`xkey_verify_cwd` 镜像 + 导出常量 + reviver 判整数 + console 进锁） | `status-model.ts`、`console.ts` + TS 测试 |
| **波 2** | T-05 `mw.py` CLI（`mw autopilot verify set/show/clear` + 锁内 RMW + dry-run） | `mw.py`（autopilot 段）+ `test_mw_autopilot_cli.py`(新) |
| | T-06 conductor/dispatch 根锚定（verify cwd + 同族 5 锚点 + `load_effective` 切换） | `autopilot/conductor.py`、`autopilot/dispatch.py` + `test_autopilot_xkey_cwd.py`(新) |
| | T-07 跨语言一致性判据（P1-P6） | TS vitest 新文件 + Python 半表新文件 + 共享语料 JSON(新) |
| **波 3** | T-08 `mw.py` update-env 锚点（A1b/A2b）+ `_apply_update_env`/`_deploy_bundle` 顺序 + build 脏树护栏 | `mw.py`（build/update-env 段）+ `test_update_env.py`、`test_mw_build.py` |
| | T-09 cwd/占位符真值表 + E2 形状回归 + `control≠partition≠parent` fixture | `test_autopilot_verify_cwd_table.py`(新) |
| **波 4** | T-10 文档（UPDATE/README）+ dist 重建 + 全量回归 | `UPDATE.md`、`README.md`、`packages/*/dist` |

依赖：T-05 ← T-01/T-02/T-03；T-06 ← T-02/T-03；T-07 ← T-01/T-04；T-08 与 T-05 同文件 ⇒ 必须串行（本表已分波）；T-10 最后。

> **依赖修订（执行期）**：T-02 需 T-01 的 13 键与 `load_config` 合并语义才能断言，故实际波次为 **波 1 = T-01/T-03/T-04**（互不依赖）、**波 2 = T-02/T-07**、**波 3 = T-05/T-06**、**波 4 = T-08/T-09**、**波 5 = T-10**。

## 2. 契约冻结（并行 worker 逐字遵守，不得重定义）

### 2.1 Python 签名

```python
# autopilot/config.py
DEFAULT_CONFIG["xkey_verify_cwd"] = ""                  # 第 13 键；顺序 = DEFAULT_CONFIG 序
def default_config() -> dict                             # 深拷贝，13 键
def load_config(project_root) -> dict                    # 校验原始 data -> 返回 {**default_config(), **data}
def cached_load(project_root) -> dict                    # = load_config + json 往返深拷贝；无 stat 短路
def invalidate_cache() -> None                           # no-op（保留名字）
def save_config(project_root, cfg) -> pathlib.Path       # validate -> tmp+replace；json.dumps(indent=2, ensure_ascii=False)+"\n"

# autopilot/effective_config.py
EFFECTIVE_KEYS = ("xkey_repair", "xkey_verify_cmd", "xkey_verify_timeout_s", "xkey_verify_cwd")
ORIGINS = ("project", "machine", "default")
class EffectiveConfig:  # 明确字段、无 dataclass 装饰器要求
    values: dict          # 13 键全量
    origins: dict         # 13 键，值域 ORIGINS
    diagnostics: list[str]
    machine_path: pathlib.Path | None
def machine_config_path(env=None) -> pathlib.Path | None
def load_effective(project_root, env=None) -> EffectiveConfig   # 项目层非法 -> raise ConfigError

# mw_common.py
def render_argv(cmd: list[str], config: dict) -> list[str]
def workspace_root(config: dict) -> str                  # partition->partition_root, dual->game_root, single/legacy->control_root
def _doctor_autopilot(project_dir) -> dict
def repo_bundle_anchor() -> dict                         # {"stale": bool|None, "detail": str}
def sourcemap_drift() -> dict
```

### 2.2 数据结构 / 落点 / 枚举

- 固定落点：项目层 `<root>/.agenticdoc/_autopilot/config.json`；机器层 `~/.agents/autopilot-defaults.json`；锁 `<root>/.mw/autopilot-config.lock`。
- env：`MW_AUTOPILOT_FILE`（整文件硬覆盖，设定但缺失 ⇒ 层空**不回落**）、`MW_AUTOPILOT_HOME`，其后 `HOME`、`USERPROFILE`。
- 机器层覆盖域 = `EFFECTIVE_KEYS` 四键；越域键 ⇒ diagnostics 告警并忽略（fail-soft）。
- origin 值域 `{project, machine, default}`；project 侧 `null` ⇒ origin `default`；machine 侧 `null` ⇒ 空操作。
- `xkey_verify_cwd ∈ {"", "control", "partition", "parent", "<root name>"}`；`""` = auto（`workspace_root`）。schema 只校验字符串，根名合法性在解析期 fail-closed（kind = `invalid-config`）。
- 锁参数冻结：`retries=6, base_delay=0.02`（Python `mw_common.acquire_lock`；TS 同协议同参数）。
- 命令形状冻结：`mw autopilot verify set --project DIR [--timeout SEC] -- ARGV...`；`--project` 必须在 `--` 之前。
- 错误前缀：`[mw autopilot verify <action>] Error: ...`；退出码 0/1（业务）、2（argparse）。
- 哈希/内容锚定口径：kind 集合锚定 `GATE_KINDS = [` 赋值处；guard 限定串 `xkey-gate-guard: blocked`、`[XKEY_GATE]`（**不用裸串**）。
- dist 判据口径：`git -c core.fileMode=false diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist`。

### 2.3 不变量（禁止违反）

- `render_toolchain_command` 一行不改（跨语言 parity fixture 锁死）。
- `xkey.run_verification` 的 `shell=False` 与 argv 原样语义不改。
- 协调根（ledger/tickets/evidence）恒为 control 根；只重锚工作区相对文件。
- 只读路径（`show`/doctor/conductor/dispatch）不得创建 `.mw/` 或任何目录。
- 新增键两侧必须同版本上线（旧 TS bundle 读 13 键文件会 fail-closed）。

## 3. 任务表（→ `tasks/T-*.md`）

| 卡 | 标题 | AC | VC | 关键交付 |
|---|---|---|---|---|
| T-01 | config.py 基础 | AC-001/003/006/012 | VC-003/016 | 13 键、去短路、补默认键、`ensure_ascii=False` |
| T-02 | effective_config 层级层 | AC-007 | VC-007 | 机器层 + 优先级 + origin + fail-soft |
| T-03 | mw_common 新增面 | AC-008/013/014/009 | VC-008/014 | `render_argv`、doctor 段、dist 锚点 helper |
| T-04 | TS 镜像与写侧 | AC-006/011/012 | VC-006/011/015 | 键镜像、导出常量、reviver、console 锁 |
| T-05 | `mw autopilot verify` CLI | AC-001/002/004/005/011 | VC-001/002/004/005/011 | 组/子组、锁内 RMW、dry-run、show/clear |
| T-06 | conductor 根锚定 | AC-013 | VC-013 | verify cwd + 同族 5 锚点 + `load_effective` |
| T-07 | 跨语言一致性判据 | AC-006 | VC-006/015 | P1-P6、共享语料、fail-closed |
| T-08 | update-env/build 防复发 | AC-009 | VC-009/010/012 | A1b/A2b、S1 顺序、脏树护栏 |
| T-09 | cwd/占位符真值表 | AC-013/014 | VC-013/014 | ≥18 行真值表 + E2 形状 + 同族回归 |
| T-10 | 文档 + dist 重建 + 回归 | AC-009/010/012 | VC-012/016 | UPDATE/README、产物重建、全量回归 |

## 4. 风险登记

| # | 风险 | 触发 | 缓解 |
|---|---|---|---|
| R1 | 去缓存改动影响 serve 1 s 轮询性能 | 每 tick 真读 | RQ-D1 实测：60–70 µs，缺文件 15 µs（比现状快 11×）；VC-016 回归 |
| R2 | `load_config` 补默认键掩盖配置错误 | 读侧放宽 | 校验仍作用于**原始 data**；未知键/类型错仍 fail-closed；机器层越域仅 diagnostics |
| R3 | 同族 5 锚点重锚引入回归 | `conductor.py:2513/2576/2942/3408/3651` | 全部改动在 `xkey_repair` 门内；现网通道全关；既有 e2e 全为 single 形状（缺省 = 原行为） |
| R4 | TS reviver 第三参在旧 Node 不可用 | `engines.node >= 22.19.0`、CI pin 22 | 已核实可用（22.0.0/22.19.0/24.19.0 实测）；窄类型 + 一次 cast，不引入 `any` |
| R5 | dist 判据被文件 mode 位污染 | `core.fileMode=true` 主机 | 判据带 `-c core.fileMode=false`；不改 tracked mode 位 |
| R6 | 本 key 写面宽（Python 4 文件 + TS 2 文件 + 测试 + 产物） | 多会话共享 cwd | 按波切文件边界；每卡只碰其写面；提交前 `git status` 核对 |
| R7 | 锁不可得时 UX（等待 1.26 s 后报错） | 并发 set | 显式 `retries=6/base_delay=0.02`；错误含锁路径与提示；只读路径不加锁 |
| R8 | 新增键的部署顺序（旧 TS bundle 读 13 键 ⇒ fail-closed） | Python 先升级 | `mw build --install` 同时更新 bundle+dist；文档写明"两侧同版本上线"；T-10 顺序 |
| R9 | CI 无 Python 步骤 ⇒ 跨语言判据可能不跑 | `ci.yml` 只有 npm | 加 `actions/setup-python`；判据 fail-closed（对端缺失即硬失败，不用 `skipIf`） |
| R10 | 脏树护栏误伤（多会话必然"脏"） | 他人未提交 TS | 只拦 `src` 且 `--allow-dirty` 可绕；非 git 跳过 |
| R11 | `render_argv` 收紧 dual/single 语义被误认为 toolchain 变更 | 共用 token 名 | 新增独立函数；`render_toolchain_command` 零改动由 parity 集证明（VC-014） |
| R12 | 测试空洞（P-016） | 只验字段写入 | VC-003/013/014 全部带**非空洞对照**（裸字节写、`control≠partition` fixture、嵌入占位负例） |

## 5. 完成定义（DoD）

- 14 AC 的 16 条 VC 全部有实物证据（`[VERIFY]` 行或报告），AC→VC 100% 覆盖。
- 默认套件相对基线 `b0a30bc12` 零新增失败；跨语言判据在 CI 路径可跑（或如实声明并给出替代跑法）。
- design §11 回填实际签名/落点/妥协；CHANGELOG 两包 + `_pitfalls.md` 新增条目。
- 产物重建并提交；`achieved.md` 含「系统行为变化」与遗留。
