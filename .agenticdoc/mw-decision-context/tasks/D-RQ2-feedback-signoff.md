# D-RQ2 自动反馈与直接签收

type: research

## 上下文
目标 `.agenticdoc/goal.md:1`；锁定spec `.agenticdoc/mw-decision-context/spec.md` AC008–010/012–014/019–020；本keySPEC证据和旧dashboard安全债。
种子 `packages/multi-workers/decide_signoff.py:340` signoff_state/collect/verdict，行号漂移按符号定位；读mw-signoff-decide-only当前DONE的spec/design/achieved及实际签收代码。decision_wire_store.py/decision_history.py、decision.py、decision-tool.ts、PM/worker消费函数。

## 要求
仅只读研究，无源码修改、测试、服务起停、安装、浏览器、真实Jev或真实凭证读取。
1. 提出精确decision/key/task/发起角色关联与自动接收/行动/结果写回的最小事件协议，writer/reader、接收不等行动、四状态派生、旧数据无DAG、重试/幂等/失败记录点。至少2方案比较，不造中心调度或大schema。
2. 四DP每个真实结果消费者和反馈位置（输入契约归RQ1）；dp2/dp3不扩大权限；dp25可以收尾直接签收无需PM二批。
3. 核实签收现行硬门，提出调用前必需门枚举与签收原子幂等、写失败/phase门禁集成；不把本地旧verdict做完交付判断又请Jev复述。
4. 新记录公开路径与known-secret安全、symlink/父目录/读时处理的必要边界，仅本功能涉及面；不能hash/id当安全证明，不展开旧key全部债。
给字段writer/reader/无写者行为表和生产创建路径验收建议；当前事实与建议分列，不捏造已测试结论。
≤200行，大文件分页，read≤120行，命令stdout≤30行，不反复全dump大文件。

## 唯一证据文件
.agenticdoc/mw-decision-context/evidence/research/design-feedback-signoff-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-context/evidence/research/design-feedback-signoff-20261022.md`

## 写入禁止面
源码/配置/凭证/其它key/spec/design/plan文档；自身report.md可按框架记录。

## 交付格式
证据含研究问题/出处路径行号+符号/事实/两方案pros-cons/推荐/接口事件草案/硬门清单/状态映射/失败与幂等/待决。PM串行写design.md，不由worker写。
worker_file的file传上述evidence相对路径，回执传basename report.md，禁止绝对file参数，≤64KiB。
