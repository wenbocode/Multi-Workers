## Achieved

### 系统行为变化

修复 autopilot conductor 的 done 收口死局（mw-done-closure-repair）：L3 meets 但 done 门禁因结案文书词表驳回时，失败原文此前在 `_done_transaction` 的 gated 返回点被丢弃、≥200B 守卫冻结坏稿、5 连败 stall 且无自愈路径（E2Feature 9 key 人工关单）。现在：

- **失败原文回流**：`_done_transaction` 返回 `(verdict, err)`；gate-blocked 且失败行含 achieved.md 时，`_verify_loop` 派发 L3 reprompt（自持预算 `used < l3_limit`，不依赖被 dispatch 打断的 streak），prompt = `_l3_prompt` + 固定指示常量 + 驳回行逐字（框架源码零工程词表字面量，词表完全可移植——第二词表夹具实证）。耗尽 stall 时 verdict 保真 meets（dossier 不失真），stall reason 点名词表门禁。
- **内容寻址坏稿守卫**：新模块 `autopilot/closure.py`——marker `.mw-achieved-baddraft.json`（字节精确 sha256 + 原子写）记录被拒现场；step-2 覆盖仅在三条件全真时授权（marker 存在 ∧ sha 匹配当前稿 ∧ 记录的失败行含 achieved.md），人工修稿/追加注记/崩溃窗一律 fail-closed 不覆盖；授权覆盖同锁删 marker，终态（DONE/closed-legacy）清扫残留。
- **e2e 全链**：gate-blocked ×1 → reprompt → 合规轮 → 三条件覆盖 → advance exit=0 → DONE，零 stalled gate 零人工应答；`e2e_l2` 7/7（修复前 full_chain 红）。
- **顺带修复**：e2e 夹具 credentials.timi 漂移（09-10 起静默断链）；发现并防御 `_md_section` H2 子节转录截断坑（P-013，指示常量钉死子节层级 < `##`）。

### 遗留

- `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` 与 `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` 两个先在失败：HEAD worktree 判定为外域 key（verdict 系列 / readcap）问题，**不在本 key 范围**——建议向对应会话通报后立新 key 处理。
- FeatureMigrator 侧需 `/mw restart` 重启 serve 后，其 9 个卡死 key 才能吃到本修复（Stage 2/3 的 9×人工关单消除）。
- 本 key 变更未提交（conductor/closure/测试×3/.gitignore/CHANGELOG/_pitfalls），等待用户提交指令。
