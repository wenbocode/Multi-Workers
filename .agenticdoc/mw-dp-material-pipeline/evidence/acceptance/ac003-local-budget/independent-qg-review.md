## 结论

独立复核通过：本批覆盖 18 组 AC/VC、39 项 QG 记录及 FLOW-001—003。AC-003 的 PM/Worker 正常入口均遵守同一 desc-local-v1 本地预算：1000 单位各发送一次，1001 单位与 11 句均发送零次；未发现需要修正的实质差异。

## 证据

已核对 review-inputs、冻结合同、PM/Worker normal-entry、v05 四段对比、T08 定向测试及当前源码指纹。`t08-pytest.log`：170 passed, 1 skipped。v0.5 对账为 36/36：32 项 justified-change，4 项 expected-rejection，0 项失败，0 项待证。1000/1001 样本分别由 999 个非 ASCII 码点、LF 与 3/4 个 ASCII 码点构成，计数结果与回执一致。

## AC/VC 逐项复核

| AC | VC | 状态 | 依据 |
| --- | --- | --- | --- |
| AC-001 | VC-001 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-002 | VC-002 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-003 | VC-003 | met | PM 与 Worker 正常入口均使用 desc-local-v1；1000 一次发送，1001 与第 11 句均零发送。 |
| AC-004 | VC-004 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-005 | VC-005 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-006 | VC-006 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-007 | VC-007 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-008 | VC-008 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-009 | VC-009 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-010 | VC-010 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-011 | VC-011 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-012 | VC-012 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-013 | VC-013 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-014 | VC-014 | met | 本批合同、源码指纹、36 项对账及当前定向结果一致；原独审剩余项可关闭。 |
| AC-015 | VC-015 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-016 | VC-016 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-017 | VC-017 | met | 本批回归及前次逐项复核见证据清单。 |
| AC-018 | VC-018 | met | 本批回归及前次逐项复核见证据清单。 |

## Quality Gate Report

| ID | Result | Evidence |
| --- | --- | --- |
| AC-001 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/qg-historical-menu-negative.json@2f6800a7c15720997e6dff242d8803bcb58f26dc0b76341d1a32d7434f9ff99c |
| AC-002 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/v05-four-stage-comparison.md@496da2992cff5b54adab488fa428b8f9c8e88110b8828c87d759c73271ae1047 |
| AC-003 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/pm/normal-entry.json@b809b408c42da7b8713ecd5ef7da8e8e2bec511065558fb7eac633728453db29 |
| AC-004 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/v05-four-stage-comparison.md@496da2992cff5b54adab488fa428b8f9c8e88110b8828c87d759c73271ae1047 |
| AC-005 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac005-rework/final-dp-w-type/normal-entry.json@91f8ceaefa4b778c94a4112a2b405d3336741529d2ede26ce373bcaa0874b24a |
| AC-006 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/supplements-v05-lineage/dp-QG/quality-gate-report.md@04590b1bacb6dc35cd9b878025bfcc4e0a1ff7302d8d50250ae81c0b6db34981 |
| AC-007 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| AC-008 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| AC-009 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/t08-pytest.log@98856edb61359406f0986919ad44fb789f529e41c1c3087c8639ace3da2c1058 |
| AC-010 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/v05-four-stage-comparison.md@496da2992cff5b54adab488fa428b8f9c8e88110b8828c87d759c73271ae1047 |
| AC-011 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| AC-012 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/v05-four-stage-comparison.md@496da2992cff5b54adab488fa428b8f9c8e88110b8828c87d759c73271ae1047 |
| AC-013 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| AC-014 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/evidence-index.json@e0aef786788f6f87b430d2cf18a6eff9ed11ebefcedf27b4d30e4dc9666326bd |
| AC-015 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| AC-016 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| AC-017 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/dp-auto-current-pm-handoff.json@6508643684b6b51ad181c1289fa00852f4cb4a21832b080af6d398c9f023f20b |
| AC-018 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| VC-001 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/v05-four-stage-comparison.md@496da2992cff5b54adab488fa428b8f9c8e88110b8828c87d759c73271ae1047 |
| VC-002 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/t08-pytest.log@98856edb61359406f0986919ad44fb789f529e41c1c3087c8639ace3da2c1058 |
| VC-003 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/worker/normal-entry.json@9bad839b2373ab49a5b170d01eb85e498269c167b3157336476b3cc531dc882a |
| VC-004 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/v05-four-stage-comparison.md@496da2992cff5b54adab488fa428b8f9c8e88110b8828c87d759c73271ae1047 |
| VC-005 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac005-rework/final-dp-w-check-task/normal-entry.json@d026ae13488e3048ee3f2a79b3f02959caf518c7003a0cbee287020ed42057ce |
| VC-006 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/supplements-v05-lineage/dp-QG/local-signoff-result.json@206c0e6ab7b641296d222fae2d5a52c2b37907c13122cccc13235db94940bedd |
| VC-007 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| VC-008 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| VC-009 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/t08-pytest.log@98856edb61359406f0986919ad44fb789f529e41c1c3087c8639ace3da2c1058 |
| VC-010 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/v05-four-stage-comparison.md@496da2992cff5b54adab488fa428b8f9c8e88110b8828c87d759c73271ae1047 |
| VC-011 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| VC-012 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/t08-pytest.log@98856edb61359406f0986919ad44fb789f529e41c1c3087c8639ace3da2c1058 |
| VC-013 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| VC-014 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/t08-pytest.log@98856edb61359406f0986919ad44fb789f529e41c1c3087c8639ace3da2c1058 |
| VC-015 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| VC-016 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| VC-017 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/v05-four-stage-comparison.md@496da2992cff5b54adab488fa428b8f9c8e88110b8828c87d759c73271ae1047 |
| VC-018 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md@5e76ba9c7798e376bce0a14b0c42bb3eb86d540cea7f6107759880968737a4ba |
| FLOW-001 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/pm/normal-entry.json@b809b408c42da7b8713ecd5ef7da8e8e2bec511065558fb7eac633728453db29 |
| FLOW-002 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/final-batch/entry-pm-transport-unknown/normal-entry.json@9232c0485bb689a4270264a7e43077c6a33b0dee0ec9a7225265756de6b9402c |
| FLOW-003 | PASS | .agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/supplements-v05-lineage/dp-QG/local-signoff-result.json@206c0e6ab7b641296d222fae2d5a52c2b37907c13122cccc13235db94940bedd |

## Achieved

- 八个 DP 共用发送前 desc 本地预算。PM 和 Worker 的 1000 单位各通过一次回环，1001 单位和 11 句各零发送。
- v0.5 九例四段核对共 36 项，32 项差异有据，4 项符合预期拒绝。旧 dp-auto 历史 PM 回执保持为空，本次接回有独立证据。
- T08 定向测试、静态检查与 T09 独立复核的证据见 evidence/acceptance/ac003-local-budget。

## 残留与未验证

整 key 的正式签收由宿主使用本次终态证据执行。本轮未调用外部模型进行 token 计量；正例为真实 POST 到本机回环。未执行正式 QG、sign 或源码修改。

## 上下文来源

原 T09、`.agenticdoc/mw-dp-material-pipeline/spec.md`、`design.md`、冻结合同、T08 源码索引、PM/Worker 两角色工具和传输记录、`v05-four-stage-comparison.md`、`t08-pytest.log`。

## 未覆盖面声明

本轮为固定本地预算。正例真实 POST 到本机回环，环境没有调用外部模型做 token 计量。历史参考及缺失的历史回执以冻结原件为准。
