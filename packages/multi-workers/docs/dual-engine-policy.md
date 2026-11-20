# dual 模式的引擎权限与扩展规范

Game 是开发工作区，保持可写，但 Worker 仍受任务卡 `write_face` / `write_scope` 的限制。配置 Engine 路径本身不授予引擎源码写权限；`engine_writable: false` 下允许 UBT 编译以及下述三类构建产物目录，不等于放开整个 Engine。

在控制工作区的 `.agenticdoc/target.yml` 配置：

```yaml
active: dual
dual:
  game: 'D:\Dark\DarkGame'
  engine: 'D:\Dark\UnrealEngine'
  engine_writable: false
```

已有 v1 平铺格式在 `engine` 同级写 `engine_writable: false`。缺省等同于 `false`；只有 YAML 布尔 `true` 授予写权限，字符串 `"true"`、数字和 null 均拒绝。开启权限时必须已经配置 dual Engine 路径。环境变量可覆盖根路径，但不单独授予 Engine 写权限。

Engine 授权与任务写入面取交集。`true` 不会让 Worker 越过任务卡；`false` 的源码保护优先于 `allow_foreign_write`，也优先于覆盖 Engine 的宽泛 glob。通过 junction 指向 Engine 的路径使用真实路径判断。Game、控制工作区中嵌套的 Engine 也受同样限制；声明面包含三类构建目录以外的 Engine 路径时，派发返回 `write-face-read-only`，不入队。`write_face_deny` 不能用于从宽泛 Engine glob 中减去源码后获得授权。

PM 在 `false` 下规划 Game 侧包装与适配，在 `true` 下可以规划授权范围内的直接 Engine 修改；两种配置均不覆盖项目/spec/任务卡的限制。项目明确“不改引擎”时，即使路径权限为 `true`，PM 也不能据此修改引擎或自行扩大配置。每轮重新读取权限，重派发会替换旧 profile；`false → true → false` 不继承上一种状态的提示与授权。

## UBT 编译与产物例外

保持 `engine_writable: false`，可运行现有 UBT（包括编译项目的 Editor target）；编译 Editor target 不等于启动 Editor 进程。允许的 Engine 内生成物、缓存与日志仅限以下目录，路径相对配置的 Engine **仓库根**，如 `D:/Dark/UnrealEngine`：

| 相对目录 | 典型内容 |
| --- | --- |
| `Engine/Intermediate/Build/**` | SourceFileCache.bin、XmlConfigCache.bin、规则程序集与构建中间产物 |
| `Engine/Saved/UnrealBuildTool/**` | UBT 配置 schema 等生成文件 |
| `Engine/Saved/Logs/**` | 构建日志 |

任务卡必须声明实际所需的产物写面，例如：

```markdown
## 写入允许面
- `D:/Dark/DarkGame/Plugins/MyPlugin/**`
- `D:/Dark/UnrealEngine/Engine/Intermediate/Build/**`
- `D:/Dark/UnrealEngine/Engine/Saved/UnrealBuildTool/**`
- `D:/Dark/UnrealEngine/Engine/Saved/Logs/**`
```

这三条例外仍与角色、`write_face` 和 `write_scope` 取交集，不自动扩大任何任务权限。两个任务共享同一产物写面仍会产生并发冲突，应串行编译或使用原有独立构建环境；不能隐瞒产物写面来规避冲突。只读角色不因此变为可写角色。

禁止直接修改 Engine 源码、构建脚本、配置或 `InstalledBuild.txt`；`Engine/**`、包含 Engine 的宽泛 Game glob、任意 `Engine/Binaries/**` 和其它 Intermediate/Saved 路径不属于例外。例外目录或其子路径经 junction 指向源码/其它未授权路径时仍拒绝。不得为编译自行开启 `engine_writable`。

本轮不授权重建 UBT 工具本身或引擎二进制。`Build.bat`/`RunUBT` 包装器若需要此类写入，必须报告具体路径，不能仅因命令名包含 UBT 就获得额外权限。可优先调用现有 `UnrealBuildTool.dll`；不能通过复制/修改 UBT 或伪造安装版标记绕过限制。

使用 `mw_run_detached` 时建议把 `run_dir` 显式放在控制工作区。如果 `cwd` 在 Engine 且未指定 `run_dir`，默认 `.mw/runs` 会落入不允许的 Engine 路径而被拒绝。调用 UBT 的 argv 中出现 Engine 路径不等于写入该路径；显式附带源码重定向/复制仍会被检查。

这些是路径权限和任务准入规则，不是对 UBT 进程全部副作用的 OS 级隔离。真实 UBT/UHT/插件加载是否通过、是否还需要其它生成路径，须在业务 key 中实际验证；遇到额外路径应报告，不在本规则中默许。

## Engine 只读时的代码规范

1. 所有引擎扩展落在 Game 的插件或模块中。每份需要扩展的原实现用项目自己的包装代码文件引用原 Engine 代码，仅维护新增、替换或接入行为。
2. 优先使用公开 API、继承、委托和组合。确实需要复用原实现翻译单元时，包装文件引用原文件，局部宏在引用后清理，并验证符号导出、重复定义、私有依赖和构建条件。不要机械地把任意 `.cpp` include 进来。
3. 禁止复制整份或部分 Engine 实现到 Game、另一个 Engine 目录或任意临时目录再修改；重命名副本也违反规范。工具链中换一个可写引擎并不构成例外。
4. 无法安全扩展时，记录缺少的扩展点并交给 PM 处理。不得通过复制源码或自行打开 `engine_writable` 绕过约束。

PM 和 Worker 每轮系统提示都会获得当前权限与上述规范；TS 手动派发和 Python/Codex PM 派发的 `task.md` 都会注入同一规则。

## 验收与保证边界

任务卡与审查记录必须列出每个包装文件、它引用的真实上游文件/API、增量行为及受影响目标的编译结果。PM 复核 diff，确认没有引擎实现副本和未经授权的 Engine 修改；单有任务结束、未改原引擎或提示词注入不能视为这项验收通过。

运行时拦截 `write` / `edit`、现有 shell 分析器能识别的写入，以及 `mw_run_detached` 的相同显式目标；显式 `cp` / `Copy-Item` 等复制源码命令会被拒绝。复制判据保守覆盖整个 Engine 根，包括三类产物目录中的 `.cpp`/`.h` 等源码形态文件和目录源；产物可写不意味着此类复制获得豁免。普通读取和复制非源码二进制不因此被禁止。

这不是操作系统沙箱。任意 Python/Node/外部程序、动态 shell 目标、脚本内部的间接复制和语义改写不能仅凭命令扫描得到绝对保证；这些仍需操作系统写隔离与代码审查。框架不声称能自动证明任意代码均符合包装规范。

源码改动需要通过现有 MW 扩展构建安装流程并重新加载 PM/Worker 后，才会影响运行中的窗口。新 Guard 每次操作重读配置；Worker 启动时解析的任务写入面仍会保留原限制，因此授权变更后应重新派发 Worker。

## 本次核对的 ueperf-platform 配置

2026-11-17 只读核对 `E:\MWWS\UEPerformanceFlow\.agenticdoc\target.yml`：v1 dual，Game 为 `D:\Dark\DarkGame`，Engine 为 `D:\Dark\UnrealEngine`，未配置 `engine_writable`。其 spec 明确排除引擎源码改造。

旧实现中两个根都可被任务写入声明授权，没有独立的 Engine 权限开关；Python dual 派发也缺少工作区规范注入。加入权限开关后，该配置默认引擎源码只读；UBT 产物按上文窄例外和任务写面处理。未改动外部项目的任务状态、既有副本、配置或正在运行的进程；存量代码是否违反规范需要在该 key 的 PM 流程中另外审计。本文源码行为需安装更新并重载后才生效，不代表本轮已经部署或完成真实 UE 构建。
