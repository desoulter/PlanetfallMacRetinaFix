#!/usr/bin/env python3
"""Exercise installation/configuration/rollback on a disposable copy of original files."""
from contextlib import redirect_stdout
import argparse
import importlib.util
import io
from pathlib import Path
import shutil
import struct
import tempfile
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('original_files', type=Path, help='Original backup directory containing Contents/')
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('retina_fix', Path(__file__).resolve().parent.parent / 'retina_fix.py')
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)
assert fix.digest(args.original_files / fix.EXE) == fix.ORIGINAL_SHA256

def hashes(app):
    return {name: fix.digest(app / name) for name in fix.FILES}

def assert_config(app, size, fps):
    data = (app / fix.EXE).read_bytes()
    assert data[fix.CONFIG_OFFSET:fix.CONFIG_OFFSET + 8] == fix.CONFIG_MAGIC
    width, height, interval = struct.unpack_from('<IIQ', data, fix.CONFIG_OFFSET + 8)
    assert (width, height) == tuple(size or (0, 0))
    assert interval == ((1000000000 + fps - 1) // fps if fps else 0)
    assert data[fix.PRESENT_CALL_OFFSET:fix.PRESENT_CALL_OFFSET + 5] == fix.PRESENT_CALL_AFTER

with tempfile.TemporaryDirectory(prefix='pf-installation-test-') as temp:
    app = Path(temp) / fix.APP_NAME
    backup = Path(temp) / 'backup'
    for name in fix.FILES:
        target = app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.original_files / name, target)
    original = hashes(app)
    # The fixture is newly created and cannot be a running application.
    with patch.object(fix, 'ensure_not_running', lambda target: None), redirect_stdout(io.StringIO()):
        fix.install(app, backup, resolution=[2048, 1280], fps_cap=60, set_resolution=True)
        assert_config(app, [2048, 1280], 60)
        # An identical development payload needs only a release metadata update.
        development = fix.read_manifest(backup, app)
        development['patch_version'] = '1.1.0-dev'
        fix.write_manifest(backup, development)
        development_files = hashes(app)
        fix.install(app, backup, allow_update=True)
        assert fix.read_manifest(backup, app)['patch_version'] == fix.VERSION
        assert hashes(app) == development_files
        assert_config(app, [2048, 1280], 60)
        fix.install(app, backup, allow_update=True, fps_cap=100, configure_only=True)
        assert_config(app, [2048, 1280], 100)
        previous, old_manifest = hashes(app), (backup / 'manifest.json').read_bytes()
        # Updating without options preserves settings and is byte-idempotent.
        fix.install(app, backup, allow_update=True)
        assert hashes(app) == previous and (backup / 'manifest.json').read_bytes() == old_manifest
        with patch.object(fix, 'run', side_effect=RuntimeError('simulated signing failure')):
            try:
                fix.install(app, backup, allow_update=True, fps_cap=30, configure_only=True)
            except RuntimeError as error:
                assert 'simulated signing failure' in str(error)
            else:
                raise AssertionError('Failed signing was accepted')
        assert hashes(app) == previous and (backup / 'manifest.json').read_bytes() == old_manifest
        fix.install(app, backup, allow_update=True, resolution=None, set_resolution=True, fps_cap=0, configure_only=True)
        assert_config(app, None, 0)
        # Later game changes are never overwritten by configure.
        (app / fix.PLIST).write_bytes((app / fix.PLIST).read_bytes() + b'\n')
        modified = hashes(app)
        try:
            fix.install(app, backup, allow_update=True, fps_cap=30, configure_only=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Unrelated changes were overwritten')
        assert hashes(app) == modified
        fix.atomic_bytes((app / fix.PLIST).read_bytes()[:-1], app / fix.PLIST)
        fix.uninstall(app, backup)
        assert hashes(app) == original
        try:
            fix.install(app, backup, allow_update=True, fps_cap=60, configure_only=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError('configure reinstalled an uninstalled patch')
        assert hashes(app) == original
print('PASS: signed install, development-to-release upgrade, independent settings, persistent/idempotent update, failed-sign rollback, reset, changed-file protection, byte-exact uninstall')
