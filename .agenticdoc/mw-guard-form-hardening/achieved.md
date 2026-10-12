# 达成记录：mw-guard-form-hardening

- key：`mw-guard-form-hardening`｜phase：verify → done
- 目标：把守卫的**形式假设**硬化为**被判定的事实**（guard form → judged facts），消除上一 key 遗留账本 R3–R11 的残余面。
- 范围来源：`mw-gate-verdict-hardening` 的残余账本（A1/A2/A3/A4/A5/A8 + C2/C7 + 14 条未覆盖分支 + 2 条空心断言 + A9/A10/A11）。
- 验收口径：`spec.md`（11 条 AC，其中 AC-006/AC-008 于 2026-10-12 `[REVISED]`）→ `design.md`（DD-01…DD-11、VC-001…VC-046、C-1…C-26）→ `plan.md` → 卡片 T-01…T-20 → 六轮质量门（QG-A/-B/-A2/-B2/-A3/-B3）。

## 系统行为变化

### 1. 守卫判据从「形式/正则假设」变为「被判定的事实」

| 面 | 变化前 | 变化后 | 载体 |
|---|---|---|---|
| 写面判定 | 单一正则 + 目录盲区 | 单一来源 `judgeWriteTarget`；分隔符/比较深度（`((`/`[[`）/命令替换/`tar -C` 全部按真实写目标判定 | T-01…T-04、`mwds-t02` 35、`mwds-t03` 63 |
| 越面拦截 | 缺审计、无法区分 allow/deny | 审计行带 **`blocked=<bool>`** + `rule=scope detail=outside-allowed-surface target= cmd=`；收尾打 `[WRITE_SCOPE_SUMMARY] allow=/deny=/allow-unknown=` | T-03、T-18、冒烟 v3（6/6 拦） |
| 任务角色判定 | 7 处各自解析 `type:`，含 `last-wins` 与 `/^type:\s*codex/im` 正文翻转路由 | **唯一来源** `shared/task-frontmatter.ts` 的 `readTaskType`；正文行永不改变角色/路由；`pm-orchestrator.ts:355` 改用它 | T-07（265 例）、T-17（A1） |
| 跨 key 写入 | 5 处无门禁 | 14 个保留名 + 稳定错误码 + 读侧归一 + `caseVariantOf`（大小写变体视为同 key） | T-09、T-15、T-16 |
| 证据链可判定性 | 74 处引用无校验、`[FORMS]` 计数 0 命中 | 锚点门禁（`refs_total` / `unresolved` / `unanchored_refs`）+ 形态门禁（`[FORMS] total=79 covered=79 missing=0`）**成为测试** | T-17（B-1/B-6）、T-18 |

### 2. 运行期（cutover）实测确认

- 产物面：`packages/multi-workers/dist/extensions/agent-team-loop.js` 与全局扩展 `~/.pi/agent/extensions/agent-team-loop.js` 重建安装（**1,043,634 B**，sha256 `0FE644319ACB25F5B16F1CD29FF2559281C78A71518B27A99E3435DDC4E026E9`），8/8 新符号命中；`packages/coding-agent/dist` 重建（`worker-mode.js` 等含新符号）。
- 装载面：运行中的 bundle 经第三方独立读取，确认含 `write-scope blocked=${String(r.blocked)}` 与 `[WRITE_SCOPE_SUMMARY]`。
- 行为面（冒烟 v3，**research = shell+writeless 角色**，唯一被守卫覆盖的角色）：**6/6 次**「key 内、worker 目录外」写入被拦，`blocked=true rule=scope detail=outside-allowed-surface`；含 `bash -c`、`cmd.exe /c`、`powershell.exe -Command`（`pattern=set-content`）三类包装器形态；4 个越面文件**均未创建**；`[WRITE_SCOPE]` 6 条与 `[WRITE_SCOPE_SUMMARY]` 均由 PM 在 `<taskDir>/trace.log` 独立复核。
- **覆盖面的成文契约（重要）**：bash 写面守卫的注册条件是 `isShellRole(type) && isWritelessRole(type)`（`worker-mode.ts:2149`，注释 `:2316`：`Write roles register no guard and stay byte-identical (VC-024)`）。即：**守卫覆盖「有 shell、无 write/edit」的角色（research/review）；`coding` 角色不注册该守卫，其写入约束来自任务书与文件工具守卫**。两次负向冒烟（用 `coding` 角色测）由此确认为**测试设计错误，非缺陷**。

### 3. 门禁与回归基线（PM 亲跑，末次）

- TS 9 文件 **433 passed / EXIT=0**；`[FORMS] 79/79/0`；`[ANCHORS] refs_total=77 resolved=77 unresolved=0 out_of_range=0 content_mismatch=0 unanchored_refs=0`；Python 4 文件 **144 passed**；`npm run check` EXIT 0（biome 1121 文件）。

## 遗留

### 1. 账本去向（C-1…C-26 / R-1…R-5 / W9）

| 编号 | 内容 | 处置 |
|---|---|---|
| C-1…C-8, C-10, C-11, C-13 | 见 `design.md` §4.6（C-2/C-13 已由 T-17 落地；C-6 body-`type:` 升级拒绝仍仅审计、C-7 `dup-type-ignored` 无审计、C-8 `resolveDispatchType` 读参数不二次解析） | 本 key 消除或按设计接受 |
| **C-9** | `.claude/scripts/update_index.py` 等 **6 份分发包副本无门禁**，且在活链上（`ui-bridge.ts:2345 → agentic-scripts.ts:21-30 → advance_phase.py:599/602`），`install.py` 会分发到每个用户项目 | **未解除**：用户裁定走 **(b) 后续 key**（提交框架 → 重同步镜像 → 重装 `.claude` → 加镜像一致性检查） |
| **C-12** | 运行期装载旧守卫（dist / multi-workers dist / 仓外全局扩展三处 fail-open） | **本 key 解除**：重建 + 安装 + `/mw restart` + `/reload`，冒烟 v3 运行期直证（见上） |
| C-14 | `.exe` 包装器泄漏 | 已由 T-18 修复（5 形态被 `rule=scope` 拦；`ls -la foo.exe`/`grep x file.exe`/`2>&1` 反例 `[]`） |
| C-19 | F-A2-1 反引号粘连 `[[` 误拦、F-A2-3 不平衡 `((` 吞重定向、F-A3-2 `tar -czf -` 被拦、F-KEY-1 Windows 设备名（`nul`/`con`/`aux`）仍允许 | **登记不修**（低概率 / 极端输入） |
| **C-20** | PowerShell 裸位置参数 `Set-Content o.txt other/report.md` 把 Value 当写目标（误拦） | **登记不修**：正确修法需 PowerShell 取值 flag 表，朴素实现会丢真实形态（`New-Item -ItemType Directory newdir`） |
| **C-21 / C-22** | U+2028/U+2029 **标签镜像**分歧（`status-model.ts::parseTaskLabels` ↔ `state.py::parse_task_labels`）；C-22（QG-A3 H-5）扩大口径：TS 会把**正文** `type` 当标签（`coding` vs Python `review`），触及 `usedRounds` 的 loop/attempt | **登记不修交后续 key**：角色判定 `readTaskType` 两侧已一致；仅标签镜像分歧 |
| C-23 | `.exe` 残余漏放 3 形态（`bash.exe --command`、反引号命令替换、`bash.exe -c=`） | **登记不修**（非真实 agent 用法） |
| C-24 | 计数误写更正：`task-frontmatter` 报告 63→69 实为 **65**（基线 59）；`corpus_py_md5_eq_ts_md5` 声称 330/330 实测 **332/332**；T-20 自报 434 而 PM 实测 **433** | 以实测为准（本报告已采用实测值） |
| C-25 | 锚点门禁正则不覆盖 `.js` / `~` 路径（覆盖缺口） | **登记**（门禁覆盖缺口，非产品缺陷） |
| **C-26** | 审计行 `target=` 把 `\` 分隔符整体删掉（`cmd=` 保留原文）⇒ `target=` 不是可回放路径 | **登记不修**（拦截结论不受影响；可观测性瑕疵） |
| R-1…R-5, W9 | 见 `pm-state.md` D-045/D-048 与 `design.md` §9 | 已随 AC 修订或卡片处置 |

### 2. 验收口径的诚实声明（不得被后续读者误读）

1. **AC-001/AC-002 的「误拦=0」是语料口径**：只在 `test/suite/mwds-t03-bash-write-scope.test.ts` 的语料与 QG 对抗用例上成立，不等于全输入空间无误拦（C-20 即为反例）。
2. **AC-006 已 `[REVISED @ 2026-10-12]` 收窄**为「**权威副本**」（`.agents/skills/agentic-task/scripts/update_index.py` 有门禁）；被 `install.py` 分发到用户项目的 `.claude/scripts` 副本**不在本 key 口径内**（= C-9，交后续 key）。
3. **AC-008 已 `[REVISED @ 2026-10-12]` 收窄为 13/14**（BR-11 = C-11 未覆盖）。
4. **11 条分支的红色证据采用「期望反转」形式**：以「修改判据 → 期望变红」的方式证明测试有效性，而非天然失败用例。
5. **F-5（Python 标签区读取）修复无跨语言测试**：该文件不在卡片写入面内 ⇒ 只有单侧测试。
6. **运行期覆盖面**：`.exe` 包装器与真实 bash 语义**无法在本机端到端冒烟** —— 本机 `bash` 工具后端为 **PowerShell 5.1**（`~/.pi/agent/settings.json: shellPath`），未安装 Git bash，唯一 `bash.exe` 为 WSL 转发器且**无发行版**。该类形态只有单元测试覆盖（T-18 的正例用 `path.win32.join` 构造以保证平台无关）；同时 T-18 也修掉了「Windows 路径用例在 POSIX CI 必红」的隐患。
7. **`coding` 角色经 bash 可写到仓库任意路径**（守卫不覆盖，见「系统行为变化 §2」的 VC-024 契约），这是设计上的信任边界。
8. **审计行落点**：`[WRITE_SCOPE]`/`[TOOL_ERR]` 只写 `<taskDir>/trace.log`（非 stderr、非 `worker.log`），`[TOOL_ERR]` 截断 ≤120 字符，被拦命令无 shell 退出码。

### 3. 过程更正（PM 自报，不隐藏）

1. **D-047 撤回**：曾判定 T-13 的引用无效（`.agents/skills/agentic-task/install.py`、`packages/multi-workers/mw.py`），实为我按裸文件名在仓库根解析所致；其引用**有效**，C-9 结论不变。
2. **QG-A 首轮角色选错**：以 `review`（只读工具集、无 bash）派发「需实测」的对抗任务 ⇒ 只得静态输出；已按 AC-022 用**新 task_key** 重派为 `research`。
3. **§9.4 引用踩坑**：我在 `design.md` §9.4 新增两条带行号的引用，导致锚点门禁一度 `unanchored_refs=2`（QG-A3/QG-B3 均独立命中）。已改为符号引用；此后相位文档一律写可解析形式并在编辑后复跑门禁。
4. **T-20 漏卡片**：派发实现型任务时只写 dispatch 描述、未落卡片文件（worker 如实上报）。已独立立档 `.agenticdoc/_incidents/dispatch-card-omission-20261012/README.md`（含 F-1/F-2/F-3 三条修法），建议随下个框架硬化 key 处理。
5. **`/reload` 判断错误**：我最初答「reload 不够、必须重启窗口」；查 pi 文档后更正 —— `/reload` **会重载扩展**（`packages/coding-agent/README.md:197`），仅宿主 `dist`（npm-link 运行时）改动才需重启窗口。
6. **两次冒烟角色选错**（`coding` 角色不注册 bash 写面守卫）⇒ 负结果不是缺陷，已由源码 + 运行 bundle + VC-024 注释三重印证。
7. **biome「Fixed 1 file」前提撤回**：不存在纯格式化修复（stdin 回显伪影），已以证据关闭该疑虑。

### 4. 未完成 / 交后续

- **C-9**（`.claude` 分发包副本门禁）与 **C-21/C-22**（标签镜像 U+2028/U+2029）、**C-20**（PowerShell 裸位置参数）、**C-19/C-23/C-25/C-26**：登记在册，均未在本 key 修复。
- **11 个陈旧 pi 窗口**：用户裁定「先不管」；其守卫在新代码下需各自 `/reload` 才生效。
- **派发卡片缺失的框架加固**（F-1/F-2/F-3）：见 `.agenticdoc/_incidents/dispatch-card-omission-20261012/README.md`。
