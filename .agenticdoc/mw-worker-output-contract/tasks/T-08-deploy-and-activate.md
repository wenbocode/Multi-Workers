# T-08 · 部署与生效 + AC-010(b) 新产物全通过（PM 直执，不派 worker）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「mw 后台服务常驻运行」「复用 built-in extension 机制」）——源码改完不等于生效：服务跑的是构建产物（bundle/dist），每个已打开的 pi 窗口还要 `/reload`。
- **本卡由 PM 直执**（不派 worker）：`mw stop` / `mw start` 会动本机的常驻服务与所有并行窗口，属于环境级操作，只能由持窗口的 PM 在**确认无 running worker** 时执行。
- 设计落点（`design.md` §10 末段）：`mw build --install --allow-dirty` →（**仅当无 running worker**）`mw stop` + `mw start` → `mw doctor` → 每个已打开的 pi 窗口**人工 `/reload`**；记录 `mw doctor` 的 `serve code:` 与 `bundle stale:` 两行。
- AC-010(b)：本 key 交付后新跑 **≥6 个 worker**（覆盖 research / review / coding 各 ≥1），受判产物在「标题判定 + 机械段自动补齐」组合下**全部 `exit=0`**。
- 前置：T-07 done（新增红 = 0）。

## 写入允许面

- `packages/*/dist/**` 与 `.mw/**`（构建产物，非源码）
- `.agenticdoc/mw-worker-output-contract/evidence/`（部署记录、新产物扫描结果）

## 写入禁止面

- `packages/*/src/**`、`packages/*/test/**`（实现已冻结；发现问题回退到对应实现卡，不在本卡就地改）
- `.agenticdoc/_index.parallel` 之外的其它 key 目录
- 不得在存在 running worker 时执行 `mw stop` / `mw start`（会杀掉别的窗口的任务）

## 要求

1. **构建前检查**：`git status` 确认工作区没有本 key 之外的未提交改动被误打包；`allow-dirty` 只用于接纳本 key 的改动。
2. **构建**：`mw build --install --allow-dirty`。
3. **重启门禁**：`mw_status` 确认无 running worker 后才 `mw stop` + `mw start`；有 worker 在跑 ⇒ 等到空闲，不得强杀。
4. **生效核对**：`mw doctor` 必须 `serve code: fresh` + `bundle stale: False`；否则回退上一 bundle 并重跑（plan §6 的部署回退）。
5. **AC-010(b)**：新跑 ≥6 个 worker（research / review / coding 各 ≥1），逐个取 `run.json.exit` 与受判产物；要求**全部 `exit=0`**（扫描锚点：`evidence/scripts/new-worker-exit-scan.py:1`）。任一 `exit≠0` ⇒ 记录该任务的受判文件、缺失段集合与 `exit` 值，**停手上报**（这是 AC-010(b) 的直接失败，不许换语料重试掩盖）。扫描脚本可用 `evidence/scripts/new-worker-exit-scan.py`。
6. **人工步骤显式列出**：每个已打开的 pi 窗口 `/reload`；在报告里逐条写清（T-09 的 `achieved.md` 会引用）。
7. 记录本卡的原始命令与原始输出（含 `mw doctor` 两行）。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**原始命令 + 原始输出**：`mw build` 尾部、`mw stop`/`start` 输出、`mw doctor` 的 `serve code:` 与 `bundle stale:` 两行、≥6 个新 worker 的 `task_key / type / run.json.exit / 受判文件` 表格、`git diff --stat`（应只含 dist/.mw 产物）。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers
mw build --install --allow-dirty
mw doctor
python -X utf8 .agenticdoc/mw-worker-output-contract/evidence/scripts/new-worker-exit-scan.py --help
git diff --stat -- packages/*/dist .mw
```

（`mw stop` / `mw start` 在 `mw_status` 显示无 running worker 时才执行。）

## 改动历史

- 2026-10-14 plan §3 批次 C 定义；design §10 给出部署序列与生效判据。
- 服务当前 PID 记录在 `pm-state.md` §7 进程日志（历史值 151032）；重启后需更新。
