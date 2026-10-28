# T07 工作台UI与四完整离线case

type: coding
ac_refs: AC-011, AC-012, AC-013, AC-015, AC-016, AC-017, AC-018, AC-019, AC-020
vc_refs: VC-011, VC-012, VC-013, VC-015, VC-016, VC-017, VC-018, VC-019, VC-020

## 上下文
目标`.agenticdoc/goal.md:1`，批准spec/design/plan `.agenticdoc/mw-decision-context/`，最新D005无强制intent/commit、dp2仅PM且原问题。种子`packages/multi-workers/decision_monitor.py:1596` history路由和default_monitor_deps；`packages/multi-workers/decision_dashboard.js:1`现UI资产；`decision_playground.py:1`已有独立观察存取与冻结backend；均分页全文读。
T01四DP契约/T02 lifecycle正在并行，实现各自基础；T06 history随后单写。你独占monitor/playground/UI/cases，不等依赖空转。先离线cases+case安全只读路由+UI布局行为测试，实现能独立工作的部分；接口问题只集中report给PM，无需追加研究。

## 要求
1. 四完整合成可编辑case，离线scripts/build_decide_cases.py→decide_cases/dp1.json dp2.json dp3.json dp25.json；包括必要原文/完整目标约束/真实合成证据/候选说明，禁止省略号或TODO占位。title/note外壳不发送；命名字段严格design §2/plan固定，dp2保留原questions，dp3动态候选，dp25四段。
2. `/api/test/cases` page鉴权固定四id只读，拒任意路径/逃逸，读取/加载/编辑/本地校验零模型/零凭证访问。case用于原观察pipeline，生产执行器仍0。
3. UI主表五列+key/DP下拉，点击新record_version2打开10节点安全DAG，旧记录只有技术日志弹窗，不猜关联；四状态按backend投影。保留现25DP编辑/校验/观察/重试能力、独立test状态与精确submission关联。身份/usage/capture分层，不byte_exact/hash当脱敏证明。CSP/textContent/page token安全不退化。
4. history投影T06将交付，切勿改decision_history：UI可使用最小约定 `{workbench:{record_version,processing_state,key,task_key,question_summary,dp_id,selection,initiator_role,nodes},facets:{keys,dps}}`，请向PM发布你采用的最终精确API。不要手填假数据冒称全链闭环。真实HTTPbody编辑断言/四case typed最终验证需T01就绪，若尚不可用先证明自己的行为测试并交付剩余依赖清单；不改T01文件。
5. 从现producer/submit联动保留完整本地材料与meta版本，T05 CLI/lifecycle精确API交付后再接线。未有writer时节点诚实未记录；观察只记录观察/未执行事实，不虚造业务执行。
先正确行为RED再实现GREEN。不以缺模块collection错误充RED，不修后mutant称test-first。首写前保存本允许面原文hash/diff含untracked，保留所有外来diff。不真实browser/Jev/凭证/服务起停/build/install/commit。测试tmp HOME/USERPROFILE/PI_CODING_AGENT_DIR、合成auth/env清理+读前spy；只look at合成资产（没有图片任务），不paid API。
实施优先，不新增性能SLA/字段字节上限，不反复安全泛审；只有明确泄漏/误执行/主功能不可用作阻塞，其它集中账。

## 写入允许面
- `packages/multi-workers/decision_monitor.py`
- `packages/multi-workers/decision_playground.py`
- `packages/multi-workers/decision_dashboard.html`
- `packages/multi-workers/decision_dashboard.js`
- `packages/multi-workers/decision_dashboard.css`
- `packages/multi-workers/scripts/build_decide_cases.py`
- `packages/multi-workers/decide_cases/dp1.json`
- `packages/multi-workers/decide_cases/dp2.json`
- `packages/multi-workers/decide_cases/dp3.json`
- `packages/multi-workers/decide_cases/dp25.json`
- `packages/multi-workers/test_decision_context_workbench.py`

## 写入禁止面
history/wire/lifecycle/points/book/CLI/TS/其它测试/框架脚本/配置/dist/依赖锁/真实凭证/其它key。旧测试若有需要迁移报告坐标给PM不越面。

## 验收命令
`cd packages/multi-workers; python -m pytest test_decision_context_workbench.py -q`（隔离合成）；局部真实loopback与Node DOM shim必须关服务且无浏览器，用定向命令。既有dashboard_assets/monitor/playground定向单文件邻接可跑（避免共享端口并发，自身串行）完整日志存evidence。不全vitest/npm test/build；npm run check最终PM稳定统一。
四case实际typed校验4/4+编辑→真实loopback HTTP正文断言属于待依赖集成，诚实分列局部与最终，不以静态GREEN代整AC。

## 状态
代码交付/局部17P原验收日志GREEN；worker终态needs-clarification exit2（dp1写入登记缺口，不需求澄清），PM完整report/output/run回读ack并核dp1 1201B/hash与report一致，保留原终态不改run。4/4 typed与validate loopback已验，显式submit→真正HTTP正文仍待T08合成backend验，不需付费模型。

## 改动历史
初派；T07从原等待DAG提前并行可独立部分（case生成/路由/UI），不改变设计/AC，等待T01/T06最终接口接线不双写。允许面含旧dashboard未结案实现，保留。

## 交付格式
report.md+evidence原RED/GREEN日志、UTC/exit/命令/hash；4case完整正文位置及生成命令、最终workbench/facets/nodes精确schema、真实HTTP/DOM与平台未验分列；剩余依赖和低影响债集中一份，不滚动碎研究。worker不写PM相位文档。
