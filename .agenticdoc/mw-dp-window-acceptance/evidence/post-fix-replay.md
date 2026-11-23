# 三项修复的隔离复验

最终工作树在三个实现 key 的变更合入后，由 Codex PM 验证。用户已授权的独立验收子代理在自己的临时工作区按相同冻结输入复跑，最终结果 21 通过。复核测试以当前源码和传输替身执行。

```powershell
python -B -m pytest -q -s --tb=short -p no:cacheprovider --basetemp=.tmp/wa-independent-final .agenticdoc/mw-dp-window-acceptance/evidence/test_window_replay.py
```

| 修复 key | 复验结果 |
| --- | --- |
| mw-dp-candidate-diagnostics | SceneProfiler 原始材料的诊断一致。混合输入中保留一次缺候选和独立证据行越界，零发送。 |
| mw-dp-qg-pass-preflight | 缺独审的 pass 零发送，宿主把下一步给 PM 补当前独审。旧快照和撤销认领均零发送。仍有合法 reopen 的对照发送一次。真实独审形态的正控允许 pass，发送前证据变动零发送，发送途中变动零业务动作。 |
| mw-vc-layout-parsing | Gaze 八条单行与 Render 六条多行均解析。等价内容和标点身份稳定，缺字段和重复编号带文件及行号。 |

八次历史原始输入仍因实际需补材料而零发送。Gaze 第二次已识别当前 VC，剩余术语问题仍反馈。UE 的引用修正仍为 ready 后一次发送 narrow，Render 的范围与术语修正仍返回 finding 的下一步。没有在生产窗口 apply、写业务结果或发起裁决。

独立复核另外验证了有有效 finding 时只可见 fix，以及同时有真实结构的合同冲突时可见 fix/reopen。没有发现正常 CLI 有绕过发送后新鲜度检查的入口。

完整 npm 检查在隔离源码副本通过。较宽的 Python 回归记录 137 通过、4 失败。三项签收正控缺当前独审证明，另一项在 Windows 文件替换时被拒绝。原窗口验收保留 VERIFY，待真实运行版本和写入链路复验。 [npm 检查](../../mw-vc-layout-parsing/evidence/npm-check.log) [扩展回归](../../mw-vc-layout-parsing/evidence/broad-regression.log)
