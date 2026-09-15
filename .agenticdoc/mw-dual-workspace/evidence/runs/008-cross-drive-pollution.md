# Evidence Run: 008-cross-drive-pollution

- Date: 2026-09-11T21:35:00+08:00
- Task: 008-cross-drive-pollution（S4）
- Deliverables:
  - `packages/coding-agent/test/suite/cross-drive-worker.test.ts`（新文件）：env 门控跨盘 e2e——dispatchTask（deny_globs 注入 + profile + 队列行）→ cwd=game 跨盘 worker 执行（scope 放行/拦截 + deny 优先）→ 目标树框架文件扫描 + 控制根齐全断言；真卷临时目录 try/finally 清理（F:/ 是 Perforce client root）
  - 门控解析 `parseCrossDriveRoots()`：`MW_TEST_CROSS_DRIVE_ROOTS` 按 `;` 拆分，≥2 条且卷根不同才执行；always-run gate 用例打印 skip 原因（D-009）

## 测试命令与结果（双跑）

```
# 1. CI 模拟（无 env）
node ../../node_modules/vitest/dist/cli.js --run test/suite/cross-drive-worker.test.ts
  [SKIP] VC-003: MW_TEST_CROSS_DRIVE_ROOTS absent or degenerate — ...
  Tests 1 passed | 1 skipped (2)   # skip 原因可见

# 2. 本机真实跨盘（F:/ 与 E:/，临时目录不触真实工程树）
$env:MW_TEST_CROSS_DRIVE_ROOTS="F:/;E:/"; node ... --run test/suite/cross-drive-worker.test.ts
  [GATE] VC-003: cross-drive roots = F:/ ; E:/
  [VERIFY] VC-003: target-tree-hits=0 control-files=complete (game-hits=0 engine-hits=0)
  Tests 2 passed (2)

# 泄漏检查：F:\ 与 E:\ 根无 mw-xdr-* 残留 ✓

# 关联回归
cross-drive + dual-root + profile-injection: 10 passed | 1 skipped (11)
npm run check → exit 0
```

## [VERIFY] 行

```
[VERIFY] VC-003: target-tree-hits=0 control-files=complete (game-hits=0 engine-hits=0)
```

## 用例覆盖（AC-002 全链）

- **fixture**：控制根与 engine 在 E:\ 卷、game 在 F:\ 卷（真实跨盘）；target.yml dual + ignore.deny_globs
- **dispatch 侧**：TS `dispatchTask` 真实调用——task.md 注入 `deny_globs: '**/*.uasset'` frontmatter + profile 块 + `_workers.parallel` 队列行落控制根
- **worker 侧（cwd=F:\...game）**：相对条目 `Content` 锚 cwd 放行；engine 绝对条目（跨盘）放行；scope 外拦截；**scope 内 deny 命中**（`Content/DDC/x.uasset`，deny 优先于 allow，跨盘下 path.relative 无法相对化、abs 基准兜底）
- **AC-002 扫描**：game 树 + engine 树递归扫 `.agenticdoc`/`.mw`/`_workers.parallel`/`_index.parallel`/`trace.log`/`output.md`/`phase-*.md` → 计数 0；控制根 task.md/trace.log/output.md/_workers.parallel 齐全，trace 含 `rule=deny-glob`

## 放置决策（执行期）

跨盘敏感代码路径全部在 TS（read-scope 双基准相对计算跨盘退化为绝对路径串、realpath 归一、worker 写路径锚定）；Py dispatch 展开是绝对路径上的纯字符串运算（同盘用例已覆盖），故 e2e 归 coding-agent test/suite，Py 侧不加重复门控用例
