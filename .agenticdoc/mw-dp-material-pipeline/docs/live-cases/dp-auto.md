# dp-auto：最终实际发送与返回

合成规范材料的真实API验证；本次请求没有生产身份或业务副作用。

响应时间：2026-11-18T07:40:47.877720+00:00；来源：首轮同字节请求原始记录复用，未重发。

## 实际请求body

以下来自实际Request.data，与本版payload.json逐字节一致；认证头不记录。

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

请求SHA256：de5dd966dd1a80eccfdd535034344747eb5977924850134297ed55bcc8d52f6d；2429 UTF-8字节。

## 完整原始响应

下方仅格式化展示，response.json保留完整原字节。

```json
{
  "model": "jev-latest",
  "answers": {
    "decision_selection": {
      "type": "choice",
      "choice": "retryA",
      "confidence": 0.16,
      "probabilities": {
        "diagnoseA": 0.42,
        "retryA": 0.58
      }
    }
  },
  "usage": {
    "input_tokens": 1150,
    "output_tokens": 39,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "id": "gen-RC8mh9EWe0GWyV2XDprAMYx27eXumtaEaX9z"
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
  "business_effects": false
}
```

原始confidence和候选概率不互换；expected_match只表示在作者参考范围，不是业务采纳。没有执行生产派工、质量产品或签收。

原始证据目录：.agenticdoc/mw-dp-terms-jev/evidence/live-final/dp-auto/；首轮完整目录另保留在evidence/live/。
