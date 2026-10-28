# T14 vision — identify screenshot log blocks

type: vision

## 上下文
Goal: .agenticdoc/goal.md. User explicitly requests vision-model inspection of two screenshots and removal of the two log-like blocks from default DP test UI. References: packages/multi-workers/decision_dashboard.html:145 (operation feedback), packages/multi-workers/decision_dashboard.js:1708 (submit output). Images: .agenticdoc/mw-decision-context/evidence/Vision/Monitor-DP-Test1.png and .agenticdoc/mw-decision-context/evidence/Vision/Monitor-DP-Test2.png.

## 要求
Read both images with image tools. Identify exactly which visible sections are log-like, quote their headings and characteristic fields, map them to shipped HTML/JS functions using read-only source. Recommend minimal default-display removal preserving DAG, selected-node detail, concise button/result/error feedback and read-only polling. Do not implement. No model/provider validation, shared service/browser/build/install/commit/config/framework operation. Only the screenshot analysis is authorized.

## 交付格式
Write concise findings to the unique evidence file below: each image visible heading/fields, source mapping, minimal proposal, uncertain parts. Distinguish screenshot facts from recommendations.

## 审计目标
Both provided screenshot log-like sections and corresponding default renderer.
## 未覆盖面声明
No real-browser/runtime acceptance; no implementation or production calls.
## 唯一证据文件
.agenticdoc/mw-decision-context/evidence/research/vision-log-blocks-20261023.md
