# RQ-1 证据：mw CLI 既有「写项目配置」命令的实现范本

- key：`mw-autopilot-verify-cli` · 日期：2026-09-26 · 性质：**只读调研**（唯一写面 = 本文件）
- 锚点：`git rev-parse --short HEAD` = `d52694cc4`（工作树仅 `?? .agenticdoc/mw-autopilot-verify-cli/`，即本 key 未跟踪目录）
- 方法：全部结论来自 git 检出实测（`read` + `Select-String` 行号）与 CLI 实跑（`python mw.py --help` / `model --help` / `model show --help` / `rag init --help`）；无一条凭印象。
- 边界：本文件只回答「CLI 层实现范本」。`_autopilot/config.json` 的读写语义/校验/拾取细节以 RQ-2（`spec-config-write-contract-20260926.md`）为准；占位符与 cwd 以 RQ-4 为准。凡交叉处标 `→RQ-x`。

## 0. 结论速览

1. **组/子组**：`sub.add_subparsers(dest="subcommand", required=True)`（`mw.py:4645`）；二级组用 `dest="<group>_action"` + `required=True`（`target_action` `mw.py:4671`、`partition_action` `mw.py:4694`、`model_action` `mw.py:4721`、`rag_action` `mw.py:4852`）。`mw autopilot` 应形如 `autopilot_p` → `autopilot_action`（verify）→ `verify_action`（set/show/clear）。
2. **argv 列表无先例**：仓库没有任何「把一条命令的 argv 原样收成 list[str]」的 argparse 形状；最接近的是 `--args STR`（单字符串原样拼接，`mw.py:4835-4839` + `:983-986`），且其注释显式记录了 REMAINDER 会吞掉后续选项的坑。`set -- python -m pytest -q` 的写法在 spec 里**尚未定形**（见 §1.3、AC-001）。
3. **写入助手不统一**：`autopilot/config.py::save_config`（`:136-148`，校验+原子+LF+indent2，全文规范化）是唯一与 TS 侧字节形状对齐的助手；`mw.py::_atomic_write_yml`（`:2378-2391`）保留原换行、原子但不校验；`mw.py::_model_write`（`:3116-3126`）**非原子**且 Windows 上写 CRLF（实测，见 §2.2）。
4. **BOM 三道**：`save_config` 读路径用 `encoding="utf-8"`（`config.py:129`）→ 带 BOM 的 config.json 直接 `ConfigError`（fail-closed）；写路径从不写 BOM。`utf-8-sig` 只在 pi settings 与 target.yml 两处读（`mw_common.py:1307`、`mw.py:1591`）。
5. **报错无 helper**：一律 `print("[mw <group> <action>] Error: ...", file=sys.stderr)` + `return 1`；`SystemExit` 只出现在顶层 `sys.exit(dispatch[...](args))`（`mw.py:4928`）。argparse 自身错误 = exit 2。
6. **CLI 测试三形状**：直接调 `mw.cmd_*` + `argparse.Namespace`（`test_dispatch_models.py:422-452`）、真子进程跑 `mw.py`（`test_rag_init.py:90-104`）、快照/零残留断言（`test_mw_target.py:52-70`）。
7. **doctor 新检查项**：加 `_doctor_*` section → 在 `doctor_report` 注册（`mw_common.py:2115-2116` 附近）→ 在 `_doctor_issues` 转 issue/suggestion（`mw_common.py:2012-2085`）→ 在 `format_doctor_text` 加行（`:2128+`）。**`mw doctor` 与 `mw bootstrap` 有两条独立的报告拼装路径**（`mw.py:509-525`、`mw.py:4143-4148`），只加在 `cmd_doctor` 里则 bootstrap 看不到。
8. **项目根**：`--project` 在 20 处一律 `required=True`，唯一例外 `bootstrap --project`（默认 `None` = 本仓根，`mw.py:4777-4778`）；**mw 从不做 cwd 探测、从不调用 detect_root**。cwd 默认的先例只在独立脚本 `autopilot/roadmap_check.py:36-39`。
9. **`autopilot` 名称无 CLI 冲突**：`mw.py` 无 `add_parser("autopilot")`（`--help` 实跑列表 17 个组，无 autopilot）；`autopilot` 已是**同子系统**的既有名字（Python 包 `packages/multi-workers/autopilot/` + pi 斜杠命令 `/autopilot`，`console.ts:85`），因此 `mw autopilot` 是「沿用既有名」而非抢占。真正的风险不是命名冲突，而是**同文件双写者**（CLI vs 窗口 `/autopilot enable`）造成丢失更新（见 §7.2）。

---

## Q1 `mw model` / `mw target` / `mw rag` 的 argparse 形状

### 1.1 组与子组怎么建

| 层 | 代码 | file:line |
|---|---|---|
| 顶层 | `sub = parser.add_subparsers(dest="subcommand", required=True)` | `mw.py:4645` |
| 无子组的命令 | `_add_serve_args(sub.add_parser("serve", help=...))` / `for name in ("stop","status")` | `mw.py:4646-4652` |
| 二级组 | `target_p = sub.add_parser("target", help=...)`；`target_sub = target_p.add_subparsers(dest="target_action", required=True)` | `mw.py:4667-4671` |
| 二级组（partition） | `partition_sub = partition_p.add_subparsers(dest="partition_action", required=True)` | `mw.py:4690-4694` |
| 二级组（model） | `model_sub = model_p.add_subparsers(dest="model_action", required=True)` | `mw.py:4717-4721` |
| 二级组（rag） | `rag_sub = rag_p.add_subparsers(dest="rag_action", required=True)` | `mw.py:4847-4852` |
| 三级组（ue-toolchain） | `toolchain_sub = toolchain_p.add_subparsers(dest="toolchain_action", required=True)` | `mw.py:4813-4819` |
| 叶子 action | `target_sub.add_parser("set", help=...)` 等，或 `for action in ("clear","show","on","off")` 批量建 | `mw.py:4672`、`:4680-4688`、`:4707-4715` |

批量建 action 的写法（`target`/`partition`）用 `for action in (...)` + `help_text = {...}[action]`（`mw.py:4680-4688`、`4707-4715`），适合 set/show/clear 三件套；`model` 则逐个建（`:4722`、`:4728`、`:4732`），因为各 action 参数不同。

### 1.2 参数命名与形状

- **`--project` 一律是 option 且 `required=True`**（20 处，见 Q6），从不是位置参数。
- **业务值用位置参数**：`model set <ROLE> <PROVIDER/MODEL>`（`mw.py:4724-4727`，带 `choices=mw_common.DISPATCH_ROLES` + `metavar="ROLE"`），`model clear <ROLE|all>`（`:4729-4731`，`metavar="ROLE|all"`，不用 `choices` 因为含哨兵值 `all`），`ue-toolchain run <NAME>`（`:4828-4829`）。`metavar` 是惯例，用于让 help 显示语义名而不是 `ROLE`/`VALUE`。
- **`choices`** 用于封闭枚举：`--vcs {git,p4,none}`（`:4676`）、`--transport {mcp,skill,both}`（`:4864`）、`--codex-scope {project,user}`（`:4739-4740`）。
- **`nargs`**：全仓只有一处 `nargs="+"`（`ue-toolchain hash <FILE>...`，`mw.py:4845`）。
- **`action="append"`**：`--root NAME=DIR`（`mw.py:4703`，可重复命名根）、`--watch PATH`（`:4832`，可重复监视文件）。
- **布尔开关**：`action="store_true"` + `dest=` 显式命名（避免 `--no-roots` 变成 `no_roots` 之类）：`--no-dist`→`dest="no_dist"`（`:4795`）、`--only-machine`→`dest="only_machine"`（`:4870`）、`--dry-run`→`dest="dry_run"`（`:4877`）、`--print`→`dest="print_templates"`（`:4879`）。
- **`default=None` + 代码里取默认值**：`--server/--url/--token-env`（`:4857-4865`）默认值由 `rag_templates.DEFAULT_*` 在实现里补（`mw.py:2098-2108`），help 里用 f-string 打出现行默认值（`:4859-4860`）。
- **`metavar` + 单位选项**：`--stale-after SEC`（`:4663-4666`）用 `metavar="SEC"` 且 help 里写 `(default: %(default)s)`。

### 1.3 多个 argv 值（重点，本 key 的 AC-001 依赖它）

**先例只有三种，且都不是「argv 列表」**：

| 形状 | 出处 | 收法 | 能否收 flag |
|---|---|---|---|
| `--args STR`（ue-toolchain run） | 定义 `mw.py:4835-4839`；消费 `mw.py:983-986` | 多 token 拍成**单个字符串**，原样拼到渲染命令尾部 | 能，但需用等号形式（help 明写 `--args="-MaxParallelActions=16"`） |
| `nargs="+"` 位置参数 | `mw.py:4845` | `list[str]` | **不能**（以 `-` 开头会被当选项） |
| `action="append"` | `mw.py:4703`、`:4832` | 重复 flag 累加成 `list[str]` | 不能（值以 `-` 开头需等号形式） |

`--args` 的实现显式记录了为什么不用 REMAINDER，这是直接可引用的判据：

> `mw.py:983-985`：`# forwarded extra args (--args "...") are appended verbatim; a single string sidesteps argparse's REMAINDER quirk (everything after the name positional would be swallowed, including --project)`

因此：**`mw autopilot verify set -- python -m pytest -q` 在 repo 内没有可照抄的先例**。`xkey_verify_cmd` 的落盘类型是 `list[str]`（`autopilot/config.py` `DEFAULT_CONFIG["xkey_verify_cmd"] = []`、`_LIST_FIELDS`），若用 `--` + `argparse.REMAINDER`，`--project` 必须写在 `--` 之前（否则被一并吞进 argv，正是上面注释记的坑）；若用 `--cmd` 可重复则无法表达 `python -m pytest -q` 里的 token 边界（每次一个 token 也可，但对人难用）。**spec 必须显式定形**（见 AC-001 批判）。

附带事实：`ue-toolchain run` 最终以 `shell=True` 执行（`mw.py:1009`），而本 key §1.4 要求 verify 保持 `shell=False`，所以 `--args` 这一路**只能借其参数形状，不能借其执行面**。

### 1.4 help 文案风格（实跑 + 源行号）

- 语言：**英文单行**，首字母大写或无主语短语，语义密，常带例子/默认值括号；`(e.g. ...)`、`(default: ...)`、`(repeatable)` 是惯例。
  - `model_set_p`：`"Set a role default (e.g. mw model set review timi/glm-5.3-air)"`（`mw.py:4722`）
  - `model_clear_p`：`"Remove one role (or 'all')"`（`:4728`）
  - `model_show_p`：`"Print the configured roles and the effective resolution"`（`:4732`）
  - `target_p`：`"Dual-workspace target config: set bootstrap fields, clear, or show the resolved view"`（`:4667-4670`）
  - `rag_init_p`：`"Zero-interaction template generator: write commented rag-servers.yml / target.yml rag: / rag-roots.json examples"`（`:4853-4855`）
- 组 help 用「<名词短语>：<能力列表>」两句式（`target`/`partition`/`model`/`rag` 同上）。
- **反例（不一致）**：`stop`/`status` 建 parser 时没给 `help=`（`mw.py:4651-4652`），所以 `python mw.py --help` 列表里根本看不到它们（实测：usage choices 里有，正文列表里没有）。`serve`/`start` 有（`:4646-4647`）。
- 子命令 help 在 `--help` 中按 `usage: mw.py model set [-h] --project PROJECT role value` 自动生成，无需额外处理。

### 1.5 互斥

仓库**没有** `add_mutually_exclusive_group`（全仓 grep 零命中）。互斥是**手检 + 报错 + return 1**：

- `mw.py:2094-2096`：`if args.machine and args.only_machine: print("[mw rag init] Error: --machine and --only-machine are mutually exclusive", file=sys.stderr); return 1`
- 同类：`rag init --print` 与 `--dry-run` 是「先 print 后 dry-run」的短路顺序（`mw.py:2132-2135`、`:2194-2197`），不是互斥声明。

### 1.6 action 分派

两种并存：
- **if 链**：`cmd_target`（`mw.py:914-926`）、`cmd_partition`（`:3105-3116`）、`cmd_model`（`:3129+`，块状 if）。
- **dict**：`cmd_rag` → `_RAG_ACTIONS[args.rag_action](args)`（`mw.py:2235-2237` + `_RAG_ACTIONS` `:2239-2245`）。
新增 autopilot 组建议照 `rag` 的 dict 形状（叶子多、每个 action 一个 `_cmd_*` 函数，独立可测）。

---

## Q2 写项目配置的实现助手

### 2.1 助手清单（**没有**统一入口）

| 助手 | 位置 | 原子 | 新行 | 缩进/键序 | 校验 | fsync |
|---|---|---|---|---|---|---|
| `autopilot.config.save_config` | `autopilot/config.py:136-148` | 是（`tmp_path.replace`，`tmp_path` = `<path>.tmp`，`:144-145`） | **强制 LF**（`newline="\n"`，`:144`） | `indent=2`，键序 = 调用方 dict 序（`:144`） | `validate_config`（`:141`） | 否 |
| `autopilot.config.load_config` | `autopilot/config.py:122-134` | — | — | 不补默认键（见 §2.4） | 读时校验 | — |
| `mw._atomic_write_yml` | `mw.py:2378-2391` | 是（`os.replace`，`:2387`） | **原样保留**（`newline=""`，`:2385`） | 不缩进/不改序，纯文本替换 | 无 | 否 |
| `mw._model_write` | `mw.py:3116-3126` | **否**（`path.write_text`，`:3120`） | Windows 上 **CRLF**（未传 `newline`，实测见 §2.2） | `yaml.safe_dump(..., sort_keys=True)`（键按字母序） | 调用方 | 否 |
| `mw_common._write_pi_settings` | `mw_common.py:1242-1248` | 是（`os.replace`，`:1248`） | Windows 上 **CRLF**（未传 `newline`） | `indent=2` + `ensure_ascii=False` | 无 | 否 |
| `mw_common._write_workers_file` | `mw_common.py:1502-1508` | 是（`tmp_path.replace`，`:1507`） | Windows 上 CRLF | 序列化函数决定 | 无 | 否 |
| `mw._rag_install_skill` | `mw.py:1153-1183` | 是（`os.replace`，`:1177`） | 二进制逐字节拷贝 | 不适用 | 无 | **是**（`:1176`） |
| `autopilot.xkey._write_json_atomic` | `autopilot/xkey.py:533-541` | 是 | 见实现 | 见实现 | 调用方 | 否 |

结论：**不存在仓库级「JSON 写助手」**；与 `_autopilot/config.json` 对齐的只有 `autopilot/config.py::save_config`（Python）与 `status-model.ts::saveConfig`（TS，`:234-256`），两者 docstring 互相声明字节形状一致（Python：`autopilot/config.py:137-139`；TS：`status-model.ts:228-233`「UTF-8, LF, indent-2 + trailing newline — the exact shape config.py save_config writes and parses back」，并声明「always normalizes to the full canonical field set in DEFAULT_CONFIG order」，`:236-249`）。

### 2.2 BOM / 换行 / 缩进 / 键顺序（实测）

在 `%TEMP%` 里做的一次性探针（不进仓库）：

- `Path.write_text("a\nb", encoding="utf-8")` → `b'a\r\nb'`（Windows `newline=None` 会把 `\n` 翻成 `os.linesep`）。
- `Path.write_text(..., newline="\n")` → `b'{\n  "a": 1\n}\n'`（LF）。
- `json.loads(带 BOM 的 utf-8 文本)` → `JSONDecodeError: Unexpected UTF-8 BOM (decode using utf-8-sig)`；`encoding="utf-8-sig"` 可读。

对应到仓库：

- `save_config`：写 **LF + indent2 + 末尾单换行**（`config.py:144`）；读用 `encoding="utf-8"`（`:129`）→ **已有 BOM 的文件进不来**（fail-closed `ConfigError`，`:130-131`），即「BOM 不支持」是既有契约而非遗漏。**键顺序**：`json.dumps(cfg, ...)` 按 `cfg` 的 dict 插入序；`load_config` 不补默认键，所以「键顺序」= 调用方构造 dict 的顺序。
- `_atomic_write_yml`：读 `newline=""`（`mw.py:2344`）、写 `newline=""`（`:2385`），**保留 CRLF/LF 原状**；配套 `_dominant_ending`（`mw.py:2395-2396`）用于新建内容时选跟随文件主导换行。
- `_model_write`：`path.write_text(..., encoding="utf-8")`（`mw.py:3124-3127`）→ Windows CRLF；`sort_keys=True`（`:3125`）→ 键字母序；**非原子**。
- `_write_pi_settings`：同样未传 `newline`（`mw_common.py:1247`）→ Windows CRLF；读侧却用 `utf-8-sig`（`:1307`）容忍 BOM。
- **无一处写 BOM**；`utf-8-sig` 只用于读（`mw_common.py:1307`、`mw.py:1591`）。

### 2.3 写后是否打印摘要或 diff

- **无 diff**（全仓没有写后 diff 的实现）。
- 三种输出惯例：
  1. **单行摘要带路径**：`mw.py:3171` `[mw model set] {role} = {value} → {path}`；`clear` 同理 `:3186`/`:3200`。
  2. **逐文件 wrote + 下一步**：`mw rag init`（`mw.py:2225-2232`）。
  3. **计划/拒绝表 + `--dry-run` 先行**：`mw rag init` 先构 `plans` / `refusals` / `report`，`--dry-run` 打印 `[mw rag init] dry-run — no files written` + 每行 `action path (detail)`（`mw.py:2194-2198`），失败时把全部 refusal 打到 stderr 并追加 `nothing written. Edit by hand or re-run with --force.`（`:2200-2204`）。
- `mw target set` 的「摘要」是**解析后的生效视图**（`_print_target_summary`，`mw.py:606-613`：mode/source/control/game/engine/vcs）——与 spec 里 `show` 的「有效解析」形状同源，可直接借用为 `mw autopilot verify show` 的输出骨架。
- 「值没变就跳过」的短路先例：`_rag_install_skill`（`mw.py:1167-1169`）在 sha 相同时打印 `unchanged (already installed) ... sha256=...` 并 `return 0`，**不触碰文件**（即不制造 mtime churn）。→ 这条直接关系到 AC-001 的「零 diff / 幂等」定义（见 §AC-001）。

### 2.4 直接踩过的坑：`save_config` 不补默认键 ⇒ 可能写出 partial 文件

- Python `load_config` **不合并默认值**（`autopilot/config.py:122-134`：解析→校验→原样返回）；TS `readConfig` 合并（`status-model.ts:178-226`，docstring 与实现都补 absent 字段）。两侧语义不同。
- `validate_config` 允许缺字段（`config.py:86-119` 只校验 present 字段）。
- 但消费侧有**直接下标**读取：`mw.py:161` `_ap_config.cached_load(project_dir)["enabled"]`、`autopilot/conductor.py:3975` `config.cached_load(project_root)["poll_interval_sec"]` → 若文件缺这两个键就 `KeyError`（serve 监督循环 / conductor 主循环）。
- 因此 CLI 侧若「`load_config` → 改一个键 → `save_config`」，在**已有 partial 文件**上会继续写出 partial 文件；TS 侧 `saveConfig` 则总会写全字段，会把同一文件「补全」。→ 新 CLI 的写入必须显式 `{**default_config(), **existing}` 补全（或复用 TS 的规范化语义），否则 AC-001 的「其它字段逐字不变」与运行时安全冲突。→RQ-2

---

## Q3 报错与退出码约定

- **无统一 helper**（全仓没有 `def _fail` / `die` / `parser.error` 调用）。
- 命令函数返回 `int`；顶层 `sys.exit(dispatch[args.subcommand](args))`（`mw.py:4908-4928`）。`SystemExit` 在其他地方只出现在独立脚本的 `main()`（如 `autopilot/roadmap_check.py:60`）。
- 错误统一形状：`print(f"[mw <group> <action>] Error: <一句话>", file=sys.stderr)` + `return 1`。
  - 例：`mw.py:3140-3143`（unknown role）、`:3148-3151`（value 形状）、`:3155-3158`（unknown prefix）、`:2091`（project dir 不存在）、`:619-636`（target set 的 game/engine/uproject 不存在）。
- 退出码语义：`0` 成功；`1` 业务失败/需要动作（`mw doctor` 的 `0 if healthy else 1`，`mw.py:525`）；argparse 自身错误（缺子命令、缺 `--project`）= **exit 2**（`required=True`，`:4645`；无 `parser.error` 调用）。
- 「什么都没写」时会额外补一句 stderr 说明（`rag init`：`mw.py:2200-2204`）。
- 失败前置校验（fail-closed）：读已有配置失败就**拒绝写**，避免把坏文件覆盖成看起来正常的文件——`mw model set`：`load_dispatch_config` 报错 → `Error: existing dispatch.yml is unusable ({err}) — fix or remove it before writing`（`mw.py:3159-3166`）；`ue-toolchain` 的 `_toolchain_load_config` 同理（`mw.py:947-953`）。这条对本 key 是硬要求：config.json 非法时 `set` 必须拒绝写（`save_config` 会 `validate_config` 抛 `ConfigError`，但 CLI 必须自己 catch 并转成 `[mw autopilot ...] Error: ...` + return 1）。
- 现状：`autopilot.config.ConfigError` **在 mw.py 里没有任何 catch**（`mw.py` 只 import + `cached_load`，`:41`/`:161`），因为目前没有 CLI 消费者。→ 新 CLI 是第一个需要决定 catch 风格的地方。

---

## Q4 CLI 层测试范本

测试文件位置：`packages/multi-workers/test_*.py`（与被测模块同目录，`pytest`，无 conftest）。CLI 层三形状：

### 形状 A — 直接调 `mw.cmd_*` + 手搓 `argparse.Namespace`（最快、断言文件内容）

`test_dispatch_models.py:422-452`：

```
def _model_args(project, action, role="", value="") -> argparse.Namespace:
    return argparse.Namespace(project=str(project), model_action=action, role=role, value=value)

class TestModelCli:
    def test_set_show_clear_roundtrip(self, tmp_path):
        assert mw.cmd_model(_model_args(tmp_path, "set", "review", "timi/glm-5.3-air")) == 0
        config, err = mw_common.load_dispatch_config(tmp_path)
        assert err is None and config["models"] == {...}
```

- **`tmp_path` 就是临时项目 root**（pytest fixture），不需要建 `.agenticdoc`——命令自己 `mkdir(parents=True)`。
- stdout 断言用 `capsys`：`test_dispatch_models.py:454-464`（`out = capsys.readouterr().out`，再 `assert "... " in out`）。
- 反向（必须拒绝）用例形状：`test_dispatch_models.py:440-452`（坏值返回 1 且**文件不存在**；已有坏文件时返回 1 且**原文件字节不变**）。
- `test_mw_target.py:37-70` 提供两个可复用 helper：`_set_args(...)`（Namespace 工厂）与 `_snapshot(root)` + `_diff_snapshots(before, after)`（全树 `(mtime_ns, size)` 快照 → changed/added/removed），用于断言「写面只有目标文件」：`test_mw_target.py:143-160` 甚至先放一个 `README.md` 再断言它没变。

### 形状 B — 真子进程跑 `mw.py`（验 argparse 层、编码、零交互）

`test_rag_init.py:63-104`（`unittest.TestCase`，非 pytest）：

```
def _run_at(self, project, *args):
    return subprocess.run(
        [sys.executable, str(MW_PY), "rag", "init", f"--project={project}", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=60, env=dict(os.environ))
```

要点：`MW_PY = pathlib.Path(__file__).parent / "mw.py"`（`:31`）；`--project=<dir>` 用**等号形式**；`encoding="utf-8"` + `errors="replace"`（Windows GBK stdio）；`stdin=DEVNULL` 验零交互；`setUp` 里用 `mock.patch.dict(os.environ, {...HOME/USERPROFILE/MW_RAG_SERVERS_HOME...})` 做 hermetic 隔离（`test_rag_init.py:64-86`）。断言用全树 sha 快照（`:102-109`）。

### 形状 C — config 助手级（幂等/原子/缓存）可照抄用例

`test_autopilot_config.py:91-103`（本 key 最直接可抄）：

```
def test_roundtrip_and_atomic_write(tmp_path):
    cfg.invalidate_cache()
    modified = cfg.default_config(); modified.update({"enabled": True, ...})
    path = cfg.save_config(tmp_path, modified)
    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n")
    assert not list(path.parent.glob("*.tmp"))          # 原子替换完成、无残留
    assert cfg.load_config(tmp_path) == modified
```

`test_autopilot_config.py:113-145`（缓存失效实测：外部改写 + `os.utime` 前进 10s 后 `cached_load` 必须 miss；`save_config` 后必须立即命中新值）。`test_autopilot_config.py:105-110`（非法值必须抛且**不落盘**）。

### doctor 段落测试形状

`test_dispatch_models.py:470-485`：`report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)` → 断言 section dict；再 `mw_common.format_doctor_text(report)` 断言**文本行**（缺席时不出现该行）。`test_mw_target.py:238+` 同理。

运行：仓库根 `./test.sh`，或包内 `python -m pytest test_<file>.py -q`（AGENTS.md 的规则）。

---

## Q5 `mw doctor` 实现结构与新增检查项

### 5.1 结构

```
_parse_args → doctor_p（mw.py:4654-4666: --project/--providers/--json/--fix/--stale-after）
cmd_doctor（mw.py:499-525）
  ├─ mw_common.load_providers(...)
  ├─ mw_common.doctor_report(project_dir, fix=, config=, stale_after_sec=)   # mw_common.py:2088-2126
  │    ├─ report["service"|"proxy"|"proxy_log"|"orphan_proxy"|"launcher_log"|"queue"
  │    │           |"worker_liveness"|"credentials"|"bundle"|"target"|"dispatch"|"pi_shell"]
  │    ├─ (fix) report["fix"]["applied"]
  │    └─ issues, suggestions = _doctor_issues(report)                       # mw_common.py:2012-2085
  │       report["summary"] = {"healthy": not issues, "issues": [...], "suggestions": [...]}  # :2124
  ├─ report["conductor"] = _ap_conductor.conductor_status(project_dir)       # mw.py:514
  ├─ report["rag"] = _doctor_rag(project_dir)                                # mw.py:517
  ├─ --json → json.dumps(report)  |  文本 → mw_common.format_doctor_text(report) + RAG 单行  # mw.py:518-523
  └─ return 0 if report["summary"]["healthy"] else 1                        # mw.py:525
```

- 输出格式两条：`--json` = 整个 report；文本 = `format_doctor_text`（`mw_common.py:2128-2259`，一行一发现，末尾 `summary:` + 每行 `suggest:`）。文本消费方在 TS：`formatDoctorReport`（`ui-bridge.ts:1693`）、`formatRagDoctorLine`（`:1663`）；JSON 结构镜像在 `DoctorJson`（`mw-runner.ts:341-404`，新 section 需在此声明可选字段）。
- **两条报告路径**：`mw doctor`（`mw.py:509-525`）与 `mw bootstrap` 第 8 步（`mw.py:4143-4148`，只补 `conductor`，**不补 `rag`**）。放 `mw_common.doctor_report` 里的 section 两边都有；放 `cmd_doctor` 的只有 `doctor` 有。
- `_autopilot` 相关的既有 section 只有 `conductor`（`report["conductor"]`，由 `_ap_conductor.conductor_status` 提供，`mw.py:514`），**没有 autopilot 配置 section**。

### 5.2 新增一个检查项 = 5 处改动

1. 写 `def _doctor_autopilot(project_dir) -> dict`（照 `_doctor_dispatch`，`mw_common.py:1254-1271`，或放 `cmd_doctor` 照 `_doctor_rag`，`mw.py:2248-2290`）。
2. 在 `doctor_report` 注册：`report["autopilot"] = ...`（`mw_common.py:2115-2123` 区段内）。
3. 在 `_doctor_issues` 转 issue/suggestion（`mw_common.py:2012-2085`，末尾 `return issues, suggestions` 在 `:2085`）。
4. 在 `format_doctor_text` 加行（`mw_common.py:2128+`；缺席时**不打印**的写法见 `dispatch` 行 `:2229-2236`：`if dispatch is not None and dispatch.get("exists")`）。
5. 若 TS 面板要显示：`DoctorJson` 加可选字段（`mw-runner.ts:341-404`）+ `formatDoctorReport`/`formatRagDoctorLine` 式渲染（`ui-bridge.ts:1663/1693`）。测试：`doctor_report(tmp_path, ...)` + `format_doctor_text`（`test_dispatch_models.py:470-485`）。

### 5.3 「配置存在但值为空 ⇒ 告警」的既有先例

**没有 issue 级先例**；既有惯例是把「便利配置存在问题」降级为 `suggestions`（不翻 `healthy`、不改退出码），只有「链路正确性」才进 `issues`：

| 场景 | 现行为 | 位置 |
|---|---|---|
| target.yml 非法 / toolchain 探针检查失败 | **issue**（`target config error (...)` / `target toolchain check failed: ...`） | `mw_common.py:2035-2043` |
| `.mw/dispatch.yml` 存在但坏 | **suggestion**（`dispatch.yml unusable ... model defaults are ignored; fix or remove`） | `mw_common.py:2063-2067`，设计理由在 `:1254-1263`（「convenience and must not flag the chain unhealthy」） |
| pi settings.json shellPath 缺/坏/不可读 | `broken` = issue；`missing`/`unreadable` = suggestion | `mw_common.py:2049-2060` |
| RAG 配置坏 / 服务器不可达 | **从不进 `issues`**（section 里带 `error`，文本行由 `_format_rag_doctor_line` 打 `rag: ERROR - ...`） | `mw.py:2248-2307`；`cmd_doctor` 注释 `mw.py:515-516` |
| `xkey_repair=true` 且 `xkey_verify_cmd=[]` | **现状**：`xkey-verify-failed` timeline 事件 + escalation 文件 + 工单 `status=verify_failed`，detail = `xkey_verify_cmd is empty (cannot prove green)` | `conductor.py:3460-3470`（空命令分支）→ `_xkey_verify_failed` `:3334-3368`（timeline `:3365-3368`、`_xkey_escalation_write` `:3363`） |

即 AC-008 说的「现状静默 fail-closed」**不成立于 timeline**（timeline 有事件、工单有 `verify_failed` 状态、有 escalation 文件）；成立的部分是「没有 doctor 聚合告警、没有派发前预检、失败 detail 里没有修复提示」。另一个「检查 + 修复提示」的形状先例是 `mw update-env` 的 check dict：`{"id","layer","status","detail","fix","auto"}`（`mw.py:4322-4323`）+ 文本渲染（`:4568+`），若 AC-008 要「含修复提示」，这是现成模板。

---

## Q6 目标项目根的选择惯例

- **`--project` 显式必填**：`mw.py` 共 20 处 `--project`，其中 19 处 `required=True`（`mw.py:4634,4652,4658,4673,4688,4698,4715,4723,4729,4733,4736,4804,4827,4842,4856,4883,4888,4892,4896`）；唯一例外是 `bootstrap --project default=None`（`mw.py:4777-4778`，help：「Project directory to init/start (default: this repo root)」）。`build` / `setup` / `pull-agentictask` / `push-agentictask` 等机器级命令**没有** `--project`。
- **无 cwd 探测**：`mw.py` / `mw_common.py` / `launcher.py` 全仓 grep `Path.cwd()` / `os.getcwd()` → `mw` 自身零命中。
- **无 `detect_root`**：`detect_root.py` 是 AgenticTask 框架的脚本，由 `autopilot/advance.py:81-141` 以子进程探测（并校验 `PROJECT_ROOT` 与目标项目一致）；`mw` CLI 从不调用它。
- **cwd 默认的先例只有独立脚本**：`autopilot/roadmap_check.py:36-39` `--project default=os.getcwd()`（`help="... (default: cwd)"`），它是 `python autopilot/roadmap_check.py` 直接运行、不属 `mw` 分派表。
- **机器级根**的定位惯例：`mw_common.machine_rag_servers_path`（`:378-395`，顺序 `MW_RAG_SERVERS_FILE` → `MW_RAG_SERVERS_HOME` → `$HOME` → `$USERPROFILE`，缺失即 `None`，**从不建目录**）与写侧镜像 `_rag_machine_write_path`（`mw.py:2017-2037`，同样顺序但可返回「待创建」路径）。
- 结论：`mw autopilot verify set/show/clear` 应照 `target`/`model`/`rag` 一律 `--project required=True`（不要引入 cwd 默认；`bootstrap` 的默认根是特例，且其语义是「本仓根」而不是「cwd」）。机器级层是**另一条路径**（`$HOME/.agents/...`），由显式 flag（`--machine` / `--only-machine`）选择，而不是靠 `--project` 缺省。

---

## Q7 冲突检查：`autopilot` 是否已是既有名

### 7.1 事实清单

| 面 | 现状 | file:line |
|---|---|---|
| mw 子命令 | **不存在** `add_parser("autopilot")`；`python mw.py --help` 实测 17 组：serve,start,stop,status,doctor,target,partition,model,init,pull-agentictask,push-agentictask,setup,bootstrap,build,update-env,ue-toolchain,rag | `mw.py:4646-4904`（全量）；实跑输出 |
| Python 包 | `packages/multi-workers/autopilot/`（`config.py` `conductor.py` `gates.py` `xkey.py` `dispatch.py` `state.py` `timeline.py` `advance.py` `closure.py` `roadmap.py` `roadmap_check.py` `audit_evidence.py` + `__init__.py`）；`mw.py` 顶部已 import | `mw.py:41-42`；`_CONDUCTOR_PY = _SCRIPT_DIR / "autopilot" / "conductor.py"` `mw.py:47` |
| pi 斜杠命令 | `/autopilot` 已注册，子命令 status/gates/gate/timeline/enable/disable/pause/resume/monitor/roadmap | `console.ts:85-87`（usage `:81-83`，命令表 `:11-35`） |
| 文档 | README 有 `## Autopilot 配置与停滞处置` 节（`:217`）；UPDATE.md 指令矩阵与锚点提到 autopilot 模块 | `README.md:217`、`UPDATE.md:46-72`、`UPDATE.md:77` |
| `mw autopilot ...` 字样 | 全仓只出现在本 key 的 `spec.md` / `evidence`，**没有任何既有代码/文档承诺** | `git grep "mw autopilot"` → 仅 `.agenticdoc/mw-autopilot-verify-cli/**` |
| 名字被锁的测试 | 没有任何测试锁定 mw 顶层子命令清单（`_parse_args` 只在 `mw.py` 与 `launcher.py`；测试里零引用顶层清单） | 全仓 grep `_parse_args` 命中仅 `mw.py:4643`、`launcher.py:1017` |

### 7.2 冲突风险判定

- **argparse 层面：无冲突**。Python 模块名（import 命名空间）与 argparse 子命令名（argv 字符串）互不相干；`mw autopilot` 也不会遮蔽 `python -m autopilot`（该包无 `__main__.py`）。
- **语义一致性：正向**。`autopilot` 已是该子系统的用户可见名字（pi 侧 `/autopilot`），`mw autopilot` 属于「同一子系统 + 新前端」，比造新名（如 `mw verify-cmd`）更符合既有词汇。
- **真正的风险（应在 spec 里处理）**：
  1. **同文件双写者竞争**：窗口 `/autopilot enable|disable|pause|resume` 走 `readConfig` → 改字段 → `saveConfig`（`console.ts:276-331`、`:333-352`；`status-model.ts:234-260`），CLI `mw autopilot verify set` 也会 read-modify-write 同一文件 → 两者并发时**后写者覆盖前写者**（丢失更新），而现有 `save_config` 只有原子替换、**没有锁**；仓库里的锁只有 `_workers.parallel` 用的 `lock_path/acquire_lock`（`mw_common.py:1438`、`:1480-1493`，`O_CREAT|O_EXCL`）。spec §2.3 只要求「原子」，未覆盖 lost update。
  2. **层级不一致**：`/autopilot` 是扁平子命令（`/autopilot status`），本 key 设计成两级（`mw autopilot verify set`）。若将来 verify 之外还要加能力，两套层的命名会分叉；建议在 spec 里写明「mw 侧组名 `autopilot` + 二级组 `verify`」与窗口侧 `/autopilot` 不要求镜像。
  3. **`dist` 产物**：扩展 bundle 内嵌的是 TS 侧字符串，不含 mw 子命令名；`mw autopilot` 不影响 dist（→RQ-3）。

---

## AC 批判（AC-001/002/003/004/005/010）

> 判定口径：AC 必须**可机械判定**（有 file:line 可指的实现点或可照抄的测试形状），且不得与既有惯例冲突。

### AC-001（set 写 argv + 其它字段逐字不变 + 重复执行零 diff）

- **表述不清 1（命令行形状未定形）**：`set` 如何收 argv 在 repo 内无先例（§1.3）；spec 场景 A 的 `mw autopilot verify set -- python -m pytest -q` 依赖 REMAINDER，而 REMAINDER 会吞掉其后的 `--project`（`mw.py:983-985` 自己记录了这个坑）。**建议**在 AC 里写死一种：`mw autopilot verify set --project <dir> -- <argv...>`（并且规定 `--project` 必须出现在 `--` 之前），或改为 `--cmd`（可重复，一次一个 token）。判据补充：加一条 argparse 级测试断言 `--project` 在 `--` 之后时**报错**（而不是静默把它写进 argv）。
- **与既有惯例冲突（「其它字段逐字不变」）**：与 `_autopilot/config.json` 的两个既有写者都不一致——Python `save_config` 写 `json.dumps(cfg, indent=2)`（`config.py:144`，格式/缩进/序由调用方 dict 决定），TS `saveConfig` **强制**规范化成全字段 + `DEFAULT_CONFIG` 序（`status-model.ts:236-249`，docstring `:228-233`）。若文件是手写的（不同缩进、CRLF、字段乱序、缺字段），「逐字不变」与「用既有助手写」二者不可同时成立。**建议**改成可判定的两条：①「未被本命令触碰的字段，其**值**与生效语义不变」；②「连续两次同参数 `set` 之后，文件与该键从未被写过时的规范形状**逐字节相同**」（规范形状 = `save_config` 的输出形状）。这两条都能用 `test_autopilot_config.py:91-103` 的形状判定。
- **零 diff 与 mtime 的关系**：`save_config` 无内容短路，同值重写也会改 mtime（触发下游 `cached_load` miss）。若 AC 想表达「真无副作用」，应显式要求照 `_rag_install_skill` 的短路先例（`mw.py:1167-1169`：内容相同就打印 unchanged 且不写文件）。否则 D-002 的「写入后下一 tick 立即拾取」与「重复执行零 diff」需要分别定义（前者按 mtime+size，后者按字节）。
- **隐含风险**：`load_config` 不补默认键（§2.4）→ 若在 partial 文件上 read-modify-write，会写出仍缺 `enabled`/`poll_interval_sec` 的文件，导致 `mw.py:161` / `conductor.py:3975` KeyError。**建议**把「写入前用 `{**default_config(), **existing}` 补全」写进 AC-001 或 §2.3。

### AC-002（无需重启即可拾取，判据 = mtime+size）

- 这条基本属 RQ-2 领域，但 **CLI 侧必须承担的只有一条**：写入必须造成 (mtime_ns, size) 变化且落盘路径就是 `config_path(root)`（`autopilot/config.py:77-78`）。可机械判定部分：`cached_load` 的比较键是 `(st.st_mtime_ns, st.st_size)`（`config.py:165-169`），且 `save_config` 只清**本进程**缓存（`:146`）——对 conductor/serve 进程**无作用**，它们的拾取完全靠 stat。因此 AC-002 的措辞「无需重启即可拾取」应改成「写入后 ≤ 一个 tick（`poll_interval_sec`，默认 4s、硬上限 5，`config.py:15`/`:47`/`:63`）被下一 tick 的 `cached_load` 读到」；窗口侧同类措辞先例：`console.ts:226` 「the conductor reads the answer within one poll interval (<=5s)」。
- **与 AC-001 的潜在矛盾**：若 AC-001 要求「幂等且零 diff（含不动 mtime）」，那么第二次 `set` 不会造成 mtime 变化，也就无法被 pickup 逻辑区分——这没问题（内容没变），但 AC-002 的测试若用「同参数 set 两次 → 观察 mtime 变化」来自证拾取就会失败。**建议**：AC-002 的测试用「**值变化**的 set」做拾取断言，AC-001 的零 diff 用例单独做（不混用 mtime）。
- 需要 AC 明确「mtime 精度/同秒写入」的替代判据（本 RQ 不判定）→RQ-2。

### AC-003（show 打印有效解析 + 来源层级）

- **可照抄的形状**：`mw model show`（`mw.py:3205-3230`：`config: <path> (missing — nothing configured)`、`window model: ...`、每个 role 打 `configured` 或 `(unset) → {effective} [{source}]`）与 `mw rag list`（`_rag_format_origins` `mw.py:1210-1230` + `_cmd_rag_list:1231-1256`，逐字段 `field = value [origin]`）。`mw target show` 的 `_print_target_summary`（`:606-613`）是「有效解析」的最小骨架。
- **表述不清**：「来源层级（项目/机器/内置默认）」在 `_autopilot/config.json` 上尚**不存在**——`config.py` 零处读 `$HOME`/env（→RQ-2/RQ-4 已证），机器层连**路径**都还没定（spec U-1）。所以 AC-003 现在不可判定：`show` 的 `[source]` 取值域依赖一个未创建的读取层（路径函数 + 优先级 + origin 报告）。**建议**：AC-003 拆成 ①（不依赖 U-1，立即可判定）show 打印「项目文件路径 + 该文件是否存在 + `xkey_verify_cmd`/`xkey_verify_timeout_s` 当前有效值 + 值来自文件还是内置默认」；②（依赖 U-1）机器层 origin 标注。①的判据可以完全照 `mw model show` 的 `[source]` 文本断言。
- 顺带：AC-003 说「超时」要显示——`xkey_verify_timeout_s` 的默认 1800 来自 `DEFAULT_CONFIG`（`config.py:56` + `:70`），所以「内置默认」这一层已有确切值可打。

### AC-004（clear 只移除本 key 键，其它字段顺序/格式不受影响）

- **与惯例冲突**：见 AC-001 的同类分析——两个既有写者都会**重排/重缩进/补全**整个文件（`config.py:144`、`status-model.ts:236-249`）。「顺序/格式不受影响」在「用既有助手写」的前提下不可满足（只有当 CLI 自己做行级 JSON 编辑时才可能，而仓库只有 YAML 行级编辑的先例 `_apply_bootstrap_line` `mw.py:535-556` 与 `_replace_top_level_block` `:2054-2073`，没有 JSON 行级编辑先例）。**建议**把「其它字段与其顺序/格式不受影响」改成「其它字段的**值**不受影响；文件被规范化为 `save_config` 形状」。
- **表述不清（clear 的终局）**：若 clear 后只剩默认值，**删文件还是留全默认文件？** 两个先例都在仓库里：删除文件（`_target_clear` → `yml.unlink()` `mw.py:733`；`_partition_clear` → `yml.unlink()` `:2970`，help 明写「delete target.yml when no mode block remains」`：4710`）vs 留文件（`mw model clear all` 写 `{}` 空 YAML，`_model_write` `:3116-3123`）。这一选择有语义后果：`config.py:8-9` 与 `monitor.ts:79` 都把「文件缺失」解释为「autopilot 从未启用 / everEnabled=false」，留一个全默认文件会改变该语义。**建议** AC-004 明确二选一，并加一条断言（删文件 ⇒ `config_path(root).exists() is False`，或留文件 ⇒ 与 `save_config(default_config())` 逐字节相同）。
- 幂等性同样要定形：对不存在文件的 clear、对不含该键的文件的 clear，输出与退出码（先例：`mw.py:3182-3184` 「nothing configured」= return 0）。

### AC-005（层级优先级可机械判定：命令行/项目/机器/默认，真值表）

- **表述不清（「命令行」这一层的语义）**：`set`/`clear` 是**写**命令，没有「命令行覆盖」的读语义；若 AC-005 指读侧（`show`）支持一次性覆盖（如 `show --cmd ...`），spec 未在任何地方描述该 flag。既有层级解析先例都是**读侧 merge + origin**（RAG：字段级 merge、`origin` 逐字段，`mw_common.py:483-500` + `_rag_format_origins` `mw.py:1210-1230`；model：链式回退 + `[source]`，`mw.py:3219-3227`），而 CLI 一次性覆盖（`--pi-port` 之类）从不与持久层做 merge。**建议**：要么把「命令行」层降级为「仅 `show` 的只读覆盖 flag（可选，未实现则从 AC 中删除）」，要么明确它只用于 `set` 的一次性写入（那就不是「解析优先级」，而是「写入目标」）。
- **不可判定（依赖未定项）**：机器层的**文件路径/文件名**未定（U-1），真值表无法写全。RAG 的先例是「机器层 = 不同文件（`~/.agents/rag-servers.yml`，`mw_common.py:378-395`）+ 字段级 merge + origin」。**建议**：AC-005 在 U-1 定稿后再锁，且真值表要按 RAG 形状写成「同名字段逐层覆盖，origin 值域 = {cli, project, machine, default}」，并用 `origin` 而非新造的措辞。
- 另一处：spec 写「`cached_load` 以 mtime+size 失效」，AC-005 又是「优先级」——两者是不同机制（缓存失效 vs 层级 merge），不要把「缓存命中」当成「层级来源」。

### AC-010（文档写进 UPDATE.md/README 含两层区别，且与 `mw autopilot --help` 输出一致）

- **冲突/无先例**：「与 `--help` 输出一致」在本仓库**没有测试先例**。唯一的 doc⇄CLI 逐字节 parity 先例是 `docs/rag-config-guide.md` 的 fenced block ⇄ `mw rag init --print`（`test_rag_docs.py:1-20` 声明，用例 `:157-189`；另有「手册里引用的错误文本必须在源码里逐字存在」`：296+`）。`README.md` / `UPDATE.md` **不被任何测试读取**（全仓测试里出现的 `README.md` 只是被当作「不该被写的旁观文件」，如 `test_mw_target.py:143`、`test_mw_partition.py:1064`）。**建议**：把「与 `--help` 输出一致」改成可判定的形式——①README/UPDATE 只要求「命令名、flag 名、层级」三列与 `--help` 语义一致（人工评审项，不进测试）；②若要机器判定，照 `test_rag_docs.py` 加一块 fenced block（例如 `mw autopilot verify --help` 的 usage 行）做逐字节/行比对。
- **落点先例**：UPDATE.md §2「指令矩阵」有 `层级` 列（`UPDATE.md:46-72`，行如 `mw update-env` 的「机器+项目」）：`mw autopilot verify set` 的「项目 / 机器」归属就写在这一列；README 的两层对照表模板是 RAG 段（`README.md:258-267`，机器层 `~/.agents/rag-servers.yml` / 项目层 `<control>/.mw/rag-servers.yml` 两行）。README 的 CLI 表（`README.md:63-86`）目前连 `partition`/`rag` 都没列全（另有独立段），所以 AC-010 不要要求「CLI 表必须有该行」。

### 批判汇总

| AC | 性质 | 关键问题 | 建议改法 |
|---|---|---|---|
| AC-001 | 冲突 + 不清 | `--`/REMAINDER 形状未定（吞 `--project`）；「其它字段逐字不变」与两个既有写者的规范化行为冲突；partial 文件会写坏运行时读取 | 定形 `--` 位置 + 断言 `--project` 前置；改判「值不变 + 二次 set 后与规范形状逐字节相同」；写入前补全默认键 |
| AC-002 | 不清（细项） | 「无需重启」= 靠 stat（save_config 只清本进程缓存）；与 AC-001 的零 diff/mtime 可能混用 | 改「≤1 tick 内被 `cached_load` 读到」；拾取测试用**值变化**的 set |
| AC-003 | 不清/不可判定 | 机器层路径未定 ⇒ 「来源层级」值域不存在 | 拆 ① 项目 vs 内置默认（立即可判定）② 机器层（依赖 U-1） |
| AC-004 | 冲突 + 不清 | 顺序/格式不改与既有写者冲突；clear 终局（删文件 vs 留默认）未定，且有语义后果 | 改判「值不变 + 规范形状」；明确删/留并加断言 |
| AC-005 | 不清/不可判定 | 「命令行」层语义未定义；机器层路径未定；缓存失效 ≠ 层级 merge | 删或定义 CLI 覆盖 flag；按 RAG 的 merge+origin 形状写，U-1 后再锁 |
| AC-010 | 无先例 | README/UPDATE 无任何测试；`--help` 一致性不可机械判定 | 拆「人工一致」与「fenced block 逐字节比对（照 test_rag_docs）」；落点 = UPDATE.md:46-72 层级列 + README.md:258-267 两层表 |

---

## 附：复现命令（本文件所有 CLI 事实）

```
python mw.py --help                      # 17 组，无 autopilot；stop/status 不列（无 help=）
python mw.py model show --help           # 二级组 + required --project 的 usage 形状
python mw.py rag init --help             # 布尔开关/choices/default 的 help 文案风格
```

换行/BOM 探针（在 `%TEMP%` 一次性跑，不写仓库）：`Path.write_text` 默认 newline 在 Windows 产出 CRLF；`newline="\n"` 产出 LF；`json.loads` 读带 BOM 的 utf-8 文本抛 `JSONDecodeError`，`utf-8-sig` 可读。