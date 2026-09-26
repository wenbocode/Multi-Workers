# Spec 期调研声明与并行计划（RQ-1..RQ-4）

- key：`mw-autopilot-verify-cli` · 日期：2026-09-26
- 性质：**spec 期调研声明 + 并行派发计划**（框架要求：派发 worker 前该 key 的 `evidence/research/spec-*.md` 必须非空；本文件即为该声明，非占位）
- 用户需求原文（2026-09-26）：① "做成一个 mw autopilot 指令，让 cmd 自动部署到项目"；② "dist 重建要做"

## 并行性分析（写面切分）

四个 RQ **彼此只读、问题域不重叠、输出文件唯一**，因此一次性并行派发：

| RQ | 问题域 | 唯一输出文件 |
|---|---|---|
| RQ-1 | mw CLI 既有"写项目配置"命令的实现范本（argparse 形状 / 写入助手 / 报错 / CLI 测试 / doctor 检查项 / 项目根定位惯例 / 组名冲突） | `evidence/research/spec-cli-patterns-20260926.md` |
| RQ-2 | autopilot 项目配置读写契约（DEFAULTS/validate/cached_load 语义、谁写、写后拾取、空命令现行为、TS 镜像同步清单） | `evidence/research/spec-config-write-contract-20260926.md` |
| RQ-3 | dist 重建机制与风险（`mw build`/`--install`/`--no-dist` 行为链、tracked 边界、UPDATE.md 锚点与 update-env、机器判据、多会话风险、测试覆盖） | `evidence/research/spec-dist-rebuild-20260926.md` |
| RQ-4 | verify 命令可移植性事实（target.yml 占位解析、四个根的算法、RAG 两层配置范本、env 覆盖惯例、现网 config 实况、解释器绑定后果） | `evidence/research/spec-verify-cmd-portability-20260926.md` |

共享资源与冲突面：四个 worker 均为 **read-only**（工具白名单 read/find/grep/ls/bash），唯一写面是各自的证据文件；**无共享文件**，不需要串行。PM 同期做 dist 重建（写面仅 `packages/multi-workers/dist/**`，与四个 RQ 无交集）。

## 为什么这些 RQ 是必需的（与 AC 的对应）

- AC-001..AC-005（CLI 形状、幂等、拾取、show/clear、层级解析）→ 需要 RQ-1 的既有惯例 + RQ-2 的拾取语义；**AC-002 的判据完全依赖 RQ-2**（`cached_load` 是否真能被写后失效，Windows mtime 精度是已知风险点）。
- AC-006（两侧校验不放宽）→ RQ-2 第 5/6 问给出必须同步的具体位置清单。
- AC-007（占位符与 cwd）→ RQ-4 第 1/2/6 问；**若不成立则 AC-007 必须重写或降级为未决项**。
- AC-008（启用前自检告警）→ RQ-2 第 4 问（空命令的确切失败路径）+ RQ-1 第 5 问（doctor 检查项形状）。
- AC-009（dist 重建判据）→ RQ-3 第 1/2/3/4 问；**判据不足则以 RQ-3 的建议为准**。
- AC-010/AC-011（文档与零扰动）→ RQ-1/RQ-3 的既有文档面与基线证据。

## 已知前置事实（PM 已核实，供 worker 复用，不必重复验证）

- `mw` 现有子命令：`serve,start,stop,status,doctor,target,partition,model,init,pull-agentictask,push-agentictask,setup,bootstrap,build,update-env,ue-toolchain,rag` ——**无 `autopilot` 组**（`mw.py --help` 实测）。
- `packages/multi-workers/dist/extensions/agent-team-loop.js`（916378 B，2026-09-24 16:54）**被 git 跟踪**（`git ls-files` 实测），当前落后于源码（缺 `xkey-authorize` kind 与 `xkey-gate-guard`）。
- `mw build`（`mw.py:4791`）用 esbuild 重建该产物（bash-free、cwd-independent，`_build_bundle():3516`）；`--install` 另装全局扩展位并（默认）跑 `_rebuild_pi_dist():3550`（`npm run build`）。
- 项目配置只有单层：`autopilot/config.py` 零处读 env/`$HOME`；FM `_autopilot/config.json` 存在但**未跟踪**（`?? .agenticdoc/_autopilot/`），MW 无 `_autopilot/` 目录，E2 有配置且未跟踪。
- RAG 已有**两层**配置范本（`mw_common.py:374` 项目层 / `:382-395` 机器层 `MW_RAG_SERVERS_HOME → $HOME → $USERPROFILE`）。
- verify 现状：`xkey.run_verification(cmd, cwd=..., run_dir=..., timeout=...)`，`shell=False`、argv 原样（零展开）；conductor 传入 `root = str(project_root)`（`:2468`/`:2645`）。
- E2 的 `.agenticdoc/target.yml` 为 `active: partition`（parent `E:\UEMigrator` / partition `H:\git\E2Feature`），toolchain 段注释声明 `{parent}/{partition}/{root name}` 占位。

## 待 PM 定稿（RQ 吸收后）

- U-1 机器级默认层是否纳入（用户上一轮提问指向"要"，待 spec 门禁确认）
- U-2 占位符集合与 `{python}` 绑定语义
- U-3 dist 重建执行面（`mw build` / `--install` / `update-env --apply`）
- U-4 多会话并行下重建的护栏
