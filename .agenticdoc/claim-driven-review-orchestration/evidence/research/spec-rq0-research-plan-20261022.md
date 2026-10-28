# 调研计划（spec 相位，claim-driven-review-orchestration）

三个 RQ 互不重叠、各自写唯一证据文件，全部只读。串行等待没有理由：它们读的文件面完全不同
（编排面 / 判据与语料 / 度量与落盘），不存在同文件冲突。

| RQ | 问题 | 唯一证据文件 | 依赖的上游事实 |
|---|---|---|---|
| RQ-1 | 编排层挂在哪：两条派发通道、能否扇出 N 个兄弟 task、`claims>5` 门禁落点、merge 读面、可复用物与空白 | `evidence/research/spec-rq1-orchestration-seams-20261022.md` | `claim-driven-review` 四层实现已交付（`exit=0`，5 claims / 13 放行取数） |
| RQ-2 | 「拆分保真度」怎么机检：损失面清单 + 每条判据（token/负例/复用或新增）+ 104 单元语料算术 | `evidence/research/spec-rq2-split-fidelity-20261022.md` | `spec-rq3-claim-taxonomy-20261020.md` 的 104 个判定单元分类 |
| RQ-3 | 度量与灰度基线：token 归因覆盖率实测、4×5 vs 1×20 报表字段、advisory 前后 exit 分布样本量 | `evidence/research/spec-rq3-metrics-baseline-20261022.md` | `usage.py:1007` 已输出 `n/a`+`attributable=false` |

## 为什么这三条必须先调研再写 spec

1. **RQ-1**：扇出与汇合的实现形态取决于队列行与锁的现状，先写 spec 会把一个不存在的机制写进契约
   （上游已经吃过一次：`mw build` 不安装到全局，导致两次 reload 无效）。
2. **RQ-2**：保真度判据如果只靠"看起来对"，就会重复 T-07 的 `carried-from` 覆辙——那条判据的精度是 0%。
   所以必须先拿到"可构造的负例"，再定 AC。
3. **RQ-3**：AC-005(a) 的分母口径（merge 单元算不算）与 AC-006 的样本量，直接决定这两条 AC 是否可判。

## 预期落点

- spec.md 的 AC 分三组：拆分门禁与扇出（RQ-1）／拆分保真度（RQ-2）／度量与灰度（RQ-3）。
- 已知的待决问题留到 spec 里显式列出，不在调研阶段替用户拍板：
  merge 单元是否自带 claims 块、拆分是否自动执行、token 归因是否作为 (a) 的前置工程。
