# MW 窗口过夜值守

一个班次可以绑定多个项目。原 PM 继续认领项目 key，值守窗口处理班前委托的一次性例外和异常。需要 Node 24、已安装本仓依赖，以及同机运行、持有目标 key 的交互式原 PM。

## 指定项目和 key

在新 PowerShell 窗口从受信任的 MW 仓库启动，项目配置会加载值守命令。

```powershell
cd E:\gitlite\Multi-Workers
pi
```

在 pi 内输入以下命令，将引号中的路径和末尾的 key 换成业务项目的实际值。

```text
/duty-on "E:\工作区\项目 A" example
```

首次接入旧项目时，若原 PM 进程存活但收件端尚未上线，值守窗会显示将更新的项目设置路径。确认后，命令在目标项目的 `.pi/settings.json` 登记本仓的收件和值守扩展，保留已有配置。在受信任的原项目窗口空闲时执行一次 `/reload`。值守窗自动等同一认领者上线后接班，期间不调用模型。`/duty-off` 可取消等待；原进程退出或换主也会终止等待。后续原窗口启动时 pi 会自动加载配置。这一步只接通窗口，班次授权仍由原 PM 按下文登记。

目标就是 pi 的启动目录时可用 `/duty-on . example`。命令按项目和 key 查在线绑定。原 PM 已用 `/duty-report-on <班次文件>` 登记本班授权时，新窗口仅接指定目标，复用原卡预算、范围和截止时间。若尚未登记，立即进入只读观察，持续空闲、worker 丢失、离线等状态变化会在窗口提示，不调用模型或发送方向。要启用班次委托下的自动接续，原 PM 登记班次后，在值守窗执行 `/duty-off`，再执行同一条 `/duty-on`。原卡改动或原 PM 换绑后需要重新核对并登记。原 PM 也可用 `/duty-report-on . example` 重新接入已登记且绑定匹配的班次。

从其它目录启动 pi 时，可用 `pi -e "E:\gitlite\Multi-Workers\packages\multi-workers\window_duty_extension.ts"` 加载相同命令。`-e` 只加载扩展，接哪个目标由窗口里的命令决定。

## 离线回放

窗口值守的联合定向命令（临时 project/home、harness + faux provider，无真实 PM 或 provider 通信）：

```powershell
# 仓库根；测试进程不应带 PI_WORKER_TASK
node --test packages/multi-workers/test_pm_watch.ts packages/multi-workers/test_window_duty.ts

# packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mw-window-duty.test.ts test/suite/codex-pm-channel.test.ts
```

这些命令验证源码与模拟集成，不替代独立审查、当前窗口加载或业务验收。完整班次历史回放可单独在仓库根目录运行：

```powershell
node --test packages/multi-workers/test_window_duty.ts
```

输入在 `fixtures/window-duty-night-20261116.json`。十条停点分别记录北京时间、业务方向 ID、当时的事实摘要和证据路径。三个后继停点沿用次日 08:54 方向的关联 ID，回放时刻取前夜终态。默认使用便携摘要；设置 `MW_DUTY_REPLAY_EVIDENCE` 为历史快照目录后会逐件校验源文件 SHA-256 并使用其原文。规则读取班次卡，期望唤醒 ID 只在测试断言中使用。

回放在临时目录创建三个项目及一个虚拟用户目录。它运行实际窗口扩展处理函数、落盘通道、时间与预算判定。UI、时钟、助手回复和后续业务产物使用模拟输入。输出中的 `started` 来自原窗口收件逻辑；业务产物用于验证接续与结算协议。真实业务验收仍归原 PM。

## 新班次

在控制者目录准备一个 JSON 班次文件。时间写带时区的 ISO 8601。用 `node packages/multi-workers/pm_channel.ts status --project <项目> --key <key>` 获取原窗口的 claim、binding、session。按各项目当前授权填写卡，而后在接班期间保持文件固定。

```json
{
  "shift": "night-demo",
  "start": "2026-11-16T23:00:00+08:00",
  "end": "2026-11-17T08:00:00+08:00",
  "targets": [{
    "project": "E:/project",
    "key": "example",
    "claim": "HOST:123",
    "session": "<原 PM 会话>",
    "binding": "<原 PM 的 binding UUID>",
    "minutes": 150,
    "rules": [
      {"name":"repair","limit":60,"scope":"原任务卡所列适配器、追加测试和证据","direction":"修复已执行动作的归档并保留独审。"},
      {"name":"first-build","limit":15,"scope":"批准卡列出的五个目标","direction":"按指定卡和独立准入条件构建一次。","exception":true},
      {"name":"resource-check","limit":10,"scope":"目标锁与已列进程","direction":"只读核实冲突，一次重新预检。","requires":"first-build","once":true}
    ]
  }]
}
```

`scope` 和 `direction` 由授权者编写。发回原 PM 的可执行方向固定取自这些字段。原卡写面、环境门禁与预算检查继续生效。接班会按规则上限、声明的本轮分钟、项目余额和班次截止核算；本轮分钟须包含 PM 验证和独审。需要并行的工时在申报时相加。批准后预留，核实结果后按实际分钟结算。旧班次在途方向沿用既有额度。每项 `exception` 可裁决一次；`requires` 只引用同卡曾批准且原 PM 已响应的例外。

1. 原项目 PM 加载 `packages/multi-workers/window_duty_extension.ts` 后执行 `/duty-report-on <班次文件>`。已有 PM 可按 pi 的扩展加载流程载入。原窗口必须匹配实际进程 claim、绑定和会话。
2. 交班时退出旧值守，保留未决事件的 ID 和证据。旧版 Codex 监听器没有目标锁，迁移前应核实旧监听已退出。新版本在接班时按项目与 key 独占监听及发送。不同目标可以继续由不同值守者负责。
3. 在全新交互式 MW/pi 窗口执行 `/duty-on <项目路径> <key>` 接指定目标，也可执行 `/duty-on <班次文件>` 接整张卡。监听器从目标的持久记录对账。仅打开窗口或载入扩展不会接班。
4. 原 PM 在有新终态或等待条件变化时使用 `mw_duty_report`，填写稳定 UUID、动作名、状态、所需分钟、停因、门禁及相对于该 key 的证据文件。首次接入尚无结构化停点时，监听器在持续空闲后提示原 PM 提交一次。历史 Markdown 的业务含义由原 PM 转成停点；监听器不从自然语言推断授权。
5. 值守窗口在例外事件上收到最小摘要，通过 `mw_duty_decide` 批准或拒绝。超范围、预算不足、门禁阻塞及班次结束会记录交班通知。发生身份或回执异常时，值守窗口查证并在窗口报告。无外部通知渠道时，用户从本机窗口和审计文件查看这些事项。
6. 原 PM 接到方向后用同一 ID 上报 `state=result`、实际消耗分钟和一份新的进展证据。收件后的 `started` 与进展分别记录。没有业务证据到约定时限、原 PM 再次持续空闲时，升级一次。方向被拒、回执失败或进程在收件后退出时保留原 ID 与预留，供接班核对。

## 对账和停机

原 PM 工具原子更新每个 key 的 `duty/<shift>/current.json`，并在 `results/<事件 ID>.json` 保存不可覆盖的结算。证据文件必须在该 key 内，按 SHA-256 流式核对。相同 ID 的停点事实固定；新事实产生新 ID。发布下一停点前，应先报告上一项的结果或阻塞。最新停点是接班时的待办，旧方向与回执可在通道里独立核对。

值守账本位于本机用户 PM 通道的 `<key>/duty-ledger/<shift>.json`。预留和发送方向先落盘再发送，重启按同一 ID 和正文恢复。班次文件旁的 `duty-audit/<shift>.jsonl` 记录接班、值守唤醒、用户事项以及助手响应实际报告的模型用量。

`/duty-off` 释放本窗口的值守锁。在目标的 `duty/<shift>/` 放置 `STOP` 会停止该目标的新工作，并使尚未被原 PM 取走的本班方向失效。已开始的工作由原 PM 按原截止收尾。换主、换 session 或绑定变化时核对在途方向，再重新交班。08:00 后重新打开旧班次只核对并提示遗留。
