# dp-w-check-task：v0.5可理解的上下文

本例为合成规范输入。术语含义和每个被引用验收项的完整正文都进入模型；真实调用结果另列，不套旧回包。

## 字段发送规则

| 字段 | 发送规则 | 模型落点 | 用途 |
| --- | --- | --- | --- |
| desc | 发送 | state.desc | 当前目标、偏差、事件、证据和未知，<=10句/1000tokens；由原主体确认 |
| completed | 发送 | state.material.completed | 本run实际已完成什么；没有完成项可如实为空。 |
| remaining_work | 发送 | state.material.remaining_work | 本run还差什么，不搬父项目全部计划。 |
| reachability | 发送 | state.material.reachability | 下一步已具备、缺失、未知的真实条件。 |
| resources | 按需发送 | state.material.resources | 继续/补证涉及的原run余额；有界probe必须能核原边界。 |
| probe | 按需发送 | state.material.probe | investigate前提成立时发具体未知、可读来源、预期事实及原限制；不是完整调查脚本。 |
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
  "dp": "dp-w-check-task",
  "role_scope": "worker",
  "binding": {
    "owner_ref": null,
    "matter_ref": null,
    "budget_ref": null,
    "status": "合成参考，无生产身份"
  },
  "sources": [
    {
      "id": "S1",
      "label": "自身任务",
      "path": "sources/S1.txt",
      "sha256": "bb7d3a39cbbebcacb6fa6b86bbb4932b99614686bd7ced49376e044d27be673b",
      "version": "synthetic-v1",
      "kind": "synthetic-original"
    },
    {
      "id": "S2",
      "label": "原host读范围与预算",
      "path": "sources/S2.txt",
      "sha256": "80fae9c01b9a734c1f6bb5b9cefccf3c9ace06da2db6fca93b09d01fcf89b8fc",
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
      "investigate"
    ],
    "status": "作者参考预期，禁止发给模型"
  },
  "actual_capture": {
    "request": "not-sent-v0.5",
    "response": "not-observed-v0.5"
  },
  "post_checks": "只由该Worker提交；investigate核指定read、一次边界和原累计预算，continue不刷新deadline，terminate只结束本run并交付真实状态。",
  "freeze": {
    "file": "payload.json",
    "sha256": "78b07296bbb25852ade5ade79f3738c72479818a4af237048702e7e379681ef4",
    "bytes": 3700
  },
  "desc_preparation": {
    "sentences": [
      "当前Worker要验证非ASCII字段解析，ASCII样本已经通过。",
      "偏差是输入编码约定仍未知，不能把非ASCII验证写成完成。",
      "本run的host记录表明还剩8分钟和一次最多1024字节的合法读取。",
      "已授权encoding-note可以提供编码说明，但正文尚未读取。",
      "需要判断继续、一次有界补证或真实收尾本run，不能刷新原预算。"
    ],
    "sentence_count": 5,
    "max_sentences": 10,
    "max_tokens": 1000,
    "estimated_tokens": 126,
    "token_count": null,
    "meter": "existing-estimator-precheck; target-model exact count not available",
    "source_note": "从v0.3合成来源归纳；QG/sign增加显式同范围fixture，非当前业务事实",
    "source_pointers": [
      "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-check-task\\reference.json"
    ],
    "sentence_sources": [
      {
        "sentence": 1,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-check-task\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 2,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-check-task\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 3,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-check-task\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 4,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-check-task\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 5,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-w-check-task\\reference.json"
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
    "desc": "当前Worker要验证非ASCII字段解析，ASCII样本已经通过。偏差是输入编码约定仍未知，不能把非ASCII验证写成完成。本run的host记录表明还剩8分钟和一次最多1024字节的合法读取。已授权encoding-note可以提供编码说明，但正文尚未读取。需要判断继续、一次有界补证或真实收尾本run，不能刷新原预算。",
    "material": {
      "completed": [
        {
          "text": "ASCII样本解析已通过。",
          "kind": "observed"
        }
      ],
      "remaining_work": [
        {
          "id": "W1",
          "outcome": "按真实编码约定验证非ASCII字段"
        }
      ],
      "reachability": [
        {
          "text": "编码约定未知；已获准的说明来源可在一次read内确认。",
          "kind": "observed"
        }
      ],
      "resources": [
        {
          "remaining": 8,
          "unit": "minutes",
          "scope": "当前Worker原run"
        },
        {
          "remaining": 1,
          "unit": "reads",
          "scope": "当前Worker原run"
        },
        {
          "remaining": 1024,
          "unit": "bytes",
          "scope": "这一次合法read"
        }
      ],
      "probe": {
        "unknown": "输入编码约定",
        "resource": "encoding-note",
        "expected": "明确编码；若说明缺失则保留未知",
        "limit": "一次read，至多1024字节且不超过剩余8分钟",
        "stop_when": "读取结束或原host停止/预算到界即重评"
      }
    },
    "references": {
      "W1": {
        "kind": "remaining_work",
        "scope": "本次任务",
        "content": "按真实编码约定验证非ASCII字段"
      }
    },
    "terminology": {
      "ASCII": {
        "full_name": "American Standard Code for Information Interchange",
        "meaning": "美国信息交换标准代码字符集；本例ASCII样本通过不能证明非ASCII字段可按真实编码正确解析。"
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
      "run": {
        "full_name": "task execution run",
        "meaning": "一次具体任务执行；结束本run不等于取消整个目标或项目事项。"
      },
      "补证": {
        "full_name": "补充证据",
        "meaning": "通过原授权工具读取、调查或验证补足已明确的证据缺口，不能编造验证结果或刷新原预算。"
      }
    },
    "enum_meanings": {
      "bytes": "字节数，限制本次读取数据量。",
      "continue": "继续原授权范围内的工作或补证。",
      "investigate": "在原工具范围及累计预算内对明确未知做有界补证。",
      "minutes": "分钟；本例对应原执行的剩余额度。",
      "observed": "来源报告的实际观测；本例整体仍是合成案例。",
      "reads": "允许的读取次数。",
      "terminate": "真实交付完成/未完成情况并结束本次执行，不取消整体目标。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "当前Worker条件是否足以继续，或应有界补证、如实收尾本run？ 只根据本次材料选择一个候选ID；选项是条件式判据，不是条件已成立的事实。不要输出额外原因或执行动作。",
      "criteria": {
        "continueA": "continue：下一步条件已充足时继续；未知编码不能当成已知。",
        "terminateA": "terminate：条件不足且无法在原边界内补证时，真实交付未完成并结束本run。",
        "investigateA": "investigate：按probe做一次既有授权读取后重评，不能刷新原预算。"
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
      "wire_id": "continueA",
      "choice": "continue",
      "basis_id": "continueA-basis",
      "criterion": "continue：下一步条件已充足时继续；未知编码不能当成已知。",
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
      "wire_id": "terminateA",
      "choice": "terminate",
      "basis_id": "terminateA-basis",
      "criterion": "terminate：条件不足且无法在原边界内补证时，真实交付未完成并结束本run。",
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
      "wire_id": "investigateA",
      "choice": "investigate",
      "basis_id": "investigateA-basis",
      "criterion": "investigate：按probe做一次既有授权读取后重评，不能刷新原预算。",
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
