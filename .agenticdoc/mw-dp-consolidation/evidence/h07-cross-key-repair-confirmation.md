# H07：跨key受限修复（已确认）

## 本轮问答

PM提出跨key修复先限定目标、文件和动作；授权内先DP判断，执行仍受claim及写面协调约束，越授权才具体问人。用户答“认可”。

## 已确认规则

- 项目级写面授权不等于任一Worker可自行修改其他key负责文件。
- PM送审前note说明跨key必要性、目标key/文件/具体动作、目标/验收/依赖/其他任务影响、已有授权依据、执行写面协调与验证方式。不能用开放式“允许跨key修复”代替明确方案。
- approve：方案/影响/授权明确，批准note限定的受限修复；不是已修改/已派发，也不自动扩角色或写面。
- steer：任务归属/拆分/执行主体需调整，由PM发起dp-pm-steer。
- need_fix：修复方案/影响评估/证据有具体缺口，由PM发起dp-auto补齐，不默认获实际跨key修改权限。
- reject：拒绝当前跨key修复，不自动放弃目标或关闭相关key；保持通用reject的获授权具体遗留方案边界，不额外授予关闭。
- 修改必须在已有授权允许范围内；新增写面或交付承诺变更须具体确认。
- claim、角色权限、独占写面及既有硬检查持续生效；approve不能夺其他窗口claim，不能允许两个Worker同时写同一文件。他窗live key读写限制及接管授权流程不被本项豁免。
- 实际派发明确执行者/受限写面；影响文件都在项目写面只是必要检查，不足以证明应该执行。

## 既有静态事实与未批准部分

autopilot-human-decision-inventory.md H07引用`packages/multi-workers/autopilot/conductor.py:5127`/`:5201`/`:5279`：当前xkey-authorize批准后派proposal，再受限apply；拒绝ticket rejected。仅复用已有静态证据，不宣称本轮动态路径或当前安装能力已验证。

具体授权绑定、proposal/执行写面、claim协调、计量、schema/状态/消费者留设计。本轮没有授予新跨key写面/外部路径权限、接管他窗、派proposal或修改目标key。

无源码/registry/配置/活gate/历史/服务或phase操作；完整SPEC/本key27AC及联合设计未批准。新增AC-026/027只属于mw-dp-consolidation，不与mw-decision-context独立26AC混同，不修改其验收或历史。

对齐`.agenticdoc/goal.md`：保留文件驱动协调、O_CREAT|O_EXCL锁、Worker进程/凭证隔离与角色工具限制；支持按模块并行，但同文件仅一个写者。
