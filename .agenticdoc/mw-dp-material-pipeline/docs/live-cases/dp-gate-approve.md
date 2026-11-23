# dp-gate-approve：最终实际发送与返回

合成规范材料的真实API验证；本次请求没有生产身份或业务副作用。

响应时间：2026-11-18T07:40:45.591340+00:00；来源：首轮同字节请求原始记录复用，未重发。

## 实际请求body

以下来自实际Request.data，与本版payload.json逐字节一致；认证头不记录。

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

请求SHA256：9c6a7b8e72dfe75aad4e126c334abc6afccb2861a861b9d5480fcadba4080aad；3257 UTF-8字节。

## 完整原始响应

下方仅格式化展示，response.json保留完整原字节。

```json
{
  "model": "jev-latest",
  "answers": {
    "decision_selection": {
      "type": "choice",
      "choice": "approveA",
      "confidence": 1.0,
      "probabilities": {
        "approveA": 1.0,
        "needFixA": 0.0,
        "rejectA": 0.0,
        "steerA": 0.0
      }
    }
  },
  "usage": {
    "input_tokens": 1519,
    "output_tokens": 56,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "id": "gen-wUe63FnuLJELTgvkFU0pB1Hg9ZSMV4UJEj8u"
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
  "business_effects": false
}
```

原始confidence和候选概率不互换；expected_match只表示在作者参考范围，不是业务采纳。没有执行生产派工、质量产品或签收。

原始证据目录：.agenticdoc/mw-dp-terms-jev/evidence/live-final/dp-gate-approve/；首轮完整目录另保留在evidence/live/。
