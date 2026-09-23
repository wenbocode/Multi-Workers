# Achieved: mw-target-partition

> 完成日期 2026-09-19
> 质检：✅ 通过（两轮：FAIL 4 BLOCKER → 处置 → 复核 PASS，evidence/quality-gate-report-2026-09-19.md）

## 系统行为变化

mw 框架的 target 配置从 UE-only（dual 词汇）扩展为**单配置文件多模式**，面向"大项目拆子目标独立迭代"场景：

- **target.yml v2**：顶层唯一 `active: single|dual|partition` 键 + `dual:`/`partition:` 模式块（toolchain/ignore/contract 随块）；partition 块声明 parent（父项目根，只读上下文、无写回/合并流程）+ partition（独立分片目录 = worker cwd）+ 可选 roots（命名附加根，键名 [A-Za-z0-9_-]+ 避保留名）+ vcs；根关系校验（不相等/不互嵌）
- **解析层**：`_decide_active_mode` 纯函数实现 12 行解析规则表（文件形态 v1/v2/无 × active × 两族 env，行序即优先级；交叉 env fail-closed；EP 覆盖激活模式字段、source 3 枚举不新增）；v1（无 active 键）原样解析零行为变化，TS/Py 双侧 1:1 parity（44 夹具 case + 112 参数组合同表）；YAML 顶层语义钉死（0 字节/空白/BOM-only → 历史 single；`null`/list/标量 → invalid-config，双侧同文案）；roots 键名 AST 级类型校验（未引号数字/布尔键拒，带引号合法）
- **派发链路**：spawn cwd = partition root；trace/output 写回控制根；`_expand_read_scope` 锚定分片根（control 追加、不并 parent）；task.md 注入 PROFILE_MARK v2 块（模式行，仅 partition；dual 维持 v1 文本零变化）；active 切换后 profile 整体替换（全块文本比对：配置变→替换、同配置→字节不变）；**三态撕裂校验**（无 marker 放行 / v2 marker+合法 mode 行比对 / v2 marker+畸形 → profile malformed 拒 spawn；块头容忍空行/注释行，限 8 行窗口）；**conductor 派发同步注入**（autopilot/dispatch.py 在 active=partition 时注入同协议 v2 块，Py/TS 渲染逐字节 parity golden 锁定）
- **CLI**：`mw partition set/show/clear/on/off`（set 含 v1 一次性迁移：dual 字段+手维护段迁入块、.bak 备份（原子替换）；块级编辑 + os.replace 原子写；--partition 省略默认控制根）；`mw partition show` 无文件/非 partition 统一 exit 1 + 切换提示；`mw target` 命令族最小改动（show 守卫、v2 dual 块分支、on/off 对称、clear v2 仅删 dual 块保留 partition 块；v1 路径零改动）；`/mw partition` TS 转发（可注入 runner）
- **诊断**：doctor partition-only 键（parent_root/partition_root/roots）+ parent/partition/root:* checks；probe 缓存 resolved-config 指纹（active 模式+归一根集合）+ mtime 双判
- **影响面**：mw_common.py / mw.py / launcher.py / autopilot/dispatch.py；target-config.ts / task-dispatcher.ts / ui-bridge.ts / mw-runner.ts；dist bundle 重建；测试 Py 677（+98）/ TS 387（+22）全绿，S0 golden 基线逐字节 MATCH，`npm run check` 0/0/0

AC/VC 勾销与证据链见 quality-gate-report-2026-09-19.md 与 verify-run-2026-09-19.md（18 [VERIFY] 行 + 零修改审计 + E2E 记录）+ e2e-spawn-2026-09-19.md（真实 spawn：cwd-evidence、v2 注入全文、config-torn 负路径）。

## 目标如何达成

- 需求三轮演化定稿：generic→derived→partition（独立目录）；两文件方案经两份独立评审（design/spec review，各 3/4 BLOCKER）后用户拍板转单文件 v2（模式块+active 键），消灭活跃文件感知/缓存绑定/切换残留整类问题；三决策点 A/A/A（parent 无写防火墙欠债、撕裂 fail-closed、根关系校验）
- 执行 S0~S4 五棒串行 worker 派发 + verify 两轮证据质检 + **终审三轮代码评审收敛**（FAIL 5 BLOCKER + 3 MAJOR → 修复 → FAIL 1 残留 + 3 欠债 → 修复 + PM BOM 跟进 → PASS）；每轮发现均 PM 逐条实测核实前提后处置；S1 首派模型流挂死（进程 CPU 0.06s/20s 实锤）精准 kill 重派零浪费完成
- 零回归三层保障：既有用例零语义修改（6 删行全为 runner 空值容差）+ S0 golden 逐字节 + 规则表行 8 v1 语义钉死

## 经验教训

- **多文件配置方案在评审面前暴露的共性问题（活跃文件感知/缓存绑定/双文件撕裂）用"唯一 active 键 + 模式块"一次性消灭**——结构选择比逐条修补便宜，沉淀到关键决策记录（key-decision.md R 章 v3 转向记录）
- **golden 基线先行是零回归约束的硬通货**：S0 在实现前录制（等价 main 快照），此后每棒 MATCH 即活断言；路径归一（tmp 根→占位符、resolved 控制根为归一键防 8.3 短路径）是跨机稳定的关键
- **"v1 标记视为 dual"的字面指令会误伤 single+sections 工作区**——S2 worker 以现行行为探测否决了 PM 指令字面义并加防误判测试；规则迁移时先探测被迁移行为的全形态再定判据
- **挂死 worker 的判别证据是 CPU 增量而非心跳**（心跳只证 wrapper 活）；kill 前用 Win32_Process 树精确定位到 pi CLI 进程，服务/launcher 不动
- **质检 FAIL 是流程资产**：第一轮 4 BLOCKER（真实 spawn E2E/签署/台账/tasks 归档）全部转为正式证据链节点；E2E 走 dist 产物 import（生产链路）优于 src 测试路径
- 去向：以上均已归档到本 key（key-decision.md、verify-run §5、tasks/）；P-001/P-002 类坑已在 spec §5 前馈；无新增 _pitfalls.md 项

## 遗留

- parent 写路径防火墙（与 dual 对 engine root 现状一致的欠债）：明确去向 = 接受不处理，将来需要硬防护另立 key（spec §1.1/§4 已声明）
- merge-back / 写回父项目流程：同上，另立 key
- E2E %TEMP% 目录（mwtp-e2e-*）保留取证未清理：接受不处理（路径已记入证据文件）
- mw-dispatch-models 同款 dist 双份 diff（coding-agent dist 树追赶）：随下次 release 常规收口，接受不处理
