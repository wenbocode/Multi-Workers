# design RQ-D2 证据：机器级默认层的落点、格式与层级解析设计

- key：`mw-autopilot-verify-cli` · 日期：2026-09-26 · 类型：design 期只读调研
- 唯一写面：本文件。除本文件外未修改仓库任何文件（见文末 §12 复核）。
- 取数环境：Windows 10.0.26100 / PowerShell 5.1；工作树 `H:\git\Multi-Workers`；Python 3.14.3（MSC v.1944）；pytest 9.0.2；PyYAML 6.0.3（`python -c "import yaml; print(yaml.__version__)"` 实测）。
- 行号以 `read`（offset）与 `Select-String` 为准；`Get-Content` 行号在本仓会因行尾差异少算 0–4 行，勿用于对账（RQ-4 同约定）。
- 关联：spec AC-004/AC-007/AC-008/AC-013；spec 期 RQ-4 §3（RAG 骨架 + 7 坑）；RQ-2（读写契约、缓存 stale）；RQ-1（CLI 形状、`--` 坑）；design RQ-D1（缓存判据选型）、RQ-D3（cwd 根锚定）。

---

## 0. 结论速览（8 问 + 测试设计）

| # | 问题 | 结论 | 决定性依据 |
|---|---|---|---|
| 1 | YAML 实现与可用性 | `mw_common.py:53` 顶层 try-import **PyYAML**（`yaml.safe_load`），无依赖声明（本包无 `requirements.txt`/`pyproject.toml`/`setup.py`）；`mw bootstrap` 缺失时 `pip install pyyaml`（`mw.py:4027-4032`）；本机 pytest 环境**可用**（6.0.3）。**推荐机器层改 JSON** | `mw_common.py:51-55,224,427,459`；`mw.py:4027-4032`；仓库根无 Python 依赖声明文件（实测 `find`） |
| 2 | 层文件命名/路径/env | 推荐 `~/.agents/autopilot-defaults.json`；env `MW_AUTOPILOT_FILE`（整文件硬覆盖）/ `MW_AUTOPILOT_HOME`（HOME 覆盖）、后接 `HOME`→`USERPROFILE`，缺失即层空**不建目录、不回落** | 照抄 `mw_common.py:368-369,378-396`；`MW_AUTOPILOT_*` 命名空间全仓零占用（实测） |
| 3 | 覆盖域 | **只允许 xkey 三键 + 新增 cwd 键**（verify 部署面）；机器层不得覆盖 `enabled`/`paused` 及其余调度/限额字段 | 消费点表见 §3；`mw.py:161`、`conductor.py:2037`、TS `StatusConfigView`（`status-model.ts:990-995`）只有 4 个非 xkey 字段 |
| 4 | merge/origin 语义 | 逐字段 merge，project 覆盖 machine；**必须补默认值**（结果恒为 12 键，这是与 RAG 最大的不同）；project `null` = 显式回退到**内置默认**（origin `default`，不是回落 machine）；machine `null` = 空操作；`xkey_verify_cmd` 整体替换不拼接 | 对比 `_rag_merge_server` `mw_common.py:483-521`；`config.py:122-133,150-171`；`mw.py:161`/`conductor.py:3975` 直接下标 |
| 5 | 机器层错误行为 | **fail-soft 逐字段**：未知键 → 告警+忽略；已知键类型/范围错 → 丢弃该字段+告警，下层胜出；整份 JSON 坏 → 该层视为空+告警。**绝不整份作废、绝不拒绝启动**；project 层仍 fail-closed | RAG 的“整份作废”在 `mw_common.py:782-796`；autopilot 为多项目共享，一个 typo poison 全机 |
| 6 | 解析落点 | **新建 `autopilot/effective_config.py`**（`load_effective(project_root) -> values/origins/diagnostics`）；**不改** `config.py::load_config` 语义；merge **之前**先对 project 层做 fail-closed 校验 | 现有测试直接调 `load_config(tmp_path)` 且不隔离 env（`test_autopilot_config.py:28-38`）；RAG 靠 `MW_RAG_SERVERS_FILE` 隔离（`test_rag_config.py:46`） |
| 7 | 缓存 | 若 AC-003 修法是“每次读盘”→ 无缓存问题；**若保留任何缓存，键必须含机器层 `(path, mtime_ns, size)`（或内容指纹）**，且同尺寸改写 stale 修复必须同样覆盖机器层 | `config.py:74,150-171`；`save_config` 只 pop 项目路径 `config.py:146`；RQ-2 §3.3 实测同 mtime_ns stale |
| 8 | CLI 覆盖层 | **建议从 AC-004/AC-007 删除“cli 层”**：`set` 是写命令（值落盘 = origin `project`），真实消费者是独立 conductor 进程（`mw.py:169`），一次性 flag 到不了它。仓库零个读侧一次性覆盖 flag 先例 | `mw.py:4835-4839`（`--args` 仅写路径）；`mw_common.py:284-306`（`[source]` 值域来自 spawn 参数，非 CLI flag） |
| 9 | 测试设计 | 12 条真值表用例（§9），逐字段断言 value+origin+diagnostics；env 用 `mock.patch.dict(..., clear=True)` 隔离 `MW_AUTOPILOT_*`/`HOME`/`USERPROFILE` | 形状照 `test_rag_config.py:310-362`、`test_autopilot_config.py:91-145` |

---

## 1. 机器层改用 JSON 是否更省事（Q1）

### 1.1 `.yml` 用的是什么实现

- **PyYAML**。`mw_common.py:51-55`：
  ```python
  try:
      import yaml  # PyYAML: implicit dep for target.yml (mw-dual-workspace D-010)
  except ImportError:
      yaml = None
  ```
- 读取函数共 4 处，全部 `yaml.safe_load`：
  | 用途 | 函数/位置 | import 形态 |
  |---|---|---|
  | `target.yml` | `_tc_read_target_yml`（`mw_common.py:2332`）→ `yaml.safe_load` `:2347` | 模块级 `yaml`（`:53`） |
  | `.mw/dispatch.yml` | `load_dispatch_config`（`:210`）→ `:224-228` | 函数内 `import yaml`（`:224`） |
  | 机器层 `rag-servers.yml` | `_rag_layer_servers`（`:425`）→ `:427-431` | 函数内 `import yaml`（`:427`） |
  | `target.yml rag:` 段 | `_rag_target_section`（`:454`）→ `:459-463` | 函数内 `import yaml`（`:459`） |
- 没有 vendor、没有自研 YAML 子集用于配置层。**唯一的自研 YAML 子集**是 gate frontmatter（`autopilot/gates.py:31-38`，注释逐字：“hand-rolled: stdlib ships no yaml and third-party pyyaml is not allowed”），其理由是跨语言逐字节 parity（TS 镜像 `autopilot/monitor.ts:147` “D-004 line scan — no YAML dependency”），**不是**依赖不可用。
- TS 侧有 `yaml`：`packages/coding-agent/package.json:66` `"yaml": "2.9.0"`，用于 `rag/config.ts:29`（`import { parse } from "yaml"`）与 `shared/target-config.ts:36`。

### 1.2 `packages/multi-workers` 是否声明了该依赖 / pytest 是否可用

- **没有任何依赖声明**：`packages/multi-workers` 下无 `requirements*.txt`、`pyproject.toml`、`setup.py`、`setup.cfg`、`Pipfile`（全仓递归实测，排除 `node_modules`/`.tmp`）。PyYAML 是**隐式依赖**——仓库自己的注释就是这么写的（`mw_common.py:53` “PyYAML: implicit dep”）。
- 装配路径：`mw bootstrap` 在缺失时 `pip install pyyaml`（`mw.py:4027-4032`）；`mw doctor` 暴露 `yaml_available`（`mw_common.py:3093`，`_doctor_target`）；缺失时读 `target.yml` **fail-closed**（`_tc_read_target_yml`：`:2336-2342` 抛 `TargetConfigError(kind="invalid-config")`）。
- 历史决策：`mw-rag-integration` 的 design critique C-2 曾把 PyYAML 当违规（“Python stdlib only”），最终以“隐式依赖 + bootstrap 自动安装”定案（`.agenticdoc/mw-rag-integration/design.md:30`、`key-decision.md:47`）。即仓库既有的容忍度是**接受 PyYAML 作为隐式依赖**，但每次用到都要再解释一遍。
- pytest 环境：本机实测 `yaml 6.0.3`（PyYAML 已装），`test_rag_config.py` / `test_common_target_config.py` 等 YAML 测试因此能跑。

### 1.3 JSON vs YAML（机器层）

| 维度 | YAML（`~/.agents/autopilot.yml`） | JSON（`~/.agents/autopilot-defaults.json`） |
|---|---|---|
| Python 读取 | 需 PyYAML（隐式依赖；缺则要么 fail-closed 要么额外分支） | stdlib `json`（零依赖） |
| TS 读取 | 需 `import { parse } from "yaml"` 进 `status-model.ts`（当前该文件只 import `node:fs`/`node:path`/`IndexStore`，见 `status-model.ts:34-36`） | `JSON.parse`（零新增 import） |
| 与项目层关系 | 异格式，两层无法共用 `validate_config` / `save_config` 的字节契约 | **同格式**：可直接 `{**default_config(), **layer}` 后交给同一 `validate_config`；将来若加 `set --machine` 可复用同一序列化形状（`config.py:136-148`） |
| 注释/可读性 | 支持注释；人手写友好 | 无注释；但只有 3–4 个键，手写成本极低 |
| 错误类型 | `yaml.YAMLError` + 非 mapping 顶层多态 | `JSONDecodeError`，与项目层同一错误类 |
| 跨侧字节 | TS `yaml.stringify` 与 Py `yaml.safe_dump` 形状不可能逐字节一致 | 与 AC-006 的“跨侧字节一致”需求同源，可复用同一 `ensure_ascii=False` 决定 |
| 代价 | 新增 `yaml` 进 status-model 依赖面（若 TS 要读）；文档要教两套格式 | 无注释；需文档说明“机器层是 JSON 不是 YAML” |

**推荐：JSON**。理由：(a) 机器层只有 3–4 个 xkey 键，YAML 的可读性优势几乎为零；(b) 与项目层同格式后，“逐字段 merge + origin”只写一套校验/序列化，直接站在 `save_config`/`validate_config` 的既有字节契约上（AC-006 才有意义）；(c) 避免把 PyYAML 隐式依赖从“target.yml 可选”升级成“autopilot 配置层必需”，也避免 TS 侧新增 yaml import（进而避免改动 `dist/.../status-model.js` 的依赖面，AC-009 的 kind 集合判据最省事）；(d) RAG 用 `.yml` 是因为它先天是 YAML 生态（服务器表分节、注释多），autopilot 不是。若 PM 坚持 YAML，则必须同时定稿：TS 侧是否读机器层（若读，`status-model.ts` 要加 `yaml` + 两侧 merge 镜像；若不读，则 `/autopilot status` 会看到与 conductor 不同的 `enabled`，语义分裂）。

---

## 2. 层文件命名、路径与测试隔离 env（Q2）

### 2.1 RAG 的形状（照抄母版）

- 项目层：`rag_servers_path(root)` → `<root>/.mw/rag-servers.yml`（`mw_common.py:373-375`）。
- 机器层：`machine_rag_servers_path(env=None)`（`mw_common.py:378-396`）：
  1. `MW_RAG_SERVERS_FILE`（`mw_common.py:368`）非空 → `Path(override)`，**存在才返回，缺失返回 None 且不回落 HOME**（`:379-384`）；
  2. 否则 `MW_RAG_SERVERS_HOME`（`:369`）→ `HOME` → `USERPROFILE`（`:385-395`），拼 `<home>/.agents/rag-servers.yml`，存在才返回；
  3. 全不存在 → `None`（层空，**从不建目录**）。
- 写入侧镜像：`mw.py:_rag_machine_write_path`（`mw.py:2017-2035`），`MW_RAG_SERVERS_HOME` 优先于 HOME，保证测试钩子不会碰真实 HOME（`mw.py:2022-2026`）。

### 2.2 候选命名

| 候选 | 优点 | 缺点 |
|---|---|---|
| `~/.agents/autopilot.yml` | 与 RAG 完全同构（同目录、同后缀） | YAML 之弊（§1.3）；名字太宽——“autopilot 的配置”会与项目层 `<root>/.agenticdoc/_autopilot/config.json` 混淆，等于承诺“机器层=整套 autopilot 配置”，而本 key 实际只允许 xkey 键 |
| `~/.agents/autopilot-defaults.json` | 名字显式声明**它是默认层**；受限域（xkey 键）与名字自洽；JSON 与项目层同格式；将来扩到别的默认字段不会改名 | 与 RAG 不同后缀（需文档解释“RAG 是 yml、autopilot 是 json”） |
| `~/.agents/autopilot.json` | 短 | 同上“太宽”的问题更严重；且未表达“默认层”，将来出现机器级运行态会无文件可用 |
| `~/.agents/xkey-verify.json` | 作用域最窄，绝不与未来字段冲突 | 与 spec AC-007 措辞“机器级默认层（`$HOME/.agents/...`，与 RAG 同构）”偏离；将来若要机器层 `xkey_repair` 之外的默认键就要重命名 |

**推荐：`<home>/.agents/autopilot-defaults.json`**。理由：(a) “defaults”把语义钉死在“下层默认”，与 §3 的受限覆盖域一致；(b) JSON 与项目层同格式（§1.3）；(c) 与 RAG 的目录/优先级形状同构，只有后缀不同，文档写一行就能解释。若 PM 最终选择覆盖全部 12 键（即机器层真的是“整套默认”），这个名字依然成立。

### 2.3 env 命名与测试隔离

- 命名空间 `MW_AUTOPILOT_*` 全仓零占用（实测 grep `MW_AUTOPILOT` 于 `packages/**/*.py`、`*.ts` 零命中），可安全使用。
- 推荐（照 `MW_RAG_SERVERS_{FILE,HOME}` 形状，RQ-4 §3.5 骨架的 `MW_<X>_FILE`/`MW_<X>_HOME`）：
  - `MW_AUTOPILOT_FILE`：整文件硬覆盖；**设定但缺失 = 层空且不回落 HOME**（这是测试 hermetic 的关键，照 `mw_common.py:379-384`）。
  - `MW_AUTOPILOT_HOME`：家目录覆盖（拼 `/.agents/autopilot-defaults.json`），测试隔离优先于真实 `HOME`；Windows 必须保留 `USERPROFILE` 兜底（`mw_common.py:391`）。
- 常量落点：与 `RAG_ENV_FILE`/`RAG_ENV_HOME`（`mw_common.py:368-369`）并列；basename 常量 `AUTOPILOT_DEFAULTS_BASENAME = "autopilot-defaults.json"`。
- 测试形状（可照抄）：`test_rag_config.py:46`（`mock.patch.dict(os.environ, {"MW_RAG_SERVERS_FILE": ...})`）、`:310-362`（四级路径真值表 + 缺失不回落 + HOME/USERPROFILE 兜底）；`test_rag_init.py:64-86`（`clear=True` hermetic env）。
- **本 key 没有机器层写者**（AC 列表只有 `set/clear/show --project`；AC-007 只要求“层 + 优先级真值表”）。因此机器层是“用户手改”的文件；若将来加 `set --machine`，必须镜像 `mw.py:2017-2035` 并纳入 AC-011 的锁（见 design RQ-D4）。

---

## 3. 机器层覆盖域（Q3）

### 3.1 12 个字段的真实消费点（非测试代码）

| 字段 | 消费点（file:line） | 性质 |
|---|---|---|
| `enabled` | `mw.py:161`（serve 监督循环 `cached_load(...)["enabled"]`，直接下标）；`conductor.py:2037`（tick 门） | **运行态开关** |
| `paused` | `conductor.py:2037` | **运行态开关** |
| `poll_interval_sec` | `conductor.py:3975`（主循环间隔，直接下标） | 调度 |
| `max_parallel_keys` | `conductor.py:266` | 并发限额 |
| `round_budget` | `conductor.py:941,1063,1570,1712` | 调度/预算 |
| `worker_timeout_min` | **无生产消费者**（非测试 `.py` 与 `packages/coding-agent/src` 实测只命中 `config.py:50`/`status-model.ts:73,96,122,205,219,243` 的声明与校验；真实 worker 超时走 `PI_WORKER_TIMEOUT_MS`，RQ-4 §4.2） | 校验保留字段（dead config） |
| `l2_read_file_cap` | `dispatch.py:204-241`（`_read_scope_caps`，用 `load_config` + `config_path().exists()`） | worker 读取限额 |
| `l2_read_byte_cap` | 同上 | worker 读取限额 |
| `advance_stall_ticks` | `conductor.py:774` | 停滞判定 |
| `xkey_repair` | `conductor.py:224,309,1592,2754`（通道总闸） | **verify 部署面** |
| `xkey_verify_cmd` | `conductor.py:2579`（ticket 快照）、`:3460`（执行） | **verify 部署面** |
| `xkey_verify_timeout_s` | `conductor.py:2580`、`:3461` | **verify 部署面** |

### 3.2 推荐：机器层只覆盖 verify 部署面

**允许**：`xkey_repair`、`xkey_verify_cmd`、`xkey_verify_timeout_s`，以及 AC-013 新增的 `xkey_verify_cwd`（若最终加进 `DEFAULT_CONFIG`）。

**禁止（机器层出现即告警并忽略该字段，见 §5）**：`enabled`、`paused`、`poll_interval_sec`、`max_parallel_keys`、`round_budget`、`worker_timeout_min`、`l2_read_file_cap`、`l2_read_byte_cap`、`advance_stall_ticks`。

理由（每条都有代码后果，不是口味）：

1. **`enabled` 机器级覆盖 = 全机所有项目自动开 autopilot**：`mw serve` 的监督循环每步读 `enabled`（`mw.py:161`）并在为真时 spawn conductor（`mw.py:166-176`）。机器层写 `enabled: true` 会让每台机器上每个被 `mw serve` 打开的项目都起 conductor——这是不可接受的副作用（也是 spec §1.4“不新建常驻调度器”的反面）。
2. **`paused` 机器级覆盖是“隐形全局暂停”**：`conductor.py:2037` 每 tick 判 `cfg["enabled"] or cfg["paused"]`；机器层 `paused: true` 会让所有项目的 conductor 静默空转，且 `mw doctor` 的 conductor section 是 informational（`mw.py:514` 注释）——难以定位。
3. **调度/限额字段机器级覆盖改变全局行为**（`round_budget` 决定工单预算、`max_parallel_keys` 决定并发、`l2_*` 决定 reviewer 能读多少）：机器层默认最适合放“部署命令”，不适合放“调度策略”；这些字段的正确层级就是项目层（每个项目测试规模不同）。
4. **与 TS 的同步面**：TS `StatusConfigView`（`status-model.ts:990-995`）只暴露 `enabled`/`poll_interval_sec`/`round_budget`/`max_parallel_keys`——**不含任何 xkey 键**。把机器层限制在 xkey 键后，TS 侧**完全不必**读机器层、不必加 `yaml`/新 merge 代码、`/autopilot status` 不会与 conductor 语义分裂。反过来，若机器层可覆盖 `enabled`，TS 侧就必须读机器层，否则窗口看到的 `enabled` 与 conductor 实际行为不一致（正是 AC-006 想避免的“两侧漂移”）。
5. **`worker_timeout_min` 是 dead config**（§3.1），把它放进机器层等于把死字段推广到全机。

若 PM 决定机器层覆盖全部 12 键，则 AC-007 必须追加：(a) TS 侧读机器层（`status-model.ts` 的 read 路径 + `yaml`/JSON 解析）；(b) origin 在 TS 也可见；(c) 机器层 `enabled` 的后果写成显式契约（而不是默认行为）。

---

## 4. merge 与 origin 的精确语义（Q4）

### 4.1 RAG 的 `_rag_merge_server`（`mw_common.py:483-521`）逐条拆解

| RAG 规则 | 位置 | autopilot 能否照抄 |
|---|---|---|
| 字段级覆盖：对 `_RAG_SERVER_FIELDS` 逐字段判 `in_machine`/`in_project` | `:486-492` | **能**（但字段表换成 12 键 / 受限子集，且无嵌套块） |
| project 侧 `null` = 显式删除该字段（`merged[field]=None`，origin=`project`） | `:493-496` | **不能照抄**（见 §4.3：autopilot 结果必须完整，且“删除”要产出 origin `default`） |
| machine 侧 `null` = 不删除任何东西 | `:497-498` | **能**（推荐保留：机器层 null 空操作） |
| 嵌套对象（`mcp`/`skill`/`capabilities`）逐 key 合并、project 覆盖 | `:499-514` | **不适用**（autopilot 无嵌套键） |
| 标量/数组：project 覆盖 machine；数组整体替换 | `:515-520` | **能**（`xkey_verify_cmd` 必须**整体替换**，绝不能拼接——与 `sources` 同理） |
| origin 逐被求值字段路径记录 `machine`/`project`，挂到 `entry["origin"]` | `:486,505,512,517,520` + `_rag_finalize_server` `:596+` | **能借形状，不能借值域**（autopilot 需第四个 `default`） |
| 单层解析/校验错误 → `load_rag_config` 返回 `({}, error)`，**整份作废** | `_rag_layer_servers` `:436-440`、`_rag_validate_layer_entry` `:404-409`、`load_rag_config` `:785,791,794` | **必须不同**（见 §5） |

### 4.2 RAG 与 autopilot 的结构性差异（决定不能整段照抄）

1. **RAG 是“条目集合”merge，autopilot 是“字段集合”merge**：RAG 按 server 名做并集（`load_rag_config:797` `sorted(set(machine_servers) | set(project_servers))`），再对每个同名 server 调 `_rag_merge_server`。autopilot 没有子实体，直接对 12 个键做同样的循环即可；`_rag_merge_server` 里 `name`/`_RAG_NESTED_FIELDS` 的逻辑整段删除。
2. **RAG 会构造完整 merged 结构**（`_rag_finalize_*` 补默认、`load_rag_config:807-817` 组装），而 **autopilot 的 `load_config` 返回原始 dict**（`config.py:133`），`cached_load` 缓存原始 dict（`config.py:168-170`）。消费侧有直接下标：`mw.py:161` `cached_load(...)["enabled"]`、`conductor.py:2036` `cfg["enabled"] or cfg["paused"]`、`:3975` `["poll_interval_sec"]`。RQ-4 §3.6 坑 1 说的就是这条。**因此 autopilot 的有效配置必须是“以 `default_config()` 为基底、逐层覆盖”的 12 键完整 dict**，merge 只能“覆盖”，不能让键消失。
3. **origin 的第四个值 `default` 必须有产生点**：RAG 里“两层都没有”= 字段不出现在 `origin`，`mw.py:_rag_format_origins` 用 `str(origin.get(path, "-"))` 打 `-`（`mw.py:1210-1230`）。spec AC-004 明确要求 `origin ∈ {cli, project, machine, default}`（若按 §8 删除 cli，则为 `{project, machine, default}`），所以“内置默认”必须显式标注，不能是 `-`。这意味着 autopilot 的 resolver 必须对**全部 12 键**记录 origin（缺省或删除后的字段 → `default`）。

### 4.3 定稿的 merge 语义（建议）

输入：`defaults = default_config()`；`machine`（已按 §5 清洗）；`project`（已先过 `validate_config`，fail-closed）。

```
effective: dict = deepcopy(defaults)
origins: dict[str, str] = {field: "default" for field in defaults}
for field in DEFAULT_CONFIG:                      # 固定顺序 = DEFAULT_CONFIG 顺序
    in_p = field in project
    in_m = field in machine
    if in_p and project[field] is not None:
        effective[field] = project[field]; origins[field] = "project"; continue
    if in_p and project[field] is None:
        # 显式 null：覆盖并“关掉”下层，回到内置默认（不回落到 machine）
        origins[field] = "default"; continue       # effective 已是默认值
    if in_m and machine[field] is not None:
        effective[field] = machine[field]; origins[field] = "machine"; continue
    # else: 保持默认，origin 已是 default（machine null 视为空操作，不记录 origin）
```

逐条对照与理由：

- **project 非 null → 最高**（对齐 RAG `:515-520`，也对齐 spec 优先级 `project > machine`）。
- **project `null` → origin `default`（不是回落 machine）**。这是与 RAG 语义最容易踩错的一处：RAG 里 project `null` 是“删除该字段”，最终由 finalize 补默认；若 autopilot 让 project `null` 回落 machine，那 `null` 就变成“无操作”，人类无法用 project 文件关掉机器层。**测试判据**：machine `xkey_verify_timeout_s: 600` + project `xkey_verify_timeout_s: null` → 有效值 `1800`、origin `default`。
- **machine `null` → 空操作**（对齐 RAG `:497-498`）：不覆盖 project、不制造默认。**测试判据**：machine `{xkey_verify_cmd: null}` + project absent → `[]`、origin `default`。
- **`xkey_verify_cmd` 整体替换**（对齐 RAG `sources` `:516-520`）：project `["a"]` + machine `["b","c"]` → `["a"]`，绝不拼接。
- **结果恒为 12 键、顺序 = `DEFAULT_CONFIG` 顺序**（与 TS `saveConfig` 的 `ordered` 形状一致，`status-model.ts:234-250`），因为 `show --json` 与跨侧字节断言都吃这个。
- **`cli` origin**：若按 §8 删除，则不产生；若保留，只在 `show --cmd` 预览路径临时置顶，绝不落盘。

---

## 5. 机器层未知字段/类型错误的行为（Q5）

### 5.1 RAG 的现状（要规避的 failure mode）

- `_rag_layer_servers`（`mw_common.py:425-450`）：顶层未知键 → `return {}, f"{label}: unknown key(s) ... (valid: servers)"`（`:436-440`）；server 条目未知键 → `_rag_validate_layer_entry` `:404-409`。
- `load_rag_config`（`:772-818`）：machine 层错误 → `return {}, error`（`:785`）；project 层错误 → `:791`；`target.yml rag:` 段错误 → `:794`。
- 即：**任一层的任何一个错误 → 整份 RAG 配置作废**（project 层正确也一起丢）。消费侧只是打印/降级（`mw rag list` exit 1 `mw.py:1234-1237`；doctor informational `mw.py:517`）。

### 5.2 autopilot 的风险不对称

机器层文件被**同机所有项目**共享。若照抄“整份作废”：(a) 机器层一个 typo（如 `xkey_verify_cmds`）会让**所有**项目的 verify 通道消失；(b) 更糟，若该错误被当作 `ConfigError` 抛出，`conductor.tick` 的 broad except 会把每 tick 变成 `"error"`（RQ-2 §6 实测：未知键 → tick `"error"` + timeline `tick error: ConfigError(...)`），autopilot 全机停摆——而问题文件根本不在项目里，用户无从查起。

### 5.3 推荐：机器层 fail-soft 逐字段；project 层保持 fail-closed

| 机器层情况 | 行为 | 诊断面 |
|---|---|---|
| 文件缺失 | 层空（`{}`），零足迹，**不建目录** | 无（正常） |
| JSON 解析失败 / 顶层非 object | 整层视为 `{}` | diagnostics 记 `<path>: <err>` |
| 未知键 | 忽略该键，其余字段照常 merge | diagnostics 记 `unknown key 'x'` |
| 已知键类型/范围错（含 `null` 之外的标量/列表形状错） | 丢弃该字段（不 apply，下层/默认胜出） | diagnostics 记 `field: <原因>` |
| 本 key 覆盖域之外的已知键（§3：如机器层写 `enabled`） | 丢弃该字段（同“不支持”） | diagnostics 记 `not machine-overridable` |

- **project 层不变**：`load_config` 的 `ConfigError`（`config.py:86-133`）仍是 fail-closed；机器层不得“救活”非法 project 配置（§6 的“先校验 project 再 merge”）。
- **不拒绝启动**：autopilot 配置是链路正确性的载体，但机器层是共享便利层；RAG 的既有契约是“永不阻塞派发”（`mw_common.py:775-777` docstring），autopilot 更不应因为一个共享文件坏掉而让全机 `serve` 拒绝运行。
- **可测判据（每条都能写成断言）**：
  1. machine `{"xkey_verify_cmds": ["pytest"]}` + project 合法 → 有效配置 == project/defaults；`diagnostics` 非空且含 `xkey_verify_cmds`；`conductor.tick()` 返回 `"ok"`（不是 `"error"`）。
  2. machine `{"xkey_verify_timeout_s": "600"}` + project `{"xkey_verify_timeout_s": 90}` → 有效值 `90`、origin `project`；diagnostics 含该字段。
  3. machine 文件写入 `"{not json"` → 有效配置 == project/defaults；tick `"ok"`。
  4. machine `{"enabled": true}`（若 §3 采纳受限域）+ 项目无 `_autopilot/config.json` → 有效 `enabled` 仍为 `false`；diagnostics 含 `enabled not machine-overridable`。
  5. 同样 fixture 下 `mw doctor` 文本/JSON 含机器层路径与字段名（诊断面落点见 §6）。
  6. project 文件含未知键 + machine 含合法值 → 仍抛 `ConfigError`（机器层不得掩盖）。

---

## 6. 解析落点：新模块 vs 改 `load_config`（Q6）

### 6.1 调用点清单（谁必须换）

| 调用 | 位置 | 现状 | 换用有效解析的理由 |
|---|---|---|---|
| serve 监督循环 `enabled` | `mw.py:161` | `cached_load(...)["enabled"]` 直接下标 | 需完整 12 键 + 机器层（虽然 §3 后 `enabled` 只可能来自 project/default） |
| conductor `orchestrate` cfg | `conductor.py:169` | `cached_load` | verify 键在这里被读 |
| conductor advance 快照 | `conductor.py:1874` | `cached_load` | 同上 |
| conductor `tick` 门 | `conductor.py:2036-2037` | `cached_load` | 同上 |
| conductor 主循环 interval | `conductor.py:3975` | `cached_load(...)["poll_interval_sec"]` 直接下标 | 需完整键 |
| dispatch read-cap | `dispatch.py:227-241` | `config_path().exists()` + `load_config` | 若机器层可覆盖 `l2_*`（不推荐）则要换；否则**也要留意** `config_path().exists()` 为假时机器层被无视 |
| 新 CLI `show`/doctor | 新增 | — | 唯一需要 origin 的消费者 |

### 6.2 两个方案

**方案 A：改 `config.py::load_config`/`cached_load` 使其返回 merge 结果。**
- 优点：调用点零改动。
- 缺点（决定性）：`load_config` 目前是“项目文件原样读”的纯函数，被**大量既有测试**直接调用且**不做 env 隔离**（`test_autopilot_config.py:28-38,91-103,105-110,113-145`）。一旦它开始读 `$HOME/.agents/autopilot-defaults.json`，这些测试会变成“依赖开发者本机 HOME”的非确定性测试。RAG 之所以没这个问题，是因为所有 RAG 测试都 patch `MW_RAG_SERVERS_FILE`（`test_rag_config.py:46`），而 autopilot 的既有测试没有。其次 `dispatch._read_scope_caps`（`dispatch.py:227-241`）刻意用 `load_config` 并自己 catch 异常——语义会被悄悄改变。

**方案 B（推荐）：新建 `autopilot/effective_config.py`。**
- 保持 `config.py` 现状：`config_path` / `load_config`（原始 + fail-closed）/ `save_config`（只写项目文件）/ `cached_load`（项目文件缓存）；新增：
  - `machine_config_path(env=None)`（照 `mw_common.py:378-396` 的四级顺序）
  - `load_effective(project_root) -> EffectiveConfig`，其中 `EffectiveConfig = {values: dict(12 键完整), origins: dict[str,str], diagnostics: list[str], layers: {project: path|None, machine: path|None}}`
  - `cached_effective(project_root)`（可选：热路径缓存，见 §7）
- 消费点改为 `effective_config.cached_effective(...)`：`mw.py:161`、`conductor.py:169,1874,2036,3975`；`show`/doctor 直接调 `load_effective` 拿 origins/diagnostics。
- `dispatch._read_scope_caps` 保持 `load_config`，但把开头的 `config_path().exists()`（`dispatch.py:227`）放宽为“项目文件或机器层任一存在”，否则机器层提供的默认在此消费点不可见（**若 §3 采纳受限域则此点无实际差异，但代码语义要一致**）。
- **顺序**：先读 project 层并 `validate_config`（fail-closed，抛 `ConfigError`），再读 machine 层（fail-soft，§5），最后 merge（§4.3）。理由：若先 merge 再校验，机器层的合法值会掩盖 project 层的非法值（例：project `{"poll_interval_sec": "4"}` + machine `{"poll_interval_sec": 4}` → merge 后合法，非法 project 被“救活”）。这正是本 RQ 要钉死的一条。
- **命名**：`autopilot/effective_config.py`（与 `config.py` 并列），避免叫 `config.py` 的新函数——`load_config` 的语义（项目文件原样）本身是既有契约，RQ-2 已把它写成测试判据。

---

## 7. 缓存（Q7）

### 7.1 现状

- `_CACHE: dict[str, tuple[int, int, dict] | None]`（`config.py:74`），键 = `str(path.resolve())`（项目 `config.json` 的解析路径，`config.py:158`），值 = `(st_mtime_ns, st_size, cfg)`（`:165-170`）。
- `save_config` 只 `_CACHE.pop(str(path.resolve()), None)`（`config.py:146`）——**只清本项目路径**，且只作用于写进程自己。
- `invalidate_cache()` 全清（`:173-175`）。

### 7.2 分情况回答

- **若 RQ-D1/AC-003 的修法是“取消 stat 短路、每 tick 读盘”**（RQ-2 §3.4 方案 a；`mw.py:161` 是 1s 复查、conductor 是 `poll_interval_sec` 秒级，两个 <1KB 文件）：**这里不再有缓存问题**——有效解析器每 tick 读 project + machine 两个文件即可。注意此时 `cached_load` 这个名字/函数应退化为“每次读盘”，或直接让有效解析器不再走 `cached_load`；`save_config` 的 `_CACHE.pop` 变成无害冗余。`dispatch._read_scope_caps` 原本就是每调用读一次（`load_config`，无缓存），语义一致。
- **若保留任何缓存**：**机器层 stat 必须进缓存键**（RQ-4 §3.6 坑 3 原文）。具体：
  - 不能沿用“键 = 项目路径”。机器层只有一个（`~/.agents/autopilot-defaults.json`，与项目无关），机器层被手改时**没有任何进程会 pop 项目键**（本 key 也没有机器层写者），所以缓存必须按 `(project_path, project_stat, machine_path, machine_stat)` 或等价复合键失效。
  - 而且 RQ-2 §3.3 已证 `(mtime_ns, size)` 本身不完备：同尺寸改写（机器层典型如 `xkey_verify_timeout_s: 1800` → `1200`，字节长度不变；`{"xkey_repair": true}` ↔ `{"xkey_repair": false}` 会变长，但数字改一位不变长）落在同一 `mtime_ns` 刻度时被静默忽略。**AC-003 选定的判据必须同样覆盖机器层**——否则“机器层改了不生效”就是一个跨项目、难复现的静默 bug。
  - 若 AC-003 选定“内容指纹（sha256/首块哈希）”，机器层用同一指纹函数；若选定“写侧推 mtime”，机器层**没有写者**，推 mtime 无从执行 → 这条方案对机器层不可用，只能读侧修。
- **结论**：机器层把 AC-003 的选型逼向“读侧修”（每次读盘或内容指纹）。若 RQ-D1 给出的是“读侧 + 缓存含 stat”的混合方案，机器层必须显式纳入缓存键并在 AC-007 里断言“机器层单独改动 ≤1 tick 生效”。

---

## 8. CLI 覆盖层（Q8）

### 8.1 事实

- 仓库**没有**任何读侧“一次性覆盖”flag（实测 `add_argument("--cmd/--override/--model/--server` 只命中 `mw.py:4857` 的 `rag init --server`，是写模板参数）。`target`/`partition`/`model`/`rag` 的 `show`/`list` 都只打印**已落盘**的内容。
- `mw model show` 的 `[source]` 值域来自 `mw_common.resolve_dispatch_model`（`mw_common.py:284-306`）：`task`（spawn 时 task.md 的 `model:`）/`config:<role>`/`window`/`default`——`cli` 这个参数（`cli="pi"`）是**路由维度**（哪家的模型兼容），不是“命令行覆盖层”。
- `--args`（`mw.py:4835-4839`，消费 `:983-986`）是写/执行路径的参数拼接，且 `mw.py:983-985` 自己记着 REMAINDER 的坑；它不构成“读侧层级”。
- 真实消费者是独立进程：conductor 由 `mw.py:169` `subprocess.Popen([sys.executable, _CONDUCTOR_PY, ...])` spawn，只读文件。任何 `show` 时的一次性 flag 都到不了它。

### 8.2 建议

**删除 AC-004/AC-007 里的 `cli` 层**（origin 值域收敛为 `{project, machine, default}`，优先级 `project > machine > default`）。理由：

1. **没有部署语义**：本 key 的交付物是“把 verify 命令部署出去”（spec §1.1(2)），`set` 是写命令，其值落进项目文件 → origin 就是 `project`。一个只影响 `show` 打印、不影响 conductor 的“层”，与 spec 的优先级表并列会误导读者（P-015：env/CLI 只作覆盖，主载体必须是持久化文件——而这里的“cli 层”连持久化都没有）。
2. **没有先例与需求**：仓库 20 处 `--project` 命令没有一个读侧覆盖 flag；RAG 的 origin 值域只有 `{machine, project}`（`mw.py:1210-1230`）；`mw model show` 的 `[source]` 也不是 CLI 层。为“4 层真值表好看”造一个无用途的层，违反 AC 必须可机械判定的原则。
3. **可测性**：删掉后 AC-007 的真值表退化成 2 层覆盖 + 默认，测试用例更少且每条都有落点。

**若 PM 坚持保留**，唯一自洽的形状是把它降级为**只读预览**并单独定 AC：
`mw autopilot verify show --cmd -- python -m pytest -q`（或 `--cmd`）→ 在 `show` 输出里把给定 argv 当作最顶层（origin `cli`）打印有效值与 cwd，**保证不写任何文件、不影响 conductor**；AC 断言：(a) 该调用后项目/机器层文件字节不变（照 `test_mw_target.py:37-70` 的全树快照）；(b) `show` 无 `--cmd` 时绝不出现 `cli` origin；(c) 文本含 `[cli]` 行。上述 (a)(b)(c) 都能机械判定，但它与“优先级 `cli > project > machine > default`”是两回事——优先级表应只描述 `set/clear` 落盘后的解析。

---

## 9. 测试设计（真值表 + 与 AC-007 的对应）

### 9.1 隔离与形状

- env 隔离（每个用例）：`mock.patch.dict(os.environ, {"MW_AUTOPILOT_FILE": str(machine_file)}, clear=True)` 或 `{"MW_AUTOPILOT_HOME": str(fake_home)}`（必要时再给 `HOME`/`USERPROFILE`）；形状照 `test_rag_config.py:46,310-362`、`test_rag_init.py:64-86`。
- 项目层：`tmp_path` 即项目 root，`cfg.save_config(tmp_path, {...})` 造文件（`test_autopilot_config.py:91-103`）；机器层：`tmp_path/"machine.json"`（或 fake_home）。
- 断言三层：`values`（逐字段值）、`origins`（逐字段 origin）、`diagnostics`（机器层诊断）；再加“零足迹”断言（`not (tmp_path/".agenticdoc").exists()`，`test_autopilot_config.py:28-38`）与“完整 12 键”断言（`set(values) == set(DEFAULT_CONFIG)`）。
- 消费者断言（P-016：不能只验字段被写）：至少一条用例走 `conductor.tick()` 断言 `"ok"` 且用到的 verify 命令来自机器层（可用会写标记文件的 argv，照 RQ-2 §7 的建议）。

### 9.2 真值表

| # | machine | project | 期望（effective value / origin） | 断言要点 | 对应 AC |
|---|---|---|---|---|---|
| 1 | 缺失 | 缺失 | 全 12 键 = `DEFAULT_CONFIG`，全部 origin `default`；不建任何目录 | 零足迹 + 完整键 | AC-007(a) |
| 2 | 仅 xkey 三键 | 缺失 | 三键 origin `machine`；其余 origin `default`；`enabled=false` | 机器层不改变运行态 | AC-004/007(b) |
| 3 | 缺失 | 仅 `xkey_verify_cmd`（partial 文件） | 该键 origin `project`；其余 `default`；**12 键齐全** | 消除 partial KeyError（`mw.py:161`/`conductor.py:3975`） | AC-001/RQ-D2 坑 1 |
| 4 | 三键 | `xkey_verify_timeout_s` 覆盖 | 该键 origin `project`；另两键 origin `machine` | 逐字段 origin | AC-004/007(b) |
| 5 | `xkey_verify_timeout_s: 600` | `xkey_verify_timeout_s: null` | 值 `1800`、origin `default`（**不回落 machine**） | null 语义（§4.3） | AC-007(b) |
| 6 | `xkey_verify_cmd: null` | 缺失 | 值 `[]`、origin `default`（machine null 空操作） | machine null 语义 | AC-007(b) |
| 7 | `{"xkey_verify_cmds": [...]}`（未知键）+ 合法三键 | 缺失 | 未知键被忽略，合法三键 origin `machine`；`diagnostics` 含 `xkey_verify_cmds`；tick `"ok"` | 机器层 typo 不 poison | AC-007(c) |
| 8 | `{"xkey_verify_timeout_s": "600"}`（类型错） | `{"xkey_verify_timeout_s": 90}` | 值 `90`、origin `project`；diagnostics 含该字段 | 逐字段丢弃 + 下层胜出 | AC-007(c) |
| 9 | 文件内容 `{not json` | 合法 | 层视为空；值 = project/defaults；tick `"ok"` | 不整份作废 | AC-007(c) |
| 10 | `{"enabled": true}`（若受限域） | 缺失 | `enabled` 值 `false`、origin `default`；diagnostics 含 `enabled not machine-overridable` | 覆盖域 | AC-007(b) |
| 11 | `{"poll_interval_sec": 4}`（合法） | `{"poll_interval_sec": "4"}`（非法） | 抛 `ConfigError`（fail-closed），机器层不掩盖 | merge 前校验 | AC-002/§6 |
| 12 | 机器层同尺寸改写（另一进程写、不 `os.utime`、不清缓存） | 不变 | ≤1 tick 内 `values` 变为新值 | 缓存键含机器层 | AC-003/AC-007(d) |

### 9.3 路径解析真值表（AC-007(a)）

照 `test_rag_config.py:310-362` 四条断言写：
1. `MW_AUTOPILOT_FILE` 命中 → 用它，且压过 `MW_AUTOPILOT_HOME`；
2. `MW_AUTOPILOT_FILE` 设定但文件缺失 → 返回 None（层空，**不回落** `MW_AUTOPILOT_HOME`/`HOME`）；
3. `MW_AUTOPILOT_HOME`（目录）压过 `HOME`；
4. 都缺失 → 层空、**不创建目录**（`assert not (fake_home/".agents").exists()`）。

### 9.4 CLI 层断言（AC-004）

- `mw autopilot verify show --project <dir>` 文本行：`config: <path> (missing)` / 逐字段 `field = value [origin]`；形状照 `mw model show`（`mw.py:3205-3230`）与 `mw rag list`（`mw.py:1210-1256`，`_cmd_rag_list` 在 `mw.py:1231`）。
- `--json` 直接输出带 `origins` 的对象（照 `mw.py:1240-1242`）。
- 若 §8 删除 cli 层：断言输出/JSON 中**永不出现** `[cli]`，origin 值域只有三个。

### 9.5 与 AC-007 判据的逐条对应

| AC-007 条款 | 测试 |
|---|---|
| 路径顺序 `MW_<X>_FILE → MW_<X>_HOME → HOME → USERPROFILE`，缺失即层空且不建目录 | §9.3 四条 |
| 优先级 `… > project > machine > default`，逐字段 origin 可断言 | §9.2 #2–#6 |
| 机器层未知字段行为显式定义 | §9.2 #7–#10（推荐 fail-soft 的六条判据见 §5.3） |
| 缓存键必须含机器层 `(path, mtime_ns, size)` | §9.2 #12（+ RQ-D1 的 AC-003 判据写法同样适用到机器层） |

---

## 10. 风险与未决项（供 PM 定稿）

1. **机器层无写者**：本 key 的 AC 列表没有 `set --machine`。机器层建议文档化为“手改的 JSON”；若后续要加写者，必须镜像 `mw.py:2017-2035` 并纳入 AC-011 的锁与 `save_config` 的字节契约（见 design RQ-D4）。
2. **`dist` 同步面**：若最终决定 TS 也读机器层，`status-model.ts` 会新增 import（JSON 用 `JSON.parse`，YAML 会引入 `yaml` npm 包），`packages/coding-agent/dist/**` 是 tracked 产物（AC-009）——JSON 方案下这条风险为零。
3. **`worker_timeout_min` 是 dead config**（§3.1）：把它放进机器层等于把无效字段推广；建议在 design 里顺手记录“不纳入机器层”。
4. **与 AC-013 的交叉**：机器层若含新增 `xkey_verify_cwd` 键，它的值与占位展开的交互（机器层给的相对路径锚到哪）属于 design RQ-D3 的 cwd 语义；本 RQ 只确定“机器层可覆盖它、origin 记 `machine`”。
5. **`{python}` 类机器特定解释器**：机器层天然是放“本机解释器路径”的地方；RQ-4 §6 已否掉 `{python}=sys.executable`，本 RQ 不改变该结论——机器层放的是**命令 argv 字面量**，不是解释器绑定。
6. **凭证**：机器层不得含凭证（spec §2.3）；只放 argv/布尔/整数，无需 token。
7. **`MW_AUTOPILOT_FILE` 语义**：必须保留“设定但缺失 = 层空且不回落”（照 `mw_common.py:379-384`），否则测试会读真实 `$HOME`（RQ-4 坑 4）。

---

## 11. 复现命令（本文件所有事实）

```powershell
# PyYAML 可用性 / 版本
python -c "import yaml, sys; print('yaml', yaml.__version__); print(sys.version)"

# 无 Python 依赖声明
Get-ChildItem -Recurse -File -Include requirements*.txt,pyproject.toml,setup.py,setup.cfg,Pipfile |
  Where-Object { $_.FullName -notmatch 'node_modules|\.tmp' }

# YAML import / 使用点
Select-String -Path packages\multi-workers\mw_common.py -Pattern "import yaml|yaml\.safe_load|yaml\.YAMLError"
Select-String -Path packages\multi-workers\mw.py -Pattern "pip.*pyyaml|import yaml"

# RAG 母版
Select-String -Path packages\multi-workers\mw_common.py -Pattern "^def (machine_rag_servers_path|rag_servers_path|_rag_merge_server|load_rag_config|_rag_layer_servers)"
Select-String -Path packages\multi-workers\mw.py -Pattern "def _rag_machine_write_path|def _rag_format_origins"

# 消费点
Select-String -Path packages\multi-workers\autopilot\conductor.py -Pattern 'cfg\.get\("|cfg\["'
Select-String -Path packages\multi-workers\mw.py -Pattern 'cached_load\(project_dir\)\["enabled"\]'

# MW_AUTOPILOT_* 命名空间是否空闲
Get-ChildItem packages -Recurse -File -Include *.py,*.ts | Select-String -Pattern "MW_AUTOPILOT"
```

---

## 12. 只读复核

- 本文件是本次任务唯一写入（`.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-machine-layer-20260926.md`）。
- 未修改任何 tracked 文件；`git status --porcelain` 只应显示本 key 目录为 untracked（其余为其它会话的既有改动，未触碰）。
- 全文结论均有 `file:line` 出处；未实测的行为均标注为“推荐/契约”，未冒充现状。