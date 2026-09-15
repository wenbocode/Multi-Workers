# Task T-13: worker read_scope 拦截（containment 算法）

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker-t13-read-scope
- ac_refs: [AC-009]
- vc_refs: [VC-011]
- pattern_refs: []

## 描述
改 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（D-106）。

**拦截器**：
- 订阅 ExtensionAPI `tool_call` 事件，返回 `{block: true, reason}`（core/extensions/types.ts ToolCallEventResult 原生支持）
- 覆盖工具与参数字段：`read.path` / `ls.path` / `find.path` / `grep.path` 同一套 containment
- task.md 带 `read_scope:` 时启用；无 read_scope → 不拦截（手动/旧任务行为不变）

**containment 算法**（实现锁定，B3 处置）：
1. **基准**：scope 条目与请求路径均相对 worker cwd（= 项目根，launcher 保证）
2. **归一化**：`path.resolve(projectRoot, p)` 先词法消解 `..`/`.`，再 `fs.realpathSync` 消解 symlink/junction；不存在路径：对最深存在祖先 realpath 后拼回剩余段（读取本身会失败，但归一化不可被绕过）
3. **比对**：`realpath(请求)` 必须等于某 `realpath(scope)` 或以其 `+ path.sep` 开头（**段边界**，杜绝 `goal-autopilot-evil` 匹配 `goal-autopilot`）
4. win32 双侧 lower-case 比对（盘符归一）
5. grep 的 glob 匹配结果不单独校验（根已在界内）

**caps**：
- 文件数 cap = worker 生命周期内放行的 read/ls/find/grep 调用累计（`l2_read_file_cap`，默认 8）
- 字节 cap = read 实际读取字节累计（`l2_read_byte_cap`，默认 65536）
- 超限 block（rule=cap-file / cap-byte）
- cap 值来源：task.md frontmatter（conductor 派发时写入）→ 缺省用默认

**拒绝记录**：
- `{tool, path, rule, ts}` 内存累积 → 退出时写 output.md `## Read Scope Rejections` 节
- trace.log 逐条 `[READ_SCOPE] blocked path=... rule=...`

## 输入
- 依赖文件: `worker/worker-mode.ts`（parseTaskMd / tool_call 注册点）、`worker/output-writer.ts`（output.md 统一写出点）
- 依赖 Task: T-06（read_scope frontmatter 协议定义）
- AC 约束:
  > AC-009: 在 L2 worker 执行期间，其文件读取限于 dossier 引用的指针集合加白名单路径，白名单外读取调用被拒绝且在 output.md 留拒绝记录（含被拒路径与命中规则）
- 设计约束:
  > D-106: containment 算法六条全文；scope 授权语义 = dossier 指针集合 + 白名单（key 目录 + goal.md）

## 预期产出
- `worker/worker-mode.ts` 改（拦截器 + caps + 拒绝记录）
- `packages/coding-agent/test/suite/autopilot-read-scope.test.ts`（vitest，测试名含 VC 编号）：
  - 越界 block（reason 含路径与规则）+ output.md 拒绝节含条目 + 界内放行（VC-011 三断言）
  - 段边界：`goal-autopilot-evil` 不匹配 `goal-autopilot`
  - `..` 逃逸、symlink/junction 指向界外、win32 大小写/盘符
  - 不存在路径归一化不可绕过
  - cap-file / cap-byte 触发
  - 无 read_scope 任务零拦截（协议兼容）
- 验证方式: 定向 vitest + `npm run check`
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 12:35 | 实现：新建 worker/read-scope.ts（纯 containment/cap 算法：isSameOrUnder 段边界 + win32 lower；normalizeForCompare resolve→realpath 含最深存在祖先回退；isWithinScope；checkReadScopeCall 含 cap-file/cap-byte；readScopeConfigFromMeta 缺省 8/65536）；worker-mode.ts 接线（parseTaskMd 解析 read_scope 块列表 + l2_read_file_cap/l2_read_byte_cap；tool_call 拦截器覆盖 read/ls/find/grep，缺省 path 归为项目根；拒绝双落盘：trace.log [READ_SCOPE] 阻断即写 + output.md `## Read Scope Rejections` 节经 writeOutputGuarded 挂到全部 4 个 writeOutput 退出点） | 代码完成 |
| 1 | 2026-09-10 12:35 | 验证：test/suite/autopilot-read-scope.test.ts 定向 vitest 19/19 绿（VC-011 三断言、段边界、../ 逃逸、junction/symlink 界外含不存在尾、win32 大小写/盘符、不存在路径归一化、cap-file/cap-byte、无 read_scope 零拦截）；既有 test/extensions/agent-team-loop.test.ts 90/90 绿（无回归）；npm run check：biome/pinned-deps/ts-imports/shrinkwrap/install-lock/browser-smoke 全过，tsgo 26 错全为 packages/ai 存量噪音（非本任务引入，未修） | 验证通过 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | lint | packages/coding-agent/test/suite/autopilot-read-scope.test.ts:418 | lint/suspicious/noShadowRestrictedNames: Do not shadow the global "escape" property | 已修（变量改名 escapeBlocked） |
| E2 | tsgo | packages/ai/*（src/providers/cloudflare-ai-gateway.ts + 12 个 test 文件，共 26 处） | error TS2353/TS2345/TS2741/TS2322/TS2339/TS1294 等（如 '"openai-completions"' does not exist in type Partial<Record<...>>） | 存量噪音，非本任务引入，未修（任务书明示如实报告） |

### PM 验收备注（2026-09-10 14:35）
亲跑 19/19 + agent-team-loop 90/90 无回归；代码走查：read-scope.ts 纯算法（段边界 + win32 双侧 lower/归一化最深存在祖先回退拼尾/cap 顺序 containment→cap-file→cap-byte 仅 read 计字节/空 scope fail-closed 已文档化）与 worker-mode.ts 接线（无 read_scope 零拦截/缺省 path 归为 `.` 堵住省参绕过/拒绝双落盘/4 个 writeOutput 退出点全走 writeOutputGuarded）均正确；git status 仅 3 个预期文件无散落。设计超预期处：空 read_scope 列表 fail-closed（防误配任务）与 read 字节 cap 用 statSync 文件大小计费均有据可依。验收通过。
