# dual 模式的引擎权限与扩展规范

Game 是功能开发工作区。`engine_writable: false` 时，UE 原有编译和运行可使用下列生成路径。Worker 的写权限仍由任务卡 `write_face` 和 `write_scope` 限定。

在控制工作区的 `.agenticdoc/target.yml` 配置：

```yaml
active: dual
dual:
  game: 'D:\Dark\DarkGame'
  engine: 'D:\Dark\UnrealEngine'
  engine_writable: false
```

已有 v1 平铺格式在 `engine` 同级写 `engine_writable: false`。缺省等同于 `false`；只有 YAML 布尔 `true` 授予写权限，字符串 `"true"`、数字和 null 均拒绝。开启权限时必须已经配置 dual Engine 路径。环境变量可覆盖根路径，但不单独授予 Engine 写权限。

Engine 授权与任务写入面取交集。`false` 的源码保护优先于 `allow_foreign_write` 和宽泛 glob。路径按真实位置判断，包括通过 junction 指向的路径以及嵌套在 Game 或控制工作区中的 Engine。声明覆盖受保护路径时，派发返回 `write-face-read-only`。`write_face_deny` 不能缩减宽泛声明以取得授权。

PM 在 `false` 下规划 Game 侧包装与适配，在 `true` 下可以规划授权范围内的直接 Engine 修改；两种配置均不覆盖项目/spec/任务卡的限制。项目明确“不改引擎”时，即使路径权限为 `true`，PM 也不能据此修改引擎或自行扩大配置。每轮重新读取权限，重派发会替换旧 profile；`false → true → false` 不继承上一种状态的提示与授权。

## UE 编译与运行产物

保持 `engine_writable: false` 时，以下目录接受构建或运行产物的写面声明。路径相对于配置的 Engine 仓库根，例如 `D:/Dark/UnrealEngine`。

| 相对目录 | 典型内容 |
| --- | --- |
| `Engine/Intermediate/**` | 编译和 UHT 中间产物、规则程序集、项目文件 |
| `Engine/Saved/**` | 生成配置、日志、运行缓存 |
| `Engine/DerivedDataCache/**` | 派生数据缓存 |
| `Engine/Programs/UnrealBuildTool/**` | 源码版 UBT 的默认日志 |
| `Engine/Binaries/Win64/**`、`Linux/**`、`LinuxArm64/**`、`Mac/**`、`DotNET/**` | 对应目标生成的二进制，包括 UBT 输出 |
| `Engine/Plugins/<插件目录>/{Binaries,Intermediate,Saved}/**` | 现有 `.uplugin` 所在目录的构建和运行产物 |
| `Engine/Source/Programs/<项目目录>/{bin,obj,uatbin,uatobj}/**` | 现有 `.csproj` 所在目录的编译产物 |

任务卡必须声明实际所需的产物写面，例如：

```markdown
## 写入允许面
- `D:/Dark/DarkGame/Plugins/MyPlugin/**`
- `D:/Dark/UnrealEngine/Engine/Intermediate/Build/**`
- `D:/Dark/UnrealEngine/Engine/Saved/UnrealBuildTool/**`
- `D:/Dark/UnrealEngine/Engine/Saved/Logs/**`
```

角色、`write_face` 和 `write_scope` 同时适用。共享产物路径参与现有并发冲突检查。编译任务可以声明实际涉及的子目录，或使用各自的生成目录。

Engine 源码、插件源码、构建脚本、输入配置、`Binaries/ThirdParty` 和 `InstalledBuild.txt` 保持受保护。`Engine/**`、`Engine/Binaries/**` 及覆盖 Engine 的 Game glob 会被拒绝。生成目录或其子路径经 junction 指向受保护路径时也会拒绝。

Windows Dual 同时支持以下仓库外生成路径。声明包含字面版本和所需的字面目录名，例如 `%LOCALAPPDATA%/UnrealEngine/5.8/Saved_RenderPerformanceT019/**`。展开环境变量后将绝对路径写入任务卡。

- 本机用户的 `AppData/Local/UnrealEngine/<major.minor>/Saved/**` 和 `Saved_<suffix>/**`，以及 `UnrealEngine/Common/DerivedDataCache/**`。
- 本机用户的 `AppData/Local/UnrealBuildTool/**`，供安装版 UBT 保存日志。
- `%ProgramData%/Epic/NotAllowedUnattendedBugReports` 单个已存在的零字节文件，由 Editor 原生维护。直接工具写入、周围目录和同名前缀文件均拒绝。

使用 `mw_run_detached` 时建议把 `run_dir` 显式放在控制工作区。如果 `cwd` 在 Engine 且未指定 `run_dir`，默认 `.mw/runs` 会落入不允许的 Engine 路径而被拒绝。调用 UBT 的 argv 中出现 Engine 路径不等于写入该路径；显式附带源码重定向/复制仍会被检查。

这些规则用于任务准入、并发判断和工具可识别的路径检查。进程实际写入仍由 Windows 权限决定。具体引擎分支、插件或 SDK 可能产生额外路径，实际编译和 Editor 启动结果由业务 key 验证。

## 仓库外额外可写根

除 `control_root` / `game_root` / `engine_root` 之外，dual 项目可以在 `.agenticdoc/target.yml` 声明一至多个额外可写根，用于 `D:/Dark/Saved`、`D:/Dark/Agents/temp` 这类仓库外目录。声明只是把外部目录纳入“可被任务写面授权”的候选根，不扩大 Game 根，也不改变 Engine 只读。

v1 平铺 dual 的顶层声明：

```yaml
mode: dual
game: 'D:\Dark\DarkGame'
engine: 'D:\Dark\UnrealEngine'
additional_write_roots:
  - 'D:/Dark/Saved'
  - 'D:/Dark/Agents/temp'
```

v2 的 canonical 位置是 `dual:` 块内的同名键：

```yaml
active: dual
dual:
  game: 'D:\Dark\DarkGame'
  engine: 'D:\Dark\UnrealEngine'
  additional_write_roots:
    - 'D:/Dark/Saved'
```

v2 `active: dual` 同时接受顶层声明（读侧兼容用户给出的形式），写侧以 `dual.additional_write_roots` 为 canonical；同一文件两处并存会被拒绝，不做隐式优先级。`active: single` 与 `active: partition` 下的顶层声明被拒绝，因为这两种模式没有 dual 写面根可追加。parked 的 `dual:` 块不参与解析，其中的声明不改变当前模式行为；`mw target on` 切回 dual 后声明才生效。

声明值必须是非空列表，每项是平台原生绝对路径字符串。以下情况在配置解析期以 `invalid-config` 拒绝，并在消息中点名字段与原因：相对路径、空字符串、非字符串、非列表、`additional_write_roots:` 后无值。路径按最终根做 realpath、8.3 短名、junction 与大小写归一后再比较，因此下列重叠同样拒绝：

- 归一后重复的根（大小写、短名或尾部分隔符差异不再算作两个根）；
- 额外根之间相等或互相包含；
- 额外根与 control / game / engine 根相等、包含或被包含；
- 额外根本身经 junction 指向 Engine 或 Game（归一后落回该根，按上一条处理）。

`MW_TARGET_GAME` / `MW_TARGET_ENGINE` 覆盖根路径后，防重叠检查基于最终解析出的根，而不是文件里的原始值。`additional_write_roots: []` 与未声明等价：不产生配置字段，也不改任何输出。

额外根是独立可写根，不会把 Game 根扩展到外部目录，也不授予任何 Engine 写权限。声明之后任务卡仍须在 `## 写入允许面` 写出目标路径；卡片只接受已声明根内的路径。未声明的外部绝对路径、含 `..` 的上跳路径、经 junction 指向 Engine 的路径继续使用现有拒绝码：`write-face-outside-base`、`write-face-escape`、`write-face-read-only`。Engine 的只读根、构建产物例外和 deny 判定顺序保持不变。

宿主派发（TS PM 与 Python PM/conductor）把已声明的根追加到写面根集合后判定卡片；Worker 启动时自行重解析同一份 `target.yml` 取得写根，宿主不通过环境变量或参数向 Worker 注入写根。额外根只进入允许侧：`bashWriteDenyReason` 的 deny 判据、`.git/**` 拒绝、其他 key 与 PM 状态文件的隔离线，以及 `worker_file` 通道都不因声明而放宽。

未声明或声明为空列表时，profile、`mw target show` 摘要、投影、read-scope、doctor `config` 段与探针缓存 fingerprint、以及现有 golden 保持逐字节不变。本特性不新增 CLI 参数、不新增环境变量、不自动创建外部目录，也不扩展读面：额外根是写面授权，读取这些目录仍受任务卡读范围限制。

PM profile 与 `mw target show` 在 dual 且已声明时逐条列出额外根（无声明时 profile 不新增行）。`mw target off`、`mw target clear`、`mw partition set|on|clear` 在把 `active` 切离 dual 或迁移到 v2 之前，先把顶层声明搬进 `dual:` 块再写盘，避免留下 `active: single|partition` 加顶层声明的非法组合；遇到顶层与块内并存、缺少 `dual:` 块或 flow/inline 列表等不支持的布局时，命令在写盘前失败、零写入并给出修复方式。v1→v2 迁移把声明保留到 `dual:` 块内，`mw target set|on` 不切离 dual，按现有行级写入保留声明。

## Engine 只读时的代码规范

1. 所有引擎扩展落在 Game 的插件或模块中。每份需要扩展的原实现用项目自己的包装代码文件引用原 Engine 代码，仅维护新增、替换或接入行为。
2. 优先使用公开 API、继承、委托和组合。确实需要复用原实现翻译单元时，包装文件引用原文件，局部宏在引用后清理，并验证符号导出、重复定义、私有依赖和构建条件。不要机械地把任意 `.cpp` include 进来。
3. 禁止复制整份或部分 Engine 实现到 Game、另一个 Engine 目录或任意临时目录再修改；重命名副本也违反规范。工具链中换一个可写引擎并不构成例外。
4. 无法安全扩展时，记录缺少的扩展点并交给 PM 处理。不得通过复制源码或自行打开 `engine_writable` 绕过约束。

PM 和 Worker 每轮系统提示都会获得当前权限与上述规范；TS 手动派发和 Python/Codex PM 派发的 `task.md` 都会注入同一规则。

## 验收与保证边界

任务卡与审查记录必须列出每个包装文件、它引用的真实上游文件/API、增量行为及受影响目标的编译结果。PM 复核 diff，确认没有引擎实现副本和未经授权的 Engine 修改；单有任务结束、未改原引擎或提示词注入不能视为这项验收通过。

运行时检查 `write` / `edit`、shell 分析器识别的写入和 `mw_run_detached` 的显式目标。复制检查覆盖整个 Engine 根，包括生成目录中的 `.cpp`、`.h` 和目录源。普通读取和非源码二进制复制继续使用原任务范围。

这不是操作系统沙箱。任意 Python/Node/外部程序、动态 shell 目标、脚本内部的间接复制和语义改写不能仅凭命令扫描得到绝对保证；这些仍需操作系统写隔离与代码审查。框架不声称能自动证明任意代码均符合包装规范。

源码改动需要通过现有 MW 扩展构建安装流程并重新加载 PM/Worker 后，才会影响运行中的窗口。新 Guard 每次操作重读配置；Worker 启动时解析的任务写入面仍会保留原限制，因此授权变更后应重新派发 Worker。

## 本次核对的 ueperf-platform 配置

2026-11-17 只读核对 `E:\MWWS\UEPerformanceFlow\.agenticdoc\target.yml`：v1 dual，Game 为 `D:\Dark\DarkGame`，Engine 为 `D:\Dark\UnrealEngine`，未配置 `engine_writable`。其 spec 明确排除引擎源码改造。

旧实现中两个根都可被任务写入声明授权，没有独立的 Engine 权限开关；Python dual 派发也缺少工作区规范注入。加入权限开关后，该配置默认引擎源码只读；UBT 产物按上文窄例外和任务写面处理。未改动外部项目的任务状态、既有副本、配置或正在运行的进程；存量代码是否违反规范需要在该 key 的 PM 流程中另外审计。本文源码行为需安装更新并重载后才生效，不代表本轮已经部署或完成真实 UE 构建。
