# PM 接续状态与历史归档

完整 SDD key 的 `pm-state.md` 是当前接续页。每轮结束前原位更新状态，覆盖已被取代的条目。继续执行前，从 `_index.parallel` 核对认领，从任务卡、Worker 状态和证据核对仍在途的工作。框架管理阶段与认领字段。

| 小节 | 保留内容 |
| --- | --- |
| `Notes` | 当前目标、阻塞、接手人和具体下一步。旧会话接续摘要已被更新时，移入历史。 |
| `Task Status` | 当前在途任务和待验收工作，记录 Worker、唯一写入者、截止或等待条件；已结束的任务以任务卡为准。 |
| `Decisions` | 仍影响执行的决定、理由和出处。阶段性范围变更同步到 spec、design 和 plan。 |
| `Evidence Ledger` | 当前结论和相应 AC、证据路径，区分 PM 自验、独立复核和未验证项。框架所需的 `- PASS` 门禁条目保留在本页。 |

Write-Before-Act 和轮末检查继续执行。当前意图和检查结论更新在接续页；逐轮问答、详细研究、命令日志、已失效的假设及历史快照落到 `evidence/`、任务卡或归档中。正文建议控制在 8 KiB 以内，超过 16 KiB 时压缩。接续时按具体引用查证，避免常规读取整个归档。`codex-lite` 的接续信息使用 `codex_doc.md`。

## 压缩已有状态

在当前持有完整 SDD key 的 pi PM 窗口，空闲时执行 `/mw pm-state compact`。当前 PM 模型会生成接续摘要并自动提交。命令确认当前窗口仍持有认领且原文未变后完成归档和替换，保留认领。若生成期间状态变化，空闲后重跑。

pi 安装可通过全局扩展目录中的 `.mw-pm-state-path` 单独指定 `pm_state.py` 的绝对路径。其它 `/mw` 命令继续使用原来的 MW CLI。

### 手动预演和应用

准备 UTF-8 Markdown 摘要，依次写四个 `##` 小节 `Notes`、`Task Status`、`Decisions`、`Evidence Ledger`。每节至少一条有效信息，无在途工作时写明「无」。依据当前 plan、Worker 和证据核对摘要，保留未验证项及有效约束。摘要最多 8 KiB，压缩后的文件最多 16 KiB。

在 pi PM 窗口，`/mw pm-state compact --key gaze-integration-spike --summary "E:/path/to/reviewed-handoff.md"` 以当前控制工作区预演。使用 `--help` 可查看参数，应用时追加 `--apply` 和预演输出的 `source_sha256`。

在 MW checkout 执行预演，可预演正在认领的 key。输出包含压缩前后字节数、认领状态和 `source_sha256`。

```powershell
$mw = (Resolve-Path packages/multi-workers/mw.py).Path
$project = 'E:/MWWS/Gaze'
$key = 'gaze-integration-spike'
$summary = 'E:/path/to/reviewed-handoff.md'
python $mw pm-state compact --project $project --key $key --summary $summary
```

应用前由 PM 暂停该 key 的写入，包括可能更新该页的自动化，并通过框架释放认领。释放后重新预演，核对接续内容及 `can_apply`，再使用这次输出的 SHA。

```powershell
$sourceSha = '把这里替换为本次预演的 source_sha256'
python $mw pm-state compact --project $project --key $key --summary $summary --apply $sourceSha
```

命令先在 key 的 `pm-state-history/` 保存可逐字节解压恢复的原稿，再原子替换接续页。归档名是原稿的 SHA-256，接续页有上一版链接，每份归档保留其原有链接。并行写入或源文件变化使应用失败。应用后可按原流程认领；需要复查历史时，把 gzip 解压到单独的路径，根据内容和当前事实核对。
