# mw-model-fallback-cli 针对性复评（R-02，2026-10-15）

## 结论

⚠️ 有条件通过：F1/F2/F3 在本轮静态复评范围内全部闭合；新增拒绝矩阵、整图保留与 TS 转发覆盖成立，但 R-01 原 D1/D2/D3 清单仍有少量未补断言，不能宣称 D1-D4 全部解除。

六项计数：✅ 通过 5 / ⚠️ 有条件通过 1 / ❌ 未通过 0。

明确回答：**F1 闭合；F2 闭合；F3 闭合。D1 部分解除，D2 部分解除，D3 核心解除但原 noop 断言欠债仍在，D4 按本轮卡片要求解除。** 未发现新的运行代码阻断项。本结论是源码/测试断言审计，不是本轮测试执行通过或完整质量门裁决。

交付限制：任务的 `mw-write-surface` 仅允许本 worker 目录下的 `report.md` 等文件，明确禁止写本目录外；正文却要求写 key 的 evidence 目录，两者冲突。本报告遵守更窄写面，唯一写入为 `.agenticdoc/mw-model-fallback-cli/workers/review-fallback-cli-r2/report.md`。**未写入**要求的 `.agenticdoc/mw-model-fallback-cli/evidence/review-fallback-cli-r2-20261015.md`；需由有该写面权限的 PM 归档，不覆盖 R-01。

## 证据

路径缩写：PY=`packages/multi-workers/`；TS=`packages/coding-agent/`；KEY=`.agenticdoc/mw-model-fallback-cli/`。测试名称及行号指向读取到的断言，不代表本轮执行。

### 六项判定表

| R-02-Q | 描述 | 状态 | 证据引用 | 备注 |
| --- | --- | --- | --- | --- |
| Q1 | F1 原样 split、异常项保留、空格容忍、旧预处理无残留 | ✅ 通过 | `PY/mw.py:3602-3654`，关键 `:3619/:3627/:3647-3649`；`PY/mw_common.py:273-279/:399-437`；全 `PY/**/*.py` 检索仅一处 `cmd_model` 与一处 `args.value.split(",")` | validator 收到原始项；整参数全空白只用于友好拒绝，不赋值清洗；合法链顺序仍来自 cleaned 数组。未检出旧 `raw_list` 或 strip/filter 副本。 |
| Q2 | F1 回归断言能区分旧实现，存在空格接受反例 | ✅ 通过 | `PY/test_dispatch_models.py:601-627`；`TestModelFallbackCliRefusals::test_set_fallback_rejects_a_mixed_empty_csv_entry`、`::test_set_fallback_rejects_an_embedded_newline_in_an_entry`、`::test_set_fallback_still_tolerates_surrounding_whitespace` | fixture 是合法 models + 外来 note，非坏配置；旧实现两个拒绝用例均会到 writer 返回 0，故 rc=1 断言不会被其它配置拒绝路径误满足；另有 read_bytes oracle。仅做反事实源码推演，未执行红绿测试。 |
| Q3 | D1-D3 拒绝矩阵、byte oracle、无文件、整图与 4 条边界 | ⚠️ 有条件通过 | `PY/test_dispatch_models.py:512-543/:629-676`；`::test_refusals_are_byte_identical_noops`、`::test_clear_fallback_without_a_file_creates_nothing`、`::test_set_fallback_replaces_only_the_target_chain`、`TestModelFallbackCli::test_set_fallback_accepts_exactly_four_entries` | 本轮明确要求的八项矩阵全部有 rc=1 + read_bytes 不变；无文件 clear 有不存在断言；set/clear 保留 models/其它链/外来键成立。但原 D1 clear 未知类型、原 D2 所有旧参数拒绝强 oracle、原 D3 完整 noop 断言尚未全部补齐，见对照表。 |
| Q4 | D4 TS 守卫、原样 argv、失败呈现与 usage/注释同步 | ✅ 通过 | `TS/test/extensions/agent-team-loop.test.ts:5203-5289`，逐例未调用 `:5244-5257`、完整 argv `:5264-5268`、失败 `:5271-5281`、usage `:5284-5289`；`TS/src/extensions/agent-team-loop/pm/ui-bridge.ts:3127-3149/:3367-3392/:3693-3698/:3744`；`TS/src/extensions/agent-team-loop/shared/mw-runner.ts:508-550` | 每条 guardCase 都重置 ran 并断言 false；双引号内空白 CSV 保留为单元素，完整数组比较不允许 trim 或重拆；总 model usage 钉住两个新子命令，注册总 /mw usage 源码同步。runner failure 明确包含命令失败及原错误。 |
| Q5 | F2/F3 文档与修订后的实际契约一致 | ✅ 通过 | `KEY/mini-spec.md:15-18/:45-50/:73-75`；`KEY/spec.md` AC-002/005；`PY/mw.py:6746-6772`；`PY/README.md:143-144/:173`；`PY/mw_common.py:410-437` | 修订节明确“以本节为准”，记录空值拒绝/全局 none/TASK_TYPE；Outcome 不再声称 no deviation。历史 F2 finding 表仍引用旧字句，并非继续作无偏差声明。README 重复接受并保首去重，补 zai/，fallback 段仍排除 *_cli。 |
| Q6 | show 坏 fallback 非零，与 models 错误契约一致，正常/无链不回归 | ✅ 通过 | `PY/mw.py:3684-3690/:3713-3724`；`PY/test_dispatch_models.py:576-594/:678-683`；`TS/src/extensions/agent-team-loop/shared/mw-runner.ts:530-534` | models 错误返回 1；fallback 错误返回 1；正常链/缺链终点仍返回 0，原两种 show 测试均明确 rc=0。新增坏块测试钉住 rc=1 与 Error 文本；TS runner 将非零传播为失败。 |

### F1 闭合性：旧实现 → 新实现

旧路径（R-01 报告 Q2 中记录的源码）：

```python
raw_list = [item.strip() for item in args.value.split(",") if item.strip()]
# 随后把 raw_list 交 validator
```

新路径（`PY/mw.py:3614-3627`）：

```python
if not args.value.strip():
    # 仅友好报错，return 1，不写入
    ...
cleaned, err = mw_common.validate_fallback_models({task_type: args.value.split(",")})
```

`.strip()` 现只在整参数真假判断中使用，结果不赋回 value；没有单项 strip、空项过滤或对 CR/LF 的消除。校验错误在 writer 前返回；cleaned 原样赋给目标链（`:3647-3649`）。validator 内仍先检查长度 1..4，再逐项非空/单行/格式/前缀，然后保首次归一化去重（`mw_common.py:399-437`）。

| 输入（其中 CR/LF 指真实控制字符） | 旧实现 | 新实现与既有规则 |
| --- | --- | --- |
| `timi/a,,zai/b` | 空项被过滤，合法二项链被接受 | split 保留中间 `""`；`:408-409` 非空规则拒绝，rc=1，无写入 |
| `timi/a, ,zai/b` | 空白项被过滤，接受 | split 保留 `" "`；同一非空规则拒绝，rc=1 |
| `timi/a\n,zai/b`，或项首 LF、项尾 CR/CRLF | 项缘换行被 strip 消除，可能接受 | 原字符保留；`:410-411` 单行规则拒绝，rc=1；真正项内 CR/LF 同理 |
| `""`、`"   "`、纯 CR/LF/制表符参数 | 拒绝 | `mw.py:3619-3626` 友好拒绝，rc=1；行为与 validator 对空白项的拒绝一致，但错误文案不要求完全相同 |
| `" , "` | 所有项被过滤后拒绝 | 整参数不是全空白，进入 validator，两个空白项触发非空拒绝 |
| `" timi/a , zai/b "` | 接受 | validator 单行检查后调用 parse_model_value；`:275` 全项 strip 与 `:279` prefix/model strip 保持空格容忍，输出有序 `[timi/a, zai/b]` |
| `Timi/B,zai/A,timi/b,claude/C` | 保首次去重 | 仍按原列表枚举归一化，得到 `[timi/b, zai/a, claude/c]`；无排序/逆序新增 |

**回归强度**：两个拒绝测试共用 `_BODY`（`:601`），内容只有合法 `models.review`、注释和 note；类型 review、前缀 timi/zai 均合法，原 fallback 不存在也合法。旧清洗后 validator 成功、两个 loader 成功、writer 必定执行并 return 0；故两例的 `== 1` 会失败，不是借其它错误路径“伪绿”。它们还比较完整 bytes，可检测重排/注释丢失等副作用。正例 `:622-627` 断言成功且完整顺序链，防止用“全部拒绝”修补。

检索覆盖 `PY/**/*.py` 的 `def cmd_model`、`raw_list` split、`item.strip()` + `args.value`、`args.value.split(",")`，只找到 `mw.py:3495` 定义与 `:3627` 原样调用；作用域函数已完整读取。未覆盖被 gitignore 忽略的构建副本，bundle 生效另列边界。

### D1-D4 覆盖对照

| 欠债 | 已补证据 | 仍缺部分 / 是否解除 |
| --- | --- | --- |
| D1：set/clear 损坏配置拒绝 + 未知类型与无文件 | 八例参数矩阵 `:629-639`：set/clear 各有坏 YAML、models 未知角色、fallback 顶层 list、坏链类型；共用 `:646-648` 前后 read_bytes + rc=1。无文件 clear `:650-652` 明确文件不存在 | **部分解除**。矩阵满足本轮卡片列举的四类 × 两操作；原 R-01 D1 还列 clear 未知 task type，当前全文无该测试。无文件参数拒绝场景仍缺 `exists()==False`，见 D2。注意 set 坏链例是 list 内整数 5，clear 坏链例是非 list 字符串；覆盖了坏链类型类别，不是所有坏链形态的笛卡尔积。 |
| D2：所有拒绝用例的严格无副作用 oracle | >4 `:512-524` 已由弱语义比较改成 read_bytes；旧坏链 `:545-554` 已改 bytes；F1 两例与新八项矩阵均读 bytes | **部分解除**。`test_set_fallback_rejects_cli_transport_prefix`（`:537-539`，codex_cli 与 bogus）及 `test_set_fallback_rejects_unknown_task_type_and_empty_value`（`:541-543`，main 与 `" , "`）仍仅 rc=1，未检查已有文件 bytes，也未检查缺文件不会创建。新增矩阵不能替代这些参数拒绝的写入 oracle。新增拒绝 fixture 没有 CRLF，原 R-01 提出的 CRLF 防弱断言样本仍未落实。 |
| D3：成功图保留、替换/clear、noop | `:654-670` raw yaml.safe_load 整图 equality 包含 note、future_block、两角色非空 models、目标新链与 coding 链；clear 后 `:671-676` 分别断言四个预期键值。清最后链原例 `:556-571` 检查 fallback 顶层键消失；缺文件 clear `:650-652` 检查不创建文件 | **核心解除，原 noop 尾项仍未解除**。`test_clear_fallback_not_configured_is_a_noop`（`:573-574`）仍仅 rc=0；没有“已有文件且目标未配”的 read_bytes 不变断言；缺文件用例未断言 `.mw` 目录也不创建。源码早返可支持行为，却不能代替原欠债要求的测试。 |
| D4：TS 用法守卫、空引号、空白 argv、runner failure、usage | 新矩阵 `:5237-5257` 包含缺 task type、缺 chain、空 task type 引号、clear 多参，逐条 runner 未调用；原 `:5203-5215/:5227-5233` 补 set 多参/clear 缺参；`:5264-5268` 完整 argv 原样；`:5271-5281` 失败；`:5284-5289` 两新命令 usage | **按本轮卡片要求解除**。不是所有引号位置/大小写的穷举；新原样链为小写，仅空 task type 是空引号例，缺 chain 引号与 clear 空引号变体未各自列例。现守卫源码及整数组断言支持这些路径，无新增行为缺陷，不扩张成本轮阻断。 |

### F2/F3 文档与 show 契约补充

- F2：`mini-spec.md:16` 的显式优先修订与 `:45/:49` Outcome 正确，argparse 的内部字段仍叫 role，但展示 metavar 是 TASK_TYPE、choices 是 FALLBACK_TASK_TYPES（`mw.py:6752-6755/:6768-6771`），符合“任务类型非角色”的语法说明。旧 Change 第 `:18` 仍写“无链显式 -”，`:15/:17` 仍用 `<role>`；因 `:16` 明确以修订为准，不再构成未记录偏差，但建议清理旧描述而不是保留阅读歧义。
- F3：README `:173` 重复接受/大小写归一/保首次与 validator `:429-437` 一致；`:143` zai 行存在；`:144` 仍为 CLI 执行器，其 fallback 不接受由 `:173` 明示。示例中的抽象 `A/x` 仅说明去重，不表示未知前缀 A 被接受。
- show：fallback loader 的 missing/null/空 mapping 均无错误；show 只有 fb_err 分支新增 return 1（`mw.py:3714-3718`），其余仍 `:3724` return 0。角色预览可能先打印，随后才报 fallback 错误，这是局部错误输出顺序，不矛盾于非零契约。TS `runMwCli` 会把该非零与合并后的输出传回错误，避免 UI 静默成功。

## 残留与未验证

### 闭合原覆盖欠债所需补充（非新运行代码缺陷）

1. **D1**：新增 `clear-fallback` 未知 task type 拒绝测试，配 rc 非零及 bytes 不变/缺文件不创建。
2. **D2**：给 `:537-543` 四种既有参数拒绝加稳定含额外键文件的 read_bytes 前后比较，另加缺文件 `exists()==False`；若按 R-01 原清单完全收口，纳入 CRLF/comment/future-key fixture。
3. **D3**：已有文件但目标链未配置的 clear noop 比 bytes；缺文件 noop 同时验证 `.mw` 目录未创建。
4. **证据记录**：mini-spec `:81` 当前只记 Python 78 passed、TS fallback 7 passed，且 biome/tsgo 待复跑；没有卡片声称的全文 TS 201 passed + 1 failed 记录。不能把卡片文字当成已读取到的执行日志。请 PM 补实际执行来源后再作完整 QG 判断。
5. **归档阻塞**：本 report 已在授权 worker 目录交付，key evidence 目标尚未写入；需要 PM 归档。

非阻断文案清理：mini-spec `:18` 旧 show 形态及 `<role>` 旧写法。F2 已有明确优先修订，不因此否定 F2 闭合。

本轮未发现需重新修复 F1/F2/F3 的项。未执行测试、红绿反证、静态检查或构建，故“静态闭合”不等于独立运行验证完成。

## 上下文来源

- 用户指定绝对任务 `H:\git\Multi-Workers\.agenticdoc\mw-model-fallback-cli\workers\review-fallback-cli-r2\task.md` 全文；原卡 `KEY/tasks/R-02-reverify-fixes.md` 全文。
- `.agenticdoc/_index.parallel` 确认本 key active/SPEC；`.agenticdoc/goal.md` 全文，锚定自有扩展面/文件证据/不改 watchdog。`KEY/pm-state.md` 不存在，与 mini 快路径背景一致；本轮不创建、不改变 phase。
- `KEY/spec.md`、`KEY/mini-spec.md`、R-01 evidence 报告全文，尤其原必须修复 F1-F3 与 D1-D4 原始措辞；判定没有把“PM 已全部处置”当独立证据。
- `PY/test_dispatch_models.py` 全文、`PY/README.md` 全文、`TS/.../shared/mw-runner.ts` 全文；完整 `cmd_model`/writer/CLI parser 作用域、`mw_common` validator/parser/loaders、TS splitter/model分支/注册总usage与完整相关 model 测试组。
- 流程参考 agentic-task/workflow-review、systematic-debugging、verification-before-completion；本轮为限定范围只读复评，不扩张成完整 design 审计。

## 未覆盖面声明

- 无 bash 工具，不执行 pytest/vitest/biome/tsgo/npm check；也未执行 PI_* 环境查询、detect_root/audit_phase、git status/diff。路径依据用户绝对路径及只读索引/goal/spec，未改写框架状态。
- 历史执行仅引用 `mini-spec.md:81` 的 Python 78 passed / TS `-t fallback` 7 passed；`:57-59` 是修复前 Python 两文件 104 passed、TS 199 passed/1 已登记基线失败、5 fallback passed 与旧静态检查。卡片称修复后全文 201 passed + 1，但当前 mini-spec 没有该记录，本轮未证实。不得称全套零失败。
- 不全面重审 R-01 已通过 Q1/Q3/Q4；仅检查修复面的 writer 数据保留、合法链顺序及 TS 薄转发不回归，不重新审查 launcher/watchdog。
- 不覆盖 pi 窗口实机交互、bundle 重建/安装与窗口重启；源码检索无残留不证明已安装 bundle 已更新。
- 不覆盖并发更新、文件锁、多读竞态、非原子 write_text 和 I/O 失败；继承 R-01 非本 key 风险，不把正常拒绝早返扩展为任何 I/O 情况的原子无变化保证。
- 本轮只写授权的 worker `report.md`，不写源码、测试、文档、索引、PM状态、其它 key 或 R-01 报告。报告具备五个恢复契约标题，归档目标路径因写面冲突尚未完成。
