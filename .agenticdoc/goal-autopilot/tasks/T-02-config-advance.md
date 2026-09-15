# Task T-02: config.py + advance.py（配置与推进封装）

## 基本信息
- Stage: 1
- 代码状态: 代码完成（autopilot/__init__.py + config.py + advance.py）
- 验证状态: 验证通过（test_autopilot_config.py 26 passed；全量 L1 147 passed 零回归；真实框架定位验证通过）
- 负责 Agent: PM 窗口（WENBOZHOU-PC4:8420，用户指令直执）
- ac_refs: [AC-025]
- vc_refs: [VC-027]
- pattern_refs: []

## 描述
新文件 `packages/multi-workers/autopilot/__init__.py`（空包标记）+ `autopilot/config.py` + `autopilot/advance.py`。

**config.py**（D-110）：
- 配置文件位置 `.agenticdoc/_autopilot/config.json`（任务状态邻接，人可见可改；`.mw/` 只放锁与 PID）
- 字段全集与默认值：`enabled`（false）、`paused`（false）、`poll_interval_sec`（4，≤5 上限校验）、`max_parallel_keys`（2，下限 2）、`round_budget`（2）、`worker_timeout_min`（30）、`l2_read_file_cap`（8）、`l2_read_byte_cap`（65536）
- 读取：文件缺失 → 返回默认值（不自动创建文件，未启用零足迹）；存在 → 解析 + 校验（非法值 → 拒绝启动，stderr 指明字段）
- 写入：console enable/disable/pause/resume 走此模块（原子替换 + UTF-8 + newline 对称，复用 mw_common 既有模式）
- mtime 缓存接口：供 serve 与 conductor 避免每秒重读

**advance.py**：
- 框架脚本定位：复用 `detect_root.py --json` 输出的 `PLATFORM_DIR`（不硬编码路径，勿重造探测逻辑）
- `advance(key, phase, project_root)` 封装：`subprocess.run([sys.executable, PLATFORM_DIR/scripts/advance_phase.py, key, phase])`，返回 `(exit_code, stdout, stderr)`
- 框架缺失（install 未装 / 脚本不存在）→ 调用方（conductor 启动路径）拒绝启动：stderr 明示 + exit 1
- 本模块不解析业务语义，只做进程封装与错误透传

注意：
- 参数用列表形式传参，禁止 `shell=True`
- config 校验失败不得静默回退默认值（错误配置应显式失败，而非悄悄用默认值跑）

## 输入
- 依赖文件: `mw_common.py`（原子替换/锁模式参考）、框架 `scripts/detect_root.py`
- 依赖 Task: T-01（基线冻结先行，本 task 是首个实现改动）
- AC 约束:
  > AC-025: 在未启用项目执行启用流程（配置开启）后，`mw status` 显示 conductor 运行中，且 1 个轮询间隔内 roadmap 提案流程启动（roadmap-writer 派发行出现）
- 设计约束:
  > D-110: config 在 _autopilot/config.json；round_budget 全局单处（AC-011 测试改此处即生效）
  > D-107/AC-005: advance_phase.py 是唯一推进通道

## 预期产出
- `packages/multi-workers/autopilot/__init__.py`
- `packages/multi-workers/autopilot/config.py`
- `packages/multi-workers/autopilot/advance.py`
- `packages/multi-workers/test_autopilot_config.py`：默认值、缺失文件零足迹、非法值拒绝、读写 round-trip、mtime 缓存失效；advance 封装对缺失框架 exit 1、对 stub 脚本成功路径 exit code 透传
- 验证方式: `python -m pytest packages/multi-workers/test_autopilot_config.py -v`（或项目现行 test runner 约定），断言输出 `[VERIFY]` 行
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 01:35 | 读依赖（mw_common 原子写/锁模式、detect_root 探测协议、advance_phase CLI 签名、.agentic-framework marker）→ 实现 config.py（D-110 字段全集 + fail-closed 校验 + mtime 缓存）+ advance.py（marker→标准布局双引导 → detect_root --json 权威定位 → 子进程封装，list-argv 无 shell）+ test_autopilot_config.py（26 用例含 stub 框架 fixture） | 26 passed 1.74s，[VERIFY] VC-027 行 ×9 正常 emit |
| 2 | 2026-09-10 01:40 | 全量回归 + 真实框架只读定位验证 | 147 passed, 1 deselected（121 基线 + 26 新增，零回归）；locate_platform_dir(H:\git\Multi-Workers) → .agents/skills/agentic-task，advance_phase.py 存在 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 设计取舍备注
- 引导链：.agentic-framework repo= 行优先 → 标准布局 .agents/skills/agentic-task 兜底（marker 指向丢失目录时降级不砖死）→ detect_root.py --json 的 PLATFORM_DIR 为权威（不自行推导路径）
- advance() 缺失框架返回 (1, "", 原因) 而非抛异常：conductor 主循环内无需特判；启动路径用 locate_platform_dir 的 AdvanceError 拒绝启动
- 超时 124 语义：advance_phase.py 卡死不阻塞 tick（catch TimeoutExpired 返回元组）

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
