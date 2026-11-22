# dp-pm-steer：决策本到PM参考决策

真实回包 `splitA`，confidence=0.92。PM参考裁定：**参考采纳split方向：拆W1/W2并回收；复核工时未计，派发前补预算核算。**

前三段为已保存的实际输入/真实API返回；第四段为2026-11-19当前会话补写的PM参考裁定，未实际派发/写业务结果，不能冒充原生产PM记录。

机器可校验全记录：[reference-chain.json](dp-pm-steer/reference-chain.json)。原捕获版本：`v0.5-draft`；实际响应ID：`gen-PjlmXy9iW50mrLrRcV5TMeXgkdKTxvEvKlu9`。

## 一 本地决策本

完整冻结决策本如下，整体不发送。其actual_capture等字段是发送前冻结时点，不能把not-sent旧值理解为没有后来真实API调用；实际发送/返回看第三段捕获。

```json
{
  "schema": "dp-reference-v0.5-draft",
  "sample_kind": "synthetic-reference",
  "dp": "dp-pm-steer",
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
      "label": "目标与剩余标准",
      "path": "sources/S1.txt",
      "sha256": "8ebb2da87380040340844d12934b97ee9ac10a10a2d9fdcd49b4c1d6735de3f1",
      "version": "synthetic-v1",
      "kind": "synthetic-original"
    },
    {
      "id": "S2",
      "label": "当前依赖和资源观察",
      "path": "sources/S2.txt",
      "sha256": "b338f1237f5d13af689ddd83b0cad79bf813ef83f6309d486ab16ee07e14a503",
      "version": "synthetic-v1",
      "kind": "synthetic-original"
    },
    {
      "id": "S3",
      "label": "PM提案而非运行事实",
      "path": "sources/S3.txt",
      "sha256": "de35c3c4f18e4f09bb5ae2a221aa0c8f79a53cf10071b27902ff964d71451ede",
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
      "split",
      "direct-exec"
    ],
    "status": "作者参考预期，禁止发给模型"
  },
  "actual_capture": {
    "request": "not-sent-v0.5",
    "response": "not-observed-v0.5"
  },
  "post_checks": "核原目标、当前写面/依赖和剩余预算；narrow保留未完成项，split/direct随后制定计划；escalate必须有真实外部问题。",
  "freeze": {
    "file": "payload.json",
    "sha256": "39c9b2d52b4fc8f2199ee2456c2830b12af9e8df31e5070ddc066ccb43547cb6",
    "bytes": 3723
  },
  "desc_preparation": {
    "sentences": [
      "目标是补齐权限拒绝和版本冲突两类负例验证，保留原验收范围。",
      "正常路径已通过，两类负例仍是当前偏差。",
      "当前观察表明两组测试写不同文件、无先后依赖，有两个执行者和原剩余50工时分钟。",
      "预计每项实施18工时分钟、总复核4分钟，估计不是新预算。",
      "证据来自当前运行结果和资源观察，未发现外部缺权；现在需要选择组织方向，具体执行计划尚未制定。"
    ],
    "sentence_count": 5,
    "max_sentences": 10,
    "max_tokens": 1000,
    "estimated_tokens": 158,
    "token_count": null,
    "meter": "existing-estimator-precheck; target-model exact count not available",
    "source_note": "从v0.3合成来源归纳；QG/sign增加显式同范围fixture，非当前业务事实",
    "source_pointers": [
      "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-pm-steer\\reference.json"
    ],
    "sentence_sources": [
      {
        "sentence": 1,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-pm-steer\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 2,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-pm-steer\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 3,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-pm-steer\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 4,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-pm-steer\\reference.json"
        ],
        "kind": "synthetic-sourced-example"
      },
      {
        "sentence": 5,
        "sources": [
          "E:\\gitlite\\Multi-Workers\\.agenticdoc\\mw-dp-runtime-reference\\cases\\dp-pm-steer\\reference.json"
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

完整body等值排版，未删字段。字节原件：[model-input.json](dp-pm-steer/model-input.json)；SHA-256 `39c9b2d52b4fc8f2199ee2456c2830b12af9e8df31e5070ddc066ccb43547cb6`，3723字节。

```json
{
  "model": "jev-latest",
  "state": {
    "scenario": "合成案例：只评估下列材料并选择，不执行任何业务动作。",
    "desc": "目标是补齐权限拒绝和版本冲突两类负例验证，保留原验收范围。正常路径已通过，两类负例仍是当前偏差。当前观察表明两组测试写不同文件、无先后依赖，有两个执行者和原剩余50工时分钟。预计每项实施18工时分钟、总复核4分钟，估计不是新预算。证据来自当前运行结果和资源观察，未发现外部缺权；现在需要选择组织方向，具体执行计划尚未制定。",
    "material": {
      "decision_problem": "两组独立负例应并行拆分、PM直执还是先完成一组？",
      "remaining_work": [
        {
          "id": "W1",
          "outcome": "证明权限拒绝无副作用",
          "depends_on": [],
          "estimate": "估计18工时分钟，复核另计"
        },
        {
          "id": "W2",
          "outcome": "证明过期版本冲突无副作用",
          "depends_on": [],
          "estimate": "估计18工时分钟，复核另计"
        }
      ],
      "dependencies": [
        {
          "text": "W1/W2写不同测试文件，已核无先后依赖；需共享相同接口约定。",
          "kind": "observed"
        }
      ],
      "resources": [
        {
          "remaining": 50,
          "unit": "worker_minutes",
          "scope": "本事项原预算"
        },
        {
          "remaining": 2,
          "unit": "available_executors",
          "scope": "本事项原预算"
        }
      ],
      "constraints": [
        {
          "rule": "不减少两类负例；PM执行后仍需独立复核。",
          "status": "known"
        }
      ]
    },
    "references": {
      "W1": {
        "kind": "remaining_work",
        "scope": "本次任务",
        "content": "证明权限拒绝无副作用"
      },
      "W2": {
        "kind": "remaining_work",
        "scope": "本次任务",
        "content": "证明过期版本冲突无副作用"
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
      "未测": {
        "full_name": "尚未执行验证",
        "meaning": "对应验证尚未运行，不表示通过。"
      },
      "直执": {
        "full_name": "直接执行",
        "meaning": "由当前项目管理者在原权限与剩余预算内直接完成工作，必要独立复核仍保留。"
      }
    },
    "enum_meanings": {
      "available_executors": "当前可用执行者数量。",
      "direct-exec": "管理Agent在现有权限预算内直接执行。",
      "escalate": "仅对真实外部条件寻求介入。",
      "known": "对应约束或条件已由本次来源确认。",
      "narrow": "先收窄本轮执行范围，仍保留原整体目标。",
      "observed": "来源报告的实际观测；本例整体仍是合成案例。",
      "split": "将可独立并协调写面的剩余工作拆分。",
      "worker_minutes": "总工时分钟：并行执行者工时相加，区别于墙钟耗时。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "当前剩余工作应收窄本轮范围、拆分、PM直执，还是需要真实外部介入？ 只根据本次材料选择一个候选ID；选项是条件式判据，不是条件已成立的事实。不要输出额外原因或执行动作。",
      "criteria": {
        "narrowA": "narrow：先处理原目标内的一块可完成工作，明确保留其它未完成项；不缩减原验收目标。",
        "splitA": "split：将可独立且写面协调的剩余工作拆分，保留整体回收和复核。",
        "directA": "direct-exec：PM在当前权限与预算内直接完成剩余工作，并保留必要独立复核。",
        "escalateA": "escalate：仅针对真实且不可自取的外部条件介入；普通未测/服务失败不等于缺授权。"
      }
    }
  }
}
```

## 三 模型原始返回与反解

原文直接取自response字节，非预计响应。原件：[model-return.raw.json](dp-pm-steer/model-return.raw.json)。

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "splitA", "confidence": 0.92, "probabilities": {"directA": 0.06, "escalateA": 0.0, "narrowA": 0.0, "splitA": 0.94}}}, "usage": {"input_tokens": 1692, "output_tokens": 57, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-PjlmXy9iW50mrLrRcV5TMeXgkdKTxvEvKlu9"}
```

实际官方解码、本地配对和当时未执行的host检查：

```json
{
  "official_decode": {
    "valid": true,
    "error": "",
    "answers": {
      "decision_selection": {
        "value": "splitA",
        "confidence": 0.92,
        "probabilities": {
          "directA": 0.06,
          "escalateA": 0.0,
          "narrowA": 0.0,
          "splitA": 0.94
        }
      }
    }
  },
  "local_decode": {
    "valid": true,
    "wire_id": "splitA",
    "choice": "split",
    "basis_id": "splitA-basis",
    "finding_ids": [],
    "remaining_ids": [],
    "confidence": 0.92,
    "probabilities": {
      "directA": 0.06,
      "escalateA": 0.0,
      "narrowA": 0.0,
      "splitA": 0.94
    },
    "expected_match": true,
    "confidence_policy": "not-evaluated-for-business",
    "executed": false
  },
  "host_checks": "not-executed: synthetic reference, no real business owner/authorization",
  "http_status": 200,
  "usage": {
    "input_tokens": 1692,
    "output_tokens": 57,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "request_sha256": "39c9b2d52b4fc8f2199ee2456c2830b12af9e8df31e5070ddc066ccb43547cb6",
  "response_sha256": "a8c3d77c239b0ecc300c4f70bc5d9675befc99b85ab66381fa761d5719cadcd2"
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
  "model_wire_id": "splitA",
  "decoded_choice": "split",
  "basis_id": "splitA-basis",
  "finding_ids": [],
  "remaining_ids": [],
  "summary": "参考采纳split方向：拆W1/W2并回收；复核工时未计，派发前补预算核算。",
  "disposition": "adopt-direction-with-budget-recheck",
  "reasoning": [
    "来源称W1/W2写不同测试文件且已核无先后依赖，共享接口约定。",
    "两项各估18工时分钟，合计36；原50余额中复核另计，不能据此断言全部成本已覆盖。"
  ],
  "follow_up": [
    "准备W1权限拒绝无副作用和W2过期版本冲突无副作用两张任务卡，协调写面与同一接口约定。",
    "先核36工时分钟加独立复核成本不超原预算，再安排真实执行者；回收两项证据，保留整体目标。"
  ],
  "must_preserve": [
    "W1、W2均未完成的真实状态",
    "独立复核要求与原预算"
  ],
  "must_not_claim": [
    "两个Worker已派发或并行执行",
    "50工时分钟已足够含复核全部工作"
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
  "expected_wire": "splitA",
  "expected_business_choice": "split",
  "expected_basis_id": "splitA-basis",
  "expected_finding_ids": [],
  "expected_remaining_ids": [],
  "expected_pm_disposition": "adopt-direction-with-budget-recheck",
  "required_pm_facts": [
    "W1、W2均未完成的真实状态",
    "独立复核要求与原预算"
  ],
  "forbidden_pm_claims": [
    "两个Worker已派发或并行执行",
    "50工时分钟已足够含复核全部工作"
  ],
  "original_request_bytes_must_remain_identical": true,
  "historical_response_must_not_be_applied_to_changed_payload": true,
  "known_material_failures": [],
  "must_not_assume_actual_execution": true
}
```
