# MW Worker任务卡片段

- Key：<沿用PM派发key>
- 对应AC：<验收标准编号>
- 目标模块绝对路径：<module_root>
- 需求与预期行为：<明确输入/输出和边界>
- 可改文件：<相对模块路径白名单>
- 已有设计/已知影响面：<DESIGN章节、精确术语ID、相关调用者>
- 现有证据/依赖：<路径；不要复制长日志>
- UE参数（如选中UE用例）：<editor、隔离project、scene-project、对应DLL构建证据>
- 修改前baseline：<本任务新证据路径>

执行协议：

1. 沿用本key；读取模块AGENTS.md与agent/GUIDE.md；Ask0→1理解目标和设计，Ask2定位术语/用例/门禁，需要历史才Ask3。
2. 保存修改前 baseline，推演设计与影响面，核对实际调用者后再实现。
3. 实现后用 `python agent/gates/design_gate.py --refresh-plan --baseline <baseline.json>` 获取变更路径，按实际实现刷新 DESIGN 与受影响的 catalog.json，再用 catalog.py 预览并生成目录。
4. 登记本轮工程记录，运行 `python agent/gates/package_gate.py --baseline <baseline.json>`。新增或变更的确认项交 PM 或用户审阅。
5. `python agent/gates/regression.py --impact <IDs> --plan` 核对选集，带 baseline 及必要宿主参数执行。失败按 next 分页展开，修复后重跑关联项。完整日志留在任务证据目录。

output.md 记录最终行为与设计差异、实际修改文件、事后设计校验结果、回归选集和依据、summary.json 绝对路径、实际结果和未执行项，以及待审内容。
