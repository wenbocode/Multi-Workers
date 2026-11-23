# 最新API原始返回：dp-auto当前设计

**已真实调用jev-latest，HTTP 200，返回retryA（先重试路径），confidence=1.0。** 这是2026-11-18 16:22:47北京时间的一次调用；本轮只整合记录，没有重发。

## 完整API返回原文

```json
{"model": "jev-latest", "answers": {"decision_selection": {"type": "choice", "choice": "retryA", "confidence": 1.0, "probabilities": {"diagnoseA": 0.0, "retryA": 1.0}}}, "usage": {"input_tokens": 2847, "output_tokens": 39, "cached_tokens": 0, "cache_write_tokens": 0}, "id": "gen-Q01BLmpj5sYEL9TL2tPSAqefaoYuCkv3bdyw"}
```

| 记录项 | 实际值 |
| --- | --- |
| 结果反解 | retryA → retry |
| 候选概率 | retryA=1.0；diagnoseA=0.0 |
| 请求/返回字节数 | 7081 / 318 |
| 输入/输出tokens | 2847 / 39 |
| HTTP/耗时/调用次数 | 200 / 1250毫秒 / 1 |
| 解码/本地检查 | 官方解码、当前pair-map反解通过；准备正例和21个反例通过 |
| 生产业务动作 | 未执行，真实身份/权限/取消/当前预算检查未运行 |

原字节：[请求](captures/dp-auto-current/request.json) · [响应](captures/dp-auto-current/response.json) · [完整调用及检查记录](captures/dp-auto-current/result.json)。

本例是明确新增目标优先级和来源范围的合成场景。旧例缺偏好，不在本轮重发；confidence从0.16到1.0不是同事实受控实验，不代表生产正确率。
