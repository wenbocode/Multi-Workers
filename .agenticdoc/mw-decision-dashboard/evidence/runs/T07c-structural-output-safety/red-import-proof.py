"""Prove which ``decision_history`` the RED run imported (baseline, unmodified)."""
import decision_history
import test_decision_history

print("test module      :", test_decision_history.__file__)
print("history module   :", decision_history.__file__)
print("has _scrub_output:", hasattr(decision_history, "_scrub_output"))
print(
    "has structural_withheld:",
    "structural_withheld" in decision_history.RedactionMarks.__dataclass_fields__,
)
print("has record.redactor:", "redactor" in decision_history.HistoryRecord.__dataclass_fields__)
