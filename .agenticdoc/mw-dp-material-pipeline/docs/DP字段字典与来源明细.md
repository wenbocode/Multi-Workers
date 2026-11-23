# DP字段字典与来源明细

配套[详细设计](DP材料准备与决策链路详细设计.md)。下列从八份当前冻结请求穷举实际可见字段；send=true表示真实body包含该字段，不表示生产来源提取器已实现。来源规则由本轮作者按详细设计编制并自验，不是通用语义证明。

本地owner/matter/run、准备过程、权限与原账本、比较报告、执行命令和作者预期不在该请求表内，主设计第4节另规定其本地合同。空对象/数组也作为实际字段记录，不能误报为未发送。

## dp-w-type

冻结样例：[reference.json](cases/dp-w-type/reference.json)；来源正文见同目录sources/，原始调用见[captures/dp-w-type/result.json](captures/dp-w-type/result.json)。

| material属性 | 来源与组装规则 |
| --- | --- |
| `work_items` | 当前可执行任务/对应验收要求；提取实际操作、对象和预期变化 |
| `output_expectations` | 当前任务卡交付和对应AC；区分代码、取证、审查或像素解释 |
| `image_requirement` | 当前任务真实像素依赖与host能力；不能因提到截图推断需要vision |
| `constraints` | 原任务范围与已确认约束；只投影影响类型比较的内容 |

| 实际模型字段（JSON Pointer） | 类型 | 发送 | 来源/规则 |
| --- | --- | --- | --- |
| `/model` | string | 是 | 既有决策后端配置；本次真实捕获为jev-latest |
| `/state/scenario` | string | 是 | 当前场景身份；本例明确合成，不是生产观察/授权 |
| `/state/desc` | string | 是 | 原主体准备/吸收的逐句来源摘要；目标、偏差、事件、证据和未知 |
| `/state/material/work_items/0/action` | string | 是 | 当前可执行任务/对应验收要求；提取实际操作、对象和预期变化 |
| `/state/material/work_items/0/object_kind` | string | 是 | 当前可执行任务/对应验收要求；提取实际操作、对象和预期变化 |
| `/state/material/work_items/0/expected_change` | string | 是 | 当前可执行任务/对应验收要求；提取实际操作、对象和预期变化 |
| `/state/material/output_expectations/0/kind` | string | 是 | 当前任务卡交付和对应AC；区分代码、取证、审查或像素解释 |
| `/state/material/output_expectations/0/content` | string | 是 | 当前任务卡交付和对应AC；区分代码、取证、审查或像素解释 |
| `/state/material/image_requirement/needed` | boolean | 是 | 当前任务真实像素依赖与host能力；不能因提到截图推断需要vision |
| `/state/material/constraints/0/rule` | string | 是 | 原任务范围与已确认约束；只投影影响类型比较的内容 |
| `/state/material/constraints/0/status` | string | 是 | 原任务范围与已确认约束；只投影影响类型比较的内容 |
| `/state/references` | object | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/terminology/CSV/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/CSV/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/Worker/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/Worker/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/host/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/host/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/review/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/review/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/enum_meanings/coding` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/known` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/research` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/review` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/vision` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/questions/decision_selection/type` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/instructions` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/criteria/codingA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/researchA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/reviewA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/visionA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |

## dp-pm-steer

冻结样例：[reference.json](cases/dp-pm-steer/reference.json)；来源正文见同目录sources/，原始调用见[captures/dp-pm-steer/result.json](captures/dp-pm-steer/result.json)。

| material属性 | 来源与组装规则 |
| --- | --- |
| `decision_problem` | 当前目标偏差与需要PM决定的组织问题 |
| `remaining_work` | 原任务/验收承诺减实际交付；逐项结果、依赖和注明单位的估计 |
| `dependencies` | 当前接口/写面/任务依赖证据；无依赖也须已核 |
| `resources` | 原事项账本及真实可用执行者观测；单位和范围不混用 |
| `constraints` | 原目标、独立复核、范围等已确认限制 |

| 实际模型字段（JSON Pointer） | 类型 | 发送 | 来源/规则 |
| --- | --- | --- | --- |
| `/model` | string | 是 | 既有决策后端配置；本次真实捕获为jev-latest |
| `/state/scenario` | string | 是 | 当前场景身份；本例明确合成，不是生产观察/授权 |
| `/state/desc` | string | 是 | 原主体准备/吸收的逐句来源摘要；目标、偏差、事件、证据和未知 |
| `/state/material/decision_problem` | string | 是 | 当前目标偏差与需要PM决定的组织问题 |
| `/state/material/remaining_work/0/id` | string | 是 | 原任务/验收承诺减实际交付；逐项结果、依赖和注明单位的估计 |
| `/state/material/remaining_work/0/outcome` | string | 是 | 原任务/验收承诺减实际交付；逐项结果、依赖和注明单位的估计 |
| `/state/material/remaining_work/0/depends_on` | array | 是 | 原任务/验收承诺减实际交付；逐项结果、依赖和注明单位的估计 |
| `/state/material/remaining_work/0/estimate` | string | 是 | 原任务/验收承诺减实际交付；逐项结果、依赖和注明单位的估计 |
| `/state/material/remaining_work/1/id` | string | 是 | 原任务/验收承诺减实际交付；逐项结果、依赖和注明单位的估计 |
| `/state/material/remaining_work/1/outcome` | string | 是 | 原任务/验收承诺减实际交付；逐项结果、依赖和注明单位的估计 |
| `/state/material/remaining_work/1/depends_on` | array | 是 | 原任务/验收承诺减实际交付；逐项结果、依赖和注明单位的估计 |
| `/state/material/remaining_work/1/estimate` | string | 是 | 原任务/验收承诺减实际交付；逐项结果、依赖和注明单位的估计 |
| `/state/material/dependencies/0/text` | string | 是 | 当前接口/写面/任务依赖证据；无依赖也须已核 |
| `/state/material/dependencies/0/kind` | string | 是 | 当前接口/写面/任务依赖证据；无依赖也须已核 |
| `/state/material/resources/0/remaining` | number | 是 | 原事项账本及真实可用执行者观测；单位和范围不混用 |
| `/state/material/resources/0/unit` | string | 是 | 原事项账本及真实可用执行者观测；单位和范围不混用 |
| `/state/material/resources/0/scope` | string | 是 | 原事项账本及真实可用执行者观测；单位和范围不混用 |
| `/state/material/resources/1/remaining` | number | 是 | 原事项账本及真实可用执行者观测；单位和范围不混用 |
| `/state/material/resources/1/unit` | string | 是 | 原事项账本及真实可用执行者观测；单位和范围不混用 |
| `/state/material/resources/1/scope` | string | 是 | 原事项账本及真实可用执行者观测；单位和范围不混用 |
| `/state/material/constraints/0/rule` | string | 是 | 原目标、独立复核、范围等已确认限制 |
| `/state/material/constraints/0/status` | string | 是 | 原目标、独立复核、范围等已确认限制 |
| `/state/references/W1/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/W1/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/W1/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/W2/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/W2/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/W2/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/terminology/ID/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/PM/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/PM/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/未测/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/未测/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/直执/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/直执/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/enum_meanings/available_executors` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/direct-exec` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/escalate` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/known` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/narrow` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/observed` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/split` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/worker_minutes` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/questions/decision_selection/type` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/instructions` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/criteria/narrowA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/splitA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/directA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/escalateA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |

## dp-w-check-task

冻结样例：[reference.json](cases/dp-w-check-task/reference.json)；来源正文见同目录sources/，原始调用见[captures/dp-w-check-task/result.json](captures/dp-w-check-task/result.json)。

| material属性 | 来源与组装规则 |
| --- | --- |
| `completed` | 当前实际Worker本run动作和观测；不外推未测范围 |
| `remaining_work` | 当前任务AC/交付与实际差额 |
| `reachability` | 实际Worker的工具/权限/说明来源和阻塞观测，prepare不能冒充 |
| `resources` | 当前Worker原run时间/次数/字节账本 |
| `probe` | 当前具体未知、原授权取证来源、预计得到的信息和硬停止边界 |

| 实际模型字段（JSON Pointer） | 类型 | 发送 | 来源/规则 |
| --- | --- | --- | --- |
| `/model` | string | 是 | 既有决策后端配置；本次真实捕获为jev-latest |
| `/state/scenario` | string | 是 | 当前场景身份；本例明确合成，不是生产观察/授权 |
| `/state/desc` | string | 是 | 原主体准备/吸收的逐句来源摘要；目标、偏差、事件、证据和未知 |
| `/state/material/completed/0/text` | string | 是 | 当前实际Worker本run动作和观测；不外推未测范围 |
| `/state/material/completed/0/kind` | string | 是 | 当前实际Worker本run动作和观测；不外推未测范围 |
| `/state/material/remaining_work/0/id` | string | 是 | 当前任务AC/交付与实际差额 |
| `/state/material/remaining_work/0/outcome` | string | 是 | 当前任务AC/交付与实际差额 |
| `/state/material/reachability/0/text` | string | 是 | 实际Worker的工具/权限/说明来源和阻塞观测，prepare不能冒充 |
| `/state/material/reachability/0/kind` | string | 是 | 实际Worker的工具/权限/说明来源和阻塞观测，prepare不能冒充 |
| `/state/material/resources/0/remaining` | number | 是 | 当前Worker原run时间/次数/字节账本 |
| `/state/material/resources/0/unit` | string | 是 | 当前Worker原run时间/次数/字节账本 |
| `/state/material/resources/0/scope` | string | 是 | 当前Worker原run时间/次数/字节账本 |
| `/state/material/resources/1/remaining` | number | 是 | 当前Worker原run时间/次数/字节账本 |
| `/state/material/resources/1/unit` | string | 是 | 当前Worker原run时间/次数/字节账本 |
| `/state/material/resources/1/scope` | string | 是 | 当前Worker原run时间/次数/字节账本 |
| `/state/material/resources/2/remaining` | number | 是 | 当前Worker原run时间/次数/字节账本 |
| `/state/material/resources/2/unit` | string | 是 | 当前Worker原run时间/次数/字节账本 |
| `/state/material/resources/2/scope` | string | 是 | 当前Worker原run时间/次数/字节账本 |
| `/state/material/probe/unknown` | string | 是 | 当前具体未知、原授权取证来源、预计得到的信息和硬停止边界 |
| `/state/material/probe/resource` | string | 是 | 当前具体未知、原授权取证来源、预计得到的信息和硬停止边界 |
| `/state/material/probe/expected` | string | 是 | 当前具体未知、原授权取证来源、预计得到的信息和硬停止边界 |
| `/state/material/probe/limit` | string | 是 | 当前具体未知、原授权取证来源、预计得到的信息和硬停止边界 |
| `/state/material/probe/stop_when` | string | 是 | 当前具体未知、原授权取证来源、预计得到的信息和硬停止边界 |
| `/state/references/W1/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/W1/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/W1/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/terminology/ASCII/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ASCII/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/Worker/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/Worker/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/host/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/host/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/run/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/run/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/补证/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/补证/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/enum_meanings/bytes` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/continue` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/investigate` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/minutes` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/observed` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/reads` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/terminate` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/questions/decision_selection/type` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/instructions` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/criteria/continueA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/terminateA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/investigateA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |

## dp-QG

冻结样例：[reference.json](cases/dp-QG/reference.json)；来源正文见同目录sources/，原始调用见[captures/dp-QG/result.json](captures/dp-QG/result.json)。

| material属性 | 来源与组装规则 |
| --- | --- |
| `review_scope` | 当前受审对象与已确认完整适用AC集合；真实版本绑定留本地 |
| `review_summary` | 同对象/版本独立review原件的核对状态、覆盖和独立性语义 |
| `ac_completion` | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `findings` | 当前独立review发现，关联具体AC与实际影响，保留未关闭状态 |

| 实际模型字段（JSON Pointer） | 类型 | 发送 | 来源/规则 |
| --- | --- | --- | --- |
| `/model` | string | 是 | 既有决策后端配置；本次真实捕获为jev-latest |
| `/state/scenario` | string | 是 | 当前场景身份；本例明确合成，不是生产观察/授权 |
| `/state/desc` | string | 是 | 原主体准备/吸收的逐句来源摘要；目标、偏差、事件、证据和未知 |
| `/state/material/review_scope/subject` | string | 是 | 当前受审对象与已确认完整适用AC集合；真实版本绑定留本地 |
| `/state/material/review_scope/ac_ids/0` | string | 是 | 当前受审对象与已确认完整适用AC集合；真实版本绑定留本地 |
| `/state/material/review_scope/ac_ids/1` | string | 是 | 当前受审对象与已确认完整适用AC集合；真实版本绑定留本地 |
| `/state/material/review_summary/status` | string | 是 | 同对象/版本独立review原件的核对状态、覆盖和独立性语义 |
| `/state/material/review_summary/coverage` | string | 是 | 同对象/版本独立review原件的核对状态、覆盖和独立性语义 |
| `/state/material/review_summary/independence` | string | 是 | 同对象/版本独立review原件的核对状态、覆盖和独立性语义 |
| `/state/material/ac_completion/0/ac_id` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/0/requirement` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/0/status` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/0/vc_results/0/vc_id` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/0/vc_results/0/verification` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/0/vc_results/0/status` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/0/vc_results/0/observation` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/0/vc_results/0/evidence` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/0/deviation` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/0/finding_ids/0` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/ac_id` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/requirement` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/status` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/vc_results/0/vc_id` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/vc_results/0/verification` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/vc_results/0/status` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/vc_results/0/observation` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/vc_results/0/evidence` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/deviation` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/ac_completion/1/finding_ids/0` | string | 是 | 逐AC原正文、关联VC合同、实际断言/观测及独立review；保留失败/未测 |
| `/state/material/findings/0/id` | string | 是 | 当前独立review发现，关联具体AC与实际影响，保留未关闭状态 |
| `/state/material/findings/0/ac_id` | string | 是 | 当前独立review发现，关联具体AC与实际影响，保留未关闭状态 |
| `/state/material/findings/0/status` | string | 是 | 当前独立review发现，关联具体AC与实际影响，保留未关闭状态 |
| `/state/material/findings/0/observation` | string | 是 | 当前独立review发现，关联具体AC与实际影响，保留未关闭状态 |
| `/state/material/findings/1/id` | string | 是 | 当前独立review发现，关联具体AC与实际影响，保留未关闭状态 |
| `/state/material/findings/1/ac_id` | string | 是 | 当前独立review发现，关联具体AC与实际影响，保留未关闭状态 |
| `/state/material/findings/1/status` | string | 是 | 当前独立review发现，关联具体AC与实际影响，保留未关闭状态 |
| `/state/material/findings/1/observation` | string | 是 | 当前独立review发现，关联具体AC与实际影响，保留未关闭状态 |
| `/state/references/AC-001/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-001/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-001/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-001/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-001/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-001/ac_ids/0` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-001/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-001/expected_result` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-002/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-002/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-002/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-002/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-002/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-002/ac_ids/0` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-002/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/VC-002/expected_result` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/F1/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/F1/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/F1/ac_ids/0` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/F1/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/F2/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/F2/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/F2/ac_ids/0` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/F2/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/terminology/AC/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/AC/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/QG/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/QG/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/VC/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/VC/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/review/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/review/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/独审/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/独审/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/补证/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/补证/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/enum_meanings/completed` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/fail` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/fix` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/not-met` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/not-run` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/open` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/pass` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/unverified` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/questions/decision_selection/type` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/instructions` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/criteria/passA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/fixA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/fixB` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |

**规范差额：实际criteria只有passA/fixA/fixB，缺少reopen。详细设计要求修复新输入，禁止改旧捕获。**

## dp-gate-approve

冻结样例：[reference.json](cases/dp-gate-approve/reference.json)；来源正文见同目录sources/，原始调用见[captures/dp-gate-approve/result.json](captures/dp-gate-approve/result.json)。

| material属性 | 来源与组装规则 |
| --- | --- |
| `proposed_action` | 原主体当前限定动作与预期业务结果，具体命令留本地 |
| `conditions` | 已有准入条件原文，不能由prepare临时改条件 |
| `condition_results` | 该动作逐条件的当前状态与实际观测 |
| `effects` | 当前方案影响、风险与原资源观测；估计不当硬保证 |
| `authority_constraints` | 原host已核授权/范围的必要语义；接回仍核真实权限 |

| 实际模型字段（JSON Pointer） | 类型 | 发送 | 来源/规则 |
| --- | --- | --- | --- |
| `/model` | string | 是 | 既有决策后端配置；本次真实捕获为jev-latest |
| `/state/scenario` | string | 是 | 当前场景身份；本例明确合成，不是生产观察/授权 |
| `/state/desc` | string | 是 | 原主体准备/吸收的逐句来源摘要；目标、偏差、事件、证据和未知 |
| `/state/material/proposed_action/0/action` | string | 是 | 原主体当前限定动作与预期业务结果，具体命令留本地 |
| `/state/material/proposed_action/0/expected_result` | string | 是 | 原主体当前限定动作与预期业务结果，具体命令留本地 |
| `/state/material/conditions/0/id` | string | 是 | 已有准入条件原文，不能由prepare临时改条件 |
| `/state/material/conditions/0/rule` | string | 是 | 已有准入条件原文，不能由prepare临时改条件 |
| `/state/material/conditions/1/id` | string | 是 | 已有准入条件原文，不能由prepare临时改条件 |
| `/state/material/conditions/1/rule` | string | 是 | 已有准入条件原文，不能由prepare临时改条件 |
| `/state/material/condition_results/0/criterion_id` | string | 是 | 该动作逐条件的当前状态与实际观测 |
| `/state/material/condition_results/0/status` | string | 是 | 该动作逐条件的当前状态与实际观测 |
| `/state/material/condition_results/0/observation` | string | 是 | 该动作逐条件的当前状态与实际观测 |
| `/state/material/condition_results/1/criterion_id` | string | 是 | 该动作逐条件的当前状态与实际观测 |
| `/state/material/condition_results/1/status` | string | 是 | 该动作逐条件的当前状态与实际观测 |
| `/state/material/condition_results/1/observation` | string | 是 | 该动作逐条件的当前状态与实际观测 |
| `/state/material/effects/0/outcome` | string | 是 | 当前方案影响、风险与原资源观测；估计不当硬保证 |
| `/state/material/effects/0/resource_cost` | string | 是 | 当前方案影响、风险与原资源观测；估计不当硬保证 |
| `/state/material/effects/0/risks` | string | 是 | 当前方案影响、风险与原资源观测；估计不当硬保证 |
| `/state/material/authority_constraints/0/rule` | string | 是 | 原host已核授权/范围的必要语义；接回仍核真实权限 |
| `/state/material/authority_constraints/0/status` | string | 是 | 原host已核授权/范围的必要语义；接回仍核真实权限 |
| `/state/references/C1/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/C1/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/C1/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/C2/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/C2/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/C2/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/terminology/ID/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/PM/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/PM/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/gate/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/gate/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/enum_meanings/approve` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/known` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/need_fix` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/pass` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/reject` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/steer` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/questions/decision_selection/type` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/instructions` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/criteria/approveA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/steerA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/needFixA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/rejectA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |

## dp-sign-key

冻结样例：[reference.json](cases/dp-sign-key/reference.json)；来源正文见同目录sources/，原始调用见[captures/dp-sign-key/result.json](captures/dp-sign-key/result.json)。

| material属性 | 来源与组装规则 |
| --- | --- |
| `delivery_scope` | 当前事项完整交付对象与AC正文，不借另一产物标准 |
| `requirement_results` | 实际交付与逐AC对照，未知和失败保留 |
| `verification` | 当前验证/独立review原件；作者自验不能伪装独审 |
| `remaining_impact` | 交付差额、实际影响和是否原权限内可继续 |
| `goal` | 当前已确认交付承诺的业务目标 |
| `deviation` | 目标与实际差额，以及真实外部条件/没有外部条件的观测 |
| `qg_summary` | 当前同对象/范围/产物和标准版本的QG业务结论、遗留和局限 |

| 实际模型字段（JSON Pointer） | 类型 | 发送 | 来源/规则 |
| --- | --- | --- | --- |
| `/model` | string | 是 | 既有决策后端配置；本次真实捕获为jev-latest |
| `/state/scenario` | string | 是 | 当前场景身份；本例明确合成，不是生产观察/授权 |
| `/state/desc` | string | 是 | 原主体准备/吸收的逐句来源摘要；目标、偏差、事件、证据和未知 |
| `/state/material/delivery_scope/subject` | string | 是 | 当前事项完整交付对象与AC正文，不借另一产物标准 |
| `/state/material/delivery_scope/criteria/0/id` | string | 是 | 当前事项完整交付对象与AC正文，不借另一产物标准 |
| `/state/material/delivery_scope/criteria/0/text` | string | 是 | 当前事项完整交付对象与AC正文，不借另一产物标准 |
| `/state/material/delivery_scope/criteria/1/id` | string | 是 | 当前事项完整交付对象与AC正文，不借另一产物标准 |
| `/state/material/delivery_scope/criteria/1/text` | string | 是 | 当前事项完整交付对象与AC正文，不借另一产物标准 |
| `/state/material/requirement_results/0/criterion_id` | string | 是 | 实际交付与逐AC对照，未知和失败保留 |
| `/state/material/requirement_results/0/status` | string | 是 | 实际交付与逐AC对照，未知和失败保留 |
| `/state/material/requirement_results/0/observation` | string | 是 | 实际交付与逐AC对照，未知和失败保留 |
| `/state/material/requirement_results/1/criterion_id` | string | 是 | 实际交付与逐AC对照，未知和失败保留 |
| `/state/material/requirement_results/1/status` | string | 是 | 实际交付与逐AC对照，未知和失败保留 |
| `/state/material/requirement_results/1/observation` | string | 是 | 实际交付与逐AC对照，未知和失败保留 |
| `/state/material/verification/0/criterion_id` | string | 是 | 当前验证/独立review原件；作者自验不能伪装独审 |
| `/state/material/verification/0/check` | string | 是 | 当前验证/独立review原件；作者自验不能伪装独审 |
| `/state/material/verification/0/review_status` | string | 是 | 当前验证/独立review原件；作者自验不能伪装独审 |
| `/state/material/verification/1/criterion_id` | string | 是 | 当前验证/独立review原件；作者自验不能伪装独审 |
| `/state/material/verification/1/check` | string | 是 | 当前验证/独立review原件；作者自验不能伪装独审 |
| `/state/material/verification/1/review_status` | string | 是 | 当前验证/独立review原件；作者自验不能伪装独审 |
| `/state/material/remaining_impact/0/unfinished` | string | 是 | 交付差额、实际影响和是否原权限内可继续 |
| `/state/material/remaining_impact/0/impact` | string | 是 | 交付差额、实际影响和是否原权限内可继续 |
| `/state/material/remaining_impact/0/resolution_scope` | string | 是 | 交付差额、实际影响和是否原权限内可继续 |
| `/state/material/goal` | string | 是 | 当前已确认交付承诺的业务目标 |
| `/state/material/deviation/unmet_or_unverified/0` | string | 是 | 目标与实际差额，以及真实外部条件/没有外部条件的观测 |
| `/state/material/deviation/impact` | string | 是 | 目标与实际差额，以及真实外部条件/没有外部条件的观测 |
| `/state/material/deviation/external_condition` | string | 是 | 目标与实际差额，以及真实外部条件/没有外部条件的观测 |
| `/state/material/qg_summary/verdict` | string | 是 | 当前同对象/范围/产物和标准版本的QG业务结论、遗留和局限 |
| `/state/material/qg_summary/review_scope` | string | 是 | 当前同对象/范围/产物和标准版本的QG业务结论、遗留和局限 |
| `/state/material/qg_summary/open_items/0` | string | 是 | 当前同对象/范围/产物和标准版本的QG业务结论、遗留和局限 |
| `/state/material/qg_summary/freshness` | string | 是 | 当前同对象/范围/产物和标准版本的QG业务结论、遗留和局限 |
| `/state/references/AC-001/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-001/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-001/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-002/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-002/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/AC-002/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/terminology/AC/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/AC/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/QG/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/QG/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/review/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/review/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/独审/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/独审/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/补证/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/补证/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/enum_meanings/continue` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/finalize` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/fix` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/pass` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/unknown` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/user-confirm` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/questions/decision_selection/type` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/instructions` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/criteria/finalizeA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/continueA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/confirmA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |

## dp-auto

冻结样例：[reference.json](cases/dp-auto-current/reference.json)；来源正文见同目录sources/，原始调用见[captures/dp-auto-current/result.json](captures/dp-auto-current/result.json)。

| material属性 | 来源与组装规则 |
| --- | --- |
| `question` | 原事项当前事件及单一决策问题 |
| `decision_scope` | 已确认的决策单位/范围；本例引用current_goal完整正文 |
| `objective` | 原主体明确目标/成功条件/优先级；本例是新增合成current_goal前提 |
| `evidence` | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `unknowns` | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `constraints` | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |

| 实际模型字段（JSON Pointer） | 类型 | 发送 | 来源/规则 |
| --- | --- | --- | --- |
| `/model` | string | 是 | 既有决策后端配置；本次真实捕获为jev-latest |
| `/state/scenario` | string | 是 | 当前场景身份；本例明确合成，不是生产观察/授权 |
| `/state/desc` | string | 是 | 原主体准备/吸收的逐句来源摘要；目标、偏差、事件、证据和未知 |
| `/state/material/question` | string | 是 | 原事项当前事件及单一决策问题 |
| `/state/material/decision_scope/unit` | string | 是 | 已确认的决策单位/范围；本例引用current_goal完整正文 |
| `/state/material/decision_scope/source` | string | 是 | 已确认的决策单位/范围；本例引用current_goal完整正文 |
| `/state/material/objective/status` | string | 是 | 原主体明确目标/成功条件/优先级；本例是新增合成current_goal前提 |
| `/state/material/objective/source` | string | 是 | 原主体明确目标/成功条件/优先级；本例是新增合成current_goal前提 |
| `/state/material/objective/success` | string | 是 | 原主体明确目标/成功条件/优先级；本例是新增合成current_goal前提 |
| `/state/material/objective/priorities/0` | string | 是 | 原主体明确目标/成功条件/优先级；本例是新增合成current_goal前提 |
| `/state/material/objective/priorities/1` | string | 是 | 原主体明确目标/成功条件/优先级；本例是新增合成current_goal前提 |
| `/state/material/objective/priorities/2` | string | 是 | 原主体明确目标/成功条件/优先级；本例是新增合成current_goal前提 |
| `/state/material/evidence/0/source` | string | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/0/kind` | string | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/0/timeout_stage` | string | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/0/failure_count` | number | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/0/implication` | string | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/1/source` | string | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/1/kind` | string | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/1/scope` | string | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/1/sampling_period_seconds` | number | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/1/freshness` | string | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/evidence/1/implication` | string | 是 | 当前观测与来源能力，逐项记录超时阶段/次数/快照范围和新鲜度局限 |
| `/state/material/unknowns/0/unknown` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/0/affects/0` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/0/affects/1` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/0/evidence_needed` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/0/available_before_choice` | boolean | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/1/unknown` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/1/affects/0` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/1/affects/1` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/1/evidence_needed` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/1/available_before_choice` | boolean | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/2/unknown` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/2/affects/0` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/2/affects/1` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/2/evidence_needed` | string | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/unknowns/2/available_before_choice` | boolean | 是 | 会改变比较的未知、受影响候选、消解证据及决策前可取性 |
| `/state/material/constraints/source` | string | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/remaining_seconds_at_preparation` | number | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/report_reserve_seconds` | number | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/max_status_retries` | number | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/max_health_reads` | number | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/retry_deadline_seconds` | number | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/health_deadline_seconds` | number | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/stop_conditions/0` | string | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/stop_conditions/1` | string | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/stop_conditions/2` | string | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/stop_conditions/3` | string | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/stop_conditions/4` | string | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/material/constraints/clock_rule` | string | 是 | 原事项额度/次数/硬上限/报告预留/停止；本例源为合成limits |
| `/state/references/current_goal/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/current_goal/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/current_goal/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/timeout_record/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/timeout_record/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/timeout_record/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/health_contract/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/health_contract/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/health_contract/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/limits/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/limits/scope` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/limits/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/terminology/ID/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/host/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/host/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/enum_meanings/explicit` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/synthetic-observation` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/synthetic-source-contract` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/synthetic-accepted-premise` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/state/enum_meanings/synthetic-budget-premise` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/questions/decision_selection/type` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/instructions` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/criteria/retryA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/diagnoseA` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |

## dp-route

冻结样例：[reference.json](cases/dp-route/reference.json)；来源正文见同目录sources/，原始调用见[captures/dp-route/result.json](captures/dp-route/result.json)。

| material属性 | 来源与组装规则 |
| --- | --- |
| `actor_role` | host真实当前角色的必要语义投影，不作为认证 |
| `question` | 当前事件需要回答的业务问题，不能复制准备日志 |

| 实际模型字段（JSON Pointer） | 类型 | 发送 | 来源/规则 |
| --- | --- | --- | --- |
| `/model` | string | 是 | 既有决策后端配置；本次真实捕获为jev-latest |
| `/state/scenario` | string | 是 | 当前场景身份；本例明确合成，不是生产观察/授权 |
| `/state/desc` | string | 是 | 原主体准备/吸收的逐句来源摘要；目标、偏差、事件、证据和未知 |
| `/state/material/actor_role` | string | 是 | host真实当前角色的必要语义投影，不作为认证 |
| `/state/material/question` | string | 是 | 当前事件需要回答的业务问题，不能复制准备日志 |
| `/state/references/dp-sign-key/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-sign-key/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-w-check-task/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-w-check-task/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-QG/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-QG/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-pm-steer/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-pm-steer/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-auto/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-auto/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-gate-approve/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-gate-approve/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-w-type/kind` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/references/dp-w-type/content` | string | 是 | 当前请求使用的具体引用正文、对象/关系；与本次material及原来源绑定 |
| `/state/terminology/DP/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/DP/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/ID/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/PM/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/PM/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/QG/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/QG/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/Worker/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/Worker/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/desc/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/gate/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/gate/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/key/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/key/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/直执/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/直执/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/补证/full_name` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/terminology/补证/meaning` | string | 是 | 当前文本/业务字段实际使用的缩写/术语定义注册表，只投影当前必需项 |
| `/state/enum_meanings/pm` | string | 是 | 当前请求实际使用的业务代码、状态或资源单位定义 |
| `/questions/decision_selection/type` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/instructions` | string | 是 | 当前DP职责及既有单选协议，一个decision_selection题 |
| `/questions/decision_selection/criteria/route1` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/route2` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/route3` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/route4` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/route5` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/route6` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
| `/questions/decision_selection/criteria/route7` | string | 是 | 本次合法候选+本地依据配对的可读判据；具体映射见请求附录 |
