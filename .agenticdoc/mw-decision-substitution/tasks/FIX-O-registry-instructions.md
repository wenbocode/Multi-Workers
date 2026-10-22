# FIX-O：给已接线的 dp 补真实 instructions / labels / criteria（jev 判得准的前提）

- type: coding
- owner key: mw-decision-substitution

## 上下文

PM 2026-10-21 用真 jev 实测：`mw decide run --dp dp3-worker-clarify` 已经能拿到答案（`candidate` 置信
0.81–0.84、`answerable` 0.55–0.57），但 `answer_kind` 置信只有 **0.13–0.16**，低于阈值 0.7 → 上抛人。
根因不是模型，是**注册表里没有问题文本**：后端只能发占位 instruction
`"answer_kind: answer this question about the supplied state"`，模型在猜。

后端（FIX-L）已支持四种输入：`instructions`（缺失才用占位）、`choice` 的 `labels`（`{选项: 说明}`）、
动态题由 state 渲染候选、`noul` 的 `criteria {"true","false"}`、`score` 的 `criteria` 有序数组。
本卡只补注册表数据与校验。

## 要求

给已接线的 4 个 dp（dp1 / dp2 / dp3 / dp8）的每个 question 补 `instructions`；静态 `choice` 补
`labels`；`noul` 补 `criteria.true/false`。未接线的 dp 不动。文案照抄下面（措辞可微调，判据含义不得改）。

- dp1 `triage_type`：instructions「这个任务应该派给哪一类 worker？」；
  labels `coding`=需要写代码或改代码或跑命令，`research`=只做检索取证不改代码，`review`=审计别人已完成的产出。
- dp1 `triage_risk`：instructions「这个任务做错了的代价有多大？」；
  labels `low`=可随时撤销且不影响他人，`mid`=影响同一 key 的其它任务或需要返工，
  `high`=跨会话或跨 key 冲突或不可逆（发布、删除、凭据变更）。
- dp2 `checkpoint_action`：instructions「以当前进度，这一步该继续、拆小、直接执行还是上抛人？」；
  labels `narrow`=收窄到剩余预算内能完成的一小块，`split`=拆成多个任务重派，
  `direct-exec`=PM 自己直接做完，`escalate`=风险高到必须问人。
- dp3 `answer_kind`：instructions「这条澄清属于哪一类：能凭已给材料查到答案、需要人的意图判断、还是已有表态可复用？」；
  labels `fact`=答案存在于给出的状态或候选条目里，`intent`=取决于人想要什么（材料里没有），
  `reuse`=之前的表态或产物已经回答了它。
- dp3 `answerable`：instructions「仅凭 state 里给出的内容与候选条目，能否确定地回答上面这条澄清？」；
  criteria `true`=材料里直接有答案，`false`=材料不足或需要人表态。
- dp3 `candidate`：instructions「state.local_candidates 里哪一条最可能承载答案？」；动态题，**不加** labels。
- dp8 `scope_decision`：instructions「这次变更应该保持、收窄还是扩大范围？」；
  labels `keep`=按原范围，`narrow`=缩小到原范围内的一子集，`expand`=扩大到原范围之外。
- dp8 `scope_reason`：instructions「为什么需要或不需要改范围？」；
  labels `outside-write-face`=目标文件在授权写面之外，`cross-key-conflict`=会与他人写面重叠，
  `scope-creep`=需求本身扩大了，`unclear-boundary`=边界不清需要先界定。

校验（`_validate_question`）新增：`instructions` 必须非空字符串；`labels` 仅允许在非动态 `choice` 上，
必须是 `dict[str,str]` 且键集合**恰好等于**该题 `choices`；`noul` 的 `criteria` 必须是恰好含
`true`/`false` 两键的字符串映射。负例必须抛 `ValueError`。

`questions_version` 必须**保持不变**（hash 只覆盖 `id`/`type`/`choices`/`dynamic_choices`）。dp3 仍然是
`q-fcbd3847`；若现有实现把新键算进 hash，就改成只 hash 上述四键，并在报告里给出前后一致的证据。

## 必做用例（`packages/multi-workers/test_decision_points.py`）

1. 四个已接线 dp 的每题都有非空 `instructions`；静态 `choice` 的 `labels` 键集合 == `choices`。
2. dp3 的 `candidate` 无 `labels`；`answerable.criteria` 恰为 `{"true","false"}`。
3. 四条负例：`instructions=""`；`labels` 键集合与 `choices` 不等；动态题带 `labels`；
   `noul.criteria` 少一键 —— 均抛 `ValueError`。
4. `questions_version` 不变：dp3 == `q-fcbd3847`，其余 dp 用改前值写死断言。
5. 在 `test_decide_backends.py` 新增一条 payload 断言：发往 `/v1/decisions` 的
   `questions["answer_kind"]["instructions"]` 等于注册表那句，`answerable` 带 `{"true","false"}` 的 `criteria`。

## 写入允许面

- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/test_decision_points.py`
- `packages/multi-workers/test_decide_backends.py`（仅新增第 5 条断言，不改既有用例）

## 写入禁止面

- `packages/multi-workers/decision.py`、`decision_backends.py`、`mw.py`、`decide_archive.py`
- `packages/multi-workers/test_decide.py`、`test_decide_cli.py`、`test_decide_dp_cli.py`、`test_decide_run_authority.py`
- `packages/coding-agent/**`、`packages/ai/**`、`docs/**`、`.agenticdoc/**`、`CHANGELOG.md`、`README.md`
- 禁止 `git` 写操作、`npm run check`、全量 pytest、真实网络调用、`Set-Content`

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decision_points.py
python -m pytest -q test_decide_backends.py
python -c "from decision_points import questions_map, get_decision_point as g; print(g('dp3-worker-clarify').questions_version); print(questions_map('dp3-worker-clarify'))"
```

## 交付格式

`report.md`：结论 / 文案落点（文件:行）/ 三条验收输出原文 / 残留 / 未覆盖面。
禁止声称「jev 已答得准」——本卡不联网，真连由 PM 复测置信度。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 实测证据（PM 2026-10-21，真 jev）：`answer_kind` 0.13–0.16、`candidate` 0.81–0.84、`answerable` 0.55–0.57
- 现状锚点：`packages/multi-workers/decision_points.py:185-230`（`_validate_question`）、
  `:366-370`（dp1）、`:377-380`（dp2）、`:389-391`（dp3）、`:441-450`（dp8）、`:210-218`（`_questions_version`）
- 后端消费点：`packages/multi-workers/decision_backends.py:398`、`:415`、`:435`

## 改动历史

- 2026-10-21 建卡：真 jev 已能回答，但注册表缺问题文本导致置信度极低（0.13~0.16）→ 上抛人。
