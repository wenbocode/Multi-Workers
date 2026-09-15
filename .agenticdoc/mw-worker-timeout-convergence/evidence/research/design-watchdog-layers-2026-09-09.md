# Design 调研补记：看门狗四层机制的设计依据

> [RETRIEVED @ 2026-09-09 恢复复验轮：自 design.md（D-001~D-006）、spec §4 决策记录（D-1~D-5）与实跑证据追溯整理补记。设计期结论的原始出处如下，无新增决策。]

## 调研问题与结论

1. **挂死检测的可用信号**（来源：OverCode 四 worker 取证 + pi 扩展 API 事件面）
   - 结论：`message_update` 的 token 级流式增量是区分「慢生成在途」与「真挂死」的关键未用信号；事件循环存活（旧 watchdog 的隐含假设）不等于调用活着
   - 依据：cpr-003/cpr-007 被杀时仍在产出（生成最终报告/~300 行实现在途）；cpr-004 被杀前 28 秒还有工具活动
2. **预算与挂死职责分离**（来源：设计对话两轮，用户拍板方案 B+A+C）
   - 结论：墙钟只做预算兜底（默认 60m，task.md/env 可调），挂死判定交给 activity watchdog（idle 10m）；两职责混在单一 setTimeout 是误杀根因
   - 依据：spec §4 D-1/D-2
3. **成果不依赖 exit 安全网**（来源：OverCode 死在收尾阶段的案例）
   - 结论：预算尾段注入 deadline steer，agent 自行把「已完成/未完成/后续建议」写入 output.md——被杀前成果已落盘
   - 依据：cpr-005（死在收尾验证）、cpr-003（生成最终报告时被杀）
4. **发散检测与升级路径**（来源：用户要求「超 30m 必须有执行日志收敛判据」）
   - 结论：min(30m, budget/2) 检查点写 [CHECKPOINT] 机器判据（elapsed/reads/writes/phases/uniq_targets/repeat_top/risk）+ worker 自评；mid/high 经 triggerTurn 升级 PM 主窗口判断（继续/收窄/分拆/直执），low 只进 widget
   - 依据：spec §4 D-2/D-4；risk 启发式定 advisory（对非编码任务会误报，决断权在 PM）
5. **steer 的排队语义**（来源：L2 Run 1 实跑发现）
   - 结论：agent 运行中裸 `sendUserMessage` 报 already-processing；checkpoint 用 followUp（不打断在途）、deadline 用 steer（紧急注入）
   - 依据：evidence/runs/smoke-watchdog-2026-09-09.md Run 1 缺陷与修复记录
6. **协议零侵入约束**（来源：goal.md GC-1 + 本 key AC-006）
   - 结论：全部机制在扩展内实现，[FLOW]/[HEARTBEAT] 等既有行格式不变，新行纯增量，Python/doctor 零改动
   - 依据：质检 Q-AC-006 git diff 范围核查（仅 6 个扩展文件 + test + goal.md/.agenticdoc）
