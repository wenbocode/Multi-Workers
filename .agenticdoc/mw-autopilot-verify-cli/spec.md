# Spec: mw-autopilot-verify-cli

- key: `mw-autopilot-verify-cli`
- 建立：2026-09-26 · **修订：2026-09-26（spec 期 4 份 RQ 吸收后，AC 首稿 6 条被推翻重写）**
- 前置（deps）：`xkey-repair-mechanism`（已 DONE，`181a75332`）；dist 重建已由 `d52694cc4` 落地（详见 AC-009）
- 状态：SPEC v2（待用户确认 4 项定稿决策后锁 AC）
- spec 期证据：`evidence/research/spec-rq-plan-20260926.md`、`spec-cli-patterns-20260926.md`、`spec-config-write-contract-20260926.md`、`spec-dist-rebuild-20260926.md`、`spec-verify-cmd-portability-20260926.md`、`evidence/spec-dist-rebuild-performed-20260926.md`

## §0 Goal Alignment

- **对齐 goal.md**：goal.md 要求"文件驱动的去中心化协调"与"mw 后台服务常驻运行"。本 key 让 **autopilot 的 verify 命令成为可部署配置**（CLI 部署 + 机器级/项目级两层），使 `xkey_repair` 机制在多机器、多项目上可运维——否则每个项目、每台机器都得手写未跟踪的 `.agenticdoc/_autopilot/config.json`，机制等于不可部署。
- **GC 继承**：继承 `xkey-repair-mechanism` 的 D-007（conductor subprocess 跑验证）、D-009（两侧镜像 + 同版本上线）；继承 `mw model set/show` 的"配置即 CLI + show 打印有效解析"惯例；继承 RAG 的**机器层+项目层 merge + 逐字段 origin** 范本（`mw_common.py:374/378-396/483-521`）；继承 P-015 结论（**主载体必须是持久化文件，env 只作覆盖**）。
- **冲突声明**：无。本 key 不改 L3/gate/判定契约，不改 `run_verification` 的 `shell=False` 安全面，不引入常驻调度器（CLI 只在被调用时写文件）。与既有 `_autopilot/config.json` 两个写者（TS console）**有共享资源冲突**，故新增 AC-011 的锁语义（原 spec 未覆盖 lost update）。
- **预期收益**：①"部署 verify 命令"从手改 JSON 变成幂等命令；②跨机器有明确持久载体，换机器不改项目；③新机器 pull 后 dist 不静默落后（修 `update-env` 的 fail-open）；④`xkey_repair=true` 而命令为空时提前告警，而不是让工单全部卡死在 `verify_failed`；⑤修 verify 的根锚定错误（control≠partition 时取错根）。

## §1 功能概述

### 1.1 目标

1. 新增 `mw autopilot` 子命令组，首个能力 **verify 命令的部署与查看**：`set` / `show` / `clear`（形状照 `mw model`：二级组 + `dest="autopilot_action"`）。
2. 部署目标 = `<root>/.agenticdoc/_autopilot/config.json` 的 `xkey_verify_cmd` / `xkey_verify_timeout_s`（必要时含 cwd 键）；写入用**既有唯一与 TS 字节对齐的** `autopilot/config.py::save_config`，并补全全字段。
3. **跨机器可部署**：机器级默认层（`$HOME/.agents/...`，与 RAG `rag-servers.yml` 同构）+ 逐字段 merge + origin 报告；优先级 `cli > project > machine > default`。
4. **可移植命令**：list argv 逐元素 whole-token 展开（复用 `mw_common.render_toolchain_command` 的 token 语义，但**不照抄** dual/single 的"未知占位静默透传"）；声明式 cwd，缺省取 **partition 根**（修现状 `cwd=project_root` 的取错根）。
5. **防呆**：`xkey_repair=true` 且有效命令为空 ⇒ `mw doctor` 报 **issue**（翻 healthy、退出码 1）+ 文本含修复命令；timeline 首次事件去重。
6. **dist 同步与防复发**：tracked 产物与源码同步有机器判据；修 `mw update-env --apply` 只 copy 不 rebuild 的 fail-open；`mw build --install` 在脏树上默认拒跑。
7. **并发安全**：CLI 与窗口 `/autopilot enable|disable|pause|resume` 读写同一文件不得静默丢失更新。

### 1.2 技术栈 / 语言

- Python：`packages/multi-workers/mw.py`（argparse CLI）+ `autopilot/config.py`（配置层/缓存）+ `mw_common.py`（doctor 段、toolchain token 渲染）+ `autopilot/conductor.py`（verify cwd 消费点）。
- TS（仅镜像与产物）：`status-model.ts`（新键镜像）、`shared/xkey-gate-guard.ts` 已存在不动；`packages/*/dist` 为 tracked 构建产物。
- 构建：`mw build`（esbuild）+ `npm run build`（tsgo）——不新增构建栈。

### 1.3 核心用户场景

- **A 部署到项目**：`mw autopilot verify set --project <dir> -- python -m pytest -q`；随后 `mw autopilot verify show --project <dir>` 打印有效值与逐字段 origin；conductor 下一 tick（≤`poll_interval_sec`）即用新命令。
- **B 多机器**：机器级层写一次（`~/.agents/...`），项目未显式配置时继承；换机器只改机器级文件。
- **C 新机器 pull 后**：`mw update-env --apply` **真的重建** bundle 与 dist（现状只 copy → 刷新 mtime 报 healthy 的 fail-open 已修），并有"干净树上重建后 `packages/*/dist` 零 diff"的判据。
- **D 防呆**：`xkey_repair: true` 而命令为空 ⇒ `mw doctor` 直接报 issue + 给出 `mw autopilot verify set` 修复命令，不再让工单静默卡在 `verify_failed`。
- **E partition 项目**：verify 在 partition 根（代码所在）执行，而不是协调仓根。

### 1.4 范围说明（不做什么）

- 不做：xkey 机制本体（前一 key 已交付）、L3/gate 判定、`run_verification` 的 argv 语义与 `shell=False`（安全边界不回退）。
- 不做：自动推断项目测试命令（推断=猜，fail-open 方向；只做显式声明 + 校验）。
- 不做：`{python}` 占位绑 `sys.executable`（RQ-4 §6：随 serve 启动方式漂移、与项目 venv 错配、无法在 `show` 里报告 origin）——若将来要做，照 `MW_RAG_PYTHON` 形状另立。
- 不做：新建常驻服务/调度器；不做 GUI。
- 不做：`packages/*/dist` 的"孤儿产物清理"（`npm run build` 无 clean 是既有行为，避免扩大写面）。

## §2 业务约束

### 2.1 平台 / 环境

- Windows + PowerShell 主开发环境；Python 3.14；`mw` CLI 必须 cwd-independent，`--project` 一律显式必填（19/20 既有命令如此；**不引入 cwd 默认**）。
- 多会话共用同一 cwd：写面必须限定明确文件；不得跑全仓 `--write` 类命令（P-017）。

### 2.2 性能指标

- `set/show/clear` 为毫秒级文件操作；无网络。机器层+项目层解析为每 tick 常数级（缓存需含机器层 stat，见 AC-007）。
- dist 重建耗时以 `mw build` / `npm run build` 现状为准。

### 2.3 安全约束

- 写入**原子**（tmp+replace，复用 `save_config`）+ **互斥**（既有 `mw_common.lock_path/acquire_lock`，`O_CREAT|O_EXCL`）；锁不可得 ⇒ 报错 `return 1`，**不覆盖**。
- 配置非法时**拒绝写**（照 `mw model set` 的 "existing ... is unusable ... fix or remove it before writing" 先例），不把坏文件覆盖成看起来正常的文件。
- 不放宽校验：未知字段仍 fail-closed（`config.py:91-93` / `status-model.ts:139-143`）；新键必须两侧同步，否则**任一侧整体失效**。
- 机器层不得含凭证；命令仍以 list argv 存储与执行，禁止 `shell=True`。
- BOM：既有契约是 config.json **不支持 BOM**（读用 `utf-8`，带 BOM 即 `ConfigError`）——写入侧不得引入 BOM。

### 2.4 集成依赖

`autopilot/config.py`（DEFAULT_CONFIG/validate/cached_load/save_config）、`autopilot/conductor.py`（`_xkey_run_verify:3448-3472`、S3 目标锚定 `:3651`）、`mw.py`（argparse `:4643+`、`cmd_doctor:499-525`、`cmd_update_env/_apply_update_env:4509-4560`、`_deploy_bundle:3609-3632`）、`mw_common.py`（`doctor_report:2088-2126`/`_doctor_issues:2012-2085`/`format_doctor_text:2128+`、`render_toolchain_command:2866`、`machine_rag_servers_path:378-396`）、`status-model.ts`（6 处同步点）、`UPDATE.md`/`README.md`、`packages/*/dist`（tracked 产物）。

## §3 验收标准（AC）

> 全部按"可机械判定"重写（RQ-1/RQ-2/RQ-3/RQ-4 批判已吸收）；每条标注判据与现状是否已满足。

- **AC-001（set 写 argv）** 命令形状定死为 `mw autopilot verify set --project <dir> -- <argv...>`：`--` 之后的 token **逐字**（含以 `-` 开头的 token）进入 `xkey_verify_cmd`；`--project` 出现在 `--` 之后时**必须报错**（不得被静默吞入 argv）；写入前用 `{**default_config(), **existing}` **补全全字段**（消除 partial 文件导致的 `mw.py:161`/`conductor.py:3975` KeyError）。判据：argparse 级两用例 + 写入后文件含全部 12 键。
- **AC-002（规范化形状与幂等）** 未被触碰字段的**值**不变（不承诺字面格式——两个既有写者都会规范化）；连续两次同参数 `set` 后，文件与 `save_config` 的规范形状**逐字节相同**。判据：`test_autopilot_config.py:91-103` 形状 + 字节比较。
- **AC-003（拾取 ≤1 tick，含同尺寸改写）** 同一 conductor 进程连续两次 `tick()`，之间由**另一进程**写入**同字节长度**的不同命令（不用 `os.utime`、不清缓存）⇒ 第二次 tick 使用新命令。**现状会红**（RQ-2 实测 300 次同长改写有 100 次 stale：`cached_load` 的 `(mtime_ns,size)` 判据不完备）⇒ 本 key 必须修缓存判据。
- **AC-004（show 有效解析 + origin）** `show` 打印：项目配置路径与存在性、`xkey_verify_cmd`/`xkey_verify_timeout_s`（+cwd）的**有效值**、逐字段 `[origin]`（值域 `{cli, project, machine, default}`）。判据：文本行断言（照 `mw model show` `[source]` 形状）。
- **AC-005（clear 语义）** `clear` **只移除本 key 引入的 xkey 键**，其它字段值不变，且**永不删除文件**（"文件缺失 = autopilot 从未启用"是既有语义，`config.py:8-9`/`monitor.ts:79`）；键原本不存在时打印 `nothing configured` 并**不写文件**（照 `mw.py:3182-3184`），退出码 0。
- **AC-006（两侧校验差分真值表 + 跨侧字节一致）** 定义 payload 语料（合法全量/partial/未知键/bool 当 int/`4.0`/`4.5`/范围边界/空与非空 list），逐条断言 Python `validate_config` 与 TS `validateConfigData` 结论**一致**（现状 `4.0` 不一致：Python 拒、TS 收 ⇒ 必须先统一）；同一配置由 Python `save_config` 写、再由 TS `saveConfig` 覆盖后**字节相同**（含非 ASCII 组合；现状 Python `ensure_ascii=True` 与 TS 原样 UTF-8 不等 ⇒ 需统一）。
- **AC-007（机器级层 + 优先级真值表）** 机器层路径解析顺序同 RAG（`MW_<X>_FILE` → `MW_<X>_HOME` → `HOME` → `USERPROFILE`，缺失即层空且**不建目录**）；优先级 `cli > project > machine > default`，逐字段 origin 可断言；机器层未知字段的行为**显式定义**（建议：只告警不作废——RAG 的"整份作废"会让一个 typo poison 所有项目）；缓存键必须包含机器层的 `(path, mtime_ns, size)`，否则机器层改动不生效。
- **AC-008（防呆：doctor issue + 修复提示 + timeline 去重）** "有效命令为空" = 层级解析（含占位展开）后 argv 为空；fixture `{enabled:true, xkey_repair:true, xkey_verify_cmd:[]}` ⇒ `mw doctor --json` 暴露机器字段（如 `report["autopilot"]["xkey_verify_missing"]==true`）、文本含修复命令 `mw autopilot verify set`、**summary 为 not healthy 且退出码 1**（判定为 issue：显式启用后功能必然失效，属链路正确性，不是便利配置）；`xkey_repair=false` 或命令非空 ⇒ 无该告警（防误报）；timeline 首次满足时追加一条事件且**状态未变不重复**（计数 == 1）。
- **AC-009（dist 同步与防复发）** 四条子判据：**(a)** 干净工作树上 `mw build --install` 后 `git diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist` 为空；**(b)** 三处产物（repo bundle、`coding-agent/dist/.../status-model.js`、`.../shared/xkey-gate-guard.js`）的 kind 集合等于源集合，且 bundle 含 guard **行为标志**（`xkey-gate-guard: blocked` / `[XKEY_GATE]`，不是路径注释）；**(c)** 新增 repo-bundle 锚点（**内容判据**，mtime 判据会漏内容陈旧）并使 `mw update-env --apply` 的修复路径**先 `_build_bundle()` 再 `_deploy_bundle()`**（现状只 copy，刷新 mtime 后复查报 healthy = fail-open，RQ-3 §3.2）；**(d)** `mw build --install` 在 `packages/coding-agent/{src,dist}` 有未提交改动时默认**拒跑并提示**，`--allow-dirty` 显式绕过（防他人未提交 TS 被静默编进 tracked 产物）。
- **AC-010（文档，可机器判定部分）** `UPDATE.md` §2 指令矩阵加行（层级列 = 项目/机器）；`README.md` 加机器层/项目层两行对照表（照 RAG 段 `README.md:258-267`）；可机器判定的部分照 `test_rag_docs.py:157-189` 做 fenced block 与 CLI 输出的逐字节比对（至少 usage 行）；"文档与 `--help` 语义一致"作为人工评审项（README/UPDATE 不被任何测试读取，不假装有机器判据）。
- **AC-011（并发写 lost-update 防护）** CLI 的 read-modify-write 必须进既有锁临界区（`mw_common.lock_path/acquire_lock`，`O_CREAT|O_EXCL`）；锁不可得 ⇒ `[mw autopilot verify set] Error: ...` + `return 1` 且目标文件**字节不变**。判据：模拟锁占用 + 并发两写者（CLI vs 桩 console 写）后断言两处改动都在或明确失败，**不得静默丢失**。
- **AC-012（默认零扰动）** 不调用新 CLI 时既有行为逐字不变：现有默认套件零新增失败（基线 `d52694cc4`）；`xkey_repair` 未启用时新增 doctor 段不改变既有输出语义。
- **AC-013（verify 根锚定修复）** 新增声明式 cwd 键（枚举 `control|partition|parent|<root name>`，或同占位集合的路径串），**缺省 = partition 根**（partition 模式；其它模式 = control 根），替换 `conductor.py:3459/3471` 的硬编码 `project_root`；真值表**必须含 `control ≠ partition ≠ parent` 的 fixture**（E2 是 `control == partition` 的退化用例，单用它不能证明修复），并含 E2 形状回归（断言 verify cwd = `H:\git\E2Feature`、parent = `E:\UEMigrator`）；**同族根锚定一并处理**：S3 的目标文件锚定（`conductor.py:3651` 的 `project_root / target_rel`）按同一根解析，否则只修一半。
- **AC-014（占位符逐元素展开）** 复用 `mw_common.render_toolchain_command` 的 token 语义，但展开域为 **list argv 逐元素、whole-token**（不做 shell 分词/引号）；未定义占位 **fail-closed**（错误文本照 `mw_common.py:2910-2912` 形状，且**写入侧 CLI 与消费侧 conductor 行为一致**）；**不照抄** dual/single 的"未知占位静默透传"怪癖；`{python}` 不提供（见 §1.4）。

## §4 已定稿决策（U-1…U-6）

**确认记录（2026-09-26，用户回复「按建议」）**：下表中每条决策**按其「我的建议」执行**，即 U-1 纳入机器级层、U-2 纳入 AC-013/014、U-3 dist (c)(d) 全纳入、U-4 Python 改 `ensure_ascii=False` 且两侧统一口径（**具体统一方向由 design 期 RQ 定稿**：TS 侧 `JSON.parse` 会把 `4.0` 与 `4` 归一为同一 number，若经核实不可逆，则改为 Python 接受整值 float 以对齐 TS——以 RQ 实测为准）、U-5 clear 永不删文件、U-6 AC-008 判 issue。

- **U-1 机器级默认层是否纳入本 key**：纳入=一次到位、真正跨机器；不纳入=scope 更小但"跨机器"仍靠手配项目文件。**我的建议：纳入**（用户上一轮提问正指向此）。影响 AC-004/007。
- **U-2 AC-013/AC-014（cwd + 占位符）是否纳入本 key**：这是**独立于 CLI 的既有缺陷**（RQ-4 实测：worker cwd = partition 根 `launcher.py:906`，verify cwd = control 根 `conductor.py:3459`；配置层不强制两者关系 `mw_common.py:2578-2589`）。**我的建议：纳入**——CLI 部署的正是这条命令，部署一条"在错的根上跑"的命令等于交付半成品；若你认为该另立 key，我把它移出并只保留 CLI+部署面。
- **U-3 AC-009(c)/(d) 是否纳入**：只做 (a)(b) 是"一次性对齐"（`d52694cc4` 已做），(c) 才修根因（update-env 的 fail-open），(d) 是多会话安全护栏。**我的建议：全纳入**。
- **U-4 AC-006 的两侧差异如何统一**：建议 Python 侧改 `ensure_ascii=False`（对齐 TS 字节）+ 两侧对整值 float `4.0` 统一为**拒**（Python 已拒；TS 改拒 = 更严格、不影响合法 payload）。若你倾向"不改 TS 校验"，则 AC-006 改为"差异登记在案 + 只对合法 payload 断言一致"。
- **U-5 clear 的终局**：本 spec 已定稿为**永不删文件**（只删键）——若你希望"只剩默认值时删文件"以恢复 `everEnabled=false` 语义，请指出（会改变 AC-005）。
- **U-6 AC-008 判为 issue（翻 healthy）还是 suggestion（不影响退出码）**：既有惯例把"便利配置"降为 suggestion（`mw_common.py:2063-2067`），而 `xkey_repair=true` 是**显式启用**且必然导致工单全卡死 ⇒ 我判 **issue**。若你要求与既有惯例一致（suggestion），AC-008 的断言相应放宽。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- `mw model set/clear/show`（`mw.py:4722-4736` + `_model_write:3116-3126` + `show:3205-3230`）：CLI 形状与"有效解析 + `[source]`"输出范本。
- `mw rag`（`mw.py:1210-1256`）与 `mw_common.py:374/378-396/483-521`：机器层+项目层 merge + 逐字段 origin 范本（可直接照抄骨架与坑清单）。
- `autopilot/config.py::save_config:136-148`：唯一与 TS 字节对齐的写助手（原子 + LF + indent2 + 校验）。
- `mw_common.lock_path/acquire_lock:1438/1480-1493`：既有 `O_CREAT|O_EXCL` 锁（AC-011 直接复用）。
- `mw_common.render_toolchain_command:2866`：占位渲染单点（AC-014 复用语义、不照抄静默透传）。
- `mw update-env` 的 check dict 形状 `{id,layer,status,detail,fix,auto}`（`mw.py:4322-4323`）：AC-008 的"含修复提示"模板。
- 测试形状：`test_dispatch_models.py:422-485`（Namespace 直调 + capsys + doctor 断言）、`test_rag_init.py:63-104`（真子进程 + hermetic env + sha 快照）、`test_mw_target.py:37-70`（全树快照断言"只写目标文件"）、`test_autopilot_config.py:91-145`（原子写/缓存失效）。

### 需规避坑点

- **P-015**：env 不落盘 ⇒ 机器级层必须是文件；env 只作覆盖（`MW_RAG_PYTHON` 形状）。
- **P-016**：新增测试不得只验"字段被写入"，必须验消费侧生效（conductor 拾取）与非空洞对照。
- **P-017**：`npm run check` 全仓 `--write`；`npm run build` 亦写 953 个 tracked dist 文件（RQ-3 §5）⇒ 脏树上构建会污染他人未提交代码（正是 AC-009(d) 的动因）。
- **P-001/P-003**：PowerShell 多行 `python -c` 撕引号（本轮已再踩一次）⇒ 用临时脚本；写文件用原子写。
- **RQ-2 §3.3**：`cached_load` 的 `(mtime_ns,size)` 判据不完备（同长度改写可被静默忽略，实测 1/3）——**不要**把它当 AC 判据。
- **RQ-2 §5.2**：两侧差异 D1（`4.0`）/D2（partial merge）/D3（规范化）/D4（非 ASCII 字节）——新增键或改校验时必须同时处理，否则 AC-006 红。
- **RQ-1 §1.3**：argparse REMAINDER 会吞 `--project`（`mw.py:983-985` 自记此坑）；`load_config` 不补默认键 ⇒ partial 文件会让 serve/conductor KeyError。
- **RQ-3 §3.2/§5**：`mw update-env --apply` 只 copy 不 rebuild（fail-open）；`npm run build` 无 clean、无锁，失败时"全局已换、dist 未换"的部分部署。
- **RQ-4 §2.3/§1.4**：verify cwd 取错根（control≠partition 时）；dual/single 模式下未知占位静默透传——两条都不要照抄。
