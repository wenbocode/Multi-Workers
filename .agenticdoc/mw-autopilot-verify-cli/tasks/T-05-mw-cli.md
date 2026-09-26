# T-05 `mw autopilot verify` CLI（set/show/clear + 锁内 RMW + dry-run）

- AC: AC-001, AC-002, AC-004, AC-005, AC-011 · VC: VC-001, VC-002, VC-004, VC-005, VC-011 · 波次: 2（依赖 T-01/T-02/T-03）
- 写面：`packages/multi-workers/mw.py`（**仅 autopilot 段**：argparse 组 + `_cmd_*` 实现 + dispatch 表） + **新建** `test_mw_autopilot_cli.py`

## 契约（plan.md §2.2/§4.2）

```
mw autopilot verify set   --project DIR [--timeout SEC] -- ARGV...
mw autopilot verify show  --project DIR [--json]
mw autopilot verify clear --project DIR
```

- 组/子组形状照 `mw model`：`dest="autopilot_action"` / `"verify_action"` + `required=True`；`--project` **必填 option**。
- `set`：**锁内** RMW（`<root>/.mw/autopilot-config.lock`，`retries=6, base_delay=0.02`，常量可 monkeypatch）→ `{**default_config(), **existing}` 补全 → **dry-run**（`render_argv` + cwd 解析；失败 ⇒ 不落盘）→ `save_config` → 打印路径与生效值。
- `--` 之后的 token **逐字**入 `xkey_verify_cmd`；`--project` 出现在 `--` 之后 ⇒ **报错**（不得静默吞入 argv）；既有配置非法 ⇒ 拒绝写（照 `mw model set` 先例）。
- `show`：项目配置路径 + 存在性 + 四键有效值 + `origin` + **展开后 argv/cwd**；`--json` 输出机器可读。
- `clear`：只删 xkey 四键；**永不删文件**；键不存在 ⇒ `nothing configured` 且不写文件、退出码 0。
- 错误：`[mw autopilot verify <action>] Error: ...` + `return 1`；锁不可得 ⇒ 同上且不写。

## 验证

- `python -m pytest -q test_mw_autopilot_cli.py` 全绿（直调 `mw.cmd_autopilot` + Namespace；或子进程跑 `mw.py` 验 argparse）。
- 关键用例：`--` 后 flag 形 token 逐字落盘、`--project` 后置报错、同参数两次 `set` 字节不变、锁被占用返回 1 且字节不变、`clear` 不删文件、`show` origin 三态。
- `[VERIFY]` 行：argv 形状、幂等、锁拒绝、clear 语义。
