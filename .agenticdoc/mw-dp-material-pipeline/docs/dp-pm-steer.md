# dp-pm-steer：v0.5可理解的上下文

本例为合成规范输入。术语含义和每个被引用验收项的完整正文都进入模型；真实调用结果另列，不套旧回包。

## 字段发送规则

| 字段 | 发送规则 | 模型落点 | 用途 |
| --- | --- | --- | --- |
| desc | 发送 | state.desc | 当前目标、偏差、事件、证据和未知，<=10句/1000tokens；由原主体确认 |
| decision_problem | 发送 | state.material.decision_problem | 说明现在为何需要调整安排；不预选split。 |
| remaining_work | 发送 | state.material.remaining_work | 还需实现或证明的结果；估计明确标估计。 |
| dependencies | 按需发送 | state.material.dependencies | 会改变并行/先后判断的接口依赖和写面冲突。 |
| resources | 按需发送 | state.material.resources | 比较方式需要时提供host当前可用执行者/原余额，不用旧额度。 |
| constraints | 按需发送 | state.material.constraints | 影响安排的范围、权限和复核要求。 |
| model | 发送 | model | 调用参数；由实际timi配置选择jev-latest，不是业务事实。 |
| scenario | 发送 | state.scenario | 本包合成验证身份；真实业务请求以真实场景替换，不伪造授权。 |
| evidence_sources | 按需发送 | state.evidence_sources | 需要原文才能理解/复核时发必要正文和限制；已在material达意则不重复；路径/hash不替正文。 |
| decision_selection.type/instructions/criteria | 发送 | questions.decision_selection | 一个单选题，完整合法候选及可读判据；依据在选项内表达一次。 |
| references | 发送 | state.references | 当前引用项完整正文/含义和适用范围；AC/VC/发现/工作项/入口在请求内可解 |
| terminology | 发送 | state.terminology | desc、材料、题干、选项及业务字段实际使用的缩写/术语解释 |
| enum_meanings | 按需发送 | state.enum_meanings | 本请求使用的状态/业务选项代码和资源单位含义 |
| 来源路径/hash/原始权限/定义提取过程/配对映射/请求身份 | 仅本地 | 不发送 | 不能用本地有定义冒充模型已收到 |

## 本地决策本

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

## 最终模型payload

完整body如下；references既解释编号对应的具体内容，terminology解释缩写和术语，两层都必须在场。只包含本次所需定义。

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

## 返回后的反解和检查

原始回包→本次别名表反解→核全部原因/剩余项→置信和概率分别保留→原host分支核验；选择不等于执行。真实本次返回单独回放。

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
  "executed": false,
  "checks": [
    "一个完整choice回答",
    "本次候选和引用定义一致",
    "当前来源/独审/权限/预算/停止边界",
    "QG逐AC/VC状态；sign当前同范围QG",
    "保留低置信，不为抬高数字重发"
  ]
}
```
