# Research: 门禁形态综合定案（design）

## 决策问题
design 的拦截形态、放行语义、bash 范围、审计与测试策略——综合 W1（拦截能力）与 W2（P-002 先例+缺口）定案。

## 调研方法与出处
- W1 调研笔记：`evidence/research/w1-pi-extension-interception.md`（pi Extension API 拦截面，file:line 证据链）
- W2 调研笔记：`evidence/research/w2-p002-guard-precedent.md`（P-002 实现全读 + 六缺口 + 活体误报实证）
- spec：AC-001~006、§4 风险、§5 前馈（ue-toolchain 教训：测试必须在真实工具调用层）

## 发现（两份调研的交汇点）
- 拦截原语三重证实（W1 源码链 + W2 P-002 落地 + W2 活体探测）：`tool_call` → `{block, reason}`，spec §4 风险第一条关闭。
- W1 三层建议（write/edit 硬门 + bash 启发式 + 事后审计）与 W2 缺口清单交汇出一个冲突：bash 启发式按 P-002 现形态复用会产生实测误报（W2 worker 写文档被拦两次：payload 引用路径拼写+写结构词即触发）——门禁的 bash 侧必须收窄到"写结构的目标参数命中代码路径"，不能照搬"引用+任意写词"。
- 放行语义的关键约束（本综合新增，两份调研未覆盖）：worker 是独立进程，pid 与 PM 窗口的 claim 行不匹配——若按"当前窗口 host:pid 匹配"判定，所有被派发的 coding worker 会被误拦。必须给 worker 一条放行路径（PI_WORKER_TASK env），否则门禁破坏正常的 worker 派发流程。
- mini fast path 不能学 P-002 的两个豁免先例（no-override 不适用、shellPath 例外无审计）——框架 mini 路径本来就写 mini-spec.md，文件本身即审计痕迹，加新鲜度防陈旧豁免。

## 结论 → 决策映射
- 形态 → design D-1（三层，v1 落前两层+block 审计，事后扫描记遗留）
- 模块结构 → D-2（复用 P-002 骨架：shared/ 纯函数+register，index.ts 三模式注册）
- 放行语义 → D-3（三条件 OR：本窗口 claim / worker env / 新鲜 mini-spec）
- 代码路径定义 → D-4（packages/ 代码扩展名，排除 node_modules/dist/.tmp，路径规范化复用 P-002 工具链）
- bash 收窄 → D-5（只判写结构目标参数，payload 引用不触发；声明非沙箱）
- reason/审计 → D-6/D-7（GUARD_EXPLANATION 范式 + 全模式 block 审计，修 W2 缺口②）
- 测试 → D-8（harness+faux provider 走真实 tool_call 层，修 W2 缺口①）
- 部署 → D-9（build+重启声明，修 W2 缺口⑥）
- SKILL.md 触发词 → D-10（框架仓 push + diff-installed clean）
- 不做 → D-11（python 镜像接线、事后 bash 逃逸扫描、setActiveTools 变更）
