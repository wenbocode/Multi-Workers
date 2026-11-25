# mini-spec: mw-anti-ornament-followup

> Key: mw-anti-ornament-followup（pm mini 快速通道）
> 来源: 2026-11-24 用户“按你建议，你来改”
> 前身: key `mw-anti-ornament-guardrails`。本单只修订其交付物的措辞和测试断言，不改逻辑。
> 状态: 已实施并自验，改动已提交；发布记录见文末。

## 目标

把 `mw-anti-ornament-guardrails` 评审中提出的 4 点修正落到它的交付物上：

1. 通用 worker 护栏只保留反粉饰一条；三条 UE 生命周期教训移到 Gaze 的 `AGENTS.md`。
2. 协作约定和 PM 协议恢复“每卡至少经真实入口调用一次”，去掉 UE 专有词汇。
3. 独立评审的触发条件由“复杂改动”改为可机械判定的路径类型。
4. AgenticTask 的 `[FLOW]` 日志由“每节点一条”改为按需，和已不逐节点检查的 design/review 对齐。

## 范围

- MW：`worker-mode.ts`、`pm-orchestrator.ts`、`agent-team-loop.test.ts`、根 `AGENTS.md`、`templates/AGENTS.md`、`test_init_agents_guide.py`、`docs/plan-closure.md`。
- AgenticTask 开发克隆：`references/workflow-code-gen.md`、`references/workflow-structured-logging.md` 及各自的 3 份镜像（保持字节一致）。
- Gaze：`E:/MWWS/Gaze/AGENTS.md` 顶部追加“项目工程约束”一节。

## 验收（AC）

| 编号 | 判据 | 结果 |
|---|---|---|
| AC-001 | `CODING_INVARIANT_GUARDRAIL` 只含反粉饰一条，不含 delegate/track、解绑、归属字样；coding/repair 注入且幂等 | 通过：97 字符（原 266）；vitest `injects CODING_INVARIANT_GUARDRAIL idempotently for coding/repair only` 通过，含新增的反向断言 |
| AC-002 | `PARALLEL_PROTOCOL` 含“至少经真实入口调用一次”“涉及异步、取消、绑定或失败态路径时另派独立评审”“重型真机留证只在竖切收口做一次”，不含 UE 专有词，长度 ≤ 2500 | 通过：2378 字符（原 2364，上限 2500）；协议用例通过 |
| AC-003 | 安装后的 AGENTS 指南含同样的三条，且不含 delegate/track、失效解绑、归属重验 | 通过：`test_init_agents_guide.py` 19 passed |
| AC-004 | code-gen 与 structured-logging 的 4 份镜像各自字节一致，且不再出现“每个节点对应一条 `[FLOW]`” | 通过：code-gen `2BE0031844` ×4，structured-logging `FB04D8F0A2` ×4（SHA256 前 10 位）；克隆内 `rg '每个节点对应一\|覆盖 Function Flow 全部节点'` 无命中 |
| AC-005 | Gaze `AGENTS.md` 顶部含三条生命周期约束原文，原有内容逐字节保留 | 通过：5431 → 5941 字节，原内容作为后缀逐字节保留；备份 `%TEMP%\mwstats\Gaze-AGENTS.md.bak-20261125-005143` |

## 证据

- `evidence/npm-check.log`：`npm run check` 完整输出，rc=0，前后 `git status` 无变化。
- `evidence/vitest-summary.txt`：`agent-team-loop.test.ts` + `agent-team-loop-checkpoint-wiring.test.ts`，227 passed / 3 failed。3 个失败与改动前基线相同，均非本单引入：
  - `dispatch_worker declares type, keeps legacy defaults…`（自 90ace0f6f 起就红，无归属）
  - `VC-MWGF-021` 语料文件 `review-mw-worker-tree-kill` 缺失（环境绑定）
  - 锚点完整性：68 处 `[ANCHORS] mismatch`，数量与改动前一致
- 规模实测：`node %TEMP%/mwstats/prompt-size.mjs E:/gitlite/Multi-Workers`。
- 执行日志：`%TEMP%\mwstats\aof-atl.log`、`aof-biome.log`、`aof-npm-check.log`。

## 与原建议的差异

- `workflow-structured-logging.md` 有同一句“每个节点对应一条”，一并改为按需，否则两份文档互相矛盾。
- Gaze 没有 `_pitfalls.md`，也不是 git 仓库，所以三条教训放进 `AGENTS.md` 顶部的新节；写入前已备份。
- 保留标识符 `CODING_INVARIANT_GUARDRAIL`，只改了注释和标记文本。

## 不做

不提交、不推送、不构建发布、不重启后端或 PM 窗口；不改 `dual-toolchain-practice-guide.md`（UE 专有指南，保留 UE 词汇）；不改 `mw-anti-ornament-guardrails` 的 Codex 记录。
