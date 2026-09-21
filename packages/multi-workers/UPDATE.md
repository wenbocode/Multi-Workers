# MW / AgenticTask 更新总览（Update Matrix）

> 目的：本地更新（MW 源码 / pi core / AgenticTask 框架）之后，pi 窗口依据**版本锚点**做增量自检，
> 只对落后的层执行最小更新动作。
> 读者：pi 窗口（PM / Worker / 交互）与人类。本文位于 Multi-Workers 检出内；其他项目的 pi 窗口
> 用绝对路径读本文件即可（`<MW 检出>\packages\multi-workers\UPDATE.md`）。

## 0. 三层更新面

```
机器层（仅 Multi-Workers 检出机）
  扩展 bundle（~/.pi/agent/extensions/agent-team-loop.js，全局）
  pi dist（packages/coding-agent/dist；npm 全局 pi 链到它）
  .tmp/agentic-task 框架缓存（无检出机器的 init 源）
        │  install.py（单一事实来源，mw init 内部调用）
        ▼
项目层（每个用 MW 的项目）
  .claude/{commands,agents,skills,scripts}   ← 文件复制，源即时生效
  .agents/skills/agentic-task                ← git 克隆，pull --ff-only（依赖源已 push）
  .agentic-framework                         ← 安装时间点 manifest（commit=）
  .mw/（serve.meta、dispatch.yml、launcher.log）
        │  重启 pi 窗口 / /reload
        ▼
窗口层（pi 进程内存）
  扩展 bundle/dist：仅启动时加载 → 改动必须重启窗口
  skill 面（SKILL.md 摘要、goal 门禁）：/reload 刷新；references/ 与 scripts/ 磁盘读、即时生效
```

传播关键差异：`.claude/` 是**文件复制**（源是检出仓时，未提交状态也会被装进本机项目）；
skill 克隆是 **pull --ff-only 自远端**（只认已 push 的 commit）。两面包一致以 push 为准。

## 1. 版本锚点（时间点信号）

| # | 锚点 | 位置 | 读取 / stale 判定 | stale → 修复 |
|---|------|------|------------------|--------------|
| A1 | MW 扩展 bundle | `~/.pi/agent/extensions/agent-team-loop.js` | mtime 对比 `packages/coding-agent/src/extensions/agent-team-loop/` 最新源 mtime；或 `/mw doctor` 报「扩展 bundle: 源码较新，建议 /mw build 重建」 | `/mw build`（任意 pi 窗口，等价 `mw build --install`）→ **重启 pi 窗口** |
| A2 | pi dist | `packages/coding-agent/dist` | dist mtime 落后 `packages/coding-agent/src` | `mw build --install`（默认含 dist 重建；`--no-dist` 跳过）→ 重启窗口 |
| A3 | mw serve | `<project>/.mw/serve.meta`（`started_at_ms`） | serve 启动时间早于 `packages/multi-workers/*.py` 最新 mtime；窗口启动 banner 与 `/mw status` 直接报 `STALE CODE … Run /mw restart` | 该项目窗口 `/mw restart`（在飞 worker 由新 launcher orphan reconcile 收养） |
| A4 | 框架源仓 | `<MW 检出>/.agents/skills/agentic-task`（live 工作仓库） | `git status`（未提交）；`git log origin/master..HEAD`（未推送） | `git commit` + `git push`（发布给其他机器 / 已装项目） |
| A5 | .tmp 框架缓存 | `packages/multi-workers/.tmp/agentic-task` | `git fetch origin` 后 `git rev-list HEAD..origin/master --count > 0` | `mw pull-agentictask`（`--force` 弃本地分歧，reset --hard 对齐远端） |
| A6 | 项目 skill 克隆 | `<project>/.agents/skills/agentic-task` | 同上 vs `origin/master` | `/update-agentictask`，或手动 `git -C … pull --ff-only`（前提 A4 已 push） |
| A7 | 项目 .claude 适配器 | `<project>/.claude/{commands,agents,skills,scripts}` | `python <框架源>/diff-installed.py <project>`（exit 1 = 有差异） | `/update-agentictask` 或 `install.py`（文件复制即新） |
| A8 | 安装时间点 | `<project>/.agentic-framework`（`commit=` 字段） | 与框架源仓 HEAD 对比 | 落后 → `/update-agentictask` 重装 |
| A9 | 窗口内缓存 | pi 进程 | — | bundle/dist 变更 → 重启 pi 窗口；仅 skill 面 → `/reload` |

## 2. 指令矩阵

| 指令 | 层级 | 关键参数 | 动作 | 生效时机 | 注意 |
|------|------|---------|------|---------|------|
| `mw bootstrap` | 机器 | `--project` `--from` `--branch` `--fast` `--no-start` | 新机器 8 步全链路（npm → build → link pi → setup → init → start → doctor） | — | 全部幂等可重跑；见 README |
| `mw setup` | 机器 | `--build` `--source <dir\|url>` `--branch` `--force` | 克隆/更新 `.tmp` 缓存 + 全局装 bundle + 写 `.mw-py-path` + 装 `/update-agentictask` + 补 pi `shellPath`（additive，不覆盖已有值） | 新窗口 | `--build` 先重建 bundle 一步到位 |
| `mw build` | 机器 | `--install` `--no-dist` | esbuild 重建扩展 bundle；`--install` 另：全局装 bundle + `.mw-py-path` + update 命令 + 重建 pi dist | 重启 pi 窗口后 | 全局 pi 链到仓内 dist，所以 dist 也要重建 |
| `mw init` | 项目 | `--project` `--sync-agentictask <dir>` `--no-framework` | 项目脚手架 + 框架安装，幂等（`.agenticdoc` 存量零触碰） | 立即 | 框架源解析：`--sync-agentictask` > 检出仓 `.agents/skills/agentic-task`（**含未提交状态**）> `.tmp` 缓存 |
| `/update-agentictask` | 项目窗口 | —（内部 = `mw init --project <cwd>`） | 一键更新本项目框架安装：`.claude/` 复制 + skill 克隆 pull + manifest 重写 | 脚本/文档即时；`/reload` 刷新 skill 摘要与 goal 门禁 | skill 克隆的 pull 依赖源已 push（A4） |
| `install.py`（框架源自带） | 项目 | `--skip-claude` `--skip-codex` `--codex-scope user\|project` | 先从 `scripts/` resync `claude/scripts` + `core/scripts` 镜像 → 复制 `claude/` → `.claude/` → clone/pull skill 克隆 → 写 `.agentic-framework` | 同上 | 镜像变更会提示 commit & push；mw init 内部调的就是它 |
| `mw pull-agentictask` | 机器 | `--force` `--branch` | clone / `pull --ff-only` 更新 `.tmp` 缓存 | 作为无检出机器的 init 源 | 本机有检出仓时 `.tmp` 只兜底 |
| `mw push-agentictask` | 机器 | — | 从 `.tmp` 克隆 commit+push 回远端 | 发布 | 检出机上一般直接在 `.agents/skills/agentic-task` 推 |
| `sync_framework.py`（已装项目内跑） | 项目 | `-m "msg"` `--direction auto\|to-install\|from-install` | auto：源仓脏 → commit/push + 重装；源净但适配器漂移 → **反向**拷回源仓 + 发布 + 重装；无差异退出 | — | 项目侧手改了 `.claude`/克隆时的发布通道 |
| `diff-installed.py` | 项目 | `<project>` | 漂移报告：克隆本地改动 / 克隆 HEAD vs 源仓 HEAD / `.claude` 差异 | — | exit 0 = 无差异，1 = 有 |
| `migrate_patterns.py` | 项目 | `--dry-run` | 一次性 legacy `{key}/patterns/` → `patterns/{key}`（pre-`efe1e44` 项目） | — | 手动幂等，不在自动更新流内 |
| `mw update-env` | 机器+项目 | `--project` `--apply` `--json` `--fetch` | 增量自检（本文 §1 全部锚点）+ 报告；`--apply` 按依赖序执行 [auto] 项（build→缓存→框架重装→serve 重启）并复查；`--fetch` 先刷新 origin 引用 | 检查即时；apply 后窗口侧仍需人工 | §3/§4 的工具化；退出码 0=healthy / 1=需要动作 |
| `/mw build` | 任意窗口 | — | 重建 + 全局安装（bash-free） | 提示后重启 pi 窗口 | 同 `mw build --install` |
| `/mw update` | 任意窗口 | `--apply` | 转发 `mw.py update-env`：锚点自检报告；`--apply` 执行安全修复 | 检查即时；apply 后窗口侧仍需人工 | 退出码 1 = 有发现项（同 doctor 语义） |
| `/mw restart` | 项目窗口 | — | 优雅停 + 起 serve；banner 报 stale 时用 | 即刻（新 PID） | 在飞 worker 被新 launcher 收养 |
| `/mw status` / `doctor [fix]` | 项目窗口 | — | serve 状态（含 STALE CODE 判定）/ 全链路诊断 | — | doctor 含 bundle、launcher log、队列、活性、凭据、派发档 |
| `/mw model set <role> <prefix/model>` | 项目窗口 | role: main/coding/review/research | 写 `.mw/dispatch.yml`（pi 窗口内先行 registry 校验，错 id 拒写） | worker role **下次 spawn**（无需重启 serve）；`main` 下次窗口启动 | 配置面而非代码面，常与更新混问 |
| `/reload` / 重启 pi 窗口 | 窗口 | — | 刷新 skill 摘要 + goal 门禁 / 重载扩展 bundle + dist | — | 扩展 bundle 只在进程启动时加载 |

## 3. 场景 → 最小动作

> 本节与 §4 已工具化为 `python mw.py update-env --project <dir> [--apply]`（pi 窗口：`/mw update [--apply]`）：
> 按序读锚点、只报 stale 层；`--apply` 自动执行 [auto] 项后复查，人工项（push / 重启窗口 / /reload）单独列出。

| 变更了什么 | 检查锚点 | 最小动作 | 重载需求 |
|-----------|---------|---------|---------|
| agent-team-loop TS 源 | A1 | `/mw build` | 重启 pi 窗口 |
| mw Python（mw.py / mw_common / launcher / autopilot） | A3 | 各受影响项目窗口 `/mw restart`（serve 是 per-project 的） | 无 |
| pi core（packages/coding-agent/src） | A2 | `mw build --install` | 重启 pi 窗口 |
| AgenticTask 框架 .md / scripts | A4 → A6/A7/A8 | 检出仓 `commit + push` → 各项目窗口 `/update-agentictask` | `/reload` |
| 派发模型档位 | — | `/mw model set …` | 无（下次 spawn / 下次窗口） |
| 全新机器 | — | `mw bootstrap`（内部含 setup + init） | — |
| 全新项目 | — | 打开 pi 窗口即自动 init（`.agenticdoc` 缺失时）+ 自动起 serve；goal.md 须 `/goal` 共创，不自动填 | — |
| `.tmp` 缓存落后 / 本地分歧 | A5 | `mw pull-agentictask`（分歧用 `--force`） | — |
| 项目侧手改了 `.claude` 或 skill 克隆 | A7 | `diff-installed.py` 定方向 → 保留：`sync_framework.py`（from-install 发布）；丢弃：`/update-agentictask` 覆盖 | `/reload` |

## 4. pi 增量自检流程（checklist）

> 一键等价：`python mw.py update-env --project <dir> --apply`（或 pi 窗口 `/mw update --apply`）。
> 下面是它内化的手工流程，供无 CLI 时或排查时对照：

在收到「更新一下 / 检查是否要更新」类指令，或本地源刚更新完需要验证传播时，按序执行，
**只处理 stale 的层**：

```
S0 定位窗口类型
   cwd 存在 packages/multi-workers/mw.py → 开发机（全量：S1→S6）；
   否则 → 项目面（从 S3 开始）。

S1 [开发机] 扩展 bundle（A1）
   /mw doctor 看「扩展 bundle」行（或比 bundle mtime vs 源 mtime）。
   stale → /mw build；记下「本窗口稍后需重启」。

S2 [开发机] mw serve（A3）
   看窗口启动 banner 或 /mw status 的 STALE CODE 行。
   stale → /mw restart（每个活跃项目各跑一次）。

S3 [任意项目] 框架面（A6/A7/A8）
   a. 读 .agentic-framework 的 commit；git -C .agents/skills/agentic-task 看 HEAD 与 origin/master。
   b. python <框架源>/diff-installed.py <project> 看 .claude 漂移。
   任一落后/漂移 → /update-agentictask
   （开发机源含未提交状态即装 .claude 面；他机 skill 克隆面需源已 push——
    发现 push 缺失时先提醒在检出机上 push）。

S4 [任意项目] legacy patterns（一次性）
   pre-efe1e44 项目：migrate_patterns.py --dry-run 确认后再实跑。

S5 收尾生效
   S1 有变更 → 重启 pi 窗口（扩展 bundle/dist 只认进程启动）。
   仅框架面变更 → /reload（刷 skill 摘要与 goal 门禁）。

S6 验证
   /mw status：serve 新 PID 且无 STALE CODE；
   /mw doctor：summary healthy；
   窗口 skill 摘要已刷新（/reload 后）。
```

## 5. 边界与陷阱

1. **未提交状态的传播不对称**：检出机的 init 源第 2 优先级是 live 工作仓库（源码注释明示
   "May carry uncommitted state: commit & push first when you want published state propagated"）。
   本机 `.claude/` 复制面立即带未发布内容；skill 克隆 pull 面只认远端 commit。**发布以 push 为准**。
2. **全局 bundle 优先**：项目本地 `.pi/extensions` 副本在全局副本存在时会被删除
   （重复注册 → pi 拒载 "tool conflicts"）。排查扩展问题先看全局目录。
3. **serve 是 per-project**：每个项目自己的 serve + launcher（`.mw/serve.meta`）。mw Python 更新后
   每个活跃项目都要各自 `/mw restart`。
4. **spawn 期解析**：角色/模型档（dispatch.yml）与 target/partition 模式都在**每次 spawn** 重新解析，
   改配置不需要重启 serve——只有 mw Python 代码本身变更才需要 restart。
5. **`/reload` 刷不到 bundle**：skill 面（SKILL.md 摘要、goal 门禁）用 `/reload`；扩展 bundle/dist
   永远要重启 pi 窗口。
6. **镜像提醒**：install.py 每次运行先把 `scripts/` 正典 resync 到 `claude/scripts` + `core/scripts`
   镜像；镜像被改时必须 commit & push 才发布。
7. **受保护配置**：任何更新动作不得在会话内改 `~/.pi/agent/` 下的 auth.json / settings.json 等
   （`_pitfalls.md` P-002；扩展与 mw Python 双侧硬拦截）。pi `shellPath` 的填充由 `mw setup` 走
   additive merge，属例外通道。
8. **写文件纪律**：自动化更新脚本一律遵守框架内置坑点 B-001（先算后写 / 原子替换），
   见 `.agents/skills/agentic-task` pm-mind「框架内置坑点」。
