from ordered_rows import ordered_rows

rows = ("z", "a", "m")
assert len(ordered_rows(rows)) == len(rows)
assert ordered_rows(rows) == rows
