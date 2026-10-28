# T-QG — 独立质检：AC-001..AC-013 证据链闭合审计（mw-worktree-junction-guard）

- type: review
- key: mw-worktree-junction-guard
- 角色约束: **只读**（不得写任何文件，唯一例外见「未覆盖面声明」）；不得执行任何命令/删除/最小改动的尝试

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 本 key 的目标是让 2026-10-09 的 junction 穿透事故（`git worktree remove --force` 删掉 3,456 个已跟踪文件）**不可达**。
- **被审对象**：
  - `.agenticdoc/mw-worktree-junction-guard/spec.md:40`（G3/G4/G5 与 AC-008..AC-013）、`spec.md:1`（全文 AC-001..AC-013 + §7 决策记录 D-1/D-2/D-9/D-10/D-11/D-12）。
  - `.agenticdoc/mw-worktree-junction-guard/design.md:1`（§3.5 边界 D-4、§5.3 巡检域、§9 验证矩阵、§4.3 阻断文本模板）。
  - `.agenticdoc/mw-worktree-junction-guard/achieved.md:1`（系统行为变化 / 遗留 / 验证入口）。
  - **实现落地**：`packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:1`（G1，含 `:180` 注册点）、`shared/bash-segments.ts:1`（D-3）、`extensions/agent-team-loop/index.ts:61`（注册面）；`packages/multi-workers/worktree_cmd.py:1`+`worktree_registry.py:1`（G2）、`worktree_doctor.py:1`（G3）、`tree_watch.py:1`+`launcher.py:1706`（G4）、`scripts/diff-model-catalog.mjs:161`（G5）。
  - **证据**：`.agenticdoc/mw-worktree-junction-guard/evidence/T-W01..T-W08-*.md` 与 `evidence/research/design-*.md`（含 RQ/necessity 三轮）。
- **PM 已跑过的门禁（作为你的输入，不是你替代执行的）**：`npm run check` exit 0（1154 files）；`pytest test_worktree_cmd.py test_worktree_doctor.py test_worktree_e2e.py test_tree_watch.py -q` → 72 passed；vitest `worktree-junction-guard-decide` 23 passed、`…-coverage` 9 passed；真机只读复检 = 1 worktree / 0 deleted tracked / 14 reparse points / 注册表不存在。
- **P-025 是本次审计的首要动机**：上一个 key 出现过「回执声称已有机器证据、而该证据根本不存在，且没有任何一层会红」。请把"抽样复核每条机器证据声称的坐标是否真的存在"当作本次第一优先级。

## 审计目标

1. **闭合判定**：对 AC-001..AC-013 逐条判定其证据链是否闭合（✅ 充分 / ⚠️ 不足 / ❌ 无证据），并给出可定位的证据坐标。
2. **反假证据（第一优先级，P-025 类）**：抽样复核 ≥8 条“已机器校验/有断言/实测输出”声称的坐标是否真实存在且内容相符；声称与证据不符者一律判 ❌ 并给反例坐标。
3. **反向对照完备性**：AC-003/AC-009 的“不误报”侧必须定位到具体用例；只有正向用例的判 ⚠️。
4. **决策–实现一致性**：`design.md` 的 D-4 边界与决策 D-10/D-11/D-12 是否与代码/测试一致（尤其是 D-11 动词面边界：`rmdir /S`、无尾分隔符 `rm -rf <link>` 必须仍放行）。
5. **漏项扫描**：AC 之间未被覆盖的交互场景（G1/G2 同版本要求、AC-013 复用 AC-012 原语、`mw doctor` 退出码与既有 doctor 断言的交互），以及 `achieved.md`「遗留」表里是否存**已被本轮实现解决**的过时条目。

## 要求

1. **逐 AC 建问题清单**：AC-001 到 AC-013 每条列出「AC 断言 → 证据坐标（`文件:行号` 或测试名+用例名）→ 三态判定（✅ 充分 / ⚠️ 不足 / ❌ 无证据）→ 备注」。
2. **抽样复核机器证据（P-025 类）**：挑**至少 8 条**"已机器校验/有断言/实测输出"类声称，逐条回到源码或证据文件确认坐标存在且内容相符（例：`executedBashCommands === []`、`remove_checks == [False]`、真机 `worktree_links` 计数为 0、D-10 期望集 14 条、`delete-penetration` 两套文本、`node --check` 退出码、G4 阈值公式）。坐标不存在或内容不符 ⇒ 记 ❌ 并给出反例坐标。
3. **反向对照审计**：AC-003/AC-009 的"不误报"侧必须能定位到具体用例（干净目标放行、期望集减法、域 (c) 跳过存活链）。只有正向用例的判 ⚠️。
4. **边界与决策一致性**：核对 `design.md` D-4/决策 D-10/D-11/D-12 与代码/测试是否一致；特别检查 D-11 的动词面边界（`rmdir /S`、无尾分隔符 `rm -rf <link>` 必须仍放行）是否有对应用例。
5. **二次印证（漏项扫描）**：重读 spec/design/achieved，回答：是否有 AC 之间未被任何 VC/用例覆盖的交互场景（例如 G1 与 G2 的版本同发要求、AC-013 与 AC-012 的原语复用、`mw doctor` 退出码与既有 doctor 断言的交互）；`achieved.md`「遗留」表里是否有条目其实**已被本轮实现解决**（过时遗留）。
6. **输出报告**：把结论写入 `.agenticdoc/mw-worktree-junction-guard/evidence/quality-gate-report-20261013.md`（**唯一允许写的文件**），结构：
   - 头部：审计者 = 本 worker key、时间、范围、输入清单、**你的只读限制**；
   - `## 问题清单与核查结果`（表：问题 ID / 描述 / 状态 / 证据坐标 / 备注）；
   - `## 抽样复核机器证据`（≥8 条，逐条列坐标与结论）；
   - `## 汇总`（总数 / ✅ / ⚠️ / ❌ + 质检结论 ✅ 通过 / ⚠️ 有条件通过（欠债 N 项）/ ❌ 未通过）；
   - `## 未通过问题行动计划`（若有：根因 + 所需动作 + 建议负责面）；
   - `## 二次印证结论`（漏项扫描结果）。

## 未覆盖面声明

- 角色允许面为**只读**（read/find/grep/ls 类），**不能执行命令**：因此所有"实跑结果"（pytest/vitest/`npm run check`/真机计数）你**无法独立复现**，只能做**坐标与内容一致性核对**（声称的断言/行号/输出是否真的存在于源码与证据文件里）。凡属此类的判定请在报告里显式标 `[无法独复现]`，不要写成"已复现"。
- 本次审计**不覆盖**：`packages/coding-agent` 与 `packages/multi-workers` 的既有测试基线失败（Windows 环境，见 AGENTS.md）；其它 key 的孤儿目录；`design.md`/`spec.md` 之外的文档。
- 若发现实现与设计不一致，**不要改任何文件**，只写进报告并给出 `文件:行号`。

## 交付格式

- 唯一产物：`.agenticdoc/mw-worktree-junction-guard/evidence/quality-gate-report-20261013.md`（新建）。
- 报告末行：`QG: <通过|有条件通过|未通过> | AC 总数 13 | ✅ N | ⚠️ N | ❌ N | 抽样复核 N 条`。
