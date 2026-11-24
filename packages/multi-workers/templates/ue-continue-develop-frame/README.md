# UE 持续开发框架

将本目录整体复制到任意位置即可安装，不依赖SceneProfiler工作区、MCP、整仓注册表或MW运行时。适用于模块/插件局部上下文；内置UE AutomationTest适配器，普通脚本检查也可作为本模块gate。

在当前 MW 项目的 Pi 输入框运行（仅 dual 工作区）：

```text
/mw ue-continue-develop-frame install --module Plugins/MyPlugin
```

终端对应命令为 `mw ue-continue-develop-frame install --module Plugins/MyPlugin`，可用 `--project` 指定控制目录。`--module` 必须是 dual `Game/Plugins` 下已存在、含 `*.uplugin` 的插件目录；缺省或指向不存在/非插件目录时拒绝执行，且不创建任何文件。目标已安装（存在 `agent/`）时只做校验，不覆盖模块数据。

安装分两步：先复制框架并运行 `agent/gates/package_gate.py` 自检（目录复现、Ask 完整性、Python 协议测试）；再校验 terms/testcase/gates/DESIGN 是否针对该插件源码生成。未生成时输出缺口清单并以退出码 3 结束（**不算安装成功**），不再打印“完整规范包检查通过”。此时在 Pi 中会由当前 PM Agent 接手生成：按 `agent/GUIDE.md` 依据插件真实源码写 `agent/catalog.json`（术语/用例/门禁）与 `DESIGN.md`，再执行 `catalog.py --write/--check`、`gates/package_gate.py`，最后用 `mw ue-continue-develop-frame verify --module Plugins/MyPlugin` 复核；只有全部通过才显示成功、terms/testcase/gates 数量与人工审核入口 `agent/REVIEW.md`。日志保存在控制目录的 `.mw/ue-continue-develop-frame/`。

生成内容是草稿：条目保持 `proposed`，不得由安装或脚本冒充人工确认；正式 UE 回归仍需逐项确认。在模块内可随时重跑 `python agent/gates/package_gate.py`；若目录尚未生成，先运行 `python agent/catalog.py --write`。

Windows 若尚未注册终端命令，在 MW checkout 运行 `python packages/multi-workers/mw.py install-cli`，然后将 `.mw/bin` 加入 PATH。独立复制此模板时可以直接运行 `install.py --target <模块根目录> --name <名称>`。

纯Python模块可将source-root设为src；C++模块需安装package/agent/requirements-source.txt。可多次传source-root，但都必须在该模块目录内。安装拒绝覆盖已有agent目录，保留已有GOAL.md和DESIGN.md，向已有AGENTS.md追加本地入口。首次生成失败会保留草稿文件并报错，不把半成品报告为成功；修复依赖或源码后在目标模块运行agent/catalog.py --write即可。

## 安装后的结构

```text
模块根目录/
  AGENTS.md                 Agent/MW Worker入口
  GOAL.md                   level 0：真实模块目标
  DESIGN.md                 level 1：软件设计、Flow、AST引用和更新规则
  agent/
    GUIDE.md                开发及人审协议
    module.json             模块、源码范围、设计和UE环境配置
    catalog.json            术语选择器、测试语义、门禁策略的唯一编辑源
    terms.csv               从真实源码声明生成的术语目录
    testcase.csv            从真实UE注册核验并生成的用例目录
    gates.csv               策略及本模块执行脚本目录
    source_nodes.json       源码AST事实
    REVIEW.md               自动生成的逐项审阅摘要
    records.csv             人工决定与工程证据索引
    ask.py                  四级渐进式查询
    catalog.py              预览/生成/更新/检查目录
    module_config.py
    build_source_index.py
    gates/                  全部执行脚本均在agent内
      regression.py         影响面最小回归与摘要输出
      run.py                单项已确认门禁执行
      automation_gate.py    UE原生报告适配
      design_gate.py
      package_gate.py
    tests/                  模块内Python协议测试
    logs/                   工程记录、决定、更新备份
```

## 从草稿到可验收模块

1. 安装后先Ask level0/1。模板明确为draft，不能当作业务设计完成。
2. `python agent/catalog.py --discover > source-facts.json`；选择真实符号，填写catalog.json中的中文解释、已实现UE测试的目的/前置/动作/预期及gate关联。不得凭空造术语或未实现用例。
3. 填真实GOAL、DESIGN及Flow/状态图，关联[N:qualified]；完成后将module.json的design_status改为ready。
4. `python agent/catalog.py`预览差异，再`--write`生成三个CSV、AST和REVIEW.md；`--check`验证可复现。所有CSV为UTF-8 BOM。变更项自动待审，旧确认保留为历史，不自动批准。
5. 人确认REVIEW的具体项后按GUIDE保存逐项决定；再次生成以同步审阅状态。先plan最小选集，再运行并仅返回摘要；失败才分页展开。

“极简”是查询/执行策略，不是另一个缩水的测试定义。权威定义是catalog.json，查询目录是terms.csv、testcase.csv、gates.csv；某次选集及理由记录在那次summary.json。默认always加影响面关联conditional，显式--full才跑全部。

## MW接入

无需修改MW框架。派发卡引用目标模块根目录、安装后 `agent/MW-TASK.md` 中的工作协议与agent/GUIDE.md；Worker沿用key和授权范围，产出实际summary.json及output.md。模板不附带SceneProfiler的术语、业务测试、地图、审批或历史日志。

## 模板维护与边界

MW checkout 随 CLI 分发此模板。直接维护此目录下的模板和安装器，安装后的实例独立运行。模板源码不含绝对本机路径。已有实例升级前先比对运行时，不覆盖模块catalog、设计、决定与日志；本版installer仅处理新安装，不伪装成无损升级器。

目录生成仅理解实际源码声明与受支持的UE注册宏，不能推导测试意图或调用图完整影响面。AST不等同编译器类型分析；普通非UE测试用模块gate脚本接入。确认摘要绑定gate脚本和module.json，配置或脚本变更后重新审阅。

新增 UE 注册必须全部登记并覆盖关联影响面的门禁；G-DESIGN 要求 v2 修改前基线与本轮工程记录。agent/change_record.py 生成模块内记录及证据摘要并登记到 records.csv，命令见 GUIDE。记录不自动批准用例或门禁。
