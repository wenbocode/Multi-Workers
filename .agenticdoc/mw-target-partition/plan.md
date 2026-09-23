# Plan: mw-target-partition

> 串行 stage 派发（TS/Py 双侧强耦合，parity 由同一 worker 保紧；每 stage 一个 worker，S0 基线必须先行）
> 方案基线：spec v2（单配置文件 target.yml，模式块 + active 键），design v2（D-001~D-013）
> 基线录制说明：AC-016 golden 于**实现合入前**的当前 HEAD 录制（等价 main 快照，target 路径无 partition 改动），独立文件不导入 partition 符号

## S0 基线先行（T-00）

- T-00 双侧 golden 基线：`packages/multi-workers/test/test_target_baseline.py` + `packages/coding-agent/test/extensions/agent-team-loop-baseline.test.ts`（v1 dual 完整样例 + 无文件 single 样例；六类输出 golden 落盘：legacy 投影 13 字段、_worker_cwd、scope 展开、注入块全文、target show、doctor 段 JSON 除时间戳）(ac: AC-016, vc: VC-016)

## S1 解析层（T-01~T-03，单 worker：双侧 + 夹具一体）

- T-01 Py 解析：mw_common.py `_decide_active_mode`（§1.5 规则表 12 行）+ v2 检测/块解析/字段层 7 类校验/roots/EP 覆盖统一（source 3 枚举）/renderToolchainCommand mode 分派 + 参数化全枚举测试 (ac: AC-001~005/017, vc: VC-001~005/VC-017)
- T-02 TS 解析：target-config.ts 同构（decideActiveMode/WorkspaceConfig 增量字段/gameRoot 可空下游核查/渲染分派）+ 参数化测试 (ac: 同 T-01, vc: 同 T-01)
- T-03 parity 夹具：target-config-cases 续号 v2/错误/结构冲突 case + 两侧 runner 增量字段（不改既有 case）(ac: AC-001~003/005/017, vc: VC-001~003/005/017)

## S2 派发链路（T-04~T-06，单 worker）

- T-04 profile 注入：task-dispatcher.ts PROFILE_MARK v2（模式行）+ renderPartitionProfileBlock + 切换整体替换（标记到 EOF）+ 注入测试扩展 (ac: AC-007/018ab/019, vc: VC-007/VC-018/VC-019)
- T-05 launcher/scope：launcher.py `_worker_cwd` mode 分派 + 撕裂校验（profile 模式行 vs 当前 active → failed "config torn"）+ autopilot/dispatch.py `_expand_read_scope` partition 锚定（control 追加、不并 parent）+ 动态错误消息共用 + 测试 (ac: AC-006/008/020, vc: VC-006/VC-008/VC-020)
- T-06 doctor/缓存：mw_common.py `_doctor_target` partition checks（parent/partition/roots，无 uproject/engine）+ partition-only 键 + .mw/toolchain.json resolved-config 指纹（旧缓存无指纹视为陈旧）+ 测试 (ac: AC-009/018cd, vc: VC-009/VC-018)

## S3 CLI 与转发（T-07~T-09，单 worker）

- T-07 Py CLI：mw.py `cmd_partition` set/show/clear/on/off（块级编辑 + 原子替换 + v1 一次性迁移 .bak + --partition 默认控制根 + --root 语法校验 + 交叉 env 前置拒绝）+ `mw target set` v2 dual 块分支（v1 路径零改动）+ `mw target show` active 守卫 + test_mw_partition.py (ac: AC-010/011/013/022/023, vc: VC-010/VC-011/VC-013/VC-022/VC-023)
- T-08 TS 转发：ui-bridge.ts runMwPartitionCommand（set/show/clear/on/off，可注入 runner）+ mw-runner.ts partitionMw + agent-team-loop.test.ts 新 describe (ac: AC-012, vc: VC-012)
- T-09 bundle 重建：mw build --install（dist/extensions/agent-team-loop.js + coding-agent dist 对齐）

## S4 验证收尾（T-10~T-11，单 worker）

- T-10 全量回归：Py 全套（test.sh 范围内相关套件）+ TS agent-team-loop 相关套件 + T-00 基线对照逐字节一致 (ac: AC-013/016, vc: VC-013/VC-016)
- T-11 `npm run check` 0/0/0 + 既有测试零修改核验（git diff --exit-code）+ evidence 落盘（evidence/ 下 VC 产物）

## VC 清单

- VC-001 v2 partition 13 字段 parity（TS/Py 逐字段相等，相对锚定）
- VC-002 缺字段/缺块 → invalid-config 含字段名/块名
- VC-003 结构层 7 类 → invalid-config 含要素
- VC-004 占位符 mode 分派：partition token 渲染；未知 token missing-field；dual 零变化
- VC-005 EP 覆盖 + source 3 枚举 + 空白串=未设置
- VC-006 spawn cwd=partition root；trace/output 写回控制根
- VC-007 PROFILE_MARK v2 块（模式行）注入幂等
- VC-008 read_scope 锚定 partition + control 追加；不并 parent
- VC-009 doctor checks + 指纹重探测
- VC-010 set exit 0 落盘 / v1 迁移 .bak / 拒绝路径文件不变
- VC-011 缺参 exit 1 / clear 删块 single（无块删文件）/ 块缺失 exit 0
- VC-012 /mw partition 透传字节一致 + 转发一致
- VC-013 零回归：全绿 + 既有用例零修改 + check 0/0/0
- VC-016 基线 golden 逐字节一致
- VC-017 规则表全枚举 parity，行 5 不解析、行 8 零变化
- VC-018 active 感知：守卫互斥 / 模式行 / partition-only 键 / 指纹随切换失效
- VC-019 切换后 profile 整体替换；同配置字节不变
- VC-020 撕裂 → failed "config torn"，不 spawn
- VC-022 set 幂等 / 手维护段保留 / 原子替换 / .bak 完整
- VC-023 on/off 翻转 / 块缺失 exit 1 / v1 报错 / 转发一致

## 派发策略

S0 → S1 → S2 → S3 → S4 串行（每 stage 完成吸收后派下一个）；S0 与 S1 可并行（S0 只加新测试文件不碰实现），保守起见串行。每 worker 产出后由 PM 吸收 + 简查 diff；S4 完成后 evidence 齐备 → verify 阶段质检。
