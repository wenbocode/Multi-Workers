---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/design-cli-reachability-20261026.md
---
# RQ22 — 完整CLI运行入口与退役/签收职责补核

## 上下文
`.agenticdoc/goal.md:5`；`.agenticdoc/mw-dp-consolidation/spec.md:34`，53AC已锁、当前DESIGN。RQ13/17只读部分mw.py，完整CLI活跃旧ID/caller/签收及dp apply权限配置差异未核。用户继续授权联合设计研究，不授权删命令/功能、配置变更/实际签收或实施。

## 要求
1. 25分钟，只读全文 `packages/multi-workers/mw.py:1`，用read分段续读至实际EOF。文件大，避免重复读旧研究，控制报告体积；如无法全文明确未读范围，不用rg片段宣称完成。相关主要源仅采用已完整读或声明未覆盖，不读活配置/gate/ledger/签收/凭证及其他key运行材料，不执行CLI/测试/服务/provider/裁决探针。
2. 核CLI parser→dispatch/show/export/book/case/answer/receipt/sign/apply/auto等实际入口、旧ID枚举/默认/帮助/探针、请求与执行器边界。区分活动调用、不可调用退役解释、测试/历史字面值；旧ID错误不能通过隐式映射重新调新DP。找齐本文件生产caller，其他文件调用链只作未覆盖线索。
3. 核同次sign-key判断→result/file→反馈、retry-write真实证据重用、适用范围、finalize词表、关联/证据实质变化；至少两种合法适配方案与pros/cons/推荐。历史旧标签可只读解释，但不得代当前有效finalize，不提供旧运行兼容。
4. 特别核dp apply/promote/demote/authority-change旧配置功能和签收目标职责区别；不能为统一词表把finalize自动接到旧权力变更执行器。若建议删除看似有意功能，明确列待用户单独批准，不实施；原安全/角色/claim/锁/预算/凭证防护不因退役消失。
5. 给候选精确文件/函数/帮助或生成接口及AC001～004、009、012～014、038～043、049～052的正反/非法旧ID0模型0业务/关联重放/失败审计断言。所有CLI行为是静态推断，禁止实测宣称；source!=安装内存身份，不冒充全仓caller审计。

## 交付格式
worker_file只写唯一证据并read回核；证据/最终回复分别有独立 `## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源` 标题。最终证据节引用完整 `.agenticdoc/mw-dp-consolidation/evidence/research/design-cli-reachability-20261026.md` 及key内 `evidence/research/design-cli-reachability-20261026.md`。不写虚假VERIFY、测试、设计/AC/QG/签收成功。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/design-cli-reachability-20261026.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/design-cli-reachability-20261026.md

## 写入禁止面
其余所有文件；不人工修改框架回执，不建report.md。禁源码/配置/历史/服务/旧研究改动。源码用read，PowerShell不用&&；禁测试/build/install/commit。
