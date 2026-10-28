# T10b monitor恢复门与契约修复

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；spec/design D-001/§9/VC-007。
- `packages/multi-workers/decision_monitor.py:704` recover_stale/:1905 ensure_instance/:1764 AttachedInstance.stop；`test_decision_monitor.py:143`（函数定位）。
- workers/dd-review-monitor/report.md全文：1P1+6P2；原T10报告和evidence完整读。T07b已交付复审中，T05已交付审查中，只有本卡monitor写者。

## 要求
先保存当前基线到本卡证据，新增行为测试在未修实现实跑正确RED，保存日志，再实现GREEN。修后mutant仅补测试有效性，不替代实现前RED。
P1：恢复三条件严格AND：对记录port实际连接得到ECONNREFUSED（Windows等价错误明确映射）+PID可证dead+锁内身份重检，才移动state/secret。timeout/权限未知/连接成功非本实例/端口无关占用均保留状态给guide；不得采review“非本实例也可恢复”建议，design未授权放宽。probe结果可注入但真实loopback refused测试必须有；记录安全观察不落token/正文。
P2锁纪律：recover_stale不允许裸调用，使用可验证start-lock guard或内置锁重构，避免state移后新secret误移；state/secret每步身份重检，失败保留余下材料，不误改新instance。默认ensure路径保持锁不死锁。
P2 stop：AttachedInstance.stop失败不得静默成功，抛或结构化stopped/detail，不误kill，T08契约明确。
P2耗尽：隔离本地100端口范围全部bind-and-hold后验证range-exhausted，所有占用者可用不误杀，别以单端口测试冒充100。环境端口被占时保持占用者并记录，不触共享服务。
P2嵌套book：明确provider必须check_book闭集/类型/enum/秘密检查，monitor对执行授权夹带提前拒绝且零provider调用；不能盲递归FORBIDDEN_KEYS误伤合法DP typed业务字段。完整读registry/book真实允许字段，若歧义报PM不改其owner源。
P2窗口：返回spawned/visibility=not-verified或明确文档ok只spawn，失败不假称已开窗；不启动真实浏览器。
P2证据更正另文件：原report1830/1267工件行数失准，按实际在档2090/1433与本次修改后数量分别记，原报告不覆写。保留skip POSIX0600非Windows用户隔离。
联合history稳定API复验（当前readact注入/marks），不越面改history。只隔离tmp localHTTP/argv模拟，无真实状态/浏览器/共享服务/付费/外网。

## 写入允许面
- `packages/multi-workers/decision_monitor.py`
- `packages/multi-workers/test_decision_monitor.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-monitor-fixes/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T10b-*`

## 写入禁止面
- 其他所有代码/测试/其他报告/任务相位/真实生产记录/凭证配置/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_monitor.py test_decision_history.py test_decision_roots_locks.py -q` 全输出/exit。
root 严格只读`npx biome check --error-on-warnings .`和其余check子步全输出，不能普通biome exit0当清零；完整npm run check若越禁止面则明确未整跑。禁build/npm test/全vitest/commit/外网。

## 改动历史
- PM吸收T10安全review，严格维持已确认三条件设计，不以dp决策更改用户需求；本卡唯一monitor写者。

## 交付格式
report逐finding修复/测试/剩余，实际基线RED及GREEN日志，API变化T08/T11/T12清单、更正文件、安全恢复观察细节；不自报reviewPASS/全AC完成。
