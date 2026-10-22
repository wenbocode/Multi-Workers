## ❗ 安全合规要求

📌 **核心底线：严禁数据出境，严禁面向 C 端。**

- **敏感信息管控**：基于公司合规管控要求，严禁输入内部敏感信息数据。
- **模型选型关注**：使用模型时需重点关注是否为**海外模型**，必须避免数据出境风险。
- **代码审批**：如涉及向非自部署模型输入**敏感代码**类相关能力建设，需联系合规侧审批。
- **跨境沟通**：涉及海外员工的使用场景，需主动拉起合规沟通。
- **评估负责人**：如需发起合规评估，请联系 `whanwang（王晗）`。
- **用户范围**：本平台相关能力**仅限公司内部开发使用**，严禁直接面向 C 端用户。
- **规范参考**：相关管理要求请参见[《腾讯内部 AI 编码辅助工具安全使用规范》](https://policy.woa.com/document/preview?documentId=db91fddddfc94a2a9bc1f7a9b2727595&from=iSearch)。

## 📗 基础信息：/v1/decisions

- **接口描述**：对接决策类模型（Jev）的 `decisions` 接口。将待评估的内容 `state` 与一组结构化问题 `questions` 一并提交，模型直接返回每个问题的判断结果（概率、选项或评分），适用于意图识别、工单分流、内容审核、质量打分等场景。
- **正式服（URL）**：`http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions`

与普通对话接口不同，`decisions` 返回的是**结构化判断结果**而非自由文本：每个问题按预设的类型（是否判断 / 选项分类 / 评分）返回确定性的答案与置信度，可直接用于下游的程序化决策，无需再做文本解析。

## 1. 接口说明

- **接口类型**：POST 接口
- **数据格式**：JSON 格式 Body 请求

**Headers 校验**：

- `Authorization`（必填）：请使用用户个人在平台申请的 API Key。
- `Content-Type`（必填）：`application/json`。

**Body 参数**：

| 参数                         | 参数类型                    | 是否必填 | 说明                    | 备注                                                                 |
| -------------------------- | ----------------------- | ---- | --------------------- | ------------------------------------------------------------------ |
| `model`                    | string                  | 是    | 模型名称                  | 平台模型库查看模型名称，需为 Decisions 类模型，如 `jev-latest`                        |
| `state`                    | string / object / array | 是    | 待评估的内容                | 纯文本可直接传字符串；对话记录、数据记录或应用状态等适合传对象或数组                                 |
| `questions`                | map[string, Question]   | 是    | 待回答的问题集合，键名由调用方自行定义   | 该键名不会发送给底层模型，也不参与推理，仅用于在响应中对应取回答案                                  |
| `questions[].type`         | string                  | 是    | 问题类型                  | 可选值：`noul`（二元判断，返回"是"的可能性）、`choice`（从给定选项中选择一项）、`score`（按有序评分标准打分） |
| `questions[].instructions` | string / object / array | 是    | 问题的描述文字               | 支持传对象或数组，以便把问题本身与参考数据分离，并在文字中以反引号引用这些字段                            |
| `questions[].criteria`     | object / map / array    | 否    | 问题的评判标准，格式随 `type` 变化 | `noul` 时可选，`choice` 与 `score` 时必填，见下方《criteria 取值形态》               |

**`criteria` 取值形态**：

| 问题类型     | 参数类型                | 是否必填 | 说明                                                                    | 示例                                      |
| -------- | ------------------- | ---- | --------------------------------------------------------------------- | --------------------------------------- |
| `noul`   | object              | 否    | 包含 `true` 与 `false` 两个键，每个键为 string/object/array，分别说明结果取值偏高或偏低各代表什么含义 | `{"true": "明确有时效性", "false": "未表达紧急性"}` |
| `choice` | map[string, string] | 是    | 选项与其判定说明的映射，无需补充说明时可将值置为 `null`                                       | 最多支持 255 个选项                            |
| `score`  | array[string]       | 是    | 有序的评分档位说明，从低到高排列                                                      | 至少 2 个档位，最多支持 10 个                      |

**使用提示**：

- 单次请求可同时提交多个问题，模型在一次推理中统一评估，相比逐题调用更省成本与时延；
- `state` 与 `questions` 均按输入 token 计费，答案部分按输出 token 计费，用量见响应 `usage` 字段。

## 2. Curl 调用示例

**Noul（是否判断）**：

```bash
curl -X POST 'http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: xxxxx' \
  -d '{
    "model": "jev-latest",
    "state": "求助！我的提现已经失败3天了。",
    "questions": {
        "is_urgent": {
            "type": "noul",
            "instructions": "这段话是否传达了紧急性？",
            "criteria": {
                "true": "明确有时效性要求",
                "false": "未表达紧急性"
            }
        }
    }
}'
```

**Choice（选项分类）**：

```bash
curl -X POST 'http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: xxxxx' \
  -d '{
    "model": "jev-latest",
    "state": "求助！我的提现已经失败3天了。",
    "questions": {
        "department": {
            "type": "choice",
            "instructions": "该工单应该由哪个团队处理？",
            "criteria": {
                "billing": "支付、开票、退款相关",
                "technical": "缺陷、故障、集成相关",
                "sales": "定价、升级、新账号相关"
            }
        }
    }
}'
```

**Score（评分）+ 多问题组合**：

```bash
curl -X POST 'http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: xxxxx' \
  -d '{
    "model": "jev-latest",
    "state": "求助！我的提现已经失败3天了。",
    "questions": {
        "frustration": {
            "type": "score",
            "instructions": "客户的情绪激烈程度如何？",
            "criteria": ["平静", "不满", "非常愤怒"]
        },
        "is_urgent": {
            "type": "noul",
            "instructions": "这段话是否传达了紧急性？"
        }
    }
}'
```

## 3. Python 调用示例

**requests 格式请求**：

```python
import json
import requests

url = "http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions"  # 正式服：替换域名 api.timiai.woa.com

data_dict = {
    'model': 'jev-latest',  # 模型对应平台库可查询到的模型名称
    'state': '求助！我的提现已经失败3天了。',
    'questions': {
        'department': {
            'type': 'choice',
            'instructions': '该工单应该由哪个团队处理？',
            'criteria': {
                'billing': '支付、开票、退款相关',
                'technical': '缺陷、故障、集成相关',
                'sales': '定价、升级、新账号相关'
            }
        }
    }
}

headers = {
    'Content-Type': 'application/json',
    'Authorization': 'xxxxx'  # 对应平台个人API Key, 且确保API key有对应模型调用权限
}

response = requests.post(url, headers=headers, data=json.dumps(data_dict))

# 判断是否异常
if response.status_code != 200:
    # 异常处理
    print(response.json())
    exit()

result = response.json()
answer = result["answers"]["department"]
print(answer["choice"], answer["confidence"])
```

**封装为可复用工单分流函数**：

```python
import json
import requests

URL = "http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions"
HEADERS = {
    'Content-Type': 'application/json',
    'Authorization': 'xxxxx'
}


def triage_ticket(content, departments, model='jev-latest'):
    """departments: dict，键为部门标识，值为部门职责说明"""
    data_dict = {
        'model': model,
        'state': content,
        'questions': {
            'department': {
                'type': 'choice',
                'instructions': '该工单应该由哪个团队处理？',
                'criteria': departments
            }
        }
    }
    resp = requests.post(URL, headers=HEADERS, data=json.dumps(data_dict))
    if resp.status_code != 200:
        print(resp.json())
        raise RuntimeError("decisions request failed")

    answer = resp.json()["answers"]["department"]
    return {
        "department": answer["choice"],
        "confidence": answer["confidence"],
        "probabilities": answer["probabilities"]
    }


if __name__ == "__main__":
    result = triage_ticket(
        "求助！我的提现已经失败3天了。",
        {
            "billing": "支付、开票、退款相关",
            "technical": "缺陷、故障、集成相关",
            "sales": "定价、升级、新账号相关"
        }
    )
    print(result["department"], result["confidence"])
```

## 4. 响应说明

**成功响应示例（Noul answer）**：

```json
{
    "model": "jev-latest",
    "answers": {
        "is_urgent": {
            "type": "noul",
            "noul": 0.95
        }
    },
    "usage": {
        "input_tokens": 307,
        "output_tokens": 20
    }
}
```

**成功响应示例（Choice answer）**：

```json
{
    "model": "jev-latest",
    "answers": {
        "department": {
            "type": "choice",
            "choice": "billing",
            "probabilities": {
                "billing": 0.88,
                "technical": 0.12,
                "sales": 0
            },
            "confidence": 0.81
        }
    },
    "usage": {
        "input_tokens": 318,
        "output_tokens": 34
    }
}
```

**成功响应示例（Score answer）**：

```json
{
    "model": "jev-latest",
    "answers": {
        "frustration": {
            "type": "score",
            "score": 1.05,
            "legend": {
                "0": "平静",
                "1": "不满",
                "2": "非常愤怒"
            },
            "probabilities": {
                "0": 0,
                "1": 0.95,
                "2": 0.05
            },
            "confidence": 0.92
        }
    },
    "usage": {
        "input_tokens": 304,
        "output_tokens": 18
    }
}
```

**响应字段说明**：

| 字段                        | 类型                  | 说明                                                     |
| ------------------------- | ------------------- | ------------------------------------------------------ |
| `model`                   | string              | 实际响应的模型名称                                              |
| `answers`                 | map[string, Answer] | 答案集合，键名与请求 `questions` 的键名一一对应                         |
| `answers[].type`          | string              | 问题类型，与请求一致：`noul` / `choice` / `score`                 |
| `answers[].noul`          | number              | 仅 `noul` 类型返回，结果为"是"的可能性，取值 0 ~ 1                      |
| `answers[].choice`        | string              | 仅 `choice` 类型返回，选中的选项键名                                |
| `answers[].score`         | number              | 仅 `score` 类型返回，评分值，取值范围对应 `legend` 档位下标（可为小数，表示介于两档之间） |
| `answers[].legend`        | object              | 仅 `score` 类型返回，档位下标到档位说明的映射                            |
| `answers[].probabilities` | object              | `choice` / `score` 类型返回，各选项/档位的概率分布                    |
| `answers[].confidence`    | number              | `choice` / `score` 类型返回，答案置信度                          |
| `usage.input_tokens`      | integer             | 输入消耗的 token 数                                          |
| `usage.output_tokens`     | integer             | 输出消耗的 token 数                                          |

## 5. 注意事项

- **模型名以平台模型库为准**：文档示例中的 `jev-latest` 仅为占位，实际调用请填写平台模型库中已部署的 Decisions 类模型名称，并确认所用 API Key 具备该模型的调用权限。
- **Decisions 模型不可用于对话接口**：该类模型仅能在本接口调用，传入 `chat/completions` 或 `responses` 接口会报错。
- **该接口不支持流式**：一次性返回全部答案，不存在 `stream` 参数（代理侧会强制忽略该字段）。
- **键名仅用于取回答案**：`questions` 的键名由调用方自定义，不参与模型推理，响应用同一键名返回答案，建议使用有业务含义的标识便于映射。
- **`criteria` 必填规则**：`choice` 与 `score` 类型必须提供 `criteria`，否则请求会报错；`noul` 可选，但补充评判标准通常能提升判断稳定性。
- **结果可程序化消费**：返回值为结构化字段（选项键名 / 评分值 / 概率），可直接做阈值判断或路由决策，无需正则解析文本；建议结合 `confidence` 设置人工兜底阈值。
- **合规提示**：严禁将内部敏感数据、密钥、用户个人信息作为 `state` 或 `questions` 传入非自部署模型；涉及海外模型时须评估数据出境风险。
- **鉴权失败排查**：返回非 200 时优先检查 `Authorization` 是否为平台个人 API Key、Key 是否具备对应模型权限、`model` 名称是否与平台模型库一致。
