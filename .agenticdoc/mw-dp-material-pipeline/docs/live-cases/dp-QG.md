# dp-QG：最终实际发送与返回

合成规范材料的真实API验证；本次请求没有生产身份或业务副作用。

响应时间：2026-11-18T07:44:16.920737+00:00；来源：中文简称覆盖修正后的实际调用。

## 实际请求body

以下来自实际Request.data，与本版payload.json逐字节一致；认证头不记录。

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

请求SHA256：3384f2220388912607c490868eefc7758989f372906ba64d7b2576d6a83e09ae；5288 UTF-8字节。

## 完整原始响应

下方仅格式化展示，response.json保留完整原字节。

```json
{
  "model": "jev-latest",
  "answers": {
    "decision_selection": {
      "type": "choice",
      "choice": "fixB",
      "confidence": 0.64,
      "probabilities": {
        "fixA": 0.24,
        "fixB": 0.76,
        "passA": 0.0
      }
    }
  },
  "usage": {
    "input_tokens": 2433,
    "output_tokens": 43,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "id": "gen-JyIrLOcq7kAB4XTjl30gEIBxHbSV5HCRo0No"
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
  "business_effects": false
}
```

原始confidence和候选概率不互换；expected_match只表示在作者参考范围，不是业务采纳。没有执行生产派工、质量产品或签收。

原始证据目录：.agenticdoc/mw-dp-terms-jev/evidence/live-final/dp-QG/；首轮完整目录另保留在evidence/live/。
