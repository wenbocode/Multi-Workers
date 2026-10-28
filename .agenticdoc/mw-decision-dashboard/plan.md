# Plan: mw-decision-dashboard

> Phase PLAN。设计独立复审PASS；本文件只规划，不授权绕过TASKS/EXECUTE门禁。代码未开始、验证未执行。

## 输入与目标
- spec.md：17条AC，原文指纹728632b37572。
- design.md：18条VC、Function Flow/覆盖矩阵；evidence-requirement.md为闭环证据要求。
- review：workers/dd-review-spec-design/report.md 初审CHANGES_REQUIRED；workers/dd-review-followup/report.md复审PASS，8/8 closed。
- 交付：窗口只读dp入口、独立本地应用窗口历史/DP测试、真实传输与消费/人工来源记录、全25DP typed输入、生产签收隔离。

## 并行性分析与单写者
- 先基础协议，再接线，再整合。每张编码卡约30min–2h；同源文件任务只能串行，阶段可按DAG交叠。
- decision_points.py与decision_book.py同一owner串行完成registry与观察；decision.py/backend由wire owner；mw.py所有新命令由CLI owner；ui-bridge.ts入口与消费接线同一TS owner。
- 新独立模块可并行：wire存储、history只读、monitor服务/资源。共享协议由PM先冻结，并在各卡引用同一schema，不允许各自改字段。
- 当前git已有其他会话ui-bridge.ts/README/test/dist改动；实施前登记基线/认领具体写面，未经协调不覆盖。禁止回滚、全文件覆盖或提交其他会话文件。
- 根helper与锁扩展影响mw_common.py，专属基础卡；不改既有默认锁语义或移除功能，只为新路径显式deadline。

## 阶段与候选任务DAG
### S1 基础协议与记录存储
目标：可验证的根/锁/scope/旁账，生产签收不受影响。
| Task | 产出/允许主写面 | 依赖 | AC / VC |
|---|---|---|---|
| T01 | 共享control根fail-closed、deadline/owner身份锁辅助；mw_common.py + 专属测试 | 无 | AC-007/008/015；VC-007/017/018 |
| T02 | decision_wire.py：schema/scope/脱敏/限长/短写/读取警告及专属测试 | T01 | AC-005/008/012/016；VC-005/008/012/016/017 |
| T03 | backend/client实际捕获；decision_backends.py/decision.py + wire真实HTTP测试 | T02 | AC-003/005/012/016；VC-003/005/012/016/017 |
验证：本地HTTP原bytes/HTTPError/Retry-After/client重试、非env secret、UTF8坏字节、写失败/锁超时，probe无call上下文零写；不得外网。

### S2 全DP输入与仅观察调用
目标：25DP契约闭集、镜像一致、内部真实链无executor/生产旁账写。
| Task | 产出/允许主写面 | 依赖 | AC / VC |
|---|---|---|---|
| T04 | typed required/optional per-field registry；points/book/generator/两处生成物/契约测试 | T01 | AC-009/011；VC-009 |
| T05 | points观察seam/共享纯预览/归档观测/book及candidate快照；观察测试 | T03,T04 | AC-003/004/008/010/011；VC-003/004/008/010/011 |
| T06 | decision_playground.py：显式test scope/evidence_path、submit去重/start/结果/重试 | T05 | AC-004/008/010/011/012/017；VC-004/008/010/011/012/015 |
T04/T05同owner依次写points/book，不能并行；迁移现有身份态测试而非放宽门。逐字段数组元素界，dp17完整17AC与signed delta测试，state2000B总预算独立。

### S3 历史与生产来源/消费接线
目标：人工与system/model真实写者、显式call/decision/response关联，历史缺失诚实。
| Task | 产出/允许主写面 | 依赖 | AC / VC |
|---|---|---|---|
| T07 | decision_history.py：旧档案+新wire/lifecycle+sign/gate读侧、跨key筛选/分页/缺失 | T02协议；最终T08/T09 | AC-002/003/012/013/014；VC-002/003/013/018 |
| T08 | Python CLI monitor/record/event/book上下文与sign元事件；mw.py/decide_signoff.py及CLI测试 | T05；monitor部分T10 | AC-003/007/014/017；VC-003/007/014/018 |
| T09 | TS origin/call ID/根与adopt/consume/steered/respond关联；pm/worker/triage/decision-tool + faux测试 | T08 | AC-003/012/014；VC-003/012/014/018 |
T08由单CLI owner分子步骤，先record/event协议再monitor接线。T09消费真动作成功点发system event；不以最近调用猜响应，task头/steer入队不冒充agent已读。人工记录不被旧fold/report/collect/verdict消费。

### S4 安全monitor与应用窗口
目标：独立进程、角色认证、静态两页签、显式调用、崩溃恢复。
| Task | 产出/允许主写面 | 依赖 | AC / VC |
|---|---|---|---|
| T10 | decision_monitor.py：启动锁/身份/高位独占绑定/health/boot token/HTTP/stop/恢复测试 | T01,T02；路由整合T06/T07 | AC-006/007/015/017；VC-006/007/015/018 |
| T11 | decision_dashboard.html/js/css：安全DOM、两页签、契约表单/详情/显式提交 | T06,T07,T10 | AC-002/003/004/005/006/011/013；VC-002/003/004/005/006/011/013/015 |
| T12 | 窗口只读dp/monitor薄入口；ui-bridge.ts/mw-runner.ts与专项faux测试 | T08,T10,T09同文件owner结束 | AC-001/006/017；VC-001/006/015 |
T10生命周期与HTTP可拆两张卡但同文件串行。可证死才恢复，无权限/未知不清理；boot长期秘密不进URL/argv，CSP 'none'严格基线。server页打开/读历史/validate一律零模型。

### S5 整合与质量/实际部署验收
目标：全部VC实证，不把task完成视为目标达成。
| Task | 产出 | 依赖 | AC / VC |
|---|---|---|---|
| T13 | isolated真实CLI→本地HTTP→真实消费入口→sign前后byte/hash；多进程/双root/多project集成 | T01–T12 | 全AC；VC-001–018本地部分 |
| T14 | 用户明确许可下实际Chrome/Edge窗口及Jev人工提交/故障展示；独立evidence | T13；许可 | AC-004/006/007；VC-004/006/007实际环境部分 |
| T15 | README/两个包Unreleased changelog、npm run check全输出、独立实现review、质量门禁与closure | T13,T14 | 全AC/VC |
T14真实付费模型不能被pytest/check隐式触发。启动实际应用若需要新bundle，遵守用户未请求build禁令，先取得构建/激活许可，不用stale dist替代验收。未经用户要求不commit。

## 四条非阻塞review建议落实
1. monitor/启动锁状态带PID启动身份时间，参考现有process_start_ms；仅保守降低unknown，不把PID不同等价于可杀其他进程。
2. 所有unknown/不兼容/半发布/锁未知出口均输出统一人工恢复指引。
3. stale先隔离无密状态再隔离对应secret，每一步身份核对；中断文件不能误认活实例，新实例secret不能被旧cleanup删；测试每步崩溃注入。
4. registry逐字段定义自由文本元素长度、max_items与说明；长度满足不保证总预算，UI显示两约束，必填事实不静默裁剪。

## 验证命令与纪律
- 编码卡使用TDD：先红测试，记录失败输出，再实现，运行修改的所有测试。
- Python按卡从packages/multi-workers运行精确pytest文件，不跑无界全包，全部临时root/本地HTTP无真实凭证。
- TS从packages/coding-agent运行 `node ../../node_modules/vitest/dist/cli.js --run test/suite/<specific>.test.ts`；使用suite/harness+faux provider，无真实API。
- 非e2e全包如必要只能经root test.sh并先协调；不npm test、不直接全vitest、不自行build。
- 代码变更完成运行root `npm run check`，全输出留档；所有errors/warnings/infos修复。已知Windows基线与新增失败分开，不以基线掩盖新错误。
- record/write失败、坏Host/Origin/token/超体/act参数、secret泄漏、端口全占用、PID复用/身份变化、半行/短写均有负向断言。

## 风险与阻塞
- 独立评审通过仅设计层；真实Windows应用窗口/锁/NTFS/Jev/dual-root尚未验证。
- 其他会话共享ui-bridge等文件当前改动，编码前需协商写面。
- 实际Jev与新产物激活/构建需显式许可；未许可则作为未验证阻塞，不假报AC-004/006通过。
- 17AC/18VC必须在正式任务卡逐条承接；本表候选任务不是可dispatch编码卡。先建立自包含TASKS卡（goal/path:line、写面禁止、验收命令、改动历史），通过TASKS/EXECUTE门禁才编码。

## 完成判定
每任务代码完成+精确测试通过+原生产接线证据；最后AC×VC质量矩阵、独立实现review、全部部署必要证据。无验收欠债才能advance done；achieved.md写系统行为/触达面/遗留，跨keysummary由框架记录，不修改其他key。
