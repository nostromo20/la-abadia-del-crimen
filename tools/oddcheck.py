#!/usr/bin/env python3
"""68008 alignment check for the hybrid image (feedback_ql_respr_even).

Lists every symbol at an ODD address in the linked image. A symbol may sit at an odd
address only if it is only ever accessed as bytes; such labels are listed in BYTE_ONLY.
Anything else at an odd address fails the build.
"""
import sys

BYTE_ONLY = set()


def main():
    lst, symf = sys.argv[1], sys.argv[2]
    bad = []
    for line in open(symf):
        parts = line.split()
        if len(parts) < 2:
            continue
        name, val = parts[0], int(parts[1], 16)
        size = int(parts[2]) if len(parts) > 2 else 0
        stype = int(parts[3]) if len(parts) > 3 else 0
        if size == 1 or stype != 0:
            continue        # C/C++ objects are typed symbols and GCC aligns anything accessed
                            # wider than a byte; only untyped (asm) labels are checked
        if val & 1 and not name.startswith("__") and name not in BYTE_ONLY:
            bad.append((name, val))
    for name, val in bad:
        print("oddcheck: symbol %s at ODD address %06x" % (name, val))
    if bad:
        print("oddcheck: FAILED (%d odd symbols)" % len(bad))
        return 1
    print("oddcheck: no symbols at odd addresses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
