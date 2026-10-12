# pm-state — mw-workspace-incident-probe

- Key: mw-workspace-incident-probe
- Phase: SPEC
- Claim-Id: WENBOZHOU-PC4:18200

（接口行 `- Phase:` / `- Claim-Id:` 由框架脚本写入，见 `_index.parallel`。）

## 目标

查清 2026-10-09 同一天同一共享工作树上的两起事故（IN-1 workspace junction 消失；IN-2 3,448 个已跟踪文件消失又恢复）的根因、执行者与机制。**只读取证，零生产改动。**

## 证据（一手，全部落盘）

| 文件 | 内容 |
|---|---|
| `evidence/research/spec-incident-probe-plan-20261009.md` | 调研声明（零新增外部调研）+ PM 已实测事实表 |
| `evidence/in1-junction-incident-20261009.md` | IN-1 取证：AC-001..AC-004 全闭环（23,663 B / 87 calls） |
| `evidence/in2-file-vanish-incident-20261009.md` | IN-2 取证：AC-005 未坐实 / AC-006 机制 / AC-007 坐实 a（26,718 B） |
| `evidence/incidents-timeline-20261009.md` | PM 汇总：合并时间线 + 同源判定 + 未坐实清单 + G1..G4 建议（3,155 B） |

## 质量证据（PASS）

- PASS：两个只读 research worker 均 done 并已 ack；AC-001..AC-004 闭环，AC-006 逐条排除候选，AC-007 坐实「改动曾写入后被丢弃」（写入 toolCall + 另一会话回读双证）。
- PASS：PM 抽验承重结论（`index.ts:42` 注册点、`ToolCallEventResult` 位置、`os.path.isjunction` 可用）与引用逐字一致。
- PASS：本 key 零生产改动——`git status` 除本 key `evidence/**`/本文件外无新增变更。
- 未坐实（显式保留，不补洞）：AC-005 删除指令来自 pi 之外；恢复命令具体条目等（见 `achieved.md` §4）。

## 遗留

- G1..G4 落地 → key `mw-worktree-junction-guard`（mini-spec + spec 已建，RQ-1/RQ-2 调研中）。
- 服务侧规则缺口（AGENTS.md 未覆盖 worktree；僵尸 worker 簿记）→ 待开 key。
