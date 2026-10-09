# T-15 doctor 能力告警范围收窄到 `vision` 角色（验证期发现的偏差修复）

- key: mw-vision-role · 波 3.5（T-12 之后、T-14 之前补入） · 独占写面：`packages/multi-workers/mw_common.py`（`_doctor_issues` 的 dispatch 段）、`packages/multi-workers/test_dispatch_models.py`
- ac_refs: AC-010 · vc_refs: VC-010
- 依赖: T-12（已 done） · 预估: 20-30min

## 偏差（PM 在真实仓库上实测发现，非测试虚构）

真实运行（`python mw.py doctor --project <repo> --json`，本仓库 `.mw/dispatch.yml` 只有 main/coding/review/research，全部纯文本模型）：

```
"healthy": true, "issues": [],
"suggestions": [ ...
  "dispatch role coding uses timi/deepseek-v4.1-flash, which cannot read images (images=no) - run 'mw model set vision <vision-model>' ...",
  "dispatch role main ... ", "dispatch role research ...", "dispatch role review ..." ]
```

即 T-12 的实现对**每个** `images=no` 的角色都发一条 suggestion。问题：

1. **超出 AC-010 范围**：AC-010 只说"对 `vision` 角色给出能力判定：已配置且探针判定 `images=no` → 一条 suggestion"。`main` / `coding` / `review` / `research` 是纯文本角色，**本就不需要**看图能力（图片任务由 auto-route 改道或 `type: vision` 承担），把它们列为待修项是假阳性。
2. **建议内容误导**：文案末句"or give 'coding' an image-capable model"给的是错误处方（正解是配置 `vision` 角色 + 派 `type: vision`）。
3. **噪声**：任何纯文本配置每次 `mw doctor` 都会多出 N 条常驻告警。

## 契约（改法）

- `mw_common._doctor_issues` 里 T-12 新增的循环**只对 `role_name == "vision"` 生效**：非 `vision` 角色的 `images=no` 不发 suggestion（`dispatch.images` 的 JSON 字段仍保留全角色 —— 那是 AC-015 的可见面，不动）。
- `vision` 角色已配置且判定 `images=no` ⇒ 仍发一条 suggestion（消息含 `mw model set vision`）。
- `vision` **未配置** ⇒ 不发任何 image suggestion（现状也如此，保持）。
- 不改三态与退出码语义（suggestion/ok/skip，均 rc=0）。

## 必须同步的测试

- `test_dispatch_models.py::TestDoctorImagesCapability::test_no_is_a_suggestion_not_an_issue`：其 `_DISPATCH` 含 `coding` + `vision` 且 stub 全部返回 `no` ⇒ 改动后仍应有 1 条 suggestion（来自 vision）；补断言：**不得**出现 `dispatch role coding` 开头的 image suggestion。
- `test_three_states_keep_doctor_rc_zero`：`no` 支的 `any("mw model set vision" in s)` 仍应成立（vision 在 `_DISPATCH` 内）；确保三支 rc 仍为 0。
- 新增一条显式回归：`vision` 未配置 + 其他角色 `images=no` ⇒ `suggestions` 里**没有**任何含 `mw model set vision` 的项，且 rc=0。

## 硬约束

- 只改这两个文件里上述两段；`dispatch.images` JSON 字段、`format_doctor_text` 的 `images=` 列、`mw model show` 的列、TS 渲染均**不得**改动（T-12 已验收）。
- `mw_common.py` 有其他会话未提交改动：以工作区现值为锚，只在自己那段改，不 reformat。
- 不 commit、不 `git add`；不跑全量套件；`print(..., flush=True)` + `-s`。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_dispatch_models.py test_serve_doctor.py -q -s
python mw.py doctor --project H:/git/Multi-Workers --json | python -c "import sys,json;d=json.load(sys.stdin);print([s for s in d['summary']['suggestions'] if 'images=no' in s])"
```
末条期望：**空列表**（本仓库无 vision 角色，且其他角色不再触发）。

## 证据格式

`[VERIFY] VC-010: vision_scoped=true other_roles_silent=true rc=0`

## 非空洞对照

把收窄条件去掉（恢复全角色）⇒ 新增的"其他角色静默"断言必须变红（贴失败输出后改回）。

## 交付

两文件改动 + 三段原始输出 + `[VERIFY]` 行 + 对照结果。
