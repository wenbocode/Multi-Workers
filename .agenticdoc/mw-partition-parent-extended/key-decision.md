# KDR: mw-partition-parent-extended

## R（需求）
- 技术栈: TypeScript（pi 扩展）+ Python（mw 框架）
- 边界: 不做切出/复制/合并流程、不做写路径防火墙、不改 dual/single 与 cwd/撕裂/doctor/trace 语义
- 关键约束: parent = 分片工作区的扩展可写目录（用户 2026-09-20 修正："就当 parent 是扩展目录，直接开发就行，可以写回"）；fail-closed 既有路径（含空 read_scope 全拒）零变化；TS/Py 渲染 line protocol 双侧 1:1
- 语义取代: mw-target-partition spec §1.1「parent 只读语义」/§1.4「不包含写回」/§4 欠债「parent 无写路径防火墙」——旧 spec 归档不回改，本 key 为现行事实源

## A（架构）

- D001 执行点: 选Py展开+worker union双层，否单层（TS路径覆盖+frontmatter透明）
- D002 union载体: 选read-scope.ts两纯函数+wiring重读，否扩parseTaskMd（接口面零波及）
- D003 不作用域: 选仅非空scope，否scope非null即并入（空scope全拒红线）
- D004 解析门控: 选模式行正则+前缀匹配，否marker定长取行（对齐撕裂锚+标签兼容）
- D005 Py追加顺序: 选[条目,control,parent]+normcase判重，否parent先行（断言族冲突最小）
- D006 标签措辞: 选extended workspace,writable+mw.py两处，否保持旧标签（语义显性化）
- D007 测试布局: 选既有文件内增量，否新测试文件（归属地+修改面限定）

## I（实施）← PM 执行中追加
