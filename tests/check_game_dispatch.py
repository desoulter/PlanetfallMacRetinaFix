#!/usr/bin/env python3
"""Check which SDL resize event the actual inspected game dispatches."""
from pathlib import Path
import importlib.util
import struct
import sys

data = Path(sys.argv[1]).read_bytes()
table = 0xEC1B40
handled = table + struct.unpack_from("<i", data, table + (5 - 4) * 4)[0]
ignored = table + struct.unpack_from("<i", data, table + (6 - 4) * 4)[0]
assert handled == 0xEC1A66
assert ignored == 0xEC1AD6
assert data[handled:handled + 3] == bytes.fromhex("48 89 df")
assert data[handled + 3] == 0xE8
target = handled + 8 + struct.unpack_from("<i", data, handled + 4)[0]
assert target == 0xEC0C2F
assert data[ignored:ignored + 3] == bytes.fromhex("48 89 df")
print("PASS: actual game dispatch calls its resize handler for RESIZED (5), and skips SIZE_CHANGED (6)")

# Independently find every direct SDL_PollEvent call in the actual event-pump
# function, then require that the installer covers all of them.
calls = []
for offset in range(0xEC185E, 0xEC1B14 - 4):
    if data[offset] == 0xE8:
        target = offset + 5 + struct.unpack_from("<i", data, offset + 1)[0]
        if target == 0xF68368:
            calls.append(offset)
installer = Path(__file__).resolve().parent.parent / "retina_fix.py"
spec = importlib.util.spec_from_file_location("retina_fix_profile", installer)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert set(calls) == set(module.POLL_CALL_OFFSETS), (calls, module.POLL_CALL_OFFSETS)
assert len(calls) == 2
print("PASS: all actual SDL_PollEvent call sites are covered:", ", ".join(hex(x) for x in calls))
module.verify_present_state(data)
assert data[module.PRESENT_CALL_OFFSET:module.PRESENT_CALL_OFFSET + 5] == module.PRESENT_CALL_BEFORE
print("PASS: original presentation call and zero-filled writable pacing state padding")
