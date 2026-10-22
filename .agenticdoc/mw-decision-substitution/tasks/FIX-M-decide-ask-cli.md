# FIX-M：`mw decide ask` —— 给人真实调用 `timi/jev-latest` 的命令行接口

- type: coding
- owner key: mw-decision-substitution
- 用户 2026-10-20 要求：「要有一个 mw decide 接口来给人真实做 timi/jev-latest」。
- 前置：FIX-L 已把决策传输收敛为唯一 `timi-decisions`（`POST {TIMI_BASE}/v1/decisions`，
  model 默认 `jev-latest`，凭据 `TIMI_API_KEY` → `~/.pi/agent/auth.json` 的 `timi.key`）。
  本卡只做 **CLI 层**（`mw.py`），不碰传输实现。

## 命令契约（人来用）

```
mw decide ask --state <text|@path> \
              [--noul <qid>=<instructions> ...] \
              [--choice <qid>=<k>:<说明>[,<k2>:<说明2>] ...] \
              [--score <qid>=<档1>,<档2>[,<档3>] ...] \
              [--json] [--project DIR]

mw decide ask --state-file <path> --choice dept=billing:支付,technical:技术
```

- `--state`：文本，或以 `@` 开头表示「从该文件读取（UTF-8）」；与 `--state-file` 二选一。
- 至少给出一个 `--noul` / `--choice` / `--score`，否则 exit 2 并打印用法摘要。
- `--choice` 的 `<k>:<说明>` 里说明可省略（`billing` → 说明为 `null`，符合官方约定）；
  冒号须在**键后**，键为 `[A-Za-z0-9_-]+`，重复键 → exit 2。
- `--score` 的档位说明按低→高，2..10 个；不足 2 或超过 10 → exit 2（官方硬约束）。
- `--noul` 可额外用 `--noul-criteria <qid>=true:<说明>;false:<说明>` 补判据（可选）。
- 模型固定为 `jev-latest`（可 `--model` 覆盖，但**只能**是 decisions 类模型；未知值不拦截，交给服务端报错并原样回显）。

## 行为

1. 组装 `questions`：`{qid: {type, instructions, criteria?}}`，与 `jev接入.md` 的字段规则逐字一致。
2. 通过既有 `decision.DecisionClient.decide(state, questions)`（**legacy 无授权路径**：
   人主动提问，不需要 dp 授权）发出，传输由配置决定（当前唯一 `timi-decisions`）。
3. 人类可读输出（stdout，UTF-8）：

```
jev-latest · 2 questions · 1186 ms · in 386 / out 58 tokens
dept      [choice] billing      confidence 0.98   probs: billing 0.99, technical 0.01
urgent    [noul]   0.87         (probability of "yes")
effort    [score]  1.05         confidence 0.92   legend: 0=小, 1=中, 2=大
```

   - 键名左对齐、类型列固定宽度；`noul` 打概率并注明含义；`choice` 打选中项 + `confidence` + `probabilities`；
     `score` 打分值 + `confidence` + `legend`。
   - `--json`：输出服务端 `answers` 原样 + `{"model","usage","latency_ms"}`，机器可读，不夹杂人类文案。
4. 失败（`available=false`）：stderr 打 `[mw decide ask] <reason>: <detail>`，exit 2；
   **不打印任何伪答案**，也不重试其它模型。
5. 每次调用照常落证据行（`DecisionClient` 已有行为），`dp` 记 `dp-human-ask`。
6. 用法写进 `mw decide ask --help` 与 `packages/multi-workers/README.md` 的 decide 小节
   （含一条真实示例 + 一条「失败时原样上抛」的说明）。

## 必做用例（`packages/multi-workers/test_decide_cli.py`）

用 `_inject_backend` 的 FakeBackend，不联网：

1. `--noul urgent=是否紧急 --choice dept=billing:支付,technical:技术` → 后端收到的 `questions` 逐字符合契约
   （`noul` 无 `criteria` 键、`choice.criteria == {"billing": "支付", "technical": "技术"}`）。
2. `--choice dept=billing`（无说明）→ `criteria == {"billing": None}`。
3. `--score effort=小,中,大` → `criteria == ["小","中","大"]`；只给 1 档或 11 档 → exit 2 且零后端调用。
4. 没有任何问题类型 → exit 2，提示里含 `--noul` / `--choice` / `--score`。
5. `available=false` → exit 2，stderr 含 reason，stdout 无答案。
6. `--json` → 输出可 `json.loads`，含 `answers`/`model`/`latency_ms`。
7. 人类可读输出：断言三行分别含 `[choice]`/`[noul]`/`[score]`、`confidence`、`probs:`、`legend:`。

## 写入允许面

- `packages/multi-workers/mw.py`
- `packages/multi-workers/test_decide_cli.py`
- `packages/multi-workers/test_decide_dp_cli.py`（仅供修复 FIX-L 后失效的断言）
- `packages/multi-workers/test_decision_points.py`（同上）
- `packages/multi-workers/test_decide_run_authority.py`（同上）
- `packages/multi-workers/README.md`
- `packages/multi-workers/CHANGELOG.md`

## 写入禁止面

- `packages/multi-workers/decision.py`、`decision_backends.py`、`decision_points.py`、`decide_archive.py`
- `packages/multi-workers/test_decide_backends.py`、`test_decide.py`
- `packages/coding-agent/**`、`packages/ai/**`、`docs/**`、`.agenticdoc/**`
- 禁止 `git` 写操作、`npm run check`、全量 pytest、**真实网络调用**（不要真跑 `mw decide ask`）、`Set-Content`

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decide_cli.py
python mw.py decide ask --help
```

第二条要求 usage 里能看到 `--state`/`--noul`/`--choice`/`--score`/`--json`。

## 交付格式

`report.md`：结论 / 命令实现落点（文件:行）/ 验收输出原文 / 残留 / 未覆盖面
（**禁止**声称「已真连 jev」——本卡不联网，真连由 PM 执行）。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 接入契约：`.agenticdoc/mw-decision-substitution/jev接入.md`（`criteria` 必填规则、响应字段表、curl 示例）
- 现状锚点：`packages/multi-workers/mw.py:903-956`（`_decide_run` legacy/structured 两条路径）、
  `packages/multi-workers/mw.py` 里 `decide` 子命令的 `add_parser`/`add_argument` 区（`run`/`set`/`show`/`probe`/`dp`/`apply`）；
  `packages/multi-workers/decision.py` 的 `DecisionClient.decide`（legacy 路径：state + caller questions）
- 传输现状（FIX-L 后）：唯一 `timi-decisions`，`POST /v1/decisions`，model 默认 `jev-latest`

## 改动历史

- 2026-10-20 建卡：需要一个人可直接使用、真实调用 `timi/jev-latest` 的 `mw decide ask` 接口。
