# Evidence: plan-prefix-e2e-20260925（T-01）

## 结论：判定 (a) —— 词表缺口在仓内 e2e 全链复现（修复前红）

## 一、前置：e2e 夹具凭证漂移（根因 + 修复）

跑修复前 e2e_l2 时发现 3/7 用例失败于 `AssertionError: no completed dispatch`。现场（保留于 `%TEMP%\mw-e2e-ad5ale0s`）worker.log：

```
[launcher] spawn failed (2026-09-25T06:48:32+00:00): Timi credential is not available (no credential sources declared).
```

根因链（非环境噪声、非近期两笔 autopilot 提交所致——3a9c40d52..a0c36fcce 的 conductor diff 无 provider/credential 改动）：
1. dispatch REGISTRY（D-107 typed registry，dispatch.py:62/:85-96）给 phase-writer/reviewer 等钉死 `provider="timi"`；
2. launcher `_build_env`（launcher.py:233-249）pi+timi 直连分支要求 `config["credentials"]["timi"]` 可解析；
3. e2e 夹具 `_PROVIDERS` 只声明 `fake` 凭证（pi 代理路由预检用），未声明 `timi`；
4. → stub worker（PATH-shadowed pi）永远无法 spawn → 3 用例稳定失败。

验证实验：diag 脚本在 `_make_project` 后向 providers-e2e.json 补 `"timi": {"sources": [{"env": "MW_E2E_FAKE_KEY"}]}` → stub 一轮 dispatch 即 done（现场 `mw-e2e-rsfmddxq`）。

修复（已落）：test_autopilot_e2e.py `_PROVIDERS.credentials` 增 timi 条目（+1 条目 + 注释）。修复后 e2e_l2：`test_conductor_kill_respawn` / `test_multi_project_isolation` 转绿。

影响面：自 REGISTRY 钉死 provider=timi 起（2026-09-10 前后）无人跑过 `-m e2e_l2`，静默断链至今；任何需要 e2e_l2 回归面的 key 均被挡。修复已随本 key T-01 落盘并向用户报告（mw-crosskey-risk-escalation 已于 09-24 结案，不再追加）。

## 二、修复前红：full_chain 词表缺口复现（本 key 目标场景）

夹具修复后 `test_full_chain_single_key` 仍红——红的正是本 key 要修的 done 收口死局。diag 复刻（现场保留于 `%TEMP%\mw-e2e-45dkir4n`，150s 观察）：

**Timeline（关键事件，seq 41-53）**：
```
41  advance  verify->done exit=1 class=gate-blocked
42  config   advance verify->done failed: GATE BLOCKED: k1 cannot advance to 'done' Current phase: verify - NO MATCH: achieved.md missing pattern '系统行为变化' — achieved.md 必含「## 系统行为变化」（新增/修改功能与影响面 …
44/45/47/48/50/51  （同样 exit=1 gate-blocked ×5）
52  gate-created  gate-0002 kind=stalled
53  stalled  advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）
```

**achieved.md（1033B，≥200B 守卫锁死）**：`## Achieved` 节 = "e2e stub 达成摘要：EXECUTE 任务全部完成，验证证据齐备，目标收益落地，无遗留阻塞项。"×6 —— 无 `## 系统行为变化` 节。stall 后 mark_stalled 追加 `## 遗留问题（stalled 草稿）` 节（含失败原文，其中嵌入了「系统行为变化」字样——污染交互，与 dcr-review R4 推演一致，方向保守无害）。

**现状行为（修复前）**：gate-blocked ×5 → stalled gate（需人工批准）→ 批准后 resume credits → 事务重跑 → step-2 只看 ≥200B → 不覆盖同一坏稿 → advance 再 gate-blocked → 循环至再 stall。**无自愈路径，每次需人工关单** —— 与 FeatureMigrator 交接单的 9 key × 1 人工收口完全一致。

**失败原文的载体事实**：timeline 的 config 事件把 GATE BLOCKED 全文压平到 200 字符（`_one_line`）——再次证实 D-002 必须从 `_done_transaction` 的 advance stderr 现场提取（不可从 timeline 回读）。

## 三、基线快照

- 夹具修复后：`python -m pytest -m e2e_l2 -q` → **1 failed (test_full_chain_single_key), 6 passed**（2026-09-25 06:5x）。
- 默认套件基线（对照）：241 passed + 1 既有无关失败（test_baseline_left_end_readcap 外部锚，非本包词表相关）。

## 四、修复后预期（T-09 验收口径）

stub reviewer 分支（test_autopilot_e2e.py `task_type == "reviewer"`）现为固定非合规 `## Achieved` 模板。修复后走通 reprompt 轮需 stub 增加确定性分支：**prompt 正文含 reprompt 指示（REPROMPT_INSTRUCTION 的 "Rejected lines" 标记）→ 产含 `## 系统行为变化`/`## 遗留` 的合规稿**。此时全链：gate-blocked → marker 落盘 → reprompt 派发 → 合规轮 → 三条件真 → 覆盖 → advance exit=0 → DONE、0 stalled gate。该 stub 扩展记入 T-09 任务卡。
