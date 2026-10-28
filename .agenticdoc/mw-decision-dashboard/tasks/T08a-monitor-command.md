# T08a monitor Python命令功能闭环

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；spec.md AC006和design.md monitor命令；原T08-cli-records.md。
- `packages/multi-workers/mw.py:10940` decide argparse；`decision_monitor.py:2254` ensure_instance/:2387 serve/:2459 launch_app_window。
- T12a已交付窗口薄转发monitor但Python invalid choice，真实开窗闭环仍缺。T11a独占monitor/assets，本卡只能mw与新test，不争文件。T05q独占decision/points。

## 要求
接通 mw decide monitor、monitor status、monitor stop与私有starter子进程入口，复用T10真实ensure_instance/serve/launch_app_window及锁与token协议，不重写monitor实现。用户命令monitor确保实例并换boot再启动Chromium app；status/stop不擅自起服务，错误非零，root未知failclosed。
生产运行流程可启动自己的独立monitor而不是shared serve，测试只隔离tmp子进程和stub browser，不实际用户浏览器。真实Chromium窗口验证仍未授权，不自报可见；spawned/visibility如实，不输出secret/boot token到公开日志。startup child argv/cwd明确，端口43170..43269只127.0.0.1。
先全文分页读mw和相关接口，保存基线，真实RED再GREEN。实际CLI subprocess测试通过私有入口在tmp独立monitor生命周期，cleanup只自身进程/端口，禁起停共享mw服务/无关listener。若需monitor文件改API报告T11a owner，不越面。
无凭证也可看历史，不读真实auth/生产记录；tmpHOME/USERPROFILE/auth/env后缀隔离，浏览器stub，loopback允许。保留旧decide run/sign和T05快照接线，不混人工来源记录/T08其它功能。

## 写入允许面
- `packages/multi-workers/mw.py`（仅monitor命令接线）
- `packages/multi-workers/test_decision_monitor_cli.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-monitor-command/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T08a-*`

## 写入禁止面
monitor/assets/decision/points/backends/其他源测试/生产凭证账本/依赖锁/dist/任务相位。

## 验收命令
包目录 `python -m pytest test_decision_monitor_cli.py -q` 加现有CLI窄回归，完整argv/cwd/UTC/exit/依赖hash全日志，实际子进程fixture。root只读严格biome/check子步，完整check未跑不等价，禁build/commit/全包pytest/真实browser/Jev。

## 改动历史
- PM功能闭环优先，拆原T08 monitor子项不等待T05或记录来源；T12a窗口入口已在位，本卡完成后monitor不再invalid choice。

## 交付格式
report最多110行，真RED/GREEN、窗口到Python argv与独立服务生命周期、secret输出安全、浏览器模拟与未覆盖，不自报整体T08或真实可见窗口完成。
