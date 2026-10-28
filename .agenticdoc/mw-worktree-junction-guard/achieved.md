# achieved.md — mw-worktree-junction-guard

- key: `mw-worktree-junction-guard`（2026-10-13 收口）
- 背景：2026-10-09 `git worktree remove --force "$env:TEMP\qg-head"` 穿透 `node_modules` junction，删掉共享主树 **3,456** 个已跟踪文件（事故取证见 `mw-workspace-incident-probe`）。
- 本 key 的目标：让该形态**不可达**——工具层拦截 + 正规命令 + 巡检 + 采样告警 + 仓库自带脚本堵口 + 运行面激活自检，共 **6** 组（G1..G5 与 G6；G6 为 2026-10-14 负空间审计后追加）。
- AC 逐条勾销与证据链判定**不在本文**：引用闭包范围内的 13/13 ✅ 见 `evidence/quality-gate-report-20261013.md`（独立 QG worker）；该 ✅ **限定于“逐条引用闭包”这一方法**，负空间面（该有而没有 / 有而无人引用 / 危害面三态）由第二审计 `evidence/negative-space-audit-20261013.md` 独立补审，其 6 项新发现中的 4 项（N-01/N-04/N-05/N-06）已在本轮处置或记为债；第三审计 `evidence/delta-adversarial-audit-20261013.md`（方法 = **对抗性证伪**，43 条攻击向量）结论 AC-014 站稳 / AC-016 站稳 / 部署站稳 / **AC-015 有裂缝**（已按 D-17 修复），并新枚举 6 条逃逸形态（1 条按 D-19 修复、4 条按 D-20 接受为边界）。三次审计方法互不重叠：引用闭包（QG）/ 负空间（W-12）/ 对抗性证伪（W-15）。

## 系统行为变化

**工具层（packages/coding-agent，需 `mw build --install` + 窗口 `/reload` 生效）**

- **新增 G1 拦截闸**：`shared/worktree-junction-guard.ts`（`registerWorktreeJunctionGuard`，注册点 `index.ts:70`（`:61-69` 为注释块），位于双加载 flag 之后、PM/Worker 分支之前 ⇒ PM / worker / 交互三种模式全覆盖）。
  - 拦 `git worktree remove|rm`（含 `--force`、`-C`/`cd`/`Set-Location` 基准、插值、通配/尾分隔符 ⇒ fail-closed）。
  - 拦**删除穿透形态** `rm -rf <dir>/`、`rm -rf <dir>/*`、`Remove-Item -Recurse <dir>\*`（决策 D-11；非 worktree 目标给第二套文本，处方逐条 `cmd /c rmdir "<link>"`）。
  - 目标树用显式栈 + `lstatSync` 扫描（不跟链、不进命中目录、20 万条预算、枚举失败 ⇒ `scan-error` 拦截）。
  - 阻断文本含**可照抄**的正规命令：注册 worktree ⇒ `mw worktree rm "<worktree>"`；否则 `cmd /c rmdir "<link>"`。拒绝写入任务 `trace.log` 的 `[WORKTREE_GUARD]` 行。
  - **误拦面**：`rm -rf <link>`（无尾分隔符）、`rmdir /S`、`robocopy /MIR` 按实测（不穿透）**保持放行**；`sudo`、`bash -c` 等静态不可判定形态明文不覆盖（见遗留 1）。
- **新增共享件**：`shared/bash-segments.ts`（D-3，从 `implementation-gate.ts` 抽出的分段/转义解析，两闸共用一套 shell 词法）。
- 影响面：所有在该仓库运行的 agent 窗口的 `bash` 工具调用；不改写权限、不拦读取、不改 `checkBashWriteTarget`/`WRITE_VERBS`。注册点数量由 6 变 **7**（`pi.on("tool_call")`，实测坐标见 §验证入口）。

**命令行（packages/multi-workers，Python 侧 / `mw serve` 重启后生效）**

- **新增 G2 `mw worktree add|rm|list`**（`worktree_cmd.py` + `worktree_registry.py`）：`add` 默认**不建链**，`--link-deps` 才建并把 `link/target/worktree/repo_root/created_at/created_by` 登记到 `<project>/.mw/worktree-registry.json`；`rm` 是六步事务（快照 → **先全量分类再动任何东西** → 摘链（`cmd /c rmdir`，无 `/S`）→ 重取快照/变了就 abort → 才 `git worktree remove --force` → 前后表格）。**没有** `--force`/`--continue`/跳步开关，abort 打 `ABORT at step N/6` 并保留现场；`foreign`（目标不属于本仓的链）⇒ 零摘链中止。影响面：任何删除 worktree 的操作者；旧写法仍可用但在 G1 面前会被拦。
- **新增 G3 `mw doctor` 的 `worktree_links` 段**（`worktree_doctor.py` + `mw_common.py` 三处）：默认域 = 注册表（`link` 在而 worktree 不在 ⇒ `leftover`；`link` 不在 ⇒ `stale-entry`）+ 仓内 `node_modules/*` 顶层；`%TEMP%` 全域猎捕走显式开关 `--worktree-scan-roots`。两条防误报判据：仓内域**减去** `package-lock.json` 的 `"link": true` 期望集（D-10，本仓 14 条正常 workspace 链静默）；开关域**跳过** worktree 仍存活的已登记链（D-12）。影响面：`mw doctor` 退出码会在**真有遗留**时变化；干净仓库逐字节不变（本仓实测 rc=1 与改动前一致、零 `worktree_links` 行）。
- **新增 G4 launcher 采样**（`tree_watch.py` + `launcher._poll_once`）：每 6 个 poll（默认 30s，`PI_TREE_WATCH_SEC` 覆盖，`0` 关）比对「已跟踪文件数」与「worktree 链清单」样本，骤降/断链 ⇒ 告警。影响面：`mw serve` 的 poll 循环多一次只读采样（失败仅记日志并跳过，不影响 beat）。
- **修 G5 `scripts/diff-model-catalog.mjs`**（`npm run diff:model-catalog`，AC-013）：`git worktree remove --force` 前先摘 `<wt>/node_modules` 链并 `lstatSync` 自检，失败则中止（跳过 remove 与临时根删除、`exitCode=1`、打印手工 `cmd /c rmdir`）。影响面：该脚本失败时**保留现场**而非删树；成功路径不变。

**运行面激活与可见性（G6，2026-10-14，决策 D-13/D-14/D-15；Python 侧 / 需 serve 重启与窗口 `/reload` 生效）**

- **AC-014 `user_bash` 通道**：`shared/worktree-junction-guard.ts` 的注册函数在 `pi.on("tool_call")` 之后**并列**挂 `pi.on("user_bash")`，复用同一 `decideWorktreeRemove(command, event.cwd, process.env)` 与同一套阻断文本/处方/trace；`block` ⇒ 返回 `{result: BashResult}`（pi 视为该命令的整体替换 ⇒ 命令体根本不 spawn），否则 `undefined`（不干预）。覆盖 TUI `!`/`!!` 与 RPC；事件名/字段/短路键取自 `node_modules` 实测（`types.d.ts:615`、`runner.js:720`）而非猜测。影响面：用户直敲命令里的危险形态由“完全不被检查”变为被拦；干净命令与处方命令实测放行。
- **AC-015 注册表损坏可见**：`worktree_doctor.py` 把 `registry_error` 镜像为段级字段；`mw_common._doctor_issues` 消费（issue ⇒ 影响 rc），`format_doctor_text` **即使 `count==0`** 也打印 `worktree_links: REGISTRY-ERROR <path>: <err>`。此前坏文件被静默当空表（与 design §5.1 矛盾）。影响面：注册表损坏时 `mw doctor` rc 变化；健康/不存在时逐字节不变。
- **AC-016 激活自检**：`mw doctor` 新增 `activation` 段（标记 `reparse-point` = G1 `basis` 字面量），判定两份扩展 bundle 是否含 G1 能力；缺失/不可读 ⇒ `guard-not-deployed` issue + `activation: MARKER-ABSENT|UNVERIFIABLE` 行 + 可照抄 `mw build --install`；serve 半**复用**既有 `serve code: STALE CODE`（不新增进程探针）。适用域 = 拥有 `packages/coding-agent/src/extensions/agent-team-loop` 的项目（避免对任意项目误报）。影响面：从此“护栏没生效”这件事本身可被机器发现，而不是只在事故后才发现。
- **部署记录（2026-10-14，PM 执行）**：`mw build --install --allow-dirty` ⇒ 两份 bundle **1,115,336 → 1,136,103 B**（tracked `packages/multi-workers/dist/extensions/` 与全局 `~/.pi/agent/extensions/` 一致），实测 `'reparse-point'`=1、`worktree`=25、`"user_bash"`=2 ⇒ **G1+AC-014 的代码已进入 pi 实际加载的产物**；`mw doctor` 的 `guard-not-deployed`/`activation:` **自动归零**（正是 AC-016 的验收方式）。**caveat**：部署时工作树有 49 个未提交文件（含其它 key 的在制品），故此 bundle 是**脏树快照**；各窗口仍需 `/reload` 才加载新 bundle。
- **部署完成记录（2026-10-14，第二轮 + 运行面激活）**：W-17 改动 guard 源码后重跑 `mw build --install --allow-dirty` ⇒ 两份 bundle **1,136,103 → 1,136,749 B**（仍含 `reparse-point`=1、`"user_bash"`=2）；随后在**无任何 worker 在跑**的窗口内 `mw stop` + `mw start`（旧 serve PID 49540 → 新 **151032**）。**验收实测**：`mw doctor` = **rc 0**、`serve code: fresh`、`bundle: stale=False`、`summary: healthy`、零 `activation:` 命中；**`.mw/tree-watch.json` 首次出现**（4,538 B：`tracked_total=5061`、`tracked_non_dist=2822`、`threshold=28`、`delta=0`、`events=[]`、`alarms=[]`、**`links`=14**）⇒ G4 采样真正生效，且采样器独立数出的 14 条链与 lockfile `"link": true` 期望集一致。

**共享判据（本 key 定稿，后续任务引用）**

- D-1：目标在仓内 ⇒ 摘链→复检→remove；在已删 worktree 子树内 ⇒ 摘链；否则 fail-closed 不摘。
- D-2：医生默认域 = 注册表 + 仓内 `node_modules/*` 顶层；全域猎捕 opt-in。
- D-10/D-12：见上（期望集减法 / 跳过存活链）。
- D-11：G1 动词面含删除穿透形态，非 worktree 目标用第二套文本。
- D-9：AC-013 由 G5 落地（它是"一条 npm 命令即可复刻事故"的唯一口子，G1 看不见）。
- 未变更：AC-008 未降级；G1/G2 同版本发布（阻断文本引用的 `mw worktree rm` 必须已存在）。

## 遗留

| # | 遗留 | 去向 |
|---|------|------|
| 1 | G1 静态不可判定绕过面：`sudo …`、`bash -c '…'`、预写脚本、`find -delete`（G1 只判命令结构，非沙箱）。**W-15 追加 4 条**（决策 D-20）：`\<LF>` 续行拼接、头部/子命令位变量插值、`env`/`nohup`/`timeout` 等前缀包装、PS 反引号转义 | **接受不处理**：设计 `design.md` D-4/§3.3 已明文声明边界；判断依据 = 事故形态是 agent 直写命令，且这些形态属刻意混淆/嵌套解释器，修法需改共享 lexer 或引入命令级展开（收益低于误拦风险） |
| 2 | 未覆盖**不穿透**动词：无尾分隔符 `rm -rf <link>`、`rmdir /S`、`robocopy /MIR` | **接受不处理**：RQ-1 实测这些默认不穿透该 junction；纳入只会增加误拦 |
| 3 | G1 通配前缀扫描刻意偏宽（fail-closed 取向）、非 worktree 处方只列前 3 条命中（+`remaining N`） | **接受不处理**：偏严可接受，处方文本已给总数 |
| 4 | G5 中止路径**刻意保留** `<wt>` + junction（在 `%TEMP%`）以保全现场 —— 它本身是 mwvg-t5 同类的活雷，且**只有** `mw doctor --worktree-scan-roots` 能看见 | **立新 key 候选**（"G5 中止后的自清理/降级摘链"）；本轮记入本表，未修 |
| 5 | 崩检把「安静但存活」的 worker 反复报成 failed（本 key 一次 run 刷 20 条伪块；PM 若自动重派会丢整轮工作 + 并发写） | **立新 key 候选**（属 `mw-dispatch-reliability` 地界）；判据与规避已写入 `_pitfalls.md` **P-028** |
| 6 | `mw.py:_repo_root()` 返回**安装脚本所在仓**而非 cwd ⇒ 夹具无法用真实 CLI 驱动 worktree 端到端（W-08 改走 `worktree_cmd` DI 面） | **立新 key 候选**（`mw worktree` 的 `--project`/`repo_root` 参数化）；本轮记入 `_pitfalls.md` **P-029** |
| 7 | 未登记 `%TEMP%` 孤儿链（mwvg-t5 形态）**不在默认巡检域**，必须显式 `--worktree-scan-roots` | **接受不处理**（D-2/D-12 已确认：5.39s 全域扫描不做默认）；命令与判据见上 |
| 8 | 其它 key 的孤儿目录（`agent-team-loop`、`mw-dispatch-reliability` 的 index-idle 残留目录） | **接受不处理**：非本 key 写面 |
| 9 | Windows 环境既有测试基线失败（`packages/agent` + `packages/coding-agent` 共 89 例；另 `test_launcher.py::test_bom_historical_books_read_through_both_callsites` 因夹具未入库而红） | **接受不处理**：AGENTS 已归类为环境噪声，本 key 未加剧（对比见 §验证入口） |
| 10 | 本 key 期间学到的框架级教训（派发卡两道静默门槛、8.3 短名别名、伪 failed 块、CLI/夹具基准、`git grep` 不含未跟踪文件） | **记入 `_pitfalls.md` P-026…P-030**，已写 |
| 11 | 审计 N-05：`.mw/tree-watch.json` 无锁 + 多 launcher 交错采样可致基线错配（漏报/误报窗口窄） | **接受为债**（决策 D-16）：该文件是诊断面、告警不阻断执行；判据与坐标见 `evidence/negative-space-audit-20261013.md` N-05 |
| 12 | 审计 N-01 的**运行面部署** | **已闭合**（2026-10-14）：bundle `mw build --install`（1,136,749 B，双标记齐）→ `mw stop`+`mw start`（PID 151032）→ 实测 `serve code: fresh`、`bundle stale=False`、`mw doctor` **rc 0**、`.mw/tree-watch.json` 出现且 `links`=14、`events/alarms` 空。**唯一人为步骤**：各已开 pi 窗口需 `/reload` 才加载新 bundle（框架不代劳） |
| 13 | 全量 `./test.sh` 在本机 Windows 上**无超时挂死**（实测 7h14m；vitest 子进程 7h 只烧 22.9s CPU，输出自第 15 分钟起停更） | **记入 `_pitfalls.md` P-032**：按包 + 超时跑，别裸跑全量；本 key 的对照改用“触及文件的定向套件”（见 §验证入口） |
| 14 | `packages/coding-agent/Python/_cache/last_welcome.txt`（`./test.sh` 期间出现的 untracked 伪目录，疑某测试路径拼接 bug） | **接受不处理**：非本 key 写面、未提交；记录以便后续归因 |
| 15 | 审计 W-15 标出的 **5 条证据强度不足**：① T-W14 的短路判据是消费者语义的**复刻**；② 阴性对照为叙述性证据、不可从提交树复现；③ T-W13 的「部署后自动转绿」只用假 bundle 夹具；④ 部署字节数无第三方复算；⑤ 执行后端是 stub ⇒「后端未被调用」≠「真实 shell 未 spawn」 | **①③④ 已处置**：W-15 在 src+dist 双侧独立复核消费者语义；PM 两轮真实部署并留存 doctor 前后对照（2 条 → 0 条、rc 1 → 0）；字节 PM 两次复算（1,136,103 / 1,136,749）。**②⑤ 接受为固有限制**（叙述性阴性对照与 stub 后端已在报告中自行声明） |
| 16 | 第三审计自身的**方法边界**：W-15 会话无 shell ⇒ 其全部「拦/放」结论为静态代码路径推演，未做执行型反例 | **接受**：执行面由 W-14 的真链路测试（真实 `activate(pi)` + `emitUserBash` + 执行记录器）与 PM 实跑覆盖；若要「执行型对抗」（在真 shell 里跑夹具命令），需另立 key |

## 验证入口（复核者可直接照跑）

```
# 工具层（TS）
npm run check                                     # 期望 exit 0（实测 1154 files, clean）
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run \
  test/suite/worktree-junction-guard-decide.test.ts \
  test/suite/worktree-junction-guard-coverage.test.ts   # 期望 25 + 13 pass（含 W-14 新增 4 条 user_bash 用例）

# 命令行/巡检/端到端（Python）
cd packages/multi-workers
python -m pytest test_worktree_cmd.py test_worktree_doctor.py test_worktree_e2e.py test_tree_watch.py -q   # 期望 73 pass
python -m pytest test_worktree_cmd.py test_worktree_doctor.py test_worktree_e2e.py test_tree_watch.py \
  test_tree_watch_doctor.py -q                                    # 期望 96 pass（含 W-09 新增 23 项）
python -m pytest test_doctor_activation.py test_worktree_cmd.py test_worktree_doctor.py test_worktree_e2e.py \
  test_tree_watch.py test_tree_watch_doctor.py test_doctor_gates.py test_serve_doctor.py -q   # 期望 172 pass（含 W-13 新增 10 项）
python -m pytest test_doctor_activation.py -q                    # 期望 10 pass（AC-015/AC-016 专测）
python -c "import mw_common; print('cycle-ok')"
python mw.py doctor --project H:/git/Multi-Workers    # bundle 部署前：零 worktree_links 行 + 2 条 guard-not-deployed、rc=1；
                                                      # bundle 部署后：activation 归零、仍 rc=1（既有 STALE CODE）；serve 重启后期望 rc=0
# bundle 标记自检：两份 agent-team-loop.js 各 1,136,103 B 且含 'reparse-point'（部署前 1,115,336 B / 0 命中）

# 真机只读复检（不写）
git worktree list            # 期望仅主 worktree
git ls-files -d | measure    # 期望 0
# node_modules 下 reparse point 期望 14（= lockfile "link": true 期望集）
```

- 一手复核记录（PM 本次会话实跑，2026-10-14 更新）：`npm run check` exit 0（1154 files）；vitest **25 + 9** pass；`pytest` 四文件 **73** pass、五文件（+`test_tree_watch_doctor.py`）**96** pass、六文件（+`test_doctor_gates.py`+`test_serve_doctor.py`）**138** pass；真机 1 worktree / 0 deleted / 14 链；注册表文件不存在（尚无 mw 建的链）。
- 注册点计数：`git grep --untracked -n '"tool_call"' -- packages/coding-agent/src` ⇒ **7** 处 `.on("tool_call")`（含新增 `worktree-junction-guard.ts:180`）。
- 一手复核记录（PM 实跑，2026-10-14 W-13/W-14 落地后）：`npm run check` **exit 0**；vitest decide+coverage = **38 pass**（25+13）；pytest 八文件（含 `test_doctor_activation.py`）= **172 pass**；`python -c "import mw_common"` cycle-ok；真实仓 `mw doctor` 部署前 = 2 条 `guard-not-deployed` + rc=1，`mw build --install --allow-dirty` 后 = **0 条 activation 命中** + 仍 rc=1（既有 STALE CODE）；两份 bundle 1,136,103 B、`'reparse-point'`=1 / `worktree`=25 / `"user_bash"`=2。
- 一手复核记录（PM 实跑，2026-10-14 W-16/W-17 落地后）：pytest 八文件 = **179 pass**（172 + W-16 新增 7）、`test_doctor_activation.py`+`test_worktree_doctor.py` = **32 pass**；vitest decide+coverage = **46 pass**（33 + 13）；`npm run check` **exit 0**；真实仓 `mw doctor` 部署前 = 2 条 `guard-not-deployed` + rc 1 → 部署 + serve 重启后 = **0 条 activation 命中、rc 0、serve fresh**；`.mw/tree-watch.json` `links`=**14**（与 lockfile `link:true` 一致）、`tracked_total`=5061；根 `node_modules` 复解析点仍 **14**、`git worktree list` 仅主树、`git ls-files -d` 0、受跟踪文件 5061。
