import pathlib

LOG = pathlib.Path(
    r"H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\evidence\implementation\dpc-t04-context-ts-generation\logs\gen-stdout-dryrun.log"
)
text = LOG.read_text(encoding="utf-8")
start = text.index("export const DECIDE_REGISTRY_PREPARATION")
end = text.index("export const DECIDE_REGISTRY:")
print(text[start:end])
print("=== dp-auto entry ===")
begin = text.index('\t"dp-auto": {')
print(text[begin : text.index("\n\t},", begin) + 4])
print("=== dp-route ===")
begin = text.index('\t"dp-route": {')
print(text[begin : text.index("\n\t},", begin) + 4])
print("=== dp-w-check-task head ===")
begin = text.index('\t"dp-w-check-task": {')
print(text[begin : begin + 700])
print("=== retired ===")
start = text.index("export const DECIDE_REGISTRY_RETIRED")
print(text[start : start + 1600])
print("=== tail ===")
print(repr(text[-160:]))
print("lines", text.count("\n"), "chars", len(text))
