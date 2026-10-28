"""Record plan.md section 7.8 = W-12 absorption (B3 e2e dual-channel parity)."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")

ADD = """
### 7.8 W-12 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑双侧复核**：TS `test/suite/write-face-e2e.test.ts` = **8 passed**；Python `test/test_write_face_e2e.py` = **7 passed**；`git status` 只多这两个 `??` 新文件（**未动生产代码**）；精确禁用项扫描（`.only(`/`.skip(`/`.todo(`/`pytest.mark.skip`/`xfail`）**零命中**（两个文件里 `only/skip/todo` 字样都出现在文档注释里）。
- **B3 三项结论（worker 自报，PM 采信其原始证据行 + 自跑复现）**：
  1. **双通道逐字段对照 0 不一致**：同一装置把语料 parse 23 + overlap 59 = 82 行喂给 conductor `_write_face_verdict` 与 PM `dispatchTask`，比 `ok`/`code`/`overlap-with:<task_key>`/`sample`/`serial-only` = **410 次对照全一致**，且两通道都与"按文档算法写的 projection"一致（同为 0）。**base 对齐坑已量化**：故意错对齐 → 4 处不一致（P12/P15/V55/V56 全是绝对路径项），显式对齐 → 0。这是对本 key 最核心主张（AC-007 两通道同判定）的收口证据。
  2. **AC-005 反证成立**：conductor 与 PM 实派后复算 **0 对**同 key 同文件多写者；人为绕过闸门直写队列行后复算 **1 对** ⇒ 这个 0 来自检测器拦阻而非空集（**检测器不自证**）。
  3. **AC-013 双向对照成立**：真写族（`..` 逃逸 / 仓外绝对 / 非法否定项 / 目录目标越界）两通道全拒；假写族（`Write-Output a <term> --glob x` 家族 11 条 + 只读 3 条）两通道 14/14 放行；运行期 `write`/`edit` 与 `bash` 两条真实注册路径上真写 4/4 拦、假写 0/14 拦。
- **仍未闭合的一处（PM 早前读码发现，本卡未覆盖）**：**拒绝分支的 `reason` 串两通道仍不等**——Python `_write_face_verdict:1169` 回 `f"{parsed.code}: {parsed.detail}"`（detail 形如 `entry '<raw>'` / `present-but-empty write_face head`，`write_face.py:654/668/674/685`），TS 侧 `writeFaceVerdict` 只回 `code`（TS 算子 `WriteFaceParseResult` 的 `rejected` 变体不带 raw entry，`shared/write-face.ts:134/514`）。W-12 的 5 个对照字段**不含 `reason`**，故未被这次对照发现；该串会经 W-13 的 `writeFaceRefusalDetail` 进入 PM 审计行 ⇒ 同一非法输入在两通道留下不同的审计 detail。**PM 判定**：这是 AC-007 的最严读法下的缺口，且已在 W-13 的审计面上可见，故**不留给"遗留"**，派 `wfg-i14-reject-reason-parity`（T-W-I14）收口后再进质量门。
- **B4 决定（PM）**：
  1. **存量卡迁移不做**：D-003（未声明不中断）+ D-115（writable 无 `write_face:` 时回落 `write_scope:`；有 `write_face:` 时以它为准）已保证不迁移也不中断，迁移脚本属可后置改动 ⇒ **不派卡**，在 `achieved.md` 的遗留里点明"若将来要清空 legacy 载体再迁"。
  2. **`dist/**` 未重建是开放的收口障碍**：本 key 的运行期能力只在 `src` 生效（W-12 §残留 3 明确测试经 type-stripping 直接 import `src`）；仓库 `AGENTS.md` 禁止我自行 `npm run build`（除非用户要求），且 `packages/multi-workers/dist/extensions/agent-team-loop.js` 已被**其它 session** 改动（mtime 08:38:48、本会话开工前即 `M`）并导致 `mwds-t23` req-4 的 sha 断言红。⇒ 交由用户在收口时决定重建时机（避免与其它 session 的 dist 写权相撞），本 key 记录为"落地上线前必做"。
"""

text = PLAN.read_text(encoding="utf-8")
if "### 7.8 W-12 终态吸收" not in text:
    PLAN.write_text(text.rstrip() + "\n" + ADD, encoding="utf-8")
    print("plan: appended 7.8")
else:
    print("plan: already has 7.8")
print(f"plan.md lines={len(PLAN.read_text(encoding='utf-8').splitlines())}")
