# <key> · Codex PM 执行记录

**仅供 Codex PM 使用。** 当本 key 的 `pm-state.md` 在 `Snapshot` 中记录 `- PM mode: codex` 时，由 Codex 在 `.agenticdoc/<key>/codex_doc.md` 创建和维护本记录。MW PM 和 worker 均无需读取或填写此文档。

从 `.agenticdoc/templates/codex_doc.md` 复制到自己的 key 后填写；已有记录时直接接续。

接手时先从 `pm-state.md` 核对认领、阶段和在途工作，再读本记录恢复 Codex 会话。AgenticTask 按正常流程读取本 key 的 `spec.md`、`design.md`、`plan.md`、`tasks/` 和 `evidence/`。本页引用其中已有的编号与路径，补充 Codex 如何执行、为什么转派、下次从哪里继续。

## 开工前

- **本次执行范围**　<引用 spec 中的 AC、design 中的验证方案和 plan 中的工作项编号>
- **工作区**　<控制工作区；代码和验证所在的目标工作区>
- **关键决定**　<已经选定的做法与理由；仍需用户决定的事项>

## 执行计划与进度

按 `plan.md` 中可分别交付或验证的工作项选择执行者。需求仍在迭代、修改紧密耦合时，可由 Codex 连续执行；交付边界和验收命令明确、适合独立运行时，可交给内置 harness 或 MW worker。下表沿用计划编号。若拆分或依赖发生变化，先更新共享计划和相应任务卡，再记录执行选择。

| 工作项 | 交付物、对应 AC | 依赖 | 执行者、选择理由 | 验证方法 | 状态、证据或下一步 |
| --- | --- | --- | --- | --- | --- |
| W1 | <结果；AC-001> | <前置项> | <Codex / 内置 harness / MW worker；理由> | <命令或观察步骤> | <待开始> |

## 转派记录（发生时填写）

只转派原工作项中的剩余工作。给 worker 的上下文、写入范围和验收命令写全在同 key 的任务卡中。回执、终态和 PM 验收分别记录。转派期间本 key 的 `PM mode` 仍为 `codex`。

| 工作项 | 交接时已完成什么、剩下什么 | 执行者变更及原因 | 同 key 任务卡、回执任务 ID | Worker 产物、PM 验收结果 |
| --- | --- | --- | --- | --- |
| <W…> | <已有改动与证据；剩余交付> | <Codex → MW；原因> | <tasks/卡名.md；实际入队后填 ID> | <output.md；verify 返回的证据路径> |

## 验收与接续

| AC | 执行者自验 | PM 或其他执行者的独立复核 | 结论与证据 |
| --- | --- | --- | --- |
| AC-001 | <谁在什么目录执行了什么、结果如何> | <复核人、方法和结果；仅有自验时写“仅自验”> | <通过 / 失败 / 待验证；证据路径> |

**下次从这里继续**　<当前工作项、在途 worker、阻塞原因及下一步；结案时填写最终交付和遗留去向。>

---

<details>
<summary>填写示例：Codex 确定模板，再把初始化逻辑交给 MW（使用模板时可删除）</summary>

假设 key 为 `init-guide`，`pm-state.md` 已记录 `- PM mode: codex`，共享的 `plan.md` 已列出 W1 至 W3。AC-001 要求保留已有项目规则且连续两次初始化后只含一个 MW 章节。AC-002 要求查明新目录首次进入 pi 时，文件何时生成、当前会话何时读到说明。以下是 Codex 对三个工作项的执行安排。

| 工作项 | 交付物 | 依赖 | 执行方式与验证 |
| --- | --- | --- | --- |
| W1 | 经用户确认的模板文字、可运行的 AC-001 回归用例 | 无 | Codex PM 与用户迭代文字，在临时项目运行用例并记录实现前的结果。 |
| W2 | 初始化时安装模板、保留已有规则并支持重跑 | W1 | 起初由 Codex 调查入口。确认入口、写入范围和验收命令后，将剩余实现转派给 MW。 |
| W3 | 从空目录首次启动 pi 的验收记录 | W2 | PM 观察文件生成时机，并分别记录首次会话和重新加载后能否读到指令。 |

**W2 交接。** Codex 已定位 `cmd_init`，W1 的模板及测试已就绪。PM 把剩余实现写入 `.agenticdoc/init-guide/tasks/T-02.md`，卡内引用 W2 / AC-001，授权 worker 修改 `packages/multi-workers/mw.py`。模板和验收测试由 PM 持有。卡的 `## 验收命令` 节使用 JSON 参数数组：

```json
["python", "-m", "pytest", "-q", "packages/multi-workers/test_init_agents_guide.py"]
```

**派发与恢复。** 以下 PowerShell 命令从 MW checkout 根目录运行。示例中的目标项目就是该 checkout。`$pmClaim` 填该 key 实际认领返回的 ClaimId。当前入口需要有效的同 key 认领、`EXECUTE` 阶段和运行中的 MW 服务；现行阶段门禁仍读取 spec、design、plan 和任务卡。

```powershell
$project = (Resolve-Path .).Path
$pm = (Resolve-Path packages/multi-workers/codex_pm.py).Path
$key = 'init-guide'
$card = 'T-02'
$pmClaim = '<本次认领的 ClaimId>'
python $pm dispatch --project $project --key $key --claim-id $pmClaim --card $card
python $pm status --project $project --key $key
```

PM 将回执里的 `task` 填到 W2，状态记为“已入队”。新会话从上面的 `status` 接续。Worker 完成后，PM 读 `output.md` 和实际差异，用派发时的原命令验收：

```powershell
python $pm verify --project $project --key $key --claim-id $pmClaim --card $card -- python -m pytest -q packages/multi-workers/test_init_agents_guide.py
```

将返回的 `evidence` 路径记回 W2 / AC-001。通过后继续 W3。失败则记录原因，以 `T-02-r2` 等新卡关联 W2 和原失败证据。AC-002 保持待验证，直到完成首次会话的实际观察。

</details>
