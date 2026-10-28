# 首次PM verifier失败留史

命令：`python -B .agenticdoc/mw-dp-consolidation/evidence/implementation/t06-r2-pm-handoff-20261026/check.py`；实际rc=1。

原始错误：
```
Traceback (most recent call last):
  File "H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\evidence\implementation\t06-r2-pm-handoff-20261026\check.py", line 55, in <module>
    assert sha(actual_diff)==worker_after[name]['diff_sha256']
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```

发生在产品after字节与worker/PM before校验通过后、任何pytest/probe子命令之前，不能算pytest失败或产品负例。原script/已生成before-inventory及第一产品原始bytes/PMdiff不改写。完整读取两worker diff后，待单独量化raw磁盘SHA、CRLF→LF内容SHA及字符/字节数以定位after.json元数据与write_text Windows落盘的差异；不同SHA不能默称exact disk parity。

新验证另写completion目录，成功与否均不能覆盖本次失败或改worker原证据。worker关于相同before证明不存在其它瞬时writer的措辞不获PM背书，净hash仅证明本次观测起点字节相等。
