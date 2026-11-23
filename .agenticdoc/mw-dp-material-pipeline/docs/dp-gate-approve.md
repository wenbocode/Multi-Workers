# dp-gate-approve：v0.5可理解的上下文

本例为合成规范输入。术语含义和每个被引用验收项的完整正文都进入模型；真实调用结果另列，不套旧回包。

## 字段发送规则

| 字段 | 发送规则 | 模型落点 | 用途 |
| --- | --- | --- | --- |
| desc | 发送 | state.desc | 当前目标、偏差、事件、证据和未知，<=10句/1000tokens；由原主体确认 |
| proposed_action | 发送 | state.material.proposed_action | 当前待准入的具体动作、预期结果和范围；不发送完整执行脚本。 |
| conditions | 发送 | state.material.conditions | 已有gate实际要求判断的条件正文。 |
| condition_results | 发送 | state.material.condition_results | 逐条件的真实满足/失败/未知及观测。 |
| effects | 按需发送 | state.material.effects | 影响准入选择的后果/预计成本/风险；不造空泛效果段。 |
| authority_constraints | 按需发送 | state.material.authority_constraints | 与本动作相关的现有授权/停止边界的可读含义；凭证与身份检查留本地。 |
| model | 发送 | model | 调用参数；由实际timi配置选择jev-latest，不是业务事实。 |
| scenario | 发送 | state.scenario | 本包合成验证身份；真实业务请求以真实场景替换，不伪造授权。 |
| evidence_sources | 按需发送 | state.evidence_sources | 需要原文才能理解/复核时发必要正文和限制；已在material达意则不重复；路径/hash不替正文。 |
| decision_selection.type/instructions/criteria | 发送 | questions.decision_selection | 一个单选题，完整合法候选及可读判据；依据在选项内表达一次。 |
| references | 发送 | state.references | 当前引用项完整正文/含义和适用范围；AC/VC/发现/工作项/入口在请求内可解 |
| terminology | 发送 | state.terminology | desc、材料、题干、选项及业务字段实际使用的缩写/术语解释 |
| enum_meanings | 按需发送 | state.enum_meanings | 本请求使用的状态/业务选项代码和资源单位含义 |
| 来源路径/hash/原始权限/定义提取过程/配对映射/请求身份 | 仅本地 | 不发送 | 不能用本地有定义冒充模型已收到 |

## 本地决策本

```json
{
  "schema": "dp-reference-v0.5-draft",
  "sample_kind": "synthetic-reference",
  "dp": "dp-gate-approve",
  "role_scope": "pm",
  "binding": {
    "owner_ref": null,
    "matter_ref": null,
    "budget_ref": null,
    "status": "合成参考，无生产身份"
  },
  "sources": [
    {
      "id": "S1",
      "label": "现有gate条件与授权",
      "path": "sources/S1.txt",
      "sha256": "536e0164a8102002444f4581f7a003471a3faef8f31694f6620eaf0c212d180f",
      "version": "synthetic-v1",
      "kind": "synthetic-original"
    },
    {
      "id": "S2",
      "label": "当前计划和条件检查",
      "path": "sources/S2.txt",
      "sha256": "ae6101069d18e89f5c26f643b1cfaeadc3e86dd94829c260fe75c59caba0a4be",
      "version": "synthetic-v1",
      "kind": "synthetic-original"
    }
  ],
  "field_trace": {
    "file": "field-trace.json",
    "note": "真实原件与字段变换留本地；本例源正文见sources/。"
  },
  "preparation": {
    "prepared_at": "由实际准备者/host落盘",
    "basis_catalog": "见pair-map.json",
    "material_refs": "每个选项关联本次材料",
    "applies_to": "本地校验，不能据此裁剪固定候选",
    "producer": "原PM/实际Worker，或受托prepare Worker起草后由原主体工具吸收"
  },
  "pair_map": {
    "file": "pair-map.json"
  },
  "host_exclusions": [],
  "execution_plan": {
    "status": "未制定；选择方向后由原主体按授权准备",
    "send": false
  },
  "expected": {
    "choices": [
      "approve"
    ],
    "status": "作者参考预期，禁止发给模型"
  },
  "actual_capture": {
    "request": "not-sent-v0.5",
    "response": "not-observed-v0.5"
  },
  "post_checks": "核已有授权、当前条件、预算/停止和动作范围；approve不增加权限，其它分支按既有接续处理，不自动释放gate。",
  "freeze": {
    "file": "payload.json",
    "sha256": "9c6a7b8e72dfe75aad4e126c334abc6afccb2861a861b9d5480fcadba4080aad",
    "bytes": 3257
  },
  "desc_preparation": {
    "sentences": [
      "当前拟在隔离输入上做一次只读回放并保存完整差异。",
      "这道既有gate要求无产品写入且差异保存开启，两项当前检查均满足。",
      "预计耗时10分钟，原余额20分钟，原授权已包含本次动作。",
      "没有观察到准入条件偏差，覆盖仅限这份固定样本；依据是当前配置和条件检查，不是历史审批。"
    ],
    "sentence_count": 4,
    "max_sentences": 10,
    "max_tokens": 1000,
    "estimated_tokens": 122,
    "token_count": null,
    "meter": "existing-estimator-precheck; target-model exact count not available",
    "source_note": "从v0.3合成来源归纳；QG/sign增加显式同范围fixture，非当前业务事实",
    "source_pointers": [
      "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-gate-approve\\reference.json"
    ],
    "sentence_sources": [
      {
        "sentence": 1,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-gate-approve\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 2,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-gate-approve\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 3,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-gate-approve\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 4,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-gate-approve\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      }
    ],
    "claims": "目标/偏差/事件/证据与未知，不写推荐答案"
  },
  "definition_sources": {
    "AC": "已确认验收正文；本例来自v0.4合成scope",
    "VC": "项目设计Verification Contract；本例来自v0.4合成review矩阵",
    "other_refs": "本次来源中的发现/剩余工作/入口职责",
    "registry": "仅使用当前请求出现的术语，未知项拒绝准备"
  }
}
```

## 最终模型payload

完整body如下；references既解释编号对应的具体内容，terminology解释缩写和术语，两层都必须在场。只包含本次所需定义。

```json
{
  "model": "jev-latest",
  "state": {
    "scenario": "合成案例：只评估下列材料并选择，不执行任何业务动作。",
    "desc": "当前拟在隔离输入上做一次只读回放并保存完整差异。这道既有gate要求无产品写入且差异保存开启，两项当前检查均满足。预计耗时10分钟，原余额20分钟，原授权已包含本次动作。没有观察到准入条件偏差，覆盖仅限这份固定样本；依据是当前配置和条件检查，不是历史审批。",
    "material": {
      "proposed_action": [
        {
          "action": "用冻结输入做一次只读回放",
          "expected_result": "保存本次差异，不改产品数据"
        }
      ],
      "conditions": [
        {
          "id": "C1",
          "rule": "无产品写入"
        },
        {
          "id": "C2",
          "rule": "保留完整差异"
        }
      ],
      "condition_results": [
        {
          "criterion_id": "C1",
          "status": "pass",
          "observation": "当前回放器配置只读"
        },
        {
          "criterion_id": "C2",
          "status": "pass",
          "observation": "差异保存已启用"
        }
      ],
      "effects": [
        {
          "outcome": "本次计划得到可审查差异",
          "resource_cost": "估计10分钟；当前原余额20分钟",
          "risks": "只覆盖这份冻结样本"
        }
      ],
      "authority_constraints": [
        {
          "rule": "当前授权含此次隔离只读回放；拒绝仅整理证据，不执行额外清理。",
          "status": "known"
        }
      ]
    },
    "references": {
      "C1": {
        "kind": "gate_condition",
        "scope": "本次具体动作的既有准入门",
        "content": "无产品写入"
      },
      "C2": {
        "kind": "gate_condition",
        "scope": "本次具体动作的既有准入门",
        "content": "保留完整差异"
      }
    },
    "terminology": {
      "ID": {
        "full_name": "Identifier",
        "meaning": "标识符；候选ID由本次criteria给出含义，业务引用编号由references给出完整定义，不能自行猜测。"
      },
      "PM": {
        "full_name": "Project Manager agent",
        "meaning": "管理当前项目事项、组织任务并回收证据的项目管理Agent；不能冒充实际执行者或独立审查者。"
      },
      "desc": {
        "full_name": "description",
        "meaning": "本次情境简述：目标、偏差、发生的事件、证据与未知；由原主体准备，最多10句/1000 tokens。"
      },
      "gate": {
        "full_name": "execution gate",
        "meaning": "已有执行准入门，核本次具体动作是否满足既有条件和权限。"
      }
    },
    "enum_meanings": {
      "approve": "既有准入条件允许当前限定动作。",
      "known": "对应约束或条件已由本次来源确认。",
      "need_fix": "推进安排明确，但存在具体技术或材料缺口。",
      "pass": "在当前检查/审核上下文满足要求；不能由局部检查扩大为整体验收。",
      "reject": "拒绝当前推进方案，不隐含额外清理/写权限。",
      "steer": "组织安排需由管理Agent调整。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "当前具体动作是否满足这道gate，应approve、steer、need_fix还是reject？ 只根据本次材料选择一个候选ID；选项是条件式判据，不是条件已成立的事实。不要输出额外原因或执行动作。",
      "criteria": {
        "approveA": "approve：当前计划满足C1/C2且仍在原权限/预算内时批准该限定动作。",
        "steerA": "steer：若问题在组织/执行安排，交PM重排，不扩大当前动作范围。",
        "needFixA": "need_fix：若安排明确但存在技术/材料缺口，交PM形成具体修复。",
        "rejectA": "reject：若计划不应推进则拒绝；仅允许原授权的证据整理。"
      }
    }
  }
}
```

## 返回后的反解和检查

原始回包→本次别名表反解→核全部原因/剩余项→置信和概率分别保留→原host分支核验；选择不等于执行。真实本次返回单独回放。

```json
{
  "pair_map": [
    {
      "wire_id": "approveA",
      "choice": "approve",
      "basis_id": "approveA-basis",
      "criterion": "approve：当前计划满足C1/C2且仍在原权限/预算内时批准该限定动作。",
      "material_refs": [
        "state.desc",
        "state.material",
        "state.references",
        "state.terminology"
      ],
      "finding_ids": [],
      "remaining_ids": []
    },
    {
      "wire_id": "steerA",
      "choice": "steer",
      "basis_id": "steerA-basis",
      "criterion": "steer：若问题在组织/执行安排，交PM重排，不扩大当前动作范围。",
      "material_refs": [
        "state.desc",
        "state.material",
        "state.references",
        "state.terminology"
      ],
      "finding_ids": [],
      "remaining_ids": []
    },
    {
      "wire_id": "needFixA",
      "choice": "need_fix",
      "basis_id": "needFixA-basis",
      "criterion": "need_fix：若安排明确但存在技术/材料缺口，交PM形成具体修复。",
      "material_refs": [
        "state.desc",
        "state.material",
        "state.references",
        "state.terminology"
      ],
      "finding_ids": [],
      "remaining_ids": []
    },
    {
      "wire_id": "rejectA",
      "choice": "reject",
      "basis_id": "rejectA-basis",
      "criterion": "reject：若计划不应推进则拒绝；仅允许原授权的证据整理。",
      "material_refs": [
        "state.desc",
        "state.material",
        "state.references",
        "state.terminology"
      ],
      "finding_ids": [],
      "remaining_ids": []
    }
  ],
  "executed": false,
  "checks": [
    "一个完整choice回答",
    "本次候选和引用定义一致",
    "当前来源/独审/权限/预算/停止边界",
    "QG逐AC/VC状态；sign当前同范围QG",
    "保留低置信，不为抬高数字重发"
  ]
}
```
