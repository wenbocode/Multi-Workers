# T10 R2原信封派发拒绝（保留，未绕守卫）

## 结论
原新卡tasks/isolated/T10-lifecycle-state-r2.md含5产品、自己rework-r2证据、已获人工限定授权OS子目录。dispatch_worker(dpc-t10-lifecycle-state-r2,type=coding,allow_foreign_write=false)实际拒绝：`write-face-outside-base: entry ' C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/worker-t10-r2/**'`。工具报告Nothing was written，无task dir/queue row。原卡保留不改，不私改dispatcher/guard或把外部写面藏在脚本内。

## 证据
用户限定OS权限已在approval.md；prepare/check真实mkdir成功，拒绝不推翻用户许可。机器worker base与人工许可是两层不同边界，不能用allow_foreign_write的只读角色逃生口发coding或去掉OS面后让worker悄悄执行。

## 改动清单
本新拒绝记录。下一新卡用同逻辑T10分段TDD交接：test-prep worker只写原两test与自己keyevidence，生成但不执行PM脚本；PM作为获批OS测试writer执行真实红测；再原T10产品writer基于实际红测原面修复，PM全suite独立验证。没有新增37逻辑任务/timeout或改原DAG/验收。

## 残留与未验证
目前无R2worker running、未产品测试/修复。PM不是产品实现writer，只直接运行测试；每阶段原五面、744旧证据/14pyc等边界仍保持。不以预期red/人工角色/许可冒充测试已经发生，不把拒绝当产品red。

## 上下文来源
实际dispatch_worker错误、原新卡、approval.md及prepare/check.json。本记录保留原失败信封和源载体，后续新seed不回填原卡SHA或任务。
