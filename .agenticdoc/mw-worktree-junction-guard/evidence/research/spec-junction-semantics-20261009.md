# RQ-1 调研报告：Windows junction/symlink 的删除语义（`%TEMP%` 最小复现）

- key: `mw-worktree-junction-guard` · worker: `wjg-rq1-junction-semantics` · type: research
- 采集时刻: 2026-10-10 (UTC+8)
- 方法: **只读生产树**。全部实验在 `%TEMP%\wjg-rq1\**` 内新建目录完成，真树零触碰（未搭任何指回 `H:\git\Multi-Workers` 的链接、未在真树建/删 worktree、未对真树执行任何 git 破坏命令）。
- 环境（实测）: Windows `10.0.26100.9168`; PowerShell `5.1.26100.9168`; `git version 2.53.0.windows.1` (`D:\Program Files\Git\cmd\git.exe`); GNU coreutils `rm (GNU coreutils) 8.32`（MSYS2/MINGW64，`/usr/bin/rm`）; `node v24.19.0`。
- 本文件是本 worker 唯一写入物；实验目录见 §11。

## TL;DR

1. **在全部被测删除 API 中，只有 `git worktree remove` 会自动穿透 junction，且递归到任意深度**（rc=0、无任何报错、静默）。`cmd /c rmdir <link>`（无 `/S`）、`rmdir /S /Q`、PowerShell `Remove-Item -Recurse -Force`、git-bash `rm -rf`、Node `fs.rmSync(recursive)` 默认**都不穿透**。
2. 但四种**显式路径形态**会让上述"默认不穿透"的 API **穿透一层**：`rm -rf <link>/`、`rm -rf <link>/*`、`Remove-Item -Recurse -Force <link>\*`、`cmd /c rmdir /S /Q <link>\`（尾部反斜杠）。这些形态都是"显式要求解析进链接目标"。
3. **双层链（junction→junction）不会让"不穿透"的 API 自动穿透第二层**——实测它们连第一层都不自动穿（Node 连尾部斜杠也不穿）。只有 `git` 会自动穿两层、三层。
4. `git worktree remove` 穿透的根因**不是** MSYS2 runtime 的 `lstat`（该 runtime 的 `stat` 把 junction 与 symlink **都**报成 `symbolic link`），而是 **git 自带的 `mingw_lstat`**：它把 `IO_REPARSE_TAG_MOUNT_POINT`（junction，tag `0xa0000003`）当作**普通目录**（`S_IFDIR`），只把 `IO_REPARSE_TAG_SYMLINK`（tag `0xa000000c`）当作链接。实测同一 junction：`git status` 报 `?? junc/`（目录）且 `git ls-files -o` 直接列出 `junc/x.txt`；`bash stat` 报 `symbolic link`。
5. **无 `--force` 的 `git worktree remove` 不是防线**：当 junction 名为 `node_modules`（被 `.gitignore` 忽略）时，无 `--force` 同样 rc=0 且照样穿透；只有链接**未被忽略**时才以 rc=128 拒绝。
6. RC≠0 + 部分删除的**充分条件**是对遍历路径上的某个文件持有**独占句柄（不带 `FILE_SHARE_DELETE`）**。只读属性不足以触发；进程 cwd 占用本次也未触发。中止形态与线上逐字一致：`error: failed to delete '<wt>': Invalid argument` + rc=255 + worktree/链接保留 + 目标部分删除。

---

## 1. 实验设计（真树零触碰）

每个 case 独立 fixture，全部位于 `%TEMP%\wjg-rq1\`：

```
<case>\
  target\sub\f1.txt, target\f2.txt        <- 被链接的"真树"目录（A）
  host\                                   <- "宿主"（B）
    link  -> target                       <- junction（由 cmd /c mklink /J 建）
    plain\g.txt, own.txt
```

git worktree 类 fixture（`New-RealTree`）：A 为 git 仓库，`packages\pkgA|pkgB|pkgC` 为已跟踪内容，`node_modules\@scope\linkA|linkB|linkC` 为指向 `packages\*` 的 junction，`node_modules` 写入 `.gitignore`；B 由 `git worktree add --detach <wt> HEAD` 建立，再在 `<wt>\node_modules` 建指向 `A\node_modules` 的 junction：

```
wt\  (git worktree)
  node_modules -> A\node_modules              <- 第 1 层 junction
A\node_modules\@scope\link{A,B,C} -> A\packages\pkg{A,B,C}   <- 第 2 层 junction
```

命中判据统一为 **"A（真树）侧是否被改"**：`Count-Files(A/packages/pkgA)==0` 或 `target\sub\f1.txt` 消失 ⇒ 穿透。

---

## 2. 问题 1：各删除 API 是否穿透（命令原文 + 原始输出）

### 2.1 汇总矩阵（全部本次实测，见 §10 `[VERIFY]`）

| # | 命令原文（`<link>` = junction 路径） | 退出码 | 是否穿透 | 链接自身 | 目标内容 |
|---|---|---|---|---|---|
| 1 | `git worktree remove --force "<wt>"`（`wt\node_modules` 为 junction） | 0 | **是** | 删 | **清空** |
| 2 | `git worktree remove --force "<wt>"`（`wt\node_modules` 为**目录 symlink**） | 0 | 否 | 删 | 完好 |
| 3 | `cmd /c rmdir "<link>"`（**无 `/S`**） | 0 | 否 | 删 | 完好 |
| 4 | `cmd /c rmdir /S /Q "<link>"` | 0 | 否 | 删 | 完好 |
| 5 | `cmd /c rmdir /S /Q "<link>\"`（**尾部反斜杠**） | 0 | **是（1 层）** | 删 | **清空** |
| 6 | `cmd /c rmdir /S /Q "<host>"`（父目录） | 0 | 否 | 随父删 | 完好 |
| 7 | `Remove-Item -Recurse -Force "<link>"` | 0 | 否 | 删 | 完好 |
| 8 | `Remove-Item -Recurse -Force "<host>"`（父目录） | 0 | 否 | 随父删 | 完好 |
| 9 | `Remove-Item -Recurse -Force "<link>\*"`（**通配**） | 0 | **是（1 层）** | 保留 | **清空** |
| 10 | `Remove-Item -Recurse -Force "<link>\"`（尾部反斜杠） | 0 | 否 | 删 | 完好 |
| 11 | `rm -rf "<host>"`（git-bash） | 0 | 否 | 随父删 | 完好 |
| 12 | `rm -rf "<link>"`（git-bash） | 0 | 否 | 删 | 完好 |
| 13 | `rm -rf "<link>/"`（**尾部斜杠**） | 0 | **是（1 层）** | 保留 | **清空** |
| 14 | `rm -rf "<link>/*"`（**通配**） | 0 | **是（1 层）** | 保留 | **清空** |
| 15 | `node -e "fs.rmSync('<host>',{recursive:true})"` | 0 | 否 | 随父删 | 完好 |
| 16 | `node -e "fs.rmSync('<link>',{recursive:true})"` | 0 | 否 | 删 | 完好 |
| 17 | `node -e "fs.rmSync('<link>\\',{recursive:true})"`（尾部反斜杠） | 0 | 否 | 删 | 完好 |
| 18 | 同 13 但 `<link>` 为**目录 symlink** | 0 | **是（1 层）** | 保留 | **清空** |

### 2.2 代表性原始命令与输出

**(1) `git worktree remove --force`（junction）—— 穿透，rc=0，静默**

```
CMD> git worktree remove --force "C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-rq1\e1\wt"
OUT>>>

<<<OUT
RC=0
AFTER :
  wt exists=False
  A/node_modules exists=True
  A/packages/pkgA files=0
  A/packages/pkgB files=0
  A/packages/pkgC files=0
  A/node_modules/plainpkg files=-1
  A/node_modules/@scope=MISSING
git status --porcelain:
 D packages/pkgA/a.txt
 D packages/pkgB/b.txt
 D packages/pkgC/c1.txt
 D packages/pkgC/c2.txt
 D packages/pkgC/c3.txt
```

**(2) `git worktree remove --force`（目录 symlink）—— 不穿透**

```
CMD> git worktree remove --force "...\e11\W1_layer1_symlink\wt"   (wt\node_modules 为 SymbolicLink)
OUT>>>
<<<OUT
RC=0 | AFTER: wt=False @scope=[linkA,linkB,linkC] pkgA=1 pkgB=1 pkgC=[c1.txt,c2.txt,c3.txt] plainpkg=1
```

**(3) `cmd /c rmdir "<link>"`（无 `/S`）—— 不穿透**

```
BEFORE: host=True host_entries=[link,plain,own.txt] host_link=LINK(Junction)->...\target target=True target_files=2 f1=True f2=True
CMD> cmd /c rmdir "<host>\link" (no /S)
OUT>>>
<<<OUT
RC=0
AFTER : host=True host_entries=[plain,own.txt] host_link=MISSING target=True target_files=2 f1=True f2=True
```

**(4) `Remove-Item -Recurse -Force`（父目录 / 链接自身）—— 不穿透**

```
===== E3a : Remove-Item -Recurse -Force "<host>" =====
RC=0 | AFTER : host=False link=MISSING target=True target_files=2 f1=True f2=True
===== E3b : Remove-Item -Recurse -Force "<host>\link" =====
RC=0 | AFTER : host=True entries=[plain,own.txt] link=MISSING target=True target_files=2 f1=True f2=True
```

**(5) `rmdir /S /Q`（父目录 / 链接 / 链接+尾反斜杠）**

```
===== E4a : cmd /c rmdir /S /Q "<host>" =====
RC=0 | AFTER : host=False link=MISSING target_files=2 f1=True
===== E4b : cmd /c rmdir /S /Q "<host>\link" =====
RC=0 | AFTER : host=True entries=[plain,own.txt] link=MISSING target_files=2 f1=True
===== E7m : cmd /c rmdir /S /Q "<host>\link1\" (trailing backslash) =====
RC=0 | AFTER: mid_entries=[] L2=MISSING deep_files=2     <- 第一层被穿透，第二层未穿
```

**(6) `rm -rf`（git-bash）—— 普通形态不穿透；尾斜杠/通配穿透一层**

```
===== E5a : rm -rf "<host>" =====   RC=0 | host=False target_files=2 f1=True
===== E5b : rm -rf "<host>/link" ===== RC=0 | host=True link=MISSING target_files=2 f1=True
===== E7f : rm -rf "<host>/link1/" (trailing slash) ===== RC=0 | host=True L1 保留 mid_entries=[] L2=MISSING deep_files=2
===== E7g : rm -rf "<host>/link1/*" =====               RC=0 | host=True L1 保留 mid_entries=[] L2=MISSING deep_files=2
```

**(7) Node `fs.rmSync(recursive)` —— 不穿透（含尾部反斜杠）**

```
===== E6a : node fs.rmSync("<host>",{recursive:true}) ===== OUT>>> NODE_OK <<< RC=0 | host=False target_files=2 f1=True
===== E6b : node fs.rmSync("<host>/link",{recursive:true}) ===== RC=0 | host=True link=MISSING target_files=2 f1=True
===== E7r : node fs.rmSync("<host>/link1/", recursive) ===== RC=0 | mid_entries=[link2,m.txt] L2=Junction deep_files=2
```

**(8) 一行汇总（本次实测，可复算）**

```
[VERIFY] pen(cmd-rmdir-link)=no rc=0 link_left=no
[VERIFY] pen(cmd-rmdirS-parent)=no rc=0 link_left=no
[VERIFY] pen(cmd-rmdirS-link)=no rc=0 link_left=no
[VERIFY] pen(cmd-rmdirS-link-trailing)=yes rc=0 link_left=no
[VERIFY] pen(ps-recurse-parent)=no rc=0 link_left=no
[VERIFY] pen(ps-recurse-link)=no rc=0 link_left=no
[VERIFY] pen(ps-recurse-link-glob)=yes rc=0 link_left=yes
[VERIFY] pen(rmrf-parent)=no rc=0 link_left=no
[VERIFY] pen(rmrf-link)=no rc=0 link_left=no
[VERIFY] pen(rmrf-link-trailing)=yes rc=0 link_left=yes
[VERIFY] pen(rmrf-link-glob)=yes rc=0 link_left=yes
[VERIFY] pen(node-rm-parent)=no rc=0 link_left=no
[VERIFY] pen(node-rm-link)=no rc=0 link_left=no
[VERIFY] pen(node-rm-link-trailing)=no rc=0 link_left=no
[VERIFY] pen(rmrf-link-symlink-trailing)=yes rc=0 link_left=yes
```
---

## 3. 问题 2：判据总结与可解释原因（reparse point 语义）

### 3.1 判据表

| 类别 | 删除 API | 对 junction / 目录 symlink | 原因 |
|---|---|---|---|
| **自动穿透** | `git worktree remove`（含 `--force`；仅对 **junction**） | 穿透，递归任意深度 | git 自带 `mingw_lstat` 把 `IO_REPARSE_TAG_MOUNT_POINT` 映射为**目录**，`remove_dir_recurse` 因此 `opendir/readdir` 进入目标树 |
| **纯路径形态穿透**（显式解析进链接） | `rm -rf <link>/`、`rm -rf <link>/*`、`Remove-Item -Recurse -Force <link>\*`、`cmd /c rmdir /S /Q <link>\` | 穿透**一层**（含 symlink） | 路径解析器对末段带分隔符/通配的路径执行"打开链接目标作为当前目录"，与递归枚举的 reparse 检测无关 |
| **不穿透（递归枚举型）** | `cmd /c rmdir <link>`、`cmd /c rmdir /S /Q <link>`、`rmdir /S /Q <父>`、`Remove-Item -Recurse -Force <link或父>`、`rm -rf <link或父>`、Node `fs.rmSync(<link或父>, recursive)` | 不穿透 | 每个条目在删除前做 `lstat`/reparse 检测；命中 reparse point 即**只删链接条目**，不进入目标（MSYS2 与 Node 都如此） |

**一句话判据**：
- "**递归删除 + 逐条目 reparse 检测**" ⇒ 不穿透（git 例外，见下）；
- "**显式把链接当目录打开**"（尾分隔符/通配） ⇒ 穿透一层；
- "**git 的目录遍历**" ⇒ 把 junction 当普通目录 ⇒ 穿透任意层。

### 3.2 reparse point 的实测身份

```
### PowerShell Get-Item -Force
PS junc : Attr=Directory, ReparsePoint LinkType=Junction     Target=...\e13\tgt
PS sym  : Attr=Directory, ReparsePoint LinkType=SymbolicLink Target=...\e13\tgt
### cmd dir /AL
2026/10/10  11:28    <JUNCTION>     junc [...\e13\tgt]
2026/10/10  11:28    <SYMLINKD>     sym  [...\e13\tgt]
### fsutil reparse tag
fsutil junc : 0xa0000003      (IO_REPARSE_TAG_MOUNT_POINT)
fsutil sym  : 0xa000000c      (IO_REPARSE_TAG_SYMLINK)
```

### 3.3 关键修正：不是 MSYS2 runtime 的 lstat，是 git 自己的 `mingw_lstat`

上一份取证报告（`in1-junction-incident-20261009.md` §3.1）写"MSYS2 的 `lstat` 只把 SYMLINK 映射为 `S_ISLNK`"——**结论（git 把 junction 当目录）正确，归因不准确**。本次实测：

```
### MSYS2 git-bash stat / ls -l（msys-2.0.dll runtime 的 POSIX 视图）
lrwxrwxrwx ... e13/junc -> /tmp/wjg-rq1/e13/tgt
lrwxrwxrwx ... e13/sym  -> /tmp/wjg-rq1/e13/tgt
stat -c '%F' : symbolic link | ...\junc
               symbolic link | ...\sym
### git 的视图（同一目录，被 git 当仓库）
git status --porcelain:
?? junc/          <- 目录语义
?? sym            <- 链接语义
?? tgt/
git ls-files -o --exclude-standard -z:   junc/x.txt|sym|tgt/x.txt|
```

- **MSYS2 runtime**（`bash`/`stat`/`rm.exe`）把 junction 与 symlink **都**报成 `symbolic link` ⇒ 所以 `rm -rf <link>` 不穿透。
- **git** 用的是自带的 `compat/mingw.c: mingw_lstat`：只把 tag `0xa000000c` 当链接，tag `0xa0000003` 当普通目录。`git ls-files -o` 直接列出 `junc/x.txt`（**git 的目录遍历已经走进了 junction 目标**）就是这一映射的直接指纹。
- 因此 `git worktree remove` 的 `remove_dir_recurse` 进入 junction 目标并逐项 `unlink`/`rmdir`；目标里若还有 junction，继续进入 ⇒ **任意深度穿透**（见 §4）。

---

## 4. 问题 3：双层链（junction→junction）是否让"不穿透"的 API 也穿透？

**结论：不会。** 双层链本身不放大穿透；只有 `git` 会自动穿任意层。逐个验证（fixture：`host\link1 -> mid`，`mid\link2 -> deep`）：

| API | 形态 | 第 1 层 | 第 2 层 |
|---|---|---|---|
| `Remove-Item -Recurse -Force <host>` | 递归父目录 | 否 | 否 |
| `cmd /c rmdir <host>\link1` | 无 `/S` | 否 | 否 |
| `cmd /c rmdir /S /Q <host>` | 父目录 | 否 | 否 |
| `rm -rf <host>` | 父目录 | 否 | 否 |
| `node fs.rmSync(<host>, recursive)` | 父目录 | 否 | 否 |
| `Remove-Item -Recurse -Force <mid>` | 直接删第 1 层目标 | —（mid 被删） | 否（deep 完好） |
| `rm -rf <mid>` | 同上 | — | 否 |
| `node fs.rmSync(<mid>, recursive)` | 同上 | — | 否 |
| `cmd /c rmdir /S /Q <mid>` | 同上 | — | 否 |
| `cmd /c rmdir /S /Q <host>\link1\` | **尾反斜杠** | **是** | 否 |
| `rm -rf <host>/link1/` | **尾斜杠** | **是** | 否 |
| `rm -rf <host>/link1/*` | **通配** | **是** | 否 |
| `Remove-Item -Recurse -Force <host>\link1\*` | **通配** | **是** | 否 |
| `rm -rf <host>/link1/link2/` | 显式写全两层 + 尾斜杠 | 是 | **是**（显式，非自动） |

原始输出片段：

```
===== E7a (Remove-Item -Recurse -Force <host>) =====
AFTER : host=False L1=MISSING | mid=True mid_entries=[link2,m.txt] L2=Junction | deep=True deep_files=2

===== E7f (rm -rf <host>/link1/  trailing slash) =====
RC=0 | AFTER: host=True L1=LINK(Junction)->mid | mid=True mid_entries=[] L2=MISSING | deep=True deep_files=2
```

**git 侧：任意深度自动穿透（实测）**

```
[VERIFY] git(G1) kind=junction force=True  rc=0 err=-        pen=yes wt_left=no @scope=[MISSING] pkgC=[]
[VERIFY] git(G2) kind=symlink  force=True  rc=0 err=-        pen=no  wt_left=no @scope=[linkA,linkB,linkC] pkgC=[c1.txt,c2.txt,c3.txt]
[VERIFY] git(G3) kind=none     force=True  rc=0 err=-        pen=no  wt_left=no @scope=[linkA,linkB,linkC] pkgC=[c1.txt,c2.txt,c3.txt]

W3 混合链（第 1 层 junction、第 2 层 symlink）：RC=0 | @scope=[MISSING] pkgA=1 pkgB=0 pkgC=[]
   -> 第 2 层 junction(pkgB/pkgC) 被穿，第 2 层 symlink(pkgA) 未被穿
W5 三层 junction 链（wt -> A/nm -> mid -> deep）：RC=0 | mid=[] deep=[] lv3=MISSING wt=False
```

**要点**：junction 与目录 symlink 在被删 API 上**不等价**——`git` 只穿 junction；`rm -rf <link>/` 对两者都穿。任何"检测链接"的 guard 必须能区分 `LinkType`（`Junction` vs `SymbolicLink`；tag `0xa0000003` vs `0xa000000c`），否则要么漏 junction、要么对 symlink 过度拦截。

---

## 5. 问题 4：复现"撞锁中止"（RC≠0 + 部分删除）

### 5.1 可复现步骤（最小）

1. 建 git worktree `wt`，并在 `wt\node_modules` 建指向真树 `A\node_modules` 的 junction；`A\node_modules\@scope\link{A,B,C}` 为指向 `A\packages\pkg{A,B,C}` 的 junction。
2. 用**独占句柄**打开 `A\packages\pkgC\c2.txt`（不带 `FILE_SHARE_DELETE`）：

```powershell
$h = [System.IO.File]::Open("$A\packages\pkgC\c2.txt", [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)
```

3. 保持句柄打开，执行 `git worktree remove --force <wt>`。
4. 关闭句柄。

### 5.2 实测结果（与线上逐字一致）

```
CMD> git worktree remove --force "...\e8\L1_exclusive_lock\wt"
OUT>>>
git : error: failed to delete 'C:/Users/wenbozhou/AppData/Local/Temp/wjg-rq1/e8/L1_exclusive_lock/wt': Invalid argument
<<<OUT
RC=255
AFTER: wt=True A_nm=True @scope=[linkC] pkgA=0 pkgB=0 pkgC=[c2.txt,c3.txt] plainpkg=1
```

- 报错文本与 2026-10-09 线上（`jsonl:144`）**逐字相同**（`failed to delete '<worktree>': Invalid argument`，rc=255）。
- 形态一致：worktree 保留 + junction 保留（`@scope=[linkC]`，即前两条已删、最后一条保留）+ 前两条链接目标被清空（`pkgA=0 pkgB=0`）+ 最后一条目标部分删除（`pkgC` 删了 `c1`，锁在 `c2`）。
- 线上真树 `packages/tui` 只删 156/236 的形态，就是"中止点落在最后一条 junction 的目标里"的同构结果。

### 5.3 是否**需要**独占锁？

| 触发条件 | rc | 是否中止 + 部分删除 |
|---|---|---|
| 独占句柄（`FileShare::None`）在目标文件上 | **255** | **是** |
| 独占句柄在**未跟踪**文件上 | **255** | **是** |
| **只读属性**（`IsReadOnly=$true`） | 0 | 否（git 会清只读后删除） |
| 进程 cwd 占用该目录（子进程活着，cwd = `pkgC`） | 0 | 否（本次未触发） |

**结论**：中止的**充分条件是有文件句柄不带 `FILE_SHARE_DELETE`**（独占锁即可复现）；只读属性**不足**。因此"线上是哪个句柄"不必坐实——只要遍历路径上存在这样一个句柄，就会产生 RC=255 + 部分删除。

### 5.4 中止点与 readdir 顺序（实测）

锁不同文件 → 残留集合不同，证明中止确实发生在"锁文件所在的递归位置"，且**未处理到的条目全部幸存**：

```
M1 lock pkgC\c1.txt : RC=255 | @scope=[linkC] pkgA=[] pkgB=[] pkgC=[c1.txt,c2.txt,c3.txt]
M2 lock pkgC\c3.txt : RC=255 | @scope=[linkC] pkgA=[] pkgB=[] pkgC=[c3.txt]
M3 lock pkgA\a.txt  : RC=255 | @scope=[linkA,linkB,linkC] pkgA=[a.txt] pkgB=[b.txt] pkgC=[c1..c3]
M4 lock plainpkg    : RC=255 | @scope=[MISSING] pkgA=[] pkgB=[] pkgC=[] plainpkg=1
```

### 5.5 中止与 junction 无关（重要）

无 junction 的干净 worktree 上，锁住一个**真实文件** `wt\.gitignore`：

```
### N1: worktree with NO junction, lock wt\.gitignore
RC=255 | wt=True A_packages_pkgA=1
```

⇒ **锁是 RC≠0 的原因，junction 是"跨树扩大战果"的原因**，二者正交。guard 防的是后者；前者说明"任何依赖 `git worktree remove` 成功退出"的流程都不可靠。

---

## 6. 问题 5：`git worktree remove`（**不带 `--force`**）能否作为弱防线？

**结论：不能。** 危险场景（junction 名为 `node_modules`，被 `.gitignore` 忽略）恰好是它**放行**的场景。

| 场景 | 命令 | 结果 |
|---|---|---|
| junction `node_modules`（**被 gitignore**） | `git worktree remove <wt>` | **rc=0；穿透：`@scope=[MISSING] pkgA=0 plainpkg=-1`** |
| junction `mylink`（**未忽略**） | `git worktree remove <wt>` | rc=128 `fatal: '<wt>' contains modified or untracked files, use --force to delete it`；零删除 |
| 干净 worktree（无链接） | `git worktree remove <wt>` | rc=0；真树零损伤 |
| 普通未跟踪文件 | `git worktree remove <wt>` | rc=128 拒绝；零删除 |
| 已跟踪文件被修改 | `git worktree remove <wt>` | rc=128 拒绝；零删除 |
| 同第 1 行 + `--force` | `git worktree remove --force <wt>` | rc=0；穿透（同第 1 行） |

原始输出：

```
===== N1 : junction node_modules (gitignored) no --force =====
CMD> git worktree remove "...\wt"
RC=0 | wt=False A/nm=True @scope=[MISSING] pkgA=0 plainpkg=-1 extra=[MISSING]
===== N2 : junction mylink (NOT gitignored) no --force =====
OUT>>> git : fatal: '...\wt' contains modified or untracked files, use --force to delete it
RC=128 | wt=True A/nm=True @scope=[linkA,linkB,linkC] pkgA=1 plainpkg=1 extra=[mylink,packages,.git,.gitignore]
===== N3 : clean worktree no --force =====
RC=0 | wt=False @scope=[linkA,linkB,linkC] pkgA=1 plainpkg=1
```

原因：`git worktree remove` 的 clean 判定用 `ls-files --others --exclude-standard`，**忽略被 gitignore 的路径**。真实仓库的 `node_modules/` 正是被忽略的，所以 `--force` 省不省没有区别。**guard 必须在命令执行前拦截，不能指望 git 自己拒绝。**

---

## 7. 支撑实现的最小可复算判据（检测片段，均已实测）

### 7.1 枚举工作树内的 reparse point（不跟随链接，避免死循环）

PowerShell 5.1 的 `Get-ChildItem -Recurse` 实测**不会**跟随 junction（返回 `link` 条目本身、不进入目标）：`count=3 entries=[\link, \plain, \plain\g.txt]`。但为稳妥（其它实现/版本差异），guard 应使用显式栈遍历并在命中 reparse point 时不再下钻：

```powershell
$links = @()                               # 元素含 Path / LinkType / Target
$stack = New-Object System.Collections.Stack; $stack.Push($worktree)
while ($stack.Count -gt 0) {
  foreach ($e in (Get-ChildItem -LiteralPath $stack.Pop() -Force -ErrorAction SilentlyContinue)) {
    if ($e.Attributes.ToString() -match 'ReparsePoint') {
      $links += [pscustomobject]@{ Path=$e.FullName; LinkType=$e.LinkType; Target=$e.Target }
    } elseif ($e.PSIsContainer) { $stack.Push($e.FullName) }
  }
}
```

实测输出（单条 junction）：`path=...\host\link type=Junction target=...\target`，**链接路径与目标均可直接照抄进报错文本**（支撑 AC-002）。

### 7.2 目标是否在仓库内（AC-006 fail-closed）

```powershell
$inside = [System.IO.Path]::GetFullPath($link.Target).StartsWith(
  [System.IO.Path]::GetFullPath($repoRoot) + [System.IO.Path]::DirectorySeparatorChar)
```

实测：链接指向 temp 目标、`repoRoot` 为另一个 temp 目录 ⇒ `insideRepo=False`（可判可拒）。

### 7.3 断链检测（AC-009 / AC-011）

```
junction ...\e16\broken -> ...\e16\tgt   (tgt 已被删)
Test-Path broken      = True        <- 对 reparse point 本身返回 True（不能当"目标完好"）
Get-Item -Force broken: LinkType=Junction Target=...\tgt （目标路径可读）
Test-Path <target>    = False       <- 目标丢失判据
```

### 7.4 语料锚点

`%TEMP%\mwvg-t5-probe\node_modules`（`in1` §4 遗留的探针 junction）本次实测 **已不存在**（`legacy probe exists = False`），不能作为现存阳性样本；AC-009 的语料需在测试中现造（或在其它 %TEMP% 残留上复核）。

---

## 8. 对 AC-001..AC-007 判据表述的直接支撑

| AC | 判据表述（可由本报告直接写定） | 依据 |
|---|---|---|
| **AC-001** | Guard 在 `git worktree remove`（含 `--force`）执行前，递归枚举 worktree 内 `Attributes` 含 `ReparsePoint` 的条目；**命中任一即 block**（在 `LinkType=Junction` 时是硬命中；symlink 经 git 本身不穿透，但经"尾分隔符/通配"形态会，故建议一并 block）。理由是执行的副作用不可逆且跨树 | §2（1/2/5/9/13/14）、§4 |
| **AC-002** | block 文本须含：每条链接的**路径** + `LinkType` + `Target`（`Get-Item -Force .LinkType/.Target` 直接可得），以及可照抄的正规命令 `mw worktree rm <path>` | §7.1 |
| **AC-003** | 对不含 reparse point 的 worktree 必须**零副作用放行**：实测干净/仅普通未跟踪/仅已跟踪改动的 worktree，`git worktree remove` 本身 rc=0 或 rc=128 且真树零损伤；guard 不得额外拦截 | §6（N3/N4/N5） |
| **AC-004** | 六步中"只摘链"必须用 **`cmd /c rmdir <link>`（无 `/S`、路径不带尾分隔符、不带通配）**；`rmdir /S /Q <link>` 与 `Remove-Item` 等价可用，但必须排除尾分隔符/通配形态 | §2（3/4/7/10/12/16）、§4 |
| **AC-005** | "只摘链"后主树零损伤：实测 `cmd /c rmdir <link>` rc=0、链接消失、目标 `target_files=2 f1=True` 不变 | §2（3）、§4（E7b） |
| **AC-006** | 链接目标在仓库外时 fail-closed 拒绝，且拒绝时不摘链；`Target` 与仓库根做规范化前缀比较即可判定 | §7.2 |
| **AC-007** | 任一步失败必须中止并保留现场：反向证据是"不中止就部分删除"——锁场景 rc=255、`@scope=[linkC]`、`pkgC` 只删 1/3 | §5.2 / §5.4 |

**补充（AC-008/009/011 的相关事实）**：junction 与 symlink 可由 `LinkType` 区分（§3.2）；断链可用"`Get-Item -Force` 成功但 `Test-Path Target` 为假"检出（§7.3）；`git worktree remove` 处理**目录 symlink 时不穿透**（§2 第 2 行 / §4 G2），因此 `--link-deps` 若要造链接，用 symlink 会比 junction 更"抗 git 穿透"，但这不是本文档的结论范围。

---

## 9. 未坐实 / caveat（不得当结论使用）

1. **仅测 git `2.53.0.windows.1`**：更早/更新版本对 `IO_REPARSE_TAG_MOUNT_POINT` 的处理可能变化，未验证。
2. **仅测 junction 与目录 symlink 两类 reparse point**：OneDrive 占位符、cloud files（`IO_REPARSE_TAG_CLOUD_*`）、卷挂载点、文件 symlink/hardlink 均未测。
3. **`rimraf` / npm 自带删除器 / robocopy `/MIR`** 未测；只测了 Node v24 的 `fs.rmSync(recursive)`。
4. **`cmd /c rmdir /S /Q <link>\*`（尾反斜杠 + 通配）未单独测**；已测 `<link>\` 与 `Remove-Item <link>\*`。
5. **进程 cwd 占用未导致中止**（E14/E14b 实测 rc=0），但该结论可能受"Windows 是否持有可删句柄"的实现细节影响，不作强断言。
6. **线上真树被哪个具体句柄/进程占用**（造成 156/236 的那个 EINVAL）无法从只读证据反推——与 `in1` §5 第 5 条一致。
7. **`git worktree remove` 具体在哪一层 `readdir` 顺序上中止**：由残留集合反推出的顺序与"@scope 先于 plainpkg、linkA→linkB→linkC、文件按名"一致（§5.4），但未从 git 源码坐实排序实现。

---

## 10. [VERIFY] 汇总（本次实测打印，可复算）

```
[VERIFY] env_os=10.0.26100.9168 ps=5.1.26100.9168 git=2.53.0.windows.1 node=v24.19.0 coreutils_rm=8.32
[VERIFY] reparse_tag junction=0xa0000003 symlink=0xa000000c
[VERIFY] ps_attr junction=Directory,ReparsePoint LinkType=Junction ; symlink LinkType=SymbolicLink
[VERIFY] msys2_stat junction=symbolic link ; symlink=symbolic link
[VERIFY] git_view status: '?? junc/' (junction=dir) vs '?? sym' (symlink) ; ls-files -o -> 'junc/x.txt'
[VERIFY] pen(cmd-rmdir-link)=no rc=0 link_left=no
[VERIFY] pen(cmd-rmdirS-parent)=no rc=0 link_left=no
[VERIFY] pen(cmd-rmdirS-link)=no rc=0 link_left=no
[VERIFY] pen(cmd-rmdirS-link-trailing)=yes rc=0 link_left=no
[VERIFY] pen(ps-recurse-parent)=no rc=0 link_left=no
[VERIFY] pen(ps-recurse-link)=no rc=0 link_left=no
[VERIFY] pen(ps-recurse-link-glob)=yes rc=0 link_left=yes
[VERIFY] pen(rmrf-parent)=no rc=0 link_left=no
[VERIFY] pen(rmrf-link)=no rc=0 link_left=no
[VERIFY] pen(rmrf-link-trailing)=yes rc=0 link_left=yes
[VERIFY] pen(rmrf-link-glob)=yes rc=0 link_left=yes
[VERIFY] pen(node-rm-parent)=no rc=0 link_left=no
[VERIFY] pen(node-rm-link)=no rc=0 link_left=no
[VERIFY] pen(node-rm-link-trailing)=no rc=0 link_left=no
[VERIFY] pen(rmrf-link-symlink-trailing)=yes rc=0 link_left=yes
[VERIFY] git(G1) kind=junction force=True  rc=0   err=-       pen=yes wt_left=no  @scope=[MISSING] pkgC=[]            (2 层 junction)
[VERIFY] git(G2) kind=symlink  force=True  rc=0   err=-       pen=no  wt_left=no  @scope=[linkA,linkB,linkC] pkgC=[c1.txt,c2.txt,c3.txt]
[VERIFY] git(G3) kind=none     force=True  rc=0   err=-       pen=no  wt_left=no  @scope=[linkA,linkB,linkC] pkgC=[c1.txt,c2.txt,c3.txt]
[VERIFY] git(G4) kind=junction force=False rc=0   err=-       pen=yes wt_left=no  @scope=[MISSING] pkgC=[]            (gitignored node_modules)
[VERIFY] git(G5) kind=junction-untracked force=False rc=128 err=refused pen=no wt_left=yes @scope=[linkA,linkB,linkC] pkgC=[c1.txt,c2.txt,c3.txt]
[VERIFY] git(G6) kind=junction force=True  rc=255 err=EINVAL pen=partial wt_left=yes @scope=[linkC] pkgC=[c2.txt,c3.txt]   (exclusive lock)
[VERIFY] locked_abort_error_text="error: failed to delete '<wt>': Invalid argument"
[VERIFY] abort_causes: lock_exclusive=255 partial=yes ; readonly=0 ; cwd_handle=0
[VERIFY] n1_clean=rc0_no_damage n4_untracked=rc128 n5_modified=rc128 no_junction_lock=rc255_A_untouched
[VERIFY] triple_junction_chain rc=0 mid=[] deep=[] lv3=MISSING
[VERIFY] legacy_probe_mwvg_t5_probe_exists=False
[VERIFY] broken_junction Test-Path(link)=True Test-Path(target)=False Get-Item.LinkType=Junction
[VERIFY] gci_recurse_no_follow count=3 entries=[\link,\plain,\plain\g.txt]
```

---

## 11. 只读合规声明与实验目录清理

- 未对 `H:\git\Multi-Workers` 执行任何写操作：未搭指回真树的链接、未在真树建/删 worktree、未执行 `git worktree add/remove`、未执行 `checkout`/`reset`/`stash`/`clean`、未修改任何跟踪文件。
- 本 worker 唯一写入物 = `H:\git\Multi-Workers\.agenticdoc\mw-worktree-junction-guard\evidence\research\spec-junction-semantics-20261009.md`（本文件）。
- 全部实验（含 git 仓库、worktree、junction、symlink、锁句柄）均位于 `%TEMP%\wjg-rq1\**`，且所有链接目标同样在该目录内。
- 实验结束后用**不穿透**方式清理 `%TEMP%\wjg-rq1`（先 `cmd /c rmdir <link>` 逐条摘链，再 `cmd /c rmdir /S /Q <root>`；两者在本次实验中被证明不穿透 junction）。
