<!-- module-agent:start -->
## 本模块的 Agent 开发协议

仅使用本模块根目录上下文，先读 `agent/GUIDE.md`。通过 `agent/ask.py` 依次读取目标（level 0）、设计（1）、术语及testcase/gates（2），需要时才查工程日志（3）。术语必须来自源码AST，设计包含流程图与源码节点引用。

修改前保存 `agent/gates/design_gate.py --snapshot <新证据文件>`。推演新设计与影响面后再实现；更新DESIGN、catalog.json，执行 `agent/catalog.py --write`。默认用 `agent/gates/regression.py --impact T-... --plan` 核对选集，再传baseline及运行参数执行。成功只报摘要，失败分页展开；全量仅显式--full。未确认的新/变更门禁由人审定，不伪造批准。

## 版本控制边界（框架自身不入库）

框架的安装产物只作为本地开发与审核上下文，不属于模块交付。根目录的 `AGENTS.md`、`GOAL.md`、`DESIGN.md` 三个文档，以及 `agent/` 目录（含脚本、CSV、生成物、决定与日志）一律**不进 CL、不提交**：Perforce 不将这些路径 add 到任何 changelist，Git 不对它们执行 `git add`/commit。不要把目录生成物、术语/用例/门禁 CSV 或本地证据混入模块提交；若某个设计决定确需入库，由人单独决定并在框架目录之外保存可提交文件。模块自身的源码、资产和构建配置仍按项目原有版本控制流程处理。

MW Worker沿用任务卡的key、修改范围和目标工作区；在模块目录使用同一工具链，将summary.json路径和实际结果写入output.md。不得创建第二个PM流程，也不得将模板draft或未执行项描述为通过。父目录的授权和协作约定继续适用。
<!-- module-agent:end -->
