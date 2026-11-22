# dp-route：决策本到PM参考决策

真实回包 `route4`，confidence=0.99。PM参考裁定：**参考路由到dp-QG准备入口；组织同范围独审/AC/VC材料，不把路由当质量结论。**

前三段为已保存的实际输入/真实API返回；第四段为2026-11-19当前会话补写的PM参考裁定，未实际派发/写业务结果，不能冒充原生产PM记录。

机器可校验全记录：[reference-chain.json](dp-route/reference-chain.json)。原捕获版本：`v0.5-draft`；实际响应ID：`gen-2I3LZXb0eFzeIKNyl395vU7Cjj4ZtccAq6SA`。

## 一 本地决策本

完整冻结决策本如下，整体不发送。其actual_capture等字段是发送前冻结时点，不能把not-sent旧值理解为没有后来真实API调用；实际发送/返回看第三段捕获。

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

## 二 实际模型输入

完整body等值排版，未删字段。字节原件：[model-input.json](dp-route/model-input.json)；SHA-256 `3b40984c3beb76a30204c0bf05af1a544429aa9f13dc897fcbb973421a30c3a8`，4332字节。

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

## 三 模型原始返回与反解

原文直接取自response字节，非预计响应。原件：[model-return.raw.json](dp-route/model-return.raw.json)。

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "route4", "confidence": 0.99, "probabilities": {"route1": 0.01, "route2": 0.0, "route3": 0.0, "route4": 0.99, "route5": 0.0, "route6": 0.0, "route7": 0.0}}}, "usage": {"input_tokens": 1889, "output_tokens": 75, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-2I3LZXb0eFzeIKNyl395vU7Cjj4ZtccAq6SA"}
```

实际官方解码、本地配对和当时未执行的host检查：

```json
{
  "official_decode": {
    "valid": true,
    "error": "",
    "answers": {
      "decision_selection": {
        "value": "route4",
        "confidence": 0.99,
        "probabilities": {
          "route1": 0.01,
          "route2": 0.0,
          "route3": 0.0,
          "route4": 0.99,
          "route5": 0.0,
          "route6": 0.0,
          "route7": 0.0
        }
      }
    }
  },
  "local_decode": {
    "valid": true,
    "wire_id": "route4",
    "choice": "dp-QG",
    "basis_id": "route4-basis",
    "finding_ids": [],
    "remaining_ids": [],
    "confidence": 0.99,
    "probabilities": {
      "route1": 0.01,
      "route2": 0.0,
      "route3": 0.0,
      "route4": 0.99,
      "route5": 0.0,
      "route6": 0.0,
      "route7": 0.0
    },
    "expected_match": true,
    "confidence_policy": "not-evaluated-for-business",
    "executed": false
  },
  "host_checks": "not-executed: synthetic reference, no real business owner/authorization",
  "http_status": 200,
  "usage": {
    "input_tokens": 1889,
    "output_tokens": 75,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "request_sha256": "3b40984c3beb76a30204c0bf05af1a544429aa9f13dc897fcbb973421a30c3a8",
  "response_sha256": "d4eeb7a5788d0185610d6d1abb7287c1e718ad1dc45f1e7248ac821efd188c62"
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
  "model_wire_id": "route4",
  "decoded_choice": "dp-QG",
  "basis_id": "route4-basis",
  "finding_ids": [],
  "remaining_ids": [],
  "summary": "参考路由到dp-QG准备入口；组织同范围独审/AC/VC材料，不把路由当质量结论。",
  "disposition": "route-to-qg-preparation-in-reference",
  "reasoning": [
    "问题问当前产物能否满足已确认标准，属于正式质量审查职责。",
    "route4只选入口，不批准动作、不完成独审或QG。"
  ],
  "follow_up": [
    "原PM确认目标产物、适用AC/VC和独立review来源，再由正确主体准备QG材料。",
    "目标DP仍按自己的前提和原预算核验；不直接把route简述当完整QG输入，不代实际Worker自评。"
  ],
  "must_preserve": [
    "七入口职责",
    "目标入口自己的准备/角色/预算前提"
  ],
  "must_not_claim": [
    "QG已经通过或已经实际请求过目标入口"
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
  "expected_wire": "route4",
  "expected_business_choice": "dp-QG",
  "expected_basis_id": "route4-basis",
  "expected_finding_ids": [],
  "expected_remaining_ids": [],
  "expected_pm_disposition": "route-to-qg-preparation-in-reference",
  "required_pm_facts": [
    "七入口职责",
    "目标入口自己的准备/角色/预算前提"
  ],
  "forbidden_pm_claims": [
    "QG已经通过或已经实际请求过目标入口"
  ],
  "original_request_bytes_must_remain_identical": true,
  "historical_response_must_not_be_applied_to_changed_payload": true,
  "known_material_failures": [],
  "must_not_assume_actual_execution": true
}
```
