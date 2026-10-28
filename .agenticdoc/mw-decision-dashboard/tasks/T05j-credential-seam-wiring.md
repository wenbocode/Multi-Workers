# T05j 凭证快照门/capture/client串行接线

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358实际Authorization与known集合一致。
- `packages/multi-workers/mw.py:968` client/:1566门；`decision_points.py:4239` _capture_scope/:4577 book门/:4595 client（函数定位）。
- workers/dd-timi-credential-snapshot/report.md完整“owner外接线”，decision.CredentialSnapshot/credential_snapshot/known_secret_redactor(snapshot=)/credential_redactor(snapshot=)/DecisionClient(credential_snapshot=)已交付，独立review将并行只读。T05h写者已终态，当前本卡唯一points/mw写者。

## 要求
完整读改动源分页<=400行，保存当前基线/hash，先合成timi resolver轮换A→B在门/client间的正确RED，再实现GREEN。
CLI每命令门之前取一次credential_snapshot(cfg)，门redactor与client同快照；核对所有真正book/ask/run客户端入口，不盲目修改不相关4个构造。book check离线也用同一快照。
points在per-DP预算后、任何known门/capture构建前取当次snapshot，_capture_scope、unknown-key安全path门、book validator、client同对象；caller-owned observation redactor不能被覆盖，必须验证/构造补全actual集合或明确failclosed拒绝不完整capture，不能clientB与callerA并存仍称安全。保持test explicit scope/evidence路径、全局disabled/未配置/凭证缺失/预算零发送。
Timi当次实际Authorization=capture集合=book门集合测试真实loopback重试，同次固定A、下次命令B，禁止原值落日志/输出/证据。tmp auth/HOME/USERPROFILE/delenv后缀全集、读前spy，禁真实凭证。
API失配/异常failclosed且业务capture失败语义保留；冷启动 CLI/points+book 两链证明，不用手造event代替生产接线。全部行为TDD，修后mutant不能当先RED。
禁止本卡改placeholder/empty/required gate/snapshot_ref/typed/schema/limits/registry/producer，missing-null快照与p0数组界另债。若T05iAPI缺陷须报PM给transportowner不越面。

## 写入允许面
- `packages/multi-workers/mw.py`（快照接线）
- `packages/multi-workers/decision_points.py`（快照接线）
- `packages/multi-workers/test_decision_credential_seam.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-credential-seam-wiring/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05j-*`

## 写入禁止面
- decision/backends/book/其他test/registry/生成物/旧报告/任务相位/真实凭证生产/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_credential_seam.py test_decision_timi_credential_snapshot.py test_decision_book_known_secrets.py test_decision_cli_config_snapshot.py test_decide_run_authority.py test_decision_observation.py -q` 全日志exit/依赖hash，所有运行外层tmpHOME隔离。
root全仓只读biome --error-on-warnings/check子步，完整check未整跑明确不等价。禁全包pytest/build/commit/真实窗口/服务/模型外网。

## 改动历史
- PM吸收T05i transport交付，门仍在client前未闭合；T05h终态允许串行points/mw接线，transport独立review并行只读。
- dd-review-timi-snapshot PASS完整吸收：P2-1 snapshot必须由门/client同一cfg产生，不能空snapshot遮蔽另一cfg有效key；P2-2每命令独立scope，禁止跨client复用陈旧自注入redactor。新增专项验证此二边界；若自定义共享scope须补全实际集合或明确failclosed，文档披露不能豁免可能泄漏。
- P2-3原RED日志实际打印合成串，不是首行声称的掩码；不是读取真实凭证。新证据副本应统一掩码，旧日志不改，报告标明更正；不能混淆无secret measure与pytest失败输出。

## 交付格式
report≤110行，实际RED/GREEN、gate/capture/Authorization同一指标、caller-owned scope安全策略/API/剩余；不自报reviewPASS/T06放行。
