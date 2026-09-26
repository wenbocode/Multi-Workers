# design RQ-D3 证据：verify 的 cwd 根锚定与占位符展开设计

- key：`mw-autopilot-verify-cli` · 日期：2026-09-26 · 类型：design 期只读调研（RQ-D3）
- 唯一写面：本文件。除本文件外未修改仓库任何文件。
- 取数环境：Windows 10.0.26100 / PowerShell 5.1；HEAD 侧工作树 `H:\git\Multi-Workers`。
- 行号约定：以 `read`（offset）为准；`grep` 只用于定位，不做行号对账。
- 前置：RQ-4 已证 worker cwd = partition 根（`launcher.py:894-906`、spawn `:960`），verify cwd = control 根（`conductor.py:3459/3471`）；配置层不强制 control 与 partition 的关系（`mw_common.py:2578-2589` 只约束 parent/partition）。本文件在其上做设计定稿。

---

## 0. 结论摘要（可直接进 design.md）

| # | 问题 | 结论 |
|---|---|---|
| Q1 | 渲染器复用 | 新增 `mw_common.render_argv(cmd, config) -> list[str]`（放 `mw_common`，不放 `xkey.py`）。公共部分只抽「partition 已定义 token 名列表构造器」，复用 `_TOKEN_RE`/`_tc_fail`/根字段；**不抽替换循环**，`render_toolchain_command` 一行不改（zero behavior change）。 |
| Q2 | token 集合 | verify argv 按 mode 使用「该 mode 的根 token + `{control}`」：partition=`{control}/{parent}/{partition}/{<root name>}`；dual=`{control}/{game}/{engine}/{uproject}`；single/legacy=`{control}/{game}/{uproject}`（`{engine}` 未配置即 fail-closed）。**新增 `{control}` 仅限 verify argv**，不进 toolchain token 集（避免动 toolchain 契约与 TS parity）。 |
| Q3 | cwd 键 | 键名 `xkey_verify_cwd`；值域**枚举**（mode 分派），缺省空串 `""` = “按 mode 自动”；缺省解析 = worker cwd 规则（partition→partition、dual→game、single→control）。非法值 fail-closed，kind 复用 `invalid-config`（不新增 kind）。 |
| Q4 | S3 同族 | **必须一起改**。同族锚点共 5 处（`2513/2576/2942/3408/3651`），只改 verify cwd 会让 apply 落在 control 根 → 目标文件缺失或改错文件 → verify 必红 → 回滚，工单永不闭环。 |
| Q5 | 写/消费一致 | set 写前用**同一解析器** dry-run（argv+cwd），失败不落盘；`show` 同时打印配置值与**展开后** argv/cwd（对 AC-004 必需）。ticket 的 `verification.command`（`conductor.py:2579`）目前存**未展开**值，建议改存展开值或并存。 |
| Q6 | 回归面 | 改动全部在 `cfg["xkey_repair"]` 门内（`conductor.py:224`）；现网三项目 xkey 通道全关（FM/E2 无 xkey 键、MW 无 config），加默认非 partition 缺省 = control 根 ⇒ 既有 xkey e2e 逐字不变。新增键会改 config 形状（12→13 键）与 TS 镜像，属预期 AC 变更。 |
| AC | 可判定性 | AC-013/AC-014 基本可机械判定，但需先钉死 4 处歧义：枚举 vs 路径串、dual 缺省根、whole-token 的精确定义、错误文本的 “original”。fixture 用 `test_partition_dispatch.py:178` 的 `_write_partition_yml` 形状即可造 `control≠partition≠parent`。 |

---

## 1. Q1 渲染器复用性：`render_toolchain_command`（str）≠ verify 需要的 argv（list）

### 1.1 现状事实

- 单点：`mw_common.render_toolchain_command(command: str, config: dict) -> str`（`mw_common.py:2866`）。
  - partition 分派 `_render_partition_command`（`mw_common.py:2894-2914`）：对**整条字符串**做 `str.replace("{parent}"/"{partition}"/"{<root>}")`（`:2897-2905`），再 `_TOKEN_RE.search(out)` 残留检查（`:2907-2913`），残留即 `_tc_fail("missing-field", ...)`。
  - dual/single：只对 `{game}`/`{engine}`/`{uproject}` 做 `if "{x}" in out` 替换（`mw_common.py:2878-2891`），**无残留检查**，未定义占位（`{sdk}`/`{python}`）原样透传（RQ-4 §1.4）。
- token 形状：`_TOKEN_RE = re.compile(r"\{([A-Za-z0-9_-]+)\}")`（`mw_common.py:2415`）。
- 值域字段：`control_root`/`parent_root`/`partition_root`/`roots`/`game_root`/`engine_root`/`uproject`（`mw_common.py:2661-2682`、`:2527-2550`），根归一化 `_tc_normalize_root`（`mw_common.py:2321-2325`），`{uproject}` 走 `discover_uproject`（`mw_common.py:2843-2859`）。
- verify 消费侧是 **list argv + `shell=False`**：`xkey.run_verification(cmd, cwd, run_dir, timeout)` 里 `argv = [str(part) for part in cmd]` 后 `subprocess.run(argv, shell=False, cwd=..., ...)`（`xkey.py:1272-1305`），**零展开**；`cwd=str(cwd)`（`:1303`）也**无任何根解析**。

**结论：`render_toolchain_command` 的返回类型与替换域都不能被 verify 直接复用**（字符串 vs list；整串 replace vs 逐元素）。必须新增函数。

### 1.2 推荐：新增 `mw_common.render_argv(cmd: list[str], config: dict) -> list[str]`

**放 `mw_common`（不放 `autopilot/xkey.py`）**，理由（均为既有事实）：

1. token 语义的单一归属地就是 `mw_common`：`_TOKEN_RE`（`:2415`）、`_tc_fail`（`:2295`）、`_TARGET_KINDS`（`:2278-2284`）、根字段与 `discover_uproject` 全在此。
2. 两个消费者都已经 import `mw_common`：`conductor.py:49`（`import mw_common`，用于锁/root 解析等）与 `mw.py`（`mw_common.render_toolchain_command` 调用点 `mw.py:980`）。放 `xkey.py` 会迫使 CLI 为了一个渲染函数去 import `autopilot.xkey`（xkey 是纯逻辑模块，模块 docstring `xkey.py:1-4` 声明它不承担配置渲染）。
3. 若放 `xkey.py`，`render_argv` 还得反向依赖 `mw_common` 的 `_TOKEN_RE`（xkey 已 import `mw_common`：`xkey.py:55-60`），造成“渲染在 xkey、语义在 mw_common”的裂脑。

**需抽出的公共部分（最小集）：**

| 抽什么 | 从哪抽 | 用途 | 是否改 toolchain 行为 |
|---|---|---|---|
| partition 已定义 token 名列表构造器（`["{parent}","{partition}", *sorted("{name}")]`） | `_render_partition_command` 的 `defined = ...`（`mw_common.py:2909`） | 两个渲染器的 “undefined placeholder” 错误文本共用同一清单，保证逐字一致 | 否（只是把内联列表提为函数，文本不变） |
| 复用 `_TOKEN_RE`（`:2415`）、`_tc_fail`（`:2295`）、`missing-field` kind（`:2281`） | 不新增 kind | 错误语义与 toolchain 对齐，TS parity（`_TARGET_KINDS` 是 parity 契约，`:2277`）不动 | 否 |
| 复用根字段解析（`control_root`/`parent_root`/`partition_root`/`roots`/`game_root`/`engine_root`/`discover_uproject`） | 只读 config dict | 数值来源单一 | 否 |

**不要抽的：替换循环。** 理由：toolchain 是「整串 `str.replace` + 嵌入替换也生效（`x{partition}` → `x<root>`）+ dual/single 未定义占位静默透传」；verify 要的是「逐元素 whole-token + 未定义 fail-closed」。把二者合并成一个“统一渲染器”必然要么放宽 verify 的 fail-closed、要么收紧 dual/single 的透传——两者都是行为变更。**`render_toolchain_command` 的 body 一行不改。**

**不改 toolchain 行为的硬证据（回归护栏）：** `render_toolchain_command` 有 4 个既有消费者（`mw.py:795` target show、`mw.py:980` ue-toolchain run、`mw.py:2906` partition show、`mw_common.render_partition_profile_md:2974` → `dispatch.py:482`），且它的行为由跨语言 parity fixture 锁死：`test_common_target_config.py:92-103` 逐 case 跑 `render_toolchain_command` 并和 `_substitute` 对账，同一 case 集由 TS vitest 执行（`test_common_target_config.py:1-10` 的 parity lock 说明）。任何 toolchain 渲染变化都会红这个 parity 集。因此 Q1 的“不能变更 toolchain 行为”可直接由该测试集机械验证。

### 1.3 `render_argv` 的推荐语义（供 design.md 定稿）

对每个元素 `element`：
1. 若 `_TOKEN_RE.fullmatch(element)`：取 token 名 `name` → 解析（见 §2/§3）；未定义/未配置 ⇒ `TargetConfigError(kind="missing-field")`。
2. 否则若 `_TOKEN_RE.search(element) is not None`（占位符不以整元素出现，如 `{partition}/tests`、`a{b}`、`{a}{b}`）：**fail-closed**，报 “placeholder must occupy a whole argv element”。理由：AC-014 明令不照抄“静默透传”；若此处放行，`{partition}/tests` 会作为字面量传给子进程（argv 进程会当成一个并不存在的路径），是静默错误。
3. 否则：字面量原样保留。

`render_argv` 返回值必定是 `list[str]`（与 `xkey_verify_cmd` 的 `_LIST_FIELDS` 契约一致，`config.py:61`），元素非空由 `validate_config` 保证（`config.py:99-107`）。

> `whole-token` 的歧义必须先钉死：AC-014 的“逐元素 whole-token”有两种读法——(a) 元素必须**恰好**是一个 token（上面的推荐）；(b) 元素内允许嵌入替换、只是不做 shell 分词。推荐 (a)，并把 (b) 的写法（`{partition}/tests`）定义为 fail-closed，否则判据不可机械判定。

---

## 2. Q2 token 集合定稿

### 2.1 现状逐字（证据）

| mode | 现有 token（toolchain） | 出处 |
|---|---|---|
| partition | `{parent}`、`{partition}`、`{<root name>}`（`partition.roots` 的每个键） | `mw_common.py:2897-2905` |
| dual / single | `{game}`、`{engine}`、`{uproject}` | `mw_common.py:2878-2891` |
| 未定义 | partition：fail-closed `missing-field`（`mw_common.py:2907-2913`）；dual/single：静默透传（无残留检查） | RQ-4 §1.4 |

- 根名字符集 `[A-Za-z0-9_-]+`（`_ROOTS_NAME_RE`，`mw_common.py:2413`），保留名 `parent/partition/game/engine/uproject`（`_ROOTS_RESERVED`，`:2412`），校验点 `mw_common.py:2567`。
- `{uproject}` 是**文件**不是目录（`discover_uproject`，`mw_common.py:2843`）；只能作 argv 占位，不能作 cwd。

### 2.2 推荐：verify argv 支持「该 mode 的根 token + `{control}`」

**逐字命令集（按 mode 分派，全部 fail-closed）：**

| mode | verify argv 已定义 | 其余（含 `{game}` 在 partition 下、`{python}`、任何 typo） |
|---|---|---|
| partition | `{control}`、`{parent}`、`{partition}`、`{<root name>}` | `missing-field`，错误文本照 `mw_common.py:2910-2913` 形状，defined 列表 = `{control}, {parent}, {partition}, {<roots sorted>}` |
| dual | `{control}`、`{game}`、`{engine}`、`{uproject}` | `{engine}` 且 `engine_root is None` ⇒ `missing-field`；其余未定义 ⇒ `missing-field` |
| single / legacy | `{control}`、`{game}`、`{uproject}`（此 mode 下 `game_root == control_root`，`mw_common.py:2671-2673`） | `{engine}` ⇒ `missing-field`（single 下 `engine_root` 恒为 None）；其余 ⇒ `missing-field` |

**是否新增 `{control}`：推荐新增，但仅限 verify argv（不进 toolchain token 集）。**

- 新增理由：verify cwd 缺省将改为 partition/game 根（§3），此时「协调/控制根」是另一个必须可引用的根（例如在 partition 根里跑 control 根的自测、或对照两个根）。没有 `{control}` 时用户无法在 argv 里表达控制根；而 `load_target_config` 的返回值里 `control_root` 一直存在（`mw_common.py:2670`、`:2745`），只是从未被 token 化。
- 仅限 verify argv 的理由：
  1. 若把 `{control}` 加进 `render_toolchain_command`，toolchain 行为就变了（partition 从「报错」变「可渲染」；dual/single 从「静默透传」变「展开」）——违反 Q1「不能变更 toolchain 行为」，且会牵连 TS 镜像 `shared/target-config.ts:756-812` 与 parity fixture 集。
  2. 没有任何 toolchain 命令依赖 `{control}`（grep `\{control\}` 只在测试的 profile 文本里出现，`test_partition_dispatch.py:90/91/107/108/123`；无 toolchain 用例），所以不加也没有损失。
  3. verify argv 渲染是 **Python 独有**（`xkey_verify_cmd` 只被 Python conductor 消费，`conductor.py:3460`；TS 侧只镜像配置 schema），因此 `render_argv` 不必纳入 TS parity，`{control}` 的“verify-only”不会制造跨语言契约分歧。

- **不提供 `{python}`**（spec §1.4；RQ-4 §6 已证绑定 `sys.executable` 会随 serve 启动方式漂移、与项目 venv 错配、`show` 无法报 origin）。partition 下 `{python}` 走未定义 ⇒ fail-closed；dual/single 下**不要**照抄 toolchain 的静默透传（AC-014 明令）。

- 与 `{control}` 相关的命名冲突：`control` 目前**不在** `_ROOTS_RESERVED`（`mw_common.py:2412`；TS 镜像 `target-config.ts:269`），所以 target.yml 可以声明 `roots.control`。一旦 `"control"` 成为保留 selector，就会和 `roots.control` 语义冲突。**推荐把 `control` 加入 `_ROOTS_RESERVED`（两侧同步）**，让词汇表无歧义；现网无项目声明 `roots.control`（E2 的 target.yml 无 `roots:` 段，FM 无 target.yml，见 §6.2），代价为零。替代方案是“保留 selector 优先、`roots.control` 被遮蔽”，但会在 `{control}` 占位上留下同样的歧义，不推荐。

### 2.3 消费者/写入者一致性（token 语义）

- 消费侧 `_xkey_run_verify` 现在是 `[str(part) for part in cfg...]`（`conductor.py:3460`）⇒ 改成 `mw_common.render_argv(list(cfg.get("xkey_verify_cmd") or []), target_config)`。
- ticket 里 `verification.command` 目前存**原始未展开** `list(cfg.get("xkey_verify_cmd", []))`（`conductor.py:2579`），而 evidence bundle 的 `verify_cmd` 存**展开后** argv（`conductor.py:3499` 一带 `verify = {..., "verify_cmd": verify_cmd, ...}`）。两者语义不一致，建议 ticket 只存展开值或显式区分 `command_template` / `command_rendered`（Q5）。

---

## 3. Q3 cwd 键设计

### 3.1 键名与值域

- **键名：`xkey_verify_cwd`**（与 `xkey_verify_cmd`/`xkey_verify_timeout_s` 同族前缀；spec AC-013/U-2 的用词）。
- **值域：枚举（mode 分派），不采用任意路径串。**

| selector | partition | dual | single / legacy |
|---|---|---|---|
| `""`（空串 = auto，缺省） | `partition_root` | `game_root`（推荐，见 §3.2） | `control_root` |
| `control` | `control_root` | `control_root` | `control_root` |
| `partition` | `partition_root` | 非法 | 非法 |
| `parent` | `parent_root` | 非法 | 非法 |
| `game` | 非法（partition 下 `game_root is None`） | `game_root` | `control_root`（`game_root == control_root`） |
| `engine` | 非法 | `engine_root`（未配置则非法） | 非法 |
| `<root name>`（`partition.roots` 的键） | `roots[name]` | 非法 | 非法 |
| 其它字符串 / 非字符串 / 绝对路径 | 非法 | 非法 | 非法 |

- “合法 selector” 列表 = 上表中该 mode 下**值非 None** 的 selector，按 `control, game, engine, partition, parent, <roots sorted>` 排序。非法值报错文本（复用 `_tc_fail("invalid-config", ...)`，**不新增 `_TARGET_KINDS`**，避免动 `_TARGET_KINDS` 的跨语言 parity 契约 `mw_common.py:2277-2284`）：
  `xkey_verify_cwd: unknown root selector '<v>' (valid: <sorted list>)`
- 非字符串：`xkey_verify_cwd: expected one of <valid list>, got <repr>`。
- 路径串作为替代方案（若设计评审坚持 AC-013 的“或同占位集合的路径串”）：定义 `"{"` 开头 ⇒ 必须 fullmatch 一个 token；否则必须 `os.path.isabs(value)`。**不推荐**，理由是“相对路径锚到哪个根”不可自洽（锚 control 还是 workspace？），而子目录需求可由 `partition.roots` 声明一个指向子目录的命名根来满足（roots 路径无“必须是仓库根”的限制，`_tc_parse_roots` 只做归一化，`mw_common.py:2554-2570`），完全覆盖“子目录 cwd”。

### 3.2 缺省解析：推荐复用 worker cwd 规则（单一真源）

`launcher._worker_cwd`（`launcher.py:894-906`）已定义“worker 实际在哪个根跑”：dual→`game_root`、partition→`partition_root`、single→`project_dir`。verify 的语义应与 worker 一致（这正是本 key 修 bug 的初衷），所以推荐：

```
mode == partition -> partition_root
mode == dual      -> game_root
mode == single    -> control_root
```

**与 AC-013 字面文本的冲突（必须由 design 定稿裁决）：** AC-013 写“缺省 = partition 根（partition 模式；其它模式 = control 根）”。对 single 而言 `control == game`，无差别；对 **dual**，AC-013 会让 verify 落在 `control_root`，而 worker cwd 是 `game_root`（`launcher.py:904`）——这正是本 key 要修的那类不一致，只是发生在 dual。推荐按上表（dual→game），并在 design.md 里显式记为对 AC-013 括注的修订。

- 现网零风险：E2 是 partition、FM 无 target.yml（legacy/single），**没有任何 dual 项目**（§6.2）；且 xkey 通道全关，dual 缺省变更不影响任何现网行为。
- 若评审要求严格照字面 AC-013（dual→control），则 dual 下 verify≠worker cwd 的缺陷保留，需另立 key——不推荐，但这是一个必答决策点。

### 3.3 可机械判定的真值表（fixture 形状）

Fixture 构造（直接照 `test_partition_dispatch.py:178-188` 的 `_write_partition_yml`：control/parent/shard/sdk 四个兄弟目录 + `_PARTITION_YML`）：

```
active: partition
partition:
  parent: '<tmp>/parent'
  partition: '<tmp>/shard'
  roots:
    sdk: '<tmp>/sdk'
  toolchain:
    build: 'make -C {partition} SDK={sdk}'
```

此时 `load_target_config(control)` ⇒ `control_root=<tmp>/control`、`partition_root=<tmp>/shard`、`parent_root=<tmp>/parent`、`roots.sdk=<tmp>/sdk`（形状同 `test_partition_dispatch.py:735-739` 的断言），且 **control≠partition≠parent**（`_tc_check_root_relation` 只要求 parent/partition 不同且不嵌套，`mw_common.py:2578-2589`；control 与二者无约束）。

| case | mode | `xkey_verify_cwd` | 期望解析 cwd | 期望错误 |
|---|---|---|---|---|
| T1 | partition | 缺省/`""` | `<tmp>/shard` | — |
| T2 | partition | `control` | `<tmp>/control` | — |
| T3 | partition | `partition` | `<tmp>/shard` | — |
| T4 | partition | `parent` | `<tmp>/parent` | — |
| T5 | partition | `sdk` | `<tmp>/sdk` | — |
| T6 | partition | `game` | — | `invalid-config`（unknown selector） |
| T7 | partition | `engine` | — | `invalid-config` |
| T8 | partition | `nope` / `H:\x` / `".."` | — | `invalid-config` |
| T9 | partition（E2 形状：control==partition） | 缺省 | control==partition 同一路径 | — |
| T10 | partition（E2 形状） | `parent` | parent 路径 | — |
| T11 | dual | 缺省 | `game_root` | — |
| T12 | dual | `control` | `control_root` | — |
| T13 | dual | `engine`（engine 已配置） | `engine_root` | — |
| T14 | dual | `engine`（engine 未配置） | — | `invalid-config` |
| T15 | dual | `partition`/`parent`/`sdk` | — | `invalid-config` |
| T16 | single / 无 target.yml | 缺省 | `control_root` | — |
| T17 | single | `game` | `control_root` | — |
| T18 | single | `partition`/`parent` | — | `invalid-config` |

- **E2 形状回归**：AC-013 要求“断言 verify cwd = `H:\git\E2Feature`、parent = `E:\UEMigrator`”。E2 实测 `control==partition==H:\git\E2Feature`、parent=`E:\UEMigrator`（RQ-4 §1.6），所以 T9/T10 用“control==partition 的 tmp 形状”等价覆盖；**不建议把 `H:\git\E2Feature`/`E:\UEMigrator` 字面量写进测试**（机器相关、CI 无此路径）。若要保留真实锚点，用 `pytest.mark.skipif(not pathlib.Path(r"H:\git\E2Feature").exists())` 包一条 live 检查。
- **现状会红的判据**：T1/T3/T5 断言 `cwd == partition_root`，而现状 `conductor.py:3459/3471` 恒为 `project_root` ⇒ control≠partition 时必红；T9/T10（E2 形状）现状恰好绿，这正是“只用 E2 不能证明修复”的原因（AC-013 已写明）。

### 3.4 校验层：写侧 vs 消费侧

- `autopilot/config.py::validate_config`（`config.py:86-127`）只能做与 mode 无关的形状校验：新增 `_STRING_FIELDS = ("xkey_verify_cwd",)`，允许任意字符串（含 `""`；`""` = auto）。**不能**在此做 selector 合法性校验（它拿不到 target.yml/mode）。
- mode 相关的合法性由 `resolve_verify_cwd(selector, target_config)`（放 `mw_common`，与 `render_argv` 同模块）在**写侧 CLI 与消费侧 conductor 共同调用**，保证“写进去就一定能被消费侧解析”（Q5）。
- 缺省值落地：`DEFAULT_CONFIG` 加 `"xkey_verify_cwd": ""`（`config.py:48-58` 之后新增一行），TS 镜像同步（`status-model.ts:79-102` 的 interface + `DEFAULT_CONFIG`、`:114-128` 的字段规则、`:198-250` 的 read/merge/save）。否则 TS console 侧读写会因 unknown field 直接 fail-closed（`status-model.ts:139-143`），两侧字节一致（AC-006）也红。**注意 AC-001 的“写入后文件含全部 12 键”要改成 13 键。**

---

## 4. Q4 S3 目标锚定同族处理：必须与 verify 一起改

### 4.1 同族锚点清单（全部以 control 根为基准，均为证据）

| 阶段 | 锚点 | 代码 |
|---|---|---|
| detect | `locate_frozen_block(root, file, test_id)`，`root = str(project_root)`（`conductor.py:2468`），函数内 `path = pathlib.Path(root) / file` | `conductor.py:2513`、`xkey.py:905-921` |
| detect | 零残留锚 `_xkey_file_sha256(project_root, file)`（`pathlib.Path(project_root) / rel`） | `conductor.py:2576`、`:3061-3070` |
| proposal 提示 | `target_abs = project_root / file_rel`（写给提案 worker 的“绝对路径”） | `conductor.py:2942` |
| apply | `xkey.apply_block_replace(root, ticket, ...)`，`root = str(project_root)`（`conductor.py:3386`），函数内 `path = pathlib.Path(root) / file_value` | `conductor.py:3408`、`xkey.py:1170/1199` |
| S3 存在性 | `target = pathlib.Path(project_root) / target_rel` | `conductor.py:3651` |
| verify | `xkey.run_verification(verify_cmd, cwd=root, ...)`，`root = str(project_root)` | `conductor.py:3459/3471` |

`file` 的来源：worker 的 handoff registration（L3 verdict 的 `output.md`/`report.md` 里的 `cross_key_test=`/`file=`/`path::test`）→ `xkey.collect_registrations`（`conductor.py:1317`）→ 归一化只做斜杠/行号清理（`xkey._normalize_rel`，`xkey.py:226-233`），**不做根解析**。而 worker 的 cwd 是 workspace 根：partition→partition（`launcher.py:906`），dual→game（`launcher.py:904`），spawn `:960`。repr 例：FM 语料 `cross_key_test=tests/test_hitl_channel.py::test_top_level_command_unchanged`（相对路径，见 `test_autopilot_xkey_registration.py:124`），测试 fixture 用 `tests/test_x.py`（`:100`）。

### 4.2 结论：**必须一起改**；只改一半的两种失败模式

- **只改 verify cwd（AC-013 的字面最小改动）**：detect 用 control 根定位 → `locate_frozen_block` 在 control 根找不到 partition 里的文件（返回 None）→ `frozen_block` 退化（`conductor.py:2513-2521`），或 apply 时 `target = control/file` 不存在 → `_xkey_stage_fail(..., "boundary_violation", "target file missing")`（`conductor.py:3652-3658`）。若 control 根恰好有同名相对路径（如两仓都有 `tests/test_x.py`），则会**改错文件**：control 的副本被改，verify 在 partition 跑 → 冻结块仍红 → `verify_failed` + 回滚（`_xkey_run_verify` 的 not-green 分支）。
- **只改 S3 锚定（不改 verify cwd）**：apply 正确改 partition 文件，但 verify 在 control 根跑该仓的测试 → `red_after` 不变 → not green → 回滚。同样永不闭环。

两种半修都让 partition 模式的 xkey 通道**完全不可用**（而不是“部分可用”），因此 AC-013 的“同族根锚定一并处理”是硬要求，不是优化项。

### 4.3 推荐实现：分离“协调根”与“工作区根”，锚点一次解析并持久化

- 引入单一真源 `mw_common.workspace_root(config, control_root) -> str`：dual→`game_root`、partition→`partition_root`、single/legacy→传入的 `control_root`。`launcher._worker_cwd`（`launcher.py:894-906`）改为委托（保留单根模式返回原始 `project_dir` 的现有行为，见 `test_partition_dispatch.py:215-224`），conductor 与 dispatch 同用。
- **工作区相对锚点**（5 处）改用 `workspace_root`：`locate_frozen_block`、`_xkey_file_sha256`、提案提示 `target_abs`、`apply_block_replace` 的 root、`conductor.py:3651` 的 `target`。
- **协调根保持 `project_root` 不变**：ledger/tickets/evidence/runs 全在 `<project_root>/.agenticdoc/_autopilot/xkey/`（xkey 模块 docstring `xkey.py:8-14` 明确 “root = 项目根”）；`ledger_append`（`xkey.py:544`）、`ticket_write`（`:790`）、`ticket_load`（`:812`）、`evidence_bundle_write`（`:1368`）、`_xkey_ticket_relpath`（`conductor.py:2396`）、timeline 全部继续用 control 根。**不要**把所有 `root` 全局换掉。
- **一次解析、持久化**：在 detect 时解析 workspace 根并把**解析结果**写进 ticket（如 `target_root: "partition"` 或解析后的绝对锚），后续 stage 只读它，避免 target.yml 在 detect→apply 之间被改动导致各 stage 锚点漂移。ticket 已存 `frozen_block`/`file`/`target_file_sha256`（`conductor.py:2561-2577`），加一个 root selector 字段成本很低（注意 tickets 是机器本地状态，存 selector 比存绝对路径更可移植）。
- **绝对路径仍可用**：`cross_key_test=`/`file=` 的值可能带盘符（`xkey._apply_cross_key_test` 只在 `::` 上切分，不剥离盘符，`xkey.py:319-330`），`pathlib.Path(root) / "H:\\..."` 在 Windows 上会整体替换成绝对路径 ⇒ 绝对形式天然锚对。但 `_PATH_TEST_RE`（`xkey.py:249-251`）的字符集不含 `:`，当只有裸 `path::test` 形状时盘符会被切掉、退化成根相对路径——这是**既有**边角，本 key 可只做“工作区根优先 + 找不到 fail-closed”，把该边角登记为已知限制。
- **找不到时不要回退 control 根**：回退会在“两仓同名文件”时静默改错文件。推荐工作区根单锚 + fail-closed（`boundary_violation`），并复用 `mw_common.describe_target_error`（`conductor.py:2954` 一带）把 target.yml 不可用时的错误文本统一。

### 4.4 性能与错误处理

- `mw_common.load_target_config` 每次调用都重读并 `yaml.safe_load` target.yml（`_tc_read_target_yml`，`mw_common.py:2331-2360`，无缓存）。xkey 通道只在 `cfg["xkey_repair"]` 为真时进入（`conductor.py:224`），且每 tick 只在有 ticket 时解析，属于常数级；如需进一步压，可加一个按 `(mtime_ns,size)` 键控的小缓存（照 `config.cached_load`，`config.py:150-170`）。**注意**：`_xkey_aggregate/_xkey_apply_stage` 的既有签名被测试直接调用（`test_autopilot_e2e.py:1477`、`test_autopilot_xkey_registration.py:722`），不要改必需参数；要传配置用可选 kwarg 或模块内惰性加载。
- `load_target_config` 抛 `TargetConfigError` 时的路由：verify 阶段 → `verify_failed`；detect/apply → `boundary_violation`；文本用 `describe_target_error`，与 dispatch 的 `target-config-unusable`（`dispatch.py:464-470`）口径一致。

---

## 5. Q5 写入侧与消费侧一致性

### 5.1 set 写前必须 dry-run（用与 conductor 相同的解析器）

`mw autopilot verify set --project <dir> --cwd <selector> -- <argv...>` 在 `save_config` 之前必须：
1. `target_config = mw_common.load_target_config(project_dir)`；`TargetConfigError` ⇒ `[mw autopilot verify set] Error: {describe_target_error}` + `return 1`，**不落盘**（对齐 `mw model set` 的 “existing ... is unusable ... fix or remove it before writing” 先例，`mw.py:3155-3162`）。
2. `mw_common.render_argv(argv, target_config)`（占位 dry-run）；失败 ⇒ 同上，不落盘。
3. `mw_common.resolve_verify_cwd(selector, target_config)`；失败 ⇒ 同上，不落盘。
4. 进 `mw_common` 锁临界区（`lock_path`/`acquire_lock`，AC-011）后 read-modify-write `{**default_config(), **existing, ...}`，再 `save_config`。

“写入侧与消费侧行为一致”的机械判据：同一份 (argv, selector, target.yml) 下，CLI 错误文本与 conductor 侧 `TargetConfigError` 文本**逐字相同**（都把渲染/解析放在 `mw_common` 单点，测试断言两侧字符串相等）。

**机器级层特例**：`--machine` 写入的 argv 不能按单个项目的 target.yml 校验（机器层跨项目共享，AC-007/U-1）。推荐机器层只做**形状校验**（元素非空、占位符形状合法：`_TOKEN_RE` 匹配或纯字面量），完整解析留到项目层/消费侧。否则一个机器的默认命令会被某个项目的 mode 误判为非法。

### 5.2 `show` 必须显示展开后的 argv 与 cwd（AC-004）

`mw autopilot verify show` 输出（形状照 `mw model show` 的 `[source]`/`[origin]` 惯例，`mw.py:3205-3230`、RQ-4 §3.3）：

```
config: <path> (missing — nothing configured)      # 照 mw.py:3205-3208
xkey_repair: true [origin]
xkey_verify_cmd: ['python','-m','pytest','{partition}'] [origin]
xkey_verify_cmd (resolved): ['python','-m','pytest','<partition_root>']
xkey_verify_timeout_s: 1800 [origin]
xkey_verify_cwd: '' (auto) [origin]
xkey_verify_cwd (resolved): <partition_root>
```

- `resolved` 行由 `render_argv` / `resolve_verify_cwd` 计算；解析失败时打印 `[unresolved] <error>` 并 `return 1`（可脚本 gate），但**仍然打印配置值**（读操作不因解析失败而丢信息）。
- AC-004 的价值就在这里：`xkey_verify_cmd` 存的是模板，真正会跑的是展开后 argv；“有效解析”必须包含展开（含 cwd 根）才有意义。
- `show` 只读：不写文件、不建目录（对齐 `mw model show` 与 config 的零足迹语义，`config.py:8-11`）。

### 5.3 ticket / evidence 里的命令记录

- `conductor.py:2579` 的 `ticket["verification"]["command"]` 存**未展开**模板；`conductor.py:3499` 的 `verify["verify_cmd"]` 存**展开后** argv。审计上两者需要能对应，建议：ticket 存模板 + 增加 `command_rendered`，或在 detect 时就用当前 `target_config` 渲染一次并只存结果。至少要在 design.md 里明确“哪个字段是权威执行值”。

---

## 6. Q6 回归风险面与“关闭时零行为变化”

### 6.1 入口门（为什么现网零影响）

所有 xkey 行为都在 `if cfg.get("xkey_repair", False):`（`conductor.py:224-234`）之内：`_xkey_aggregate` / `_xkey_proposal_stage` / `_xkey_apply_stage`，以及 `_l3_verdict` 的 registration 记录（`conductor.py:1592`）。`xkey_repair` 缺键 = `False`（`cfg.get` + `config.py` 不补默认键，RQ-4 §5.2；`config.py:54` 只是默认值，`load_config` 返回原 dict `config.py:126-133`）。所以 §3/§4 的改动（verify cwd、render_argv、S3 锚定）**只在显式打开通道的项目里才可达**。

### 6.2 现网证据：三项目通道全关（2026-09-26 实测复核）

| 项目 | config.json | xkey 键 | target.yml | 结论 |
|---|---|---|---|---|
| FM `E:\CLI_workspace\FeatureMigrator` | 存在（9 键） | **无** | **不存在** ⇒ legacy/single | `cfg.get("xkey_repair",False)`=False ⇒ 通道关 |
| E2 `H:\git\E2Feature` | 存在（8 键） | **无** | `active: partition`（parent=`E:\UEMigrator`、partition=`H:\git\E2Feature`） | 同上；partition 但通道关 |
| MW `H:\git\Multi-Workers` | **不存在**（`.agenticdoc/_autopilot/` 缺失） | — | 无 | 同上；零足迹（`config.py:8-11`） |

（本 RQ 已重读 FM/E2 的 config.json 与 target.yml 逐字确认，与 RQ-4 §5.1/§1.6 一致。）

### 6.3 受影响的既有测试

| 测试 | 为什么绿/红 | 说明 |
|---|---|---|
| `test_autopilot_e2e.py` 的 xkey 全链（VC-009/VC-010，`_xkey_project` 只写 goal+roadmap，无 target.yml） | 现有 fixture 是 **single（无 target.yml）** ⇒ workspace 根 = control 根 = `project_root`，改动后逐字不变 | 必须保持绿（“关闭/退化形状零变化”护栏） |
| `test_autopilot_xkey_registration.py`（`_xkey_aggregate`/`_xkey_apply_stage` 直调，`xkey_repair=True` 但无 target.yml；`:718`；VC-008 关通道 `:736-757`） | 同上，single 形状；且 detect 阶段若引入 `load_target_config` 在无 target.yml 时返回 single，不抛 | 不能在 `_xkey_aggregate` 里对外抛异常 |
| `test_partition_dispatch.py::TestWorkerCwdDispatch`（`:215-260`） | 若把 `_worker_cwd` 委托给新 `mw_common.workspace_root`，需保持 single 返回**原始** `project_dir`（该测试断言 `== control`，非 `.resolve()`） | 委托时保留返回值语义 |
| `test_common_target_config.py:92-103` parity | 只要 `render_toolchain_command` body 不动，此集不受影响 | Q1 的护栏 |
| `test_autopilot_config.py:91-103/118-135` | 新增键后 `cached_load == DEFAULT_CONFIG`（`:120`）仍成立（两侧同改）；roundtrip 逐字相等仍成立 | 形状变化但断言不自相矛盾 |

### 6.4 “关闭时零行为变化”的三条保证

1. **入口门**：新增解析（`render_argv`/`resolve_verify_cwd`/`workspace_root`/S3 重锚）全部只在 `xkey_repair` 为真且 ticket 落地时执行（`conductor.py:224`）；`xkey_repair:false` 时 `orchestrate`/`tick` 的调用序列与现网逐字相同。
2. **缺省退化**：非 partition 模式 verify cwd 缺省 = `control_root`（single/legacy 与现状逐字相同）。dual 缺省若采纳 `game_root`（§3.2），只影响 dual+xkey-on 的组合——现网不存在，且这正是 bug 修复语义。
3. **无 token 的 argv 逐字不变**：`render_argv` 对不含占位符的元素原样返回；只有含 `{...}` 的命令才进入新路径。现网 `xkey_verify_cmd` 全空（§6.2），零影响。

**回归测试建议（新增）：**
- `xkey_repair:false` + partition target.yml ⇒ tick 后 `_autopilot/xkey/` 不存在、timeline 无 `xkey-*`（扩展现有 `test_autopilot_xkey_registration.py:735-757` 的 fixture 加 target.yml）。
- `xkey_repair:true` + partition `control≠partition` + verify 命令把 cwd 写进文件 ⇒ 断言 cwd=partition 根（现状红，修复后绿）。
- `render_argv` 真值表（§2.2/§1.3）：no-token 逐字、`{control}`、嵌入占位 fail-closed、未定义 token fail-closed 且错误文本与 toolchain 同形。
- S3 同族：`control≠partition`，`file=tests/test_x.py` 只存在于 partition 根 ⇒ detect/apply/verify 全部落在 partition 根（现状红：detect 找不到文件或 apply `target file missing`）。
- 写侧 dry-run：非法占位/非法 selector 下 `set` 退出码 1 且文件字节不变。

---

## 7. AC-013 / AC-014 是否可机械判定 + 需补 fixture

### 7.1 AC-013

可机械判定的部分：`xkey_verify_cwd` 的解析真值表（§3.3）、E2 形状回归、`control≠partition≠parent` fixture、S3 目标锚定。

**必须先钉死的歧义（否则不可机械判定）：**
1. 值域“枚举 vs 路径串”（推荐枚举，§3.1）。
2. “其它模式 = control 根”对 **dual** 是否成立（推荐 dual→game，§3.2）。
3. “替换 conductor.py:3459/3471 的硬编码”是代码形状，行为判据应写成“verify 的 subprocess cwd == 解析后的根”，并且**同族锚点（§4.1 的 6 处）一并断言**，否则“只修一半”也能过 AC。
4. E2 字面路径（`H:\git\E2Feature`/`E:\UEMigrator`）不可移植：判据应锁定“形状等价”（control==partition 的 tmp fixture），live 路径用 skipif。

**FIX-13 式的 fixtures：**
- 复用 `test_partition_dispatch.py:178-188` 的 `_write_partition_yml`（control/parent/shard/sdk 四个兄弟目录）造 `control≠partition≠parent`；断言 `control_root/partition_root/parent_root/roots.sdk` 与 §3.3 真值表。
- E2 形状：每行只把 `partition` 改成 `control` 的同一路径（control==partition），断言缺省 cwd = 该路径、`parent` selector = parent 路径。
- S3 同族：partition 根放 `tests/test_x.py`（control 根放**同名但内容不同**的文件作为“改错文件”探针），断言 apply 改的是 partition 根那份、verify 在 partition 根跑。
- 双模式/单模式零变化回归：无 target.yml / v1 dual 下缺省 = control 根（现状逐字）。

### 7.2 AC-014

可机械判定的部分：token 集合、fail-closed、错误文本、list argv 逐元素、写/消费一致。

**必须先钉死的歧义：**
1. whole-token 定义（推荐“元素必须恰好是一个 token”，§1.3），以及嵌入占位（`{partition}/tests`）是 fail-closed 还是字面量。
2. 错误文本的 “original” 是**元素**还是整条 argv；推荐元素（并建议附 index），文本骨架照 `mw_common.py:2910-2913`：`verification command references undefined placeholder '{token}' (… defines: …): {element}`。
3. 是否新增 `{control}`（推荐是，verify-only，§2.2）；以及 `{python}` 明确不提供（spec §1.4、RQ-4 §6）。
4. 写侧与消费侧一致 = 同一函数 + 两侧错误字符串相等（§5.1）。

**fixtures：** 见 §6.4 的 `render_argv` 真值表 + 写侧 dry-run；另加一条“同一 (argv, target.yml) 下 CLI 文本 == conductor 文本”的断言。

---

## 8. 证据索引（file:line 速查）

- 渲染：`mw_common.py:2866`（`render_toolchain_command`）、`:2878-2891`（dual/single）、`:2894-2914`（partition + 错误文本 `:2910-2913`）、`:2415`（`_TOKEN_RE`）、`:2412-2413`（保留名/字符集）、`:2567`（roots 名校验）、`:2843`（`discover_uproject`）、`:2295`/`:2278-2284`（`_tc_fail`/`_TARGET_KINDS`）、`:2321`（`_tc_normalize_root`）、`:2578-2589`（root 关系）、`:2974`（profile 渲染）。
- verify 执行：`xkey.py:1272-1305`（`run_verification`，`shell=False`）、`:1289`（零展开）、`:1303`（cwd 原样）。
- cwd/锚点：`launcher.py:894-906`（`_worker_cwd`）、`:960`（spawn cwd）；`dispatch.py:336`（read-scope 锚 partition）；`conductor.py:2468`、`:2513`、`:2576`、`:2942`、`:3408`、`:3448-3472`（`_xkey_run_verify`）、`:3651`、`:3939`（project_root 解析）。
- 配置：`config.py:48-58`（DEFAULT_CONFIG）、`:61`（`_LIST_FIELDS`）、`:86-127`（validate/load）、`:136-170`（save/cache）；`status-model.ts:79-102`、`:114-128`、`:198-250`；TS `target-config.ts:756-812`、`:269`（ROOTS_RESERVED）。
- 测试形状：`test_partition_dispatch.py:172-188`（partition fixture）、`:215-260`（`_worker_cwd`）、`:604-660`（read-scope 分区锚定）、`:730-760`（doctor）；`test_autopilot_e2e.py:1200-1280`（xkey project，无 target.yml）、`:1240`（`xkey_repair=True`）；`test_autopilot_xkey_registration.py:95-105`（registration fixture）、`:707-757`（aggregate/关通道）；`test_common_target_config.py:92-103`（parity render）。
- CLI 先例：`mw.py:957-1009`（`_toolchain_run`，含 REMAINDER 坑注 `:983-985`）、`:3116-3126`（`_model_write`）、`:3155-3162`（unusable 拒写）、`:3205-3230`（`model show` 形状）。
