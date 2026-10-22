# D1 设计调研：dp 注册表 + 配置表 + `mw decide dp` 指令族

- type: research
- 唯一证据文件: `.agenticdoc/mw-decision-substitution/evidence/research/design-registry-config-20261019.md`
- goal 锚点: `.agenticdoc/goal.md`（"文件驱动的去中心化协调"、"项目级目标对齐"）
- 超时: 30m

## 上下文（已冻结，别推翻）

spec 定稿 rev3：授权**唯配置论**，配置表 `.mw/decide-points.json` 是唯一权威；P2 默认开，P1/P0 默认关；机器零写配置；`mode ∈ {auto,suggest}`；P0 开启需 `--i-understand-p0`。24 个 dp 的 id/档位见 `spec.md` §4。

底座可复用：`packages/multi-workers/decision.py:111-134`（响应与 11 字段证据）、`:402-417`（`_encode_state` 规范化）、`mw.py:672-688`（`_DECIDE_SET_KEYS` 白名单）、`mw.py:772-792`（`_decide_write_config`：锁 + tmp + `os.replace`）、`mw.py:794-813`（`_decide_run`）、`mw.py:953-987`（`cmd_decide` 分支）、`mw_common.py:2369-2384`（`acquire_lock`）。

## 要求（逐条回答，每条带 path:line）

- **RQ-1 注册表数据结构**：`DecisionPoint` 应有哪些字段（id / tier / default_enabled / default_mode / questions / build_state / executor / questions_version / 描述）？各字段的类型与生产者；问题集常量如何与 TS 侧 `DP1_QUESTIONS`（`pm/triage-client.ts:55-58`）对齐而不双写。给最终 Python 代码骨架（可编译的 stub 级别）。
- **RQ-2 `decide_for` 控制流**：从 `(dp_id, trigger)` 到"生效/上抛人"的完整分支序列：未知 dp → 配置缺行 → enabled=false → mode=suggest → 预算/可用性 → 校验失败 → binding 执行。每步给出返回类型与 `escalated_reason` 取值。必须证明 `enabled=false` 路径零 spawn 零网络（对照 `triage-client.ts:14` 的 complete-bypass 语义）。
- **RQ-3 配置表 schema 与校验**：JSON 形状、字段类型/取值域、`version` 演进策略；读侧 fail-soft 的具体分层（文件缺失 / JSON 语法错 / 行不是对象 / 字段类型错 / 未知 dp / tier 与 enabled 冲突）；`dp check` 应报哪些项、exit 码。
- **RQ-4 热重载**：按 mtime 重读的缓存放在哪（进程内全局 / `lru_cache` / 每次读文件）、并发与锁的边界、Windows 上 mtime 精度是否够（至少要指出风险与替代：size+mtime 或 `st_mtime_ns`）。要给出可测的"改文件后下一次决策即生效"方案。
- **RQ-5 `dp` 指令族**：`list/show/on/off/set/refresh/check/preset` 的参数、输出（人读 + `--json`）、exit 码；`on` 对 P0 的 `--i-understand-p0` 缺失时行为；`set` 允许的键集合；与既有 `cmd_decide` 的解析顺序冲突（`mw decide dp ...` 与 `mw decide set ...` 如何分流，锚点 `mw.py:953-987`）。
- **RQ-6 `refresh` 合并算法**：注册表 → 配置表的单向合并伪代码：新增缺失行用默认值、不动已有 `enabled/mode`、注册表已删的 dp 标 `orphaned` 不删、`updated_by=refresh` 是否写、幂等性证明（第二次 added=0）、输出计数格式。

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/design-registry-config-20261019.md`

## 写入禁止面

- 任何源码（`packages/**`）、配置（`.mw/**`）、其它 key 目录、其它 evidence 文件
- 禁止 `git add` / `git commit` / `git checkout` / `git stash`

## 交付格式

- 只写唯一证据文件；文件头写 `# D1 设计调研`，每问一节 `## Q1..Q6`，末尾 `Q-answered: 6/6`。
- 结论必须给 `path:line`；无法确认写"未验证"并说明缺什么。
- 不修改任何源码/配置；不做 git 操作。

## 验收命令

```
grep -c '^## Q' .agenticdoc/mw-decision-substitution/evidence/research/design-registry-config-20261019.md
```
期望 6。
