# QG pass 资格验收

## 系统行为变化

共享准备在渲染候选前读取当前范围的真实独审事实。已知缺独审的 pass 不进入正式问题；没有其他可用候选时只返回 PM 补独审的下一步。合法 fix/reopen 继续按其证据准备。已有独审的快照绑定审阅记录，发送后继续核查证据新鲜度。

## 验收证据

Codex PM 自验 86 项通过。真实记录形态的测试覆盖 pass、发送前变动零发送和发送途中变动零业务动作。SceneProfiler 组合样本覆盖缺独审、旧快照、撤销认领均零发送，以及另有合法 reopen 时只发送一次。 [验收记录](evidence/codex-pm/self/1795453808385846200-16lrktqq/result.json)

## 遗留

扩展回归的签收正控和 Windows writer 文件替换仍需单独核对。候选发布和实窗复验归 mw-dp-window-acceptance。
