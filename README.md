# Planetfall macOS Retina Fix

**Version 1.0.0** · [Changelog](CHANGELOG.md) · [MIT license](LICENSE)

Fix blurry fullscreen rendering in the native macOS version of **Age of Wonders: Planetfall**. The patch enables Retina backing and makes the game render its scene and interface at the fullscreen drawable resolution. Mouse coordinates follow the interface dimensions, and the cursor retains its normal size.

The game continues to use its original Intel executable, SDL, and MoltenVK libraries. Apple Silicon Macs run it through Rosetta. Normal launches require no wrapper, injected library, or background process.

## Compatibility

- The Intel GOG macOS build with executable SHA-256 `2968fee158b24c83f44486f7c37f6abae9fea0a9aa98060a672b6800acd8f894`.
- macOS with Python **3.8 or later** and Apple's **Command Line Tools** (`clang`, `make`, and signing tools). No Python packages or downloaded dependencies are required.
- Rosetta on Apple Silicon, including for the assembly tests.
- Write access to the game application and its parent directory.

The installer checks the original executable fingerprint before applying changes. Other game builds, including Steam builds, have not been validated and are rejected if their fingerprint differs.

## Build from source

Install Command Line Tools if needed:

```sh
xcode-select --install
```

Download or clone this repository, open Terminal in its directory, then run:

```sh
make
make test
```

`make` assembles `pixel_events.S`, resolves its game references, and writes `pixel_events.bin`. The result must match the verified 418-byte payload and its SHA-256; a different result is rejected. Generated binaries are local build products and are excluded from the repository.

## Install

Quit Planetfall before installation, updating, or restoration. From this repository directory:

```sh
python3 retina_fix.py status
python3 retina_fix.py install
```

By default, the installer looks beside this directory, in the current directory, then in `/Applications/Age of Wonders Planetfall`. For a different installation:

```sh
python3 retina_fix.py install --app '/path/to/Age of Wonders - Planetfall.app'
```

After installation, launch the game normally and select fullscreen in its video settings. Fullscreen uses the desktop's drawable pixel resolution.

The original executable, `Info.plist`, and signature resource seal are saved in `PlanetfallMacRetinaFixBackup` beside the game application. **Keep this backup until the patch is uninstalled.** Failed installations restore the preceding files. Later unrelated modifications are protected from overwrite.

The modified application is signed locally with an ad-hoc signature. The inspected GOG package already contains invalid signatures in bundled libraries; the installer verifies the new main executable signature without recursively validating those unchanged vendor resources.

## Update or uninstall

After downloading an updated source release, rebuild and update:

```sh
make
python3 retina_fix.py update
```

The update command also accepts development prototypes and preserves their original backup. The verified development revision 5 already contains the same binary patch as v1.0.0, so it does not need reinstalling.

To restore the original files byte for byte:

```sh
python3 retina_fix.py uninstall
```

Add `--app '/path/to/Age of Wonders - Planetfall.app'` to any command when needed. If a custom `--backup` path was used during installation, use the same path for later commands. Use `python3 retina_fix.py --help` for available options and `python3 retina_fix.py --version` for the installer version.

## Scope and validation

Native fullscreen sharpness was validated at **3024×1890** on a Retina display. Runtime traces confirmed matching application render dimensions, interface dimensions, and main viewport. The event wrapper is covered by x86_64 execution tests, and installation, failed-install rollback, and byte-exact restoration were checked against the supported build.

This release has the following limits:

- The in-game resolution menu does not change fullscreen resolution. Fullscreen follows the desktop drawable size.
- Refresh-rate selection and an FPS limiter are not provided. Reported display mode frequency is not a measurement of instantaneous adaptive panel refresh.
- Windowed HiDPI rendering remains unresolved. The patch leaves windowed resize events unchanged.
- Extended gameplay, performance, and repeated display transitions have not been extensively validated. Rendering more pixels can increase GPU work.

See [technical notes](docs/technical-notes.md) for the rendering pipeline, binary locations, and build fingerprints.

## Optional diagnostics

These tools are provided as source and compile their own local executables. They are not needed for ordinary play.

```sh
./Run_Game_Diagnostics.command
./Run_Display_Probe.command
```

The game diagnostic launcher temporarily loads a tracing library for one process and logs render, UI, surface, viewport, and presentation dimensions. `--update` rebuilds and updates the patch first. It writes `game_display_trace.log` and `game_diagnostics_launch.log` beside the scripts and retains the preceding render trace as `game_display_trace.previous.log`.

The display probe creates hidden test windows using the bundled SDL and MoltenVK libraries. It writes `display_probe.log`; it does not measure game FPS. Both launchers locate the game beside this directory or in the default GOG location shown above.

## Developer checks

```sh
make test
make verify-game GAME_EXECUTABLE='/path/to/original/Age of Wonders - Planetfall'
make clean
```

`make test` builds and executes the assembly wrapper under x86_64, checks Python syntax, and checks both zsh launchers. `make verify-game` additionally checks resize-event dispatch and both SDL polling calls in an original, unpatched game executable. The executable can come from the local original backup; it is not part of this repository.

`make clean` removes generated binaries and the test build directory. Logs and original game backups are retained.

## License

The patch source is available under the [MIT license](LICENSE). No proprietary game executable, libraries, or assets are distributed. Age of Wonders: Planetfall and its game files remain the property of their respective owners.
