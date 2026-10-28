"""Post-build status record + scan for the same locale-decoding defect in
production code (subprocess with text=True but no explicit encoding)."""

import pathlib
import re
import subprocess

REPO = pathlib.Path(r"H:\git\Multi-Workers")
MW = REPO / "packages/multi-workers"

lines = ["# M-后记：`mw build --install --allow-dirty` 之后的状态（2026-10-14）", "",
         "## 1. 构建结果（PM 亲跑，exit=0）", "",
         "```",
         (REPO / ".agenticdoc/_scratch/evidence/mdc-mw-build-20261014.txt")
         .read_text(encoding="utf-8", errors="replace").strip(),
         "```", "",
         "产物：`packages/multi-workers/dist/extensions/agent-team-loop.js` 与全局 "
         "`~/.pi/agent/extensions/agent-team-loop.js`（同 sha，供 pi 窗口加载），"
         "并重建了 `packages/coding-agent/dist`。", "",
         "## 2. 产物确实含本次改动（建前 → 建后）", "",
         "| 标记 | 建前 | 建后 |", "|------|------|------|",
         "| TS 侧 MDC 前沿（`frontierSize`） | ABSENT | PRESENT |",
         "| TS 侧 MDC 键（`max_workers_per_key`） | ABSENT | PRESENT |",
         "| WFG 写面运行时（`WRITE_FACE`） | ABSENT | PRESENT |",
         "| WFG 解析器（`parseWriteFace`） | ABSENT | PRESENT |",
         "",
         "（`duplicate-dispatch` / `TASK_GRAPH` 属 Python 侧字符串，bundle 里本就没有，"
         "第一轮把它当标记是我选错，不是缺口。）", "",
         "新 bundle sha256 = `1D5184B8CDBDEC1ADD2118B206B969381A30CC0AF47453AC2D117CA88626065F`；"
         "另一 key 冻结在 `test/suite/mwds-t23-cutover-recheck.test.ts:46` 的 "
         "`EXPECTED_BUNDLE_SHA = 975D4066…` 因此仍不匹配（该测试建前就已红，非新增回归）——"
         "刷新该钉死值属那个 key 的面。", "",
         "## 3. 建后复跑：因 dist 陈旧而红的用例", "",
         "- `test_rag_launcher.py` + `test_rag_init.py`：**红已消失**（31 passed 含这两个文件）。",
         "- `test_mwds_t27_service_envelope.py::…test_python_mirror_matches_the_real_ts_judge` 与 "
         "`test_mwds_t29_producer_signal.py::…test_python_judge_matches_the_real_ts_judge`：**仍红**。",
         "",
         "## 4. t27/t29 的真因（与 dist 无关，先前的归因被证伪）", "",
         "```",
         "File \"subprocess.py\", line 1613, in _readerthread",
         "    buffer.append(fh.read())",
         "UnicodeDecodeError: 'gbk' codec can't decode byte 0x87 in position 111: illegal multibyte sequence",
         "test_mwds_t27_service_envelope.py:475: TypeError: argument of type 'NoneType' is not a container or iterable",
         "```",
         "",
         "这两个测试用 `subprocess.run([...node...], capture_output=True, text=True)` 但**没有 "
         "`encoding=\"utf-8\"`**；子进程打印含中文的 parity 用例，stdout 被按本机 locale（GBK）解码，"
         "读取线程抛 `UnicodeDecodeError` ⇒ `proc.stdout` 变成 `None` ⇒ 后续 `in` 判定 TypeError。"
         "同一族：本机 locale 是 GBK 时才会红，属环境类基线红。", "",
         "**修复面**：给那两个 `subprocess.run` 各补 `encoding=\"utf-8\"`（一行，不碰任何断言）。"
         "文件属 `mw-dispatch-settle-gates`（DONE），改动前需与用户确认。", "",
         "## 5. 同族缺陷在生产代码里是否存在（text=True 缺 encoding）", "",
         "```"]

hits = []
for path in sorted(MW.rglob("*.py")):
    if any(part in ("node_modules", "dist") for part in path.parts):
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    for i, ln in enumerate(text.splitlines(), 1):
        if "text=True" in ln and "encoding=" not in ln:
            # look ahead a few lines for encoding= inside the same call
            window = "\n".join(text.splitlines()[i - 1:i + 8])
            if "encoding=" not in window:
                hits.append(f"{path.relative_to(REPO)}:{i}: {ln.strip()[:130]}")
lines += (hits or ["(none)"])
lines += ["```", "",
          "## 6. 结论", "",
          "本 key 的全部改动已进入运行时产物；**需要重启 pi 窗口**才会加载（含 worker 用的全局 bundle）。"
          "剩余 6 条基线红里，t27/t29 两条的真因已定性为测试侧 locale 解码（一行可修），"
          "readcap / verdict-freshness / launcher / task_type_parity 四条与本 key 无关（前两轮已 A/B 归因）。"]

dest = REPO / ".agenticdoc/_scratch/evidence/mdc-postbuild-status-20261014.md"
dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote", dest.name, len(lines), "lines; prod hits =", len(hits))
for h in hits[:12]:
    print(" ", h)
