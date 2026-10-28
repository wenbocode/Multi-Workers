# R T05c迁移独立审查及新阻塞核实

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec/design typed25DP/AC-005/010/011/012，evidence-requirement。
- `packages/multi-workers/decision_book.py:1000` _check_secrets/_flatten与placeholder规则（按函数定位）；`decision_points.py:1` dp25声明/identity/validator/_snapshot_ref。
- workers/dd-unified-input-contract/report.md全文/evidence/runs/T05c-unified-input-contract，workers/dd-review-observation-fixes/report.md旧项。

## 审计目标
独立核对dp25三typed字段与真实signoff_state类型/数组界，legacy/allow_paths删除及生成JSON/TS只有预期声明变化；N1..N4逐闭合，RED27/8、GREEN35后补36、478=442+36时序及pin-GREEN项不假称RED覆盖全部。
新数组credential可发送是阻塞，不因snapshot脱敏免责。核实_check_secrets数组/嵌套对象/映射键/metadata已知secret与pattern到底覆盖哪些，給最小写面和行为RED设计，不能运行真实模型。区分已配置凭证known-set与仅sk/Bearer pattern检查，不泛声称所有秘密可识别。
p0_open=[]真实态与placeholder冲突：读取AC-019真正来源（本key仅17AC，不混同book旧规则/其他key），是否已有明确允许空业务列表的规范；不要建议全局取消空容器检查，给字段级声明/显式空已填机制选项及哪些intentional规则需用户确认。测试记录旧错误不能算合法真实生产book覆盖。
重复book_ref：内容寻址标识是否设计允许多事件共享？按submission/call/event join是否歧义，定位真正ID生成owner（未必wire）及最小修复。不凭重复值直接推泄漏/错误。
478只是限定绿、321邻接+skip、biome仅生成TS单文件exit0，未全仓check；PM未放行T06。review源码全文分页及旧日志非自己实测。

## 要求
PASS/CHANGES_REQUIRED，逐关闭表/新P0/P1/P2触发path:line/验收缺口/精确续卡建议；明确T06开工阻塞，不改任何源/测试，不猜业务事实。只自身report，禁外网/模型/服务/build/真实凭证读取。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-unified-input/**`

## 写入禁止面
- 所有源/测试/任务相位/旧报告证据/真实档案/其他worker。

## 未覆盖面声明
真实Jev/HTTP/TS运行时/UI/全仓check未验；静态不能复现真实发送/平台，不把FakeBackend称paid请求实测。

## 交付格式
report≤150行，关闭表/新缺陷/placeholder规范来源与需确认点/最小owner卡/证据偏差/未覆盖。
