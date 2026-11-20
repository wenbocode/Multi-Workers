<!-- module-agent:start -->
## 本模块的 Agent 开发协议

仅使用本模块根目录上下文，先读 `agent/GUIDE.md`。通过 `agent/ask.py` 依次读取目标（level 0）、设计（1）、术语及testcase/gates（2），需要时才查工程日志（3）。术语必须来自源码AST，设计包含流程图与源码节点引用。

修改前保存 `agent/gates/design_gate.py --snapshot <新证据文件>`。推演新设计与影响面后再实现；更新DESIGN、catalog.json，执行 `agent/catalog.py --write`。默认用 `agent/gates/regression.py --impact T-... --plan` 核对选集，再传baseline及运行参数执行。成功只报摘要，失败分页展开；全量仅显式--full。未确认的新/变更门禁由人审定，不伪造批准。

MW Worker沿用任务卡的key、修改范围和目标工作区；在模块目录使用同一工具链，将summary.json路径和实际结果写入output.md。不得创建第二个PM流程，也不得将模板draft或未执行项描述为通过。父目录的授权和协作约定继续适用。
<!-- module-agent:end -->
