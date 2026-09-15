# KDR: mw-dispatch-reliability

## R（需求）

- 技术栈: Python（mw/launcher/doctor）+ TypeScript（pi 扩展）+ pytest/vitest/Bash（测试）
- 边界: 不新增任务状态、不自动 rebuild bundle、不自动杀孤儿 proxy、L2 仅 pi/timi 真实路由
- 关键约束: 文件总线 + 跨语言文件锁不变；worker 凭证隔离语义不变；测试密封（不依赖机器真实凭证）

### 需求决策记录（2026-08-28 澄清）

| # | 问题 | 决策 |
|---|------|------|
| Q1 | 缺凭证任务失败语义 | A：复用 `failed`，exitReason 区分配置缺失 vs 执行失败 |
| Q2 | 预检与凭证配置 | 要启动预检；凭证来源可配置扩展（配置文件路径+字段），加路由不改代码 |
| Q3 | 陈旧条目治理 | B：定期扫描，移入专门归档目录/文件，不留在队列 |
| Q4 | doctor 形态与权限 | CLI（mw.py doctor）+ pi 内（/mw doctor）双入口；允许自动修复 |
| Q5 | L2 成本与测试归属 | 接受真实 LLM 调用；测试文件全部并入正式套件（pytest/vitest），不留游离脚本 |
| - | 全路由凭证缺失时 | [AI 推荐，承前轮方向] 预检失败 → mw serve 拒绝启动（fail fast） |

## A（架构）

- D001 缺凭证隔离位置: 选 _spawn 内降级 per-task failed，否预检快照过滤（判定靠近使用点）
- D002 预检载体: 选 cmd_serve 入口+预检后写 PID，否 launcher 侧（fail fast 语义清晰）
- D003 凭证配置: 选 providers.json 增 credentials 节，否独立 credentials.json（单一事实来源）
- D004 stale 归档: 选 launcher poll 内扫描归档，否 PM 侧/doctor 触发（队列单写者纪律）
- D005 doctor 形态: 选 mw_common.py 共享核心+双入口薄壳，否塞 mw.py/TS 重实现（避免两套实现）
- D006 播报修复: 选 waitForMwStart 3s 稳定窗，否下轮 turn 二次校验（改动集中）
- D007 测试架构: 选假 CLI 注入真 launcher+marker 隔离 L2，否 mock subprocess（覆盖真实文件总线）

## I（实施）← PM 执行中追加
