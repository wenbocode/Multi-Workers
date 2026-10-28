# dp1 合成决策样例字段调查（只读）

## 结论

所读文件为单个离线合成 case，顶层字段 5 个，`book.state` 下字段 6 个，`book` 自身 4 个字段。文件名中的 `dp1` 与 `book.state.decision_point` 名称一致（均为 `dp1-dispatch-type`），`case_version` 与 `schema_version` 各自独立存在。本次仅核对字段名，**不代表 DAG 整体验收完成**，也不构成对十个节点或其他 21 个决策点契约的结论。

## 证据

来源路径（唯一读取目标，只读）：`packages/multi-workers/decide_cases/dp1.json:1`

顶层字段名（5）：
- `book`
- `case_version`
- `dp`
- `note`
- `title`

`book` 下字段名（4）：
- `decision_point`
- `notes`
- `schema_version`
- `state`

`book.notes` 下字段名（1）：
- `evidence`

`book.notes.evidence` 下字段名（3）：
- `task_deliverables`
- `task_goal`
- `task_requirements`

`book.state` 下字段名（6）：
- `decision_point`
- `questions_version`
- `schema_version`
- `task_deliverables`
- `task_goal`
- `task_requirements`

字段值未复制；仅记录名称与层级。`book.notes.evidence` 的三个键与 `book.state` 中的同名业务键名称重复，但位于不同层级（一处为来源定位，一处为材料正文）。

## 残留与未验证

- 未读取任何其他 decide case 文件，因此未确认其余 21 个决策点是否使用同一组顶层/`state` 字段名。
- 未运行解析脚本或 schema 校验，字段清单来自一次纯文本读取，非机器校验结果。
- 未验证该合成样例是否被构建脚本（`packages/multi-workers/scripts/build_decide_cases.py`）按相同 schema 生成；该脚本仅作为文件中 `notes.evidence` 的路径引用出现，本次未打开。
- 未涉及运行期行为、真实派发记录或 DAG 节点间的字段兼容性。
- 按任务约束，未运行命令、未调用决策或模型工具、未读取鉴权文件或环境凭证、未修改任何文件。

## 上下文来源

- 任务卡：`.agenticdoc/mw-decision-context/workers/dc-dag-acceptance-20261023/task.md:1`
- 项目目标：`.agenticdoc/goal.md:1`
- 已批准设计：`.agenticdoc/mw-decision-context/design.md:1`（十节点 DAG 保持不变；本次不评估其验收状态）
- 只读检查目标：`packages/multi-workers/decide_cases/dp1.json:1`
