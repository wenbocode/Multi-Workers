# dp-sign-key：v0.5可理解的上下文

本例为合成规范输入。术语含义和每个被引用验收项的完整正文都进入模型；真实调用结果另列，不套旧回包。

## 字段发送规则

| 字段 | 发送规则 | 模型落点 | 用途 |
| --- | --- | --- | --- |
| desc | 发送 | state.desc | 当前目标、偏差、事件、证据和未知，<=10句/1000tokens；由原主体确认 |
| delivery_scope | 发送 | state.material.delivery_scope | 当前交付承诺和所有适用标准正文。 |
| requirement_results | 发送 | state.material.requirement_results | 逐项实际交付与验证结果，未知如实保留。 |
| verification | 发送 | state.material.verification | 独立复核是否存在、验证覆盖和限制；不靠作者自述。 |
| remaining_impact | 按需发送 | state.material.remaining_impact | 仍未完成/未验证项及交付影响；已在结果说清可合并。 |
| goal | 发送 | state.material.goal | 本次新补的精确审核/交付事实 |
| deviation | 发送 | state.material.deviation | 本次新补的精确审核/交付事实 |
| qg_summary | 发送 | state.material.qg_summary | 当前同范围/同版本QG业务结论、未关闭面及限制；source身份留本地核验 |
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
  "dp": "dp-sign-key",
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
      "label": "当前交付承诺",
      "path": "sources/S1.txt",
      "sha256": "0cbc1b2193abd6e00e515ada912153d1ce6eb67ba7667e9bc0d0c52aa3c25fa4",
      "version": "synthetic-v1",
      "kind": "synthetic-original"
    },
    {
      "id": "S2",
      "label": "当前真实验证与独审",
      "path": "sources/S2.txt",
      "sha256": "41d3dd2688cebc0ef773b50c3b0f026a0164ca21403fe550cb211a322d2e6d8c",
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
      "continue"
    ],
    "status": "作者参考预期，禁止发给模型"
  },
  "actual_capture": {
    "request": "not-sent-v0.5",
    "response": "not-observed-v0.5"
  },
  "post_checks": "核当前全部交付标准、真实独审、未完成/外部条件和唯一writer；finalize不等于已签收，user-confirm必须是具体真实问题。",
  "freeze": {
    "file": "payload.json",
    "sha256": "609ae3e2283faa901f66d9fc5e5285a44c9faee220dff601720998900975e29c",
    "bytes": 4436
  },
  "desc_preparation": {
    "sentences": [
      "交付目标是稳定导出，必须满足特殊字符往返一致及中断不留半成品。",
      "当前偏差是中断场景尚未执行，AC-002仍未验证。",
      "同版本独立复核确认AC-001测试有效，并指出AC-002证据缺口。",
      "本合成示例的当前同范围QG业务结论是fix，未关闭项就是中断验证，不借用其它产物的QG结果。",
      "依据为当前交付检查和QG摘要；缺口可在原权限内补取，没有真实需用户决定的外部条件。"
    ],
    "sentence_count": 5,
    "max_sentences": 10,
    "max_tokens": 1000,
    "estimated_tokens": 157,
    "token_count": null,
    "meter": "existing-estimator-precheck; target-model exact count not available",
    "source_note": "从v0.3合成来源归纳；QG/sign增加显式同范围fixture，非当前业务事实",
    "source_pointers": [
      "qg-fixture.json",
      "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-sign-key\\reference.json"
    ],
    "sentence_sources": [
      {
        "sentence": 1,
        "sources": [
          "qg-fixture.json",
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-sign-key\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 2,
        "sources": [
          "qg-fixture.json",
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-sign-key\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 3,
        "sources": [
          "qg-fixture.json",
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-sign-key\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 4,
        "sources": [
          "qg-fixture.json",
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-sign-key\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 5,
        "sources": [
          "qg-fixture.json",
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-sign-key\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      }
    ],
    "claims": "目标/偏差/事件/证据与未知，不写推荐答案"
  },
  "qg_fixture": {
    "sample_kind": "synthetic-QG-fixture-not-a-production-verdict",
    "artifact": "稳定导出",
    "version": "demo-export-v04",
    "verdict": "fix",
    "open_ac_ids": [
      "AC-002"
    ],
    "open_items": [
      "中断不留半成品尚未验证"
    ],
    "review_scope": "特殊字符往返与中断恢复两项当前交付标准",
    "freshness": "与本sign示例交付对象和当前版本一致",
    "note": "不引用导入适配器QG，不把v0.3 jev响应伪装成此处QG产品",
    "criteria_version": "demo-export-criteria-v04",
    "scope_ac_ids": [
      "AC-001",
      "AC-002"
    ]
  },
  "delivery_binding": {
    "artifact": "稳定导出",
    "version": "demo-export-v04",
    "criteria_version": "demo-export-criteria-v04",
    "scope_ac_ids": [
      "AC-001",
      "AC-002"
    ]
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
    "desc": "交付目标是稳定导出，必须满足特殊字符往返一致及中断不留半成品。当前偏差是中断场景尚未执行，AC-002仍未验证。同版本独立复核确认AC-001测试有效，并指出AC-002证据缺口。本合成示例的当前同范围QG业务结论是fix，未关闭项就是中断验证，不借用其它产物的QG结果。依据为当前交付检查和QG摘要；缺口可在原权限内补取，没有真实需用户决定的外部条件。",
    "material": {
      "delivery_scope": {
        "subject": "稳定导出",
        "criteria": [
          {
            "id": "AC-001",
            "text": "特殊字符往返保持一致。"
          },
          {
            "id": "AC-002",
            "text": "中断时不留下半成品。"
          }
        ]
      },
      "requirement_results": [
        {
          "criterion_id": "AC-001",
          "status": "pass",
          "observation": "往返实测一致"
        },
        {
          "criterion_id": "AC-002",
          "status": "unknown",
          "observation": "中断场景未执行"
        }
      ],
      "verification": [
        {
          "criterion_id": "AC-001",
          "check": "当前回归实测",
          "review_status": "独立review已核断言有效"
        },
        {
          "criterion_id": "AC-002",
          "check": "未执行",
          "review_status": "独立review指出未覆盖"
        }
      ],
      "remaining_impact": [
        {
          "unfinished": "中断无半成品的验证",
          "impact": "AC-002尚无支持，不能完成交付承诺",
          "resolution_scope": "现有授权内继续补证"
        }
      ],
      "goal": "稳定导出：特殊字符往返保持一致，中断时不留下半成品。",
      "deviation": {
        "unmet_or_unverified": [
          "中断场景未执行，AC-002未验证"
        ],
        "impact": "尚不能完成全部交付承诺",
        "external_condition": "没有，现有权限内可补取"
      },
      "qg_summary": {
        "verdict": "fix",
        "review_scope": "特殊字符往返与中断恢复两项当前交付标准",
        "open_items": [
          "中断不留半成品尚未验证"
        ],
        "freshness": "与本sign示例交付对象和当前版本一致"
      }
    },
    "references": {
      "AC-001": {
        "kind": "acceptance_criterion",
        "scope": "稳定导出",
        "content": "特殊字符往返保持一致。"
      },
      "AC-002": {
        "kind": "acceptance_criterion",
        "scope": "稳定导出",
        "content": "中断时不留下半成品。"
      }
    },
    "terminology": {
      "AC": {
        "full_name": "Acceptance Criterion / Acceptance Criteria",
        "meaning": "验收标准：已确认的应达到的业务结果；具体编号的完整正文在references中。"
      },
      "ID": {
        "full_name": "Identifier",
        "meaning": "标识符；候选ID由本次criteria给出含义，业务引用编号由references给出完整定义，不能自行猜测。"
      },
      "QG": {
        "full_name": "Quality Gate",
        "meaning": "质量门禁/正式质量审核：按已确认验收标准、验证结果和独立审查形成pass/fix/reopen业务结论；不等于模型置信度。"
      },
      "desc": {
        "full_name": "description",
        "meaning": "本次情境简述：目标、偏差、发生的事件、证据与未知；由原主体准备，最多10句/1000 tokens。"
      },
      "review": {
        "full_name": "independent review",
        "meaning": "独立审查：对当前对象/版本的标准、断言、实际证据和未覆盖面进行核对，不是作者自评。"
      },
      "独审": {
        "full_name": "独立审查",
        "meaning": "由与实现/准备角色独立的审查来源核对当前标准、实际证据和未覆盖面，不能以作者自评替代。"
      },
      "补证": {
        "full_name": "补充证据",
        "meaning": "通过原授权工具读取、调查或验证补足已明确的证据缺口，不能编造验证结果或刷新原预算。"
      }
    },
    "enum_meanings": {
      "continue": "继续原授权范围内的工作或补证。",
      "finalize": "交付具备收尾条件；仍须原签收写入者和业务检查。",
      "fix": "有明确产物缺陷或证据缺口，需修复/补证后复核。",
      "pass": "在当前检查/审核上下文满足要求；不能由局部检查扩大为整体验收。",
      "unknown": "当前事实或验证结论未知。",
      "user-confirm": "确有需要用户回答的外部条件或取舍。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "按交付承诺和验证结果，现在能收尾、应继续，还是确需用户回答具体问题？ 只根据本次材料选择一个候选ID；选项是条件式判据，不是条件已成立的事实。不要输出额外原因或执行动作。",
      "criteria": {
        "finalizeA": "finalize：全部必需标准及独审证据齐备时才收尾；未知不能当pass。",
        "continueA": "continue：补AC-002中断证据并复核，保留未完成事实。",
        "confirmA": "user-confirm：仅对真实需用户决定且不能在原权限内取得的条件提具体问题。"
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
      "wire_id": "finalizeA",
      "choice": "finalize",
      "basis_id": "finalizeA-basis",
      "criterion": "finalize：全部必需标准及独审证据齐备时才收尾；未知不能当pass。",
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
      "wire_id": "continueA",
      "choice": "continue",
      "basis_id": "continueA-basis",
      "criterion": "continue：补AC-002中断证据并复核，保留未完成事实。",
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
      "wire_id": "confirmA",
      "choice": "user-confirm",
      "basis_id": "confirmA-basis",
      "criterion": "user-confirm：仅对真实需用户决定且不能在原权限内取得的条件提具体问题。",
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
