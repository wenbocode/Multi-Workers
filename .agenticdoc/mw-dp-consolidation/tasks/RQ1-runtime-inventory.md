---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-runtime-inventory-20261024.md
---

# RQ1: DP运行能力盘点

## 上下文
目标锚点：`.agenticdoc/goal.md:5`。需求：`.agenticdoc/mw-dp-consolidation/spec.md`、`key-decision.md`。用户确认只保留dp1、dp2、dp3、dp25、dp15、dp7、dp6、dp20，退役其余17DP运行能力，历史只读。dp1/dp2/dp3/dp25业务设计不改。
入口证据：`packages/multi-workers/decide_registry.json:344`（dp6登记），`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:138`（工具DP集合，按符号复查漂移），`packages/multi-workers/decision_points.py`（DP_REGISTRY）。登记的wired/注释不等于真实运行可达性。
RQ1只回答运行盘点及删除范围，不设计四门的问题/选项（RQ2），不审计历史展示迁移（RQ3）。

## 要求
1. 枚举25DP在Python/TS注册、生成器、CLI/tool/producer、配置解析和提示词中的运行能力，归入保留8项或退役17项；区分自动触发、显式可调用、仅登记、未接线executor。
2. 给出实际调用入口与消费者的路径:行号和符号；标记生成表与源码可能不一致，无法证明的写未覆盖，不猜运行状态。
3. 给出精确候选删除面和下游依赖，不改文件；退役DP背后的安全规则仍保留，区分删除模型入口和删除守卫。
4. 点名框架或安装镜像需要另行授权的精确路径；禁止改pi核心。配置仅可读非秘密的DP结构，不访问凭证或个人agent配置。
5. 时间预算约15分钟；报告<=180行。限制扫描在相关源码/生成器/文档目录，排除node_modules/dist/内置Python；优先符号定点读取，禁止无界全仓dump。
6. 不运行测试、真实模型请求、mw serve、monitor、sign、build、install、commit；不调用ask_decision。不手工修改任何其他任务状态或phase。

## 交付格式
唯一研究证据含：结论、25DP分类表、运行入口与消费者证据、删除候选路径、授权风险、未覆盖面。每项结论带路径:行号+符号；提案和事实分开。先落盘简短骨架，再填证据；可用worker_file按本key的evidence相对路径落盘。最终回复只给摘要及证据路径，不能把盘点当实现。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-runtime-inventory-20261024.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/spec-runtime-inventory-20261024.md

## 写入禁止面
源码、registry和生成物、配置、framework、spec/design/plan/pm-state、其他RQ证据、生产ledger和历史记录禁止修改。除框架自动管理的自身worker产物外，不写其他路径。
