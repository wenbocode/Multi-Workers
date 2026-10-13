# T-20 conductor roadmap keys 表解析健壮化 + 降级局部化 + fail-loud（AC-012）

- Key: mw-dispatch-card-gate｜Wave: 13（与 T-18/T-19 并行，写面不相交）｜type: coding

## 上下文（实测根因：conductor 活着却不推进）
`H:\git\E2Feature` 的 conductor 进程**一直在跑**（`.mw/conductor.pid`，日志 mtime 今天），但队列 **2 天零派发**。它的 `conductor.log` **每个 tick 重复同一条错误**：

```
[conductor] gate reminders: roadmap unavailable, stage-terminal suppression disabled this tick:
  line 87 (stage 5): keys table row must have 3 columns (key | role | depends_on), got 4:
  ['feature-mine-line', '**阶段 2 找底线：L3 Feature 卡 + /mine**（...）...', 'module` 哪个 `53`...', 'feature-planning-cockpit']
```

机制：keys 表按 `|` 分列，而**某单元格正文含有未转义的 `|`**（如 `module | 53`），使 3 列的表切成 **4 列** ⇒ conductor 判定 **roadmap unavailable** ⇒ **整个调度与门禁降级（连 `stage-terminal suppression` 一起被禁用）** ⇒ 零派发；且该失败**从未告警到操作者**（只在 conductor.log 里自说自话 2 天）。

旁证：该项目 `_index.parallel` = 35 行（32 个 DONE/idle + 1 个 DONE/active），**工作状态正常，坏的是调度器**。

## 要求（逐条可验收）

1. **定位并修真源**：在 `packages/multi-workers/autopilot/**` 内定位产生 `roadmap unavailable` / `must have 3 columns` / `stage-terminal suppression disabled` 的解析与降级点（把文件+行号写进报告），按下述语义修：
   - **`|` 容错**：表头声明的列数为 N，数据行切出 M>N 个片段时**不得判该表/该行非法**；按 **首列 = key、末列 = depends_on、中间所有片段用 `|` 重新拼接为 role** 恢复该行（确定规则，须有测试固化）；
   - **坏行局部化**：无法恢复的行（如片段数 < N 且无法补全）⇒ **跳过该行并告警**，**不得**把整张表判为不可用；
   - **只有结构性不可用**（找不到 keys 表/表头缺失）才允许 `roadmap unavailable`。
2. **降级局部化**：某一行/某单元格的问题**不得**禁用与该表无关的能力（`stage-terminal suppression` 必须在该场景下**仍然生效**）。请给出"修前会禁用、修后仍生效"的对照证据。
3. **fail-loud 且可操作、不刷屏**：
   - roadmap 解析出现告警/失败时，必须产生**操作者可看到的告警**（不得只在 `conductor.log` 自述），内容含：**文件路径 + 行号 + 原因 + 怎么修**；
   - **限频**：同一 `文件+行号` 每 session 只告警一次（不得每 tick 重复）；
   - 复用既有告警出口（`conductor` 的 alarm 通道 / `mw` 可见面），不要新造不可见的日志。
4. **不得静默吞掉**：容错恢复的行必须留**警告事实**（说明该行含未转义 `|` 已按规则恢复）；跳过行必须留警告事实。
5. **测试**（新建 `packages/multi-workers/test_mwds_t20_roadmap_table.py`）：
   - 单元格含 `|`（4 列）⇒ roadmap **available** + 该行 key/role/depends_on **恢复正确** + 有警告事实；
   - 片段数 < 列数 ⇒ 该行跳过 + 警告 + 其余行仍可用；
   - 表头缺失/无表 ⇒ 仍 `unavailable`；
   - 降级局部化：上述场景下 `stage-terminal suppression` **仍生效**（对照修前行为）；
   - 告警限频：同文件同行多次触发 ⇒ 只告警一次。
6. **真实语料证据（只读）**：用**触发该问题的真实文档**跑一次解析（读 `H:\git\E2Feature` 内那份 roadmap，**只读、绝对不得写入**；若无法定位该文档，则用从 conductor.log 逐字复原的同一行作为夹具，并说明），输出：`roadmap available`、被恢复的 key 行三元组、告警文案。报告中给出原始命令与输出。

## 交付格式
- 写入允许面：`packages/multi-workers/autopilot/gates.py`、`packages/multi-workers/autopilot/conductor.py`、必要时新建 `packages/multi-workers/autopilot/roadmap*.py`、新建 `packages/multi-workers/test_mwds_t20_roadmap_table.py`。
- 写入禁止面：`autopilot/dispatch.py`（T-13 语义）、`autopilot/card_audit.py`、`packages/multi-workers/launcher.py`（T-19 可能在写）、`packages/coding-agent/**`、`.agenticdoc/**`（除本 worker 目录 taskDir）、`H:\git\E2Feature\**`（**只读**）。
- 验收命令（在 `packages/multi-workers` 下）：
  - `python -X utf8 -m pytest test_mwds_t20_roadmap_table.py -q` 全绿；
  - 回归 `python -X utf8 -m pytest test_autopilot_gate_schema_v2.py test_autopilot_config.py test_autopilot_effective_config.py -q` 全绿；
  - `python -X utf8 -m pytest packages/multi-workers -q`（在仓库根）失败数 == **2**（既有基线），不得新增。
- 报告（`report.md`）须含：结论、证据（原始命令与输出；**真源文件+行号**；修前/修后对照；真实语料的 `roadmap available` 输出；告警文案与限频证据）、改动清单、残留与未验证、上下文来源清单。
- 不做 cutover（**不要重启任何项目服务**）；不改 task 卡；不得弱化或删除既有断言；如认为卡有误，在报告中提出供 PM 裁定。
