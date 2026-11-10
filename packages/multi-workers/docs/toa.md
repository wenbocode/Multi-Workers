# TOA 混元模型

MW 的 pi 扩展通过 TokenLink 的 `https://tokenlink.woa.com/openapi/v1/chat/completions` 调用混元。密钥可在 [TokenLink 控制台](https://tokenlink.woa.com) 创建。

| pi 模型 | 输入 | 上下文 | 最大输出 |
| --- | --- | --- | --- |
| `toa/hy4` | 文本、图片 | 1024K | 64K |
| `toa/hy3` | 文本 | 256K | 128K |

两个模型都支持流式输出和工具调用。Hy4 支持关闭思考或高档，Hy3 另支持低档；输入和输出能力参考[腾讯混元调用指南](https://cloud.tencent.com/document/product/1823/132252)及[思考档位说明](https://cloud.tencent.com/document/product/1823/131208)。pi 的本地费用估算暂为 0，实际收费以 TokenLink 账单为准。

## 使用

在启动 pi 的终端设置 `TOA_API_KEY`。从仓库根目录运行以下命令可单次加载仓库的扩展并使用 Hy4。

```powershell
pi --no-extensions -e ./packages/multi-workers/dist/extensions/agent-team-loop.js --provider toa --model hy4
```

要让 PM 和新派发的 worker 都使用更新后的扩展，可按项目安装流程执行 `python packages/multi-workers/mw.py build --install`。重开 pi，在当前 worker 完成后，从同样配置了凭证的终端重启已有的 MW 服务。

```text
/model toa/hy4
/mw model set coding toa/hy3
```

第一行切换当前窗口，第二行设置后续 coding worker 的默认模型。launcher 优先使用环境变量，也可读取 pi 默认认证文件 `~/.pi/agent/auth.json` 中的 `toa.key`。模型名传给上游时为 `hy4` 或 `hy3`。

每个 HTTP 请求携带独立的 `X-Model-Request-Id`。在 pi 会话中，工具续轮复用当前提问的 `X-QA-Id` 和会话的 `X-Session-Id`；启用 prompt cache 时请求还带有 `prompt_cache_key`。
