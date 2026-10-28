# 联合设计候选文档检查（2026-10-26）

## 结论
03:08:59+08:00的新鲜文档检查通过：锁定SPEC原字节一致，53AC→53VC有53行映射、零漏AC/零未绑定VC；12候选架构、11业务Flow、16Coverage行和12Mermaid块。Mermaid rc0、0错误/0警告；phase audit rc0、仍DESIGN。仅文档结构/兼容性检查，不是用户设计批准、产品L2/53AC验收或QG/签收。

## 证据
- `evidence/design-joint-document-check-20261026.json`：完整结构检查测量、fingerprint及三个审核产物SHA256；`evidence/design-joint-document-check-20261026.log`：两框架检查完整stdout/stderr与各自rc0。均已read回读。
- 临时stdlib脚本命令：`python C:/Users/wenbozhou/AppData/Local/Temp/dpc-design-contract-check-20261026.py` → rc0。脚本读取SPEC/锁稿、解析VC四行合同与独立映射表，逐行检查Source和ID，检查章节0～11、每图≤15节点及带条件边；生成新的evidence-requirement.md，并调用原check_mermaid/audit_phase，保存真实输出。运行脚本源归档为`evidence/design-joint-document-check-20261026.py.txt`后删除临时.py，不修改产品/框架源码。末次独立重跑Mermaid/audit仍PASS，三个审核文件Get-FileHash仍同以上JSON。
- SPEC SHA256：`cfe737d29aed2d0c4e79d8b02107f754f254a225bb21ea8d900eaa5ba289d006`；与锁稿原字节完全相同。AC payload SHA为锁定证据继承值，不把编号fingerprint冒充正文hash。
- `ac_fingerprint=767fc1acdbcb`：按workflow-quality-gate的全部AC ID排序去重、每行LF含末尾LF后sha1前12位，已实算。VC未获批准/冻结，生成时间不是VC锁定时间。
- `design.md` SHA256：`e73df377e656490d629e984c3508e1a3e5e9ca09c019bee36a6bba39fc94b7a3`。
- `evidence-requirement.md` SHA256：`332d0a8a28cdef709752e7a3cea0d0793e2ddd78899376ab92473b5e734dc4a4`。
- `design-write-scope.md` SHA256：`8319a45e82fb2d30e8c778615bf3c6ec7992d6fe29bc978bb269aec85a05171c`。

## 失败及最小修正历史
1. 03:05:21初次stdlib结构检查rc0，Mermaid子命令实际失败：157个R2“连线标签带引号”错误、0warning；后续audit rc0，因此组合shell最后exit0不能用作Mermaid通过。原完整失败输出在本轮tool回读中，未另持久化全部157行，不伪称已有完整失败log。
2. 根因已读全check_mermaid.py：R2明确拒绝边的双引号；workflow-system-design Step4示例/文字却引导边加引号。旧三图无边引号原可通过，本轮照示例新增引号导致157错误，不是provider或运行问题。
3. 只对本key12图的边标签做精准edit，移除边的双引号，中文节点/判断标签仍保留引号；graph TD、节点、条件及动作含义不变。未修改框架规则或绕检查；stdlib辅助检查同步按实际兼容规则检查。
4. 03:08:59重新完整执行，生成/映射/12图check与audit均rc0。该修正仅文档语法，无产品修复/测试结论。

## 残留与未验证
- D012A模型选择预备理由与原生自由理由的差异须用户明确审核；当前backend只解码choice/score/noul，不能拿note/失败reason冒充理由。
- human ask目前是自由问题直连模型，human-only隔离保留须审核并实际证明；H12真实来源/权限/受限writer隔离仍须产品L2证明，不是自报token或移动tick。
- 框架advance_phase.py及配套test_advance_phase.py候选特批面尚未授权；不修改安装镜像或部署。
- 源caller全面分类、生产行为、安装/内存身份未验收；未跑产品测试/check/build/provider/browser/service，未实际gate/预算/刹车恢复/签收或进入PLAN。
- git status展示大量现有/他窗修改；本轮未建立全仓before manifest，不称全仓字节不变。当前agent只写本key文档、临时文档检查脚本与sanctioned claim；原RQ15/16及独立26AC/monitor8AC/formatter/dropdown/dp3等债保留。

## 上下文来源
用户“继续”；锁定SPEC/研究终态及PM设计使用限制；workflow-system-design/quality-gate指纹定义、完整Mermaid检查源码与实际输出。主审核包为本keydesign.md、evidence-requirement.md、design-write-scope.md，均候选而非批准。
