# KDR: agent-team-loop

## R（需求）

- 技术栈: Python 3.10+（launcher / proxy）、TypeScript / Node.js 18+（Pi extension）、Bash（smoke test）
- 边界: 只做 Windows 平台；不做 codex extension、CI 集成、Web UI
- 关键约束: launcher 轮询 ≤ 5s；subprocess 禁止 shell=True；API key 只走环境变量

## A（架构）

- D001 pm-orchestrator 结构: 选4模块分层，否单文件（PM逻辑量大，分层可独立测试）
- D002 _index.parallel 写入: 选tmp+rename原子写，否直接writeFileSync（AC-029要求并发安全）
- D003 worker状态侦测: 选fs.watch+setInterval fallback，否纯轮询/纯watch（Windows watch偶发漏事件）
- D004 provider配置: 选providers.json，否硬编码（30+provider不改代码扩展）
- D005 Extension互斥加载: 选单入口activate()检查env，否两个独立extension（一进程一角色）
- D006 goal.md感知: 选检查点re-read，否push通知（检查点间无需实时，零额外开销）
- D007 后台服务管理: 选mw serve统一服务（serve/start/stop/status + PID防重复），否pi Extension内spawn（Pi退出会杀worker；重复activate会重复spawn）
- D008 Extension分发: 选mw init复制预编译bundle到.pi/extensions/，否target项目自编译（零npm依赖；目标项目无需TypeScript工具链）

## I（实施）← PM 执行中追加
