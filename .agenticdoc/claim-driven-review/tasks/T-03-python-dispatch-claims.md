# T-03: Python 派发层 —— conductor 的 claims 解析与 caps 推导（coding）

- Key: claim-driven-review
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「文件驱动的去中心化协调」「不引入中心化调度器」）。
- 设计依据：`design.md` §3.2、§4、D-007。
- 上游实测：
  - `_read_scope_caps` 当前签名与项目层语义：`packages/multi-workers/autopilot/dispatch.py:224-270`（缺键返回 `(None, None)` → 不写 caps 行，VC-007/VC-008 字节不变）。
  - 调用顺序缺陷：`dispatch.py:1492` 现在在 `:1495` 的 `dispatch_card(...)` **之前**，因此拿不到当次卡的预算（`evidence/research/spec-rq2-seams-20261020.md` §3.3/§3.4）。
  - 渲染面已就绪：`render_task_md` 已在签名（`:860-861`）与渲染处（`:980-983`）支持 `read_file_cap`/`read_byte_cap`，**不需要改**。
  - synthesized 卡路径：`dispatch.py:777`（无卡文件 → `dispatch_card` 返回 `None`）。
- 预算常数（RQ-1 §5，不得自行改数）：`callCap=30`、`claimByteCap=65536`、`byteCapMax=393216`、`perClaim=6`、manual 记 2、`Σ预算 ≤ 40`。

## 要求

1. `dispatch_card`（`:569-601`）在返回 dict 里加 `"claims": [...]`（用与 TS 同构的解析：七列表、别名、全角、fence 跳过；解析失败进 `errors` 不抛异常）。该函数已读全文，是唯一卡文本来源——补一次即可，不要新增读文件。
2. 在 `dispatch.py` 定义四个模块级常量（T-06 平价锁会逐字对比）：`CLAIM_TYPES`、`UNVERIFIED_REASONS`、`CLAIM_GATE_DEFAULT = "advisory"`、`CLAIM_BUDGET`（与 TS 同名同值同序）。
3. `_read_scope_caps(project_root, claims=None)`：
   - `claims` 为 `None` 或空 → 保持现有行为（项目层配置或 `(None, None)`）。
   - 否则：`file_cap = min(30, pair_sum)`（`pair_sum = Σ(manual?2:1)`）、`byte_cap = min(393216, 65536*len(claims))`。
   - **项目层显式值优先**：若 `_autopilot/config.json` 里已配置非空 caps，则不用推导值（保持 263-270 的"缺键才回退"语义）。
4. **顺序修正**：把 `:1492` 的 caps 计算下移到 `:1495` 的 `card_backed = dispatch_card(...)` 之后，改为 `_read_scope_caps(project_root, card_backed["claims"] if card_backed else None)`。修订后必须保证：无 claims 的卡渲染结果与改动前逐字节相同。
5. `claim_gate` 读取：`os.environ.get("MW_CLAIM_GATE", CLAIM_GATE_DEFAULT)`，非法值回落默认并写一行 `[CLAIMS] claim_gate=<invalid> fallback=advisory` 到 stderr（fail-open，不阻断派发）。
6. 新增测试 `packages/multi-workers/test_claim_dispatch.py`：① `dispatch_card` 返回 claims（含别名/全角/缺列各一例）；② caps 随卡变（同一次派发内，卡的预算不同 → 渲染出的 `l2_read_file_cap:` 不同）；③ 无 claims 卡渲染与改动前逐字节相同（用改动前的 golden 字符串）；④ synthesized 路径不写 caps 行；⑤ 项目层显式配置优先于推导；⑥ `MW_CLAIM_GATE` 非法值回落。
7. 不改任何既有测试的断言；不改 `REGISTRY`（不新增类型，T-17 必须保持绿）。

## 写入允许面

- `packages/multi-workers/autopilot/dispatch.py`
- `packages/multi-workers/test_claim_dispatch.py`

## 写入禁止面

- 其余所有 `packages/multi-workers/*.py`（尤其 `launcher.py`、`conductor.py`、`mw_common.py`）、`packages/multi-workers/autopilot/config.py`（不新增配置键）、`packages/coding-agent/**`、`dist/**`

## 验收命令

```
cd packages/multi-workers
python -m pytest test_claim_dispatch.py -q
python -m pytest test_autopilot_readcap_injection.py test_autopilot_dispatch.py test_autopilot_l0.py -q
```

第二条必须全绿（T-17 平价锁在那里）。若有既有红，必须先证明它与本改动无关（给出改动前的同样红）。

## 改动历史

- 2026-10-21 创建（无既有改动）

## 交付格式

`output.md` 四段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。证据段给：`dispatch.py` 的改动行号、caps 前后值对照（一例）、三条 pytest 输出的 passed/failed 数。残留段写清未覆盖的夹具（如 synthesized 卡的 claims 形态）。
