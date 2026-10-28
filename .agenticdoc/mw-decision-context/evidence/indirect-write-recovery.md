# PM补偿登记：Python r2两处间接写

时间：2026-10-23T04:07:57.125316Z。命令 `python -X utf8 .agenticdoc/mw-decision-context/evidence/verify-python-indirect-writes.py`，exit 0。只在内存重放归档脚本的AST literal/替换，不执行归档脚本，不写源码。

| 路径 | actor脚本（Python r2 evidence） | 首写前SHA256 / bytes | 当前终态SHA256 / bytes | 重建 |
|---|---|---|---|---|
| packages/multi-workers/decision_dashboard.js | patch_dashboard_js.py | bd8a374f74e25be31d8e62204e6c9505a86614a5dc2613ac9485a066b6b349c1 / 99997 | 359117cfde64af9d38ef0643d8c75b42aee4465526fd18f4aba95eba3f6571e4 / 100635 | snapshot+唯一old/new替换，LF bytes逐字一致 |
| packages/multi-workers/test_decide_sign_auto.py | rewrite_sign_auto_tests.py | ec4f5edacd75087b6ae4dacc867147b2ec494eef648d1ad700ba17cd8c4dca99 / 29402 | 047684d4e7290ceaab49088c537b1c282801b56b7aa15bdb8434ceabfee833ce / 24890 | snapshot+REMOVE15/NEW10重放，Windows CRLF bytes逐字一致 |

业务审查：见integrity-review.md §2。dashboard withheld筛选不回插秘密；sign_auto退役旧计数入口、替代拒绝矩阵，删除用例映射需结合新stdin签收套件而非仅拒绝测试推断。

此文件是PM事后补偿登记，不伪造原worker trace/ledger已登记，不修改needs-clarification历史终态。证明范围仅两处r2写入与归档脚本完全对应；不等行为复验或全AC验收。

TS审查限定：UTF16/CP936捕获存在有损吞字节；确定性转换不等单射，两个乱码diff一致不能推出底层原始字节一致。审查“无关原文全一致”尚未证实。HEAD相同仅证明共享pre-image，不恢复baseline新增行丢失字节。暂记录未发现阻塞级语义损伤，字符/字节盲区保留，须寻找可靠原文再判，不猜修。
