# 用户确认的工作台可读性修订（2026-10-23）

## 并行性分析
后端事实投影/观察questions/离线case与前端图形/格式化渲染可按文件边界并行。后端独占decision_points/history/monitor与case脚本生成物及后端测试；前端独占html/js/css及DOM/assets测试。同文件单writer，PM串行文档和最终验证。无需追加研究：依据用户确认及已读取真实记录、源码，不派研究模型。

## 设计
保留10节点及现有边界：key/role/dp/input/decide/request/model/response/receipt/action。有向图表达既定流程，不凭连接线推断成功。前端画节点和箭头；点击侧边详情，生产/test共用。无需新依赖。
input只呈现快照实际业务state，不展示book wrapper。request/response从安全化实际capture.text解析格式化，非JSON显示原文；复制原始捕获文本，不改事实，不称格式化字节原文。缺失/脱敏/截断明确，元信息仅必要警告不铺字段。
日志默认仅时间/关联key-task/发起角色/请求/响应/接收处理结果/错误，去来源阶段决策本版本hash等栏目，不删除底层必要日志。
low-confidence显示未采纳而非API失败，展示建议选择、API confidence、本次阈值、人工兜底原因。持久记录本次生效阈值供history读取；旧记录不以当前配置猜阈值。本次实链trace detail若已有阈值可精确读取，不猜。四主状态闭集保持，未采纳可仍归failed但节点文案区分策略拒绝。
四离线case有完整原生questions。测试UI材料及问题可编辑，预览model/state/questions，server以同一构建路径验证/发送而非预览另造。questions override仅观察路径，不写生产registry/授权。dp3候选id/label/description只维护state一份，原生criteria生成完整说明；instructions可测试编辑，冲突显式拒绝/规范化并让预览展示最终值。保留typed业务材料校验及8192B预算/安全门，不恢复legacy审计schema。

## 验证
AC015修订，追加AC021图形10节点/有向边及点击、AC022材料与实际正文可读/复制不变、AC023本次阈值诚实、AC024完整case/questions编辑仅观察。RED必须真实DOM及loopback行为，源字符串搜索不独占验收。known-secret所有新展示/API/错误/复制面继承安全输出。PM停写后定向复验与全npm check（保护外来diff），未真实browser不冒称视觉验收。此次不追加真实模型、不build/install/commit/service/framework变更。
