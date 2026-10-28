本文件是 T-ACC 切割验收探针交付物，用于核对 change-ledger 的声明确认与不可解析通道。
探针载荷（常量名形态）：INFRA_DIR_SEGMENTS 是框架内部符号，不应被判为改动清单条目。
探针载荷（代码调用形态）：os.replace 是 Python 标准库调用，同样不是文件路径声明。
探针载荷（幽灵路径形态）：`.agenticdoc/_scratch/evidence/does-not-exist.py` 在磁盘上不存在，应走 unresolvable 警告通道而不是 extra 红判。
本次真实写入仅限本文件与 worker taskDir 下的 report.md、progress.md，未改动任何 packages/** 文件。
验收命令与逐字输出见同 taskDir 的 report.md「验证命令与实测输出」段。
