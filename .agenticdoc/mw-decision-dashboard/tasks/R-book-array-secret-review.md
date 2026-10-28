# R T05d book秘密门复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec AC-005/design known-secret实际config/Authorization注入。
- `packages/multi-workers/decision_book.py:1010` _iter_secret_texts/_check_secrets/_check_context（函数定位）；`decision.py:559` credential_redactor。
- workers/dd-book-array-secret/report.md全文/evidence/runs/T05d-book-array-secret/RED7F2P/GREEN9/验收351/未修模拟探针，workers/dd-review-unified-input/report.md原P0。

## 审计目标
递归dict/list/tuple字符串值和键真正补数组漏扫，typed/flatten未改，路径/错误所有门known-secret不echo，不只secret scanner本身。原secret env/Bearer/sk识别与实际cfg/api_key/Authorization集合的区别：配置凭证非sk非Bearer且不在env时book能否携带并发送，给精确seam注入/API写面修复建议，不以未知secret边界豁免已配置known-secret。
未知context slot路径回显原键是否导致outcome/HTTP/证据秘密通道，定位最小修复。P0若仅数组遍历closed与整体known集合未闭分别判，不笼统PASS。
RED7/2先实现时序与GREEN351=342+9；probe是内存恢复未修门模拟，不是真实HTTP/ paid发送；browser-smoke卡实际上禁browser不是禁check子步，记录未跑不追认全子步。
P1empty规则等待用户确认，不修改/不全局放宽；ledger证据目录已授权PM吸收ack。

## 要求
完整必要源/测试分页读，PASS/CHANGES_REQUIRED，关闭表/新P0/P1/P2具体path:line/触发/最小owner续卡；只有自身report，无源/测试/服务/外网/build/真实凭证读取。静态旧日志非本人实测。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-book-secret/**`

## 写入禁止面
- 所有源/测试/任务相位/旧报告证据/真实档案/其他worker。

## 未覆盖面声明
真实Jev/HTTP/UI/平台/全仓check未验；P1待用户empty_is_value仅dp25确认。

## 交付格式
report≤120行，结论/关闭表/新finding/实际known集合缺口/证据偏差/未覆盖。
