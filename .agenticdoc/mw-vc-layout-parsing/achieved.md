# VC 文档布局验收

## 系统行为变化

VC 解析可以识别已有的单行和分行布局。等价内容保留相同的断言、层级、输出和来源身份。缺字段、重复编号和冲突布局仍拒绝，材料诊断指明设计文件、VC、行号及原因。

## 验收证据

Codex PM 自验 67 项。Gaze 八条单行 VC、Render 六条多行 VC 均解析，多层值保留。等价写法及标点、缺 Output/Source、重复 ID 和原始工具回放同时覆盖。完整 npm 检查在隔离源码副本通过。 [验收记录](evidence/codex-pm/self/1795454020291243200-7gpmz3cl/result.json) [npm 检查](evidence/npm-check.log)

## 遗留

Gaze 原始材料还有术语问题，Render 仍须补相应的 finding 或独审。全局发布与实窗复验归 mw-dp-window-acceptance。
