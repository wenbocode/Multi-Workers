# ACB-R1 调查结论：matchesWriteScopeEntry（write-surface.ts:292-307）

- 判定规则：条目先 trim，空条目直接拒绝；含 glob 魔字符（`* ? [ ] { }`，GLOB_MAGIC_RE 第 245 行）时走 minimatch 双基准匹配——(a) 项目根相对路径（L298）与 (b) 绝对路径转正斜杠（L299），且 `/**` 结尾的 glob 额外匹配去掉 `/**` 的目录本身（L300-302）。
- 裸 basename/无 glob 条目：走 `isSameOrUnder(normalizeForCompare(projectRoot, entry), absoluteTarget)`（L306），即把条目按项目根锚定后做归一化包含判定（win32 忽略大小写、段边界），目标须等于或位于条目路径之下。
- 本任务 write_scope 两条均为无 glob 条目，按 L306 包含判定命中：任务目录与 evidence 目录均被接受。
