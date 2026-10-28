# D-RQ1 monitor lifecycle and security

type: research

## 上下文
- Goal: `.agenticdoc/goal.md`；锁定需求 `.agenticdoc/mw-decision-dashboard/spec.md`，设计草案 `design.md`（不编码）。
- `packages/multi-workers/mw.py:10217` _publish_stats_html；`:133` serve 元信息；`packages/multi-workers/console_run.py:1` 隐藏进程机制。
- 用户已定：浏览器独立应用窗口，非常规高位端口，monitor 命令开启；真实测试显式人工触发、loopback/访问校验、隔离生产。

## 要求
只读设计取证，不重新要求用户选择 TUI。比较 monitor 独立按需进程与挂 serve 两案，给出生命周期、重复开启、多项目、旧实例/版本、端口占用、退出策略、隐藏控制台和应用浏览器探测的精确契约。候选端口 43170..43269，检查现有项目冲突/浏览器禁用依据，推荐范围与绑定重试（不是先探测再释放的 TOCTOU）。设计最小 loopback HTTP 安全边界：Host/Origin、令牌、CSRF、DNS rebinding、请求大小、方法白名单、XSS、模型提交超时/并发/取消。明确启动 URL 中 token 的泄漏防护、状态文件权限、无浏览器回退。提出 REST 接口候选和 AC-006/007/015 验证。读完整相关小模块/文档；巨大文件用分页完整读相关函数，不要全文件 dump。不得起/停服务、真实模型调用、改代码/配置或安装依赖。

## 唯一证据文件
.agenticdoc/mw-decision-dashboard/evidence/research/design-monitor-lifecycle-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/evidence/research/design-monitor-lifecycle-20261022.md`
- `.agenticdoc/mw-decision-dashboard/workers/dd-drq1-lifecycle/**`

## 写入禁止面
- 所有代码、配置、其他 key、其他任务与相位文档。

## 交付格式
唯一证据 ≤250 行，先结论，再 path:line/版本出处、两案 pros/cons、推荐接口/参数/失败、验证契约、未覆盖。report.md 四段结论/证据/残留与未验证/上下文来源，≤80 行。先写 report.md 骨架再调查；单次命令输出 ≤30 行，read 分页，禁止付费与大规模测试。每条推荐区分证实事实/设计建议，不伪称验证。
