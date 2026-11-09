# Changelog

## 1.1.0 — 2026-11-09

- Add persistent fullscreen render resolution and FPS cap options to `install`, `update`, and the new `configure` command.
- Preserve unspecified settings and show the active configuration in `status`.
- Pace Vulkan presentation with monotonic deadlines and sleeping, accounting for wake-up jitter and missed frames.
- Add configuration, frame pacing, and signed installer rollback checks.

Resolution settings control the internal scene/UI frame. The desktop output mode and monitor refresh rate remain unchanged.

## 1.0.0 — 2026-11-09

First release for the supported Intel GOG macOS build of Age of Wonders: Planetfall.

- Enable Retina backing for the native fullscreen window.
- Pass drawable pixel dimensions to the game's resize handler through both SDL event-polling calls.
- Map mouse coordinates to the current interface frame and retain normal cursor assets.
- Provide installation, update, status, and byte-exact restoration with checksum validation and rollback after failed installation.
- Build the verified x86_64 patch payload from assembly source using Apple's Command Line Tools.
- Include optional display diagnostics and event-processing checks.

Fullscreen uses the desktop drawable resolution. In-game resolution selection, refresh-rate control, and an FPS limiter are outside this release.
