# Evidence Run: 007-profile-rendering

- Date: 2026-09-11T21:10:00+08:00
- Task: 007-profile-rendering（S3）
- Deliverables:
  - `pm/task-dispatcher.ts`: `injectWorkspaceProfile()`（派发时增补 task.md）+ `renderProfileBlock()`（三节要点 + 控制根绝对路径，行前缀刻意非 `key:` 形避免 parseTaskMd 全文件扫描误读）+ `insertDenyGlobs()`（与 Py render_task_md 同格式单引号块；有 `---` 对插入闭合标记前，无分隔符则前置——兼容 ui-bridge 手写形态）+ `dispatchTask` 注入后入队
  - `pm/pm-orchestrator.ts`: 扫描循环 per-task try/catch（broken target.yml → stderr 记录 + 该任务不入队、不炸整轮扫描；修好 yml 后下次扫描自愈）
  - `test/extensions/agent-team-loop-profile-injection.test.ts`: 7 用例（新文件）

## 测试命令与结果

```
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-profile-injection.test.ts
  Tests 7 passed (7)   # exit=0

# 关联套件（dispatchTask/dispatchNewTasks 既有用例 + 001~005 成果回归）
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop*.test.ts test/suite/dual-root-worker.test.ts test/suite/autopilot-read-scope.test.ts
  Tests 191 passed (191)

npm run check → exit 0
```

## [VERIFY] 行

```
[VERIFY] VC-013: toolchain-mark=true ignore-mark=true contract-mark=true
```

- VC-013 断言：toolchain 占位符**派发时解析**（`{engine}`/`{uproject}` → realpath 绝对路径，fail-closed——引用未配置根即拒派）；ignore 节要点 + frontmatter `deny_globs:` 单引号块（与 Py 渲染逐字对齐，parseTaskMd 实测解出 `["**/*.uasset"]`）；contract 三字段要点 + `docs:` 渲染引用行不内联；dual 下含 `Control workspace: <abs>` 引用行
- 快照：single 无 target.yml → task.md 逐字节不变、入队正常
- 幂等：重派发 profile 块仅一份（`<!-- mw-profile: v1 -->` 哨兵）
- 任务级 deny_globs 不被覆盖：自带列表时 frontmatter 保持原样，**profile 块跳过 ignore 节**（渲染 yml 默认值会谎称其被强制——首跑抓出后修正）
- broken yml：scan 零入队 + stderr 可见，修复后下次扫描自愈入队

## 关键语义（执行期确定）

- fixture 教训：任务真实形状是 `<control>/.agenticdoc/_scratch/workers/<task>/task.md`（5 层），首版测试漏 `.agenticdoc` 层导致 controlRootFromTaskPath 推到 tmpdir、注入静默跳过——修正 fixture 后注入全通（实现本身无 bug）
- task.md 不可读（如既有测试的假路径 `/t`）→ 跳过注入仅警告，入队照常（launcher spawn 侧自会校验任务文件）；**config 损坏才 fail-closed 拒派**
- `resolveWorkspaceConfig` 对 controlRoot/gameRoot realpath 归一（短路径 8.3 → 长路径），渲染与断言均以归一形态为准
