# dp-auto：v0.5整合后的当前设计

当前采用有目标优先级、区分证据、条件后继和停止条件的合成正例；原缺证例留历史页。当前冻结结构体的schema仍标v0.6-draft，文档整合不改写实际发送版本。

## 字段发送规则


| 字段 | 来源与组装 | 是否发送 |
| --- | --- | --- |
| state.scenario | 真实场景身份；本例明确写合成参考，无业务执行 | 发送 |
| state.desc | 原PM/实际Worker吸收的目标、偏差、事件、证据与未知，最多10句/1000tokens | 发送 |
| state.material.decision_scope | 当前事项说明，明确选择下一条有界路径，未授权全部恢复动作 | 发送 |
| state.material.objective | 已确认目标的成功条件和有序优先级；未知写未知，不由准备者造偏好 | 发送 |
| state.material.evidence | 当前观测、接口/来源能力、新鲜度、范围、局限、观测/估计性质及来源引用 | 发送 |
| state.material.unknowns | 会改变排序的未知、影响、何种证据可消解及本轮是否可取 | 发送 |
| state.material.constraints | 原余量、只读、一次重试、各步硬上限、报告预留及公共停止条件 | 发送 |
| questions.decision_selection.criteria | 2..5真实路径；各路径首步、信息价值、条件后继、成本上限、风险；只表达一份 | 发送 |
| state.references | 每个引用的必要正文和适用对象；路径/hash不替内容 | 发送 |
| state.terminology / enum_meanings | 当前请求实际使用的术语、缩写、状态或代码解释 | 发送 |
| source-manifest / field-trace | 原件、版本/hash、逐字段来源/变换、发送标记；超限压缩记录遗漏和保留项 | 仅本地 |
| discriminability-report | 逐对比较、缺口、反转条件及准备状态；避免把作者推荐再塞一份题面 | 仅本地 |
| pair-map / path-ledger | 返回别名反解、路径上限机械核对；模型已从criteria看到路径含义 | 仅本地 |
| execution_plan / owner / budget_ref | 原身份、工具命令、原预算账本及真实授权检查 | 仅本地 |
| expected / 校验器过程 / request hash | 样例作者预期、编制过程及传输核验元数据 | 仅本地 |

仅把影响选择的预算余量和约束投影入模；本地budget_ref仍是实际执行依据。正文较大时由同一准备者在原预算内压缩，保留否定、失败、未知、范围与全部候选判据；仍不足则输出具体缺口，禁止截尾/只给路径。


逐字段来源见[cases/dp-auto-current/field-trace.json](cases/dp-auto-current/field-trace.json)，所有模型叶子字段send=true；下列本地决策本整体不发送。

## 本地决策本

```json
{
  "schema": "v0.6-draft",
  "sample_kind": "synthetic-reference",
  "binding": {
    "owner_ref": null,
    "matter_ref": null,
    "budget_ref": null,
    "status": "无生产身份和真实业务时钟"
  },
  "sources": [
    {
      "path": "sources/scenario.json",
      "sha256": "0abb9e91866d403545f8e504db88d71a3e2b8e98c6739c0ccba2d5d46b313c0c",
      "version": "synthetic-v06",
      "content_sent": true
    }
  ],
  "preparation": {
    "producer": "Codex本轮样例编制，未启动prepare Worker",
    "helper_tools": "proposed-not-implemented"
  },
  "desc_preparation": {
    "sentences": [
      "这是新设合成场景，目标是在原期限内优先尽快取得当前只读状态，原因诊断次之。",
      "第一次请求已建立连接但等待响应体超时，没有可用状态，也未确认服务离线。",
      "允许的重试只有一次，健康快照是服务级汇总，其最新内容与实际采样时间尚未读取。",
      "本次比较先重试与先诊断两条有条件后继的有界路径，不把首步当完整恢复。",
      "原余量300秒持续扣减，每步重核并预留30秒报告，不能刷新额度。"
    ],
    "max_sentences": 10,
    "max_tokens": 1000,
    "estimated_tokens": 173,
    "token_count": null,
    "meter": "estimate-only; target-model exact meter unavailable",
    "sentence_sources": [
      [
        "current_goal"
      ],
      [
        "timeout_record"
      ],
      [
        "health_contract",
        "limits"
      ],
      [
        "current_goal",
        "limits"
      ],
      [
        "limits"
      ]
    ]
  },
  "expected": {
    "choices": [
      "retry",
      "diagnose"
    ],
    "note": "两个均合法；不以作者排序、confidence或选中某一项作为传输通过条件。"
  },
  "dynamic_candidates": [
    "retry",
    "diagnose"
  ],
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
  "path_ledger": {
    "retryA": {
      "start": "retry",
      "steps": {
        "retry": {
          "seconds": 60,
          "resource": "retry",
          "next": [
            "health",
            "end"
          ]
        },
        "health": {
          "seconds": 120,
          "resource": "health",
          "next": [
            "end"
          ]
        }
      }
    },
    "diagnoseA": {
      "start": "health",
      "steps": {
        "health": {
          "seconds": 120,
          "resource": "health",
          "next": [
            "retry",
            "end"
          ]
        },
        "retry": {
          "seconds": 60,
          "resource": "retry",
          "next": [
            "end"
          ]
        }
      }
    }
  },
  "discriminability": {
    "status": "ready",
    "scope": "synthetic-reference-only",
    "semantic_review": "Codex作者核对，不是独立审核或通用语义证明",
    "candidate_coverage": [
      "retryA",
      "diagnoseA"
    ],
    "decision_unit": "选择下一条有界路径及其条件后继；不是批准所有恢复动作",
    "priority_source": "current_goal",
    "pairwise": [
      {
        "left": "retryA",
        "right": "diagnoseA",
        "sources": [
          "current_goal",
          "timeout_record",
          "health_contract"
        ],
        "left_better_when": "当前响应优先且未确认离线时，先重试直接接触目标输出，成功后避免额外健康读取。",
        "right_better_when": "若已确认目标改为原因诊断优先，或新增适用当前离线信号，先快照可避免无效重试。",
        "current_support": "本例响应优先，单次响应体超时未证明离线；快照为服务级汇总。",
        "reversal_conditions": [
          "来自原主体已确认的目标优先级变化",
          "同范围新证据明确当前服务离线或约束改变"
        ],
        "not_proven": "未知成功概率与实际耗时；不声称先重试在所有分支更好。"
      }
    ],
    "gaps": [],
    "path_bounds": {
      "retryA": 180,
      "diagnoseA": 180
    },
    "original_budget_continues": true,
    "source_support": {
      "current_goal": "0abb9e91866d403545f8e504db88d71a3e2b8e98c6739c0ccba2d5d46b313c0c"
    },
    "input_sha256": "ffa98bc1193a7bd1e08aa2c424e1ab85d11ba7d58bd5b690e64d759b165c4225"
  },
  "execution_plan": {
    "send": false,
    "status": "本例不制定/执行真实业务命令"
  },
  "freeze": {
    "sha256": "ffa98bc1193a7bd1e08aa2c424e1ab85d11ba7d58bd5b690e64d759b165c4225",
    "bytes": 7081,
    "file": "payload.json"
  },
  "host_checks": {
    "status": "not-executed",
    "reason": "合成样例无原生产主体；真实授权/取消/当前账本/执行不得由本例代过"
  }
}
```

## 最终模型payload

与真实发送body完全等值；原件在[captures/dp-auto-current/request.json](captures/dp-auto-current/request.json)。不把作者比较报告或预期答案发送给模型。

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

## 返回后的反解和检查

实际返回retryA→retry；confidence=1.0，概率{"diagnoseA": 0.0, "retryA": 1.0}。完整原始返回在顶层“最新API原始返回”页直接展示。

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
  "input_checks": {
    "passed": true,
    "errors": []
  },
  "host_checks": {
    "status": "not-executed",
    "reason": "Synthetic fixture has no production owner, scope grant, cancellation state or current execution ledger."
  },
  "business_effects": false
}
```

准备正例和21个反例的本地验证记录见[checks/dp-auto/local-checks.json](checks/dp-auto/local-checks.json)。生产host身份/授权/取消/执行预算检查未运行。
