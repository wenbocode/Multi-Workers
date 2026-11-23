# dp-auto：v0.5可理解的上下文

本例为合成规范输入。术语含义和每个被引用验收项的完整正文都进入模型；真实调用结果另列，不套旧回包。

## 字段发送规则

| 字段 | 发送规则 | 模型落点 | 用途 |
| --- | --- | --- | --- |
| desc | 发送 | state.desc | 当前目标、偏差、事件、证据和未知，<=10句/1000tokens；由原主体确认 |
| question | 发送 | state.material.question | 一个明确的现场处理问题。 |
| facts | 发送 | state.material.facts | 比较方案所需共同事实，保留相反事实。 |
| unknowns | 按需发送 | state.material.unknowns | 会改变选择的未知和影响，已在事实中说清可合并。 |
| constraints | 按需发送 | state.material.constraints | 影响本次比较的既有权限/资源/范围。 |
| options | 发送 | questions.decision_selection.criteria | 真实方案的动作、预期结果及必要成本/风险/条件；只在单选criteria中表达一次。 |
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
  "dp": "dp-auto",
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
      "label": "事项事实和范围",
      "path": "sources/S1.txt",
      "sha256": "9f1f6c430595c2a501705bc963c2b54a17f4cdcb83057ed41ea143097b2709af",
      "version": "synthetic-v1",
      "kind": "synthetic-original"
    },
    {
      "id": "S2",
      "label": "PM两个真实方案",
      "path": "sources/S2.txt",
      "sha256": "a52436783268371ce85b052e3de111d6309a8b60ecfd053cf651272a6866e35a",
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
      "retry",
      "diagnose"
    ],
    "status": "作者参考预期，禁止发给模型"
  },
  "actual_capture": {
    "request": "not-sent-v0.5",
    "response": "not-observed-v0.5"
  },
  "post_checks": "选中方案必须仍在本次2..5真实候选内、条件/范围/原预算有效；同事实重试受去重限制，选项不是执行证明。",
  "dynamic_candidates": [
    "retry",
    "diagnose"
  ],
  "freeze": {
    "file": "payload.json",
    "sha256": "de5dd966dd1a80eccfdd535034344747eb5977924850134297ed55bcc8d52f6d",
    "bytes": 2429
  },
  "desc_preparation": {
    "sentences": [
      "当前目标是在原预算内取得可信只读状态或明确失败原因。",
      "刚发生第一次只读请求超时，尚不能确定服务是否离线。",
      "当前允许一次有界重试或先读已授权健康快照，原剩余5分钟。",
      "两个方案都合法，现有事实没有给出必须优先时延或优先诊断的偏好。",
      "证据来自本次超时和当前预算范围，应在未知仍保留的情况下比较方案，不能靠历史故障编造离线结论。"
    ],
    "sentence_count": 5,
    "max_sentences": 10,
    "max_tokens": 1000,
    "estimated_tokens": 156,
    "token_count": null,
    "meter": "existing-estimator-precheck; target-model exact count not available",
    "source_note": "从v0.3合成来源归纳；QG/sign增加显式同范围fixture，非当前业务事实",
    "source_pointers": [
      "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-auto\\reference.json"
    ],
    "sentence_sources": [
      {
        "sentence": 1,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-auto\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 2,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-auto\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 3,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-auto\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 4,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-auto\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 5,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-auto\\reference.json"
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
    "desc": "当前目标是在原预算内取得可信只读状态或明确失败原因。刚发生第一次只读请求超时，尚不能确定服务是否离线。当前允许一次有界重试或先读已授权健康快照，原剩余5分钟。两个方案都合法，现有事实没有给出必须优先时延或优先诊断的偏好。证据来自本次超时和当前预算范围，应在未知仍保留的情况下比较方案，不能靠历史故障编造离线结论。",
    "material": {
      "question": "第一次只读请求超时后，应重试一次还是先读取健康快照？",
      "facts": [
        {
          "text": "第一次只读请求超时；尚未确认服务离线。",
          "kind": "observed"
        }
      ],
      "unknowns": [
        {
          "unknown": "单次超时还是服务离线",
          "affects": [
            "retry",
            "diagnose"
          ],
          "evidence_needed": "当前响应或健康快照"
        }
      ],
      "constraints": [
        {
          "rule": "原剩余5分钟，只读、一次有界重试；不刷新事项预算。",
          "status": "known"
        }
      ]
    },
    "references": {},
    "terminology": {
      "ID": {
        "full_name": "Identifier",
        "meaning": "标识符；候选ID由本次criteria给出含义，业务引用编号由references给出完整定义，不能自行猜测。"
      },
      "desc": {
        "full_name": "description",
        "meaning": "本次情境简述：目标、偏差、发生的事件、证据与未知；由原主体准备，最多10句/1000 tokens。"
      }
    },
    "enum_meanings": {
      "diagnose": "本请求准备的先读取健康事实的诊断方案。",
      "known": "对应约束或条件已由本次来源确认。",
      "observed": "来源报告的实际观测；本例整体仍是合成案例。",
      "retry": "本请求准备的一次有界重试方案。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "请选择最合适的已准备处理方案。 只根据本次材料选择一个候选ID；选项是条件式判据，不是条件已成立的事实。不要输出额外原因或执行动作。",
      "criteria": {
        "retryA": "retry：对当前瞬态超时做一次有界只读重试；预期：取得当前响应或保留失败；估计1分钟；风险：可能再次超时；条件：原只读请求、原剩余5分钟内，不重复写动作。",
        "diagnoseA": "diagnose：先读已授权服务健康快照；预期：区分服务离线与单次超时；估计2分钟；风险：快照可能不能说明单个请求；条件：只读来源仍在原范围。"
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
      "wire_id": "retryA",
      "choice": "retry",
      "basis_id": "retryA-basis",
      "criterion": "retry：对当前瞬态超时做一次有界只读重试；预期：取得当前响应或保留失败；估计1分钟；风险：可能再次超时；条件：原只读请求、原剩余5分钟内，不重复写动作。",
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
      "wire_id": "diagnoseA",
      "choice": "diagnose",
      "basis_id": "diagnoseA-basis",
      "criterion": "diagnose：先读已授权服务健康快照；预期：区分服务离线与单次超时；估计2分钟；风险：快照可能不能说明单个请求；条件：只读来源仍在原范围。",
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
