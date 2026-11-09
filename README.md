# Planetfall macOS Retina Fix

**Version 1.1.0** · [Changelog](CHANGELOG.md) · [MIT license](LICENSE)

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

`make` assembles `pixel_events.S`, resolves its game references, and writes `pixel_events.bin`. The result must match the verified 3352-byte code/configuration template and its SHA-256; a different result is rejected. Generated binaries are local build products and are excluded from the repository.

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

After installation, launch the game normally and select fullscreen in its video settings. By default, fullscreen uses the desktop's drawable pixel resolution and the additional FPS limiter is disabled.

The original executable, `Info.plist`, and signature resource seal are saved in `PlanetfallMacRetinaFixBackup` beside the game application. **Keep this backup until the patch is uninstalled.** Failed installations restore the preceding files. Later unrelated modifications are protected from overwrite.

The modified application is signed locally with an ad-hoc signature. The inspected GOG package already contains invalid signatures in bundled libraries; the installer verifies the new main executable signature without recursively validating those unchanged vendor resources.

## Update or uninstall

After downloading an updated source release, rebuild and update:

```sh
make
python3 retina_fix.py update
```

The update command also accepts v1.0.0 and development prototypes, preserves the original backup, and retains existing render settings when no new options are supplied.

To restore the original files byte for byte:

```sh
python3 retina_fix.py uninstall
```

Add `--app '/path/to/Age of Wonders - Planetfall.app'` to any command when needed. If a custom `--backup` path was used during installation, use the same path for later commands. Use `python3 retina_fix.py --help` for available options and `python3 retina_fix.py --version` for the installer version.

## Render resolution and FPS cap

Quit the game, then configure either setting or both:

```sh
python3 retina_fix.py configure --resolution 2048x1280 --fps-cap 60
python3 retina_fix.py status
```

Settings are embedded in the installed patch and take effect on the next ordinary game launch. Changing one option preserves the other. `install` and `update` accept the same options; `configure` requires an existing recorded installation.

```sh
# Change only the frame-rate cap.
python3 retina_fix.py configure --fps-cap 100

# Restore maximum Retina sharpness, keeping the current FPS cap.
python3 retina_fix.py configure --resolution desktop

# Disable the additional FPS limiter.
python3 retina_fix.py configure --fps-cap 0
```

`--resolution WIDTHxHEIGHT` sets the **internal fullscreen scene/UI frame**, from 640×480 through 8192×8192. The game composites that frame into its desktop-sized output surface; this does not switch the monitor's physical mode. Prefer the desktop aspect ratio to avoid stretching. A lower internal resolution can reduce scene rendering work, but scaling also reduces text sharpness. `desktop` (or `auto`) restores native drawable dimensions.

`--fps-cap` accepts an integer from 1 to 1000, or 0 to disable the cap. The limiter sleeps against monotonic frame deadlines before Vulkan presentation. It absorbs ordinary timer wake-up jitter and resets after missed deadlines. It does not change monitor refresh rate, disable the game's VSync, or guarantee a target that the game/GPU cannot sustain. The cap also applies in menus.

## Scope and validation

Native fullscreen sharpness was validated at **3024×1890** on a Retina display. Runtime traces confirmed matching application render dimensions, interface dimensions, and main viewport. The event wrapper is covered by x86_64 execution tests, and installation, failed-install rollback, and byte-exact restoration were checked against the supported build.

Runtime checks in the main menu also confirmed a 2048×1280 scene/UI frame with correctly aligned mouse input. After loading settled, presentation traces averaged **59.98/s** with a 60 FPS cap at 2048×1280, and **99.96/s** with a 100 FPS cap at native 3024×1890. These are presentation submission rates, not panel refresh measurements or gameplay benchmarks.

This release has the following limits:

- The in-game resolution menu does not control the configured render size; use the script and restart the game.
- Monitor refresh-rate selection is not provided. Reported display mode frequency is not a measurement of instantaneous adaptive panel refresh.
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
make verify-installation ORIGINAL_FILES='/path/to/PlanetfallMacRetinaFixBackup'
make clean
```

`make test` builds and executes the event and presentation wrappers under x86_64, checks Python syntax, and checks both zsh launchers. Tests include custom render sizes, mouse mapping, presentation arguments/results, wake-up jitter, interruptions, and missed deadlines. `make verify-game` additionally checks resize-event dispatch, both SDL polling calls, the presentation call, and unused writable state padding in the original executable. `make verify-installation` checks signed installation, independent setting changes, idempotence, rollback, changed-file protection, and restoration on a disposable copy of the original backup. Game files are not part of this repository.

`make clean` removes generated binaries and the test build directory. Logs and original game backups are retained.

## License

The patch source is available under the [MIT license](LICENSE). No proprietary game executable, libraries, or assets are distributed. Age of Wonders: Planetfall and its game files remain the property of their respective owners.
