# T12a 窗口只读入口功能闭环

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；本key spec.md AC001和AC006、design.md窗口入口、原tasks/T12-window-entry.md。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4496` parseDecideArgs；`packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:575` decideMw。
- 用户明确按优先级推进功能闭环。拆出只读dp入口与monitor路由，不依赖未交付T08和T09生命周期。Python CLI已有25DP，T10 monitor接口已有。
- ui-bridge现有其他会话21行diff必须保留，当前_workers.parallel仅T05q running不写TS，跨key均idle。首写前保存当前基线与diff，发现新活写者停止报PM不覆盖。

## 要求
真正修复窗口unknown sub dp：dp list/show/export只读及monitor命令先于watched-key要求解析。拒on/off/set/apply/verify-live/export--write及未知尾参数，旧sign等intentional功能不删。薄转发复用Python真实CLI与runner，不能仅加parser mock即声称入口闭环。
先完整分页读改动文件、pi官方README及相关docs和md交叉引用，按harness faux provider真实入口测试，先正确RED再实现GREEN。无key也能列25集合与PythonCLI一致；monitor正确argv且不实际打开窗口或起共享服务，启动模拟只证路由，真实浏览器仍未授权。
T12原生命周期依赖仅本切片解除，不追认整体T12完成。未知root failclosed，不硬编码快捷键，不改pi核心，不inline import或any。
完整隔离HOME凭证，不读真实auth，不模型外网，不build/commit/共享serve。只读check分拆非完整npm check通过，禁止biome --write越面。

## 写入允许面
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（decide入口局部）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`（对应薄转发）
- `packages/coding-agent/test/suite/decision-dashboard-command.test.ts`
- `.agenticdoc/mw-decision-dashboard/workers/dd-command-closure/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T12a-*`

## 写入禁止面
其他源测试、worker-mode、README、其他会话diff、生产凭证账本、依赖锁、dist、pi核心、任务相位。

## 验收命令
coding-agent目录 `node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-dashboard-command.test.ts`；root只读biome严格与tsgo及check子步，全输出日志含argv/cwd/exit/hash。不运行全suite/build/npm test。

## 改动历史
- PM按用户功能闭环优先拆出原T12可先行只读入口。T05q Python安全写者并行无文件冲突。

## 交付格式
report最多110行，RED/GREEN/真实入口覆盖/保留他人diff/下游路由与未覆盖。不得自报browser可见或整体T12完成。
