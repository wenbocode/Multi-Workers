# Research: 八DP真实派发与业务后继样例缺口

## 决策问题

用户反馈当前设计缺少所有DP包含真实派发结果的样例用于验收和对比，补spec AC-015—018、design D-007及T10/T11；本轮仍仅规划。

## 出处与方法

用户2026-11-19本轮反馈；本key docs完整请求/返回附录、captures各DP的result/reference快照、spec/design/plan和T08/T09。没有外部调研、没有触发任何真实调用/派发。

## 发现

旧包明确为synthetic-reference的真实HTTP实验，无正式原主体运行绑定，业务效果false、host检查未执行；只证明相应body/响应/静态映射，缺真实派发/Worker终态/output/PM回收与正式writer链。离线真实代码+faux同样不能冒充当前构建真实jev闭环。

## 决策映射

- AC-015/T11：每DP至少1正式运行闭环；真实派发/输出/PM回收或该分支业务回执须可回溯正式账本，不能强造无意义Worker。
- AC-016/T10/T11：八份逐项对比，同事实/事实变化/历史未配对分开，不以confidence提升验收。
- AC-017/T10/T08：固定28业务候选+auto路径+八DP边界由确定性离线生产链覆盖，不为真实模型刷齐choice。
- AC-018/T11/T09：后续原PM授权与原预算成立后才采集，保留失败/未完成；本轮0/8、全not-collected，不拿旧HTTP包补绿。
