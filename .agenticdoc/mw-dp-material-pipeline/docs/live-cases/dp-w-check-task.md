# dp-w-check-task：最终实际发送与返回

合成规范材料的真实API验证；本次请求没有生产身份或业务副作用。

响应时间：2026-11-18T07:44:15.700764+00:00；来源：中文简称覆盖修正后的实际调用。

## 实际请求body

以下来自实际Request.data，与本版payload.json逐字节一致；认证头不记录。

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

请求SHA256：78b07296bbb25852ade5ade79f3738c72479818a4af237048702e7e379681ef4；3700 UTF-8字节。

## 完整原始响应

下方仅格式化展示，response.json保留完整原字节。

```json
{
  "model": "jev-latest",
  "answers": {
    "decision_selection": {
      "type": "choice",
      "choice": "investigateA",
      "confidence": 0.98,
      "probabilities": {
        "continueA": 0.01,
        "investigateA": 0.99,
        "terminateA": 0.0
      }
    }
  },
  "usage": {
    "input_tokens": 1674,
    "output_tokens": 52,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "id": "gen-akpf0QTLvOymma39OOCF9KOl5ID31dWAmnzN"
}
```

## 实际反解与本地检查

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
  "business_effects": false
}
```

原始confidence和候选概率不互换；expected_match只表示在作者参考范围，不是业务采纳。没有执行生产派工、质量产品或签收。

原始证据目录：.agenticdoc/mw-dp-terms-jev/evidence/live-final/dp-w-check-task/；首轮完整目录另保留在evidence/live/。
