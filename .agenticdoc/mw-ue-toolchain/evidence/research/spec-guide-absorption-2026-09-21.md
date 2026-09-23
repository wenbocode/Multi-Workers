# Research: 实践指南吸收面划分（spec）

## 决策问题
spec §1（吸收什么）/ §1.4（不做什么）——指南哪些部分进框架、哪些留在项目层。

## 调研方法与出处
- 通读指南全文：`C:\Users\wenbozhou\Documents\WXWork\1688851418302063\Cache\File\2026-09\_toolchain-dual-mode-guide.md`（45,489 bytes，AssetImportGate 项目 PM 窗口产出，每条带出处/哈希）
- 对照现有实现：`packages/multi-workers/mw_common.py` 的 `render_toolchain_command`（fail-closed 占位符渲染）、`probe_target_toolchain`（doctor 探测 + `.mw/toolchain.json` 缓存）、`toolchain_probe_path`；`mw.py` 的 `_target_template`；`dispatch.py` task.md 注入逻辑
- 指南 §9 移植清单本身给出了划分：§9.A 项目特定 vs §9.B 通用不变

## 发现
- 现状：toolchain 只是模板映射（注入 task.md 文档 + doctor 探测缓存），**无执行/取证/判定纪律**。
- 指南 §9.B 通用不变部分：§2.1 目标名从 `Source\*.Target.cs` 现查勿猜；§2.2/§2.3 执行留证（cmd.txt/run.log/exit.txt/errors.txt + `.log` 扩展名约定）；§2.3-2 退出码必要但不充分（错误签名 `error C\d{1,5}|LNK\d{4}|error :`，625 绿断言藏 C2039 实例）；§5.5 EOL 归一化 sha256（autocrlf=input 假漂移）；--watch 前后哈希防"执行期间改源码"。
- 指南 §9.A 项目特定部分（不进框架，逐项目替换）：UBT 参数形态（-WaitMutex/-NoUBA/-MaxParallelActions=16）、模态窗处理、夹具分区、日志契约前缀。
- 差分验收：基线本来就红的项目（Game Target exit 8 既有红）对比两次 run 的 errors.txt 集合，不是对比退出码。
- 指南原文在 WXWork 缓存目录——路径会失效，必须入仓固化。

## 结论 → 决策映射
- §9.B → mw CLI 三动词 + mw_common 三纯函数（spec §1.1，design 全部决策）
- §9.A → target.yml 模板注释给 canonical 示例 + 指引入仓供逐项目替换（design D-4/D-5）
- 差分验收 → `run` 退出码语义设计（mw 退出码 = 合成判定；差分是使用侧约定，写进 README）（spec §4 待确认项）
