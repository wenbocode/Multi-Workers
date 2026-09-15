# Quality Gate Report: mw-widget-terminal-lifecycle

**时间**: 2026-09-10T17:55+08:00
**触发**: 手动（/quality-gate，VERIFY 阶段，review S1~S3 修复后）
**范围**: 全量（T-01~T-09 全部任务 + 指纹 + 任务文件簿记）

## 前置门禁

| 检查项 | 结果 | 说明 |
|--------|------|------|
| spec.md AC 编号 | ✅ | AC-001~013（13 条） |
| design.md VC 编号 | ✅ | VC-001~013（13 条） |
| AC→VC 映射覆盖 | ✅ 100% | §8 映射表 13/13 |
| evidence-requirement.md | ✅ | 存在，逐 AC 充分性判定齐全 |
| ac_fingerprint | ⚠️→✅ 重锚 | 见下「指纹重锚记录」 |
| evidence/baseline/ | ⚠️ | 空目录——设计 D-009 将验证范围定为 L1 + 既有套件零回归，无 L2 层；**需用户确认接受** |
| task ac_refs/vc_refs | ✅ | 9/9 非空（修正 T-01/02/03/08 四处滞留的「未验证」表头为验收通过实录） |

### 指纹重锚记录（披露）

- 原记录 `4340acf7b818` 为早期会话 ad-hoc 计算，20 种哈希口径变体均无法复现（方法已随上下文压缩丢失）
- **AC 集合零漂移独立证实**：evreq 锁定 ac_ids（AC-001~013）与当前 spec 完全一致；spec.md mtime（12:14:44）早于 evreq generated_at（12:30:00）
- 重锚值 `95d6a253ba12`，采用 quality-gate 文档 canonical 管道（git-bash 实跑 + Python 双重验证）
- 已更新 evidence-requirement.md（含 provenance 注记）与 plan.md 引用

## 问题清单与核查结果

### Q-AC（spec 13 条，经 §8 映射落 VC 证据）

| 问题 ID | 描述 | 状态 | 证据引用 |
|--------|------|------|---------|
| Q-AC-001 | live 行全部显示不折叠 | ✅ 充分 | runs/regression §2 VC-001 行；今日复跑 121/121 |
| Q-AC-002 | 未 ack 终态行常驻 + ack 后移出 | ✅ 充分 | VC-002 行；ack 前后双渲染对照 |
| Q-AC-003 | history 折叠 5 + more | ✅ 充分 | VC-003 行（7/5 两组边界） |
| Q-AC-004 | ack 持久化/幂等/拒绝非终态 | ✅ 充分 | VC-004 行（存储半 + 通道半）+ bundle 冒烟实录 |
| Q-AC-005 | ack_worker_result 工具 PM-only | ✅ 充分 | VC-005 行（worker 模式零注册实证） |
| Q-AC-006 | ack 不改队列不重派 | ✅ 充分 | VC-006 行（快照 diff=0 + 无新增行） |
| Q-AC-007 | failed detail = Exit Reason/前缀剥离 | ✅ 充分 | VC-007 行 |
| Q-AC-008 | nc detail 回退链 | ✅ 充分 | VC-008 行（questions→log_tail→no_output 三段） |
| Q-AC-009 | done detail = TL;DR ≤100 + 回退 | ✅ 充分 | VC-009 行（写入半 + 展示半 + starter 半） |
| Q-AC-010 | hint 含 ack 指示 | ✅ 充分 | VC-010 行（L0 常量断言） |
| Q-AC-011 | list_tasks acked 徽标 | ✅ 充分 | VC-011 行 + bundle 冒烟实录（wtl-t03/t04 带徽标） |
| Q-AC-012 | 孤儿行正证据 reconcile | ✅ 充分 | VC-012 行（exit 0/1/2 三映射 + output-only + own 行不动） |
| Q-AC-013 | 静默窗口 + beat 退让 | ✅ 充分 | VC-013 行（+ 今日 S2 新增 expired-dead-pruned/alive-kept 两用例） |

### Q-VC（design 13 条）

全部 ✅ 充分：13/13 [VERIFY] 埋点在 runs/regression §2 表逐条勾销；今日 S1~S3 修复后全量复跑（TS 121/121、Python 365 passed、biome 零告警）埋点仍全量输出。

### Q-COV（Coverage Matrix F1~F9）

| 问题 ID | 覆盖判定 | 证据 |
|--------|---------|------|
| Q-COV-F1 | ✅ | ack-store.test 5 用例（正常/边界/异常三列全） |
| Q-COV-F2 | ✅ | renderWatchLines 用例组（三区 + 5/6 折叠边界 + 空 key（无任务头行）+ 无 ack 文件（AckStore 缺文件→空 map）） |
| Q-COV-F3 | ✅ | terminal detail 用例组（三状态 + 截断 + 空节 + 无 output.md） |
| Q-COV-F4 | ✅ | output.test 8 用例（直通/截断/剥离/空 fallback） |
| Q-COV-F5 | ✅ | ack channels 用例组（命令/工具等效 + all 语义 + PM-only） |
| Q-COV-F6 | ✅ | VC-006（task.md 保留场景） |
| Q-COV-F7 | ✅ | reconcile 组（三映射 + output-only + ≤1 poll + own 行不动） |
| Q-COV-F8 | ✅ | reconcile 组（90m/新鲜/beat 退让 + S2 新增两用例） |
| Q-COV-F9 | ✅ | VC-010/011 |

### Q-X（交叉问题，PM 推导）

| 问题 ID | 描述 | 状态 | 推理链 |
|--------|------|------|--------|
| Q-X1 | reconcile 转终态的孤儿行能否被 widget 作为 unhandled 呈现（AC-012 × AC-002 交互） | ✅ | 单一数据源（_workers.parallel，GC-4 协议不变）：launcher 写终态 → renderWatchLines 读同文件按状态分区；两段各自 L1 验证 + 数据同源，组合正确性由构造保证 |
| Q-X2 | 双 PM 窗口并发 ack 同一 key | ✅ | 同一 workers.lock（O_EXCL）串行 read-merge-write；重 ack 幂等覆盖（VC-004 单实例幂等 + 锁机制既有验证） |
| Q-X3 | worker 写 output.md 与 PM 渲染并发（torn read） | ✅ | 时序上无重叠窗口（行状态翻转依赖 [END]/reap，均晚于 output.md 写完成）；即便瞬态读破也仅展示降级且 4s 自愈，无持久错误 |

## 汇总

- **总问题数**: 38（Q-AC 13 + Q-VC 13 + Q-COV 9 + Q-X 3）
- **通过（充分）**: 38（100%）
- **有条件通过（不足）**: 0
- **未通过**: 0

**质检结论**: ✅ 通过（附 1 项门禁层 ⚠️ 待用户确认：evidence/baseline/ 为空——D-009 设计定性为 L1 + 既有套件零回归，无 L2 层；bundle 级冒烟已作为最接近 L2 的补充证据）

## 二次印证

1. spec 约束（时间戳 UTC 口径 / 队列 7-8 列协议不动 / PM-only 注册 / 不引入 TTL）：分别由 VC-012 前置的 _parse_utc_ts、GC-4 复验（测试断言列格式）、VC-005、renderWatchLines 无 TTL 逻辑覆盖 ✅
2. Function Flow 两图全部节点（ack 链 7 节点 + reconcile 链 12 节点）均落到至少一个 VC/用例 ✅
3. Coverage Matrix 异常路径列（非终态拒绝/无 output.md 回退/own 行不动/beat 退让/expired-dead 清理）全有对应用例 ✅
4. 无 vc_refs 为空但 AC 有 VC 的遗漏绑定 ✅

## 备注

- review S1~S3 已修复（evidence/runs/review-2026-09-10.md 复核记录段），修复后全量复跑绿
- 环境副作用留痕见 runs/regression §5（冒烟 ack 两行、mw serve 重启、pytest.ini 属他 key）
