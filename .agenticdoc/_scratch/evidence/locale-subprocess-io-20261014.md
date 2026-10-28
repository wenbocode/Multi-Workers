# 潜在缺陷：subprocess 文本模式缺 `encoding="utf-8"`（locale 依赖解码）

- 发现时间：2026-10-14（mw-dynamic-concurrency 收口后，由 `test_mwds_t27`/`t29` 两条红反查）
- 状态：**未修**（跨 key 面；本文件只做证据登记，供后续开 key）

## 1. 现象（可复现）

`packages/multi-workers/test_mwds_t27_service_envelope.py:473` 与
`test_mwds_t29_producer_signal.py:571`：

```python
subprocess.run([node, "--experimental-strip-types", "-e", _TS_SCRIPT],
               capture_output=True, text=True, timeout=180, env=env)
```

`text=True` 但不给 `encoding`，Python 用 **locale 首选编码**解码子进程 stdout。本机 locale 为 GBK，
而子进程（node 打印含中文的 parity 用例）输出 UTF-8 ⇒ 读取线程抛错：

```
File "subprocess.py", line 1613, in _readerthread
    buffer.append(fh.read())
UnicodeDecodeError: 'gbk' codec can't decode byte 0x87 in position 111: illegal multibyte sequence
```

后果不是断言失败，而是 `proc.stdout` 变成 `None`：

```
test_mwds_t27_service_envelope.py:475: TypeError: argument of type 'NoneType' is not a container or iterable
```

⇒ 表现为"TS 判官没返回"，极易被误判成"dist 没重建"（我第一轮就是这么错的，建后复跑证伪）。

## 2. 生产代码里的同族位置（本次扫描，`text=True` 且调用窗口内无 `encoding=`）

| 位置 | 说明 |
|------|------|
| `packages/multi-workers/mw.py:4391` | |
| `packages/multi-workers/mw.py:4742` | `_build_bundle` 的 esbuild 自检 |
| `packages/multi-workers/mw.py:4951` | `_install_framework`（跑 `install.py`） |
| `packages/multi-workers/mw_common.py:2313` | 短超时探针（`timeout=5`） |
| `packages/multi-workers/worktree_cmd.py:245` / `:262` | git 输出 |

测试侧另有 30 余处（`test_worktree_*`、`test_tree_watch`、`test_update_env`、`test_serve_doctor`、
`test_mdc_e2e.py:368` 等），其中只有输出含中文/非 ASCII 的会红。

## 3. 影响与判定

- 影响面：任何非 UTF-8 locale 的机器（本机 GBK）上，子进程输出含 CJK 时**要么抛 `UnicodeDecodeError`**
  （`text=True` 走 `_readerthread`，异常发生在读取线程里）**要么静默乱码**（若字节序列恰好能被 locale 解码）。
- 现有红：`test_mwds_t27` / `test_mwds_t29` 两条（属 `mw-dispatch-settle-gates`，DONE）。
- 最小修复（不改任何断言）：那两处各补 `encoding="utf-8"`（也可加 `errors="replace"`，但会掩盖真实编码问题，
  故只建议 `encoding="utf-8"`）。
- 更大范围：生产 5 处建议一并核查——其子进程输出若含仓库路径中的中文/非 ASCII（本仓有中文文档与
  `_scratch` 路径），同样会炸或乱码。属独立 key 的范围（可挂在"locale 安全的子进程 IO"名下）。

## 4. 判定口径（给后续 key）

- 复现命令（本机必红）：
  `cd packages/multi-workers; python -m pytest -q test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge`
- 判定：加了 `encoding="utf-8"` 之后必须**转绿**，且不得放宽任何断言（对比两侧行数据仍逐字段比对）。
- 反例守护：修复后应在 locale=GBK 与本机默认之外再验证一次（例如 `set PYTHONUTF8=1` 前后行为一致）。
