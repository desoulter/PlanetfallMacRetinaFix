#!/usr/bin/env python3
"""Reversible Retina fullscreen patch for Age of Wonders: Planetfall on macOS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile

APP_NAME = "Age of Wonders - Planetfall.app"
VERSION = "1.0.0"
EXE = "Contents/MacOS/Age of Wonders - Planetfall"
PLIST = "Contents/Info.plist"
SEAL = "Contents/_CodeSignature/CodeResources"
ORIGINAL_SHA256 = "2968fee158b24c83f44486f7c37f6abae9fea0a9aa98060a672b6800acd8f894"
PATCH_OFFSET = 0xEC1324
BEFORE = bytes.fromhex("41 b9 20 00 00 10")
AFTER = bytes.fromhex("41 b9 20 20 00 10")
# Keep the binary patch revision compatible with installed development builds.
REVISION = 5
CURSOR_OFFSET = 0xEC175B
CURSOR_BEFORE = bytes.fromhex("48 0f 4f c1")
CURSOR_AFTER = bytes.fromhex("90 90 90 90")
PIXEL_CODE_OFFSET = 0x7000
PIXEL_CODE_SIZE = 418
PIXEL_CODE_SHA256 = "73362c4967d14ddbcc7b11c58b113a4d262a46f28653d605c0968f925f8e405c"
POLL_CALL_OFFSETS = (0xEC18E4, 0xEC1AD9)
POLL_PATCHES = tuple(
    (offset,
     b"\xe8" + struct.pack("<i", 0xF68368 - (offset + 5)),
     b"\xe8" + struct.pack("<i", PIXEL_CODE_OFFSET - (offset + 5)))
    for offset in POLL_CALL_OFFSETS
)
FILES = (EXE, PLIST, SEAL)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_code():
    code = Path(__file__).with_name("pixel_events.bin").read_bytes()
    if len(code) != PIXEL_CODE_SIZE or hashlib.sha256(code).hexdigest() != PIXEL_CODE_SHA256:
        raise RuntimeError("Pixel event wrapper has an unexpected checksum. Run make to rebuild it.")
    return code


def run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def ensure_not_running(app):
    result = subprocess.run(["/bin/ps", "-axo", "command="], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Cannot inspect running processes. Run this script in macOS Terminal after quitting the game.")
    executable = str(app / EXE)
    for line in result.stdout.splitlines():
        if line.strip().startswith(executable):
            raise RuntimeError("Quit Planetfall before installing or restoring the patch.")


def atomic_copy(source, target):
    fd, name = tempfile.mkstemp(prefix=".retina-", dir=target.parent)
    os.close(fd)
    try:
        shutil.copy2(source, name)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def atomic_bytes(data, target):
    fd, name = tempfile.mkstemp(prefix=".retina-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(target, name)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def read_manifest(backup, app):
    manifest = json.loads((backup / "manifest.json").read_text())
    if manifest["app"] != str(app):
        raise RuntimeError("This backup belongs to a different app path.")
    for relative in FILES:
        if digest(backup / relative) != manifest["original"][relative]:
            raise RuntimeError(f"Backup is damaged: {relative}")
    if manifest["original"][EXE] != ORIGINAL_SHA256:
        raise RuntimeError("Backup executable is not the supported original build.")
    return manifest


def write_manifest(backup, manifest):
    target = backup / "manifest.json"
    data = json.dumps(manifest, indent=2).encode() + b"\n"
    if target.exists():
        atomic_bytes(data, target)
    else:
        target.write_bytes(data)


def restore_files(app, backup):
    for relative in FILES:
        atomic_copy(backup / relative, app / relative)


def inspect(app, backup):
    if not (app / EXE).is_file():
        raise RuntimeError(f"Game executable not found in {app}")
    sha = digest(app / EXE)
    code = (app / EXE).read_bytes()[PATCH_OFFSET:PATCH_OFFSET + len(BEFORE)]
    info = plistlib.loads((app / PLIST).read_bytes())
    print(f"App: {app}\nExecutable SHA-256: {sha}")
    print(f"Window flags instruction: {code.hex(' ')}")
    cursor_code = (app / EXE).read_bytes()[CURSOR_OFFSET:CURSOR_OFFSET + len(CURSOR_BEFORE)]
    print(f"Cursor policy: {'normal 32px assets' if cursor_code == CURSOR_AFTER else 'original automatic 32/96px selection'}")
    binary = (app / EXE).read_bytes()
    covered = sum(binary[offset:offset + 5] == after for offset, before, after in POLL_PATCHES)
    print(f"Render/input conversion call sites: {covered}/{len(POLL_PATCHES)}")
    print(f"NSHighResolutionCapable: {info.get('NSHighResolutionCapable', 'absent')}")
    if (backup / "manifest.json").exists():
        m = read_manifest(backup, app)
        expected = m.get("installed")
        if expected and all(digest(app / r) == expected[r] for r in FILES):
            revision = m.get("patch_revision", 1)
            release = m.get("patch_version") or (VERSION if revision == REVISION else None)
            label = f"v{release}" if release else f"revision {revision}"
            print(f"Status: Retina patch {label} installed")
        elif all(digest(app / r) == m["original"][r] for r in FILES):
            print("Status: original files; backup available")
        else:
            print("Status: files differ from backup and recorded installation")
    elif sha == ORIGINAL_SHA256 and code == BEFORE:
        print("Status: supported original build; ready to install")
    else:
        print("Status: unsupported or modified build; installation will be refused")


def install(app, backup, allow_update=False):
    ensure_not_running(app)
    if (backup / "manifest.json").exists():
        manifest = read_manifest(backup, app)
        expected = manifest.get("installed")
        if expected and all(digest(app / r) == expected[r] for r in FILES):
            if manifest.get("patch_revision", 1) == REVISION:
                print(f"Retina patch v{VERSION} is already installed.")
                return
            if not allow_update:
                raise RuntimeError("An older patch is installed. Run retina_fix.py update to upgrade it.")
        elif not all(digest(app / r) == manifest["original"][r] for r in FILES):
            raise RuntimeError("Game files changed since backup. Refusing to overwrite them.")
    else:
        executable = app / EXE
        if digest(executable) != ORIGINAL_SHA256:
            raise RuntimeError("Unsupported executable SHA-256. No files changed.")
        if backup.exists():
            raise RuntimeError(f"Incomplete backup at {backup}. Keep it and choose a new --backup path.")
        for relative in FILES:
            if not (app / relative).is_file():
                raise RuntimeError(f"Required file missing: {relative}")
        backup.mkdir(parents=True)
        for relative in FILES:
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(app / relative, target)
        manifest = {"app": str(app), "original": {r: digest(backup / r) for r in FILES}}
        write_manifest(backup, manifest)
    binary = bytearray((backup / EXE).read_bytes())
    if binary[PATCH_OFFSET:PATCH_OFFSET + len(BEFORE)] != BEFORE:
        raise RuntimeError("Patch instruction does not match. No game files changed.")
    if binary[CURSOR_OFFSET:CURSOR_OFFSET + len(CURSOR_BEFORE)] != CURSOR_BEFORE:
        raise RuntimeError("Cursor instruction does not match. No game files changed.")
    wrapper = pixel_code()
    for offset, before, after in POLL_PATCHES:
        if binary[offset:offset + 5] != before:
            raise RuntimeError(f"SDL event call at {offset:#x} does not match. No game files changed.")
    if binary[PIXEL_CODE_OFFSET:PIXEL_CODE_OFFSET + PIXEL_CODE_SIZE] != bytes(PIXEL_CODE_SIZE):
        raise RuntimeError("Reserved executable padding is occupied. No game files changed.")
    # Keep the immediately preceding installation recoverable if an upgrade fails.
    transaction = Path(tempfile.mkdtemp(prefix=".retina-transaction-", dir=backup.parent))
    for relative in FILES:
        target = transaction / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(app / relative, target)
    try:
        binary[PATCH_OFFSET:PATCH_OFFSET + len(AFTER)] = AFTER
        binary[CURSOR_OFFSET:CURSOR_OFFSET + len(CURSOR_AFTER)] = CURSOR_AFTER
        binary[PIXEL_CODE_OFFSET:PIXEL_CODE_OFFSET + PIXEL_CODE_SIZE] = wrapper
        for offset, before, after in POLL_PATCHES:
            binary[offset:offset + 5] = after
        atomic_bytes(binary, app / EXE)
        original_plist = (app / PLIST).read_bytes()
        info = plistlib.loads(original_plist)
        info["NSHighResolutionCapable"] = True
        fmt = plistlib.FMT_BINARY if original_plist.startswith(b"bplist") else plistlib.FMT_XML
        atomic_bytes(plistlib.dumps(info, fmt=fmt, sort_keys=False), app / PLIST)
        # Ad-hoc signing is required after changing signed machine code.
        # Do not preserve hardened-runtime library validation on a local signature.
        run(["/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none", str(app)])
        # The inspected GOG package already has invalid signatures in bundled
        # dylibs (including libGalaxy's unused i386 slice). Verify the new main
        # code signature without recursively rejecting those unchanged files.
        run(["/usr/bin/codesign", "--verify", "--strict", "--ignore-resources", str(app)])
        if (app / EXE).read_bytes()[PATCH_OFFSET:PATCH_OFFSET + len(AFTER)] != AFTER:
            raise RuntimeError("Patched instruction failed verification.")
        if (app / EXE).read_bytes()[CURSOR_OFFSET:CURSOR_OFFSET + len(CURSOR_AFTER)] != CURSOR_AFTER:
            raise RuntimeError("Cursor instruction failed verification.")
        installed = (app / EXE).read_bytes()
        if installed[PIXEL_CODE_OFFSET:PIXEL_CODE_OFFSET + PIXEL_CODE_SIZE] != wrapper or any(installed[offset:offset + 5] != after for offset, before, after in POLL_PATCHES):
            raise RuntimeError("Pixel conversion code failed verification.")
        manifest["installed"] = {r: digest(app / r) for r in FILES}
        manifest["patch_revision"] = REVISION
        manifest["patch_version"] = VERSION
        write_manifest(backup, manifest)
    except BaseException:
        restore_files(app, transaction)
        print("Installation did not finish; previous files restored.", file=sys.stderr)
        raise
    finally:
        shutil.rmtree(transaction)
    print(f"Retina patch v{VERSION} installed. Backup: {backup}")
    print("Launch the game normally. Fullscreen uses the desktop drawable resolution.")


def uninstall(app, backup):
    ensure_not_running(app)
    manifest = read_manifest(backup, app)
    if all(digest(app / r) == manifest["original"][r] for r in FILES):
        print("Original files are already restored.")
        return
    expected = manifest.get("installed")
    if not expected or not all(digest(app / r) == expected[r] for r in FILES):
        raise RuntimeError("Game files changed after installation. Refusing to overwrite them; original backup is retained.")
    restore_files(app, backup)
    for relative in FILES:
        if digest(app / relative) != manifest["original"][relative]:
            raise RuntimeError(f"Restore verification failed: {relative}")
    print("Original executable, Info.plist, and signature resource seal restored byte for byte.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("command", choices=("status", "install", "update", "uninstall"))
    parser.add_argument("--app", type=Path, help="Path to the game .app")
    parser.add_argument("--backup", type=Path, help="Backup directory (keep it until uninstalling)")
    args = parser.parse_args()
    app = args.app
    if app is None:
        candidates = [Path(__file__).resolve().parent.parent / APP_NAME,
                      Path.cwd() / APP_NAME, Path("/Applications/Age of Wonders Planetfall") / APP_NAME]
        app = next((p for p in candidates if (p / EXE).is_file()), candidates[0])
    app = app.expanduser().resolve()
    backup = (args.backup or app.parent / "PlanetfallMacRetinaFixBackup").expanduser().resolve()
    try:
        if args.command == "update":
            install(app, backup, allow_update=True)
        else:
            {"status": inspect, "install": install, "uninstall": uninstall}[args.command](app, backup)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
