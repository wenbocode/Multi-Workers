# KDR: mw-done-closure-repair

## R（需求）
- 技术栈: Python（packages/multi-workers/autopilot，pytest）
- 边界: 只改 verify→done 失败回路的 2 处——gate 失败原文回流 L3 reprompt、内容寻址坏稿 marker；不动转写/审批/预算/工具白名单机制
- 关键约束: 框架源码零工程词表字面量（唯一来源 = advance 失败原文）；判定不代写（QG/PASS 转写路径不动）；marker 失效方向恒为"不覆盖"；l3 预算封顶 + stalled 兜底语义保持

## A（架构）← system-design 追加
- D-001 回传契约: 选元组 (verdict, err)，否 dataclass/State 字段（最小充分、无隐藏契约）
- D-002 失败行提取: 选 "   - " 前缀全量解析+基底拼接，否 timeline 回读（逐字不可恢复）
- D-003 marker: 选 key 目录点前缀 JSON+字节精确 sha+同锁删，否 .mw/ 落点/EOL 归一哈希（fail-closed）
- D-004 覆盖守卫: 选三条件+原子写+同锁，否裸 write_text/锁外校验（W5b fail-safe）
- D-005 gate-blocked 分支: 选四路展开+自持 l3 预算+verdict 保真 meets，否 streak 兜底/耗尽翻 below（streak 被 dispatch 打断，P-009）
- D-006 事件: 选 l3-reprompt 限长摘要事件，否全文进 timeline（多行破坏协议）
- D-007 判据: 选合成词表「行为影响」「未了事项」+e2e_l2 证实，否 Impact/Follow-ups（自然词项假阳性）

## I（实施）← PM 执行中追加
