# Achieved: mw-autopilot-verify-cli

key: `mw-autopilot-verify-cli` · phase: execute→verify · 基线: `b0a30bc12` / `d52694cc4` · ac_fingerprint `9c90fbb3e171` · 覆盖 HEAD `8cd472a7b`

## 系统行为变化

**新增功能（默认关闭；xkey 通道本身是 per-project opt-in，本 key 不改这个前提）**

1. **`mw autopilot verify set|show|clear`**（`mw.py`）——xkey 验证通道的项目侧写入口，不再需要手编 JSON：
   - `--project` **必填且必须在 `--` 之前**；`--` 之后的 token **逐字**成为 `xkey_verify_cmd`（不分词、不解释引号，`-x` / `--flag` / `a b` / `-` / `--` / 空串都原样保存）；
   - `set` 把文件补全到 **13 键**（`{**default(), **raw, **changes}`）、同参数重复写**字节幂等**、`--dry-run` 只打印不落盘；`show` 给出逐字段 `[origin]`（`project`/`machine`/`default`）与 `--json`；`clear` **只移除自己管的四个 xkey 键、永不删除文件**（文件缺失 = 从未启用 ⇒ 打印 `nothing configured` 并 return 0，不建目录不写文件）；
   - 错误一律 `[mw autopilot verify <action>] Error: ...` + `return 1`；`--timeout < 1`、`--` 后空 argv、非法 cwd 根名、含 AI 占位符的 argv **在取锁前**拒绝；
   - 只读动作（`show`）零足迹：不建 `.mw/`。

2. **机器级配置层**（`autopilot/effective_config.py` 新模块）——`~/.agents/autopilot-defaults.json`，解析顺序 `MW_AUTOPILOT_FILE` → `MW_AUTOPILOT_HOME` → `HOME` → `USERPROFILE`（**`MW_AUTOPILOT_FILE` 指向的文件不存在时不回落**）：
   - **只允许**覆盖 `xkey_verify_cmd` + `xkey_verify_cwd`（机器相关、项目无法预知的两个键）；越域键（`xkey_repair`/`xkey_verify_timeout_s`）⇒ **告警并忽略**；
   - 规则 **「空值即未决定」**：`[]`/`""` ⇒ 让给机器层；项目层非空 ⇒ 项目胜出；两层皆空/缺失 ⇒ 内置默认；
   - 机器层 **fail-soft**（逐字段丢并记诊断，绝不整份作废）；项目层 **fail-closed** 且**先于** merge 生效；
   - `load_effective(root, env) -> .values/.origins/.diagnostics/.machine_path`；**只读路径从不创建目录**。

3. **verify 根锚定修复**（`conductor.py`）——新增第 13 个配置键 **`xkey_verify_cwd`**（`""`=auto=worker cwd 规则：partition→partition 根、dual→game 根、single/legacy→control 根；或显式 `control|game|engine|partition|parent|<root name>`；未知根名 ⇒ `invalid-config` 且**不执行 verify**）：
   - verify cwd 由硬编码 `project_root` 改为解析后的工作区根；**同族 5 个路径锚点一并重锚**（冻结块定位、目标文件 sha、提案里的绝对 target、apply 的 root、S3 `target` 存在性判断）；
   - **协调产物仍锚 control 根**（ledger/tickets/evidence/runs/timeline 不变）；ticket 新增 `argv`（展开后）+ `cwd`；
   - partition 模式下原先"apply 写错位置 → verify 失败 → 工单永不闭合"的死局被消除。

4. **并发写锁**（两侧同路径 `<root>/.mw/autopilot-config.lock`）——CLI 与 extension console 的 **read-modify-write 进同一把锁**（`retries=6`、`base_delay=0.02`；TS `baseDelayMs:20`）；锁在 **RMW 站点**（不在 `save_config` 内部，原语不可重入）；锁不可得 ⇒ 报错 + `return 1` 且目标文件**字节不变**；残锁不自动抢占；只读不加锁不建目录。
   - 实测的既有缺陷：两个 console 写者 30 轮丢 **28** 次更新；两个 TS 写者单独也能在 30 轮内硬失败。

5. **dist 防复发 + 脏树护栏**（`mw_common.py` + `mw.py`）：
   - **A1b**：repo bundle 判据从 mtime 升级为**内容**（kind 集合 + guard 行为标志 `xkey-gate-guard: blocked` / `[XKEY_GATE]`），mtime 刷新不再能骗过检查；
   - **A2b**：新增 `pi-dist-content` 判据——把 `packages/coding-agent/dist/**/*.map` 的 `sourcesContent` 与当前 `.ts` 源逐字节比对；**落地当天即抓到真实漂移**（`console.ts`/`status-model.ts`，4/472）；
   - `mw update-env --apply` 的修复路径改为**先 build 后 deploy**（build 失败 ⇒ 不部署，消除 fail-open）；`_deploy_bundle` 先重建 dist 再 copy 全局副本（消除部分部署）；
   - `mw build --install` / `mw bootstrap` 在 `packages/*/src` 有未提交改动时**默认拒跑**（避免把别人未提交的 TS 编进 tracked 产物），`--allow-dirty` 显式绕过并打印提示；非 git 目录跳过。

6. **两侧一致性判据（跨语言）+ 文档**：
   - 共享语料 `test/fixtures/autopilot-config-corpus.json`（53 例，sha256 `951987eaf2abebfa256365ed6642ce1ae0b077a2a6a6c18b4f974729c7dc594d`，D1–D6）驱动两侧：**同判 53/53**、**31 例规范化写字节 sha256 相同**、P3 双向幂等 31/31、P5 键序/默认值/类型/范围逐字镜像（bool 3 / list 1 / str 1 / int 8）、P6 原始视图与解析视图**两侧分层断言**；
   - TS `readConfig` 用 `context.source` 拒非整数数字字面量（`4.0`/`4.00`/`1e2`/`1E2`/`-0.0`），与 Python 判定对齐；`save_config` 改 `ensure_ascii=False`（两侧产物可字节相同）；
   - `test_autopilot_docs.py` 把 README 的 fenced `--help` 块与真跑 CLI 输出**逐字节**钉住（417B），并锚定 12 条已定稿语义句；UPDATE.md 补 CLI 行（层级列=项目/机器）与 A1b/A2b 锚点行。

**影响面**

- **关闭时（默认，且当前无任何项目 opt-in）**：既有行为逐字不变。判定套件 `2 failed, 1182 passed, 10 deselected`——红的**集合与基线完全相同**（两条外部既有红）；`e2e_l2 8 passed`；`packages/coding-agent` 6 个相关 vitest 套件 `101 passed`。
- **配置语义**：13 键（新增 `xkey_verify_cwd`，序尾，默认 `""`）；`load_config` **不补默认**（原始视图），完整视图走 `default_config()` / `load_effective()`——**两个视图同时存在且各自有判据**（这是撤回 D-004 后的定局）。
- **消费侧**：conductor 4 个读配置点切到有效层（机器层命令**真正被执行**，实测捕获 argv 逐字等于机器层命令）；`dispatch._read_scope_caps` 走有效层但**存在性仍判项目层原始键**（保住更早 key 的冻结判据）；doctor 新增 autopilot 段（两层 + origin + 机器层路径 + 越域 issue + 修复串）。
- **构建产物**：`packages/multi-workers/dist/extensions/agent-team-loop.js` 与 `packages/coding-agent/dist/**`（共 9 个 tracked 文件）随本 key 重建并提交；**其它已在运行的 pi 窗口需重启 serve 才加载新 bundle/dist**；两侧必须**同版本上线**（旧 bundle 读含 `xkey_verify_cwd` 的文件会 fail-closed）。

**验证证据**

| 层 | 结果 |
|---|---|
| AC-009(a) dist 重建后 diff | **PM 亲验 `git -c core.fileMode=false diff --exit-code` = 0（空）** |
| A1b / A2b | `{"stale": false, ...}` / `{"stale": false, "detail": "sourcesContent matches for 472 source(s)"}`（A2b 由执行期 `stale=true` 4/472 转绿） |
| 默认套件 | `2 failed, 1182 passed, 10 deselected`（红集合 == 基线） |
| e2e_l2 | `8 passed` |
| coding-agent vitest（6 套件） | `101 passed` |
| AC-010 文档判据 | fenced block 417B 逐字节 + 12 语义锚点 + UPDATE 矩阵行 + A1b/A2b 行（4 passed） |
| AC-013 真值表 | 30 行（3 模式 × 4 互异根 × 8 选择子 × 5 argv 形态），失败行断言 spy 零调用 |
| 跨语言语料 | sha256 `951987ea…`，53 例，P1 53/53、P2 31 sha 相同、P3 31/31 双向幂等 |
| 非空洞对照 | **每卡一条**（13 张卡各自的反证变红记录，见 `evidence/runs/verify-20260926-evidence-collection.md` §F） |

## 遗留

| # | 遗留 | 去向 |
|---|---|---|
| 1 | **两条既有红不属本 key**：`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`（该 key 自留的 `dispatch.py` 冻结副本已陈旧，与 HEAD blob sha 不等）、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`（读 live 外部项目 `H:\git\E2Feature`） | 基线 `b0a30bc12` 即红；本 key 全程保持"红集合不变"，未修（不属本 key 写面）。已在质量门禁报告 §E 与证据汇总披露 |
| 2 | **没有任何真实项目启用 xkey 通道**：FM/E2 的 `_autopilot/config.json` 无 xkey 键，MW 无 `_autopilot/` ⇒ "真项目 opt-in 后由 xkey 修复闭合工单"的端到端未实测（L2 合成链路已覆盖，含 partition 根锚定与机器层命令消费） | 启用前必须先配 `xkey_verify_cmd`；建议下一 key 在 E2 上做一次真实 opt-in 演练 |
| 3 | **`>2^53` 整数字面量值域残差**：`2**53`/`2**53-1` 两侧一致且已入语料；`2**53+1` 两侧会分歧（JS 舍入 vs Python 精确） | **判定为不修，只记录**（design §11 + `_pitfalls.md` P-022）；**刻意不把分歧值放进语料**，避免把错误行为固化成契约 |
| 4 | **机器层只支持两个键**（`xkey_verify_cmd`/`xkey_verify_cwd`）；`xkey_repair`/`xkey_verify_timeout_s` 越域即告警忽略 | 设计决策（用户选项 1）：bool 机器层硬开会造成项目无法关闭；timeout 材料化后无法区分"显式默认"与"未配置"。若将来需要，须先让材料化写侧保留"未配置"标记 |
| 5 | **`evidence/baseline/` 目录未建**（本 key 的基线值记在 `evidence-requirement.md` 与证据汇总 §A1） | 质量门禁记为验证欠债 1 项（非阻断）；后续 key 建议统一建该目录 |
| 6 | **本 key 的提交只 commit 未 push**（`b0a30bc12`..`8cd472a7b`，本 key 22 个；连前两个 key 共 21 个未推送） | 待用户指令 |
