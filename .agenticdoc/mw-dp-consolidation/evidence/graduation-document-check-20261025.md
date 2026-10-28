# 毕业考文档结构核验（2026-10-25 23:17）

性质：只检查文档结构/基准字节/phase一致性，不是AC语义验收、运行测试、QG或签收。

## 命令与检查范围

PM按项目规则把stdlib临时核验脚本写至系统Temp后执行，退出码0后删除本轮临时文件。脚本仅read_text/read_bytes本key文档，不发模型、不读配置/凭证、不修改运行状态。

- AC行正则`^\| AC-(\d{3}) \| (.+) \|$`：唯一连续001～053；原快照001～039全部仍存在。
- §1.1表精确八个已确认目标名，保持dp-QG大小写。
- §1.6表H01～H13各一行。
- 原SPEC快照SHA256与派发前SPEC一致，未改原快照。
- AC无workflow禁止的空泛词，且不存在锁定标记；state仍SPEC。

完整stdout：

```json
{
  "verification": "document-structure-only",
  "ac_count": 53,
  "original_ac_numbers_preserved": 39,
  "target_names": [
    "dp-w-type",
    "dp-pm-steer",
    "dp-w-check-task",
    "dp-QG",
    "dp-gate-approve",
    "dp-sign-key",
    "dp-auto",
    "dp-route"
  ],
  "h_scenarios": 13,
  "snapshot_sha256": "015f12af2afdea96dd5f67f25c5abd3524280b192b76542f17b7f694c0e493f1",
  "ac_locked": false,
  "phase": "SPEC",
  "runtime_tests_run": false
}
```

随后运行`python .agents/skills/agentic-task/scripts/audit_phase.py mw-dp-consolidation`：

```text
[audit] key=mw-dp-consolidation phase=SPEC
[audit] VERDICT: PASS
```

该PASS仅相位证据一致性，不等于完整SPEC/53AC已获批准或运行验收。完整用户审核、联合设计/写面、真实隔离路径验证及独立审查仍待完成。
