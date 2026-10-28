# R T05p redactor安全契约复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358完整known安全。
- `packages/multi-workers/decision.py:965` known工厂；`:1960` caller-owned覆盖校验（函数定位）。
- 全读workers/dd-redactor-contract/report.md与evidence/runs/T05p-redactor-contract，tasks/T05p-redactor-contract.md。
- F-R1此前仅评低风险误用，现RED实证stored_legacy=True，PM不接受误用免责。编码已终态，无新写者。

## 审计目标
None-base三API TypeError、capture None、gate fail_closed正确，不隐式放行。client-only production caller-owned完整known校验在采集和POST前，回调不替换，发现一次、retry复用、下call刷新、无scope0额外auth。
_redactor_covers仅hits或文本变化是否足够证明完整secret不残留：回调返回hits>0但原值仍在、添加前缀仅变化、部分替换、裁剪/异常/无scrub_tail_prefix等边界。若存在raw残留用明确代码触发说明，不以第三方误用免责。任意metadata键值和失败输出同安全要求；KnownSecretRedactor非wire-compatible传入是否failclosed还是绕过。
caller生产scope覆盖收紧是否误拒合法过滤器、test scope既有omit/自定义边界不退化、ContextVar reset/跨cfg union/合法工厂pin/缺凭证disabled预算0/sink故障best-effort保持。未知redactor不可根据hits就假证完整脱敏。
RED3F2P真实实现前墙钟与hash查trace，red01测试自身修正不冒充代码RED；78两轮8文件argv/cwd/UTC/exit/依赖hash与1301邻接实核，完整check未跑不等价。fixture完整env后缀清理/auth读前spy/隔离loopback。

## 要求
PASS或CHANGES_REQUIRED、原缺口关闭表、新finding严重度与具体path:line和最小owner面、准确验证和未覆盖。仅自身report，不源测试，不运行外网服务build，不读真实凭证；纯静态旧日志非本人实跑，hash未重算须声明。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-redactor-contract/**`

## 写入禁止面
所有源测试、任务相位、旧报告证据、真实凭证生产、其他worker。

## 未覆盖面声明
真实Jev、平台、并发、全仓check、dispatch迁移未验或未关。

## 交付格式
worker_file 写report.md，最多130行，关闭表、覆盖判定安全边界、证据、下一最小卡、未覆盖。
