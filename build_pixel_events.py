#!/usr/bin/env python3
"""Assemble the wrapper and resolve its known rel32 game references."""
from pathlib import Path
import argparse
import hashlib
import struct
import subprocess
import tempfile

from retina_fix import PIXEL_CODE_SHA256, PIXEL_CODE_SIZE

BASE = 0x100007000
SYMBOLS = {
    "_pf_sdl_poll_event": 0x100F68368,
    "_pf_sdl_window_size": 0x100F68344,
    "_pf_sdl_drawable_size": 0x100F682F6,
    "_pf_window": 0x1015AED70,
    "_pf_fullscreen": 0x1015AED9C,
    "_pf_application": 0x1015AED28,
}


def assemble():
    source = Path(__file__).with_name("pixel_events.S")
    with tempfile.TemporaryDirectory(prefix="pf-assemble-") as temp:
        obj = Path(temp) / "pixel_events.o"
        subprocess.run(["clang", "-arch", "x86_64", "-c", str(source), "-o", str(obj)], check=True)
        data = obj.read_bytes()
    count = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    section = symtab = None
    for _ in range(count):
        cmd, size = struct.unpack_from("<II", data, offset)
        if cmd == 0x19:
            n = struct.unpack_from("<I", data, offset + 64)[0]
            for i in range(n):
                p = offset + 72 + 80 * i
                if data[p:p + 16].split(b"\0")[0] == b"__text":
                    address, length, start = struct.unpack_from("<QQI", data, p + 32)
                    reloc, nreloc = struct.unpack_from("<II", data, p + 56)
                    section = address, length, start, reloc, nreloc
        if cmd == 2:
            symtab = struct.unpack_from("<IIII", data, offset + 8)
        offset += size
    if section is None or symtab is None:
        raise RuntimeError("Assembler object has no text or symbols")
    symoff, nsyms, stroff, strsize = symtab
    strings = data[stroff:stroff + strsize]
    names = []
    for i in range(nsyms):
        index = struct.unpack_from("<I", data, symoff + 16 * i)[0]
        names.append(strings[index:].split(b"\0")[0].decode())
    address, length, start, reloc, nreloc = section
    if address != 0:
        raise RuntimeError("Unexpected nonzero text address")
    code = bytearray(data[start:start + length])
    for i in range(nreloc):
        where, info = struct.unpack_from("<II", data, reloc + 8 * i)
        symbol, pcrel, width, external, kind = info & 0xFFFFFF, (info >> 24) & 1, (info >> 25) & 3, (info >> 27) & 1, info >> 28
        if (pcrel, width, external) != (1, 2, 1) or kind not in (1, 2):
            raise RuntimeError(f"Unsupported relocation {info:#x}")
        addend = struct.unpack_from("<i", code, where)[0]
        target = SYMBOLS[names[symbol]]
        struct.pack_into("<i", code, where, target + addend - (BASE + where + 4))
    return bytes(code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the assembled wrapper to this binary file")
    args = parser.parse_args()
    code = assemble()
    if len(code) != PIXEL_CODE_SIZE or hashlib.sha256(code).hexdigest() != PIXEL_CODE_SHA256:
        raise RuntimeError("Assembled wrapper differs from the verified release payload")
    print(f"Wrapper bytes: {len(code)}; destination: {BASE:#x}")
    if args.output:
        args.output.write_bytes(code)
    else:
        print(code.hex())
