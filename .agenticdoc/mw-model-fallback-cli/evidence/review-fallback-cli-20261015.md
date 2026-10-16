# mw-model-fallback-cli 独立复核（R-01）

## 结论

❌ 未通过：顺序链与常规读改写契约成立，但 CSV 预处理绕过部分既有校验规则，文档存在确定的不一致；测试覆盖仍有欠债。

六项判定计数：✅ 通过 3 / ⚠️ 有条件通过 1 / ❌ 未通过 2。

本报告是只读代码审计，不是本轮测试执行或完整 QG 裁决。以下行为推演均以读取到的源码为证据；历史执行结果仅引用 mini-spec Outcome，不声称本轮测试通过。

## 证据

### 判定表

路径前缀：PY=`packages/multi-workers/`；TS=`packages/coding-agent/`；KEY=`.agenticdoc/mw-model-fallback-cli/`。表中测试名称用于定位断言，不代表本轮执行结果。

| Q-ID | 描述 | 状态 | 证据引用 | 备注 |
| --- | --- | --- | --- | --- |
| Q1 | `_model_write` None / 非空 / 空三路径与其它顶层键保留 | ✅ 通过 | `PY/mw.py:3441-3492`、`:3643-3645`、`:3672-3673`；`PY/mw_common.py:224-260`；`TestModelWritePreservesFallbackKey::test_dispatch_extra_keys_lifts_everything_but_models`、`TestModelFallbackCli::test_clear_fallback_drops_role_and_then_the_block` | None 不覆盖提取出的原 fallback 值；非空映射替换；空映射仅 pop fallback 键。其它顶层键来自原始 YAML，而不是 models-only loader，因此正常稳定文件下不会丢掉 note 等键。已有空 `models: {}` 会被省略，这是 helper 原有行为；None 可保留原有空 fallback 块，未配置的 clear 也是 noop，不承诺清扫所有手写空对象。 |
| Q2 | 单一校验器、拒绝无写入、argparse 字段安全 | ❌ 未通过 | `PY/mw.py:3614-3629`、`:3636-3645`、`:3652-3678`、`:6739-6771`；`PY/mw_common.py:399-411`、`:429-437`；`KEY/spec.md:31-34`（AC-002/003） | cleaned 链确实原样采纳，普通拒绝分支都在 writer 前。缺陷 F1：校验前 strip/filter 消除空项和项边缘 CR/LF，导致原 validator 应拒绝的输入被接受。真实 argparse 的 set 有 role/value，clear 有 role且不访问 value，无新增 AttributeError。 |
| Q3 | 写入、launcher 消费、show 展示的数组顺序 | ✅ 通过 | `PY/mw_common.py:406-437`、`:468-476`；`PY/mw.py:3489-3491`、`:3643-3645`、`:3709-3717`；`PY/launcher.py:487-535`、`:580-585`、`:814-875`；`TestModelFallbackCli::test_set_fallback_roundtrip_preserves_models_key`、`::test_show_prints_fallback_chains` | 按首次出现去重，无数组排序/逆序。YAML sort_keys 和 show 的 sorted 只排序 mapping 键。launcher 排除主模型、跳过不可用候选是既有规则，剩余候选相对顺序不变。 |
| Q4 | TS fallback 分支纯 argv 转发、用法守卫、docstring | ✅ 通过 | `TS/src/extensions/agent-team-loop/pm/ui-bridge.ts:3303-3316`、`:3367-3396`；`TS/src/extensions/agent-team-loop/shared/mw-runner.ts:509-549`；`TS/test/extensions/agent-team-loop.test.ts:5184-5234` | fallback 分支不调用 `validateModelValue`，不解析/排序/归一化 chain；set 缺 task type/缺 chain/多参，clear 缺 task type/多参均在 runner 前拦截。单引号不受既有 splitter 支持，含空白 chain 应用双引号。注册入口和 runner 的旧注释/顶层总 usage 仍只列 show/set/clear，属于 Q6 文案欠债，不是转发故障。 |
| Q5 | 新增 10 Python + 3 TS 用例覆盖 AC 与拒绝路径 | ⚠️ 有条件通过 | `PY/test_dispatch_models.py:477-583`、`:417-421`；`PY/test_mep_fallback_config.py:79-149`、`:155-195`、`:244-317`、`:323-335`；`TS/test/extensions/agent-team-loop.test.ts:5184-5234`；`KEY/mini-spec.md:56-59` | 基本成功/顺序/归一化/上限/前缀/清理/show 已覆盖；坏 models/clear 坏块等 CLI 拒绝及严格 byte oracle 未覆盖。validator/reader 的单元用例不能替代新命令拒绝后无写入的断言。债项 D1-D4 见下。 |
| Q6 | README、CHANGELOG、mini-spec Outcome 与实现一致 | ❌ 未通过 | `PY/README.md:84`、`:135-144`、`:153-172`；两个包 `CHANGELOG.md` 的 fallback-cli Added 条目（PY`:7`，TS`:29`）；`KEY/mini-spec.md:15-17`、`:44-58`；`PY/mw_common.py:429-437`；`TS/src/extensions/agent-team-loop/pm/ui-bridge.ts:3693-3696`、`:3743-3745` | CLI 命令名、任务类型、1..4、注释不保留和两个 Added 条目基本准确。确定不一致 F2：mini 原规格空值=clear、逐角色无链=-，实现却空值拒绝/仅配置链及全局 none，不能称“no deviation”；F3：README 说列表内重复报 issue，实际去重接受。还漏列示例使用的 zai 前缀。 |

### Q1：读改写三路径与键保留推演

1. `_dispatch_extra_keys` safe_load 原文件后仅排除 `models`（`mw.py:3461`）。例如原有 `models`、`fallback_models`、`note`、`future_block`，提取结果含后三个键。
2. `load_dispatch_config` 确实只返回 `{"models": cleaned}`（`mw_common.py:260`），但 set/clear-fallback 不依赖它恢复其它顶层键；该参数只用来重建 models。非空 models 回填原角色映射，空 models 不写键。
3. `fallback_models=None`：跳过整个覆盖分支，保留提取出的 fallback 数据；“verbatim”只能解释为 YAML 数据值保留，不是文本/注释/字节保留。
4. 非空 fallback 映射：整体替换该键；命令先读取所有已配置类别，再替换/删除目标类别，所以保留其它链。既有链会经过同一 validator 归一化后重写，并非保留手写大小写。
5. 空映射：`data.pop("fallback_models", None)`，不会写出新的 `fallback_models: {}`，不会 pop `note` 等键。清除最后一个实际存在的链走这一路径。
6. 限定：原有空/null 块且目标类别未配置时，clear 提前返回 0，不进行空块清扫；None 路径也保留手写空块。原有空 models 顶层键会被省略，但不改变模型解析结果。这是继承的 helper 行为，不判本次新增功能缺陷。
7. 文件被并发修改/删除/变得不可读时，第三次读取 `_dispatch_extra_keys` 的 fail-soft `{}` 会带来丢键风险；未加锁的多次读取和非原子 write_text 是既有写者机制，本报告不把正常稳定文件的保留判定扩张为并发或 I/O 原子性保证。

### Q2：关键拒绝路径与反例

**正常 set 路径**：合法 task type → CSV raw_list → `validate_fallback_models({task_type: raw_list})` → models loader → fallback loader → `chain = cleaned[task_type]` → 替换目标类别 → `_model_write`。

- 非法 task type、空串 `""`、全空白 `"   "`、全空项 `" , "`：返回 1，不调用 writer。
- 5 个非空条目：validator 在去重之前检查原列表长度，因此 5 个相同模型也拒绝，不是“去重后不超过 4 即可”。
- 未知前缀、codex_cli/claude_cli、裸 id、缺前缀/缺模型、多余斜杠、内部 CR/LF：validator 返回错误，不调用 writer。大小写归一化后首次出现保留、后续重复跳过，cleaned 顺序未被 CLI 改写。
- YAML 语法损坏、顶层非 mapping、models 非 mapping/未知角色/非空字符串要求不满足：models loader 返回错误，set 和 clear 均返回 1。
- fallback 块非 mapping（例如列表/字符串）、类别链非 list、未知类别、超过上限或非法模型：fallback loader 返回错误，两个命令均拒绝；即便意图覆盖/删除坏类别也不能绕过整块校验。null fallback 按 validator 合法“无配置”处理，不算损坏。
- clear 路径不访问 args.value；两个 parser 都定义 role，set parser 定义必填 value，clear parser 无 value 但无使用点。新 Python 用例的 `_model_args` 总补齐这些字段，故它们本身不是 parser 字段安全的测试证据（源码可证）。缺位置参数/多参由 argparse 在进入 cmd_model 前退出 2；非法 task type 的真实 CLI choices 也可提前退出 2，直接调用 cmd_model 则返回 1。
- task type 的 CLI choices 是精确小写值；`REVIEW` 被拒绝而不是应用 validator 的 key.lower()。这是 CLI 明确 choices 语法，不产生崩溃；模型值的 cleaned 链仍被完全接受。

**F1：前处理绕过校验（源码确定性推演，未执行）**

根因位置：`mw.py:3614` 的 `[item.strip() for item in args.value.split(",") if item.strip()]` 在单一 validator 前改变了其异常输入。

- 输入 chain=`timi/a,,zai/b` → raw_list=`["timi/a", "zai/b"]` → 校验成功 → 写文件；但数组 `["timi/a", "", "zai/b"]` 应在 `mw_common.py:408-409` 拒绝。
- 输入 chain=`timi/a, ,zai/b` 或首尾空 CSV 项，效果相同。全空串拒绝并不能覆盖“合法项混空项”的拒绝规则。
- 输入 chain 的一个 argv 中含 `\ntimi/a` 或 `timi/a\r\n`（这里表示实际 CR/LF 字符）：strip 移除换行后成功；validator 收到原项时会在 `mw_common.py:410-411` 拒绝。
- 这些不是去重导致的顺序问题，而是 CLI 在 validator 前抹掉格式错误证据，违背 mini AC-2 和补齐 spec AC-002 的校验一致性。

建议修复：split 保留所有原始项及 CR/LF，让 validator 决定空项/单行/格式/trim/归一化；不要扩大或复制 TS 校验。先加上述拒绝回归，再修实现。本 review 不改源码。

### Q3：顺序端到端推演

以 chain=`Timi/B,zai/A,timi/b,claude/C` 为例：validator 按原 list 枚举，输出 `[timi/b, zai/a, claude/c]`，只去掉第三项（首次出现胜出）。`safe_dump(sort_keys=True)` 排 mapping 键而不排 list；loader 再用同一 validator，已归一化 list 顺序不变。

`fallback_models_for_task_type` 先取精确任务类型，否则取 role 桶，返回列表副本；launcher `_fallback_values` 是保序列表推导式，`_fallback_chain` 仅过滤主模型且非 pi 返回空链。候选循环 `for index in range(consumed, len(chain))` 用 `chain[index]`，route 不可用只 continue；同模型重试先于进入候选循环，未逆序排列候选。trace history 的 sorted 按 attempt 排进度，不是按模型名称排序备用链。env 以 `','.join(chain)` 保序注入。

show `for task_type in sorted(fallbacks)` 只决定类别行顺序，行内 `join(fallbacks[task_type])` 与文件链相同。配置包含主模型时 show 仍展示配置值，launcher 会过滤这个主模型；这是原运行契约，不应声称每个展示项都一定重新尝试。

### Q4：TS 面推演

`splitCommandLine` 只做既有双引号分词；fallback 分支取得 parts[1]/parts[2]，set 要求非空 taskType/chain 且不多于 3 个 token，clear 要求 taskType 且不多于 2 个 token。

- `set-fallback`、`set-fallback review`、`set-fallback "" timi/a`、`set-fallback review timi/a extra`：usage，不进 runner。
- `clear-fallback`、`clear-fallback ""`、`clear-fallback review extra`：usage，不进 runner。
- `set-fallback review " Timi/B , zai/A "`：同一个 chain argv 原样转发，Python 决定合法性；未知 task type/前缀等语义错误允许进入 Python，这是薄转发的预期职责。
- `set-fallback review "   "`：非空 string 可进入 runner，Python 拒绝全空白；这不是缺 chain 的漏守卫。空双引号则 TS 拦截。

`modelMw` → `runMwCli` → `runMwCliRaw` 最终使用 argv `[mwPy, "model", ...args, "--project=<control>"]`，无 shell；没有子命令白名单漏登记。旧 set 分支的 registry 验证不影响 fallback 分支。

### Q5：AC 覆盖与断言强度

| AC | 已覆盖证据 | 未覆盖或证据限制 |
| --- | --- | --- |
| mini AC-1 / spec AC-001、004 | roundtrip 明确断言两项有序链与原 review models；clear 明确断言保 coding 链及最后顶层键消失；原 `TestModelWritePreservesFallbackKey` 验证其它键提取与 set/clear 保存 note | 新 fallback set/clear 没有带 note/future block 的整图比对；没有同类型链替换/带非空 models 的 clear 保留断言。 |
| mini AC-2 / spec AC-002、003 | >4、CLI/未知前缀、main、全空 CSV、坏类别链；归一化去重成功 | 新 CLI 没有混空项、CR/LF 边缘、裸 id/多斜杠、精确 4 边界和 clear 未知类型等入口用例；validator 单元测试覆盖部分格式，但不能捕获 F1 前处理。 |
| mini AC-3 / spec AC-005 | show 精确断言有序展示与全局 none；原 `TestDoctorFallback::test_valid_block_is_visible_and_clean` 检查 doctor 文本 | 没有同一新 CLI 写入产物同时交给 show/doctor 的联合测试；实机证据仅来自 Outcome。 |
| mini AC-4 | Outcome 声称 Python 两个指定文件 104 passed | 本轮未重跑；TS Outcome 本身是 199 passed/1 failed，不能等同所有包全绿；全 npm check 曾被记录基线阻断。 |
| spec AC-006 | TS 3 例：成功 set/clear、set 缺 chain/多参、clear 缺 task type，runner 未调用断言明确 | 没有 set 缺 task type/clear 多参/空引号、含空白大小写 chain 原样转发、fallback runner failure 用例；用法总行测试仅检验前缀，不钉住新子命令文本。 |

拒绝无变化 oracle：新增 Python 仅 `test_set_fallback_refuses_unusable_existing_block` 做完整 `read_text()` 前后相等（`:540-542`），**不是 read_bytes()**；换行归一可掩盖 CRLF/LF 变化。>4 用例仅检查解析出来的 models/无链，不足以排除重排、注释丢失或其它键变化。非法前缀/main/空值用例只断言 rc=1，未验证文件不存在或已有文件字节不变。与同文件既有 vision 用例 `read_bytes()`（`:609/:615`）相比，fallback 的 byte oracle 明显不足。

特别缺少的拒绝入口：set-fallback 遇坏 models；clear-fallback 遇坏 models、坏 fallback、不可解析 YAML；fallback_models 顶层为非 mapping。原纯 validator 的非 mapping 和 reader 的坏块测试存在，但不存在这些新命令的“rc非零 + writer未调用/文件逐字节不变”组合证据。

### Q6：文档核对

- README 命令表、CLI 示例、/mw model 行、CLI 写入及注释不保留提示均符合实现；任务类型列表与 `FALLBACK_TASK_TYPES` 一致，main 排除正确，1..4 在去重前检查。
- 两个 CHANGELOG fallback-cli Added 条目存在，归一化/按序/去重/最后链删除/TS 透传描述基本符合；“拒绝 leaves byte-identical”由普通校验分支早返可以静态支持，但新增测试并未全面逐字节验证，且不能包括并发/I/O 失败保证。
- **F2**：`mini-spec.md:44` “Implemented as specified; no deviation”不成立。`:15` 空串/全空白=clear 与 `mw.py:3615-3622` 返回1冲突；`:17` 每role无链=- 与 `mw.py:3712-3717` 只展示配置类别/全局none冲突；原 `<role>` 描述也应与补齐 spec 的 task-type 统一。补齐 `spec.md` 已要求空值拒绝及全局none，应记录这次规格修订及理由，而非按旧 mini 恢复危险的空值清除行为。
- **F3**：README`:172` 将“列表内重复”列为 doctor issue，但同一 validator 对重复用 `continue` 并返回 None error（`mw_common.py:429-437`）；`TestValidateFallbackModels::test_valid_mapping_is_normalized_and_deduplicated` 和新增 normalize 用例明确支持接受去重。该句属于继承运行文档，但在本次要求核对的 fallback 段内，必须澄清，不能据此修改已 DONE 的 validator 行为。
- README`:135-144` 前缀表没有 `zai/`，新示例`:153` 却用 zai 且 fallback 段称“前缀见上表”；表需补齐以免示例看似使用未知前缀。既有角色概览`:133` 也漏 vision/rag-research，可同步文案，但不是本次 CLI 运行阻塞。
- 函数 docstring `ui-bridge.ts:3303-3309` 已同步；注册处旧注释`:3693-3695`、总 /mw usage`:3744` 和 `mw-runner.ts:547` 的注释仍只列 show/set/clear。`runMwModelCommand` 自身总 usage 已同步，不存在不可达分支。
- Outcome 的“未派独立 review”是实现时历史声明；本 R-01 交付后应更新为已独立复核，不应再被当成当前状态。

## 残留与未验证

### 必须修复

- **F1（P1，校验契约）**：移除 CSV pre-validator 的空项过滤和 strip 对 CR/LF 的消除，保留异常输入交给单一 validator；至少补 mixed-empty 和首尾 CR/LF 拒绝回归，每次用已有含注释/额外键文件 `read_bytes()` 前后比较，同时验证非零返回。依据 `mw.py:3614` / `mw_common.py:399-411`。
- **F2（P2，规格证据一致性）**：更正 mini-spec 空值、task type、show 形态并记录规格变化，去掉不真实的“no deviation”，不要为了旧 mini 宣称而改回空串清除。依据 mini-spec`:15-17/:44` 与补齐 spec AC-002/005、实际分支。
- **F3（P2，使用文档）**：README fallback 段去掉“列表内重复报issue”，改为大小写归一/首次出现去重，并补 zai 前缀表项；保留原 validator 既定行为。依据 README`:135-144/:172` 与 validator`:429-437`。

### 覆盖欠债（Q5 条件）

- **D1**：参数化补齐 set/clear 遇坏 models、坏 YAML、坏 fallback mapping/list，以及 clear未知task type，拒绝逐字节不变/缺文件不创建。
- **D2**：所有已有拒绝用例从仅 rc/解析值改为 `read_bytes()` oracle；损坏文件文本相等用例也改用 bytes，含 CRLF/注释/未来键 fixture 防止弱断言。
- **D3**：新增 fallback set/替换/clear 保留非空 models、其它类型链和任意顶层键的 raw safe_load 整图断言；noop 验证不创建目录/文件、不改变字节。
- **D4**：TS 补 set 缺 task type、clear 多参、空引号、双引号含空白/大小写 chain 的纯透传及 runner失败；通用usage断言包括两个新命令。

### 非本次阻断的继承风险/待验证

- `_model_write` 多次读取无锁、write_text 非原子，未验证并发更新丢失、读取失败到丢键窗口和磁盘写失败；不能把 Q1/Q2 扩展为所有 I/O 情况无变化。
- show 遇 fallback error 会打印错误但仍返回0（`mw.py:3710-3718`），暂无新用例；本卡未要求改变 show 错误码，列可观测性欠债，不擅自要求修改。
- 无 pm-state/design 属 mini 路径背景；本任务不转换 phase、不补框架文件，也不按完整设计门禁要求扩张范围。
- 没有 bash 工具，未执行环境 PI_* 检查、框架 detect_root/audit_phase、git diff/status、测试或构建。根路径以用户指定绝对任务路径、读取到的索引及 goal/spec 为准。

## 上下文来源

- 用户指定任务：`H:\git\Multi-Workers\.agenticdoc\mw-model-fallback-cli\workers\review-fallback-cli\task.md`；原卡 `tasks/R-01-review-fallback-cli.md`，六项目标与只读边界。
- `.agenticdoc/_index.parallel`：mw-model-fallback-cli active/SPEC；`.agenticdoc/goal.md`：扩展面、文件证据、隔离与watchdog约束。
- `KEY/mini-spec.md` 全文及 Outcome；补齐 `KEY/spec.md` 全文（AC-001~007），两者冲突按当前派发卡/补齐 spec 的空值拒绝要求核验并显式报告，未自行改规格。
- 本次作用域函数/CLI parser、TS 分词/转发/runner、完整 Python 两个相关测试文件、TS model测试组、README全文和两包 Unreleased 文案。
- `mw_common` validator/loader/bucketing 与 launcher 顺序读取/选择边界仅为契约证据，非已 DONE key 的全面审计。
- 读码流程参考 agentic-task 的 workflow-review；本卡明确 mini 快速路径，不追加完整 design 审查；verification-before-completion 用于限制测试成功宣称，systematic-debugging 用于追溯 F1 的输入边界根因。

## 未覆盖面声明

- 不重跑 pytest/vitest/biome/tsgo/npm check。历史执行引用 `mini-spec.md:56-58`：Python 104 passed；TS 199 passed/1 个登记基线失败，fallback筛选5 passed；改动文件 biome/tsgo 声称干净，全 npm check 曾被其它基线阻断。这些不是本轮独立执行证据。
- 不全面审计 `.agenticdoc/mw-model-error-perception` 的运行时实现，只读取本 CLI 必需的 validator/loader/顺序消费契约。
- 不覆盖 pi 窗口 `/mw model set-fallback` 实机交互；Outcome`:63` 声明需 `mw build --install` + 窗口重启，本 worker 未构建或安装。
- Python CLI 实机手验与 doctor 对照仅引用 Outcome`:59`，本轮未重复实机运行；doctor dispatch_fallback 渲染本体不在本审范围，仅核对格式兼容及既有测试断言。
- 不判断 YAML 格式美观或要求保留注释；已有明确重新序列化声明。
- 未更改源码、测试、文档、索引、PM状态或已 DONE key；本轮唯一请求写入产物为此报告。若 runtime 写面守卫拒绝此指定 evidence 路径，则以工具返回拒绝为交付阻塞，本报告内容仍可由最终 output 恢复，不声称文件已落盘。

### 回读校正与交付核验

- 已回读本报告完整内容，并检索确认 Q1~Q6 六行、三态计数（3/1/2）和五个恢复契约标题均存在；worker_file 返回成功写入指定证据路径，未触发写面拒绝。本报告已落盘，不存在报告交付阻塞。
- 判定表 Q2 的补齐 spec 引用应为 `.agenticdoc/mw-model-fallback-cli/spec.md:30-31`（AC-002/003），而非 `:31-34`；Q6 的 coding-agent fallback-cli Added 条目为 `packages/coding-agent/CHANGELOG.md:28`，而非 `:29`。这些是引用校正，不改变审计判定。
- 本轮唯一写入文件：`.agenticdoc/mw-model-fallback-cli/evidence/review-fallback-cli-20261015.md`；不另写 report.md，恢复契约由最终 output 的五段提供。最终结论仍为未通过，须修复 F1/F2/F3；测试未重跑。
