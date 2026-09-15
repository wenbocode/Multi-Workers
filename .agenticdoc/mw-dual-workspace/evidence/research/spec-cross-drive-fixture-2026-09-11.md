# Research: 跨盘真机取证（Game=F:\ProjectH / Engine=E:\CFHEngine）（spec）

## 决策问题

关闭 spec §2.2 两项「未实证」性能断言、§4 风险 1（cwd 沙箱）与风险 2（跨盘 junction realpath）、部分回答待确认 8（长路径）；为 AC-002/AC-004 的跨盘前置提供真机 fixture；量化上下文防火墙动机。

## 调研方法与出处

- 用户指定的真实 fixture：Game=`F:\ProjectH`、Engine=`E:\CFHEngine`（2026-09-11 对话指定）。两独立本地卷（Win32_LogicalDisk DriveType=3，E:/F: 各 ~3.7TB）。
- 只读检查：`Get-ChildItem` 顶层列举、pi read 工具读取 `F:\ProjectH\ProjectH.uproject`（全文）。
- 量化计数：`cmd /c dir /s /b F:\ProjectH\Content\*.uasset | find /c /v ""`。
- 写探针：pi write 工具写 `F:\mw-evd-tmp\pi-write-probe.txt`（147 字节，测后删除）。
- Node 实测（node v24.19.0，进程 cwd=H:\git\Multi-Workers）：临时脚本 `fs.appendFileSync` 逐行追加 n=500/盘（H:/F:/E: 各一文件）、`fs.realpathSync`/`realpathSync.native` 跨盘 junction 解析、realpathSync x1000 单次成本、长路径 mkdir/write/read（277/319 字符）。junction 由 `New-Item -ItemType Junction` 创建（F:\mw-evd-tmp\jn→E:、jnH→H:，无需特权）。全部临时物测后清理（Test-Path 验证 4 项均 False）。
- 注册表：`reg query HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled`。

## 发现

1. **fixture 真实性**：`F:\ProjectH\ProjectH.uproject` 存在（UE5 工程，~84 个 module，DLSS/Wwise/PCG 等 plugin）；`E:\CFHEngine` 为引擎 fork（Engine/、FeaturePacks/、Templates/、Setup.bat、UE5.sln，含 .git）。Game 树 VCS 为 **Perforce**（p4config.txt、.p4ignore，无 .git）；Engine 树为 git。
2. **防火墙量级**：`F:\ProjectH\Content` 下 `.uasset` **1,429,392 个**、`.umap` **2,318 个**（dir /s /b 计数）。单次误读即上下文灾难——deny globs 是刚需不是优化。顶层另见 DerivedDataCache/Intermediate/Binaries/Saved/node_modules/.vs。
3. **pi 工具非 cwd 沙箱**：read 工具从 cwd=H: 跨盘读取 F: 文件成功；write 工具跨盘写 F: 成功。worker（cwd=Game 根）写控制工作区为同机制反向，成立。
4. **appendFileSync 逐行追加实测**（n=500/盘）：H: mean 0.114 / median 0.098 / p95 0.201 / max 0.485 ms；F: mean 0.076 / median 0.061 / p95 0.102 / max 4.985 ms；E: mean 0.086 / median 0.060 / p95 0.115 / max 8.916 ms。**跨盘不劣于同盘**（F:/E: 略快，盘体质差异）；max 尾部为冷启动/AV 扫描。
5. **跨盘 junction realpath**：对 F:→E: junction，`realpathSync` 与 `realpathSync.native` 均返回 E: 目标绝对路径；F:→H: junction 返回 H: 路径。read-scope `normalizeForCompare` 的包含判定跨盘成立：目标树内指向控制盘（或任意盘）的 junction 解析为目标盘路径，**不能经 junction 绕过 scope**（fail-closed 保持）。
6. **realpathSync 单次成本**（跨盘 junction 路径，n=1000）：mean 0.088 / p95 0.110 / max 0.464 ms。
7. **长路径**：本机 `LongPathsEnabled=0x1`；277 与 319 字符路径 plain `mkdirSync`/`writeFileSync`/`readFileSync` 成功。依赖机器级开关；未开启的机器需 `\\?\` 前缀（失败分支本次未测）。

## 结论 → 决策映射

- 发现 4 → spec §2.2 第一条：阈值由「< 100ms（未实证）」重锚定为 p95 < 1ms、max < 50ms（实测 p95 ≤ 0.2ms，余量 >5x）
- 发现 6 → spec §2.2 第二条：现状 realpathSync 基线锚定；改造回归用单测套件前后对照（实施时取证）
- 发现 3 → spec §4 风险 1 关闭
- 发现 5 → spec §4 风险 2 关闭（symlink 需特权未测，design 补）
- 发现 1 → spec §4 待确认 4 扩展：VCS 绑定须考虑 Game=P4 工作区、Engine=git 的混合现实
- 发现 2 → spec §1.3 场景 D 量化锚定；AC-006 deny globs 动机
- 发现 7 → spec §4 待确认 8 部分回答（本机 OK，可移植性 caveat 留 design）
- fixture 记录 → spec §2.1：开发机跨盘验证以 F:/E: 为基准；CI 无第二盘符 → 新增待确认 9（跨盘用例执行环境门控）

## 补充核查（2026-09-11，design 证据复查）

- .gitignore 存在性实测（2026-09-11 Test-Path）：F:\ProjectH 顶层**无** .gitignore（False）、E:\CFHEngine **有**（True）→ design D-004 已知限制（P4 工作区 find/grep 遍历不排除 DDC，依赖输出截断+read-scope caps 限流）的直接依据。
- ProjectH.uproject 的 EngineAssociation 为 GUID `{23E9971E-494F-379B-3DDE-2B87E07A1A55}`（本机注册表绑定引擎，实测读取 2026-09-11）→ design D-014 否决 GUID 发现、采用 {uproject} 占位符的依据。
