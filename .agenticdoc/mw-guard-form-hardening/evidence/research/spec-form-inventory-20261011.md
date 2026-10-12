# RQ-1: worker bash 写面守卫 —— 写入形态全集 vs 现提取器覆盖

- Task: `mwgf-rq1-form-inventory` (type=research, phase=SPEC)
- 目标代码: `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- 守卫挂载: `:1467-1497`（`isShellRole && isWritelessRole` 时注册 `tool_call`；`:1480-1495` 逐个 candidate 判定，第一个违规即 block）
- 角色条件: `isShellRole :126-128` / `isWritelessRole :133-136`；`research` 是当前唯一 shell+writeless 角色（`TOOL_ALLOWLISTS :70`）

## 0. 方法与证据强度

- 只读研究，未修改任何源码/测试；未运行 vitest / npm run check / npm run build / mw build。
- 实测设施：`packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` 与 src 逐段比对一致（`tokenizeShellCommand` / `extractBashWriteCandidates` / `checkBashWriteScopeTarget` 函数体完全相同），因此用 node 直接 import dist 跑真实函数，不靠人肉推演。
- 79 条最小命令逐条跑过（含 5 条负向对照），结果原文进表；另跑了 6 条 `checkBashWriteScopeTarget` 判定（配置用与生产同形的 Windows `taskDir`/`keyDir`）验证误拦。
- 判定分类：`COVERED`（提取到且目标/基址正确，含「正确地不提取」）、`PARTIAL`（提对主目标但漏/错一部分）、`MISS`（完全没提取 = 静默放行）、`FP`（提取到非写入 token，会把合法命令拦下 = false block）。
- 「依据」列指向真正做该决定的代码。

## 1. 覆盖率数值（机器可读）

```
forms_total=79
forms_covered=35
forms_missing=33
forms_partial=3
forms_false_positive=8
write_forms_total=74          # 79 减去 5 条非写入/负向对照 (R37,R58,R77,R78,R79)
write_forms_covered=30
write_forms_missing=33
forms_covered_definition=extractor_verdict_matches_expected_including_correctly_no_target
extractor=worker-mode.ts:809-912 (redirect :818-826, command switch :830-911)
```

`forms_missing` 形态名（33）：

```
bash -c / sh -c / zsh -c / dash -c / ksh -c
cmd /c
powershell -Command / pwsh -c
perl -e / ruby -e
env VAR=x CMD
sudo FLAG... CMD / doas
xargs ... sh -c
timeout N CMD / setsid
stdbuf FLAG CMD / nice -n N CMD / time -p CMD
redirect >| / redirect >&
install / dd of= / ln / rsync / tar -xf / tar -xzf / perl -i
find -exec / find -delete
-- 之后的合法操作数 (rm -- -weird.txt)
python -c "os.system(...)" / node -e "child_process.execSync(...)"
```

`forms_partial`（3）：`sed -i.bak`（漏 `f.bak` 旁写）、`cd X && echo x > Y`、`cd X && > Y`（Y 被提取但按 projectRoot 解析，不是按 X）。
`forms_false_positive`（8，会误拦合法命令）：`truncate -s 0 F`、`echo x > $(date).txt`、`` echo x > `date`.txt ``、`echo x > *.txt`、`rm *.txt`、`echo x > ~/t1.txt`、`echo x > {a,b}.txt`、`python3 -c "Path(F).write_text('x')"`。

## 2. 形态 × 覆盖表

`现实现` 列：`COVERED` / `MISS` / `PARTIAL` / `FP`（定义见 §0）。
`实际 target` 列 = 真实 `extractBashWriteCandidates()` 返回值（`target (pattern)`），`[]` = 空。
`判定` 列：① 目标可静态确定；② 只能确定前缀/需额外解析；③ 完全不可确定。

### 2.1 包装器族（R01–R27）

| # | 形态 | 最小可复现命令 | 现实现 | 实际 target | 期望判定 | 判定 | 修复方向 | 依据 |
|---|---|---|---|---|---|---|---|---|
| R01 | `bash -c` | `bash -c "echo x > o1.txt"` | MISS | `[]` | 目标 `o1.txt` | ① 字面 body（含 `$`/glob 时 ③） | 解包 `-c` 后对内层字符串递归 re-tokenize（深度上限 3） | tokenizer 把引号内整段当一个 word（`:667-731`）；`bash` 不在 `:830-911` 的 switch |
| R02 | `sh -c` | `sh -c "echo x > o2.txt"` | MISS | `[]` | `o2.txt` | 同上 | 同上 | 同上 |
| R03 | `zsh -c` | `zsh -c "echo x > o3.txt"` | MISS | `[]` | `o3.txt` | 同上 | 同上 | 同上 |
| R04 | `dash -c` | `dash -c "echo x > o4.txt"` | MISS | `[]` | `o4.txt` | 同上 | 同上 | 同上 |
| R05 | `ksh -c` | `ksh -c "echo x > o5.txt"` | MISS | `[]` | `o5.txt` | 同上 | 同上 | 同上 |
| R06 | `cmd /c` | `cmd /c "echo x > o6.txt"` | MISS | `[]` | `o6.txt` | ① 字面内层 | 解包 `/c` 后同一 `>` 解析 | `:830-911` 无 cmd；`:818-826` 看不到引号内 |
| R07 | `powershell -Command` | `powershell -Command "Set-Content -Path o7.txt -Value x"` | MISS | `[]` | `o7.txt` | ① | 解包后递归（复用 `POWERSHELL_WRITE_COMMANDS :766-772`） | 同上 |
| R08 | `pwsh -c` | `pwsh -c "Set-Content -Path o8.txt -Value x"` | MISS | `[]` | `o8.txt` | ① | 同上 | 同上 |
| R09 | `perl -e` | `perl -e "open(F,'>','o9.txt')"` | MISS | `[]` | `o9.txt` | ① 字面路径 | perl 进 inline 分支，加 path 型 pattern | `:884-890` 只认 python/python3/py/node；`:786-795` 的 `-c`/`-e` 只被上述命令名调用 |
| R10 | `ruby -e` | `ruby -e "File.write('o10.txt','x')"` | MISS | `[]` | `o10.txt` | ① | ruby 进 inline 分支，加 `File.write` 型 path pattern | 同上 |
| R11 | `env VAR=x cmd` | `env FOO=bar cp a b` | MISS | `[]` | `b.txt` | ①（`NAME=value` 可跳过） | 解包 env 的 `NAME=value` 前缀后继续判 command position | `:735-741` 只看紧邻前一 token 是否属于 `:733` wrapper 集；`FOO=bar` 两者都不是 |
| R12 | `env cmd` | `env cp a b` | COVERED | `b.txt (cp)` | `b.txt` | ① | 保持 | `:733` + `:735-741` |
| R13 | `sudo cmd` | `sudo cp a b` | COVERED | `b.txt (cp)` | `b.txt` | ① | 保持，补 flag 感知 | `:733` |
| R14 | `sudo` + flag | `sudo -u root cp a b` | MISS | `[]` | `b.txt` | ②（sudo flag 元数已知） | 按已知 arity 跳过 flag 及其参数 | `:735-741` 只检查紧邻 token `root` |
| R15 | `doas` | `doas cp a b` | MISS | `[]` | `b.txt` | ② | 加入 wrapper 集（flag 处理同 sudo） | `:733` 无 doas |
| R16 | `xargs ... sh -c` | `xargs -n1 sh -c "echo x > o11.txt"` | MISS | `[]` | `o11.txt` | ②（含 `{}` 时 ③） | xargs 解包 + 递归 `sh -c` | `:733` 有 xargs 但 `-n1` 断开；`sh` 不在 `:830-911` |
| R17 | `xargs CMD` | `xargs rm a` | COVERED | `a (rm)` | `a` | ① | 保持（xargs 在 `:733` 使 `rm` 处于 command position） | `:733` + `:735-741` + `:842-847` |
| R18 | `timeout N cmd` | `timeout 5 cp a b` | MISS | `[]` | `b.txt` | ①（首个非 flag 是 duration） | 加入 wrapper + duration 位置处理 | `:733` 无 timeout |
| R19 | `setsid cmd` | `setsid cp a b` | MISS | `[]` | `b.txt` | ① | 加入 wrapper 集 | `:733` 无 setsid |
| R20 | `stdbuf FLAG cmd` | `stdbuf -o0 cp a b` | MISS | `[]` | `b.txt` | ② | wrapper + flag 跳过 | `:733` 有 stdbuf，`-o0` 断开 |
| R21 | `stdbuf cmd` | `stdbuf cp a b` | COVERED | `b.txt (cp)` | `b.txt` | ② | 保持 | `:733` |
| R22 | `nice cmd` | `nice cp a b` | COVERED | `b.txt (cp)` | `b.txt` | ② | 保持 | `:733` |
| R23 | `nice -n N cmd` | `nice -n 5 cp a b` | MISS | `[]` | `b.txt` | ②（`-n` 消耗参数） | wrapper + flag arity | `:735-741` |
| R24 | `time cmd` | `time cp a b` | COVERED | `b.txt (cp)` | `b.txt` | ① | 保持 | `:733` |
| R25 | `time -p cmd` | `time -p cp a b` | MISS | `[]` | `b.txt` | ② | wrapper + flag 跳过 | `:735-741` |
| R26 | `command cmd` | `command cp a b` | COVERED | `b.txt (cp)` | `b.txt` | ① | 保持 | `:733` |
| R27 | `nohup cmd` | `nohup cp a b` | COVERED | `b.txt (cp)` | `b.txt` | ① | 保持 | `:733` |

包装器族未覆盖（MISS）已全部列出：R01–R11、R14–R16、R18–R20、R23、R25。

### 2.2 重定向算子族（R28–R39）

| # | 形态 | 最小可复现命令 | 现实现 | 实际 target | 期望判定 | 判定 | 修复方向 | 依据 |
|---|---|---|---|---|---|---|---|---|
| R28 | `>` | `echo x > r1.txt` | COVERED | `r1.txt (redirect)` | `r1.txt` | ① | 保持 | `:818-826` |
| R29 | `>>` | `echo x >> r2.txt` | COVERED | `r2.txt (redirect)` | `r2.txt` | ① | 保持 | `:821` |
| R30 | `>` 加 pipe (`>!\|`) | `echo x >\| r3.txt` | MISS | `[]` | `r3.txt` | ① | 把 clobber 算子当一个算子；解析 fd 前缀后再看算子 | `:821` 只认字面量 `>`/`>>`；tokenizer 把 `>` 与 `\|` 拆成两个 operator（`:713-724`） |
| R31 | `<>` | `echo x <> r4.txt` | COVERED | `r4.txt (redirect)` | `r4.txt` | ①（读写打开，目标即文件） | 保持（当前靠 `<` 与 `>` 各自成 token 的副作用） | `:818-826` |
| R32 | `>` 加 `&` (`>&`) | `echo x >& r5.txt` | MISS | `[]` | `r5.txt` | ①（bash `>&word` 等价 `&>word`） | 同 R30 | `:821` + tokenizer |
| R33 | `&>` | `echo x &> r6.txt` | COVERED | `r6.txt (redirect)` | `r6.txt` | ① | 保持 | `:818-826` |
| R34 | `2>` | `echo x 2> r7.txt` | COVERED | `r7.txt (redirect)` | `r7.txt` | ① | 保持；建议显式解析 fd 前缀 | `:818-826` |
| R35 | `2>>` | `echo x 2>> r8.txt` | COVERED | `r8.txt (redirect)` | `r8.txt` | ① | 同上 | `:818-826` |
| R36 | `1>` | `echo x 1> r9.txt` | COVERED | `r9.txt (redirect)` | `r9.txt` | ① | 同上 | `:818-826` |
| R37 | `2>&1` | `echo x 2>&1` | COVERED | `[]` | 无文件目标（fd dup） | ① | 保持「不产生 candidate」；解析 fd 前缀后必须显式排除 `>&N` / `N>&M` / `N>&-` | `:818-826`：`>` 后紧跟 operator 故跳过 |
| R38 | `> f 2>&1` | `echo x > r10.txt 2>&1` | COVERED | `r10.txt (redirect)` | `r10.txt` | ① | 保持 | `:818-826` |
| R39 | `exec 3> f` | `exec 3> r11.txt` | COVERED | `r11.txt (redirect)` | `r11.txt` | ① | 保持；建议显式识别 `exec` + fd 前缀 | `:818-826` |

### 2.3 操作数即目标族（R40–R57）

| # | 形态 | 最小可复现命令 | 现实现 | 实际 target | 期望判定 | 判定 | 修复方向 | 依据 |
|---|---|---|---|---|---|---|---|---|
| R40 | `cp` | `cp a.txt b.txt` | COVERED | `b.txt (cp)` | `b.txt` | ① | 保持 | `:835-841` |
| R41 | `cp -- a b` | `cp -- a.txt b.txt` | COVERED | `b.txt (cp)` | `b.txt` | ① | 保持（last positional） | `:837` |
| R42 | `mv` | `mv a.txt b.txt` | COVERED | `b.txt (mv)` | `b.txt` | ① | 保持 | `:835-841` |
| R43 | `install` | `install a.txt b.txt` | MISS | `[]` | `b.txt` | ① | 加入 operand 白名单（last positional） | `:830-911` 无 install |
| R44 | `tee` | `tee t.txt` | COVERED | `t.txt (tee)` | `t.txt` | ① | 保持 | `:831-834` |
| R45 | `tee -a` | `tee -a t.txt` | COVERED | `t.txt (tee)` | `t.txt` | ① | 保持 | `:831-834` |
| R46 | `dd of=` | `dd if=/dev/zero of=ddf.txt bs=1 count=1` | MISS | `[]` | `ddf.txt` | ① | 解析 `of=` 目标 | `:830-911` 无 dd |
| R47 | `truncate` | `truncate -s 0 tr1.txt` | FP | `"0" (truncate)`, `tr1.txt (truncate)` | 只应 `tr1.txt` | ②（`-s` 消耗一个 size 参数） | 跳过 `-s`/`--size` 的值；只取 positional | `:842-848` 对所有非 `-` 开头 operand 都 add |
| R48 | `ln` | `ln a.txt b.txt` | MISS | `[]` | `b.txt` | ① | 加入白名单（第 2 个 positional） | `:830-911` 无 ln |
| R49 | `rsync` | `rsync a.txt b.txt` | MISS | `[]` | `b.txt` | ② | 加入白名单（last positional；flag arity 复杂） | `:830-911` 无 rsync |
| R50 | `tar -xf` | `tar -xf x.tar` | MISS | `[]` | 解包目录 = cwd 或 `-C` | ②（archive 是输入，写面是 cwd/`-C`） | 专门处理 `-x` + `-C`；无 `-C` 时目标 = cwd | `:830-911` 无 tar |
| R51 | `tar -xzf` | `tar -xzf x.tgz` | MISS | `[]` | 同 R50 | ② | 同上 | `:830-911` 无 tar |
| R52 | `sed -i` | `sed -i s/a/b/ s1.txt` | COVERED | `s1.txt (sed -i)` | `s1.txt` | ① | 保持 | `:849-855` |
| R53 | `sed -i.bak` | `sed -i.bak s/a/b/ s2.txt` | PARTIAL | `s2.txt (sed -i)` | `s2.txt` + `s2.txt.bak` | ①（后缀字面可判） | 从 `-i<suffix>` 推出 sidecar target | `:850-854` 只把非 `-` positional 当目标，忽略 `-i` 后缀语义 |
| R54 | `sed --in-place` | `sed --in-place s/a/b/ s3.txt` | COVERED | `s3.txt (sed -i)` | `s3.txt` | ① | 保持 | `:850-855` |
| R55 | `perl -i` | `perl -i -pe s/a/b/ p1.txt` | MISS | `[]` | `p1.txt` | ②（需理解 `-i` + `-e/-pe` script 的 operand 语义） | perl 加入白名单：`-i` 时非 `-e/-pe` 的 positional 是文件 | `:884-890` 不含 perl |
| R56 | `find -exec` | `find . -exec rm {} \;` | MISS | `[]` | `-exec` 内嵌命令递归；目标 = `{}` 展开集 | ② 前缀（③ 全量） | `-exec` 到 `;`/`+` 之间递归 extract | `:830-911` 无 find |
| R57 | `find -delete` | `find . -delete` | MISS | `[]` | 搜索根路径当前缀 | ② | 同上 | `:830-911` 无 find |

### 2.4 其他族（R58–R71）

| # | 形态 | 最小可复现命令 | 现实现 | 实际 target | 期望判定 | 判定 | 修复方向 | 依据 |
|---|---|---|---|---|---|---|---|---|
| R58 | here-string `<<<` | `cat <<< x` | COVERED | `[]` | 无文件目标（读） | ① | 保持；tokenizer 把 `<<<` 合成一个 operator | `:713-724` |
| R59 | here-string + `>` | `cat <<< x > h1.txt` | COVERED | `h1.txt (redirect)` | `h1.txt` | ① | 保持 | `:818-826` |
| R60 | `--` 之后的操作数 | `rm -- -weird.txt` | MISS | `[]` | `-weird.txt` | ①（`--` 之后全是操作数） | 见到裸 `--` 后停止把 operand 当 flag | `:843-847` 的 `!value.startsWith("-")` 把 `-weird.txt` 丢掉 |
| R61 | 引号目标 | `echo x > "a b.txt"` | COVERED | `a b.txt (redirect)` | `a b.txt` | ① | 保持 | `:667-731` quote-aware |
| R62 | 转义目标 | `echo x > a\ b.txt` | COVERED | `a b.txt (redirect)` | `a b.txt` | ① | 保持 | `:667-731` |
| R63 | `$(...)` 作目标 | `echo x > $(date).txt` | FP | `"$" (redirect)` | 目标不可静态确定 | ③ | 目标含 `$`/`(`/反引号 ⇒ 不可确定 ⇒ 放行 + 审计 | `:818-826` 把 `$`（`(` 前的 word）当成重定向目标 |
| R64 | `$(...)` 作命令 | `$(rm cst.txt)` | COVERED | `cst.txt (rm)` | `cst.txt` | ①（命令替换内部恰好是 command position） | 保持（副作用）；建议显式支持子 shell | `:713-724`（`(` 是 operator）+ `:735-741`（前一 token 是 operator ⇒ command position） |
| R65 | 反引号目标 | `echo x > \`date\`.txt` | FP | `` `date`.txt (redirect) `` | 不可静态确定 | ③ | 含反引号 ⇒ 放行 + 审计 | `:818-826` 整段含反引号仍被当字面路径 |
| R66 | glob 目标 | `echo x > *.txt` | FP | `*.txt (redirect)` | 运行时展开，集合不可静态确定 | ③（前缀可判） | 含 glob 元字符 ⇒ 放行 + 审计（或只判前缀面） | `:818-826`；`GLOB_MAGIC_RE` 只用在 write_scope 匹配侧，target 侧不处理 |
| R67 | glob 操作数 | `rm *.txt` | FP | `*.txt (rm)` | 同 R66 | ③ | 同上 | `:842-847` |
| R68 | `~` | `echo x > ~/t1.txt` | FP | `~/t1.txt (redirect)` | `$HOME/t1.txt` | ②（HOME 在进程 env 可查） | 展开 `~`/`~/`（`os.homedir()`）；否则不要当字面相对路径 | `:818-826` + `normalizeForCompare`（`read-scope.ts:100-114`）不做 `~` 展开；实测 `path.resolve(root,"~/t1.txt")` = `<root>/~/t1.txt` |
| R69 | `cd X && > Y` | `cd /tmp && echo x > cd1.txt` | PARTIAL | `cd1.txt (redirect)` | `/tmp/cd1.txt` | ①（字面 `cd` 可词法跟踪） | 同一命令行内词法跟踪字面 `cd P`，其后相对 target 以 P 为基址 | `:818-826` 与 `:735-741` 都不带 cwd 状态 |
| R70 | `cd X && > Y`（裸） | `cd /tmp && > cd2.txt` | PARTIAL | `cd2.txt (redirect)` | `/tmp/cd2.txt` | ① | 同上 | 同上 |
| R71 | 花括号展开 | `echo x > {a,b}.txt` | FP | `{a,b}.txt (redirect)` | `a.txt` / `b.txt` | ③（brace 集合可判但当前无解析） | 含 `{}` ⇒ 当作不可确定 ⇒ 放行 + 审计（勿误伤 `find {}`） | `:818-826` |

### 2.5 内联脚本族（R72–R77）

| # | 形态 | 最小可复现命令 | 现实现 | 实际 target | 期望判定 | 判定 | 修复方向 | 依据 |
|---|---|---|---|---|---|---|---|---|
| R72 | `python -c open(...,'w')` | `python3 -c "open('py1.txt','w')"` | COVERED | `py1.txt (inline-script)` | `py1.txt` | ① | 保持 | `:775-784` + `:884-890` |
| R73 | `python -c Path().write_text()` | `python3 -c "from pathlib import Path; Path('py2.txt').write_text('x')"` | FP | `"x" (inline-script)`, `py2.txt (inline-script)` | 只应 `py2.txt` | ① | 删掉裸 `write_text/write_bytes` pattern（它抓的是 content 不是 path），只保留 `Path(...).write_*` | `:777` 的 `\bwrite_(?:text\|bytes)\(...` 捕获写内容 |
| R74 | `python -c os.system()` | `python3 -c "import os; os.system('cp a b')"` | MISS | `[]` | `b.txt` | ②（内层字符串字面可再解析） | 对 `os.system/os.popen/subprocess.*` 的字符串字面量递归解析，或归 ③+审计 | `:775-784` 无这些 pattern |
| R75 | `node -e fs.writeFileSync()` | `node -e "require('fs').writeFileSync('n1.txt','x')"` | COVERED | `n1.txt (inline-script)` | `n1.txt` | ① | 保持 | `:781-783` + `:884-890` |
| R76 | `node -e child_process` | `node -e "require('child_process').execSync('cp a b')"` | MISS | `[]` | `b.txt` | ② | 同 R74 | `:775-784` 无 child_process pattern |
| R77 | `node -e`（无写入） | `node -e "console.log(1)"` | COVERED | `[]` | 无文件目标 | ① | 保持 | `:775-807` |

### 2.6 负向对照（R78–R79）

| # | 形态 | 最小可复现命令 | 现实现 | 实际 target | 期望判定 | 判定 | 修复方向 | 依据 |
|---|---|---|---|---|---|---|---|---|
| R78 | 纯读命令 | `rg foo` | COVERED | `[]` | 放行（P1：未知即放行） | ① | 保持 | `:830-911` default 分支只处理 PowerShell cmdlet |
| R79 | 引号内 `>` | `echo "a > b"` | COVERED | `[]` | 放行（不是重定向） | ① | 保持 | `:667-731` |

## 3. 可判定性分类（逐形态）

### ① 目标可静态确定（应纳入提取）
| 形态 | 为什么可判 |
|---|---|
| 字面重定向目标 `>` `>>` `>`-pipe `<>` `&>` `>&` `N>` `N>>` `exec N>` | 目标是算子后的一个词元，字面可读；唯一需要的是把 fd 前缀 / fd-dup / clobber 算子解析对 |
| `cp` / `mv` 最后一个 positional；`tee`；`install`；`ln` 第 2 个 positional；`sed -i` 的 file；`dd of=P`；`truncate` 的 file（修正后）；`sort -o P`；`uniq IN OUT` | 写目标是固定位置的 positional 或 `key=value`，命令名已知 |
| 引号 / 转义后的字面路径（R61/R62） | tokenizer 已做 quote-aware 还原 |
| 包装器 + 全字面内层：`bash\|sh\|zsh\|dash\|ksh -c`、`cmd /c`、`powershell\|pwsh -Command`、`perl\|ruby -e`、`env VAR=x`、`timeout N`、`setsid`、`nice`、`stdbuf`、`sudo`/`doas`、`command`、`nohup`、`time`、`xargs`（无 `{}`） | 内层命令是同一字符串的字面片段，可 re-tokenize 后递归同一提取器 |
| `cd LITERAL && ...` | 字面 `cd` 目标可词法跟踪，其后相对 target 的基址确定 |
| `--` 之后的操作数（R60） | `--` 之后不再有 flag 语义，全部是 positional |
| `$(CMD)` 出现在命令位置（R64） | 子命令本身可递归提取；但作为**目标**时属 ③ |
| here-string `<<<`、纯读命令、引号内 `>`（R58/R78/R79） | 非写入，可确定地「不提取」 |

### ② 只能确定前缀 / 需按已知 arity 额外解析
| 形态 | 为什么只能到前缀 |
|---|---|
| `sudo -u/-g/... CMD`、`nice -n N CMD`、`stdbuf -oX/-eX/-iX CMD`、`time -p CMD`、`xargs -n1 CMD` | 目标是内层命令，但需先按 flag arity 跳过参数；flag 表可枚举，故不是 ③ |
| `rsync SRC DEST` / `tar -x [-C DIR]` / `find ROOT -delete` | 写面是目录（rsync 目标目录、tar 解包根、find 搜索根），只有前缀可判 |
| `find ROOT -exec CMD ... \;` | 目标集是运行时匹配文件集；前缀 = 搜索根 |
| `~/path`（R68） | `$HOME` 可从进程 env 得到，前缀可判；当前代码完全未展开 |
| glob target（R66/R67） | 非 magic 前缀可判；展开后的文件集不可静态判 |
| inline python/node 的字符串字面量（R72/R73/R75） | 字面串可判；一旦路径由变量/插值拼接即降到 ③ |
| `dd of=P` 之外的 dd 目标（`dd if=X of=P`） | `of=` 可判；无 `=` 的 `dd of out.bin` 不是 dd 的合法语法（实测未提取，符合预期） |

### ③ 完全不可确定
| 形态 | 原因（一句话） |
|---|---|
| 目标位置的 `$VAR` / `${VAR}` / `$(...)` / 反引号（R63/R65） | 值只在运行时存在 |
| glob / brace 展开的完整集合（R66/R67/R71） | 展开结果取决于运行时目录内容 |
| 脚本文件调用 `bash x.sh` / `python3 x.py` / `node x.js` | 文件内容不在命令行字符串里（实测 `[]`） |
| `eval` / `source` / `. script` / shell function 覆盖 `cp` | 被调用体不在命令行字符串里 |
| heredoc body（`bash <<EOF ... EOF`） | 语义上不可静态判；当前只因 tokenizer 把换行变成 `;`（`:705-710` 附近）而**偶然**被扫描（实测 `bash <<EOF\ncp a b\nEOF` → 提取到 `b`） |
| `os.system` / `child_process.execSync` / `sh -c` 内层含变量（R74/R76） | 内层是另一个解释器的字符串，只有再解析一轮才能部分恢复 |
| `xargs` 的 `{}` / `-I` 展开集、`find -exec {} +` 批处理集 | 目标集由输入数据决定 |

## 4. 修复方向（只到「应该怎么判」层面）

### 4.1 先修 8 个 FP（这些正是「扩大正则」的产物）
1. `truncate`：只取 positional，跳过 `-s`/`--size` 消耗的 size 参数（`:842-848`）。
2. 删掉裸 `write_text` / `write_bytes` pattern，只保留带 `Path(...)` 接收者的 pattern；否则内容串被当路径（`:777`）。
3. 重定向目标若以 `$`、反引号、`*`、`?`、`[`、`{`、`~` 开头或含之 ⇒ **不进 candidate**，转 4.3 的审计（`:818-826`）。
4. `--` 之后的操作数不再按 flag 过滤（`:837`/`:843-847`）。
5. `sed -i<suffix>` 补 sidecar `f.bak`（`:850-854`）。
6. `cd LITERAL` 词法跟踪：其后相对 target 以 `P` 为基址（`:818-826` + `:735-741` 无 cwd 状态）。

### 4.2 应纳入提取（① + ②）
- 重定向算子全表：`>` `>>` `>|` `<>` `&>` `>&` + 显式 fd 前缀 `N>`/`N>>`，并显式排除 fd-dup `>&N` / `N>&M` / `N>&-`（`:818-826`）。
- 包装器递解开箱（白名单集 + flag arity + 递归深度上限 + 每层 re-tokenize），至少覆盖 §2.1 的 R01–R27；现状只有 `:733` 的 8 个名字且只在紧邻位置生效。
- operand 白名单补齐：`install`、`dd of=`、`ln`、`rsync`、`tar -x`/`-C`、`perl -i`、`find -exec`/`-delete`、`sort -o`、`uniq` 第 2 个 operand（`:830-911` 目前无这些）。
- inline 分支扩展到 `perl`/`ruby` 以及 `os.system`/`child_process.execSync` 的字符串字面量（`:884-890` 只认 python/python3/py/node；`:775-784` 无对应 pattern）。

### 4.3 归入「不可确定 ⇒ 放行 + 审计」
目标含 `$` / 反引号 / glob 元字符 / `{}`（brace）/ 未展开的 `~` / 非字面 `cd` 基址 / 脚本文件调用 / `eval`/`source` / `{}` 占位符展开 ⇒ 不 deny，写一条 `[WRITE_SCOPE] ... write-scope undecided ...` 审计即可（与现有 `appendBashWriteScopeTraceLine :1017-1030` 同构）。理由 = P1（`:615-617` 注释：miss 优于 false block），且完整命令已进 trace，漏掉的异形写可事后审计。

### 4.4 为什么不需要引入 shell 解释器
1. **解释器也解决不了核心问题**：`$VAR`、`$(...)`、glob 结果、脚本文件内容、heredoc body、子 shell 的 `cd` 状态都只在执行期存在。要真知道就得真执行 ⇒ 副作用 + TOCTOU（判定与执行是两次解析），与守卫在 `tool_call` 前置、纯静态的定位冲突（`:1479-1495`）。
2. **跨平台语义**：守卫在 `tool_call` 内同步运行；Windows 上真正的 shell 是 PowerShell/cmd（`:713` 的 tokenizer 不分平台）。用 bash 解释器解析 `cmd /c` / `pwsh -c` 会得到错误语义，而这正是当前最宽的几个口子（§1 missing 列表）。
3. **精度**：写原语集合有界（§2 矩阵）。在白名单化集合上做「解包 + 递归」比部分解释精度更高；当前「宽正则」已经产出 8 个 FP（§4.1），解释器的收益是把不确定性从「漏」变成「误拦」。
4. **纵深已有**：deny list（`bashWriteDenyReason :923-937`）+ `write_scope:`（`matchesWriteScopeEntry :939-955` / `checkBashWriteScopeTarget :959-1000`）+ trace 审计（`:1017-1030`）+ 角色 tool allowlist（`:68-80`）已覆盖；P1 明确误拦（worker 卡死）比漏掉一个异形写更贵。

### 4.5 ≥3 条「简单扩大正则会误拦」的反例（前 3 条为实测 BLOCK）
1. `truncate -s 0 <taskDir>/report.md`：把 size 参数当目标 → 实测 `0 => BLOCK(outside-allowed-surface)`，真实目标 `report.md` 是 ALLOW。**合法命令被拦。**
2. `python3 -c "from pathlib import Path; Path('<taskDir>/report.md').write_text('x')"`：把内容当路径 → 实测 `x => BLOCK(outside-allowed-surface)`，真实目标 ALLOW。
3. `echo x > $(date).txt` / `echo x > $OUT`：「取重定向后一个 token」的朴素正则把 `$` / `$OUT` 当路径 → 实测 `$ => BLOCK(outside-allowed-surface)` / `$OUT (redirect)`；实际目标由运行时决定。
4. `find . -exec grep -l foo {} \;`（纯读）：若规则是「任何 `-exec` 都当写」→ 误拦只读搜索；正确做法是递归解析内层命令，`grep` 无写目标 ⇒ 放行。
5. `grep -rn "open('f','w')" .`（纯读）：若把 `open(...,'w')` 文本匹配放宽成全局扫描（不要求命令是 python/node）→ 误拦只读搜索；当前之所以安全，仅因为它被 gate 在 `:884-890` 的命令名分支里。

## 5. 复现（本报告用过的手段，均只读）
- 提取器实测：`node --input-type=module -e 'import("file:///H:/git/Multi-Workers/packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js")'`，调用 `extractBashWriteCandidates(cmd)` / `tokenizeShellCommand(cmd)`；79 条命令的输出即 §2 的 `实际 target` 列。
- 判定实测：同一模块的 `checkBashWriteScopeTarget(cfg, target)`，`cfg = { projectRoot: <repo>, taskDir: <repo>\.agenticdoc\mw-guard-form-hardening\workers\mwgf-rq1-form-inventory, keyDir: <repo>\.agenticdoc\mw-guard-form-hardening, trueRoot: <repo>\.agenticdoc }`（Windows 反斜杠路径；首次用正斜杠路径会因 `isSameOrUnder` 的 `path.sep` 比较而全部 BLOCK，属测试配置问题，非代码缺陷）。
  - `truncate -s 0 <taskDir>/report.md` → `0 => BLOCK(outside-allowed-surface)`，`report.md => ALLOW`
  - `python3 -c "Path('<taskDir>/report.md').write_text('x')"` → `x => BLOCK(...)`，`report.md => ALLOW`
  - `echo x > $(date).txt` → `$ => BLOCK(...)`
  - `echo x > *.txt` → `*.txt => BLOCK(...)`
  - `cd <taskDir> && echo x > report.md` → `report.md => BLOCK(...)`
  - `echo x > <taskDir>/report.md`（对照）→ `ALLOW`
- token dump（用于解释机制）：`bash -c "..."` → `["bash","-c","echo x > o1.txt"]`；`echo x >| r3.txt` → `["echo","x","#>","#|","r3.txt"]`；`echo x >& r5.txt` → `["echo","x","#>","#&","r5.txt"]`；`echo x > $(date).txt` → `["echo","x","#>","$","#(","date","#)",".txt"]`；`nice -n 5 cp a b` → `["nice","-n","5","cp","a","b"]`；`cat <<< x > h1.txt` → `["cat","#<<<","x","#>","h1.txt"]`。

## 6. 未验证 / 边界（不猜）
- 「未验证」：真实 pi worker 进程里 bash 工具的 `event.input.command` 是否与我在本机输入的字符串 100% 相同（本机 bash 工具走 PowerShell，但守卫拿到的是命令文本，命令替换/引号语义由 PowerShell 决定）——提取器是平台无关的，本报告的 token 结论只对给定的命令字符串成立。
- 「未验证」：未实际执行 `xargs`/`find -exec`/`tar` 的行为验证，§2 的 ②/③ 分类基于命令语义 + 提取器输出，未跑真实命令。
- 「未验证」：生产 launcher 是否总以 projectRoot 为 cwd（代码注释 `:1470` 声称如此，未在运行中验证），这直接影响 R69/R70 的基址错误严重性。
- 「未验证」：除 `worker_file` 外是否还有其他写通道（`lsp`/`web_fetch` 等）——本任务只审 bash 写面。
- 「未验证」：heredoc（`<<EOF`）与多行命令的确切语义；只验证了 `bash <<EOF\ncp a b\nEOF` → 提取到 `b`（换行被 tokenizer 变成 `;`），未验证 `bash` 自身对 heredoc 的解析差异。
- 「未验证」：`GLOB_MAGIC_RE`（`:919`）与 `matchesWriteScopeEntry`（`:939-955`）对 glob 的 target 侧行为——本文只断言 target 侧（`:818-826`）不做 glob 展开，未审 write_scope 侧的 glob 匹配细节。
- 结论强度：§2 的 `实际 target` 与 §4.5 的 1–3 条 BLOCK 是**实测**；§4.5 的 4–5 条与 §4.4 的推理是**分析**（已标注）。
