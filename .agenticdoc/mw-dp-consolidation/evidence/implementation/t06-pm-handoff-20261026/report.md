# T06 PM independent verification

## 结论

`semantic_handoff_verified=false`。原 worker 的 done/exit0/acked 保留；指定纯判断套件通过不代表语义交接。PM 完整读当前两个产品到 EOF，独立重跑指定套件；新单变量纯判断负例复现签收、契约复用、claim 和未知效果的边界缺口。没有修改产品、派返工或放行后继。

## 证据

证据根：`.agenticdoc/mw-dp-consolidation/evidence/implementation/t06-pm-handoff-20261026/`（本报告内相对路径均相对此根）。

- `check.json`：原 bootstrap/literal 两次指定测试分别 65 passed in 0.12s / 0.14s，子命令 rc0。`check.py` 在测试及 probe 后读取 baseline inventory 时错误假设值为 metadata，实际为 SHA 字符串，退出 rc1；保留原脚本、失败及输出。`finish.py` rc0 仅补完证据，不重跑或改写原测试。
- `supplement.py` 实跑：2026-10-26T12:45:02.364946+00:00，fresh assigned suite 65 passed in 0.11s/rc0；九个业务边界检查均未满足预期，整个 supplement 有意 rc1，不是套件失败或 verifier 异常。完整结果 `supplement.json`，原 stdout/stderr 为 `supplement-test.stdout` / `.stderr`。
- `probe.json` 包含十四个单变量观测与正向 control；`supplement.json` 将九个负例的实际值和预期边界分列。全部只调实际副本纯函数，无 HTTP、CLI、实际 claim/锁/授权/效果/签收写入。
- 当前产品：`decision_validity.py` 54353B / 1652LF / SHA256 `64b9b9e1060aab955a4d0428385e2d450ae94826d1a548088c65f5874c049eb1`；指定测试 49049B / 1297LF / `c9dc013110de702f733b5ec292c1d62ccdaa93d7ffb4fa7ffcec9101c2a97349`；均 CRLF0。
- `pm-full.diff` 106533B / SHA256 `a70b52a5d772b98109122989f3738d1faed9006e1cde1abd5b8206bf240aa974`，从当前完整源机械重构，不宣称整份 diff 逐行人工审计。
- baseline 1864；PM before/after/finish inventory 均1883且相同；supplement 另核整副本 inventory 前后一致。复验净产品变化0。七原允许产品之外14个既有 `.pyc` 留字节/SHA；没有删除。

### 当前复现及源头

下列源码坐标均相对于隔离 `implementation-worktree/packages/multi-workers/decision_validity.py`。

1. **必需签收不能仅认合法菜单词**：line88 将 finalize/continue/user-confirm 全放入 `FINALIZE_CHOICES`；`assess_signoff` line1540 起据此认有效，两个非 finalize 单变量例均 `status=valid,reasons=[]`。同一 fixture 将 key 换为 other-key 或 signoff_ref 置 null 也 valid（函数未核这两个字段）。对应 design §D007/4.2、VC039；不是已发生生产错误签收，函数从未写文件，fixture artifact reference 不是实际产物证明。
2. **证据契约变化没有反映到 verdict**：`assess_evidence` line1014 记录 contract_version_changed，但 line1057 起只按 unknown/stale dependencies 选 status。仅 v1→v2、其余依赖不变，输出 `applies,reusable=true` 同时含换版理由。没有当前合同适用性证明，不能当作无关材料或纯排版复用；不能据此要求所有字节变化重审。
3. **claim 必须保留任务及完整请求边界**：line1446 起把非法路径记录后跳过；包含 safe.py 与 ../outside.py 的请求仍 clear。line1462 把同 owner 全跳过，另 task 的同文件 active claim 仍 clear。这里只证明判据；没有真实锁/双 writer 或越路径写入发生。返工必须保留合法同任务复入，不把模型判断当 claim 转移。
4. **已存在效果的未知状态不能盲重试**：`plan_actions` line1612 起只分 applied / unknown / in-progress，匹配记录 status=unrecorded 或 null 时输出 proceed/actions=[act]。显式 unknown 的 control 被 blocked。缺失/未识别的已有记录状态不等于无记录；未执行任何 action，真实 CAS/锁/崩溃对账仍 T20/T31。

## 残留与未验证

- 定点返工处理尚未获得本轮具体授权，不建立新 R2、不由 PM 修业务代码。既有 `blocked on decision dp4-failure-handling` 原失败事实保留，未重问/绕通道或造 receipt。
- 所有 authority/artifact/claim/effect 都为明确 fixture 输入，不证明生产来源资格、真实签收、实际并发/文件锁或消费者安全；T17/T20/T31 仍需全链验证。
- `ACTIVE_ENTRIES`/`MATTER_OWNERS` 与 T03 单源一致性及全回归留后续；并非全部53VC/L2/QG/签收通过。
- 十四 `.pyc` 存在独立实证，T08自报创建不代独占进程作者证明。完整 live/历史递归或瞬时 no-write 审计未做；只读产品与 inventory 相等不能证明没有其他 writer。
- UTF-8/minimal env、-B、禁 pytest autoload/cache 均为本地验证前提；不批准全仓 locale 改造、npm check/build/install/copyback/部署。

## 上下文来源

- `.agenticdoc/goal.md`；锁定 spec/53AC；approved design §4.3/4.4 与 D007、VC039/052。
- `tasks/isolated/T06-validity.md` / `implementation-isolated-dag.json` 原T06两文件面与只读纯判断责任。
- 原 worker `workers/dpc-t06-validity/{task.md,run.json,output.md}` 及 `evidence/implementation/dpc-t06-validity/{report.md,assertions.json}`；原卡/终态/红绿不改。
- 本轮当前源EOF、`check.json`、`probe.json`、`supplement.json`，历史 verifier rc1明确保留。

## 改动清单

仅本key私有证据脚本/日志/字节库存及本报告；两个业务产品和指定测试未改，原 worker evidence 未覆盖。原7stage/36task及依赖、权限预算、phase不变。
