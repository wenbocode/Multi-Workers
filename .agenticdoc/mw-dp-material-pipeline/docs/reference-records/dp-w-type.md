# dp-w-type：决策本到PM参考决策

真实回包 `codingA`，confidence=1.0。PM参考裁定：**参考采纳coding：准备代码与回归测试任务，不把类型选择当已派发。**

前三段为已保存的实际输入/真实API返回；第四段为2026-11-19当前会话补写的PM参考裁定，未实际派发/写业务结果，不能冒充原生产PM记录。

机器可校验全记录：[reference-chain.json](dp-w-type/reference-chain.json)。原捕获版本：`v0.5-draft`；实际响应ID：`gen-LRdB5V1LEHwXAnrEKcbCS3agGKuaTEzyTWpH`。

## 一 本地决策本

完整冻结决策本如下，整体不发送。其actual_capture等字段是发送前冻结时点，不能把not-sent旧值理解为没有后来真实API调用；实际发送/返回看第三段捕获。

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

## 二 实际模型输入

完整body等值排版，未删字段。字节原件：[model-input.json](dp-w-type/model-input.json)；SHA-256 `30fe499cefea039fff9756ad73bd0ae5982ef437c64a16adbfd3a28c52536cd5`，2795字节。

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

## 三 模型原始返回与反解

原文直接取自response字节，非预计响应。原件：[model-return.raw.json](dp-w-type/model-return.raw.json)。

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "codingA", "confidence": 1.0, "probabilities": {"codingA": 1.0, "researchA": 0.0, "reviewA": 0.0, "visionA": 0.0}}}, "usage": {"input_tokens": 1308, "output_tokens": 56, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-LRdB5V1LEHwXAnrEKcbCS3agGKuaTEzyTWpH"}
```

实际官方解码、本地配对和当时未执行的host检查：

```json
{
  "official_decode": {
    "valid": true,
    "error": "",
    "answers": {
      "decision_selection": {
        "value": "codingA",
        "confidence": 1.0,
        "probabilities": {
          "codingA": 1.0,
          "researchA": 0.0,
          "reviewA": 0.0,
          "visionA": 0.0
        }
      }
    }
  },
  "local_decode": {
    "valid": true,
    "wire_id": "codingA",
    "choice": "coding",
    "basis_id": "codingA-basis",
    "finding_ids": [],
    "remaining_ids": [],
    "confidence": 1.0,
    "probabilities": {
      "codingA": 1.0,
      "researchA": 0.0,
      "reviewA": 0.0,
      "visionA": 0.0
    },
    "expected_match": true,
    "confidence_policy": "not-evaluated-for-business",
    "executed": false
  },
  "host_checks": "not-executed: synthetic reference, no real business owner/authorization",
  "http_status": 200,
  "usage": {
    "input_tokens": 1308,
    "output_tokens": 56,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "request_sha256": "30fe499cefea039fff9756ad73bd0ae5982ef437c64a16adbfd3a28c52536cd5",
  "response_sha256": "813a38c31a5f083214444f6ef6a74dae262f2bb30fd70edeb666e9e43e5c15f7"
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
  "model_wire_id": "codingA",
  "decoded_choice": "coding",
  "basis_id": "codingA-basis",
  "finding_ids": [],
  "remaining_ids": [],
  "summary": "参考采纳coding：准备代码与回归测试任务，不把类型选择当已派发。",
  "disposition": "adopt-direction-in-reference",
  "reasoning": [
    "work_items要求修改转义算法并增加回归断言，交付是代码和测试。",
    "没有必须解释像素的要求，不能因文本提及格式就改派vision。"
  ],
  "follow_up": [
    "由原PM编制coding任务卡，交付导出器修复及逗号/双引号样本的往返断言。",
    "写面限定导出器和相应测试，保留格式协议不变；实际派发前核真实模型/权限/预算。"
  ],
  "must_preserve": [
    "四类候选及原约束",
    "代码与回归断言均需交付"
  ],
  "must_not_claim": [
    "Worker已经启动或测试已通过"
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
  "expected_wire": "codingA",
  "expected_business_choice": "coding",
  "expected_basis_id": "codingA-basis",
  "expected_finding_ids": [],
  "expected_remaining_ids": [],
  "expected_pm_disposition": "adopt-direction-in-reference",
  "required_pm_facts": [
    "四类候选及原约束",
    "代码与回归断言均需交付"
  ],
  "forbidden_pm_claims": [
    "Worker已经启动或测试已通过"
  ],
  "original_request_bytes_must_remain_identical": true,
  "historical_response_must_not_be_applied_to_changed_payload": true,
  "known_material_failures": [],
  "must_not_assume_actual_execution": true
}
```
