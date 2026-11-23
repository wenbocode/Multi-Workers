# dp-w-type：最终实际发送与返回

合成规范材料的真实API验证；本次请求没有生产身份或业务副作用。

响应时间：2026-11-18T07:40:41.353468+00:00；来源：首轮同字节请求原始记录复用，未重发。

## 实际请求body

以下来自实际Request.data，与本版payload.json逐字节一致；认证头不记录。

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

请求SHA256：30fe499cefea039fff9756ad73bd0ae5982ef437c64a16adbfd3a28c52536cd5；2795 UTF-8字节。

## 完整原始响应

下方仅格式化展示，response.json保留完整原字节。

```json
{
  "model": "jev-latest",
  "answers": {
    "decision_selection": {
      "type": "choice",
      "choice": "codingA",
      "confidence": 1.0,
      "probabilities": {
        "codingA": 1.0,
        "researchA": 0.0,
        "reviewA": 0.0,
        "visionA": 0.0
      }
    }
  },
  "usage": {
    "input_tokens": 1308,
    "output_tokens": 56,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "id": "gen-LRdB5V1LEHwXAnrEKcbCS3agGKuaTEzyTWpH"
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
  "business_effects": false
}
```

原始confidence和候选概率不互换；expected_match只表示在作者参考范围，不是业务采纳。没有执行生产派工、质量产品或签收。

原始证据目录：.agenticdoc/mw-dp-terms-jev/evidence/live-final/dp-w-type/；首轮完整目录另保留在evidence/live/。
