# dp-auto-original：决策本到PM参考决策

真实回包 `retryA`，confidence=0.16。PM参考裁定：**保留实际retryA回包；原材料缺优先级/完整路径，PM参考退回补材料。**

前三段为已保存的实际输入/真实API返回；第四段为2026-11-19当前会话补写的PM参考裁定，未实际派发/写业务结果，不能冒充原生产PM记录。

机器可校验全记录：[reference-chain.json](dp-auto-original/reference-chain.json)。原捕获版本：`v0.5-draft`；实际响应ID：`gen-RC8mh9EWe0GWyV2XDprAMYx27eXumtaEaX9z`。

## 一 本地决策本

完整冻结决策本如下，整体不发送。其actual_capture等字段是发送前冻结时点，不能把not-sent旧值理解为没有后来真实API调用；实际发送/返回看第三段捕获。

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

## 二 实际模型输入

完整body等值排版，未删字段。字节原件：[model-input.json](dp-auto-original/model-input.json)；SHA-256 `de5dd966dd1a80eccfdd535034344747eb5977924850134297ed55bcc8d52f6d`，2429字节。

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

## 三 模型原始返回与反解

原文直接取自response字节，非预计响应。原件：[model-return.raw.json](dp-auto-original/model-return.raw.json)。

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "retryA", "confidence": 0.16, "probabilities": {"diagnoseA": 0.42, "retryA": 0.58}}}, "usage": {"input_tokens": 1150, "output_tokens": 39, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-RC8mh9EWe0GWyV2XDprAMYx27eXumtaEaX9z"}
```

实际官方解码、本地配对和当时未执行的host检查：

```json
{
  "official_decode": {
    "valid": true,
    "error": "",
    "answers": {
      "decision_selection": {
        "value": "retryA",
        "confidence": 0.16,
        "probabilities": {
          "diagnoseA": 0.42,
          "retryA": 0.58
        }
      }
    }
  },
  "local_decode": {
    "valid": true,
    "wire_id": "retryA",
    "choice": "retry",
    "basis_id": "retryA-basis",
    "finding_ids": [],
    "remaining_ids": [],
    "confidence": 0.16,
    "probabilities": {
      "diagnoseA": 0.42,
      "retryA": 0.58
    },
    "expected_match": true,
    "confidence_policy": "not-evaluated-for-business",
    "executed": false
  },
  "host_checks": "not-executed: synthetic reference, no real business owner/authorization",
  "http_status": 200,
  "usage": {
    "input_tokens": 1150,
    "output_tokens": 39,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "request_sha256": "de5dd966dd1a80eccfdd535034344747eb5977924850134297ed55bcc8d52f6d",
  "response_sha256": "cb4146e578990d84dffb2ba0eb701385dd1e49d9d8c4f52d4185612344c70791"
}
```

## 四 PM参考决策与开发校验

以下是当前PM基于上述材料/真实回包补写的参考接回，不是历史生产执行回执。语义采纳、材料退回、后续安排和实际执行明确分开。

```json
{
  "record_kind": "current_session_pm_reference_adjudication",
  "recorded_on": "2026-11-19",
  "author": "Codex PM 当前设计整理会话",
  "historical_runtime_pm_record": null,
  "scope": "针对所列真实API回包的离线PM参考裁定；不是原生产窗口已采纳/执行的记录",
  "model_wire_id": "retryA",
  "decoded_choice": "retry",
  "basis_id": "retryA-basis",
  "finding_ids": [],
  "remaining_ids": [],
  "summary": "保留实际retryA回包；原材料缺优先级/完整路径，PM参考退回补材料。",
  "disposition": "return-material-for-goal-and-path-clarity",
  "reasoning": [
    "旧desc明确说时延/诊断偏好未给；两方案均合法且可先后执行，不能替原主体编出优先级。",
    "单次超时未证明服务离线；首步选项未给完整条件后继/停止，不能把低confidence本身当唯一退回原因。"
  ],
  "follow_up": [
    "原主体在原预算内明确本次决策单位、已确认目标取舍、超时阶段及健康来源范围/新鲜度，再准备可比较路径。",
    "若已有合法本地处置规则可按原continuity接回；不为提高confidence重复调用，不把优化版新增事实倒填旧请求。"
  ],
  "must_preserve": [
    "两个合法候选和未给偏好的未知",
    "实际confidence=0.16及原概率，不互换指标"
  ],
  "must_not_claim": [
    "旧样例已证明必须先重试",
    "优化版新增目标来自原旧事实"
  ],
  "pending_real_host_checks": [
    "原真实owner/matter/run与对象版本",
    "原权限/取消/停止和当前余额",
    "该DP必要独审/业务writer前提"
  ],
  "runtime_business_acceptance": null,
  "actual_dispatch_run_ids": [],
  "actual_business_receipt": null,
  "production_executed": false
}
```

开发预期：wire/全部原因严格按原件校验；PM文本按保留事实、禁止错误声明和参考处置校验，不要求自然语言逐字相同。已知缺陷是负例，不冻结成正确实现。

```json
{
  "record_scope": "reference-check-vectors-not-production-receipt",
  "expected_wire": "retryA",
  "expected_business_choice": "retry",
  "expected_basis_id": "retryA-basis",
  "expected_finding_ids": [],
  "expected_remaining_ids": [],
  "expected_pm_disposition": "return-material-for-goal-and-path-clarity",
  "required_pm_facts": [
    "两个合法候选和未给偏好的未知",
    "实际confidence=0.16及原概率，不互换指标"
  ],
  "forbidden_pm_claims": [
    "旧样例已证明必须先重试",
    "优化版新增目标来自原旧事实"
  ],
  "original_request_bytes_must_remain_identical": true,
  "historical_response_must_not_be_applied_to_changed_payload": true,
  "known_material_failures": [
    "missing-goal-priority-and-bounded-path"
  ],
  "must_not_assume_actual_execution": true
}
```
