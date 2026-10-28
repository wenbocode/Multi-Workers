# Research: 39AC覆盖与机械可验性（RQ12 毕业考）

## 结论

1. **事实**：spec.md 共 39 条 AC（spec.md:84-122），全部属"草案未锁定"，§4 明写"39条AC均未锁定"（spec.md:124-129）。按四要素推导规则（workflow-requirements.md:160/172/175/177/184/186/197）做纯文档判定，结果：四要素齐且可构造 **4 条**（AC-006/013/027/038）；有主体与量化但缺一处载体/schema **27 条**；前置或对象不可构造/自相矛盾 **8 条**（AC-001/002/003/008/009/014/025/036）。无一条可称已锁定或可验收。
2. **系统性缺口（设计缺口，不等于业务未确认）**：
   - **G1 证据版本/幂等无载体**：AC-011/019/024/029/033/039 依赖"同一证据版本""受影响旧批准"，spec 未给 version 字段或落盘标识，版本隔离类 AC 不可构造。
   - **G2 零指标无正向对照**：AC-002/003/008/018/021 只写"次数=0"，无成功路径或产物观测，over-blocking（把正常路径也堵死）无法被发现。
   - **G3 四层只有禁止、没有正向**：AC-007/014 写"不冒充"，但 selection→后继调用→真实动作→settled 各自的可观测行（consumed/executed/settled、trace、steer/签收文件）没有一条 AC 要求"该发生的确实发生了"（现有消费面事实见 spec-decision-action-consumption.md:8-52：唯一消费面是工具返回值，无 selection→action 转换器）。
   - **G4 dp-route 零专属 AC**：全文只有 AC-011 提到"路由"（spec.md:94），七目标枚举、固定节点直调、角色资格、复合问题拆分、路由成功≠业务决策全部无 AC。
   - **G5 dp-auto 只有门禁失败场景**（AC-009，spec.md:92）：动态候选合法性、非法材料、不可用、无有效选择、"不创造未准备方案"、执行分离无 AC；AC-012 的"四门"（spec.md:95）未点名，无法判断是否含 dp-auto/dp-route。
   - **G6 dp-w-check-task 三固定结果**（spec.md:28）只在 AC-004 一句内出现，技术ID/终态映射/有限补证结束判据/不等待PM 均无可观测载体。
   - **G7 dp-w-type vision 硬门**仅作 AC-004 从句，缺可构造输入（带图任务＋无图像能力模型）。
   - **G8 空值语义**：材料 null 与 [] 的区分、时间戳递增、历史不回填，只有 AC-013 覆盖历史字节不变；null-vs-[] 无 AC。
3. **八DP覆盖极不均衡**：dp-gate-approve 12 条、dp-QG 5 条、dp-sign-key 3 条较厚；dp-auto 2 条、dp-route 1 条、dp-w-type 1 条、dp-w-check-task 1 条，且都是一句话覆盖。
4. **H01–H13 各 1–2 条**推导 AC，但 H03（stalled 专用停滞证据）与 H12（隔离恢复通道）的场景自身条件未进 AC；H12 因此成为唯一"前置不可构造"的 H 项。
5. **事实**：AC-001~003 的对象（"§1.1 的8项""退役17项"）与 §1.5 最新八入口（spec.md:58-67）自相矛盾；按卡交 RQ10 主责，本报告只标不判，不做退役审计。
6. **候选 AC 14 条**见 §证据5，全部未编号、未批准、不编辑 spec；原编号不重用，待完整 SPEC 审核后才锁定。本报告不宣称 SPEC/AC/QG/实现验收通过，也不声称任何测试结果。

## 证据

### 1. 39 条 AC 逐条判定（档位 A=四要素齐可构造；B=缺一处载体/schema；C=前置或对象不可构造；`0`=只有"次数0"无正向对照）

| AC | 前置条件 | 对象/可观测结果 | 量化断言 | 档 | 主要缺口 |
|---|---|---|---|---|---|
| 001 | 注册表与 schema 生成后 | 可调用集合 vs "§1.1 8项" | 集合相等 + 退役 0 | C | 集合与 §1.5 冲突；交 RQ10；`0` |
| 002 | 通过各入口请求退役DP | 入口返回明确拒绝 | 拒绝 1 + 三类计数 0 | C | 退役集合未定；"明确拒绝"形式未定；`0` |
| 003 | 盘点源码/配置/提示词/case | 活跃注册、调用、可提交选项 | 均为 0 + 逐项标注只读 | C | 审核判定非运行观测；旧基准；`0` |
| 004 | dp25/dp1/dp2/dp3 各自材料齐 | 四个 DP 混在一句 | 候选=4；目标缩减 0 | B | 一 AC 四对象；"指定基线"未指名；dp3 无 ID/终态 |
| 005 | PM 提交完整质量审核材料 | dp6 结论 | pass/fix/reopen 枚举 | B | "可复核/未覆盖面"无格式；pass 消费未设计 |
| 006 | 质量证据缺失或硬门失败 | dp6 | 有效通过 0、放行 0、缺失可见 | A | 放行消费者未设计（需借 gate 结果观测） |
| 007 | PM 提交 gate 背景+预拟 note | dp-gate-approve | 四选一枚举 + note/理由两处 | B | note 字段/存储未定；"已发起 dp-pm-steer"未量化 |
| 008 | 未获该 gate 启用条件/授权 | dp15 结果不得作放行依据 | 未授权副作用 0 | C | "启用条件"未定义→前置不可构造；`0` |
| 009 | 相位门失败 + PM 行动候选 | dp-auto 处置选择 | 选择 + 保留未解决项 | C | 候选动态→无预期枚举；未解决项载体未定；`0` |
| 010 | stage close 材料齐 | dp-gate-approve 审批 | 可关闭/不可关闭分支 | B | 分支多；状态转换未设计；"披露"载体未定 |
| 011 | 四门及 dp2/dp25 处理同一事项 | 路由 + 职责表 | 唯一归属；重复审批 0 | B | 职责表未设计；证据版本无标识 |
| 012 | 不可用/材料非法/无有效裁决 | "四门" | 阻塞 + 原因可见 + 放行 0 | B | "四门"未枚举；原因格式未定；未含 dp-auto/dp-route |
| 013 | 载入含退役DP历史记录 | 列表/详情/原始文件 | 只读+不可发起+字节变化 0 | A | 退役集合依赖 RQ10 |
| 014 | 跨 Python/TS/观察界面传递 | producer→writer→consumer→projection | 链路可核验+三态不冒充+明文 0 | C | 四层载体未点名；"隔离生产路径测试"未定义；无正向观测 |
| 015 | goal/范围/写面/预算授权明确 | autopilot 首次评估 | 启动判断 1 次、人审 0 | B | 未点名 DP（应为 dp-gate-approve）；授权 fixture 形态未定 |
| 016 | 仅缺授权内可补工程证据 | autopilot | 补齐前启动 0、重判 1 | B | "工程证据"判定主体/清单未定 |
| 017 | 缺业务意图或越授权 | 升级信息 | 列出缺失项；越权启动/执行 0 | B | 升级载体（文件/字段）未定 |
| 018 | 任一机器硬检查失败 | autopilot | 记录阻断+停止；豁免 0 | B | 硬检查清单未点名；记录载体未定；`0` |
| 019 | 实质版本变化 | autopilot | 不用旧批准；重复审批/动作 0 | B | 版本标识无载体 |
| 020 | 软轮次耗尽且有授权 | dp-gate-approve | note 四要素；限定追加；重复 0 | B | 轮次计量载体未定 |
| 021 | 追加/steer/need_fix 将突破硬预算 | 预算边界 | 不越界；须人工授权含量/用途/风险 | B | 预算字段未定；提高预算成功路径无观测；`0` |
| 022 | pending-review 被事件/到期触发 | dp-gate-approve | 触发≠恢复；无依据恢复 0 | B | 事件/阈值未定→fixture 难稳定构造 |
| 023 | pending-review 选 steer/need_fix/reject | 移交或拒绝 | 不默认返工；越权 0；复用证据 | B | "复用"观测=审核次数 1，记录载体未定 |
| 024 | goal 变化触发核查 | 版本采用 | 仅 approve 采用指定版本；reject 不刷新 | B | 目标版本号/基线载体未定 |
| 025 | 实质变更影响 key/验收/依赖/写面 | 旧批准失效 | 不用旧批准；越权自动执行 0 | C | "实质"判据需人/规则，无可机械判定输入 |
| 026 | PM 请求跨 key 受限修复 | note 五要素 | approve 限定；开放式修改 0 | B | note schema/授权绑定未定 |
| 027 | 跨 key 修复派发/执行 | 执行者+受限写面 | claim/角色/独占检查；抢占/双写 0 | A | 依赖既有 claim/写面机制（goal.md:31-33） |
| 028 | 申请冻结 AC/VC 变更 | note 四要素 | 限定批准；删减/伪造 0 | B | 冻结 AC 载体未在本 spec 点名 |
| 029 | 获准变更后 | 重验受影响部分 | 重验≥1；旧通过不沿用；历史不改写 | B | "受影响"边界判定未定 |
| 030 | proposal 耗尽恢复前 | 派发/执行/接收/pending/running | 核实后才重派；无依据重派 0 | B | "核实"产物载体未定 |
| 031 | 耗尽与标记处理 | 清除标记机制 | 保留失败；可追踪恢复；改记录 0 | B | 恢复机制未设计→成功路径不可观测；`0` |
| 032 | roadmap/stage 提案耗尽 | 重规划 | 有依据重规划；无限相似 0 | B | "实质修订依据"的 diff 观测未定 |
| 033 | 提案重规划 | 版本保留 | 不清次数；新 stage 仍审批；直接授权 0 | B | 版本/次数载体未定 |
| 034 | 请求 halted stage 恢复 | note 五要素 | 限定恢复；历史保留；无依据 0 | B | 恢复记录结构未定 |
| 035 | halted 源于用户停止/撤权/硬保护 | 授权与硬检查 | 不得以技术消除替代；越权 0 | B | 授权证明载体未定 |
| 036 | 自动熔断后 | 受控恢复通道 | 绕刹车/默认批准/偷换通道 0 | C | 独立通道未设计→前置不可构造；`0` |
| 037 | 缺授权/证据或用户停用撤权 | 保持刹车 | 提具体问题；不自解限制；记录保留 | B | 授权问题载体未定；观察/再熔断规则未设 |
| 038 | 需签收 key 的有效 finalize | 签收条件 | 仅 finalize+证据；不冒充 done/关闭；二次批准 0 | A | "需签收"判据引用旧规则（h13...:17），未冻结入本 spec |
| 039 | 命名/硬门衔接 + 证据实质变更 | finalize 契约识别 | 不伪造旧标签/disable；不扩范围；不复用受影响 | B | 旧词表/受影响判据未定 |

### 2. 八DP × AC 覆盖映射

| DP | 职责出处 | 覆盖 AC | 强度 | 主要缺口 |
|---|---|---|---|---|
| dp-w-type | spec.md:26 | 004（从句） | 弱 | vision 输入不可构造；rag-research 等框架类型保留无 AC |
| dp-pm-steer | spec.md:27；dp2-pm-convergence-definition.md:9-20 | 004, 011 | 中弱 | split 写面冲突、direct-exec 上下文依赖、escalate 具体问题无观测；真实动作与 settled 无 AC |
| dp-w-check-task | spec.md:28；dp3-worker-initiated-discussion.md:18-27 | 004（从句） | 极弱 | 三终态技术ID/落盘产物/不等待PM/有限补证结束判据 |
| dp-QG | spec.md:29 | 005, 006, 011, 029, 038 | 中 | 材料格式与 pass 消费；reopen 判据不可机械 |
| dp-gate-approve | spec.md:31-45；gate-four-option-confirmation.md:11-32 | 007, 008, 010, 020-024, 026, 028, 034, 035 | 中强 | gate 类型枚举；四选项后继调用/状态/settled；note schema |
| dp-sign-key | spec.md:25；h13...:9-17 | 010（输入）, 038, 039 | 中 | null/[]；"需签收"判据；签收文件≠phase done/stage 关闭 |
| dp-auto | spec.md:60；AC-007 need_fix 移交 | 009（仅门禁失败）, 007（从句） | 极弱 | 候选合法性/非法材料/不可用/无有效选择/不创造新方案/执行分离 |
| dp-route | spec.md:62-63 | 011（唯一提及） | 空洞 | 七目标枚举/直调/角色资格/复合拆分/路由≠业务决策 |

### 3. H01–H13 × AC 映射

| H | AC | 场景自身条件入 AC | 备注 |
|---|---|---|---|
| H01 启动授权 | 015-019 | 部分 | AC-015 未点名 dp-gate-approve；授权/预算 fixture 形态未定 |
| H02 阶段关闭 | 010 | 是 | 披露载体、状态转换未定 |
| H03 stalled gate | 007/008（通用四选项） | 否 | stalled 专属停滞证据未进 AC；场景边界交 RQ11 |
| H04 软/硬预算 | 020/021 | 是 | 轮次/预算计量载体未定 |
| H05 pending-review | 022/023 | 是 | 触发事件/阈值未定 |
| H06 goal 变更 | 024/025 | 是 | 版本标识未定；AC-025 判据不可机械 |
| H07 跨 key 修复 | 026/027 | 是 | claim/写面机制可复用，最接近可测 |
| H08 冻结 AC/VC | 028/029 | 是 | 冻结载体未点名；重验边界未定 |
| H09 proposal 耗尽 | 030/031 | 部分 | 核实产物与恢复机制未设计 |
| H10 重规划 | 032/033 | 是 | 次数/版本载体未定 |
| H11 halted | 034/035 | 是 | 恢复记录结构、授权证明未定 |
| H12 熔断恢复 | 036/037 | 部分 | 独立通道未设计→AC-036 前置不可构造 |
| H13 签收硬门 | 038/039 | 是 | 词表/旧标签/证据关联未定 |

### 4. 主要缺口纸面例（纸面推演，非测试结果）

**正路径**
- P1（路由→业务）：输入 PM 现场问题 material（候选入口 [dp-QG, dp-auto]）；预期返回 selection=dp-QG、consumed 行 1、业务动作 0；随后 PM 另发 dp-QG（新 decision_id）得 pass/fix/reopen。禁止：路由答复写签收/改 baseline、把路由 selection 记 settled、把路由材料当 dp-QG 材料。
- P2（固定节点直调）：输入 stage-close gate 直接 ask dp-gate-approve（note 四要素+四选项）；预期 dp-route 调用 0、note 与模型理由分别保存。禁止：以"临时问题"名义绕过 gate note；approve 连带批准下一 stage。

**边界**
- B1：dp-auto 候选=5、id 连续 c1..c5、说明非空 → selection 必属 c1..c5。候选=2 与=5 两端合法；=1 或=6 → input-incomplete。禁止服务端补造第 6 项或截断到 5 项。
- B2（有限补证）：结束判据"3 次证据查询内确认 X"→ 第 3 次未确认即转终止并落盘结论。禁止无限续跑或把补证当目标完成。

**异常**
- E1：候选 id 重复/跳号/说明空/问题空 → input-incomplete、selection 空、动作 0、settled 0。禁止 fallback 首候选、自动重试补齐。
- E2：服务 unavailable → 被点名 DP 各自阻塞+原因、业务动作 0。禁止默认 approve、改 gate/phase 状态、记 settled=ok。
- E3：服务返回未准备的 selection id → 拒绝并要求材料重准备。禁止按最近候选执行。
- E4：dp-QG 机器硬门失败 + dp-gate-approve approve → 放行 0、blocked 记录。禁止 DP 选择改判门、reopen 授权改 AC。

**并发/版本/历史**
- C1：两窗口同 key+对象+证据版本并发提交 → 1 有效决策 + 1 幂等/冲突，业务动作 1，_workers/_index 锁未破。禁止双签收/双 steer/互相覆盖。
- C2：goal v1→v2 影响 key 验收 → 旧 approve 不放行、新决策新 id、旧记录字节不变。禁止静默刷新 baseline、复用旧签收。
- C3：载入含退役 DP 历史 → 列表/详情只读+retired 标记、发起请求被拒、文件 sha256 不变。禁止按当前 registry 补造字段/删记录。
- C4：null vs []：verified 未记录=null 与真实空=[] 在投影中区分。禁止把 null 渲染为"已验证"或回填当前证据。

### 5. 候选 AC（未编号、未批准，不编辑 spec）

- **C-A dp-route 正常路径**：在 PM 提交决策主体/判断对象/具体待决问题/候选入口材料时，dp-route 返回且仅返回七目标之一（selection ∈ 七项枚举），返回体不含业务结论字段，业务动作数=0。
- **C-B dp-route 直调**：在固定业务节点直接调用对应固定 DP 时，dp-route 调用数=0 且材料字段与该 DP 原合同一致；缺固定材料返回 input-incomplete 而非路由。
- **C-C 角色资格**：PM 以 dp-w-check-task、或 Worker 以 dp-pm-steer/dp-sign-key 发起时返回角色拒绝；被拒请求的决策记录=0、业务动作=0、ledger 新行=0。
- **C-D dp-auto 候选合法性**：候选 2..5 个、id 连续 c1..cN、label≤80 单行、description 非空时，selection 必为其中之一；未准备 id 出现数=0，返回体不得新增候选。
- **C-E dp-auto 非法/无有效选择**：候选<2 或>5、id 重复跳号、description 或 question 为空时返回 input-incomplete；selection 缺省、业务动作=0、settled=0、fallback=0。
- **C-F 不可用**：决策服务 unavailable 时，被枚举的"四门"各自返回 unavailable+escalated_reason；默认放行=0、业务动作=0、settled 写入=0；重试不复用旧裁决。
- **C-G dp-w-check-task 终态**：Worker 选定三项之一后以结论文件落盘（完成项/未完成项/阻断原因/证据四段）并结束本次执行；PM 同步等待轮次=0；key 状态/目标/验收字段变化=0。
- **C-H 有限补证**：选"继续并补充证据"时材料含待补证问题与结束判据；判据未满足前补证轮次≤N（N 待设计）、不越预算；超出即转终止并落盘结论，无限续跑=0。
- **C-I dp-w-type vision 门禁**：需读图任务选 vision 时，仅图像能力门禁通过的模型可派发（worker 启动=1 且可读图）；不通过时启动=0，回退 coding 冒充=0。
- **C-J 四层正向**：一次完整处理中 consumed=1、executed receipt=1、settled=1，decision_id 相同、时间戳非递减，且真实动作证据（steer/签收/关闭）存在；缺层不得由他层推断（以状态代证=0）。
- **C-K 版本幂等**：同对象+同 evidence_version 重复提交时第二次返回 duplicate/幂等结果，新决策记录=0、业务动作=0；版本变化后允许新决策且旧记录字节变化=0。
- **C-L null/[] 与历史**：dp-sign-key 未记录项为 null、真实为空为 []，投影分别显示"未记录"/"无"；用当前状态回填历史次数=0、历史文件字节变化=0。
- **C-M 并发**：两窗口同时提交同一对象决策时有效决策=1，另一为幂等/冲突；业务动作=1、双写同文件=0、_workers/_index 锁破坏=0。
- **C-N reject 边界**：dp-gate-approve 返回 reject 且无获授权遗留关闭方案时，关闭动作=0、目标/验收/预算变更=0，并输出拒绝原因与所需授权；steer/need_fix 不记为已整改。

## 残留与未验证

- 纯文档推演：未运行任何测试/build/install/commit，未调用 ask_decision 或 provider 探针，未起停服务；A/B/C 档位是四要素纸面判定，不是执行结果。
- 未读 RQ10/RQ11 报告与其证据，职责与场景结论可能重叠；按卡其主责，本报告只标缺口。
- 未全文核旧独立 key（mw-decision-context）26AC、旧 registry 条目与 advance_phase.py 签收门实现；相关事实转引自本 key 既有证据（h13...:17、spec-decision-action-consumption.md:8-52），不宣称旧链验收。
- 未知（需设计或用户确认）："四门"具体所指、七目标技术 ID、gate 类型枚举、证据版本标识、note/schema 字段、软轮次与预算计量、隔离恢复通道、"需签收 key"判据。
- 未覆盖：性能/数值类 AC（按规则不补）、UI 投影细节、跨语言具体字段；AC-001~003 退役审计交 RQ10。

## 上下文来源

- `.agenticdoc/goal.md:5`（目标锚点）、`:31-33`（文件锁、工具白名单）
- `.agenticdoc/mw-dp-consolidation/spec.md:20`（§1.1 旧范围）、`:24`（§1.2 职责）、`:58-67`（§1.5 路由/命名）、`:70`（§2 约束）、`:84-122`（39 AC）、`:124-129`（§4 未决/未锁）
- `.agents/skills/agentic-task/references/workflow-requirements.md:160`（Step 3.5）、`:172/175`（四要素）、`:177`（禁止词）、`:184`（编号永不重用）、`:186/197`（推导检查）、`:294`（锁定协议）
- 本 key 既有证据（只引用，不重审）：`evidence/autopilot-requirements-clarification.md:11`（通用入口/固定DP/路由）、`:23`（独立路由）、`:37`（选择结果不等于已执行）；`evidence/dp2-pm-convergence-definition.md:9-20`；`evidence/dp3-worker-initiated-discussion.md:18-27`；`evidence/gate-four-option-confirmation.md:11-18,26-32`；`evidence/h13-signoff-gate-link-confirmation.md:9-17`；`evidence/research/spec-decision-action-consumption.md:8-52`；`evidence/research/spec-pm-question-generation.md:8-52`
- 任务卡：`.agenticdoc/mw-dp-consolidation/tasks/RQ12-graduation-ac-coverage.md:1`
