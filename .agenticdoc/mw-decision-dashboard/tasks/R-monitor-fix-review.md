# R T10b monitor修复独立复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec/design D-001/VC-007/§9。
- `packages/multi-workers/decision_monitor.py:1` recover_stale/StartLockGuard/probe_recorded_port/AttachedInstance.stop/_smuggled_book_paths；test_decision_monitor全文。
- workers/dd-review-monitor/report.md原1P1/6P2，workers/dd-monitor-fixes/report.md全文与evidence/runs/T10b-monitor-fixes/verify-summary.md/RED/GREEN/probe/依赖快照/更正。

## 审计目标
逐原1P1/6P2关闭表；恢复严格refused+dead+锁内重检AND，不允许non-instance响应替代refused。guard真实性/根绑定/owner-start校验/失锁裸调用/每步身份重检，state移后secret inode/size/mtime是否足以防新材料误移，异常保留/guide/零kill。
stop仅端口refused是否足以证明原实例stop，错误control响应/无关listener/竞态不得成功假报；合法停止延迟失败诚实。
嵌套book registry路径白名单是否因object子树过宽放行危险键、合法dp12 command/dp24 path不误伤，unknown dp零provider，validate与submit差异明示；T06 check_book仅义务常量不当已执行。不得越面改book/points。
真100端口block耗尽未kill、测试skip实际、Windows10061/timeout classification保守；spawned/visibility API所有现有调用方迁移登记，不当真窗口。
真实基线RED16先于实现与GREEN137+skip（并行history快照）核对，52monitor+skip；报告1865 vs summary1863行数不一致查在档定位而非自造。biome exit1/3w2i，分步不是完整check。
T07c当前输出marks/filters/capture接口接缝只读核对，不判整个historyPASS。

## 要求
完整必要源/test读，结论PASS/CHANGES_REQUIRED，精确path:line/触发/严重性/最小修复/证据。仅自身report，禁源/测试/服务/生产/凭证/外网/build/模型命令。不运行命令须声明静态+旧日志不是本人实测。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-monitor-fixes/**`

## 写入禁止面
- 所有源/测试/任务相位/其他worker/真实生产档案。

## 未覆盖面声明
真实浏览器/崩溃/TIME_WAIT/ACL/Linux/macOS/真实Jev/T06接线/全仓check未验，独立代码review不等价AC达成。

## 交付格式
report≤150行，逐finding关闭表/新项/证据偏差/API残留/未覆盖，摘要≤25行。
