# Plan: mw-dispatch-reliability

## 概览
- Key: mw-dispatch-reliability
- Spec: .agenticdoc/mw-dispatch-reliability/spec.md（AC-001~017）
- Design: .agenticdoc/mw-dispatch-reliability/design.md（VC-001~018，D-001~D-007）
- 预计阶段数: 6
- 创建时间: 2026-08-28

## 阶段列表

### Stage 1: 共享基础模块 mw_common.py
**目标**: providers.json 新 schema（credentials 节）+ 凭证解析（env→file 链）+ 路由预检 + stale 归档函数，全部可单测密封
**依赖**: 无
**产出**:
- `packages/multi-workers/mw_common.py`（load_providers / resolve_credential / route_precheck / archive_stale_entries）
- `packages/multi-workers/providers.json`（新 schema）
- `packages/multi-workers/test_common.py`
**Tasks**: T-01, T-02
**验证**: VC-017（file 源解析）、VC-004/VC-005 数据级单测

---

### Stage 2: launcher.py 改造
**目标**: 缺凭证任务隔离降级（per-task failed + worker.log 原因落盘，移除 FATAL 连坐）；poll 内 stale 扫描归档；凭证构建走 mw_common；密封化修复 2 个失败用例
**依赖**: Stage 1（mw_common 凭证/归档函数）
**产出**:
- `packages/multi-workers/launcher.py`（改造）
- `packages/multi-workers/test_launcher.py`（修复 + 新用例）
**Tasks**: T-03, T-04, T-05
**验证**: VC-001/VC-002（单元级）、VC-005（单元级）、VC-010 部分

---

### Stage 3: mw.py 预检门禁 + doctor
**目标**: cmd_serve 入口预检（全缺 fail fast，PID 写入移到预检后）；doctor_report/doctor_fix 核心 + `mw.py doctor [--json] [--fix]` 子命令（≥7 诊断节，<5s）
**依赖**: Stage 1（预检/归档/凭证函数）
**产出**:
- `packages/multi-workers/mw.py`（cmd_serve 门禁 + cmd_doctor）
- `packages/multi-workers/mw_common.py`（doctor_report/doctor_fix）
**Tasks**: T-06, T-07
**验证**: VC-003/VC-004、VC-007/VC-009

---

### Stage 4: TypeScript 侧（稳定窗 + /mw doctor + vitest 收编）
**目标**: waitForMwStart 3s 稳定窗（假成功播报修复）；/mw doctor 命令（spawnSync doctor --json 同源播报）；test-l1-full.ts 断言收编为正式 vitest 文件
**依赖**: Stage 3（doctor --json 接口存在）
**产出**:
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`（改造）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（/mw doctor）
- `packages/coding-agent/test/extensions/agent-team-loop.test.ts`（新）
- 删除 `packages/multi-workers/test-l1-full.ts`
**Tasks**: T-08, T-09, T-10
**验证**: VC-006、VC-008、VC-016

---

### Stage 5: L1 集成测试 + smoke 修复
**目标**: 假 CLI 注入框架 + 真 launcher 进程的集成测试（状态机/串行/并发/隔离/预检/归档/doctor/配置扩展全场景）；smoke_test.sh T5 假阳性修复
**依赖**: Stage 1-3（被测对象全部就绪）
**产出**:
- `packages/multi-workers/test_integration.py`（新）
- `packages/multi-workers/smoke_test.sh`（修复）
**Tasks**: T-11, T-12, T-13
**验证**: VC-011/VC-012/VC-013、VC-001~005/007/009/018（集成级）、VC-015

---

### Stage 6: L2 真实链路 + 现场实战修复
**目标**: test_e2e_real.py（marker e2e_real，真实 pi/timi "Say exactly: ok" 全链）；本仓库现场修复（清 stale 条目、/mw build 重建 bundle、真实调度验证崩溃循环消除）；npm run check + 全量回归
**依赖**: Stage 1-5（全部改动就绪）
**产出**:
- `packages/multi-workers/test_e2e_real.py`（新）
- 现场修复记录（evidence/runs/）
**Tasks**: T-14, T-15
**验证**: VC-014、AC-001 现场版、全 AC 汇总

---

## 风险与缓解
- **跨语言锁一致性**（归档重写 vs PM upsert）: T-12 并发用例前置验证；归档函数与 launcher._update_status 共用同一锁路径
- **L2 依赖真实上游**: T-14 加超时与 skip 判定（无凭证自动 skip，上游故障标注环境不可用）
- **bundle 重建影响运行中窗口**: T-15 放最后执行，重建后需重启本会话验证
- **Windows .cmd 假 CLI 形态**: T-11 fixture 同时生成 .cmd 与 POSIX 脚本，PATH 注入前插
