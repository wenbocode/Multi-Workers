# 模块开发指引

全部路径相对当前模块根目录；无整仓注册入口。Python 3.9+；存在C++源码时先安装 `python -m pip install -r agent/requirements-source.txt`。普通Ask和门禁调度仅用标准库，目录重建对C++使用tree-sitter，对Python使用stdlib AST。

## 渐进式披露

```text
python agent/ask.py --level 0
python agent/ask.py --level 1 --ref T-...
python agent/ask.py --level 2 --query <真实符号或说明>
python agent/ask.py --level 3 --ref <记录ID>
```

0=模块目标，1=设计，二者返回精确术语；2=模糊术语搜索与相关testcase/gates；3=工程记录及分页日志。根据next继续，不先扫整个仓库。必要时沿源码调用者核对影响面。

## 单一事实来源与目录更新

- `agent/module.json`：模块名、源码目录、设计章节、UE插件和用例运行前置参数。UE适配器可省略plugin描述符，直接使用项目已编译模块。其它测试工具可通过本模块自有脚本门禁接入。
- `agent/catalog.json`：人工设计元数据：术语的真实源码选择器与解释、已实现UE测试的目的/前置/动作/预期、gate策略与影响面关联。不能从AST自动推断测试目的和门禁策略。
- `agent/terms.csv`、`agent/testcase.csv`、`agent/gates.csv`：脚本生成的可搜索目录；不手工双写。`testcases`仍是JSON数据/API分类名，磁盘文件统一单数`testcase.csv`。
- `agent/source_nodes.json`：源码AST；`agent/records.csv`索引人工决定及工程证据。

```text
python agent/catalog.py --discover > <证据目录>/source-facts.json
python agent/catalog.py
python agent/catalog.py --write
python agent/catalog.py --check
```

discover仅列真实源码符号和已注册的UE AutomationTest，供选择；默认命令只预览差异。write同时更新三个CSV、AST和REVIEW.md，UTF-8 BOM保留中文，备份放agent/logs/catalog-updates。不存在的符号/注册/脚本报错，失败恢复原文件；已移除ID须先处理设计和records引用，再显式--allow-remove。check不写文件，发现漂移退出非零。

目录生成不会批准条目。仅与已有人工决定的内容、实现摘要完全匹配才保留accepted，其它为proposed。每项决定的category、item_id、decision、item_sha256、confirmed_by、confirmed_at、source_ref保存在logs/decisions JSON，由records.csv的human_decision引用。摘要用ask.item_digest(该项所有行,模块根目录)计算；gate摘要同时包含module.json。人确认具体版本后才记录原话、时间与摘要，不以模板安装或脚本执行冒充确认。

## 设计与最小回归

```text
python agent/gates/design_gate.py --snapshot <修改前的新baseline.json>
python agent/gates/regression.py --impact T-... --plan
python agent/gates/regression.py --impact T-... --baseline <baseline.json> --report-root <证据目录>
```

在DESIGN写明新行为、影响面、流程图及[N:qualified]节点，再落实源码。模板默认draft，必须完成真实业务设计再改为ready。影响面由Agent根据设计和调用者核对；执行选always加所有关联conditional并去重，不另存一份“极简测试集”。未指定/未知术语拒绝执行。脚本只运行已确认门禁。新模块没有业务用例时，基础门禁通过不代表业务覆盖充分，必须补已实现的测试及人审判据。

UE测试另传--editor与--project；配置profile=scene的用例传--scene-project，map由module.json配置。用例排序需遵守fixture依赖；脚本门禁先执行，其余保留catalog.json中的顺序；有依赖的用例须按执行顺序列出。源码、DLL、地图和RHI需满足testcase前置条件，不因极简输出放宽。

stdout只返回摘要；summary.json保存选集理由、命令、退出码、时长及完整日志。首个失败退出非零，后续标记not_run。失败后用 `--details <summary.json> --gate <G-ID>` 分页；`--stream editor`读原生日志，默认4000字节，上限8000，next_offset继续。全量仅显式 `--full`（可先--plan），用于用户要求、发布验收或无法界定影响面；最小回归通过不等于全量通过。

## MW Worker交付

PM派发时给出模块绝对路径、任务key、需求/AC、可改范围、已知影响面、baseline与宿主参数。Worker先Ask0/1推演设计，Ask2核对选集，必要时Ask3；沿用任务key，不创建PM文档。只在授权模块内修改，生成/更新目录并保留待审状态；output.md写实际行为变化、选集、摘要路径、失败/未执行项及待人审事项。参见模板根目录MW-TASK.md。

### 新测试与工程记录完整性

catalog.py 双向核对源码 UE 注册与目录：源码新增注册未登记即失败，每个 testcase 的每个影响术语必须有 always 或同术语 gate 覆盖。保持新增条目 proposed，逐项确认后才正式回归。

修改前 design_gate.py --snapshot 保存 v2 基线，包括源码、设计、规范运行时与目录定义摘要、已有记录摘要。发生变更后必须新增或更新 development 记录，绑定该基线与当前输入。已有历史记录、旧源码摘要或被改动的证据文件不能通过 G-DESIGN。记录只证明可追溯性，validation 必须如实标明待确认/开发自测/正式结果，不能代替 UE 验证。

完成最后一批编辑后运行：
```powershell
python agent/change_record.py --baseline <修改前baseline.json> --id R-唯一标识 --term T-受影响术语 --summary "实际设计与影响" --validation "待人工确认，尚未正式回归" --artifact agent/logs/实际证据.json
```
记录及证据必须在模块内，Ask level 3 可检索。正式回放后追加实际结果记录；之后再改输入必须重新绑定。旧版本基线无记录快照时拒绝正式校验，不得伪称事后快照为修改前证据；迁移期保留旧基线并说明升级时点。
