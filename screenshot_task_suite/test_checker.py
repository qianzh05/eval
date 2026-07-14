#!/usr/bin/env python3
"""Gate for checker.py: every _meta.test_vectors entry in tasks/pilot_tasks.json
must produce its expected verdict. Run: python3 test_checker.py
Exit code 0 = all green (scoring may proceed); 1 = checker not usable."""

import json
import os
import sys

from checker import check

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    data = json.load(open(os.path.join(HERE, "tasks", "pilot_tasks.json")))
    vectors = data["_meta"]["test_vectors"]
    failures = []
    for i, v in enumerate(vectors):
        expected = v["expect"].split()[0].split("(")[0].strip().upper()
        got = check(v["task"], v["answer"], v.get("urls"))
        status = "ok" if got["verdict"] == expected else "MISMATCH"
        if status == "MISMATCH":
            failures.append((i, v, got))
        print(f"[{status}] #{i:02d} {v['task']}: expect {expected}, got {got['verdict']}"
              f" (final_assertion={got.get('final_assertion')})")
    print(f"\n{len(vectors) - len(failures)}/{len(vectors)} vectors pass")
    if failures:
        print("\nFAILING VECTORS:")
        for i, v, got in failures:
            print(f"  #{i:02d} {v['task']} | answer: {v['answer'][:100]!r}")
            print(f"       expected {v['expect'][:80]!r} got {got}")
        sys.exit(1)


if __name__ == "__main__":
    main()
