# T-02 `mw decide dp` 指令族

- key: mw-decision-substitution · type: coding · phase TASKS
- timeout: 40
- 依据: spec.md rev3（AC-001/002/010/012）+ design.md D-001、D-014、D-016、D-022 + plan.md §1

## 上下文

- `mw decide` 已有子命令 `run/probe/show/set`，入口 `mw.py:cmd_decide:953`；`decide_sub` 挂载点在 `mw.py:7508`。
- 写协议复用 `mw.py:_decide_write_config:772-792`（锁 + tmp + `os.replace`）。
- 契约见 design §2.5 的命令表与 exit 码（0/1/2）。

## 要求

1. 在 `mw.py` 的 `dp` 子命令段实现 `list / show / on / off / set / refresh / check / apply(骨架)`：
   - `on` 对 P0 必须要求 `--i-understand-p0`，缺失时 exit 2 **且配置文件 sha256 不变**（测试断言）。
   - `set` 白名单 `tier|enabled|mode|note`，非法值 exit 2。
   - `refresh` 单向合并：补缺失行、不动已有 `enabled/mode`、标 `orphaned`、**无变化不写文件**、幂等（第二次 added=0）。
   - `check`：坏行 / 孤儿 / tier 冲突 / 未注册 id；exit 0 干净、1 warning、2 error。
   - `apply` 本轮只做骨架（读文件 + 校验 conclusion/promote/demote/p0-open 格式 + agent 会话拒绝），真正写回留 T-09。
2. 新建 `packages/multi-workers/test_decide_dp_cli.py`：每命令至少一条用例，含 P0 flag、sha256 不变、refresh 幂等、check 三种 exit 码。

## 交付格式

- 实现按上列写入允许面落地；报告四段：结论 / 证据（命令 + 输出摘要）/ 残留与未验证 / 改动文件清单。
- 每处关键实现附 `path:line`；关闭态未证明前不得声称完成。
- 遇到契约不足：停手并在报告"残留"里写明，禁止自行改契约。

## 种子

- goal 锚点: `.agenticdoc/goal.md`（文件驱动的去中心化协调 / 项目级目标对齐）
- 代码锚点: `packages/multi-workers/mw.py:953`
- 代码锚点: `packages/multi-workers/mw.py:772-792`

## 契约补充（T-03 实现事实，必须对齐）

- `questions_version` 必须是 `q-<8 hex>`（如 `q-3f2a11c0`）；`config_sha_after` 必须是 16 hex。
- `authority-change` 的 `trigger_id` 允许含 `:`（按**首个** `:` 切分 decision_id），ISO 时间戳可直接作 trigger。
- 身份串文法：`human` 或 `human:<account>`（account 非空、无空白）；`agent:*` / `pm` / `worker` 一律拒绝。

## 契约补充二（T-04 实测的集成缺口，必须在本卡闭环）

结构化请求**不再携带 `questions`**（问题集权威在 Python 注册表），但 `mw.py:718` 现行逻辑强制要求该键，实测 `rc=2 "request is missing questions"`。本卡必须改 `_decide_run`：

- 请求含非空 `questions` → 原行为不变（legacy 路径，逐字节兼容）。
- 请求缺 `questions` 且给了 `--dp <id>` → 从 `DP_REGISTRY[dp].questions` 解析并填充；`--dp` 未知 → exit 2。
- 两者都缺 → exit 2，错误信息点名"缺 --dp 或 questions"。
- `dp` 与请求内 `state.dp` 不一致 → exit 2（拒绝歧义）。
- 新增测试：结构化请求（无 questions + 合法 dp）成功；未知 dp 拒绝；缺两者拒绝；legacy 带 questions 字节不变。

## 写入允许面

- `packages/multi-workers/mw.py`（仅 `dp` 子命令及其注册段，不碰 `run/probe/show/set` 既有逻辑）
- `packages/multi-workers/test_decide_dp_cli.py`（新建）

## 写入禁止面

- 除上列文件外的一切文件（含其它包的源码、其它 key 目录、`_pitfalls.md`、`_project_log.md`）
- 禁止 `git add` / `git commit` / `git checkout` / `git stash` / `git clean`
- 禁止修改 `packages/ai/src/models.generated.ts`、禁止跑 `npm run build`、禁止跑完整 vitest 套件（用 `./test.sh` 或指定测试文件）

## 验收命令

```bash
cd packages/multi-workers && python -m pytest test_decide_dp_cli.py -q
python packages/multi-workers/mw.py decide dp list --project .   # 期望列出 24 项，不崩
```

## 改动历史

- 2026-10-20 创建
