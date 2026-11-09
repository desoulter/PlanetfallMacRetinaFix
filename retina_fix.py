#!/usr/bin/env python3
"""Reversible Retina fullscreen patch for Age of Wonders: Planetfall on macOS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile

APP_NAME = "Age of Wonders - Planetfall.app"
VERSION = "1.1.0"
EXE = "Contents/MacOS/Age of Wonders - Planetfall"
PLIST = "Contents/Info.plist"
SEAL = "Contents/_CodeSignature/CodeResources"
ORIGINAL_SHA256 = "2968fee158b24c83f44486f7c37f6abae9fea0a9aa98060a672b6800acd8f894"
PATCH_OFFSET = 0xEC1324
BEFORE = bytes.fromhex("41 b9 20 00 00 10")
AFTER = bytes.fromhex("41 b9 20 20 00 10")
# Keep the binary patch revision compatible with installed development builds.
REVISION = 6
CURSOR_OFFSET = 0xEC175B
CURSOR_BEFORE = bytes.fromhex("48 0f 4f c1")
CURSOR_AFTER = bytes.fromhex("90 90 90 90")
PIXEL_CODE_OFFSET = 0x7000
CONFIG_OFFSET = 0x7D00
CONFIG_MAGIC = b"PFCONF11"
PIXEL_CODE_SIZE = CONFIG_OFFSET - PIXEL_CODE_OFFSET + 24
PIXEL_CODE_SHA256 = "ba505e076f88073f76ab6bf5ca6b8d55162c59c0d893603173a2ebedb9a34ca4"
PRESENT_CALL_OFFSET = 0x437435
PRESENT_CODE_OFFSET = 0x7400
PRESENT_STATE_ADDRESS = 0x1015AF400
PRESENT_CALL_BEFORE = b"\xe8" + struct.pack("<i", 0xF690DC - (PRESENT_CALL_OFFSET + 5))
PRESENT_CALL_AFTER = b"\xe8" + struct.pack("<i", PRESENT_CODE_OFFSET - (PRESENT_CALL_OFFSET + 5))
POLL_CALL_OFFSETS = (0xEC18E4, 0xEC1AD9)
POLL_PATCHES = tuple(
    (offset,
     b"\xe8" + struct.pack("<i", 0xF68368 - (offset + 5)),
     b"\xe8" + struct.pack("<i", PIXEL_CODE_OFFSET - (offset + 5)))
    for offset in POLL_CALL_OFFSETS
)
FILES = (EXE, PLIST, SEAL)


def resolution_arg(value):
    if value.lower() in ("desktop", "auto"):
        return None
    match = re.fullmatch(r"(\d+)[xX](\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError("Use desktop or WIDTHxHEIGHT, for example 2048x1280.")
    width, height = map(int, match.groups())
    if not (640 <= width <= 8192 and 480 <= height <= 8192):
        raise argparse.ArgumentTypeError("Resolution must be between 640x480 and 8192x8192.")
    return [width, height]


def fps_arg(value):
    try:
        fps = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("FPS cap must be an integer from 0 to 1000.") from error
    if not 0 <= fps <= 1000:
        raise argparse.ArgumentTypeError("Use 0 to disable the cap, or 1 to 1000 FPS.")
    return fps


def settings_for(manifest, resolution=None, fps_cap=None, set_resolution=False):
    settings = dict(manifest.get("settings", {"resolution": None, "fps_cap": 0}))
    if set_resolution:
        settings["resolution"] = resolution
    if fps_cap is not None:
        settings["fps_cap"] = fps_cap
    # Validate saved values too; never inject corrupt or excessive intervals.
    size = settings["resolution"]
    if size is not None:
        if not isinstance(size, list) or len(size) != 2 or any(type(x) is not int for x in size):
            raise RuntimeError("Invalid saved render resolution.")
        try:
            resolution_arg(f"{size[0]}x{size[1]}")
        except argparse.ArgumentTypeError as error:
            raise RuntimeError("Invalid saved render resolution.") from error
    fps = settings["fps_cap"]
    if type(fps) is not int or not 0 <= fps <= 1000:
        raise RuntimeError("Invalid saved FPS cap.")
    return settings


def configured_code(settings):
    code = bytearray(pixel_code())
    width, height = settings["resolution"] or (0, 0)
    fps = settings["fps_cap"]
    interval = (1000000000 + fps - 1) // fps if fps else 0
    struct.pack_into("<IIQ", code, CONFIG_OFFSET - PIXEL_CODE_OFFSET + 8, width, height, interval)
    return bytes(code)


def verify_present_state(binary):
    """Require zero-filled RW segment padding outside every declared section."""
    offset = 32
    for _ in range(struct.unpack_from("<I", binary, 16)[0]):
        command, size = struct.unpack_from("<II", binary, offset)
        if command == 0x19 and binary[offset + 8:offset + 24].rstrip(b"\0") == b"__DATA":
            address, length, file_offset, file_size = struct.unpack_from("<QQQQ", binary, offset + 24)
            protection, sections = struct.unpack_from("<II", binary, offset + 60)
            end = PRESENT_STATE_ADDRESS + 8
            if protection & 2 == 0 or not address + file_size <= PRESENT_STATE_ADDRESS < end <= address + length:
                raise RuntimeError("Frame pacing state is not in zero-filled writable padding.")
            for index in range(sections):
                section = offset + 72 + index * 80
                start, size = struct.unpack_from("<QQ", binary, section + 32)
                if PRESENT_STATE_ADDRESS < start + size and end > start:
                    raise RuntimeError("Frame pacing state overlaps a game section.")
            return
        offset += size
    raise RuntimeError("Writable game data segment not found.")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_code():
    path = Path(__file__).with_name("pixel_events.bin")
    if not path.is_file():
        raise RuntimeError("Pixel event wrapper is missing. Run make before installing.")
    code = path.read_bytes()
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
            release = m.get("patch_version") or ({5: "1.0.0"}.get(revision)) or (VERSION if revision == REVISION else None)
            label = f"v{release}" if release else f"revision {revision}"
            print(f"Status: Retina patch {label} installed")
            settings = settings_for(m)
            resolution = settings["resolution"]
            print("Fullscreen render resolution: " + (f"{resolution[0]}x{resolution[1]}" if resolution else "desktop drawable"))
            print("FPS cap: " + (str(settings["fps_cap"]) if settings["fps_cap"] else "disabled"))
            paced = binary[PRESENT_CALL_OFFSET:PRESENT_CALL_OFFSET + 5] == PRESENT_CALL_AFTER
            print(f"Frame pacing hook: {'installed' if paced else 'absent'}")
        elif all(digest(app / r) == m["original"][r] for r in FILES):
            print("Status: original files; backup available")
        else:
            print("Status: files differ from backup and recorded installation")
    elif sha == ORIGINAL_SHA256 and code == BEFORE:
        print("Status: supported original build; ready to install")
    else:
        print("Status: unsupported or modified build; installation will be refused")


def install(app, backup, allow_update=False, resolution=None, fps_cap=None, set_resolution=False, configure_only=False):
    ensure_not_running(app)
    if configure_only and not (backup / "manifest.json").exists():
        raise RuntimeError("Install the patch before using configure.")
    if (backup / "manifest.json").exists():
        manifest = read_manifest(backup, app)
        settings = settings_for(manifest, resolution, fps_cap, set_resolution)
        expected = manifest.get("installed")
        if expected and all(digest(app / r) == expected[r] for r in FILES):
            if (manifest.get("patch_revision", 1) == REVISION
                    and manifest.get("patch_payload_sha256") == PIXEL_CODE_SHA256
                    and settings == settings_for(manifest)):
                if manifest.get("patch_version") != VERSION:
                    manifest["patch_version"] = VERSION
                    write_manifest(backup, manifest)
                    print(f"Recorded release v{VERSION}; installed game files and settings are unchanged.")
                    return
                print(f"Retina patch v{VERSION} is already installed.")
                return
            if not allow_update:
                raise RuntimeError("Run retina_fix.py update or configure to change an existing installation.")
        elif configure_only:
            raise RuntimeError("A recorded patch installation is required before using configure.")
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
        settings = settings_for(manifest, resolution, fps_cap, set_resolution)
        write_manifest(backup, manifest)
    binary = bytearray((backup / EXE).read_bytes())
    if binary[PATCH_OFFSET:PATCH_OFFSET + len(BEFORE)] != BEFORE:
        raise RuntimeError("Patch instruction does not match. No game files changed.")
    if binary[CURSOR_OFFSET:CURSOR_OFFSET + len(CURSOR_BEFORE)] != CURSOR_BEFORE:
        raise RuntimeError("Cursor instruction does not match. No game files changed.")
    wrapper = configured_code(settings)
    verify_present_state(binary)
    if binary[PRESENT_CALL_OFFSET:PRESENT_CALL_OFFSET + 5] != PRESENT_CALL_BEFORE:
        raise RuntimeError("Presentation call does not match. No game files changed.")
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
        binary[PRESENT_CALL_OFFSET:PRESENT_CALL_OFFSET + 5] = PRESENT_CALL_AFTER
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
        if installed[PRESENT_CALL_OFFSET:PRESENT_CALL_OFFSET + 5] != PRESENT_CALL_AFTER:
            raise RuntimeError("Frame pacing call failed verification.")
        manifest["installed"] = {r: digest(app / r) for r in FILES}
        manifest["patch_revision"] = REVISION
        manifest["patch_version"] = VERSION
        manifest["patch_payload_sha256"] = PIXEL_CODE_SHA256
        manifest["settings"] = settings
        write_manifest(backup, manifest)
    except BaseException:
        restore_files(app, transaction)
        print("Installation did not finish; previous files restored.", file=sys.stderr)
        raise
    finally:
        shutil.rmtree(transaction)
    print(f"Retina patch v{VERSION} installed. Backup: {backup}")
    size = settings["resolution"]
    print("Fullscreen render resolution: " + (f"{size[0]}x{size[1]}" if size else "desktop drawable"))
    print("FPS cap: " + (str(settings["fps_cap"]) if settings["fps_cap"] else "disabled"))
    print("Launch the game normally. Settings apply on its next launch.")


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
    parser.add_argument("command", choices=("status", "install", "update", "configure", "uninstall"))
    parser.add_argument("--resolution", type=resolution_arg, default=argparse.SUPPRESS,
                        help="Fullscreen render size, e.g. 2048x1280; desktop restores native Retina size")
    parser.add_argument("--fps-cap", type=fps_arg, default=None,
                        help="Maximum presentation rate, 1 to 1000; 0 disables the limiter")
    parser.add_argument("--app", type=Path, help="Path to the game .app")
    parser.add_argument("--backup", type=Path, help="Backup directory (keep it until uninstalling)")
    args = parser.parse_args()
    has_resolution = hasattr(args, "resolution")
    has_settings = has_resolution or args.fps_cap is not None
    if has_settings and args.command not in ("install", "update", "configure"):
        parser.error("Render settings are accepted only by install, update, and configure.")
    if args.command == "configure" and not has_settings:
        parser.error("configure requires --resolution and/or --fps-cap.")
    app = args.app
    if app is None:
        candidates = [Path(__file__).resolve().parent.parent / APP_NAME,
                      Path.cwd() / APP_NAME, Path("/Applications/Age of Wonders Planetfall") / APP_NAME]
        app = next((p for p in candidates if (p / EXE).is_file()), candidates[0])
    app = app.expanduser().resolve()
    backup = (args.backup or app.parent / "PlanetfallMacRetinaFixBackup").expanduser().resolve()
    try:
        if args.command in ("install", "update", "configure"):
            install(app, backup, allow_update=args.command != "install",
                    resolution=getattr(args, "resolution", None), fps_cap=args.fps_cap,
                    set_resolution=has_resolution, configure_only=args.command == "configure")
        else:
            {"status": inspect, "uninstall": uninstall}[args.command](app, backup)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
