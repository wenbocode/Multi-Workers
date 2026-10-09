# Quality Gate Report: mw-vision-role

**时间**: 2026-09-26T18:50:00Z
**触发**: 全量质检（收口前；用户显式要求由独立 review worker 先行审查）
**范围**: 全量（19 个 AC，其中 AC-018 = OBSOLETE ⇒ 活跃 18）
**独立审查**: `.agenticdoc/mw-vision-role/evidence/reviews/qg-review-mw-vision-role-20260926.md`（T-16，`type: research` 独立 worker，结论 `PASS-WITH-NITS`、`blockers=0`）
**主证据**: `.agenticdoc/mw-vision-role/evidence/runs/verify-mw-vision-role-20260926.md`（T-14 正文 + T-19 附录 A）

---

## Step 1 — 前置门禁

| 检查项 | 结果 | 备注 |
|--------|------|------|
| spec.md 存在 AC 编号 | ✅ | 19 个（AC-001…AC-019） |
| design.md 存在 VC 编号 | ✅ | 19 个（VC-001…VC-019，VC-018 不适用） |
| AC→VC 映射覆盖 100% | ✅ | design §8 覆盖 19/19 行；活跃 18 条全部有 VC |
| evidence-requirement.md 存在 | ✅ | 19 个小节逐 AC |
| ac_fingerprint 一致 | ⚠️→✅ | 原记录 `6857a77db10f` 用的是"spec §3 区块文本归一化 sha1"口径，该口径**对文本编辑敏感**：AC-010 追加 `[REVISED @ 2026-09-26]` 注后漂移到 `0cdc159d3d10`（AC **集合**未变）。本次按 `workflow-quality-gate.md` 的 id-set 口径（`grep -oE 'AC-[0-9]{3}' \| sort -u \| sha1 \| cut -c1-12`）校正为 **`918de4e2b149`**，并在 evidence-requirement.md 同时保留旧口径值供追溯。**AC 集合未增未减**（19 个 id，含 OBSOLETE 的 AC-018）。 |
| evidence/baseline/ 非空 | ⚠️→✅ | 建 key 时未建该目录；本次补建 `evidence/baseline/baseline-mw-vision-role-20260926.md`（含滚动基线 + 两红成因 + 真实进程基线；如实写明"多 key 并发脏工作区 ⇒ 无法取 pristine baseline"） |
| 每个 task 有非空 ac_refs/vc_refs | ✅ | 19 个任务文件全部有绑定（含 T-15…T-19 追加卡） |

---

## Step 2/3 — 问题清单与证据链核查

### A. Q-AC-xxx（来源：spec.md AC）+ Q-COV-xxx（来源：design §8 路径行）

AC 与 VC 为 1:1，路径分类取 design §8 的"路径分类"列，故合并为一表。

| 问题 ID | 描述 | VC | 路径 | 证据引用 | 状态 |
|---------|------|----|------|---------|------|
| Q-AC-001 | `mw model set vision <model>` 成功写入 | VC-001 | 正常 | runs §4 ledger：`VC-001: vision=timi/deepseek-v4-flash-vision-exp rc=0`；T-11 `test_yes_writes_vision_role` | ✅ |
| Q-AC-002 | 未知角色拒绝且列出 5 个角色 | VC-002 | 异常 | ledger：`VC-002: rc=nonzero roles=5` | ✅ |
| Q-AC-003 | 解析链命中 `config:vision`（task 覆盖时返回 task） | VC-003 | 正常 | runs **§A.2.1 line 987**：`[VERIFY] VC-003: source=config:vision task_override=task`（T-18 补齐；T-14 时为 GAP） | ✅ |
| Q-AC-004 | 类型↔角色映射两侧一致 | VC-004 | 正常 | `VC-004: role_for_vision=vision mirror_ok=true`；T-16 §2.1 脚本逐元素复算（`TASK_TYPE_TO_ROLE`↔`DISPATCH_ROLE_BY_TYPE` 10 键同序同值） | ✅ |
| Q-AC-005 | 工具白名单两侧逐元素相等 | VC-005 | 正常 | `VC-005: allowlist_vision=read,write,edit,bash,find,grep,ls parity=true`；T-16 §2.1 `REGISTRY`↔`TOOL_ALLOWLISTS` 7/7 同序 | ✅ |
| Q-AC-006 | 能力不匹配 ⇒ 拒绝且零副作用 | VC-006 | 异常 | `VC-006: refused=true queue_delta=0 dir_exists=false`；对照（去门禁）变红 | ✅ |
| Q-AC-007 | 放行 + `^images: yes$` + 头部行序 | VC-007 | 正常 | runs **§A.2.2 line 991**：`[VERIFY] VC-007: queue_delta=1 images_line=yes order_ok=true`（T-18 补齐；断言为整行匹配 + 严格递增序） | ✅ |
| Q-AC-008 | 不可判定 ⇒ fail-open 不拒绝 | VC-008 | 边界 | `VC-008: failopen_ok=true queue_delta=1`；TS 9 条不可判定分支 + Python `unknown` 分支；对照（`=== "no"`→`!== "yes"`）变红 | ✅ |
| Q-AC-009 | 未声明时逐字节零变化 | VC-009 | 边界 | `VC-009: zero_byte=true frozen_copy=true`（自备冻结副本，未挂基线红断言）+ `VC-009-order: line_order=type<phase<images<model order_ok=true`；对照（`if images:`→`is not None`）泄漏 `images: ` 变红 | ✅ |
| Q-AC-010 | doctor 三态、退出码均 0、`no` 落 suggestion | VC-010 | 正常+异常 | `VC-010: doctor_rc=0 states=suggestion,ok,skip`；真实仓库 `mw doctor --json` rc=0、`healthy=true`、suggestion 含 `mw model set vision`（E-10）；T-15 收窄后真实仓库 image suggestion = `[]`；suggestion 级（落 issues 会使 `summary.healthy` 假 ⇒ 退出码 1） | ✅ |
| Q-AC-011 | worker 运行时兜底 `[IMAGE-CAP]` + 非零退出 | VC-011 | 异常 | `VC-011: image_cap_line=true exit=1 control_ok=true`；**真实进程 L2-1**（源 builtin）`[IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes`、`rc=1`、`trace.log` 有 `[ERROR]` 行；对照（禁用检查）`exit(1)` 未被调用 | ✅（活窗口路径见 ⚠️-3） |
| Q-AC-012 | 测试与静态检查全绿 | VC-012 | 流程 | runs **§A 末 line 1132**：`[VERIFY] VC-012: scoped_tests=green check=green`（取代 T-14 的 `check=FAILED`）；Python 203 passed/2 failed（2 红 = B-1 已定位基线）、TS 201 passed、`tsgo rc=0`、biome rc=0 | ✅（`npm run check` 字面见 ⚠️-1） |
| Q-AC-013 | 配置期拒绝 + `--force`（仅 vision） | VC-013 | 正常+异常 | `VC-013: no_rc=1 yml_unchanged=true force_rc=0`；真实 CLI 输出 `reports images=no` + `Suggest: … --force`；`--force` 对其他角色报错 | ✅ |
| Q-AC-014 | PM 知情面四处文本 + token 集 | VC-014 | 正常 | `VC-014: surfaces=4 token_set_ok=true`；`type` 描述 token 集合 == `DISPATCHABLE_TYPES ∪ {codex}`；`/worker`、`/mw model set`、`PARALLEL_PROTOCOL` 三处齐；对照（漏 `PARALLEL_PROTOCOL` / 漏 `rag-research`）均红 | ✅（断言强度见 N-6） |
| Q-AC-015 | 能力可见：`show`/`doctor` 每行 `images=` | VC-015 | 正常 | `VC-015: show_images=yes/no/unknown rc=0`；真实仓库 `mw model show` 5 行均带 `images=`（E-10）；doctor JSON `dispatch.images` 全角色 + TS 渲染单测（含 `images=unknown` 回退） | ✅（活窗口渲染见 ⚠️-2） |
| Q-AC-016 | auto-route 只换模型 | VC-016 | 正常+边界 | `VC-016: auto_route=true type_unchanged=true explicit_model_untouched=true`；对照（改写 `type:`）5 例红 | ✅ |
| Q-AC-017 | auto-route 按能力（参数化两类型） | VC-017 | 正常 | `VC-017: types=vision,review type_unchanged=true effective_vision=2 auto_route_fired=1`；**期望串实现期修正**（原 `routed=2` 逻辑不可满足：`roleForTaskType("vision")=="vision"` ⇒ 源角色==目标角色），已回写 design §7 + evidence-requirement，语义未变 | ✅ |
| Q-COV-018 | （作废） | VC-018 | N/A | spec AC-018 标记 OBSOLETE；未计入 18 条 | N/A |
| Q-AC-019 | conductor 允许派发 vision | VC-019 | 正常+异常 | `VC-019: conductor_dispatchable=true unknown_type_refused=true`（属性访问取证：`REGISTRY["vision"]` 是 frozen dataclass `DispatchType`） | ✅ |

### B. Q-VC-xxx（来源：design §7）

| 问题 ID | 断言（摘要） | 证据（`[VERIFY]` 原始行 / 位置） | 状态 |
|---------|-------------|-------------------------------|------|
| Q-VC-001 | set vision 写入成功、rc=0 | `VC-001: vision=timi/deepseek-v4-flash-vision-exp rc=0` | ✅ |
| Q-VC-002 | 未知角色拒绝、列 5 角色 | `VC-002: rc=nonzero roles=5` | ✅ |
| Q-VC-003 | 解析链 `config:vision` / task 覆盖 | `VC-003: source=config:vision task_override=task`（runs line 987） | ✅ |
| Q-VC-004 | 两侧映射一致 | `VC-004: role_for_vision=vision mirror_ok=true` + T-16 脚本复算 | ✅ |
| Q-VC-005 | 白名单逐元素相等 | `VC-005: allowlist_vision=… parity=true` + T-16 脚本复算 | ✅ |
| Q-VC-006 | 拒绝 + 零副作用 | `VC-006: refused=true queue_delta=0 dir_exists=false` | ✅ |
| Q-VC-007 | 放行 + `images: yes` + 行序 | `VC-007: queue_delta=1 images_line=yes order_ok=true`（runs line 991） | ✅ |
| Q-VC-008 | 不可判定 fail-open | `VC-008: failopen_ok=true queue_delta=1` | ✅ |
| Q-VC-009 | 零字节 + 行序 + 冻结副本 | `VC-009: zero_byte=true frozen_copy=true`；`VC-009-order: line_order=type<phase<images<model order_ok=true` | ✅ |
| Q-VC-010 | doctor 三态、均 rc=0 | `VC-010: doctor_rc=0 states=suggestion,ok,skip`；真实仓库 rc=0 | ✅ |
| Q-VC-011 | `[IMAGE-CAP]` + exit 1 | `VC-011: image_cap_line=true exit=1 control_ok=true` + L2-1 真进程 | ✅ |
| Q-VC-012 | 触达面绿 + check 绿 | `VC-012: scoped_tests=green check=green`（附录 A） | ✅（⚠️-1） |
| Q-VC-013 | 配置期拒绝 + `--force` | `VC-013: no_rc=1 yml_unchanged=true force_rc=0` | ✅ |
| Q-VC-014 | 四处文本 + token 集 | `VC-014: surfaces=4 token_set_ok=true` | ✅（N-6） |
| Q-VC-015 | show/doctor 能力列 | `VC-015: show_images=yes/no/unknown rc=0` | ✅（⚠️-2） |
| Q-VC-016 | auto-route 只换模型 | `VC-016: auto_route=true type_unchanged=true explicit_model_untouched=true` | ✅ |
| Q-VC-017 | 参数化两类型结论一致 | `VC-017: types=vision,review type_unchanged=true effective_vision=2 auto_route_fired=1` | ✅ |
| Q-VC-018 | — | N/A | N/A |
| Q-VC-019 | conductor 可派发 | `VC-019: conductor_dispatchable=true unknown_type_refused=true` | ✅ |

### C. Q-X-xxx（交叉问题，PM 推导）

| 问题 ID | 交叉场景 | 结论 | 证据 |
|---------|---------|------|------|
| Q-X-01 | auto-route 与能力门禁的相对顺序（路由后是否会绕过门禁 / 门禁是否会误判被路由的模型） | ✅ 顺序正确：auto-route 先选 `effective`，门禁随后用**同一** `effective` 判能力；显式 `model:` 一律不改写、不路由 | T-16 §2.2（`ui-bridge.ts` plan→gate→`mkdirSync` 顺序）；VC-008/VC-016 用例 |
| Q-X-02 | D-013 显式 `images: no` 与自动探测命中图片路径 的优先级 | ✅ 显式 `no` 最高优先且**短路**（不调探测器），不会写入 `images: yes` | T-16 §3 对抗例（`images: no` + 存在 png ⇒ 不改道）；T-05/T-06 单测 |
| Q-X-03 | 拒绝路径的副作用边界（目录 / 队列行 / dispatch.yml） | ✅ 拒绝发生在**任何磁盘写入之前**：目录未创建、`_workers.parallel` 无新增、`dispatch.yml` 字节未变 | VC-006（`dir_exists=false queue_delta=0`）、VC-013（`yml_unchanged=true`） |
| Q-X-04 | 两侧镜像的**漂移**风险（本 key 的核心不变量） | ✅ T-16 用脚本直接 import 两侧表逐元素比对（10 键 / 7 桶 / provider 前缀互逆），非人眼 | T-16 §2.1 |
| Q-X-05 | 未声明 `images` 的既有任务是否被静默改变字节 | ✅ 零字节（自备冻结副本 + 4 处既有 golden 未重冻） | VC-009；`test_rag_phase.py`、`test_autopilot_dispatch.py`、`test_autopilot_conductor_exec.py` 绿 |
| Q-X-06 | `unknown` 能力是否会导致"假安全"（放行到看不懂图的模型） | ✅ 设计如此且已记录：`unknown` 一律 fail-open 放行（与 `validateModelValue` 同契约，GC-8）；`images: yes` 的任务仍有 worker 运行时兜底兜住 `ctx.model` 可判定为不可看图的情形 | VC-008 + VC-011；N-2/N-5 |
| Q-X-07 | `vision` 角色未配置时的行为 | ✅ 解析回退到 window model / 默认链（`mw model show` 示 `(unset) → … [window]`）；doctor 不发 image suggestion（T-15 收窄）；auto-route 要求 `vision` 已配置且判定为 `yes`，否则退回门禁拒绝路径 | VC-008/VC-010/VC-016；N-5 |
| Q-X-08 | 本 key 是否触碰 pi 核心 / 引入新 provider 凭证 | ✅ `src/core/**`、`src/cli/**` 无本 key 特性改动（唯一 core 改动 `bash.ts` 属另一 key 的心跳特性）；`.mw/dispatch.yml`、providers/auth/settings 未动 | T-16 §2.4 |

---

## Step 4 — 二次印证

| 检查 | 结论 |
|------|------|
| spec 中每个约束（性能/安全/平台）都有 Q 覆盖 | 覆盖：性能（探针只出现在 `model set/show/doctor` 三个一次性命令、`MODEL_PROBE_TIMEOUT_S=3.0` 保 `doctor_report` <5s、进程内记忆化）→ Q-AC-010/Q-AC-015；安全/边界（fail-open、零副作用、零字节）→ Q-AC-008/009/006；平台（Windows）→ 无平台特有分支，测试在 Windows 全绿 |
| design Function Flow 每个节点至少一个 Q | 覆盖：写侧（Q-AC-007/009）→ 门禁（Q-AC-006/008）→ auto-route（Q-AC-016/017）→ worker 兜底（Q-AC-011）→ 探针（Q-AC-010/013）→ 可见面（Q-AC-014/015）|
| Coverage Matrix 每条"异常路径"行都有 Q | 异常路径 = AC-002/006/008/010/011/013/019 共 7 条，全部有 Q-COV 行与 `[VERIFY]` 证据 |
| 是否有 task 的 vc_refs 为空但 AC 有对应 VC | 无：19 个任务文件全部非空 |

---

## 汇总

- **总问题数**: 19（AC）+ 19（VC）+ 8（交叉）= 46；其中 N/A 2（AC-018 / VC-018）
- **通过（充分）**: 44/44
- **有条件通过（不足）**: 3（下列 ⚠️，均为"当前工作区/活窗口不可验"，非功能缺陷）
- **未通过（无证据）**: 0

**质检结论**: ⚠️ **有条件通过（验证欠债 3 项，见下）**

## 未通过 / 有条件通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 |
|------|------|---------|------|
| ⚠️-1（Q-AC-012 / Q-VC-012） | `npm run check` 字面第一步是 `biome check --write .`，在多 key 并发的脏工作区会**改写他人在飞文件**（违反并行纪律），故未按字面执行 | 已逐条跑其**只读**组件（全仓 biome `--error-on-warnings`、`tsgo --noEmit`、pinned-deps、ts-imports、shrinkwrap、install-lock、browser-smoke）全绿。**债务**：`npm run check` 的写模式是否在提交后全绿，需在干净工作区（或由 CI）复验一次。建议把写模式与只读门禁拆分（N-1） | 用户/CI（提交前） |
| ⚠️-2（Q-AC-015 doctor/TS 渲染） | 活窗口加载的是**陈旧 bundle**（`bundle.stale=true`，B2 遗留），TS 渲染只有单测覆盖 | `/mw build` + `/mw restart` 后在活窗口跑一次 `/mw doctor`，确认 `派发模型: … images=` 渲染 | 用户（需授权 `/mw build`） |
| ⚠️-3（Q-AC-011 活窗口兜底路径） | 同上：走陈旧 bundle 的 L2-1 **不触发** `[IMAGE-CAP]`（源 builtin 用 `-ne` 已验证触发） | 同上；另可经 mw launcher 真派发一次 `images: yes` 任务复验 | 用户（需授权 `/mw build`） |

## 二次印证结论

无遗漏：二次扫描未发现新的未覆盖问题。三点口径类 NIT（N-4 跨 key VC 编号歧义、N-6 断言强度、N-7 evidence-requirement 测试入口过期）在下方登记，**不改变任何 AC 的行为判定**。

---

## 独立审查交叉引用（T-16）

`evidence/reviews/qg-review-mw-vision-role-20260926.md`：`QG verdict: PASS-WITH-NITS`、`[VERIFY] VC-QG: acs_total=18 acs_pass=18 invariant_violations=0 blockers=0`。其 N-1…N-7 与本报告的 ⚠️/NIT 一致；其 §6.4 列出的 4 项"未验证"（`npm run check` 字面、活窗口 TS 渲染、L2-2 真实 token 复跑、已配置 `vision` 角色的 doctor suggestion）与本报告 ⚠️-1/2/3 及 N-5 一一对应。

**PM 对 T-16 发现的处置**：
- B1（`tsgo` 4×TS2741）→ T-17 修复，`tsgo rc=0` 已由 PM 独立复跑 ✅ 闭环
- B2（陈旧 bundle）→ 判定为**部署遗留**而非代码缺陷（源 builtin 真进程已验证）→ 登记于 ⚠️-2/3 与「遗留」
- 证据缺口 VC-003/VC-007 → T-18 补齐，PM 独立复跑两条 `[VERIFY]` 行 ✅ 闭环
- N-1…N-7 → 全部作为「遗留/NIT」登记，无需再改代码

## NIT 登记（不阻塞，不改变判定）

| ID | 内容 | PM 处置 |
|----|------|---------|
| N-1 | `npm run check` 写模式与"全绿"口径冲突 | 登记为 ⚠️-1 + 遗留（建议拆分只读门禁） |
| N-2 | 纯函数层对非法 `images` 值静默回落（用户可达路径均已拒绝） | 接受现状（fail-open 方向安全）；登记为可选加固 |
| N-3 | AC-011 的 `worker.log` 由 launcher 捕获 stdout 创建，源 builtin 直调不落该文件 | 已在 baseline/L2 文档写明复现口径 |
| N-4 | `evidence-requirement.md` 引用 readcap 的 `VC-007/008`，与 readcap 套件同号 VC 混淆 | 文档歧义，登记 |
| N-5 | `vision` 未配置时 doctor 不显示该角色行（"未配置 ⇒ skip"语义） | 与 AC-015 的"每个**已显示**角色行"一致；如需未配角色也出行需另开需求 |
| N-6 | VC-014 的 `/worker` USAGE 与 `PARALLEL_PROTOCOL` 断言为子串级，弱于 token 集要求 | 登记；token 集断言已在 `type` 描述上做严格集合比较 |
| N-7 | `evidence-requirement.md` 的"测试入口"段漏列实际承载 VC-006/007/016/017 的 TS 文件 | 已在 T-19 附录的逐 AC 证据表中覆盖引用；登记 |
