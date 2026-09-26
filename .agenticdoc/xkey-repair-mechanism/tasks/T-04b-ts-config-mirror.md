# T-04b TS config 镜像补齐（跨包缺口，小卡）

key: `xkey-repair-mechanism` · 依赖: T-03（Python 侧 config 已落地） · 覆盖: AC-008 的跨包一致性

## 背景（已核实的真实缺口）

`packages/multi-workers/autopilot/config.py` 已新增三个键（`xkey_repair` / `xkey_verify_cmd` / `xkey_verify_timeout_s`），但 TS 镜像未同步：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:118` 用 `known = new Set(Object.keys(DEFAULT_CONFIG))` 做已知字段集，`:122` 对未知字段报错 fail-closed。⇒ 一旦项目 `config.json` 写入 `xkey_repair`，TS 控制台会判配置非法并丢弃该键。

## 改动（只 mirror，不放宽任何既有校验）

1. `AutopilotConfig` 接口（`:67-80`）+ `DEFAULT_CONFIG`（`:82-92`）：加
   - `xkey_repair: boolean`（默认 `false`）
   - `xkey_verify_cmd: string[]`（默认 `[]`）
   - `xkey_verify_timeout_s: number`（默认 `1800`）
2. `BOOL_FIELDS`（`:94`）加 `"xkey_repair"`。
3. 新增 `LIST_FIELDS` 校验，**逐字镜像** `config.py` 的语义：`xkey_verify_cmd` 必须是「非空字符串组成的列表」，否则报错（错误文案风格与既有 `unknown field(s)` / 类型错误一致）。
4. `INT_RANGES`（`:97-105`）加 `xkey_verify_timeout_s: [1, null]`（对应 `config.py` 的 `(1, None)`）。
5. 检查 `DEFAULT_CONFIG` 的消费方（读取/合并/落盘路径）是否会因新增数组字段而出错——若 `AutopilotConfig` 类型被别处按「全是 number|boolean」处理，需一并修正类型；报告须列出你核验过的消费点（file:line）。

## 验收

- `npm run check`（全量输出，不 tail）干净。
- 单测/手动证明：① `{"xkey_repair": true, "xkey_verify_cmd": ["python","-m","pytest"], "xkey_verify_timeout_s": 60}` ⇒ `validateConfigData` 返回 `[]`（零错误）；② `xkey_repair: 1` ⇒ 类型错误；③ `xkey_verify_cmd: "pytest"` ⇒ 列表类型错误；④ `xkey_verify_timeout_s: 0` ⇒ 范围错误；⑤ 未知字段仍报错（不得因本次改动放宽）。
- 报告含：`git diff --stat`、五条验证的真实输出、核验过的消费点清单。

## 纪律

- **只写** `autopilot/status-model.ts`（+ 报告）。不改 Python 侧、不改 guard、不改其它扩展、不跑 `npm run build`/`npm test`、不 commit。
- 不引入新依赖；类型不使用 `any`。
