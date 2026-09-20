# E2E Evidence: zai-coding-cn 真实派发冒烟（VC-005 / AC-005）

- 日期: 2026-09-17
- 运行: `python -m pytest test_e2e_real.py -m e2e_real`（multi-workers 包根，env 源 ZAI_CODING_CN_API_KEY）
- 结果: **2 passed in 40.12s**（TestRealTimiDispatch + TestRealZaiDispatch）

## 派发形态（复现 PM 真实路径）

- task.md: `type: coding` + `model: zai/glm-5.3` 接口行 + prompt（"Your entire reply must be exactly: ok"）
- queue 行: `provider=timi, model=""`（PM 默认传输；路由由 task.md model: 行驱动）

## 观测证据

| 证据 | 值 |
|---|---|
| launcher-out.log | `[launcher] e2e-zai-ok: model=zai/glm-5.3 source=task`（flush 修复后可见） |
| 终态 | status=done（退出码 0 语义） |
| output.md | 存在，含 `## Summary`，回复含 ok（真实模型往返完成） |
| trace.log | `[MODEL] ... model=glm-5.3` 生命周期行 |

## 结论

zai/ 前缀 → provider zai-coding-cn → 直连 env 注入（ZAI_CODING_CN_API_KEY，无 localhost）→ `pi --provider zai-coding-cn --model glm-5.3` → open.bigmodel.cn 真实往返 → worker 正常结项。AC-005 全链路成立。

## 附注

- launcher 派发日志行补 `flush=True`（stdout 重定向到文件时块缓冲导致 e2e 期间不可见；stderr 失败路径原本已 flush）。
- 凭证走 env 源，未触 auth.json。
