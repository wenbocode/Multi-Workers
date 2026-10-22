# RQ-2 — pi 交互面：扩展能否在"人要出现"的位置替代人

- key: mw-decision-substitution · type: research · SPEC 相位调研
- timeout: 40

## 上下文

goal.md（`.agenticdoc/goal.md`）：PM Agent 管多 Worker 并行，减少人工介入。用户 2026-10-16 重定义：**jev 是决策模型，要替换中低风险的人工决策**。要做到"替换"，jev 的答案必须能在**人本来会出现的位置**生效——这取决于 pi 扩展到底能介入哪些交互面。**不能修改 pi 核心**（GC-2），只能走 Extension API。

已知锚点：
- 扩展 API 文档：`packages/coding-agent/README.md`、`packages/coding-agent/docs/extensions.md`、`examples/extensions/`
- 现有 PM 主动唤醒人的通道：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:188`（`deliverPmAlert`）
- 现有工具注册示例：`pm/ui-bridge.ts` 里 worker/PM 工具的注册处；`worker/worker-file-tool.ts:1`
- 现有 worker 终态之一：`needs-clarification`（worker 卡住时甩给人）

## 审计目标（调研问题）

- **Q1 可用钩子清单**：Extension API 提供哪些与本目标相关的钩子？至少核对：自定义工具注册、工具执行前/后拦截（pre/post tool call）、消息/轮次钩子（含 `triggerTurn`/steer 类注入）、用户输入钩子（能否观察或改写用户输入）、会话/系统提示注入、权限/确认门（bash 命令确认、文件写入确认）。每项给 `文件:行号` 与能力边界。
- **Q2 权限与确认面**：pi 的"破坏性操作确认"（命令执行、写文件、危险 bash）在代码哪一层实现？扩展能否**在确认前接管或短路**（比如拿到 tool call 参数、直接返回允许/拒绝并附理由）？如果不能，明确写"不可介入"及原因（这是 DS-3 的判据）。
- **Q3 替代"提问"的可行性**：当 agent 想找人澄清时，现状是什么机制（工具返回提示文本？结束 turn 等人输入？`ask` 类工具？）。扩展能否注册一个工具，让 agent 在"想问人"时调它——**由 jev 回答**，并且答案以什么身份回到对话里最安全（工具返回值 vs 伪造 user 消息 vs 系统注入）？三种方式各自的可见性/审计/风险。
- **Q4 人已表态的检测**：能否从会话里判断"人已经就这件事明确说过话"（人的 override 优先级最高，jev 不得推翻人）？现有什么结构可以读取（消息列表？session 文件？）。给出可行做法或明确"不可行"。
- **Q5 worker 侧**：worker 进程（非 PM）加载的是同一套扩展吗？worker 能不能调用扩展注册的工具、能不能触发 `triggerTurn` 类注入？worker 的 `needs-clarification` 在代码里由谁判定、能否在判定前插入一次决策调用？
- **Q6 成本与副作用**：这些钩子里哪些是**每 turn 都会跑**的（会影响所有会话性能）、哪些是按需触发；接一条决策调用（同步 ~5s）放在哪个钩子最不容易拖慢正常流程。

## 唯一证据文件

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-pi-interaction-surface-20261016.md`（新建，全文中文，每条结论附 `文件:行号`；无法确认的写"未验证 + 缺什么证据"）

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/spec-pi-interaction-surface-20261016.md`

## 写入禁止面

- 一切源码/配置/测试/其它 evidence 文件；禁止 `git add`/`git commit`；禁止改动其它 key 目录

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-decision-substitution\evidence\research\spec-pi-interaction-surface-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

## 交付格式

- 证据文件：`Q1` 钩子能力表（钩子 / 代码位置 / 能做什么 / 不能做什么）；`Q2..Q6` 各一节；末尾「三接触面的可行形态」：PM 侧、worker 侧、pi 确认面各自"能替代到什么程度 + 实现位置 + 风险"。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；**write-first**：前 10 次写调用内先落骨架，再增量补。
