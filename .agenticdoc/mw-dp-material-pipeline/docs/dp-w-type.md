# dp-w-type：v0.5可理解的上下文

本例为合成规范输入。术语含义和每个被引用验收项的完整正文都进入模型；真实调用结果另列，不套旧回包。

## 字段发送规则

| 字段 | 发送规则 | 模型落点 | 用途 |
| --- | --- | --- | --- |
| desc | 发送 | state.desc | 当前目标、偏差、事件、证据和未知，<=10句/1000tokens；由原主体确认 |
| work_items | 发送 | state.material.work_items | PM说明实际动作、对象、预期变化，用于区分写代码/取证/审查/识图。 |
| output_expectations | 按需发送 | state.material.output_expectations | 产物内容能区分任务类型时发送；若已在工作动作说清，不再重复。 |
| image_requirement | 按需发送 | state.material.image_requirement | 识图要求或有无图像存在歧义时，说明真实需要；未核实不能默认false。 |
| constraints | 按需发送 | state.material.constraints | 只发影响类型选择的读写/对象/能力边界，不搬项目规则全文。 |
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
  "dp": "dp-w-type",
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
      "label": "获准任务",
      "path": "sources/S1.txt",
      "sha256": "7368e8afa33dc788e276e28d3a82786c638fe0e33ac9bb56813182f89d1cd80e",
      "version": "synthetic-v1",
      "kind": "synthetic-original"
    },
    {
      "id": "S2",
      "label": "输入与能力",
      "path": "sources/S2.txt",
      "sha256": "877b4fb150345c24204c4a7903ff2365c97788be7b0321b91efcc1dc07bc9618",
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
      "coding"
    ],
    "status": "作者参考预期，禁止发给模型"
  },
  "actual_capture": {
    "request": "not-sent-v0.5",
    "response": "not-observed-v0.5"
  },
  "post_checks": "核当前任务/角色/写面和有效模型能力；vision须真实识图能力。通过后只是类型建议，派发另由原工具检查。",
  "freeze": {
    "file": "payload.json",
    "sha256": "30fe499cefea039fff9756ad73bd0ae5982ef437c64a16adbfd3a28c52536cd5",
    "bytes": 2795
  },
  "desc_preparation": {
    "sentences": [
      "目标是修复CSV导出对逗号和双引号的转义并补往返回归测试。",
      "任务尚未执行，当前待决定的是交给哪类Worker，并非审核既有产物。",
      "任务定义要求修改导出器和测试，禁止改格式协议。",
      "已核输入都是文本代码和CSV样本，不需要解释图像。"
    ],
    "sentence_count": 4,
    "max_sentences": 10,
    "max_tokens": 1000,
    "estimated_tokens": 102,
    "token_count": null,
    "meter": "existing-estimator-precheck; target-model exact count not available",
    "source_note": "从v0.3合成来源归纳；QG/sign增加显式同范围fixture，非当前业务事实",
    "source_pointers": [
      "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-type\\reference.json"
    ],
    "sentence_sources": [
      {
        "sentence": 1,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-type\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 2,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-type\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 3,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-type\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 4,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-type\\reference.json"
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
    "desc": "目标是修复CSV导出对逗号和双引号的转义并补往返回归测试。任务尚未执行，当前待决定的是交给哪类Worker，并非审核既有产物。任务定义要求修改导出器和测试，禁止改格式协议。已核输入都是文本代码和CSV样本，不需要解释图像。",
    "material": {
      "work_items": [
        {
          "action": "修改转义算法并增加回归断言",
          "object_kind": "CSV导出器及测试",
          "expected_change": "特殊字符往返解析一致"
        }
      ],
      "output_expectations": [
        {
          "kind": "代码与回归断言",
          "content": "导出器修复及含逗号/双引号样本的往返测试"
        }
      ],
      "image_requirement": {
        "needed": false
      },
      "constraints": [
        {
          "rule": "只改导出器和相应测试，不改格式协议。",
          "status": "known"
        }
      ]
    },
    "references": {},
    "terminology": {
      "CSV": {
        "full_name": "Comma-Separated Values",
        "meaning": "逗号分隔值文本格式；本例需正确转义逗号和双引号并保持往返解析一致。"
      },
      "ID": {
        "full_name": "Identifier",
        "meaning": "标识符；候选ID由本次criteria给出含义，业务引用编号由references给出完整定义，不能自行猜测。"
      },
      "Worker": {
        "full_name": "Worker agent",
        "meaning": "执行已派发任务的Agent；自身可达性由实际当前Worker判断，准备助手不能冒充它。"
      },
      "desc": {
        "full_name": "description",
        "meaning": "本次情境简述：目标、偏差、发生的事件、证据与未知；由原主体准备，最多10句/1000 tokens。"
      },
      "host": {
        "full_name": "host runtime",
        "meaning": "执行工具、核身份/读写范围/停止/预算的宿主框架；材料文本不能替它授予权限。"
      },
      "review": {
        "full_name": "independent review",
        "meaning": "独立审查：对当前对象/版本的标准、断言、实际证据和未覆盖面进行核对，不是作者自评。"
      }
    },
    "enum_meanings": {
      "coding": "需要修改代码或测试的任务类型。",
      "known": "对应约束或条件已由本次来源确认。",
      "research": "以取证/研究为主的任务类型。",
      "review": "审查已有产物的任务类型。",
      "vision": "必须解释图像像素的任务类型。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "这项获准工作应派给哪类Worker？ 只根据本次材料选择一个候选ID；选项是条件式判据，不是条件已成立的事实。不要输出额外原因或执行动作。",
      "criteria": {
        "codingA": "coding：有明确算法改动和测试交付时选coding。",
        "researchA": "research：若当前工作仅为取证、无需修改代码时选research。",
        "reviewA": "review：若当前工作是审查别人已完成的产物时选review。",
        "visionA": "vision：若必须解释图像像素且host能力允许时选vision。"
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
      "wire_id": "codingA",
      "choice": "coding",
      "basis_id": "codingA-basis",
      "criterion": "coding：有明确算法改动和测试交付时选coding。",
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
      "wire_id": "researchA",
      "choice": "research",
      "basis_id": "researchA-basis",
      "criterion": "research：若当前工作仅为取证、无需修改代码时选research。",
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
      "wire_id": "reviewA",
      "choice": "review",
      "basis_id": "reviewA-basis",
      "criterion": "review：若当前工作是审查别人已完成的产物时选review。",
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
      "wire_id": "visionA",
      "choice": "vision",
      "basis_id": "visionA-basis",
      "criterion": "vision：若必须解释图像像素且host能力允许时选vision。",
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
