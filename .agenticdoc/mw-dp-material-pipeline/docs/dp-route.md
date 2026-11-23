# dp-route：v0.5可理解的上下文

本例为合成规范输入。术语含义和每个被引用验收项的完整正文都进入模型；真实调用结果另列，不套旧回包。

## 字段发送规则

| 字段 | 发送规则 | 模型落点 | 用途 |
| --- | --- | --- | --- |
| desc | 发送 | state.desc | 当前目标、偏差、事件、证据和未知，<=10句/1000tokens；由原主体确认 |
| actor_role | 按需发送 | state.material.actor_role | 主体角色会影响入口归属时发送；真实绑定仍由host核验。 |
| question | 发送 | state.material.question | 当前需要判断的具体业务问题。 |
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
  "dp": "dp-route",
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
      "label": "真实主体和当前问题",
      "path": "sources/S1.txt",
      "sha256": "ea72dab667698da5c0a73e27c94110287df47766126821b815c5029c7f994feb",
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
      "dp-QG"
    ],
    "status": "作者参考预期，禁止发给模型"
  },
  "actual_capture": {
    "request": "not-sent-v0.5",
    "response": "not-observed-v0.5"
  },
  "post_checks": "核真实PM绑定及目标是本次7个入口之一；只转交责任，Worker目标仍由真实Worker执行，不代目标业务判断。",
  "freeze": {
    "file": "payload.json",
    "sha256": "3b40984c3beb76a30204c0bf05af1a544429aa9f13dc897fcbb973421a30c3a8",
    "bytes": 4332
  },
  "desc_preparation": {
    "sentences": [
      "原PM当前需要判断一份产物是否满足已确认的质量标准。",
      "尚未提出整个key交付收尾，也不是申请执行gate动作。",
      "当前偏差是入口尚未归类，依据是这次明确的业务问题和审核范围。",
      "这里只选择责任入口，不代后续入口作质量判断；若已处于固定QG节点就无需再路由。"
    ],
    "sentence_count": 4,
    "max_sentences": 10,
    "max_tokens": 1000,
    "estimated_tokens": 115,
    "token_count": null,
    "meter": "existing-estimator-precheck; target-model exact count not available",
    "source_note": "从v0.3合成来源归纳；QG/sign增加显式同范围fixture，非当前业务事实",
    "source_pointers": [
      "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-route\\reference.json"
    ],
    "sentence_sources": [
      {
        "sentence": 1,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-route\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 2,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-route\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 3,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-route\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 4,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-route\\reference.json"
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
    "desc": "原PM当前需要判断一份产物是否满足已确认的质量标准。尚未提出整个key交付收尾，也不是申请执行gate动作。当前偏差是入口尚未归类，依据是这次明确的业务问题和审核范围。这里只选择责任入口，不代后续入口作质量判断；若已处于固定QG节点就无需再路由。",
    "material": {
      "actor_role": "pm",
      "question": "这份当前产物能否满足已确认标准，应交哪个判断入口？"
    },
    "references": {
      "dp-sign-key": {
        "kind": "decision_entry",
        "content": "判断当前工作项是否满足交付承诺并可签收收尾。"
      },
      "dp-w-check-task": {
        "kind": "decision_entry",
        "content": "实际执行者判断当前任务继续、有界补证或如实结束本次执行。"
      },
      "dp-QG": {
        "kind": "decision_entry",
        "content": "对当前产物按完整验收标准和独立证据形成正式质量结论。"
      },
      "dp-pm-steer": {
        "kind": "decision_entry",
        "content": "判断剩余工作的组织方向：收窄本轮、拆分、管理者直执或真实外部介入。"
      },
      "dp-auto": {
        "kind": "decision_entry",
        "content": "在当前明确的现场问题所准备的真实方案之间选择。"
      },
      "dp-gate-approve": {
        "kind": "decision_entry",
        "content": "判断已有准入门是否允许当前具体动作。"
      },
      "dp-w-type": {
        "kind": "decision_entry",
        "content": "选择派发的执行者类型：写代码、取证、审查或识图。"
      }
    },
    "terminology": {
      "DP": {
        "full_name": "Decision Point",
        "meaning": "一个职责明确的决策入口；路由只选择入口，不批准入口对应动作。"
      },
      "ID": {
        "full_name": "Identifier",
        "meaning": "标识符；候选ID由本次criteria给出含义，业务引用编号由references给出完整定义，不能自行猜测。"
      },
      "PM": {
        "full_name": "Project Manager agent",
        "meaning": "管理当前项目事项、组织任务并回收证据的项目管理Agent；不能冒充实际执行者或独立审查者。"
      },
      "QG": {
        "full_name": "Quality Gate",
        "meaning": "质量门禁/正式质量审核：按已确认验收标准、验证结果和独立审查形成pass/fix/reopen业务结论；不等于模型置信度。"
      },
      "Worker": {
        "full_name": "Worker agent",
        "meaning": "执行已派发任务的Agent；自身可达性由实际当前Worker判断，准备助手不能冒充它。"
      },
      "desc": {
        "full_name": "description",
        "meaning": "本次情境简述：目标、偏差、发生的事件、证据与未知；由原主体准备，最多10句/1000 tokens。"
      },
      "gate": {
        "full_name": "execution gate",
        "meaning": "已有执行准入门，核本次具体动作是否满足既有条件和权限。"
      },
      "key": {
        "full_name": "project work key",
        "meaning": "项目工作项标识；本例讨论整个key交付时才属于签收，不能仅凭标识推测认领者。"
      },
      "直执": {
        "full_name": "直接执行",
        "meaning": "由当前项目管理者在原权限与剩余预算内直接完成工作，必要独立复核仍保留。"
      },
      "补证": {
        "full_name": "补充证据",
        "meaning": "通过原授权工具读取、调查或验证补足已明确的证据缺口，不能编造验证结果或刷新原预算。"
      }
    },
    "enum_meanings": {
      "pm": "项目管理Agent的角色标签，真实身份仍由宿主核验。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "这个业务问题应交给哪个入口？只路由，不代目标入口判断。 只根据本次材料选择一个候选ID；选项是条件式判据，不是条件已成立的事实。不要输出额外原因或执行动作。",
      "criteria": {
        "route1": "dp-w-type：问题是选择派发类型时选择此入口；不代该入口裁决。",
        "route2": "dp-pm-steer：问题是PM组织安排时选择此入口；不代该入口裁决。",
        "route3": "dp-w-check-task：问题归当前Worker自身可达性时，仅交该Worker准备选择此入口；不代该入口裁决。",
        "route4": "dp-QG：问题是对当前产物按标准做正式质量审查时选择此入口；不代该入口裁决。",
        "route5": "dp-gate-approve：问题是既有gate对具体动作准入时选择此入口；不代该入口裁决。",
        "route6": "dp-sign-key：问题是整个key交付收尾时选择此入口；不代该入口裁决。",
        "route7": "dp-auto：问题是其它明确现场方案比较时选择此入口；不代该入口裁决。"
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
      "wire_id": "route1",
      "choice": "dp-w-type",
      "basis_id": "route1-basis",
      "criterion": "dp-w-type：问题是选择派发类型时选择此入口；不代该入口裁决。",
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
      "wire_id": "route2",
      "choice": "dp-pm-steer",
      "basis_id": "route2-basis",
      "criterion": "dp-pm-steer：问题是PM组织安排时选择此入口；不代该入口裁决。",
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
      "wire_id": "route3",
      "choice": "dp-w-check-task",
      "basis_id": "route3-basis",
      "criterion": "dp-w-check-task：问题归当前Worker自身可达性时，仅交该Worker准备选择此入口；不代该入口裁决。",
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
      "wire_id": "route4",
      "choice": "dp-QG",
      "basis_id": "route4-basis",
      "criterion": "dp-QG：问题是对当前产物按标准做正式质量审查时选择此入口；不代该入口裁决。",
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
      "wire_id": "route5",
      "choice": "dp-gate-approve",
      "basis_id": "route5-basis",
      "criterion": "dp-gate-approve：问题是既有gate对具体动作准入时选择此入口；不代该入口裁决。",
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
      "wire_id": "route6",
      "choice": "dp-sign-key",
      "basis_id": "route6-basis",
      "criterion": "dp-sign-key：问题是整个key交付收尾时选择此入口；不代该入口裁决。",
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
      "wire_id": "route7",
      "choice": "dp-auto",
      "basis_id": "route7-basis",
      "criterion": "dp-auto：问题是其它明确现场方案比较时选择此入口；不代该入口裁决。",
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
