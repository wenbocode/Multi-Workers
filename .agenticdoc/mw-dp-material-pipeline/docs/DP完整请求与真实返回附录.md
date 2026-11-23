# DP完整请求与真实返回附录

配套[详细设计](DP材料准备与决策链路详细设计.md)。以下按实际捕获无删减展示全部八DP请求、原始响应、配对映射和反解。请求JSON仅等值排版；响应原文直接插入，原字节文件另有链接。认证头不记录，本轮新增API调用0次。

QG原例缺reopen候选，属于固定闭集覆盖缺口；保留它用于传输/原因配对回放，不用它证明详细设计DPA-001已完成。当前auto是新设合成前提，不能把新旧confidence当同事实对照。

## dp-w-type

来源版本：`v0.5-draft`；传输时间：`2026-11-18T07:40:39.981547+00:00`；模型：`jev-latest`；HTTP 200。

原件：[请求](captures/dp-w-type/request.json) · [响应](captures/dp-w-type/response.json) · [本地决策本](cases/dp-w-type/local-book.json) · [完整调用记录](captures/dp-w-type/result.json)。

请求2795字节，SHA-256 `30fe499cefea039fff9756ad73bd0ae5982ef437c64a16adbfd3a28c52536cd5`；响应352字节，SHA-256 `813a38c31a5f083214444f6ef6a74dae262f2bb30fd70edeb666e9e43e5c15f7`。

### 完整请求body

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

### 完整原始响应

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "codingA", "confidence": 1.0, "probabilities": {"codingA": 1.0, "researchA": 0.0, "reviewA": 0.0, "visionA": 0.0}}}, "usage": {"input_tokens": 1308, "output_tokens": 56, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-LRdB5V1LEHwXAnrEKcbCS3agGKuaTEzyTWpH"}
```

### 同版合法配对与反解

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
  "business_effects": false,
  "usage": {
    "input_tokens": 1308,
    "output_tokens": 56,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  }
}
```

准备/独审/业务授权不由接口成功证明。以上host检查保留实际未执行状态；没有执行正式派工、QG或签收。

## dp-pm-steer

来源版本：`v0.5-draft`；传输时间：`2026-11-18T07:44:12.960128+00:00`；模型：`jev-latest`；HTTP 200。

原件：[请求](captures/dp-pm-steer/request.json) · [响应](captures/dp-pm-steer/response.json) · [本地决策本](cases/dp-pm-steer/local-book.json) · [完整调用记录](captures/dp-pm-steer/result.json)。

请求3723字节，SHA-256 `39c9b2d52b4fc8f2199ee2456c2830b12af9e8df31e5070ddc066ccb43547cb6`；响应353字节，SHA-256 `a8c3d77c239b0ecc300c4f70bc5d9675befc99b85ab66381fa761d5719cadcd2`。

### 完整请求body

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

### 完整原始响应

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "splitA", "confidence": 0.92, "probabilities": {"directA": 0.06, "escalateA": 0.0, "narrowA": 0.0, "splitA": 0.94}}}, "usage": {"input_tokens": 1692, "output_tokens": 57, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-PjlmXy9iW50mrLrRcV5TMeXgkdKTxvEvKlu9"}
```

### 同版合法配对与反解

```json
{
  "pair_map": [
    {
      "wire_id": "narrowA",
      "choice": "narrow",
      "basis_id": "narrowA-basis",
      "criterion": "narrow：先处理原目标内的一块可完成工作，明确保留其它未完成项；不缩减原验收目标。",
      "material_refs": [
        "state.desc",
        "state.material",
        "state.references",
        "state.terminology"
      ],
      "finding_ids": [],
      "remaining_ids": [
        "W2"
      ]
    },
    {
      "wire_id": "splitA",
      "choice": "split",
      "basis_id": "splitA-basis",
      "criterion": "split：将可独立且写面协调的剩余工作拆分，保留整体回收和复核。",
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
      "wire_id": "directA",
      "choice": "direct-exec",
      "basis_id": "directA-basis",
      "criterion": "direct-exec：PM在当前权限与预算内直接完成剩余工作，并保留必要独立复核。",
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
      "wire_id": "escalateA",
      "choice": "escalate",
      "basis_id": "escalateA-basis",
      "criterion": "escalate：仅针对真实且不可自取的外部条件介入；普通未测/服务失败不等于缺授权。",
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
  "business_effects": false,
  "usage": {
    "input_tokens": 1692,
    "output_tokens": 57,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  }
}
```

准备/独审/业务授权不由接口成功证明。以上host检查保留实际未执行状态；没有执行正式派工、QG或签收。

## dp-w-check-task

来源版本：`v0.5-draft`；传输时间：`2026-11-18T07:44:14.348067+00:00`；模型：`jev-latest`；HTTP 200。

原件：[请求](captures/dp-w-check-task/request.json) · [响应](captures/dp-w-check-task/response.json) · [本地决策本](cases/dp-w-check-task/local-book.json) · [完整调用记录](captures/dp-w-check-task/result.json)。

请求3700字节，SHA-256 `78b07296bbb25852ade5ade79f3738c72479818a4af237048702e7e379681ef4`；响应352字节，SHA-256 `c708391ea304a7779173cae07c12091a948e61a7ec69e07ee970b9f0e42975cf`。

### 完整请求body

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

### 完整原始响应

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "investigateA", "confidence": 0.98, "probabilities": {"continueA": 0.01, "investigateA": 0.99, "terminateA": 0.0}}}, "usage": {"input_tokens": 1674, "output_tokens": 52, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-akpf0QTLvOymma39OOCF9KOl5ID31dWAmnzN"}
```

### 同版合法配对与反解

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
  "business_effects": false,
  "usage": {
    "input_tokens": 1674,
    "output_tokens": 52,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  }
}
```

准备/独审/业务授权不由接口成功证明。以上host检查保留实际未执行状态；没有执行正式派工、QG或签收。

## dp-QG

来源版本：`v0.5-draft`；传输时间：`2026-11-18T07:44:15.706262+00:00`；模型：`jev-latest`；HTTP 200。

原件：[请求](captures/dp-QG/request.json) · [响应](captures/dp-QG/response.json) · [本地决策本](cases/dp-QG/local-book.json) · [完整调用记录](captures/dp-QG/result.json)。

请求5288字节，SHA-256 `3384f2220388912607c490868eefc7758989f372906ba64d7b2576d6a83e09ae`；响应326字节，SHA-256 `a518ccee792c9a4dea13c99f0361f3d25288513c966c2329d8caf20010e45321`。

### 完整请求body

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

### 完整原始响应

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "fixB", "confidence": 0.64, "probabilities": {"fixA": 0.24, "fixB": 0.76, "passA": 0.0}}}, "usage": {"input_tokens": 2433, "output_tokens": 43, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-JyIrLOcq7kAB4XTjl30gEIBxHbSV5HCRo0No"}
```

### 同版合法配对与反解

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
  "official_decode": {
    "valid": true,
    "error": "",
    "answers": {
      "decision_selection": {
        "value": "fixB",
        "confidence": 0.64,
        "probabilities": {
          "fixA": 0.24,
          "fixB": 0.76,
          "passA": 0.0
        }
      }
    }
  },
  "local_decode": {
    "valid": true,
    "wire_id": "fixB",
    "choice": "fix",
    "basis_id": "fixB-basis",
    "finding_ids": [
      "F1",
      "F2"
    ],
    "remaining_ids": [],
    "confidence": 0.64,
    "probabilities": {
      "fixA": 0.24,
      "fixB": 0.76,
      "passA": 0.0
    },
    "expected_match": true,
    "confidence_policy": "not-evaluated-for-business",
    "executed": false
  },
  "host_checks": "not-executed: synthetic reference, no real business owner/authorization",
  "business_effects": false,
  "usage": {
    "input_tokens": 2433,
    "output_tokens": 43,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  }
}
```

准备/独审/业务授权不由接口成功证明。以上host检查保留实际未执行状态；没有执行正式派工、QG或签收。

## dp-gate-approve

来源版本：`v0.5-draft`；传输时间：`2026-11-18T07:40:44.705793+00:00`；模型：`jev-latest`；HTTP 200。

原件：[请求](captures/dp-gate-approve/request.json) · [响应](captures/dp-gate-approve/response.json) · [本地决策本](cases/dp-gate-approve/local-book.json) · [完整调用记录](captures/dp-gate-approve/result.json)。

请求3257字节，SHA-256 `9c6a7b8e72dfe75aad4e126c334abc6afccb2861a861b9d5480fcadba4080aad`；响应352字节，SHA-256 `c853de9d2fffbe27940bd038e2e40e04d8dffcbfb696d977a4def873301d2572`。

### 完整请求body

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

### 完整原始响应

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "approveA", "confidence": 1.0, "probabilities": {"approveA": 1.0, "needFixA": 0.0, "rejectA": 0.0, "steerA": 0.0}}}, "usage": {"input_tokens": 1519, "output_tokens": 56, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-wUe63FnuLJELTgvkFU0pB1Hg9ZSMV4UJEj8u"}
```

### 同版合法配对与反解

```json
{
  "pair_map": [
    {
      "wire_id": "approveA",
      "choice": "approve",
      "basis_id": "approveA-basis",
      "criterion": "approve：当前计划满足C1/C2且仍在原权限/预算内时批准该限定动作。",
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
      "wire_id": "steerA",
      "choice": "steer",
      "basis_id": "steerA-basis",
      "criterion": "steer：若问题在组织/执行安排，交PM重排，不扩大当前动作范围。",
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
      "wire_id": "needFixA",
      "choice": "need_fix",
      "basis_id": "needFixA-basis",
      "criterion": "need_fix：若安排明确但存在技术/材料缺口，交PM形成具体修复。",
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
      "wire_id": "rejectA",
      "choice": "reject",
      "basis_id": "rejectA-basis",
      "criterion": "reject：若计划不应推进则拒绝；仅允许原授权的证据整理。",
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
  "business_effects": false,
  "usage": {
    "input_tokens": 1519,
    "output_tokens": 56,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  }
}
```

准备/独审/业务授权不由接口成功证明。以上host检查保留实际未执行状态；没有执行正式派工、QG或签收。

## dp-sign-key

来源版本：`v0.5-draft`；传输时间：`2026-11-18T07:44:16.933236+00:00`；模型：`jev-latest`；HTTP 200。

原件：[请求](captures/dp-sign-key/request.json) · [响应](captures/dp-sign-key/response.json) · [本地决策本](cases/dp-sign-key/local-book.json) · [完整调用记录](captures/dp-sign-key/result.json)。

请求4436字节，SHA-256 `609ae3e2283faa901f66d9fc5e5285a44c9faee220dff601720998900975e29c`；响应341字节，SHA-256 `ddeeb5a2b562f5e486815877860dc36355e494f14bb9ec3cce173e97f380c066`。

### 完整请求body

```json
{
  "model": "jev-latest",
  "state": {
    "scenario": "合成案例：只评估下列材料并选择，不执行任何业务动作。",
    "desc": "交付目标是稳定导出，必须满足特殊字符往返一致及中断不留半成品。当前偏差是中断场景尚未执行，AC-002仍未验证。同版本独立复核确认AC-001测试有效，并指出AC-002证据缺口。本合成示例的当前同范围QG业务结论是fix，未关闭项就是中断验证，不借用其它产物的QG结果。依据为当前交付检查和QG摘要；缺口可在原权限内补取，没有真实需用户决定的外部条件。",
    "material": {
      "delivery_scope": {
        "subject": "稳定导出",
        "criteria": [
          {
            "id": "AC-001",
            "text": "特殊字符往返保持一致。"
          },
          {
            "id": "AC-002",
            "text": "中断时不留下半成品。"
          }
        ]
      },
      "requirement_results": [
        {
          "criterion_id": "AC-001",
          "status": "pass",
          "observation": "往返实测一致"
        },
        {
          "criterion_id": "AC-002",
          "status": "unknown",
          "observation": "中断场景未执行"
        }
      ],
      "verification": [
        {
          "criterion_id": "AC-001",
          "check": "当前回归实测",
          "review_status": "独立review已核断言有效"
        },
        {
          "criterion_id": "AC-002",
          "check": "未执行",
          "review_status": "独立review指出未覆盖"
        }
      ],
      "remaining_impact": [
        {
          "unfinished": "中断无半成品的验证",
          "impact": "AC-002尚无支持，不能完成交付承诺",
          "resolution_scope": "现有授权内继续补证"
        }
      ],
      "goal": "稳定导出：特殊字符往返保持一致，中断时不留下半成品。",
      "deviation": {
        "unmet_or_unverified": [
          "中断场景未执行，AC-002未验证"
        ],
        "impact": "尚不能完成全部交付承诺",
        "external_condition": "没有，现有权限内可补取"
      },
      "qg_summary": {
        "verdict": "fix",
        "review_scope": "特殊字符往返与中断恢复两项当前交付标准",
        "open_items": [
          "中断不留半成品尚未验证"
        ],
        "freshness": "与本sign示例交付对象和当前版本一致"
      }
    },
    "references": {
      "AC-001": {
        "kind": "acceptance_criterion",
        "scope": "稳定导出",
        "content": "特殊字符往返保持一致。"
      },
      "AC-002": {
        "kind": "acceptance_criterion",
        "scope": "稳定导出",
        "content": "中断时不留下半成品。"
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
      "continue": "继续原授权范围内的工作或补证。",
      "finalize": "交付具备收尾条件；仍须原签收写入者和业务检查。",
      "fix": "有明确产物缺陷或证据缺口，需修复/补证后复核。",
      "pass": "在当前检查/审核上下文满足要求；不能由局部检查扩大为整体验收。",
      "unknown": "当前事实或验证结论未知。",
      "user-confirm": "确有需要用户回答的外部条件或取舍。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "按交付承诺和验证结果，现在能收尾、应继续，还是确需用户回答具体问题？ 只根据本次材料选择一个候选ID；选项是条件式判据，不是条件已成立的事实。不要输出额外原因或执行动作。",
      "criteria": {
        "finalizeA": "finalize：全部必需标准及独审证据齐备时才收尾；未知不能当pass。",
        "continueA": "continue：补AC-002中断证据并复核，保留未完成事实。",
        "confirmA": "user-confirm：仅对真实需用户决定且不能在原权限内取得的条件提具体问题。"
      }
    }
  }
}
```

### 完整原始响应

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "continueA", "confidence": 1.0, "probabilities": {"confirmA": 0.0, "continueA": 1.0, "finalizeA": 0.0}}}, "usage": {"input_tokens": 2003, "output_tokens": 48, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-xS4Uhmo9PSieWTIIeNVc1CNQv2uLufYDxOGl"}
```

### 同版合法配对与反解

```json
{
  "pair_map": [
    {
      "wire_id": "finalizeA",
      "choice": "finalize",
      "basis_id": "finalizeA-basis",
      "criterion": "finalize：全部必需标准及独审证据齐备时才收尾；未知不能当pass。",
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
      "wire_id": "continueA",
      "choice": "continue",
      "basis_id": "continueA-basis",
      "criterion": "continue：补AC-002中断证据并复核，保留未完成事实。",
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
      "wire_id": "confirmA",
      "choice": "user-confirm",
      "basis_id": "confirmA-basis",
      "criterion": "user-confirm：仅对真实需用户决定且不能在原权限内取得的条件提具体问题。",
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
  "official_decode": {
    "valid": true,
    "error": "",
    "answers": {
      "decision_selection": {
        "value": "continueA",
        "confidence": 1.0,
        "probabilities": {
          "confirmA": 0.0,
          "continueA": 1.0,
          "finalizeA": 0.0
        }
      }
    }
  },
  "local_decode": {
    "valid": true,
    "wire_id": "continueA",
    "choice": "continue",
    "basis_id": "continueA-basis",
    "finding_ids": [],
    "remaining_ids": [],
    "confidence": 1.0,
    "probabilities": {
      "confirmA": 0.0,
      "continueA": 1.0,
      "finalizeA": 0.0
    },
    "expected_match": true,
    "confidence_policy": "not-evaluated-for-business",
    "executed": false
  },
  "host_checks": "not-executed: synthetic reference, no real business owner/authorization",
  "business_effects": false,
  "usage": {
    "input_tokens": 2003,
    "output_tokens": 48,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  }
}
```

准备/独审/业务授权不由接口成功证明。以上host检查保留实际未执行状态；没有执行正式派工、QG或签收。

## dp-auto

来源版本：`v0.6-draft`；传输时间：`2026-11-18T08:22:47.073534+00:00`；模型：`jev-latest`；HTTP 200。

原件：[请求](captures/dp-auto-current/request.json) · [响应](captures/dp-auto-current/response.json) · [本地决策本](cases/dp-auto-current/local-book.json) · [完整调用记录](captures/dp-auto-current/result.json)。

请求7081字节，SHA-256 `ffa98bc1193a7bd1e08aa2c424e1ab85d11ba7d58bd5b690e64d759b165c4225`；响应318字节，SHA-256 `d1c12bbfe2375a48e9481470241a4c9c355d151f176246d8bfb4151abe6e4690`。

### 完整请求body

```json
{
  "model": "jev-latest",
  "state": {
    "scenario": "新设合成参考场景v06；以下约定和记录不是UEPerformanceFlow/Bearing实际观察。",
    "desc": "这是新设合成场景，目标是在原期限内优先尽快取得当前只读状态，原因诊断次之。第一次请求已建立连接但等待响应体超时，没有可用状态，也未确认服务离线。允许的重试只有一次，健康快照是服务级汇总，其最新内容与实际采样时间尚未读取。本次比较先重试与先诊断两条有条件后继的有界路径，不把首步当完整恢复。原余量300秒持续扣减，每步重核并预留30秒报告，不能刷新额度。",
    "material": {
      "question": "按本次有来源的目标优先级，下一步应采用哪条有界路径？",
      "decision_scope": {
        "unit": "选择下一条有界路径及其条件后继；不是批准所有恢复动作",
        "source": "current_goal"
      },
      "objective": {
        "status": "explicit",
        "source": "current_goal",
        "success": "取得本次状态接口的当前有效响应；否则如实交付有证据的失败与未知。",
        "priorities": [
          "遵守原权限、次数、时间与停止条件",
          "优先尽快取得当前状态响应",
          "原因诊断次之，本轮不要求根因定位"
        ]
      },
      "evidence": [
        {
          "source": "timeout_record",
          "kind": "synthetic-observation",
          "timeout_stage": "连接后等待响应体",
          "failure_count": 1,
          "implication": "既不能推断服务离线，也不能保证重试成功。"
        },
        {
          "source": "health_contract",
          "kind": "synthetic-source-contract",
          "scope": "同服务汇总，非本状态接口专属",
          "sampling_period_seconds": 60,
          "freshness": "实际采样时间待读取验证，周期不等于新鲜度",
          "implication": "可增加服务健康证据；健康或不明结果都不能代替当前状态响应。"
        }
      ],
      "unknowns": [
        {
          "unknown": "当前状态请求重试是否成功",
          "affects": [
            "retryA",
            "diagnoseA"
          ],
          "evidence_needed": "唯一一次有界重试的实际响应",
          "available_before_choice": false
        },
        {
          "unknown": "最新快照内容、时间和对象适用性",
          "affects": [
            "retryA",
            "diagnoseA"
          ],
          "evidence_needed": "读取后核快照时间和同服务范围",
          "available_before_choice": false
        },
        {
          "unknown": "两种读取的实际耗时与成功概率",
          "affects": [
            "retryA",
            "diagnoseA"
          ],
          "evidence_needed": "本次执行；没有概率统计，不能把硬上限当耗时预测",
          "available_before_choice": false
        }
      ],
      "constraints": {
        "source": "limits",
        "remaining_seconds_at_preparation": 300,
        "report_reserve_seconds": 30,
        "max_status_retries": 1,
        "max_health_reads": 1,
        "retry_deadline_seconds": 60,
        "health_deadline_seconds": 120,
        "stop_conditions": [
          "当前有效状态响应取得后结束",
          "有适用且明确的当前服务离线证据则报告阻塞并结束",
          "当前路径用完则报告失败和未知，不循环",
          "下一步硬上限加30秒报告预留超过当时余量则不开始，报告剩余未知",
          "取消、授权失效或原期限到达立即停止"
        ],
        "clock_rule": "准备/决策/执行均扣同一原额度；本例无真实业务时钟，生产host须按当前账本核验。"
      }
    },
    "references": {
      "current_goal": {
        "kind": "synthetic-accepted-premise",
        "scope": "本次只读状态请求",
        "content": "在原剩余300秒内，首先遵守只读、仅一次重试及原期限，其次优先尽快取得这次状态接口的当前有效响应，最后才是原因诊断；本轮不要求根因定位。若无法取得当前响应，保留可复核失败和未知并交付。"
      },
      "timeout_record": {
        "kind": "synthetic-observation",
        "scope": "当前状态接口第一次读取",
        "content": "第一次只读请求连接已建立，在等待响应体时达到60秒上限，没有得到可用状态。当前仅这一次失败；未确认服务离线，也不知道重试成功率。"
      },
      "health_contract": {
        "kind": "synthetic-source-contract",
        "scope": "同服务只读健康快照",
        "content": "已授权读取同服务健康快照，读取硬上限120秒。来源为服务级汇总，每60秒采样，不能直接证明当前状态接口可用。最新快照尚未读取，其实际采样时间和内容未知；只有时间与对象适用且明确当前服务离线的记录才足以报告该阻塞。"
      },
      "limits": {
        "kind": "synthetic-budget-premise",
        "scope": "同一原事项",
        "content": "准备交付时原余量300秒；所有准备、决策、执行及报告持续扣减同一额度。允许状态请求最多重试一次、健康快照最多读取一次；动作各有60/120秒硬上限，预留30秒报告。进入每一步前必须重核剩余时间，余量不足不开始；取消、授权失效或原期限到达立即停止。"
      }
    },
    "terminology": {
      "ID": {
        "full_name": "Identifier",
        "meaning": "标识符；候选ID由本次criteria给出含义，业务引用编号由references给出完整定义，不能自行猜测。"
      },
      "desc": {
        "full_name": "description",
        "meaning": "本次情境简述：目标、偏差、发生的事件、证据与未知；由原主体准备，最多10句/1000 tokens。"
      },
      "host": {
        "full_name": "host runtime",
        "meaning": "执行工具、核身份/读写范围/停止/预算的宿主框架；材料文本不能替它授予权限。"
      }
    },
    "enum_meanings": {
      "explicit": "来自本例明确的合成目标约定，不是准备者推断。",
      "synthetic-observation": "合成场景所设观察，不代表生产实测。",
      "synthetic-source-contract": "合成来源的范围和能力说明。",
      "synthetic-accepted-premise": "本例新设的已确认目标前提；不是对旧例缺失偏好的补事实。",
      "synthetic-budget-premise": "本例原额度约定，无真实业务授权。"
    }
  },
  "questions": {
    "decision_selection": {
      "type": "choice",
      "instructions": "按当前目标优先级、证据局限和完整有界路径选择一个候选ID。不要假定未知概率，不把条件当已发生事实，不输出额外原因或执行动作。",
      "criteria": {
        "retryA": "先重试路径：先用唯一一次60秒上限读取当前状态。信息价值：直接得到当前有效响应，或增加一次失败证据，不能证明根因。若成功立即结束；若失败且当时余量足够120秒加30秒报告，再读一次健康快照，随后报告有证据的阻塞或失败/未知并结束。动作合计上限180秒，非耗时预测。风险：可能再次超时；快照仍可能无法解释本请求。适合优先当前响应且没有已确认离线证据的目标；根因诊断更重要或已有适用离线证据时价值下降。始终遵守公共停止条件，不再第二次重试。",
        "diagnoseA": "先诊断路径：先读一次120秒上限的同服务健康快照。信息价值：得到服务级状态、实际采样时间与适用性；健康不能证明本状态接口可用。若适用且明确当前服务离线，报告阻塞并结束；若健康、不明或读失败且当时余量足够60秒加30秒报告，再用唯一一次60秒重试，随后报告响应或失败/未知并结束。动作合计上限180秒，非耗时预测。风险：取得当前状态前增加一次读取；可能节省对离线服务的无效重试。适合原因诊断优先或快照可先确认阻塞的情形。始终遵守公共停止条件，不再第二次读取。"
      }
    }
  }
}
```

### 完整原始响应

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "retryA", "confidence": 1.0, "probabilities": {"diagnoseA": 0.0, "retryA": 1.0}}}, "usage": {"input_tokens": 2847, "output_tokens": 39, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-Q01BLmpj5sYEL9TL2tPSAqefaoYuCkv3bdyw"}
```

### 同版合法配对与反解

```json
{
  "pair_map": [
    {
      "wire_id": "retryA",
      "choice": "retry",
      "basis_id": "retryA-basis",
      "criterion": "先重试路径：先用唯一一次60秒上限读取当前状态。信息价值：直接得到当前有效响应，或增加一次失败证据，不能证明根因。若成功立即结束；若失败且当时余量足够120秒加30秒报告，再读一次健康快照，随后报告有证据的阻塞或失败/未知并结束。动作合计上限180秒，非耗时预测。风险：可能再次超时；快照仍可能无法解释本请求。适合优先当前响应且没有已确认离线证据的目标；根因诊断更重要或已有适用离线证据时价值下降。始终遵守公共停止条件，不再第二次重试。",
      "material_refs": [
        "state.material.objective",
        "state.material.evidence",
        "state.material.constraints"
      ],
      "finding_ids": [],
      "remaining_ids": []
    },
    {
      "wire_id": "diagnoseA",
      "choice": "diagnose",
      "basis_id": "diagnoseA-basis",
      "criterion": "先诊断路径：先读一次120秒上限的同服务健康快照。信息价值：得到服务级状态、实际采样时间与适用性；健康不能证明本状态接口可用。若适用且明确当前服务离线，报告阻塞并结束；若健康、不明或读失败且当时余量足够60秒加30秒报告，再用唯一一次60秒重试，随后报告响应或失败/未知并结束。动作合计上限180秒，非耗时预测。风险：取得当前状态前增加一次读取；可能节省对离线服务的无效重试。适合原因诊断优先或快照可先确认阻塞的情形。始终遵守公共停止条件，不再第二次读取。",
      "material_refs": [
        "state.material.objective",
        "state.material.evidence",
        "state.material.constraints"
      ],
      "finding_ids": [],
      "remaining_ids": []
    }
  ],
  "official_decode": {
    "valid": true,
    "error": "",
    "answers": {
      "decision_selection": {
        "value": "retryA",
        "confidence": 1.0,
        "probabilities": {
          "diagnoseA": 0.0,
          "retryA": 1.0
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
    "confidence": 1.0,
    "probabilities": {
      "diagnoseA": 0.0,
      "retryA": 1.0
    },
    "expected_match": true,
    "confidence_policy": "not-evaluated-for-business",
    "executed": false
  },
  "host_checks": {
    "status": "not-executed",
    "reason": "Synthetic fixture has no production owner, scope grant, cancellation state or current execution ledger."
  },
  "business_effects": false,
  "usage": {
    "input_tokens": 2847,
    "output_tokens": 39,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  }
}
```

准备/独审/业务授权不由接口成功证明。以上host检查保留实际未执行状态；没有执行正式派工、QG或签收。

## dp-route

来源版本：`v0.5-draft`；传输时间：`2026-11-18T07:44:17.987096+00:00`；模型：`jev-latest`；HTTP 200。

原件：[请求](captures/dp-route/request.json) · [响应](captures/dp-route/response.json) · [本地决策本](cases/dp-route/local-book.json) · [完整调用记录](captures/dp-route/result.json)。

请求4332字节，SHA-256 `3b40984c3beb76a30204c0bf05af1a544429aa9f13dc897fcbb973421a30c3a8`；响应393字节，SHA-256 `d4eeb7a5788d0185610d6d1abb7287c1e718ad1dc45f1e7248ac821efd188c62`。

### 完整请求body

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

### 完整原始响应

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "route4", "confidence": 0.99, "probabilities": {"route1": 0.01, "route2": 0.0, "route3": 0.0, "route4": 0.99, "route5": 0.0, "route6": 0.0, "route7": 0.0}}}, "usage": {"input_tokens": 1889, "output_tokens": 75, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-2I3LZXb0eFzeIKNyl395vU7Cjj4ZtccAq6SA"}
```

### 同版合法配对与反解

```json
{
  "pair_map": [
    {
      "wire_id": "route1",
      "choice": "dp-w-type",
      "basis_id": "route1-basis",
      "criterion": "dp-w-type：问题是选择派发类型时选择此入口；不代该入口裁决。",
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
      "wire_id": "route2",
      "choice": "dp-pm-steer",
      "basis_id": "route2-basis",
      "criterion": "dp-pm-steer：问题是PM组织安排时选择此入口；不代该入口裁决。",
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
      "wire_id": "route3",
      "choice": "dp-w-check-task",
      "basis_id": "route3-basis",
      "criterion": "dp-w-check-task：问题归当前Worker自身可达性时，仅交该Worker准备选择此入口；不代该入口裁决。",
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
      "wire_id": "route4",
      "choice": "dp-QG",
      "basis_id": "route4-basis",
      "criterion": "dp-QG：问题是对当前产物按标准做正式质量审查时选择此入口；不代该入口裁决。",
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
      "wire_id": "route5",
      "choice": "dp-gate-approve",
      "basis_id": "route5-basis",
      "criterion": "dp-gate-approve：问题是既有gate对具体动作准入时选择此入口；不代该入口裁决。",
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
      "wire_id": "route6",
      "choice": "dp-sign-key",
      "basis_id": "route6-basis",
      "criterion": "dp-sign-key：问题是整个key交付收尾时选择此入口；不代该入口裁决。",
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
      "wire_id": "route7",
      "choice": "dp-auto",
      "basis_id": "route7-basis",
      "criterion": "dp-auto：问题是其它明确现场方案比较时选择此入口；不代该入口裁决。",
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
  "business_effects": false,
  "usage": {
    "input_tokens": 1889,
    "output_tokens": 75,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  }
}
```

准备/独审/业务授权不由接口成功证明。以上host检查保留实际未执行状态；没有执行正式派工、QG或签收。
