# 调研声明 — spec 期

- **key**：mw-worktree-junction-guard
- **日期**：2026-10-09

## 声明

本 key 的**领域事实已由前一 key 的取证提供**，无需外部文献调研；spec 期只做两类**本地只读**调研，各写唯一文件、互不重叠：

| RQ | 问题 | 产出文件（唯一写者） |
|---|---|---|
| **RQ-1** | 在 `%TEMP%` 内复现并固化 junction 语义：`git worktree remove --force`（穿透）/`cmd /c rmdir`（不穿透）/PS `Remove-Item -Recurse`（不穿透），并界定"何种删除 API 穿透、何种不穿透"的判据 | `evidence/research/spec-junction-semantics-20261009.md` |
| **RQ-2** | 定位工具层已有 guard（`protected-config`）的**实现位置、注册方式、匹配与 block 机制、报错文本规范**，以及 mw 侧子命令（`mw.py`）的既有结构约定（子命令注册、doctor 检查挂载点、测试范式） | `evidence/research/spec-guard-and-mw-seams-20261009.md` |

## 事实基线（可直接引用，来自取证 key）

`mw-workspace-incident-probe/evidence/{in1-junction-incident-20261009.md, in2-file-vanish-incident-20261009.md, incidents-timeline-20261009.md}`：事故命令原文与时刻、双层 junction 链机制、受害面 3,448 文件、`rmdir` 与 `git worktree remove` 的穿透差异（含最小复现）、未提交改动被静默丢弃的写入证据。

**约束**：两个 RQ 均**只读**；不得改任何生产文件；复核已在 `%TEMP%` 内做过的最小复现，不重复损伤真树；结论必须给命令原文与原始输出，推算值标注为推算。
