# dp-w-check-task：决策本到PM参考决策

真实回包 `investigateA`，confidence=0.98。PM参考裁定：**接回investigate：由实际Worker按probe读编码说明后重评；PM不代其自评。**

前三段为已保存的实际输入/真实API返回；第四段为2026-11-19当前会话补写的PM参考裁定，未实际派发/写业务结果，不能冒充原生产PM记录。

机器可校验全记录：[reference-chain.json](dp-w-check-task/reference-chain.json)。原捕获版本：`v0.5-draft`；实际响应ID：`gen-akpf0QTLvOymma39OOCF9KOl5ID31dWAmnzN`。

## 一 本地决策本

完整冻结决策本如下，整体不发送。其actual_capture等字段是发送前冻结时点，不能把not-sent旧值理解为没有后来真实API调用；实际发送/返回看第三段捕获。

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

## 二 实际模型输入

完整body等值排版，未删字段。字节原件：[model-input.json](dp-w-check-task/model-input.json)；SHA-256 `78b07296bbb25852ade5ade79f3738c72479818a4af237048702e7e379681ef4`，3700字节。

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

## 三 模型原始返回与反解

原文直接取自response字节，非预计响应。原件：[model-return.raw.json](dp-w-check-task/model-return.raw.json)。

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "investigateA", "confidence": 0.98, "probabilities": {"continueA": 0.01, "investigateA": 0.99, "terminateA": 0.0}}}, "usage": {"input_tokens": 1674, "output_tokens": 52, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-akpf0QTLvOymma39OOCF9KOl5ID31dWAmnzN"}
```

实际官方解码、本地配对和当时未执行的host检查：

```json
{
  "official_decode": {
    "valid": true,
    "error": "",
    "answers": {
      "decision_selection": {
        "value": "investigateA",
        "confidence": 0.98,
        "probabilities": {
          "continueA": 0.01,
          "investigateA": 0.99,
          "terminateA": 0.0
        }
      }
    }
  },
  "local_decode": {
    "valid": true,
    "wire_id": "investigateA",
    "choice": "investigate",
    "basis_id": "investigateA-basis",
    "finding_ids": [],
    "remaining_ids": [],
    "confidence": 0.98,
    "probabilities": {
      "continueA": 0.01,
      "investigateA": 0.99,
      "terminateA": 0.0
    },
    "expected_match": true,
    "confidence_policy": "not-evaluated-for-business",
    "executed": false
  },
  "host_checks": "not-executed: synthetic reference, no real business owner/authorization",
  "http_status": 200,
  "usage": {
    "input_tokens": 1674,
    "output_tokens": 52,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "request_sha256": "78b07296bbb25852ade5ade79f3738c72479818a4af237048702e7e379681ef4",
  "response_sha256": "c708391ea304a7779173cae07c12091a948e61a7ec69e07ee970b9f0e42975cf"
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
  "model_wire_id": "investigateA",
  "decoded_choice": "investigate",
  "basis_id": "investigateA-basis",
  "finding_ids": [],
  "remaining_ids": [],
  "summary": "接回investigate：由实际Worker按probe读编码说明后重评；PM不代其自评。",
  "disposition": "accept-worker-direction-as-reference",
  "reasoning": [
    "ASCII样本通过不能证明非ASCII正确，当前编码约定未知。",
    "样例给出一次合法read、至多1024字节、原8分钟边界，可做有界补取。"
  ],
  "follow_up": [
    "由原实际Worker读取encoding-note；说明缺失仍保留未知，读取结束或原停止/预算到界即重评。",
    "PM接回应检查实际读结果、剩余任务与交付，不把investigate直接标为完成。"
  ],
  "must_preserve": [
    "实际Worker责任身份",
    "一次read/1024字节/原8分钟约束"
  ],
  "must_not_claim": [
    "PM已替Worker读过说明",
    "非ASCII验证已通过"
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
  "expected_wire": "investigateA",
  "expected_business_choice": "investigate",
  "expected_basis_id": "investigateA-basis",
  "expected_finding_ids": [],
  "expected_remaining_ids": [],
  "expected_pm_disposition": "accept-worker-direction-as-reference",
  "required_pm_facts": [
    "实际Worker责任身份",
    "一次read/1024字节/原8分钟约束"
  ],
  "forbidden_pm_claims": [
    "PM已替Worker读过说明",
    "非ASCII验证已通过"
  ],
  "original_request_bytes_must_remain_identical": true,
  "historical_response_must_not_be_applied_to_changed_payload": true,
  "known_material_failures": [],
  "must_not_assume_actual_execution": true
}
```
