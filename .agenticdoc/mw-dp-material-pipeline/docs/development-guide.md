# 开发接入与验收清单

本包提供八DP当前语义规范、冻结输入、真实API输出、反解与本地检查。实际发送/返回的版本和时间保留在捕获中；整合为v0.5文档不代表已上线。

## 八DP的职责与材料入口

| DP | 问什么/合法业务结论 | 需要从哪里准备材料 |
| --- | --- | --- |
| dp-w-type | 任务类型：coding/research/review/vision | 当前可执行任务的目标、交付和必要操作，不能只发worker_execution等标签 |
| dp-pm-steer | 组织剩余工作：narrow/split/direct-exec/escalate | 当前目标与偏差、剩余工作、已用/剩余资源和真实外部条件；执行actionplan留本地 |
| dp-w-check-task | 当前实际Worker：continue/terminate/investigate | 该Worker本次已做/未做、可达性与证据/资源；PM或prepare助手不能代它自评 |
| dp-QG | 质量结论及原因范围：pass/fix/reopen | 当前版本独立review先完成核对，完整适用AC正文/完成状态、关联VC/实际结果、发现与未知 |
| dp-gate-approve | 当前具体动作：approve/steer/need_fix/reject | 已有准入条件正文、当前满足状态、范围/资源与具体缺口；不由模型授予新权限 |
| dp-sign-key | 当前事项签收：finalize/continue/user-confirm | 目标与实际偏差、交付逐项证据、当前同对象/范围/版本QG结论与未关闭项 |
| dp-auto | 当前明确问题的2..5真实路径 | 来源目标优先级、区分性证据/未知、信息价值、条件后继、成本上限和停止条件 |
| dp-route | 选择七个职责入口之一 | 当前事件、需回答的问题、必要上下文与各入口职责；路由不执行相应动作 |

固定候选不能按偏好缩为一个。fixA/fixB等wire是“业务结论+原因/剩余项集合”的合法配对；返回一个wire后按同一冻结pair-map恢复全部原因，不要求jev自由文本解释或第二道理由选择题。

各DP字段发送规则和本地决策本在前半部八DP页签。material各属性必须有当前来源、事实性质、变换和适用范围；sources路径/hash用于本地核验，必要正文在state.material/references中实际发送。大文件先取必要正文，再按原预算压缩，保留反证、失败、未知和引用定义，不静默截断。新属性需说明决策用途，不能用整段task goal/requirements/preparation日志充填。

## 组装与返回的边界

| 层 | 必须保存/执行 | 模型是否收到 |
| --- | --- | --- |
| 本地决策本 | 原owner/事项/run、范围、准备模型、源正文版本/hash、逐字段变换、候选/原因映射、执行计划、原累计预算账本 | 整体不发送；只投影必要事实、约束和定义 |
| 模型请求 | model、state.desc/material/references/terminology/enum_meanings、一个decision_selection单选 | 仅冻结完整body，所有入模字段明确可见 |
| 准备比较报告 | 全部候选对的差异、来源支持、反转条件、缺口及ready/needs-evidence/equivalent/invalid | 留本地；相关事实已投影入请求，避免重复推荐答案 |
| 网络捕获 | 最终Request.data原字节、响应原字节、时间、模型/ID/usage/HTTP及hash | 不记录密钥；捕获记录不是业务权限 |
| 返回后 | 官方协议解码→同版pair-map→全部原因/剩余项→原host核来源、身份/权限、停止和当前余量→既有业务writer | 模型选择不等于采纳或执行 |

desc由原PM/实际Worker准备或吸收，最多10句/1000 tokens。精确目标模型token计量仍待接入；现有估计仅预检，不能将整份API input_tokens当desc计数。未知/缺review/过期QG保留，不由词典或confidence推导pass。

## 需要实施的接口与顺序

复用已有任务派发、任务卡model选择、原身份/范围/预算与决策发送通道。拟议prepare profile需实现限定source handles读取、受限产物写入、状态守卫和发布/吸收；严格顺序见prepare Worker页和机器合同。

prepare_model由任务卡选择已注册provider/model，记录请求和实际模型；回退须沿既有显式允许规则。它与decision_model=jev-latest是两个角色。prepare不拿决策密钥、不任意shell/网络/改产品、不改claim，不冒充独审或实际Worker。

原主体可直接准备简单DP，也可委托prepare Worker；所有读取、准备、退回和等待消耗原累计预算。补证失败/模型不可用时可按continuity继续原权限下合法本地处置，不把准备失败设成全局停止门，也不为吸收增加用户审批。草稿/来源/候选/范围/预算变化均重验再冻结。

## 后续实现验收

| 验收面 | 正反例 | 已有证据 / 待完成 |
| --- | --- | --- |
| 候选与配对 | 固定闭集不缩减；多个fix原因完整反解；未知wire拒绝；auto为2..5真实路径 | 八DP请求/返回及pair-map可参考；生产入口需接入回归 |
| 来源与定义 | 只给路径、错对象同ID、无AC正文/术语、源漂移/遗漏/过度压缩 | 结构体与原来源正文集中；实际自动提取/压缩忠实性待实现 |
| QG/sign前提 | 独审与逐AC/VC核对，失败/未测保留；签收引用同范围当前QG | 合成fixture已提供，不是生产review证据 |
| 可区分性 | 缺偏好/比较漏项/无反转条件/等价、路径循环/超预算/额度刷新 | 当前auto正例与21个反例；通用语义与生产守卫待实现 |
| prepare隔离 | 越序/越读写/换模型/冒充Worker或独审/旧报告发布/预算重置 | 工具合同与顺序设计；未部署，需进程/工具层测试 |
| 请求/返回回放 | 完整字节/模型/时间/ID/usage绑定；旧返回不套新payload；不因低confidence自动重试 | captures和integration-manifest绑定原件；生产monitor展示待接入 |
| 执行业务边界 | 接回重核身份、权限、当前来源/余量、取消及唯一writer | 本轮未执行；HTTP200/高confidence不能代过 |

本包由作者自验，无独立复核。历史API共14次，本次整合0次。全仓npm run check此前因其它任务9个证据快照嵌套Biome根配置失败，后续阶段未运行；本包HTML/字节校验单独记录，不冒充全仓通过。未实现项按此表进入后续开发任务后再验收。
