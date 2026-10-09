# mini-spec: 让 render_task_md 签名冻结断言与提交顺序无关

- key: mw-vision-role（DONE 后的收尾修复）· 日期 2026-10-09 · 类型：trivial-fix 快车道（单断言）
- 关联: `T-08-python-render-images.md`、`evidence/runs/verify-mw-vision-role-20260926.md`（VC-009）、commit `7a864c1c7`

## 问题（客观现象）

在 `7a864c1c7` 的**干净检出**上跑 `packages/multi-workers` 触达面：

```
FAILED test_autopilot_readcap_injection.py::test_render_task_md_signature_shape
    assert extra == ["read_file_cap", "read_byte_cap", "images", "worker_timeout_min"]
AssertionError: ['read_file_cap', 'read_byte_cap', 'images']
```

T-08 把 `extra` 期望列表写成了**精确列表**，其中 `worker_timeout_min` 属并发 key `mw-autopilot-slot-capacity` 的未提交改动。于是该断言在两个提交顺序下各红一次：本 key 先提交 ⇒ 干净树上缺 `worker_timeout_min` ⇒ 红；对方先提交 ⇒ 本 key 的 `images` 未落 ⇒ 也红。即「精确列表」这种冻结写法与并发会话工作流不兼容。

## 修法（唯一改动）

`test_render_task_md_signature_shape`：保留「已移除参数必须为空」与「新增参数默认值必须为 None」两条守卫，把精确列表换成
`已知有序前缀（read_file_cap, read_byte_cap, images）相等` + `set(extra) ⊆ 已知集合（含 worker_timeout_min）`。
未知参数仍会被拒绝 ⇒ 冻结语义保留，只是不再因**已知的跨卡参数**红。

## 验收

```bash
# 干净检出（worktree）上跑，必须绿
cd packages/multi-workers && python -m pytest test_autopilot_readcap_injection.py -q
# 主工作区（含并发 key 的 worker_timeout_min）也必须绿
cd packages/multi-workers && python -m pytest test_autopilot_readcap_injection.py -q
```

期望：两条命令下 `test_render_task_md_signature_shape` 都 PASS（`test_baseline_left_end_bound` 与 `test_existing_regression_files_untouched` 的既有红不属本修复范围：前者冻结 sha 早于 HEAD，后者是 Windows `core.autocrlf=true` 下 live 字节（CRLF）与 `git show HEAD:`（LF）比对所致）。

## 边界

不改 `dispatch.py`、不改其他测试、不放宽任何其他断言；本修复只让该断言的**期望形状**与并发会话兼容。
