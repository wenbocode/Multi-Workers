# R T05 observation seam独立审查

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec/design/evidence-requirement全文。
- `packages/multi-workers/decision_points.py:1` 全文（约4200行）；`decision_book.py:362` check_book/scaffold（函数定位），`decide_archive.py:1`；T05卡、workers/dd-observation-seam/report.md、evidence/runs/T05-observation-seam/verify-summary.md与实际日志。
- 原run_id 05:03:45.433Z已done exit0；混入的子run失败不能混判。T07b已交付正在复审，T10正在独立review。

## 审计目标
全文读points和新30测试、依赖client/store/book/archive实际API。观察成对intent=answer/archive=False/test scope/显式evidence_path且零executor，越DP disabled/P0但全局disabled/未配置/缺凭证/typed非法/预算仍零发送。重点核查report说seam只检查必填/预算，check_book由T06负责：直接内部observation在错类型/enum/未知业务键时是否可发送？不能把公开内部安全契约仅推给页面producer；合法book与实际state/evidence/candidate一致，必填不能静默裁，book秘密字段校验。
每decide新scope+真实secret集合新鲜、调用thread ContextVar reset/显式client scope是否覆盖ambient导致串生产、production root resolver/双根错归属、book/input-state/rendered candidate真实当次快照与ID join、结构豁免字段可信校验、脱敏安全剪裁长secret、冻结dict/outcome新增是否真消费、archive异常原样重抛/created-replayed-skipped准确。
module-unavailable观察拒绝/生产结果不变且capture failure显式；preflight零请求无伪成功。capture_scope创建新生产旁账是否影响原collect/archive/signoff字节契约，实际只tmp fixture无真实授权。preview是纯授权预测不冒称执行成功；policy未写保留闭集硬条款。
RED29缺API与GREEN30/36/873真实核查；mutant能证明哪些边界，缺实HTTP/Jev严格未验证。全包11失败不因无直接import自动判无关，monitor/dispatch属于本key迁移债，归因需证据不足则待核实，不要求重跑全包。

## 要求
PASS/CHANGES_REQUIRED，精确P0/P1/P2/AC-VC/触发/后果/最小修复。只读，不源/测试写、不外网/build/模型/服务；无shell明示静态旧日志。

## 未覆盖面声明
真实Jev/页面/TS消费/collect hash/T06/T11未交付，不声称全AC；不审T07b/T10在产。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-observation/**`

## 写入禁止面
- 所有源/测试/生产记录/任务相位/其他worker。

## 交付格式
report≤180行，结论/Findings/证据/下游风险与未覆盖/上下文；摘要≤30行。
