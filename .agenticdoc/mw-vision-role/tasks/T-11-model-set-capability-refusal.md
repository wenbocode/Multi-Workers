# T-11 `mw model set vision` 能力拒绝与 `--force`

- key: mw-vision-role · 波 2 · 独占写面：`packages/multi-workers/mw.py`（`cmd_model` set 段 + argparse）、`packages/multi-workers/test_dispatch_models.py`
- ac_refs: AC-001, AC-002, AC-013 · vc_refs: VC-001, VC-002, VC-013
- 依赖: T-10（探针） · 预估: 45-60min

## 目标

配置期就知道模型能不能看图：纯文本模型拒绝写入（并提供 `--force` 逃生口）；探针不可用时 fail-open。

## 契约（逐字遵守）

- argparse：`mw.py:5127-5132 model_set_p` 加 `model_set_p.add_argument("--force", action="store_true", help="...")`（同仓 `--force` 风格见 `:5190`/`:5207`）
- 校验层放**命令层**（`mw.py:3143-3152`，紧跟既有 role/prefix 校验），不要依赖 argparse 做按 role 的条件校验
- 行为表：

| 情形 | 退出码 | 副作用 |
|---|---|---|
| `role == "vision"` 且 `model_images(value) == "no"` 且无 `--force` | 非 0 | `.mw/dispatch.yml` **字节不变**；消息含 `images` 与替代建议（含 `mw model set vision`/`--force`） |
| `role == "vision"` 且判定 `"yes"` | 0 | 写入 `models.vision = value` |
| `role == "vision"` 且判定 `"unknown"` | 0 | 写入 + 一行 skip 提示（fail-open） |
| `role == "vision"` + `--force` | 0 | 跳过探针直接写入 + stdout 提示已强制 |
| `--force` 用于非 `vision` 角色 | 非 0 | 不写入（确定性报错，不做静默忽略） |
| 其他角色 | 不新增任何限制（不调探针） | 原行为 |

- AC-002 的"5 个角色"由 `DISPATCH_ROLES`（T-01）自动产生，确认 stderr/`choices` 文案含 `vision`
- **必须同步**：`test_dispatch_models.py:423-425 _model_args` 直接构造 `argparse.Namespace` → 补 `force=False`（或实现里用 `getattr(args,"force",False)` 兜底；二者取一，在 output 中写明选了哪个）

## 步骤

1. argparse 加 `--force`；命令层实现上述行为表。
2. `test_dispatch_models.py`：补 `_model_args` 的 `force`；新增用例覆盖上表 5 行（探针用 `monkeypatch.setattr(mw_common, "model_images", ...)` 注入，先例 `test_serve_doctor.py:96`）。
3. 拒绝路径断言 `read_bytes()` 前后相等（不是只看退出码）。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_dispatch_models.py -q -s
python -m pytest test_dispatch_models.py::<新增用例名> -q -s
```

## 证据格式

`[VERIFY] VC-001: vision=timi/deepseek-v4-flash-vision-exp rc=0` ·
`[VERIFY] VC-002: rc=nonzero roles=5` ·
`[VERIFY] VC-013: no_rc=1 yml_unchanged=true force_rc=0`

## 非空洞对照

去掉"no ⇒ 不写盘"的前置判断（先写后判）⇒ `yml_unchanged` 红；把 `unknown` 当 `no` ⇒ fail-open 用例红。

## 交付

`mw.py` 两处 + `test_dispatch_models.py` 用例 + 原始输出。
