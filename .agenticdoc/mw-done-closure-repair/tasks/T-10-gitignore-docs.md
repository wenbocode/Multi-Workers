# T-10-gitignore-docs

状态: done（2026-09-25） · 覆盖: 收尾登记 · 依赖: T-09

## 目标

配置与文档收尾：marker 忽略项、CHANGELOG、pitfalls 沉淀。

## 步骤

1. 仓库根 `.gitignore`（:65-69 既有 .agenticdoc 区段）追加一行：`.agenticdoc/**/.mw-achieved-baddraft.json`。
2. `packages/multi-workers/CHANGELOG.md` [Unreleased]：
   - Fixed：autopilot verify→done gate-blocked 时失败原文丢弃导致 L3 reprompt 缺失 + ≥200B 草稿永久锁死（achieved.md 词表类失败现回流 L3 修正循环）
   - Added：closure 模块（三条件坏稿覆盖授权 + 内容寻址 marker）
3. `_pitfalls.md`（或 key dir pitfalls 节）沉淀：子进程 stderr 丢弃类缺口——回传通道设计须最小充分（元组 err），失败原文是唯一无词表污染的 vocab 载体；锁内原子写 + 同锁删是死文件窗的通用解。

## 验证

- diff 自检：.gitignore 恰一行；CHANGELOG 段落符合规范（[Unreleased] 下 Fixed/Added）；无 emoji。
