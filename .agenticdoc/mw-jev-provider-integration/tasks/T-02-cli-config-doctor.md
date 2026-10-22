# T-02 — CLI 接线 / 配置面 / doctor 行

- key: mw-jev-provider-integration · type: coding · W2 · timeout: 50

## 上下文

goal.md 第 2 条「框架需要决策的时候能正确调用并有效反馈」（第 1 条 jev 跑通已由 W1 的 B2 真实调用落地）。本任务把决策服务接到 mw CLI。

W1 已交付 `decision.py`（客户端核心）与 `decision_backends.py`（B1/B2/B3 + probe_matrix）。本任务把决策服务**接到 mw CLI**，并加两处最小运维面：`.mw/decide.json` 配置与 doctor 行。

必读锚点：
- `.agenticdoc/mw-jev-provider-integration/design.md`：D-001（CLI 锚点与形态）、D-003（契约/退出码）、D-005 第 3 条（doctor 行格式）、D-007（配置字段与 fail-soft/原子写）。
- `.agenticdoc/mw-jev-provider-integration/plan.md`：§1 冻结接口、§2 W2 验收。
- `packages/multi-workers/decision.py` 与 `decision_backends.py`（W1 产物，**只读**，按它们实际的公开名字调用；若签名与 plan §1 有出入，以文件为准并在 report 记录差异）。
- `evidence/research/design-mw-python-patterns-20261016.md`：Q1（argparse 骨架 `mw.py:6682-6684`、嵌套 action `:6711-6731`、dispatch 字典 `:7144-7166`）、Q3（doctor 行锚点 `mw_common.py:1558`/`:4234-4287`/`:4473-4496`、zero-perturbation）、Q2（fail-soft 读 `mw_common.py:224-252`、P-003 原子写 `console_run.py:191-195`）。

## 要求

1. **CLI**（`packages/multi-workers/mw.py`，最小改动）：
   - 新增 `cmd_decide(args) -> int`：`mw decide <run|probe|show|set> --project <dir>`。
     - `run`：读 JSON 请求（`--request-file` 或 stdin；**禁止**把 `state` 放命令行参数），调 `DecisionClient`，成功/不可用均 exit 0（不可用 = exit 0 + `available=false`），参数非法 exit 2。
     - `probe`：跑 `probe_matrix`，打印 ≤20 行人类摘要；`--json` 出机读矩阵。
     - `show`：打印解析后的配置与最近一条证据（`.agenticdoc/_autopilot/triage-decisions.jsonl` 末行），未配置时明示"disabled"。
     - `set`：写 `.mw/decide.json`（**P-003 原子写**：temp + `os.replace`，`encoding="utf-8"`、`newline="\n"`）；未识别的键拒绝并 exit 2。
   - `--json` 机器出口（照 `cmd_doctor` `mw.py:653-662` 风格）。
   - 注册：`_parse_args()` 加 `sub.add_parser("decide", ...)`（嵌套 action，形态照 `target`/`model`）+ 底部 dispatch 字典加一行。
   - **禁止触碰** `_goal_gate_install` 及其注册/安装点（属并行 key `mw-goal-gate-write-intent`）、`cmd_model`/`_model_write` 段（属 `mw-model-fallback-cli`）。
2. **配置**：`.mw/decide.json`，字段 = design D-007（含 `enabled/transport/model/timeout_s/max_retries/max_questions/max_state_bytes/max_tokens/points.{dp1}.enabled/points.dp1.alert_on_disagreement/triage_notify_on_unavailable`）。缺文件 = disabled 且**零行为变化**；坏文件 → fail-soft（返回错误串给 doctor 展示，不抛）。
3. **doctor 行**（`packages/multi-workers/mw_common.py`）：
   - 新 `_doctor_decide(project_dir) -> dict`（照 `_doctor_dispatch` `:1558`），挂进 `doctor_report`，在 `format_doctor_text` 里条件渲染，行文本：`triage: enabled <transport> last_suggestion=<seq|none> last_unavailable=<reason|none>` 或 `triage: disabled`；坏配置 → `triage: ERROR — <msg>`。
   - **zero-perturbation 铁律**：未配置项目下 doctor 输出必须与改动前**逐字节一致**（既有测试不得变红）；信息行**不进** `_doctor_issues`（不翻转 healthy）。
4. **测试** `packages/multi-workers/test_decide_cli.py`（pytest，hermetic）：
   - `cmd_decide` 四个 action 的直接调用（`argparse.Namespace`）与至少一条 `subprocess.run([sys.executable, MW_PY, "decide", ...], encoding="utf-8")` 冒烟；
   - `set` 原子写（写后无 `.tmp` 残留、`\n` 行尾）、坏键 exit 2；
   - doctor：未配置 → 无 `triage:` 行且输出与基线逐字节一致；配置后 → 出现 `triage:` 行且 `--json` 内有对应 section；
   - `run` 用 FakeBackend 注入（不联网），覆盖 available=true/false 两条路径的退出码语义。
5. **不动** `decision.py` / `decision_backends.py` / `test_decide.py` / `test_decide_backends.py` 的实现逻辑，**唯一例外**（窄授权）：证据行需补一个 `ts` 字段——`.agenticdoc/_autopilot/triage-decisions.jsonl` 每行加 `ts`（UTC `isoformat(timespec="seconds")`，照 `mw_common.iso_now` 风格），并同步 `test_decide.py` 的断言；`mw decide show` 末行展示要带 `ts`。除此之外若发现需要 W1 文件暴露新函数，在 report 里提出，**不要**改。

## 写入允许面

- `packages/multi-workers/mw.py`
- `packages/multi-workers/mw_common.py`
- `packages/multi-workers/test_decide_cli.py`
- `packages/multi-workers/decision.py`（**仅**证据行加 `ts` 字段）
- `packages/multi-workers/test_decide.py`（**仅**同步 `ts` 断言）

## 写入禁止面

- `packages/multi-workers/decision_backends.py`、`packages/multi-workers/test_decide_backends.py`
- 其它一切文档/配置；禁止 `git add`/`commit`；禁止写入其它 key 目录

## 验收命令

```bash
cd packages/multi-workers && python -m pytest -q test_decide_cli.py test_decide.py test_decide_backends.py
cd packages/multi-workers && python -m pytest -q test_doctor.py   # 若无此文件，改跑 doctor 相关既有测试并记录
```

## 改动历史

- 新建任务；`mw.py` 与 `mw_common.py` 本任务独占改动（同波无其它束写这两个文件）。

## 交付格式

- 三个文件 + `report.md`（结论 / 证据 / 残留与未验证 / 上下文来源）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；**前 10 次写调用内落出 `cmd_decide` 初版**。
