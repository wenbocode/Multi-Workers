# Plan: xkey-repair-mechanism

基线: `6d98c5ee3`（HEAD，工作树对本次写面干净）· fingerprint `b944d7646135` · design D-001…D-012

## 并行度分析（按文件边界）

| 写面 | 归属 | 依赖 | 冲突面 |
|---|---|---|---|
| `autopilot/xkey.py`（新模块，全部纯函数/文件原语） | **W1 单写者** | 无（契约冻结见下） | 无 |
| `test_autopilot_xkey_registration.py`（新 L1/TDD 红测） | **W2 单写者** | 仅契约（ASCII 签名） | 无 |
| `autopilot/conductor.py` + `autopilot/config.py`（挂载点） | **W3 单写者** | 契约 + design D-010 挂载坐标 | 无 |
| `status-model.ts` + `shared/xkey-gate-guard.ts` + `index.ts`（TS 镜像与 gate-dir 写拦截） | **W4 单写者** | 契约（kind 名/目录前缀） | 无 |
| `test_autopilot_e2e.py` + `test_autopilot_conductor_exec.py`（L2 追加） | **W5** | **必须 W1+W3 落地后**（须真跑通链路） | 与 W3 不同文件，但语义依赖 |
| 全量回归 / CHANGELOG / `_pitfalls.md` / achieved / 质检 | PM 串行 | T-05 全绿后 | — |

**并行波次**：
- **波 1（4 路并行）**：T-01(W1) ‖ T-02(W2) ‖ T-03(W3) ‖ T-04(W4) —— 四者写面互不重叠；W2 为 TDD 红测（对 HEAD 必红），W3/W4 靠冻结契约与 W1 并行
- **波 2（1 路）**：T-05(W5) L2/e2e
- **波 3（PM）**：T-06 全量回归 → T-07 收口

**必须串行的理由**：T-05 的 e2e 需要真实链路可跑通（stub conductor + stub provider），在 W1/W3 未落地时无法构造分支键；T-06 全量回归必须在所有写面冻结后。

## 契约冻结（并行不漂移的前提，W1/W2/W3/W4 逐字遵守）

```python
# autopilot/xkey.py  —— 公开面（其余 helper 自由命名）
REGISTRATION_KEYS = ("cross_key_test", "owner", "handoff", "frozen_block")
def parse_registration(source_text: str) -> dict | None
    # -> {"file","test_id","owner_key","handoff","frozen_block"} 或 None（=不可解析，须升级）
def collect_registrations(sources: list[tuple[str, str]]) -> dict | None   # [(source_name, text)]
def dedup_key(file: str, test_id: str, block_sha: str) -> str
def ledger_load(root: str) -> dict
def ledger_append(root: str, row: dict) -> str        # 幂等：同 dedup_key 不新增行；返回 dedup_key
def ticket_write(root: str, ticket: dict) -> str      # -> ticket path
def ticket_load(root: str, request_id: str) -> dict | None
def tickets_iter(root: str) -> list[dict]
def locate_frozen_block(root: str, file: str, test_id: str) -> dict | None
    # -> {"file","symbol","line_range","old_block_sha256"} 或 None（=定位歧义 → 降级仅提案）
def check_boundary(proposal: dict, ticket: dict) -> str    # "ok" | "violation"
def apply_block_replace(root: str, ticket: dict, new_bytes: bytes) -> str  # -> 新 sha256（原子写）
def run_verification(cmd: list[str], cwd: str, run_dir: str, timeout: int) -> dict
    # -> {"stdout_path","sha256","red_counts"}
def evidence_bundle_write(root: str, request_id: str, bundle: dict) -> str
XKEY_STATUSES = ("detected","ticketed","approved","applied","verified","closed",
                 "rejected","timed-out","boundary_violation","escalated")
```

- **落点**：`<project>/.agenticdoc/_autopilot/xkey/{ledger.json,tickets/,evidence/<request_id>/}`
- **账本行**：`{dedup_key, source_key, owner_key, test_id, file, frozen_block, status, request_id, history[{ts,event,detail}]}`
- **config 键**（`autopilot/config.py` + `_autopilot/config.json`）：`xkey_repair`(bool,默认 false)、`xkey_verify_cmd`(list[str])、`xkey_verify_timeout_s`(int,默认 1800)
- **gate kind**：`xkey-authorize`（两侧闭集镜像）
- **哈希口径**：冻结块 = 字节精确 sha256；同记录附 `sha256_eol_normalized`（D-012）
- **锚定**：一切机械判定用 sha，不用行号（D-011）

## 任务表

| # | 任务 | 执行者 | 覆盖 | 验收 |
|---|---|---|---|---|
| T-01 | `autopilot/xkey.py` 核心模块（解析/账本/工单/定位/边界/应用/验证/证据包） | W1 | VC-001…003,005,006,011,012 | 自测脚本通过；`python -c "import autopilot.xkey"` 干净；无 `any` 等价物 |
| T-02 | 新 L1 测试文件（10 字形真值表 + 账本幂等 + 边界正反例 + 证据包五项 + gate flood），TDD 红测 | W2 | VC-001…006,011,012 | 对 HEAD 红（可证非空洞）；W1 落地后由 PM 复跑 |
| T-03 | conductor 挂载（step F 消费 + `:214/:216` 聚合 + `_gate_open` request_id 维度 + L3 登记解析并入 provenance + config 键） | W3 | VC-002,003,004,007,008,012 | 既有套件全绿；开关关闭零行为变化 |
| T-04 | TS 镜像：`gates.py:52` ↔ `status-model.ts:467` kind 闭集 + 新 `shared/xkey-gate-guard.ts` gate-dir 写拦截（注册进 `index.ts`） | W4 | VC-004 | `npm run check` 该包干净；既有 guard 测试绿 |
| T-05 | L2/e2e：合成 fixture 全链重放 + FM 语料 fixture 重放（路 b） | W5 | VC-009,010 | fixture 红 1→0；FM 树零污染 |
| T-06 | 全量回归：默认套件 vs 基线（978 passed + 2 外域先在）+ 证据落 `evidence/runs/` | PM | VC-008 | 零新增失败 |
| T-07 | CHANGELOG [Unreleased] + `_pitfalls.md` 新条目 + `achieved.md` + 质检报告 + 任务卡收口 | PM | — | 文档 diff 过目 |

## 风险登记

| 风险 | 缓解 |
|---|---|
| W3 与 W1 接口漂移 | 契约冻结节逐字给出签名；W3 只 import 不重定义 |
| W2 红测与 W1 实现名漂移 | 同上；W2 只依赖公开面 |
| conductor 挂载点顺序错 → xkey approve 无法解冻 key | T-03 卡面钉死"消费分支必须先于 `:211/:214`"；并用 L1 断言双 pending gate 场景 |
| gate flood（6684/12h 红线复发） | T-01 的 `_gate_open(request_id)` 语义 + T-02 的 N-tick 用例（VC-012） |
| consumer 侧 gate 目录写拦截误伤提案路径 | T-04 卡面写明**只拦 gate 目录**，`xkey/evidence/**`（提案）必须仍可写 |
| L3 prompt 改动破坏既有 prompt 断言测试 | T-03 卡面列出需同步的写侧测试（`test_reviewer_prompt_documents_fallback:919` 等） |
| 旧 conductor 遇新 kind 每 tick skip | T-03 与 T-04 同版本落地（D-009）；CHANGELOG 注明部署顺序 |
| FM 工作树被污染（AC-010 要求只用 fixture） | T-05 卡面钉死：`E:\CLI_workspace\FeatureMigrator` 只读 |
| 并行会话提交造成基线漂移 | T-00 已核验 HEAD `6d98c5ee3`；漂移则更新锚点再派发 |
