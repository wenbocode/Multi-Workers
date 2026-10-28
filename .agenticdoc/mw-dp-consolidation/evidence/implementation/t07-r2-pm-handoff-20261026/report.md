# T07 R2 PM 局部交接

## 结论

接受原逻辑T07有界R2的局部纯policy交接，`semantic_handoff_verified=true`仅限当前指定测试与授权关系/unknown边界；不代真实writer、人类身份、H12受控恢复或S2/L2/QG/签收通过。

## 证据

- `completion/check.json`：2026-10-27T02:20:57.765896Z，network-poisoned bootstrap和literal assigned suite各35passed/rc0；17个负例、6个正例、失败0，31个原测试函数AST保留。
- `../s2-r2-fresh-recheck-20261027/check.json`：2026-10-27T03:51:08.699315Z新鲜35passed/rc0，当前policy SHA `77a9282fb8e7cbcd5ec6ffcea8cf2ded73e16f87a06a7808f6ef6d14e06c259c`、test SHA `3947d05db48887ac15df9a7ab5cfe58492e1e017497d0c9d603c5dde4cd94761`一致。
- 原七授权负例/已撤权rule-ref换other-ref绕过被阻断；合法H11 fresh human/显式supersedes仍通过。真实worker red各轮stdout/rc由completion保留引用。
- 1883镜像验证零净变、818个原worker证据hash及14pyc保留。worker run `dpc-t07-policy-r2@2026-10-26T15:52:28.129Z`真实done/exit0，已吸收/ack。

## 改动清单

Worker在原两产品面修复policy/request scope、halt origin与machine-verified guard、breaker disable未知值、恢复规则授权ref和撤权检查；readonly `AuthorityRecord.supersedes`支持合法新授权关系，而非盲目要求ref相等。PM只写验证/状态证据，不修产品或创建真实grant。

## 残留与未验证

- 初始checker因误猜before-bytes文件名rc1，失败脚本/说明保留；completion改用实际双下划线文件名，不改worker证据。
- 实际supersedes writer、TS/T21采纳、可信human/H12与权限/锁/effect链尚未证；fixture授权不是生产授权。分段源文件读取有工具截断，当前边界与AST核对不冒称本轮完整EOF审计或全仓审计。
- 净hash/不存在两live路径不证明全live/瞬时写入/独占作者。14pyc不清，dp4原不可用/PM输入质量限制不修、不重问、不造receipt。
- 原目标、53AC/VC、DAG和预算/部署禁面保留。

## 上下文来源

原T07卡、R2卡、用户有界批准、pre-dispatch基线、原T07 PM七负例与撤权探针、worker R2各轮证据；本目录completion及fresh-recheck为独立局部验证出处。
