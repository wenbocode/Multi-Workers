# design 阶段前置研究说明（PM 自证范围 + DRQ 划分）

- key: `mw-guard-form-hardening`｜阶段: DESIGN｜日期: 2026-10-11｜基线 commit: `ab546bb64`
- 性质: **PM 自证的前置说明**（非 worker 产出）；DRQ-1…DRQ-3 报告回收后由 PM 收录为 `evidence/research/design-<rq>-20261011.md`
- 上游: `spec.md`（11 AC，19,049 B）+ 5 份 spec 阶段 RQ 证据；`design.md` 骨架（§1 mermaid 过 gate 0 错 0 警）

## 1. 设计阶段要解决的三件事

| # | 问题 | 输入 | 归属 |
|---|---|---|---|
| ① | 写面判据的**落点与形态补全**：`verbatim` 三档怎么落地、33 条缺失形态怎么补、审计行怎么改 | RQ-2 §1/§3（P-1…P-6）、RQ-1 §4 | `worker/worker-mode.ts` |
| ② | PM 侧**目标集轴与路径判定**：形状判定取代扩展名白名单、先目录后 basename、Windows 边界 | RQ-3 §2…§5 | `pm/ui-bridge.ts` |
| ③ | **角色解析单源 + key 身份**：6 份解析器收敛、`frontmatter-only`、豁免显式清单、大小写与 `_index.md` 回退 | RQ-4 §2/§3、RQ-5 §3/§4 | `worker/worker-mode.ts` + `shared/index-store.ts` + `pm/ui-bridge.ts` |

## 2. 已冻结的设计约束（PM 裁定，DRQ 不得改）

1. **方向二分**（D-002/D-006）：写面守卫 fail-open（`verbatim` 之外一律 `allow-unknown` + 审计）；PM 侧 fail-closed。
2. **不引入 shell 解释器**（D-003）：不得调用 bash 做 dry-run 解析。
3. **禁裸 token 兜底**（D-011）：PM 侧不得对无法判形状的 token 一律拒绝（实测 35% 假阳性）。
4. **引用信息是必需项**：`'$T/...'` 与反斜杠转义形式必须仍 deny。
5. **`<key>/evidence` 不得并入白名单**（会让 write-intent 唯一真阳消失、断言变红）。
6. **不引入 `any`**；`packages/*/src` 只用可擦除 TS 语法；无内联 import。

## 3. 串行链与冻结面（与 `design.md` §5 一致）

- S1 `worker-mode.ts`：AC-002 → AC-001 → AC-007（DRQ-1 的交付是这三个 AC 的实现蓝图）。
- S2 `ui-bridge.ts`：AC-003 → AC-004（DRQ-2）。
- S3 跨文件接缝：AC-005 → AC-006（DRQ-3，含 Python 侧同语义方案）。
- DRQ 期间**冻结** `packages/*/src`（research 角色只读，PM 不并发改码）。

## 4. 证据标准（沿用 AC-011）

数值机器可读 + `文件:行号` + 反例三列（输入 / 期望 / 现实现）+ 引用必须锚定最终工作树；
设计结论必须能直接抄进 `design.md`（表格/伪代码），不得只给方向。
