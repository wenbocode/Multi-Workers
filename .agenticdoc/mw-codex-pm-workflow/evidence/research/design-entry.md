# 接口依据

pm/ui-bridge.ts 中 registerWorkerTools 的 dispatch_worker 显式接收 key、task_key、card_path，并运行外部 claim 和卡片门禁。自动驾驶 dispatch.py 会记录 conductor 来源；PM 路径应通过原有手动写者。mw_common.py 的 parse_workers_queue、worker_owner_key 和 workspace_root 可供恢复与验收复用。test_integration.py 已有独立 launcher、临时项目和假 worker CLI fixture。
