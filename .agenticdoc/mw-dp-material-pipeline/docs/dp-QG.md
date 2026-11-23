# dp-QG：v0.5可理解的上下文

本例为合成规范输入。术语含义和每个被引用验收项的完整正文都进入模型；真实调用结果另列，不套旧回包。

## 字段发送规则

| 字段 | 发送规则 | 模型落点 | 用途 |
| --- | --- | --- | --- |
| desc | 发送 | state.desc | 当前目标、偏差、事件、证据和未知，<=10句/1000tokens；由原主体确认 |
| review_scope | 发送 | state.material.review_scope | 当前受审对象与适用范围；真实版本身份留本地。 |
| review_summary | 发送 | state.material.review_summary | review过程完成/覆盖/独立性事实，不等于AC通过 |
| ac_completion | 发送 | state.material.ac_completion | 独立review后逐AC完成情况及VC结果；未执行VC不可填pass |
| findings | 发送 | state.material.findings | 独审具体发现、状态、关联标准；保留缺陷与证据缺口。 |
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
  "dp": "dp-QG",
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
      "label": "当前质量标准",
      "path": "sources/S1.txt",
      "sha256": "019f057aaef838b7437a893f356a9ac05fe4e35e8076e55b2cda390610fd8ce3",
      "version": "synthetic-v1",
      "kind": "synthetic-original"
    },
    {
      "id": "S2",
      "label": "独立审查与复现实测",
      "path": "sources/S2.txt",
      "sha256": "b4335424644f449c28c788b0a2370d09f254363d3e198ab5e63643a816c23a16",
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
  "host_exclusions": [
    {
      "choice": "reopen",
      "rule_ref": "decision_points.entry_choice_issues:dp-QG/reopen",
      "source_ids": [
        "S1"
      ],
      "reason": "合成S1明确无实质标准争议；依现有规则推演排除，不伪造争议。"
    }
  ],
  "execution_plan": {
    "status": "未制定；选择方向后由原主体按授权准备",
    "send": false
  },
  "expected": {
    "choices": [
      "fix"
    ],
    "status": "作者参考预期，禁止发给模型"
  },
  "actual_capture": {
    "request": "not-sent-v0.5",
    "response": "not-observed-v0.5"
  },
  "post_checks": "核适用标准完整、真实独审及来源版本；pass须必要证据齐备，fix保留全部已知原因和剩余面，reopen须实质标准问题；不直接写QG产品。",
  "freeze": {
    "file": "payload.json",
    "sha256": "3384f2220388912607c490868eefc7758989f372906ba64d7b2576d6a83e09ae",
    "bytes": 5288
  },
  "desc_preparation": {
    "sentences": [
      "本次审核导入事务适配器是否满足重复键无写入和并发顺序两项验收标准。",
      "本合成示例的独立review已完成对全部AC和关联VC的核对，这不表示AC通过。",
      "AC-001未满足：VC-001复现了拒绝重复键后仍发生一条写入，对应F1。",
      "AC-002未验证：VC-002并发检查尚未执行，对应F2。",
      "依据是同一冻结版本的review矩阵和观测；标准无实质争议，当前问题是质量结论及需处理的范围。"
    ],
    "sentence_count": 5,
    "max_sentences": 10,
    "max_tokens": 1000,
    "estimated_tokens": 154,
    "token_count": null,
    "meter": "existing-estimator-precheck; target-model exact count not available",
    "source_note": "从v0.3合成来源归纳；QG/sign增加显式同范围fixture，非当前业务事实",
    "source_pointers": [
      "review-fixture.json"
    ],
    "sentence_sources": [
      {
        "sentence": 1,
        "sources": [
          "review-fixture.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 2,
        "sources": [
          "review-fixture.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 3,
        "sources": [
          "review-fixture.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 4,
        "sources": [
          "review-fixture.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 5,
        "sources": [
          "review-fixture.json"
        ],
        "kind": "synthetic-sourced-example"
      }
    ],
    "claims": "目标/偏差/事件/证据与未知，不写推荐答案"
  },
  "review_fixture": {
    "sample_kind": "synthetic-review-fixture-not-actual-review",
    "artifact": "导入事务适配器",
    "version": "demo-import-v04",
    "reviewer_role": "independent-reviewer-fixture",
    "review_status": "completed",
    "covered_ac_ids": [
      "AC-001",
      "AC-002"
    ],
    "ac_completion": [
      {
        "ac_id": "AC-001",
        "requirement": "拒绝重复键且失败时不写入",
        "status": "not-met",
        "vc_results": [
          {
            "vc_id": "VC-001",
            "verification": "重复键拒绝后检查写入数",
            "status": "fail",
            "observation": "仍有一条写入",
            "evidence": "同版本review记录的复现实测"
          }
        ],
        "deviation": "无副作用要求未满足",
        "finding_ids": [
          "F1"
        ]
      },
      {
        "ac_id": "AC-002",
        "requirement": "并发导入保持规定顺序",
        "status": "unverified",
        "vc_results": [
          {
            "vc_id": "VC-002",
            "verification": "并发顺序检查",
            "status": "not-run",
            "observation": "尚未执行，review已明确核对这一缺口",
            "evidence": "同版本review的覆盖说明"
          }
        ],
        "deviation": "尚无并发顺序证据",
        "finding_ids": [
          "F2"
        ]
      }
    ],
    "criteria_dispute": "已核无实质标准争议",
    "note": "AC/VC为示例逻辑映射，不是新完成的生产review或测试"
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
    "desc": "本次审核导入事务适配器是否满足重复键无写入和并发顺序两项验收标准。本合成示例的独立review已完成对全部AC和关联VC的核对，这不表示AC通过。AC-001未满足：VC-001复现了拒绝重复键后仍发生一条写入，对应F1。AC-002未验证：VC-002并发检查尚未执行，对应F2。依据是同一冻结版本的review矩阵和观测；标准无实质争议，当前问题是质量结论及需处理的范围。",
    "material": {
      "review_scope": {
        "subject": "导入事务适配器",
        "ac_ids": [
          "AC-001",
          "AC-002"
        ]
      },
      "review_summary": {
        "status": "completed",
        "coverage": "全部适用AC及其VC已核对；VC-002仍未运行",
        "independence": "来自示例独立review角色；实际运行须验真实review身份"
      },
      "ac_completion": [
        {
          "ac_id": "AC-001",
          "requirement": "拒绝重复键且失败时不写入",
          "status": "not-met",
          "vc_results": [
            {
              "vc_id": "VC-001",
              "verification": "重复键拒绝后检查写入数",
              "status": "fail",
              "observation": "仍有一条写入",
              "evidence": "同版本review记录的复现实测"
            }
          ],
          "deviation": "无副作用要求未满足",
          "finding_ids": [
            "F1"
          ]
        },
        {
          "ac_id": "AC-002",
          "requirement": "并发导入保持规定顺序",
          "status": "unverified",
          "vc_results": [
            {
              "vc_id": "VC-002",
              "verification": "并发顺序检查",
              "status": "not-run",
              "observation": "尚未执行，review已明确核对这一缺口",
              "evidence": "同版本review的覆盖说明"
            }
          ],
          "deviation": "尚无并发顺序证据",
          "finding_ids": [
            "F2"
          ]
        }
      ],
      "findings": [
        {
          "id": "F1",
          "ac_id": "AC-001",
          "status": "open",
          "observation": "重复键拒绝仍有写入"
        },
        {
          "id": "F2",
          "ac_id": "AC-002",
          "status": "open",
          "observation": "并发顺序未验证"
        }
      ]
    },
    "references": {
      "AC-001": {
        "kind": "acceptance_criterion",
        "scope": "导入事务适配器",
        "content": "拒绝重复键且失败时不写入"
      },
      "VC-001": {
        "kind": "verification_contract",
        "scope": "导入事务适配器",
        "ac_ids": [
          "AC-001"
        ],
        "content": "重复键拒绝后检查写入数",
        "expected_result": "拒绝重复键且失败时不写入"
      },
      "AC-002": {
        "kind": "acceptance_criterion",
        "scope": "导入事务适配器",
        "content": "并发导入保持规定顺序"
      },
      "VC-002": {
        "kind": "verification_contract",
        "scope": "导入事务适配器",
        "ac_ids": [
          "AC-002"
        ],
        "content": "并发顺序检查",
        "expected_result": "并发导入保持规定顺序"
      },
      "F1": {
        "kind": "review_finding",
        "scope": "导入事务适配器",
        "ac_ids": [
          "AC-001"
        ],
        "content": "重复键拒绝仍有写入"
      },
      "F2": {
        "kind": "review_finding",
        "scope": "导入事务适配器",
        "ac_ids": [
          "AC-002"
        ],
        "content": "并发顺序未验证"
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
      "VC": {
        "full_name": "Verification Contract",
        "meaning": "验证合同/验证项：本项目设计文档规定如何验证关联验收标准、应观察什么结果；具体编号定义在references中。"
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
      "completed": "此处所指核对过程已结束，不代表所有验收标准通过。",
      "fail": "该验证实际失败。",
      "fix": "有明确产物缺陷或证据缺口，需修复/补证后复核。",
      "not-met": "验收标准已确认未满足。",
      "not-run": "这条验证尚未执行，不能填通过。",
      "open": "该发现或缺口尚未关闭。",
      "pass": "在当前检查/审核上下文满足要求；不能由局部检查扩大为整体验收。",
      "unverified": "验收标准尚无足够验证，不能当作完成。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "按当前适用标准，受审产物应pass、fix还是reopen？ 只根据本次材料选择一个候选ID；选项是条件式判据，不是条件已成立的事实。不要输出额外原因或执行动作。",
      "criteria": {
        "passA": "pass：全部适用AC满足且VC和独审证据充分、无未覆盖面时通过；不能忽略当前失败和未验证项。",
        "fixA": "fix：先处理F1并复评F2，保留AC-002未验证状态；不表示全范围质量已关闭。",
        "fixB": "fix：处理F1和F2，即修复重复键写入并补并发检查，再对照AC/VC独立复核。"
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
      "wire_id": "passA",
      "choice": "pass",
      "basis_id": "passA-basis",
      "criterion": "pass：全部适用AC满足且VC和独审证据充分、无未覆盖面时通过；不能忽略当前失败和未验证项。",
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
      "wire_id": "fixA",
      "choice": "fix",
      "basis_id": "fixA-basis",
      "criterion": "fix：先处理F1并复评F2，保留AC-002未验证状态；不表示全范围质量已关闭。",
      "material_refs": [
        "state.desc",
        "state.material",
        "state.references",
        "state.terminology"
      ],
      "finding_ids": [
        "F1"
      ],
      "remaining_ids": [
        "F2"
      ]
    },
    {
      "wire_id": "fixB",
      "choice": "fix",
      "basis_id": "fixB-basis",
      "criterion": "fix：处理F1和F2，即修复重复键写入并补并发检查，再对照AC/VC独立复核。",
      "material_refs": [
        "state.desc",
        "state.material",
        "state.references",
        "state.terminology"
      ],
      "finding_ids": [
        "F1",
        "F2"
      ],
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
