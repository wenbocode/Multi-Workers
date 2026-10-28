# T-W12 — 负空间审计：工件清单差集 + 危害面全量清单（方法正交于 QG）

- type: review
- key: mw-worktree-junction-guard
- 角色约束: **只读**（read/find/grep/ls 类），**不得执行任何命令**，**不得改任何文件**；唯一产物见「交付格式」

## 上下文

- **目标锚点**: `.agenticdoc/goal.md:1` —— 本 key 要让 2026-10-09 的 junction 穿透事故（`git worktree remove --force` 穿过 reparse point 删掉 3,456 个已跟踪文件）**不可达**，且同类事故**可被机器发现**（INV-4）。
- **为什么要第二份审计（与 `wjg-qg-evidence-closure` 的区别）**: 已有独立 QG 报告 `evidence/quality-gate-report-20261013.md`（13/13 ✅、16/16 反假证据抽样相符），但它的方法是**引用闭包**：以卡片给的文件清单 + 各证据文件自称的 `file:line` 为入口，逐 AC 核对坐标与内容。它**没有**做「以仓库为入口」的负空间枚举，也没有做危害面的全量清单。本任务补的正是这块，方法必须独立：**先按 AC/决策独立推导必需工件与风险面，再拿仓库求差集**。
- **被审基准**: `.agenticdoc/mw-worktree-junction-guard/spec.md:1`（AC-001..AC-013 + §7 决策 D-1/D-2/D-9..D-12）、`design.md:1`（§3.3 规则表、§3.5 D-4 边界、§5.3 巡检域、§6.1 动作 (3)、§9 验证矩阵、§4.3 模板）、`achieved.md:1`。
- **实现面（已知，作为起点不是上限）**: `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:180`（G1 注册点）、`shared/bash-segments.ts:106`、`packages/multi-workers/worktree_cmd.py:529`（remove 流程）、`worktree_doctor.py:211`（域扫描）、`packages/multi-workers/launcher.py:1706`（采样挂点）、`tree_watch.py:107`（阈值）、`packages/multi-workers/mw_common.py:3818`（升级消费点，W-09 新增）、`scripts/diff-model-catalog.mjs:285`（摘链调用点）。
- **已被处理、不要重复报为新发现（可复核，可推翻）**: QG 的 F-01/F-03/F-04 = PM 已修的文档坐标；F-02 = W-09 落地 `TREE_WATCH_ISSUE_WINDOW_SEC` + collapse/链 delta 升级；F-05 = W-11 抽出 `scripts/detach-node-modules-link.mjs` + `scripts/detach-node-modules-link.test.mjs`；F-06 = W-10 追加处方 allow 断言。

## 审计目标

1. **先验工件清单 vs 仓库实际（负空间差集）**：对 AC-001..AC-013 与决策 D-1/D-2/D-9..D-12 **逐条独立推导**「该存在什么工件」（文件 / 符号 / 注册点 / 测试用例 / 常量或开关 / 文档条目），**在打开任何 `evidence/T-W*.md` 或 QG 报告之前**把这份先验清单写下来；随后用 `git ls-files --untracked`、`find`、`ls`、`grep` 与仓库实际求差集，输出两类：
   - **该有而没有**（设计/规格要求但仓库里找不到，或找不到任何测试/开关支撑）；
   - **有而无人引用**（仓库里存在、但 spec/design/卡面/证据都没指向的实现或测试 —— 可能是漏审面，也可能是死代码）。
2. **危害面全量清单（本任务的核心交付）**：枚举**全仓所有能到达穿透式删除的路径**，逐条给三态，不允许留空：
   - **被守住**（由 G1 / G2 / G5 覆盖，指明是哪一个 + 证据坐标）；
   - **不在覆盖面且有理由**（例：`rmdir /S`、无尾分隔符 `rm -rf <link>`、`robocopy /MIR` —— 属 design §3.5 D-4 第 3 条明确不扩的面，要求写出理由与风险承受）；
   - **未守住（新发现）**。
   必须覆盖的机制面（每面都要给出"枚举方法 + 命中的路径 + 三态"）：`git worktree remove|rm|prune`（含 `--force`、`-C`、`cd`/`Set-Location` 前缀）、`rm -rf`/`Remove-Item -Recurse` 的**尾分隔符与通配**形态、`rmdir /S`、`robocopy /MIR`；TS 侧枚举全部 `tool_call` 注册点（用 `git grep --untracked -n '"tool_call"'`，注意未跟踪文件，P-030）、`worker-mode.ts` 的 git 分支（约 `:1501`、`:2165`、`:2218`）、Python 侧 `mw.py`/`worktree_cmd.py` 的 worktree 子命令、`scripts/**`（含 `diff-model-catalog.mjs` 的 worktree 生命周期）、`package.json` scripts 与 lifecycle、CI workflow（`.github/workflows/**`）、**文档/卡面里可被照抄的命令**（design §4.3 阻断文本、CHANGELOG、README）。
3. **不以证据自述为准**：仓库正文是第一来源，证据文件只作对照。凡发现"声称存在但仓库里没有"或"仓库里如此但声称相反"，一律作为新发现给出反例坐标。
4. **对既有 QG 结论的复核权**：允许**推翻**其 ✅（给出反例坐标即可），也允许确认；不要重做它的逐 AC 证据链表（已有报告），把笔墨放在差集与危害面上。
5. **已知盲区必查项（至少要逐条给结论，哪怕是"已确认安全"）**：
   - G1 的注册是否在所有三种模式与"重复加载"下都真正生效（注册点与双加载 flag 的顺序）；
   - 工具白名单/扩展加载：新文件 `worktree-junction-guard.ts` 是否被构建/发布/白名单纳入（读 `package.json` 的 `files`、构建脚本、`scripts/check-*.mjs`）；
   - G3 段对既有 `mw doctor` rc 语义的影响（真机当前 rc=1 为既有 STALE CODE；域扫描是否可能把"正常态"算成 issue）；
   - G4 采样在 worker 忙/长任务时的**采样缺失**（若整窗无采样，AC-010 判据是否永不触发，是否有人会知道）；
   - `.mw/tree-watch.json` / `.mw/worktree-registry.json` 的 `.gitignore` 覆盖与**多 worktree/多会话并发**下的锁竞争；
   - W-09 新增消费点的取值来源（`worktree_links.registry_path` 反推 project root）在真实调用面上是否恒成立。

## 要求

1. **方法与顺序**：报告中先写 `## 方法`，写明你在读证据文件**之前**写下的先验清单（原始形态）、随后用了哪些枚举命令/判据、哪些假设被差集推翻。
2. **可定位**：每条结论给 `文件:行号` 或"命令 + 输出片段"。无法确认的写"未确认"，不要写成"已确认"。
3. **不执行**：本角色不能执行任何命令。所有依赖实跑（pytest/vitest/`npm run check`/真机 git 计数）的结论一律标 `[无法独复现]`，只做**存在性与内容一致性**核对。
4. **反假纪律（P-025 类）**：抽样复核 ≥6 条"已机器校验/有断言"类声称在仓库中是否真的存在且内容相符；不符者列为新发现。
5. **不写仓库**：不得修改任何被审文件；唯一产物见「交付格式」。

## 交付格式

- **唯一产物**：本任务目录下的报告文件 `report-negative-space-audit-20261013.md`（框架允许的写面；PM 负责原样提升到 `.agenticdoc/mw-worktree-junction-guard/evidence/negative-space-audit-20261013.md`，两文件 sha 需一致）。结构：
  - 头部：审计者 = 本 worker key、时间、范围、输入清单、只读限制；
  - `## 方法`；
  - `## 先验工件清单 vs 仓库实际`（该有而没有 / 有而无人引用，两张表）；
  - `## 危害面全量清单`（表：机制 / 入口路径 / 三态 / 证据坐标 / 备注）；
  - `## 新发现`（编号 N-01..；每条：现象 / 反例坐标 / 影响 / 建议动作 / 是否建议新 key）；
  - `## 对既有 QG 报告的复核意见`（确认项与推翻项分开，推翻项给反例坐标）；
  - `## 未覆盖面声明`；
  - `## 上下文来源`。
- **另**：`output.md` 必须自带 `## 结论` / `## 证据` / `## 残留与未验证` / `## 上下文来源` / `## 未覆盖面声明` 五段（框架恢复契约对本角色要求 `结论`、`证据`、`残留与未验证`、`上下文来源` 四段 + review 额外 `未覆盖面声明`；缺段会导致本任务以 `needs-clarification` 收尾，见 `.agenticdoc/_framework-reflect.md` FW-001）。
- 报告末行：`NEG-SPACE: 新发现 <n> | 危害面路径 <n>（守住 <n>/不在覆盖面 <n>/未守住 <n>）| 该有而没有 <n> | 有而无人引用 <n> | 反假抽样 <n> 条`

## 未覆盖面声明

- 只读角色，**不能执行命令**：所有实跑结论（pytest/vitest/`npm run check`/`node --check`/真机 git 与 doctor 计数/夹具复演）**无法独立复现**，只做坐标与内容一致性核对，一律标 `[无法独复现]`。
- 本次审计**不覆盖**：Windows 环境既有测试基线失败（AGENTS.md 记载 89 例 + `test_launcher.py` 语料缺失 1 例）；其它 key 的孤儿目录与在飞改动；`spec.md`/`design.md`/`achieved.md` 之外的文档措辞与格式；性能与容量（除 G4 采样缺失这类"判据是否可能永不触发"的功能性问题）；跨仓（本仓之外）。
- 发现不一致**不改任何文件**，只写进报告并给 `文件:行号`。
