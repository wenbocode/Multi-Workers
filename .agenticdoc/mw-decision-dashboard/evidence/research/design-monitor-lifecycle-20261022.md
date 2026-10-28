# 设计取证：monitor 生命周期 / 非常规端口 / 应用浏览器窗口 / 本地接口安全

> Key: mw-decision-dashboard · 卡片: D-RQ1-lifecycle · 2026-10-22 · 只读取证（未起停服务、未真实调用模型、未改代码/配置、未装依赖）
> 标签：【事实】= 本次直接读到/本机只读命令输出；【建议】= 设计提议，未实现未验证；【外部】= 通用知识，本机未验证。行号为取证快照。

## 1. 结论（先给判断）
1. 【建议】D-001 选 **方案 A：`mw decide monitor` 自持按需独立进程**，不挂 `mw serve`。决定性依据是安全与可用性：serve 进程内存里装着全部 provider 凭证，且无凭证时直接拒启（mw.py:332）；把 loopback HTTP 面并进该进程，等于给凭证持有者加一个网页可达攻击面，并在"凭证缺失"时恰好无法用看板排查。
2. 【建议】端口沿用 **43170..43269（100 个）**：本机 TCP 动态端口 49152..65535、排除仅 50000-50059、区间内当前无监听（【事实】）；不落在 Chromium 受限端口表（【外部】）。分配用 **bind-and-hold 线性重试**（`bind()` 成功即持有），**不是**现有 `port_is_bound()` 的 `connect_ex` 探测（mw_common.py:2564-2582，有 TOCTOU）。
3. 【建议】`http.server` 默认 `allow_reuse_address=True`（http/server.py:117）在 Windows 上会让"端口已被别人占用"时 bind 仍成功（stdlib 原文注释 socket.py:938-948）；monitor 必须 `allow_reuse_address=False` + `SO_EXCLUSIVEADDRUSE`，否则重复开启/占用检测全失效。
4. 【建议】浏览器用 Chromium `--app=` 独立窗口；本机 Chrome（`C:\Program Files\...\chrome.exe`）与 Edge（`C:\Program Files (x86)\...\msedge.exe`）均存在【事实】。开窗前必须探 `/api/health` 达稳定窗口，不得"spawn 成功即报成功"。
5. 【建议】本地接口最小边界 = **仅 127.0.0.1 + Host/Origin/Sec-Fetch-Site 白名单 + 无 Cookie + 自定义头令牌 + 方法白名单 + 请求体上限**；CSRF 由"无 Cookie + 必须自定义头"消解，DNS rebinding 由 Host 校验消解。
6. 【建议】长令牌**不进 URL/argv/日志/状态文件**：控制令牌在 `<root>/.mw/decide-monitor.secret`（0600），状态 `.mw/decide-monitor.json`（无密），浏览器只拿 URL fragment 里 60s 单次 code 换页内令牌。
7. 【建议】停止走认证 `POST /api/shutdown`，失败退化 `.mw/decide-monitor.stop` 文件（serve 的 `mw.stop` 先例 mw.py:112-129,430-431）；**任何路径都不 kill 非本实例进程**，`--force` 也先校验 `/api/health` 的 `instance_id`。
8. 未验证集中在"真实窗口/真实浏览器/防火墙"（§10），不进 AC 判据。

## 2. 取证基线（事实）
| # | 事实 | 出处 |
| --- | --- | --- |
| F1 | 现有"看板"是**静态 HTML + `webbrowser.open(file://)`**，无 HTTP 服务 | mw.py:10217-10257（`_publish_stats_html`；`webbrowser.open(target.as_uri())` :10253） |
| F2 | 除测试桩外仓库无本地 HTTP server | grep `ThreadingHTTPServer|BaseHTTPRequestHandler`：仅 test_rag_cli.py:8,97,192 |
| F3 | 无 app-mode 浏览器启动先例 | grep `--app=|msedge|chrome.exe` 无产品代码命中 |
| F4 | `serve` 无路由凭证时 **FATAL 拒启**（return 1） | mw.py:305-335（:332 消息） |
| F5 | `mw start` 隐藏控制台契约：`CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP`、禁用 `DETACHED_PROCESS`、stdout/stderr → `.mw/serve-console.log` | mw.py:496-548 |
| F6 | 窗口侧后台启动：`spawn(detached, stdio:"ignore", windowsHide)+unref`；普通转发 `spawnSync(timeoutMs=30_000)` 并追加 `--project=` | mw-runner.ts:121-135 / :513-535（:517,:522-523） |
| F7 | 稳定窗口先例：连续存活 `stableMs` 才算启动；`waitForMwStart` :149（`8000/3000`），`waitForStart` :159 | mw-runner.ts:149-178 |
| F8 | `serve.meta` 先例：`schema`(:134)/pid/started_at/code_dir/code_digest/version，原子写(:175)，退出删除；stale 判定 fail-open 只报"需重启"；`_runtime_digest` :9157 | mw.py:134-200，:9295-9300，:9340 起 |
| F9 | 停止用 `.mw/mw.stop` 文件，serve 1s 循环检查；`mw stop` 等 30s 不强杀 | mw.py:112-129，:430-431，:552-568 |
| F10 | 端口占用检测现有实现是 `connect_ex` 探测 + `netstat` 找 owner pid | mw_common.py:2564-2582 / :2585-2602 |
| F11 | 文件锁协议 `O_CREAT|O_EXCL`（TS 同协议） | mw_common.py:2388-2404 |
| F12 | `HTTPServer.allow_reuse_address=True`；`ThreadingHTTPServer.daemon_threads=True`；`BaseHTTPRequestHandler.protocol_version="HTTP/1.0"` | http/server.py:115-129,:714；运行时复核 `True True HTTP/1.0`（Python 3.14.3） |
| F13 | Windows 设 `SO_REUSEADDR` 的后果（stdlib 原文）："another socket is free to bind() on the same address, effectively preventing this one from accepting connections" | socket.py:938-948 |
| F14 | `socket.SO_EXCLUSIVEADDRUSE` 本机可用 | 运行时 `hasattr` 复核 True |
| F15 | 请求行 65536B、最多 100 header 是 `http.client` 解析上限（非 body 上限） | http/client.py:111-112 |
| F16 | 决策传输 `timeout_s` 默认 20.0s 可配 | decision_backends.py:89,:732,:836 |
| F17 | 脱敏已有生产实现（env `*_API_KEY/_TOKEN/_KEY/_SECRET/_PASSWORD`、Bearer、`sk-`、超长截断） | decision.py:508-545（`_scrub_detail` :542） |
| F18 | `--project` 可传 key 目录，`.agenticdoc` 根有归一 | decide_signoff.py:138-144,:164-173；decision_points.py:96,98 |
| F19 | `.mw/` 已 gitignore | .gitignore:53 |
| F20 | 本机 TCP 动态端口 49152..65535（16384）；排除仅 50000-50059；43170..43269 无监听 | `netsh int ipv4 show dynamicportrange tcp`、`show excludedportrange protocol=tcp`、`Get-NetTCPConnection -State Listen` |
| F21 | 本机 Chrome=`C:\Program Files\Google\Chrome\Application\chrome.exe`、Edge=`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`；LOCALAPPDATA 与 Program Files Edge 不存在 | `Test-Path` 逐项 |
| F22 | 现有 mw 端口 7001/7003/7004，无 43xxx 使用 | README.md:73；grep `43170|43[0-9]{3}` 无产品命中 |
> 本机只读命令均为 2026-10-22 执行。

## 3. 两案比较（D-001）
| 维度 | A：独立按需进程【建议采用】 | B：挂 `mw serve` |
| --- | --- | --- |
| 可用性/耦合 | 看板与调度互不影响；serve 重启（`/mw restart`、`update-env --apply`）不断页 | serve 重启即断页；长观察回调被一起打死 |
| 凭证面（决定性） | 可用**裁剪 env** 启动：只留决策传输所需，provider key 不注入；网页可达面与 provider 凭证不同进程 | serve 持有全部 provider 凭证；接口一旦被注入/越权即凭证侧信道 |
| 启动前置条件 | 无；无凭证也能开看板排查（F4 反面） | F4：无路由凭证直接拒启 |
| 故障隔离 | 看板崩溃只影响看板 | 影响调度/代理/launcher 监督 |
| 生命周期成本 | 需自建状态/复用/停止/退出/多项目（§4 已给契约） | 复用 `serve.meta`/`mw stop`/doctor（F8/F9） |
| 版本/旧实例 | 自建 `schema+digest`（照抄 F8） | 已有 |
| 多项目 | 每项目 1 实例，按 bind 抢端口，自然隔离 | 每项目 1 个 serve，同样 N 实例 |
| 结论 | **推荐 A**；B 唯一优势（少一个进程）不抵凭证面与可用性 | 不采用 |

【建议】不引入 Electron、不做远程访问；`monitor` 不读写 `.mw/decide-points.json`，只读展示授权状态。

## 4. 生命周期契约（方案 A）
### 4.1 进程模型与状态机
- 入口：`mw decide monitor [--project DIR] [--no-open] [--print-url] [--status] [--stop] [--restart] [--port N] [--idle-timeout MIN] [--open-fallback] [--foreground]`；窗口 `/mw decide monitor` 只转发只读白名单参数（`--no-open/--print-url/--status`），**不透传任意 argv**（AC-017；RQ-1 V3）。
- 状态机 `absent → starting → serving → (stopping) → absent`；只有 `/api/health` 通过并写入状态后才算 `serving`。

### 4.2 状态文件（无密）与 secret（有密）
- `.mw/decide-monitor.json`（原子 `os.replace`，照 mw.py:175）：`schema:"mw-monitor/1"`, `instance_id`(uuid4), `pid`, `host:"127.0.0.1"`, `port`, `project_root`, `project_root_key`(realpath+normcase), `started_at_ms`, `code_dir`, `code_digest`, `version`, `serving_since_ms`。
- `.mw/decide-monitor.secret`：控制令牌（32B base64url），`os.open(..., O_CREAT|O_EXCL, 0o600)` 后 `chmod 0o600`（Windows 上尽力；文档写明同用户可读的边界：能读它的攻击者本就能读 decisions.jsonl）。
- 两者都在 gitignore 的 `.mw/`（F19）；日志/状态**不含** secret、page token、boot code。

### 4.3 重复开启（单实例/多窗口）
- 规范化 `--project` → 读状态 → `/api/health`（比对 `instance_id`）：
  - 健康 + instance_id 匹配 + `code_digest` 与 F8 同口径一致 → **复用**：控制令牌 `POST /api/boot-code` 取新 code → 开窗/打印，rc=0，输出 `reused instance_id=… url=…`。
  - 健康但 digest 不同（代码已升级）→ **不静默复用**：`E-MONITOR-STALE`，提示 `--restart`；带 `--restart` 才 `POST /api/shutdown` → 等 ≤10s → 重启。
  - 健康但 instance_id 不同（pid 复用/残留）→ 视为他人实例，只报错，不改不杀。
  - 不健康（拒绝/超时）→ 判陈旧：删状态+secret 后启动。
- 【建议】多窗口语义：每次调用新开一个 app 窗口（服务器幂等、UI 不幂等），不声称"聚焦已开窗口"。

### 4.4 旧实例/版本
- 只认 `schema`：缺失或 `<1` → 不信任，按"陈旧"处理（fail-open 到重启，不 fail-open 到复用）。
- `code_digest` 用现有 `_runtime_digest()`（F8 同函数），避免两套版本语义。
- `monitor --status` 必须给出 `running/stale/reused/foreign` + pid/port/digest 前 8 位 + version。

### 4.5 停止与退出
- `--stop`：`POST /api/shutdown`（控制令牌）→ 轮询 `/api/health` 变不可达（≤10s）→ 删状态/secret，rc=0；HTTP 不可达 → 写 `.mw/decide-monitor.stop`（accept 循环 ≤0.5s 检查，照 F9）再等 ≤10s；仍失败 rc=4 + 打印 pid 与日志尾，**不强杀**。
- 空闲退出：`--idle-timeout` 默认 30 分钟（`0` 关闭），按"最后一次成功请求"计时；退出删状态；页面显示 `disconnected, re-run mw decide monitor`。
- 退出统一 `finally`：仅当 instance_id 仍是自己才删状态/secret，flush 日志，关监听 socket；异常残留由下次启动按 §4.3 三态清理。

### 4.6 多项目
- 状态/secret/stop 锚定**控制根**（`_agenticdoc_root(project).parent`，F18），Windows 用 `normcase(realpath())`，保证 `.` 与 `.agenticdoc/<key>` 落到同一实例（否则两实例抢同一归档）。
- 每实例独立端口，无跨项目协商；`43170..43269` 支撑 ≤100 并发实例，超出 `E-MONITOR-NO-PORT`。

### 4.7 隐藏控制台与窗口 handoff
- 窗口入口必须非阻塞：`python mw.py decide monitor` 自己 detach（`CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP`，stdio→`.mw/decide-monitor.log`，`close_fds=True`，F5），≤3s 返回；**禁止**让服务继承窗口 `spawnSync` 的管道（否则窗口挂到服务退出）。
- 返回前完成健康探测（≤5s，2 次成功且间隔 ≥150ms，照 F7），否则 rc≠0 并打印日志尾与 URL。

### 4.8 退出码【建议】
`0` 已服务/复用/已停止；`2` 参数或项目路径非法；`3` 端口用尽；`4` 停止失败；`5` 浏览器不可用但服务已起（附 URL）；`6` stale 且未给 `--restart`。

## 5. 端口契约
### 5.1 范围取证
- 【事实】F20 在动态端口段之下、排除段之外、当前无监听；F22 不与既有 7001/7003/7004 冲突。
- 【外部】Chromium `kRestrictedPorts` 不含 43xxx（该表集中在 <1024 与 2049/3659/4045/5060/6000/6566/6665-6669/6679/6697/10080）。实现仍要内置受限表断言，否则只能到浏览器侧拿到 `ERR_UNSAFE_PORT`。

### 5.2 分配算法（无 TOCTOU）
```
BASE, SPAN = 43170, 100
start = BASE + crc32(normcase(realpath(control_root)).encode()) % SPAN
for i in range(SPAN):
    port = BASE + (start - BASE + i) % SPAN
    s = socket(AF_INET, SOCK_STREAM)                    # 不设 SO_REUSEADDR（F13）
    if win32: s.setsockopt(SOL_SOCKET, SO_EXCLUSIVEADDRUSE, 1)   # F14
    try: s.bind(("127.0.0.1", port)); s.listen(8)       # 成功即持有
    except OSError: s.close(); continue                 # EADDRINUSE/EACCES → 下一个
    → ThreadingHTTPServer(socket=…, allow_reuse_address=False)
```
- 【建议】`--port N` 只接受区间内端口，越界 rc=2（无"任意端口"后门）；端口用尽 rc=3 + 打印区间与 `port_owner_pids()`（F10）前 3 个占用者，**不对占用进程做任何动作**。
- 【建议】`SO_EXCLUSIVEADDRUSE` 的代价：服务端先关连接会进 TIME_WAIT，快速重启可能绑不回原端口 → 由"继续扫描"消化，**实际端口以状态文件/输出为准**，哈希端口只是"尽量稳定"。
- 【建议】复用探测用"带控制令牌的 `GET /api/health`"，不用裸 connect（裸 connect 分不清"别人的 HTTP 服务"）。

### 5.3 失败模式
| 场景 | 行为 | AC |
| --- | --- | --- |
| 某端口被占 | 静默下一个候选，日志 `port_busy=<n>` | 006/007 |
| 全部被占 | rc=3，列出区间与占用者 pid，不启动 | 007 |
| 监听者不是我们 | 不 kill、不复用、不写状态，明确报 foreign listener | 007 |
| bind 成功但 listen 失败 | 关闭 socket 继续下一个，绝不半启动 | 007 |

## 6. 浏览器应用窗口契约
### 6.1 探测顺序【建议】
1. `MW_MONITOR_BROWSER`（显式路径/命令；设了但不存在 → rc=5，**不静默回退**）。
2. Chrome：`%ProgramFiles%\Google\Chrome\Application\chrome.exe` → `%ProgramFiles(x86)%` → `%LOCALAPPDATA%`（F21 命中第 1 条）。
3. Edge：`%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe` → `%ProgramFiles%`（F21 命中第 1 条）。
4. 可选 Chromium/Brave 同形路径；非 Windows 用 `shutil.which`（本次未实测）。

### 6.2 启动 argv【建议】
`[exe, f"--app={url}", "--no-first-run", "--no-default-browser-check", "--disable-extensions", f"--user-data-dir={profile_dir}"]`
- `url = http://127.0.0.1:<port>/#c=<code>`：**必须 127.0.0.1 字面量**（`localhost` 可能先解析到 `::1`，而服务只绑 IPv4）。
- `profile_dir = %LOCALAPPDATA%\mw\monitor-profile\<hash(control_root)>`（不入仓库；隔离扩展与既有 cookie，避免第三方扩展在带令牌页面注入；代价是独立浏览器进程的内存/首启开销）。`MW_MONITOR_BROWSER_PROFILE` 可覆盖；单 profile 复用列为替代并注明风险。
- `close_fds=True`、stdio→`DEVNULL`（Chrome 会往 stderr 写调试输出）。

### 6.3 启动校验（不得假报成功）
- spawn 后 5s 内退出且 rc≠0 → 抓 stderr → `E-MONITOR-BROWSER-LAUNCH`（rc=5），提示可复制 URL 手动打开。
- 仍在或 rc==0 → 输出 `browser: launched (app mode, not verified)`：**明确不承诺窗口真的出现**（Chromium 把启动交给既有进程时不可观察）。
- 开窗前先确认 `/api/health` 通过（§4.7），否则只会看到连接被拒。

### 6.4 不可用/回退
| 场景 | 行为 |
| --- | --- |
| 找不到 app-mode 浏览器 | 服务照起，打印 URL（含 code + "单次 60s"警告）与安装/指定方法，rc=5，**不冒充已开独立窗口** |
| 显式 `--open-fallback` | `webbrowser.open(url)` 普通标签页，输出 `fallback: normal window (not app mode)` |
| 裸 `http://127.0.0.1:port/`（无 code） | 页面显示"未授权：请重新运行 mw decide monitor"，0 次数据请求 |

### 6.5 URL 令牌泄漏防护【建议】
- 长令牌（控制令牌/page token）**永不**出现在 URL、argv、日志、状态文件。
- URL 只带 **boot code**：128-bit、`secrets.token_urlsafe(16)`、TTL 60s、单次、服务端只存 sha256；`POST /api/session` 换 page token（仅浏览器内存/sessionStorage）。
- fragment（`#c=`）不发送给服务器、不进 `Referer`（【外部】URI 规范：fragment 不参与请求与 referrer 计算）→ 服务端日志天然无 code。
- 进程命令行仍可见 code（`--app=` 参数）→ 这正是用"短时单次 code"而非长令牌的理由。
- `--print-url` 是唯一打印完整 URL 的路径，同时打印"60s 内单次有效，勿外发"。

## 7. 本地 HTTP 安全边界（最小实现）
### 7.1 威胁模型
对手 = (a) 本机其他用户进程，(b) 用户访问的外部网页，(c) DNS rebinding 页面。**不**防"同用户本地进程直接读 `.mw/` 与项目文件"（超出接口能力，且与 decisions.jsonl 明文同级）。

### 7.2 Host / Origin / DNS rebinding
- 只 `bind(127.0.0.1)`（AF_INET，不开 dual-stack），不监听 `0.0.0.0`/`::`。
- `Host` ∈ {`127.0.0.1:<port>`, `localhost:<port>`}，否则 `403 E-BAD-HOST`（rebinding 时 Host 是攻击者域名）。
- 有 `Origin` 必须是 `http://127.0.0.1:<port>`；有 `Sec-Fetch-Site` 且非 `same-origin|none` → `403`。
- 不返回任何 `Access-Control-Allow-*`；`OPTIONS` 直接 `405`。
- **完全不用 Cookie**（无 CSRF 面）；数据接口一律要求 `X-MW-Monitor-Token`。

### 7.3 令牌与 code
| 凭证 | 存放 | 有效期 | 用途 |
| --- | --- | --- | --- |
| 控制令牌（32B） | `.mw/decide-monitor.secret` 0600 | 实例生命周期 | CLI 复用取 code、shutdown、boot-code |
| boot code（16B） | 服务端内存（sha256+exp） | 60s、单次 | 浏览器首次换 page token |
| page token（32B） | 浏览器内存/sessionStorage | 实例生命周期 | 页面所有数据/提交请求 |
- 比较用 `hmac.compare_digest`；失败统一 `401 {"error":"unauthorized"}`（不区分缺/错令牌）。
- 失败限速：401 >20/min → `429` 60s；`/api/session` 单实例 10 次/60s；code 校验失败即丢弃（防爆破）。

### 7.4 方法白名单 / 大小 / 超时 / 并发
- 方法：`GET/HEAD` 只读路径；`POST` 仅 `/api/session`、`/api/book/check`、`/api/observe`、`/api/calls/<id>/cancel`、`/api/boot-code`、`/api/shutdown`；其余（含 `PUT/DELETE/PATCH/TRACE/CONNECT`）`405 + Allow`。
- body：POST 必须带 `Content-Length`，>64 KiB → `413`（先按长度拒绝）；读取 `rfile.read(min(len, cap+1))` 复核；JSON 解析失败 `400`；header 上限沿用 stdlib（F15）。
- 超时：连接 `settimeout(30)`；body 读取总计 ≤5s；观察调用 HTTP 侧 30s（后端 20s +10s 余量，F16）。`protocol_version` 保持 `HTTP/1.0`（F12：一请求一连接，无管线/走私面）。
- 并发：ThreadingHTTPServer，但 `/api/observe` 用 `Semaphore(1)` 串行；第二次 `409 E-BUSY`（不排队，避免隐式积压付费调用）。
- 异常隔离：handler `try/except` → `500 {"error":"internal"}`（不回栈），避免线程异常打断 accept 循环。

### 7.5 模型提交：显式、超时、取消
- 唯一模型出口是 `POST /api/observe`，body 必须含 `dp`、`book`、`state`、`confirm:"human-explicit"`、`test_only:true`；缺任一 → `400`，0 次调用（AC-011/015）。
- 返回 `202 {call_id}`，结果由 `GET /api/calls/<id>` 轮询（1s→3s 退避）；**打开页面/刷新历史/轮询一律 0 次模型调用**（AC-015）。
- 禁止字段（命中即 `400 E-READONLY-FIELD`）：`enabled/mode/apply/exec/signoff/sign` 等授权或执行字段（AC-017）；服务端不读不写 `.mw/decide-points.json`。
- 超时沿用后端 `timeout_s`（F16），HTTP 侧不早于它；超时记 `status:"timeout"` 并保留原因。
- 取消：`POST /api/calls/<id>/cancel` 置 `cancel_requested`；【事实约束】传输是阻塞 `urllib`（decision_backends.py:246-260），**无法中断在途请求** → 只保证"返回后丢弃、不落吸收/不采纳"，标注 `cancel_effect: after_response`。

### 7.6 XSS / 响应头
- 页面 = 本地静态资产（`monitor_assets.py` 内联 CSS/JS，无 CDN/外链）；数据只走 JSON API，前端只用 `textContent`/`createElement`，禁止 `innerHTML`（含错误信息、路径、模型输出）。
- JSON 响应头：`Content-Type: application/json; charset=utf-8`、`Cache-Control: no-store`、`X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、`Cross-Origin-Resource-Policy: same-origin`。
- 页面头：`Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`、`X-Frame-Options: DENY`。
- 若任何服务端渲染引入数据，复用 `usage._html_escape`（usage.py:1940），不新写转义。

### 7.7 脱敏
- 所有来自上游/自由文本的字段（失败原因、原始响应、决策本 note）进 API 响应前过 `decision._scrub_detail`（F17），保留 `redacted: true`；截断同样标记（spec §2.2）。
- 服务端日志同样脱敏，且永不打印 `X-MW-Monitor-Token`/boot code/`Authorization`。

## 8. REST 接口候选【建议】
| 方法 | 路径 | 凭证 | 说明 | 主要失败 |
| --- | --- | --- | --- | --- |
| GET | `/` | 无 | 静态外壳（无数据） | — |
| GET | `/assets/app.js`,`/assets/app.css` | 无 | 静态资产 | 404 |
| POST | `/api/session` | code | 换 page token；`no-store`；限速 | 401/429 |
| GET | `/api/health` | 控制或 page | `{ok,schema,instance_id,version,uptime_s}`；无令牌只回 `{ok,schema}` | 401 |
| GET | `/api/meta` | page | 控制根、registry version、归档统计（行/坏行/链断） | 401/500 |
| GET | `/api/history?key=&dp=&source=&status=&limit=&cursor=` | page | `decide_archive.fold` 后的视图（AC-002） | 400/413 |
| GET | `/api/decisions/<decision_id>` | page | 决策本/请求/返回/吸收/应答 + 未记录/推断标记（AC-003/013） | 404 |
| GET | `/api/dps` | page | 注册表快照 + `required_state_fields` + 授权状态（只读） | 500 |
| GET | `/api/dps/<id>/scaffold` | page | 决策本骨架（AC-009） | 404 |
| POST | `/api/book/check` | page | 纯校验，0 次模型调用（AC-011） | 400 |
| POST | `/api/observe` | page | 显式人工提交观察调用 → 202 `{call_id}` | 400/409/413 |
| GET | `/api/calls/<call_id>` | page | 状态/结果/元数据/脱敏标记（AC-012/016） | 404 |
| POST | `/api/calls/<call_id>/cancel` | page | 置取消标记 | 404/409 |
| POST | `/api/boot-code` | 控制 | CLI 复用路径取新 code | 401 |
| POST | `/api/shutdown` | 控制 | 优雅退出（202） | 401 |
| * | 其他 | — | `405 + Allow` | 405 |

## 9. AC-006 / 007 / 015 验证契约
建议新增 `packages/multi-workers/test_decide_monitor.py`（pytest，不标 `e2e_real`；不起真实浏览器、不打真实模型）。
| VC | AC | 断言 | 证据形态 |
| --- | --- | --- | --- |
| DR1-01 | 006 | 默认候选 == `list(range(43170,43270))`；`server.server_address[0]=="127.0.0.1"`；`allow_reuse_address is False`（类属性，跨平台） | 纯单测 |
| DR1-02 | 006 | 状态文件 schema/字段齐全且**不含** code/token；`--status` 含 port/pid/digest8 | 单测 + tmp_path |
| DR1-03 | 006 | app-mode argv 纯函数：`[exe,"--app=http://127.0.0.1:<p>/#c=<code>","--no-first-run",…]`；探测顺序用假 exe + `MW_MONITOR_BROWSER` 覆盖；**不 spawn** | 纯单测（注入 launcher） |
| DR1-04 | 007 | 占住 1 个候选（测试自己 bind）→ 选下一个并成功；占住全部 → rc=3 且消息含区间，无状态文件 | 单测（注入候选列表） |
| DR1-05 | 007 | 二次调用 → 复用同一 instance_id/port，仅 1 个监听者；第二进程 rc=0 且输出 `reused` | 单测（注入 health） |
| DR1-06 | 007 | health 不可达 → 判陈旧并重启（状态原子替换）；digest 不同且无 `--restart` → rc=6，旧进程仍活 | 单测 |
| DR1-07 | 007 | 无浏览器（空探测 + `MW_MONITOR_BROWSER` 指向不存在）→ rc=5、打印 URL、服务仍健康、输出无"已打开窗口"字样 | 单测 |
| DR1-08 | 015 | 无令牌/错令牌/坏 Host/坏 Origin/`Sec-Fetch-Site: cross-site` → 401/403，后端调用计数 == 0 | 单测 + stub backend |
| DR1-09 | 015 | GET `/api/meta`、`/api/history`、轮询各 10 次 → 后端计数 == 0；只有 `POST /api/observe` 使其 +1 | 单测 |
| DR1-10 | 015 | `PUT/DELETE/TRACE/OPTIONS` → 405 且无 `Access-Control-Allow-*`；65537B body → 413 且计数 0 | 单测 |
| DR1-11 | 012/015 | 两个并发 `POST /api/observe` → 1×202 + 1×409，后端计数 1；取消后该 call 标 `cancel_effect: after_response` | 单测（线程） |
| DR1-12 | 005/015 | `monitor.log`、状态文件、`/api/*` 响应均无控制令牌/boot code 明文；上游错误被 `<redacted>` 且 `redacted:true` | 单测（注入含 `sk-…` 的错误） |
| DR1-13 | 007/017 | 未认证 `/api/shutdown` → 401 且进程仍在；带 `enabled/mode/apply` 的 observe → 400，计数 0，`.mw/decide-points.json` 字节不变 | 单测 |
| DR1-14 | 007 | `--idle-timeout` 注入 0.2s → 退出、状态/secret 删除、health 不可达 | 单测（短超时） |
| DR1-15 | 006/007 | 手工验收（不进 CI）：真实 `mw decide monitor` 弹 app 窗口、`--status` 可查、关浏览器后空闲退出 | 人工（显式触发） |
- 【建议】真实 Jev 调用（AC-004/016）不在本卡自动化范围：人工显式提交、loopback、隔离生产（spec §2.2）。
- 【建议】CI 端口测试不复用 43170..43269（并发互撞），注入自定义候选；默认范围由 DR1-01 纯函数覆盖。

## 10. 未覆盖 / 未验证
1. **未实测** `--app=` 真实行为：窗口样式、重复调用是否新开窗、`--user-data-dir` 首启开销、返回码语义（只给 argv 契约与 "launched, not verified"）。
2. **未实测** Windows 防火墙对 127.0.0.1 监听是否弹窗（本卡禁止起服务）；只保留"URL 可手动打开"回路。
3. `SO_EXCLUSIVEADDRUSE` × TIME_WAIT 的快速重启行为未实测；用"继续扫描 + 端口以状态文件为准"回避，不承诺端口稳定。
4. Chromium 受限端口表属外部知识，未本机验证；实现需内置断言。
5. 阻塞 `urllib`（decision_backends.py:246-260）无在途取消；`cancel_effect: after_response` 是设计上限而非已验证行为。
6. 待 PM 合并决策：页面资产组织、`--idle-timeout` 默认值、浏览器 profile 是否默认隔离。
7. 本卡不覆盖：记录 schema/关联 ID/吸收链（D-RQ2）、25 DP 字段契约与测试隔离权限（D-RQ3）、窗口只读白名单实现（RQ-1）。
