# pyc 偏差记录（真实发生，未修复）

## 事实

- 受保护的 14 个 `__pycache__` 条目中，13 个与
  `evidence/implementation/s2-t05-t10-pre-dispatch-20261027/pyc-protection.json`
  记录的 SHA256 一致。
- `packages/multi-workers/__pycache__/decision.cpython-314.pyc`
  由 `e4b51f5b85198575ba723fca7f85e48a0962da44b2820f4f53f4ebea3de80677`
  变为 `b95f933d321d7cba48808279d4a9823d4c8719fe26ee26013d705439d7bcb280`。

## 成因（可核）

- 本卡执行早期有一条临时探针命令 `python -X utf8 -c ...` 读取 `decision_points.ENTRY_CHOICES`，
  该命令**未带 `-B`/`PYTHONDONTWRITEBYTECODE`**，导入链 `decision_points -> decision`
  在字节码缓存失效时刷新了 `decision.cpython-314.pyc`。此后所有 Python 调用均为
  `-B` + `PYTHONDONTWRITEBYTECODE=1`，日志见 `logs/*/meta.json` 的 env 段。
- 源文件 `decision.py` 未变：`ef9c2c68eee18bb93ad716c76c7b146279ac5f111c9f626c68a01d1c35ed691e`，
  与 `s2-t05-t10-pre-dispatch-20261027/mirror-inventory.json` 记录一致。
- 刷新后的 pyc 头 `mtime/size` 与当前 `decision.py` 匹配（flags=0，mtime=1793030138，
  size=119248），是同一源码的合法缓存，不含任何业务或配置改动。

## 未做与限制

- 没有原始 pyc 字节，无法还原到记录值；再次编译只会得到同一 `b95f...`，因此未做无意义的写回。
- 没有删除、清理或改写其他 pyc；没有触碰任何受保护源文件。
- 该偏差不改变任何断言结论，但它确实是一次write_face之外的写入，按事实报告，交由 PM 判断是否需要
  在下一轮以“基线重取”处理，而不是由本 writer 自行宣布无影响。
