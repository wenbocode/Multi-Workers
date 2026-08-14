# T-02: dispatch-table.md 更新（L3）

type: design/synthesis
cli: claude
deps: T-01
status: pending

## Description
在 `.claude/skills/pm-mind/reference/dispatch-table.md` 的路由表中增加 `CLI` 列，
并在 PM 行为说明中补充「创建 task key 时写入 CLI metadata」的步骤。

## Acceptance Criteria
- AC-1: `grep -c "| CLI |" .claude/skills/pm-mind/reference/dispatch-table.md` >= 1
- AC-2: 表格中每行 task.type 都有对应 CLI 值（pi / codex / claude）
- AC-3: PM 行为说明中包含 `update_index.py set-meta <key> --cli <...>` 示例

## Tool Constraints
allowed: [read, write, glob]
denied: [bash, network]

## Do NOT
- 不要修改 dispatch-table.md 的其他路由逻辑
- 不要在表格外新增文件

## Expected Output
更新后的 `.claude/skills/pm-mind/reference/dispatch-table.md`。
