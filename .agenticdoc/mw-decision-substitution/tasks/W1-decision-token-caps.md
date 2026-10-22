# W1：`DecisionClient` 的 state 类型收紧 + token 上限

- type: coding
- owner key: mw-decision-substitution

## 上下文

用户裁定三点：
1. `state` 只应有三种形态：**结构化 JSON object / string / array of string**，且**最优是 JSON object**；
2. 函数内要加**总 64k tokens** 上限，以及**`state` + 最长单个问题 ≤ 32k tokens** 的上限；
3. 现在的 16384 B 字节闸会让 token 闸永远走不到，必须一起改。

现状：`packages/multi-workers/decision.py:735 decide()`，`DecisionState = Mapping[str, object] | Sequence[object] | str | bytes`（FIX-R 刚加），
字节闸在第 3 步（`max_state_bytes=16384`，`_emit(..., REASON_BUDGET_EXHAUSTED, ...)`），
配置解析在 `DecisionConfig.from_dict`（`:242` 起），`_encode_state` 在 `:413`。

## 要求

1. `DecisionState` 改成 `Mapping[str, object] | str | Sequence[str]`（数组元素是字符串；去掉 `bytes` 与 `Sequence[object]`），
   文档字符串写明三种形态与「最优是 JSON object」。`bytes` 不再接受：`_encode_state` 里 `bytes`/`bytearray` 分支删掉，
   改为走 `json.dumps(..., default=str)`（bytes 不是合法 JSON 值）。
2. `DecisionConfig` 新增两个字段（都要能从 `.mw/decide.json` 读，缺省值如下，非法值走现有 fail-soft 降级）：
   - `max_total_tokens: int = 65536`
   - `max_state_plus_question_tokens: int = 32768`
3. `max_state_bytes` 缺省值改为 `0`，语义 = **关闭字节闸**（`0` 表示不检查；>0 时行为与现在一致）。理由：token 闸才是用户要的闸，
   字节闸保留成可选项目级约束。
4. 新增 `_estimate_tokens(text: str) -> int`（模块级纯函数，公开给测试）：
   - 非 ASCII 字符每个按 1 token；ASCII 每 4 个字符按 1 token（向上取整）；
   - docstring 写明这是**保守估计**（CJK 1 字≈1 token，ASCII 略偏高），不是精确 tokenizer。
5. `decide()` 在第 3 步（体积闸）改成按序检查，全部走 `_emit(..., REASON_BUDGET_EXHAUSTED, Reason 细节写清数字)`：
   - `state_tokens = _estimate_tokens(state 的文本形态)`（用 `_encode_state(state).decode("utf-8")`）；
   - `question_tokens[qid] = _estimate_tokens(json.dumps(问题 spec, ensure_ascii=False))`；
   - `longest = max(question_tokens.values())`；
   - 若 `max_state_bytes > 0 and len(bytes) > max_state_bytes` → 失败（原有行为）；
   - 若 `state_tokens + longest > max_state_plus_question_tokens` → 失败，
     detail 形如 `state+longest question is 40123 tokens > max_state_plus_question_tokens=32768 (state=38000, longest=2123)`;
   - 若 `state_tokens + sum(question_tokens) > max_total_tokens` → 失败，
     detail 形如 `request is 70000 tokens > max_total_tokens=65536 (state=..., questions=...)`。
6. 测试（`packages/multi-workers/test_decide.py`）：
   - `_estimate_tokens` 三例（纯 ASCII、纯 CJK、混合）；
   - `state` 接受 dict / str / list[str] 三形态各一例；`bytes` **不再**被接受（类型层删掉后运行时行为：
     若传 bytes，`_encode_state` 走 json 序列化路径，断言不崩且不发 bytes）；
   - 超 `max_state_plus_question_tokens`：构造大 state（如 `{"blob": "字"*20000}`）→ `available=false`、`reason=budget-exhausted`、
     detail 含两个数字；
   - 超 `max_total_tokens`：多个大问题（8 题各 ~5000 tokens）→ 同上；
   - `max_state_bytes=0` 时 20KB 的 state 不再被字节闸拒（只受 token 闸约束）；
   - 原有「16384 字节」相关用例改成显式设置 `max_state_bytes=16384` 后仍生效（语义保留，缺省变了）。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py test_decide_signoff.py
python -c "import decision; print(decision._estimate_tokens('abc中文'))"
```

## 写入允许面

- `packages/multi-workers/decision.py`
- `packages/multi-workers/test_decide.py`

## 写入禁止面

- `decision_points.py`、`decision_backends.py`、`mw.py`、`decide_signoff.py`、`decide_registry.json`
- 其它 `test_*.py`、`packages/ai/**`、`packages/coding-agent/**`、`.agenticdoc/**`、`.agents/**`、`.mw/**`
- 禁止 `git` 写、`npm run check`、`npm run build`、`mw build --install`、全量 pytest、真实网络、`Set-Content`

## 交付格式

`report.md`：结论 / 落点（文件:行）/ 三条验收原文 / 缺省值变化对既有调用的影响（逐条）/ 残留。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 已知事实：dp 管线在客户端之前已把 state 截到 2000 B（`decision_points.MAX_STATE_BYTES=2000`，
  `decide_for` 第 6 步两段截断），所以新 token 闸主要保护人用面 `mw decide ask --state-file` 与将来的大 state 调用；
  机器面现在恒为 JSON object，`mw decide ask` 走 string
- 参考：`docs/decision-points.md` §1/§2（PM 刚写，描述的就是你要改的这层）
- 失败码词表见 `decision.py:80-105`，新增语义请复用 `REASON_BUDGET_EXHAUSTED`，不要造新码

## 改动历史

- 2026-10-21 建卡：用户要求 state 三形态（最优 JSON object）+ 64k/32k token 上限。
