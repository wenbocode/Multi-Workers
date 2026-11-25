# MW 窗口过夜值守

一个班次可以绑定多个项目。通道仍以文件为准：只读观察只需要 Node 24、已安装本仓依赖和本项目里的一个交互式 pi 窗口，不需要原 PM 在线；完整班次与受限跟进仍由同机运行、持有目标 key 的交互式原 PM 承担委托和身份校验。

## 指定项目和 key

单个窗口即可开始只读观察。在项目目录（pi 的启动目录）打开一个交互式 pi 窗口，项目配置会加载值守命令。

```powershell
cd E:\工作区\项目 A
pi
```

在 pi 内用单参数形式 `/duty-on <key>` 指定项目 key（`<key>` 换成业务项目的实际 key）：

```text
/duty-on example
```

随后用状态工具查看本窗口的观察状态：

```text
mw_duty_status {}
```

单参数的 project 就是该窗口的启动目录，不需要第二个窗口，也不需要原 PM 在线或事先认领。`<key>` 必须出现在目标项目的 `.agenticdoc/_index.parallel` 中且 `phase` 不是 `DONE`，否则命令明确拒绝并保持 `inactive`：未知 key 报最接近的 key 名，已结案的 key 报 phase。两条拒绝路径都不创建租约、不写通道文件、不发消息。

观察只读：`mw_duty_status {}` 返回 `mode="observation"`，`pinnedTargets` 只有该目标且 claim/binding/session 为空（未固定），`observedStates` 来自每 5 秒一次的有界抽样（worker 队列与选中 worker 的 `run.json`）。整个观察不改 `_index.parallel`、不调用模型、不发送方向、不登记班次。状态变化以 `Duty observation: <project> / <key>: <state> <detail>` 提示。

观察不要求目标 key 处于 `active`、claim 进程存活、原 PM 在线或另开第二个窗口。原 PM 没有心跳时状态仍以 worker 队列与 `run.json` 为准，`detail` 附注 `PM offline`；队列中 `status=running`、心跳超过 90 秒且 pid 已退出的 worker 仍报 `worker-lost`（`detail` 列出 taskKey），不会被 `offline` 遮蔽。持续空闲、worker 丢失、状态不可读等停点沿用稳定 45 秒提示一次、同一停点不重复的规则；`waiting-for-worker` 与 `working` 只更新状态，不产生提示。

跨项目目标仍用两参数形式 `/duty-on "E:\工作区\项目 A" example`；目标就是当前目录时也可写 `/duty-on . example`。命令按项目和 key 查在线绑定：原 PM 已用 `/duty-report-on <班次文件>` 登记本班授权且在线、claim/binding/session 匹配时，新窗口仅接指定目标，复用原卡预算、范围和截止时间；尚未登记或原 PM 不在线时进入上面的只读观察。要启用班次委托下的自动接续，原 PM 登记班次后，在值守窗执行 `/duty-off`，再执行同一条 `/duty-on`。原卡改动或原 PM 换绑后需要重新核对并登记。原 PM 也可用 `/duty-report-on . example` 重新接入已登记且绑定匹配的班次。

首次接入旧项目的登记不再是 `/duty-on` 的一步，而是 `/duty-followup-on` 的显式确认步骤（见下节）。`/duty-on <shift.json>` 的班次模式、`mw_duty_decide`、`/duty-report-on` 以及账本、预算和截止时间规则都不因观察入口放宽而改变（见下文新班次与对账）。工作树里的源码不等于当前窗口已加载的实现：改完源码后必须在本窗口 `/reload`，否则仍按旧实现执行。

## 显式受限跟进（无班次授权）

只需要监督窗口核查停点、向原 PM 请求状态或证据时，可明确启用受限模式，无须编造班次卡：

```text
/duty-followup-on "E:\工作区\项目 A" example
```

目标原 PM 必须已在线、处于 `active` 状态、仍认领未完成的 key，claim 存活，且不是当前监督会话；不满足时命令拒绝并保持原模式，通道目录不新增 `.request.json`。单参数 `/duty-followup-on <key>` 同样取当前目录，供观察窗原地升级。首次接线的登记在这一步进行：若原 PM 进程存活但收件端尚未上线，值守窗显示将更新的项目设置路径，确认后在目标项目的 `.pi/settings.json` 登记本仓的收件和值守扩展并保留已有配置，随后在受信任的原项目窗口空闲时执行一次 `/reload`，再重试该命令；拒绝确认则不写文件。只读观察入口本身不登记、不弹确认框。这个命令不接受班次文件，也不会因为目标登记了班次而自动选择完整班次模式。原 PM 的业务范围、门禁、预算和截止时间不变；跟进请求不是新工作授权、Stage grant、DP 决定或批准。

同一实例已观察同一目标时可显式升级，保留自身的 monitor 锁，再取得 send 锁。控制器准备或固定身份检查失败时保留原观察计时器、模式和 monitor 锁，并释放本次新取得的 send 锁；不删除旧 ledger 来绕过失败。重复同目标 `/duty-on` 或 `/duty-followup-on` 只报告实际模式，不重复创建监听器。切换目标、退出完整班次或更换模式前使用 `/duty-off`；不能接管其它窗口持有的目标锁。

受限模式观察到持续空闲至少 45 秒时，通过 Extension API 唤醒监督 Agent。监督窗口忙或已有待处理消息时保留通知；每次实际通知前重新核对当前停点，恢复工作或候选证据变化后不发送旧通知。同一未变化停点去重；暂时离线或状态不可读后，在同一固定身份恢复且重新稳定空闲时，未发送成功的通知可沿用原 ID 恢复。计时器本身不调用 provider。收到通知后，Agent 应先读目标任务卡、worker 产物与工程证据，再使用正式工具：

- `mw_duty_status {}`：报告 `inactive` / `observation` / `followup` / `shift` / `waiting`、固定目标身份、观察状态、待处理通知、outbox 和回执。
- `mw_duty_followup {id,note}`：仅在当前监督会话明确启用受限模式后可用。`id` 来自已发出的停点通知，不能任意生成；`note` 为单行、非空、最多 1000 字符且最多 1600 UTF-8 字节。正文带固定的受限范围说明，由原 PM 核实事实并只在既有授权内行动。

固定 canonical 项目、key、claim、binding、session；每次发送或重试前重新检查身份、连接与未完成阶段。首次发送还核对当前实际状态和停点指纹，恢复工作或证据变化后拒绝旧停点的新请求。离线、完成、换主、换 session/binding 或不可读状态会暂停发送，不能静默改绑。相同 ID 与完全相同正文可对账；修改正文会拒绝。发送结果不确定或仍处于预留状态时，保留原 ID 和正文，跨重启阻止新停点与后继请求，直到按原 ID 得到可核实的传输结果；仅有 `queued` 不清除既有不确定性。状态中的 `deliveryBlockedBy` 指向待对账 ID；`sendAllowed` 表示当前可首次发送，不取消按原 ID 对账的能力。接收窗口将此来源标为 `MW/pi follow-up`，不携带班次或阶段授权。

`queued` / `received` / `started` 和 PM `working` 只是传输或活动事实。状态始终报告 `businessProgress=unverified`；文件与 worker 变化也是待核实候选，不是工程验收。跟进后再次持续空闲且抽样证据未变，仅升级一次“无已验证进展”，不自动反复发送。

候选观察是有界抽样，不是项目全量扫描：优先读取 key 根目录的 `pm-state.md`、`spec.md`、`design.md`、`plan.md`、`achieved.md`，再按目录枚举前缀取样；每次最多枚举 512 项、保留 128 个文件、递归深度 4。超过 256 KiB 的文件只读取前 64 KiB，并结合大小和修改时间。状态的 `evidenceObservation` 报告这些限制、实际枚举数和 `partial`。普通文件数量超限不会使整个模式暂停，但未选文件、深层文件或大文件尾部变化可能漏观测；不保证后续轮询最终覆盖。既有 index/worker queue 的权威解析仍按原接口执行，不受候选目录扫描上限替代。选中文件或权威状态不可读时继续 fail-closed；任何“未变化”摘要仅指本次候选，不代表没有工程进展。

持久记录在本机用户 PM 通道的 `<key>/duty-followup/ledger.json`，不写目标项目的业务文档。固定身份已变化而旧 ledger 仍有记录时，当前没有公开的安全归档/迁移入口；重新启用会继续拒绝，不可删除未决 outbox 或放宽身份校验来恢复运行，须先保全并核对旧记录。`/duty-off`、监督会话变化、shutdown 或 reload 释放本地权限、计时器和锁，保留 outbox；reload 后必须显式重新启用。已有源码、离线测试通过或登记扩展路径，都不证明正在运行的窗口已加载新实现。实际加载及激活状态必须另行核实；未验证时不能声称已恢复自动监督。

从其它目录启动 pi 时，可用 `pi -e "E:\gitlite\Multi-Workers\packages\multi-workers\window_duty_extension.ts"` 加载相同命令。`-e` 只加载扩展，接哪个目标由窗口里的命令决定。

## 离线回放

受限跟进的联合定向命令（临时 project/home、harness + faux provider，无真实 PM 或 provider 通信）：

```powershell
# 仓库根；测试进程不应带 PI_WORKER_TASK
node --test packages/multi-workers/test_duty_followup.ts packages/multi-workers/test_pm_watch.ts packages/multi-workers/test_window_duty.ts

# packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mw-duty-followup.test.ts test/suite/mw-window-duty.test.ts test/suite/codex-pm-channel.test.ts
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
