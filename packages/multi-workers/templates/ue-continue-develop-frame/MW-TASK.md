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
2. 写明需求落地后的设计与影响面；保存修改前baseline；核对实际调用者后再实现。
3. 在授权范围完成代码、DESIGN和catalog.json更新。运行catalog.py预览/--write/--check；有新增或变更确认项时交PM/用户审阅，不能自行批准。
4. `python agent/gates/regression.py --impact <IDs> --plan`核对；带baseline及必要宿主参数执行。普通开发不默认--full。
5. 只汇报摘要；失败按next分页展开，定位修复后重跑关联项。完整日志留在任务证据目录。

output.md须包含：最终行为与设计差异、实际修改文件、选集和选择依据、summary.json绝对路径、每项结果及未执行项、待人审定内容/阻塞。禁止把plan、目录生成或审批当成真实运行结果。
