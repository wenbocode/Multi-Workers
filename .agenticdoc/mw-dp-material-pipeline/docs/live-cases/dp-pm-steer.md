# dp-pm-steer：最终实际发送与返回

合成规范材料的真实API验证；本次请求没有生产身份或业务副作用。

响应时间：2026-11-18T07:44:14.343567+00:00；来源：中文简称覆盖修正后的实际调用。

## 实际请求body

以下来自实际Request.data，与本版payload.json逐字节一致；认证头不记录。

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

请求SHA256：39c9b2d52b4fc8f2199ee2456c2830b12af9e8df31e5070ddc066ccb43547cb6；3723 UTF-8字节。

## 完整原始响应

下方仅格式化展示，response.json保留完整原字节。

```json
{
  "model": "jev-latest",
  "answers": {
    "decision_selection": {
      "type": "choice",
      "choice": "splitA",
      "confidence": 0.92,
      "probabilities": {
        "directA": 0.06,
        "escalateA": 0.0,
        "narrowA": 0.0,
        "splitA": 0.94
      }
    }
  },
  "usage": {
    "input_tokens": 1692,
    "output_tokens": 57,
    "cached_tokens": 0,
    "cache_write_tokens": 0
  },
  "id": "gen-PjlmXy9iW50mrLrRcV5TMeXgkdKTxvEvKlu9"
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
  "business_effects": false
}
```

原始confidence和候选概率不互换；expected_match只表示在作者参考范围，不是业务采纳。没有执行生产派工、质量产品或签收。

原始证据目录：.agenticdoc/mw-dp-terms-jev/evidence/live-final/dp-pm-steer/；首轮完整目录另保留在evidence/live/。
