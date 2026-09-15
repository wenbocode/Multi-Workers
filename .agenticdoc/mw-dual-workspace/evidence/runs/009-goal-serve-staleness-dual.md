# Evidence Run: 009-goal-serve-staleness-dual

- Date: 2026-09-11T21:30:00+08:00
- Task: 009-goal-serve-staleness-dual（S4）
- Deliverables:
  - `test/suite/dual-root-worker.test.ts` 扩展新 describe「dual-root goal check + serve staleness」：
    - VC-014：phased task.md 全流程（初始 settle 派发 phase → agent_end 带 assistant 文本 → phase 完成）在 cwd=game 下运行——[GOAL_CHECK] 落控制根 trace.log 且记录**控制根** goal.md 的真实 mtime（断言非 0——0 意味着 stat 错根，D-116）；phase-1.md（progress/ 子目录）与 output.md 落控制根 task dir；game 树无 goal.md/.agenticdoc
    - VC-016：staleness 基准=控制工作区源码 mtime——game 树远新于 serve 启动的"build 产物"（Cooked.py）不触发 stale；控制根 mw 源码晚于 serve.meta started_at_ms → stale=true

## 测试命令与结果

```
node ../../node_modules/vitest/dist/cli.js --run test/suite/dual-root-worker.test.ts
  Tests 4 passed (4)   # 既有 VC-005/VC-009 + 新增 VC-014/VC-016

# 关联回归
agent-team-loop + target-config + profile-injection + cross-drive: 160 passed | 1 skipped (161)

npm run check → exit 0
```

## [VERIFY] 行

```
[VERIFY] VC-014: goal-check-pass=true trace-has-goalcheck=true
[VERIFY] VC-016: staleness-detect=true
```

## 语义确认（AC-008/AC-009）

- **goal mtime 追踪不受 cwd=game 影响**：goalMtime(meta.trueAgenticdocRoot)——trueAgenticdocRoot 由 PI_WORKER_TASK 五层推导（控制根），与 cwd 无关；固定 utimes 后 stat 回读值与 trace 记录逐字一致，且非 0（错根必得 0，D-116 注释语义）
- **staleness 只看控制根**：mwCodeNewestMtimeMs 走控制工作区 mw 源树（.py/.json、排除 test_*/_/pycache/dist）；game 树任意新文件（UE 构建产物常态性地新）不产生重启提示——双工作区下重启提示噪声不放大

## 执行期修正（测试自身）

- 首跑失败两处均为测试错误而非实现 bug：phase-1.md 实际写 `progress/` 子目录（writePhaseFile 既有约定）；phased task.md 规范形态是 phase 作为 body 内容（prompt 至下一 `- name:` 行终止），frontmatter 形态会把闭合 `---` 吞进 prompt
- mtime 断言改为 stat 回读值（Windows NTFS 精度与 utimes 设定值可能有亚毫秒差），另加 `goal_mtime=0` 反断言锁错根情形
