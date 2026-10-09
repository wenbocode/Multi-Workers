# Achieved: mw-vision-role

- key: mw-vision-role
- 阶段: EXECUTE/VERIFY → DONE · 2026-09-26
- 上游: spec.md（AC-001..AC-019，AC-018 OBSOLETE）· design.md（D-001..D-013）· plan.md（T-01..T-14）· 执行期追加 T-15..T-19
- 证据: `evidence/runs/verify-mw-vision-role-20260926.md`（T-14 正文 + T-19 附录 A）· `evidence/quality-gate-report-20260926T1850Z.md` · `evidence/reviews/qg-review-mw-vision-role-20260926.md`（独立 QG：PASS-WITH-NITS / 0 blocker）· `evidence/baseline/baseline-mw-vision-role-20260926.md`

## 系统行为变化

1. **新增第 5 个派发角色 `vision`（含新任务类型 `vision`）**：此前 dispatch 只有 main/coding/review/research 四个角色、9 个任务类型，**没有任何角色能读图**。现在 `mw_common.DISPATCH_ROLES` / `TASK_TYPE_TO_ROLE`（10 键）与 TS `DISPATCH_ROLE_BY_TYPE` / `DISPATCHABLE_TYPES` 两侧逐元素一致，`autopilot/dispatch.py` 的 `REGISTRY["vision"]` 标记为 conductor 可派发，工具白名单 `["read","write","edit","bash","find","grep","ls"]` 两侧同序相等，并有双侧镜像锁（VC-004/VC-005）。
2. **派发期能力门禁**：任务需要读图（显式 `images: yes`，或 `images` 未声明但描述里引用了**存在的**图片文件）而解析出的模型 `input` 不含 `image` ⇒ 在**任何磁盘写入之前**拒绝（消息含 `images` / `mw model set vision` / `images: no`），且**零副作用**：worker 目录不创建、`_workers.parallel` 不新增行。此前这类任务会被正常派发并在运行时才失败/降级为「当前模型不支持图片」提示。
3. **fail-open 契约**：模型值为空 / 带 CLI 前缀 / provider 未知 / registry 缺失 ⇒ 能力判为 `unknown` ⇒ **放行**（与既有 `validateModelValue` 同契约，GC-8）。只有明确判定 `no` 才拒绝。
4. **自动改道（auto-route）**：任务未显式指定 `model:`、需要读图、其角色默认模型不可读图、且 `vision` 角色已配置并被判为可读图 ⇒ **只替换 `model:`**（`type:` 行逐字节不变），`model-reason:` 追加 `auto-route: <源角色> -> vision`，回显追加 `model-source: auto-route`。显式 `model:` 一律不改写；`vision` 未配置/不可判定则退回门禁路径拒绝。
5. **task.md 新增 `images:` 头 + 严格行序**：写侧三态优先级（D-013）——显式 `yes`/`no` 最高优先且 `no` 短路（不触碰文件系统），未声明时按描述自动探测，命中即写 `images: yes`（否则 AC-011 的运行时兜底覆盖不到自动探测的任务）；头部行序锁定 `type < phase < images < model`。**未声明 `images` 时逐字节零变化**——4 处既有 golden 语料无需重冻（用自备冻结副本取证）。
6. **worker 运行时兜底 `[IMAGE-CAP]`**：`images: yes` 且解析出的 `ctx.model` 不含 image 输入 ⇒ 在任务正文运行**之前**写 `[IMAGE-CAP] model=… provider=… task=… declared=images:yes` 到 `worker.log` / `trace.log` / `output.md` 并 `exit(1)`（此前 worker 会带着不可读图的模型整个跑完）。`ctx.model` 未解析（不可判定）⇒ 只写 fail-open trace 注记，不阻塞。
7. **配置期能力探测与拒绝**：`mw model set vision <纯文本模型>` 直接拒绝并给出 `Suggest:` 处方（要求 `mw model set vision timi/deepseek-v4-flash-vision-exp`），`--force` 可越过（**仅** vision 角色接受该旗标，其他角色报错）；探测实现为解析 `pi --list-models`（`MODEL_PROBE_TIMEOUT_S=3.0`、进程内记忆化、不可用/超时/不可解析一律 `unknown`），只出现在 `model set|show|doctor` 三个一次性命令，不进热路径。
8. **能力可见面（三态）**：`mw model show` 与 `mw doctor` 的每条角色行都带 `images=yes|no|unknown`；doctor JSON 的 `dispatch.images` 是唯一真源（缺 `dispatch.yml` 的早退分支仍**只**返回 `{"exists": False}`）。能力不匹配落 **suggestion** 而非 issue（落 issue 会让 `summary.healthy` 为假、`mw doctor` 退出码变 1，与"三情形退出码 0"互斥），且**只对 `vision` 角色发**——执行期实测发现初版对每个 `images=no` 角色都告警（本仓库一次 4 条常驻噪声 + 错误处方），已由 T-15 收窄并加回归。
9. **PM 主动知情**：`dispatch_worker` 的 `type` 参数描述此前只列 `'coding' | 'review' | 'research'`（**连已有的 `rag-research` 都没列**），现在补齐为 5 个类型并写明图片语义；`/worker` USAGE、`/mw model set` USAGE 的角色清单、`PARALLEL_PROTOCOL`（新增第 6 条）同步；L0 断言把「描述里的类型 token 集合 == `DISPATCHABLE_TYPES ∪ {"codex"}`」钉死，防止再次漂移。

## 目标收益

- **能力闭环**：此前"需要看图的 UI/界面任务"在框架里无角色、无提示、无门禁——PM 无从知道某模型能否读图，派出去只能等运行时降级。现在从「配置期拒绝 → PM 知情 → 派发期门禁/自动改道 → worker 运行期兜底 → doctor 可见」形成六段闭环，且每段都有 `[VERIFY]` 证据。
- **真视觉可用性已实证**：真实调用 `timi/deepseek-v4-flash-vision-exp` 读一张 64×64 纯红 PNG，回答 `red square`，会话 JSONL 里出现图片内容块（`"type":"image"` + base64）而非降级行（L2-2）。
- **回归面**：Python 触达面 **203 passed / 2 failed**（两红为已定位基线 E-04/E-06，本 key 引入红 = 0）；TS 触达面 **201 passed / 0 failed**（独立复核跑 5 文件 210 passed）；`npx tsgo --noEmit` rc=0；biome `--error-on-warnings` scoped 9 文件与宽面 317 文件均 rc=0。
- **独立质检**：由**独立 review worker**（非 PM）完成 QG 审查，自算 AC/VC 矩阵、脚本逐元素复算两侧镜像、10 例对抗式反例、自做变异验证测试非空洞性 ⇒ `acs_total=18 acs_pass=18 invariant_violations=0 blockers=0`，结论 `PASS-WITH-NITS`。它在过程中抓出并促使修复了 2 个阻塞（`tsgo` 4×TS2741、VC-003/VC-007 缺证）。
- **执行期自查抓到的两处真实缺陷**（均由"单测绿 ≠ 真机正确"暴露）：① T-12 的 doctor 告警范围溢出（真实仓库 4 条噪声，测试因 `any(...)` 断言抓不到）→ T-15 收窄 + 回归；② VC-017 期望串逻辑不可满足（`type: vision` 源角色==目标角色）→ 拒绝写假来源 `auto-route: vision -> vision`，修正期望串并回写 design。

## 遗留

- **扩展 bundle 未重建（B2，需用户授权）**：全局 `~/.pi/agent/extensions/agent-team-loop.js` mtime 15:15，早于本 key 的 T-09，grep `IMAGE-CAP` = 0 ⇒ 运行中的窗口/服务加载的是**旧代码**，`mw doctor` 报 `bundle.stale=true`。因此 AC-011 的**活窗口路径**与 AC-015 的**活窗口 TS 渲染**只有单测/源 builtin 证据。动作：`/mw build`（`mw.py build --install`）后 `/mw restart`，再复验一次（源 builtin 用 `-ne` 的真进程 L2-1 已通过：`[IMAGE-CAP] … declared=images:yes`、`rc=1`）。
- **本仓库尚未配置 `vision` 角色**：`.mw/dispatch.yml` 只有 main/coding/review/research（`mw model show` 示 `vision: (unset) → … [window] images=no|yes`）。要让 `type: vision` 走**角色配置**（而非 window 回退），需 `mw model set vision timi/deepseek-v4-flash-vision-exp`。
- **`npm run check` 未按字面执行（⚠️-1）**：其第一步 `biome check --write .` 在多 key 并发的脏工作区会改写他人在飞文件；已逐条跑其只读组件全绿（全仓 biome `--error-on-warnings`、`tsgo`、pinned-deps、ts-imports、shrinkwrap、install-lock、browser-smoke）。建议把写模式与只读门禁拆分，或提交后在干净工作区复验一次。
- **N-2**：`planDispatchFrontmatter` 对非法 `images` 值（`maybe`/大小写变体）静默按"未声明"处理（用户可达路径 tool schema / `--images` 都已拒绝，纯函数层不可达）。fail-open 方向安全，可选择性加固为 fail-loud。
- **N-5**：`vision` 未配置时 doctor 不显示该角色行（"未配置 ⇒ skip"语义）；若要求未配角色也出行需另开需求。
- **N-6**：VC-014 的 `/worker` USAGE 与 `PARALLEL_PROTOCOL` 断言为子串级，弱于 token 集要求（严格集合断言只做在 `type` 描述上）。
- **N-3 / N-4 / N-7**：分别为 `worker.log` 依赖 launcher 捕获 stdout、`evidence-requirement.md` 与 readcap 套件的 VC 同号歧义、测试入口清单过期；均为文档/口径问题，已登记，不改行为判定。
- **既有基线红（与本 key 无关，未修）**：`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`（E-04，冻结副本 sha ≠ 脏工作区 HEAD）与 `::test_existing_regression_files_untouched`（E-06，另一 key `mw-autopilot-slot-capacity` 在改 `test_autopilot_config.py`；另含本 key T-03 的**授权**重冻，提交后消失）。
- **AC-017 期望串修正**：设计期写的 `routed=2` 逻辑不可满足，已改为 `type_unchanged=true effective_vision=2 auto_route_fired=1`（语义未变，仅计数口径），`design.md` §7 与 `evidence-requirement.md` 均已标注 `[REVISED @ 2026-09-26]`。
- **未提交**：本 key 的全部改动仍在工作区（未 commit、未 `git add`），与 `mw-autopilot-slot-capacity`、`mw-rag-integration-fix` 等并发 key 的脏文件共存于同一 worktree。

---

## 收口后状态更新（2026-10-09，提交 + 构建 + 干净检出复验）

上面「遗留」里的第一条（B2 陈旧 bundle）已处置，判定随之更新：

- **已提交**（分支 `dev/AgentTeam`）：`7a864c1c7`（feat：代码 + 测试，19 文件）、`5c1149f1b`（docs(agentic)：本 key 全部文档与证据）、`fd30eb8be`（fix：让 `render_task_md` 签名冻结断言与提交顺序无关）。并发 key 的在飞文件仍留在工作区未纳入（逐 hunk 归属后部分暂存）。
- **已构建并全局安装**：`python mw.py build --install --allow-dirty` ⇒ 全局 bundle 952,453 B（`IMAGE-CAP`/`auto-route` 标记已在），`packages/coding-agent/dist` 同步重建。
  - 因工作区含**并发 key 未提交的 src**，构建用了 `--allow-dirty`，故受跟踪产物 `packages/multi-workers/dist/extensions/agent-team-loop.js` 处于 modified 且**有意未提交**（待对方 src 干净后重跑 `mw.py build --install` 再提交，见 `handover.md` R2）。
- **构建后真进程复验（无 `-ne`，走安装后的 bundle）通过**：`pi-via-tsx rc=1`、`[IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes`、`trace.log` 有 `[ERROR]` 行、`output.md` 为「Task refused (image capability)」。⇒ ⚠️-3 的源码层/安装层证据已齐，仅剩「运行中的窗口重启后再看一眼」。
- **⚠️-1（`npm run check` 字面）** 与 **⚠️-2（活窗口 TS 渲染）** 仍未闭（后者需窗口重启）。3 项欠债与全部 NIT 已逐条写入 `handover.md`（R1–R6）。
- **干净检出复验（对 `fd30eb8be` 建 detached worktree）**：`test_dispatch_models.py + test_autopilot_readcap_injection.py` = **68 passed / 2 failed**，两红均为已登记基线（`test_baseline_left_end_bound` 冻结 sha 早于 HEAD；`test_existing_regression_files_untouched` 在本机 `core.autocrlf=true` 下把 live 文件字节（CRLF）与 `git show HEAD:`（LF）比对 ⇒ 环境性红。**该红在干净检出上也复现，证实 E-06 除并发 key 改文件外还含 CRLF 成分**）。`test_render_task_md_signature_shape` 在干净检出上由红转绿（本次修复本体）。`test_serve_doctor.py` 的 3 例 `TestUpdateIndexClaim` 在 detached worktree 里因 `.agents/skills/**` 未被跟踪而报 `FileNotFoundError`，属 worktree 环境伪影。
