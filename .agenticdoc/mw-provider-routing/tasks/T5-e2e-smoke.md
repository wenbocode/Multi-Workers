# Task T5: e2e 真实冒烟

- 状态: done
- ac_refs: AC-005
- 来源: plan.md T5

## 内容

`packages/multi-workers/test_e2e_real.py` 新用例（e2e_real 标记，默认 deselect）：以 `model: zai/glm-5.3` 派发真实 pi worker（预算 ≥1024 token，thinking 模型），断言：

- worker 命令含 `--provider zai-coding-cn`
- 完成至少一次对 open.bigmodel.cn 的真实模型往返（输出非空）
- 退出码 0

凭证用 env 源（ZAI_CODING_CN_API_KEY），不触 auth.json。真实运行记录（命令+输出摘要）留底 `evidence/e2e-zai-smoke-<date>.md`。

## 测试点（VC-005）

- exit_code=0 real_roundtrip=yes

## 完成判据

- 显式 `-m e2e_real` 运行 PASS；留底文件存在
