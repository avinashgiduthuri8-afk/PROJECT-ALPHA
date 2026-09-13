import json

with open("classified_summary.json", "r", encoding="utf-8") as f:
    data = json.load(f)

active = data["ACTIVE"]

non_test_active = [a for a in active if not a["file"].replace("\\", "/").startswith("./tests/")]

print(f"Non-test ACTIVE references count: {len(non_test_active)}")
for a in non_test_active:
    print(f"[{a['file']}:{a['line_num']}] {a['line']}")

