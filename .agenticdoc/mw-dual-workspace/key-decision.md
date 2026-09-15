# KDR: mw-dual-workspace

## R（需求）

- 技术栈: TypeScript（agent-team-loop 扩展）+ Python 3（mw serve / launcher）
- 边界: 不做多控制工作区共享目标的跨工作区锁（N:1）、不做 UE 专用任务类型扩展、不做二进制资产直接编辑；目标是双工作区基座（路径模型 / Game+Engine 双目录配置 / 模式切换 / deny 防火墙 / profile 注入）
- 关键约束:
  - 双根路径模型：协调文件根（控制工作区）与工件 cwd（目标工程）分离；未配置时必须回落到现有单目录语义（用户明确要求保留）
  - UE 目标配置必须显式区分 Game 与 Engine 两个目录（用户明确要求）
  - 运行模式经持久化配置或 mw 指令区分，不改代码不重建 bundle（用户明确要求）
  - deny 规则优先于 allow 的上下文防火墙；read_scope fail-closed 语义保留
  - 目标工程零框架污染（AGENTS.md/指针文件都不放）
  - 沿用 goal.md 约束 GC-1~GC-6（Extension API only / 文件驱动协调 / 进程隔离 / 文件锁 / 按类型白名单 / goal mtime 追踪）

## A（架构）

- D001 worker cwd/控制根: 选 cwd=game + PI_WORKER_TASK 推导，否 cwd=控制根（工具链相对路径锚目标）
- D002 双根所有权: 选 launcher 唯一注入点 + TS/Py 双侧解析 parity，否跨语言共享解析（PM/serve 零改动）
- D003 read_scope 锚定: 选相对锚 cwd + deny_globs/minimatch，否别名前缀（语义不变零新依赖）
- D004 deny 执行层级: 选调用级强制+遍历有界+提示级三层，否核心工具改动/影子工具（GC-1 合规）
- D005 profile 注入: 选 task.md 渲染 + 控制根授权，否 instructions API（自包含原则）
- D006 目标 AGENTS.md: 选不干预，否合并/禁止（pi 原生优先）
- D007 conductor scope: 选 game 根展开失败报错，否 worker 侧展开（单一锚定）
- D008 长路径: 选不特殊处理，否 \\?\\ 守卫（本机实测 OK）
- D009 跨盘测试门控: 选 env 门控+显式 skip，否同盘模拟（假覆盖）[AI 推荐]
- D010 target.yml 载体: 选单文件含三节无新目录，否三份 md/.mw 私有（用户决策；_ 前缀约定）
- D011 切换指令: 选 target set/clear/show + env 覆盖，否仅手编（AC-005）[AI 推荐]
- D012 VCS/游戏 CI: 选不抽象手动提交，否 VCS 无关层（用户决策，后续讨论）
- D013 toolchain 探测: 选 .mw/toolchain.json 持久化，否写 target.yml（机器属性不进项目配置）
- D014 编译锚点: 选 {uproject} 占位符+唯一性发现，否 GUID 发现（跨机器可复现）

## I（实施）← PM 执行中追加
