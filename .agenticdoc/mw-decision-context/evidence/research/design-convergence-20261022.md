# Research: 三路设计收敛与PM纠正

## 方法与出处
- 全文回读D-RQ1/RQ2/RQ3的唯一研究证据、report/output与run.json，均done/exit0并已ack。
- `.agenticdoc/mw-decision-context/spec.md:1` 用户锁定20AC；三research文件的F*为静态事实、方案为建议。
- 本轮没有源码更改、运行测试、真实Jev或浏览器验证。三证据自报行数不计量。

## 关键纠正
- RQ1仅producer删字段不能分离Python注入身份，推荐唯一模型投影；denylist不保证未来闭集，用registry model allowlist。保留本地输入snapshot与model state分别可证。
- 不采用任意字段字节上限；dp25保持四部分，dp3选项说明不裁掉。原2000B能否容纳须完整case运行核实，研究手算不证明。
- dp2零写对research/review不当然异常；最小候选规则只附现有重复目标告警事实，threshold4待用户审核。缺自评不发不消耗资格，所有角色必须有真实自评artifact。
- dp3处理候选/PM路径、dp25三选项、PM无task、四状态含义都是用户确认，不重新作为业务未决。
- RQ2碰撞：同key同DP的多次调用fallback id可能相同，不是三个不同DP共享一个id；未运行复现，只静态推导。
- consumed不是completed。显式record_version识别新旧，新捕获失败不能归旧。失败未落盘不能假定reader能读到失败。
- 两次写交换顺序不跨文件原子；选择可恢复intent/file/commit协议，prepared不代表签收。commit失败不假成功；commit后反馈失败保留签收事实但诚实报告反馈问题。
- 不能沿旧continue/narrow/revoke标签映射新三选项。框架phase仍原门禁，现签收consumer须接commit而非仅存在文件。源码接consumer，不越面改framework脚本。
- RQ3 byte_exact=false不证脱敏，hash不证发送/安全，case省略号是草案非交付，技术副状态不回主表。

## 决策映射
- design.md D001–D003 ← RQ1及以上修正；D004–D005 ← RQ2及修正；D006–D007 ← RQ3及修正。
- 模块与接口皆PM待审核推荐，不是用户已批准架构。
- 验证层统一L0静态/L1局部/L2合成真实路径（faux/loopback/DOM）；浏览器/Jev另列未授权平台验收，不继承RQ3的L1–L5编号混用。
