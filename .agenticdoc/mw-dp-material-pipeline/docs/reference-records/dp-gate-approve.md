# dp-gate-approve：决策本到PM参考决策

真实回包 `approveA`，confidence=1.0。PM参考裁定：**参考采纳approve该限定只读回放；保留C1/C2，不能扩成额外清理授权。**

前三段为已保存的实际输入/真实API返回；第四段为2026-11-19当前会话补写的PM参考裁定，未实际派发/写业务结果，不能冒充原生产PM记录。

机器可校验全记录：[reference-chain.json](dp-gate-approve/reference-chain.json)。原捕获版本：`v0.5-draft`；实际响应ID：`gen-wUe63FnuLJELTgvkFU0pB1Hg9ZSMV4UJEj8u`。

## 一 本地决策本

完整冻结决策本如下，整体不发送。其actual_capture等字段是发送前冻结时点，不能把not-sent旧值理解为没有后来真实API调用；实际发送/返回看第三段捕获。

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

## 二 实际模型输入

完整body等值排版，未删字段。字节原件：[model-input.json](dp-gate-approve/model-input.json)；SHA-256 `9c6a7b8e72dfe75aad4e126c334abc6afccb2861a861b9d5480fcadba4080aad`，3257字节。

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

## 三 模型原始返回与反解

原文直接取自response字节，非预计响应。原件：[model-return.raw.json](dp-gate-approve/model-return.raw.json)。

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "approveA", "confidence": 1.0, "probabilities": {"approveA": 1.0, "needFixA": 0.0, "rejectA": 0.0, "steerA": 0.0}}}, "usage": {"input_tokens": 1519, "output_tokens": 56, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-wUe63FnuLJELTgvkFU0pB1Hg9ZSMV4UJEj8u"}
```

实际官方解码、本地配对和当时未执行的host检查：

```json
{
  "official_decode": {
    "valid": true,
    "error": "",
    "answers": {
      "decision_selection": {
        "value": "approveA",
        "confidence": 1.0,
        "probabilities": {
          "approveA": 1.0,
          "needFixA": 0.0,
          "rejectA": 0.0,
          "steerA": 0.0
        }
      }
    }
  },
  "local_decode": {
    "valid": true,
    "wire_id": "approveA",
    "choice": "approve",
    "basis_id": "approveA-basis",
    "finding_ids": [],
    "remaining_ids": [],
    "confidence": 1.0,
    "probabilities": {
      "approveA": 1.0,
      "needFixA": 0.0,
      "rejectA": 0.0,
      "steerA": 0.0
    },
    "expected_match": true,
    "confidence_policy": "not-evaluated-for-business",
    "executed": false
  },
  "host_checks": "not-executed: synthetic reference, no real business owner/authorization",
  "http_status": 200,
  "usage": {
    "input_tokens": 1519,
    "output_tokens": 56,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "request_sha256": "9c6a7b8e72dfe75aad4e126c334abc6afccb2861a861b9d5480fcadba4080aad",
  "response_sha256": "c853de9d2fffbe27940bd038e2e40e04d8dffcbfb696d977a4def873301d2572"
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
  "model_wire_id": "approveA",
  "decoded_choice": "approve",
  "basis_id": "approveA-basis",
  "finding_ids": [],
  "remaining_ids": [],
  "summary": "参考采纳approve该限定只读回放；保留C1/C2，不能扩成额外清理授权。",
  "disposition": "adopt-limited-action-in-reference",
  "reasoning": [
    "C1无产品写入、C2保留完整差异均由样例观测标pass。",
    "effects给估计10分钟和原20分钟余额，仍需发送/执行前核真实余额和授权。"
  ],
  "follow_up": [
    "原主体在真实host复核通过后做一次冻结输入的隔离只读回放，并保存实际差异。",
    "只覆盖该样本；若拒绝则仅按原授权整理证据，不执行额外清理。"
  ],
  "must_preserve": [
    "限定动作/无产品写入/完整差异",
    "单份样本覆盖局限"
  ],
  "must_not_claim": [
    "动作已经执行",
    "approve创造了新权限"
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
  "expected_wire": "approveA",
  "expected_business_choice": "approve",
  "expected_basis_id": "approveA-basis",
  "expected_finding_ids": [],
  "expected_remaining_ids": [],
  "expected_pm_disposition": "adopt-limited-action-in-reference",
  "required_pm_facts": [
    "限定动作/无产品写入/完整差异",
    "单份样本覆盖局限"
  ],
  "forbidden_pm_claims": [
    "动作已经执行",
    "approve创造了新权限"
  ],
  "original_request_bytes_must_remain_identical": true,
  "historical_response_must_not_be_applied_to_changed_payload": true,
  "known_material_failures": [],
  "must_not_assume_actual_execution": true
}
```
