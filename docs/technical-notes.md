# Technical notes

These findings apply to the executable fingerprint listed below. The source targets the original x86_64 macOS game through its bundled SDL 2.0.10 and MoltenVK libraries. File offsets and virtual addresses are specific to this build.

## Retina rendering pipeline

Enabling a Retina output surface alone does not correct the game's application and interface dimensions. The uncorrected UI intermediate is enlarged into the drawable, producing blurry text.

| Stage | HiDPI surface alone | v1.0.0 |
| --- | --- | --- |
| SDL window | 1512×945 points | 1512×945 points |
| Backing scale | 2× | 2× |
| Metal drawable / Vulkan swapchain | 3024×1890 pixels | 3024×1890 pixels |
| Application render size / UI frame | 1512×945 pixels | 3024×1890 pixels |
| Main viewport | 1512×945 pixels | 3024×1890 pixels |

The supported game dispatches `SDL_WINDOWEVENT_RESIZED` (5) to its resize handler and ignores `SDL_WINDOWEVENT_SIZE_CHANGED` (6). Both calls to `SDL_PollEvent` in its native event pump must pass through the conversion wrapper; the second call delivers events inside the polling loop.

## Binary changes

| Change | Location and behavior |
| --- | --- |
| SDL HiDPI flag | At file offset `0xEC1324`, change `41 B9 20 00 00 10` to `41 B9 20 20 00 10`, adding `SDL_WINDOW_ALLOW_HIGHDPI`. |
| App capability | Set `NSHighResolutionCapable=true` in `Info.plist`. |
| Normal cursor assets | At `0xEC175B`, replace `48 0F 4F C1` with four NOPs to prevent automatic selection of 96px images instead of 32px images. |
| Event wrapper | Redirect calls at `0xEC18E4` and `0xEC1AD9` to the wrapper at file offset `0x7000`, in checked zero-filled executable padding. |
| Resize handling | Convert fullscreen `RESIZED` dimensions from window coordinates to drawable pixels before the game handles the event. |
| Mouse handling | Scale positions and motion using the actual application UI dimensions at `b688/b68c`, divided by SDL window dimensions. |
| Presentation wrapper | Redirect the `vkQueuePresentKHR` call at `0x437435` to file offset `0x7400`; pace presentation when the configured cap is nonzero. |
| Configuration | Store an eight-byte format marker, width, height, and frame interval in the code/configuration payload at file offset `0x7D00`. |

The dispatch table at `0xEC1B40` routes resize reason 5 to `0x100EC0C2F`. The application's resize method at `0x100EBA87E` updates render and UI dimensions, and the Vulkan setter at `0x100437D56` stores the render dimensions. The frame path passes the UI dimensions to both layout and input handling.

The wrapper obtains the window, fullscreen flag, and application pointer from the inspected globals. Relative references support ASLR. Zero, invalid, or excessive dimensions bypass conversion. Keyboard, text, wheel, controller, and other unrelated events pass through. Windowed resize events remain unchanged.

The 3352-byte code/configuration template is rebuilt by `build_pixel_events.py`. Expected SHA-256 before applying local settings:

```text
ba505e076f88073f76ab6bf5ca6b8d55162c59c0d893603173a2ebedb9a34ca4
```

v1.1.0 uses internal patch revision 6 and retains compatibility with v1.0.0/revision 5 backups. The manifest records the payload fingerprint separately from local settings, so an updated payload is installed even if the version number has not changed. Upgrading an identical development payload to the release updates the recorded version while preserving installed game bytes and settings.

## Internal resolution and frame pacing

A custom resolution replaces fullscreen `RESIZED` event dimensions directly. The application's render and UI frames use that size, and the original renderer composites them into the desktop-sized swapchain. The presentation surface itself stays at the desktop resolution. Mouse mapping uses the actual UI frame, including custom sizes and fractional ratios.

The cap interval is `ceil(1,000,000,000 / FPS)` nanoseconds. The presentation wrapper uses the game's imported `clock_gettime` with macOS `CLOCK_MONOTONIC` (6) and `usleep`. It sleeps until a monotonic deadline, preserving the original Vulkan arguments and return value. Subsequent deadlines retain their phase across ordinary timer wake-up jitter instead of accumulating oversleep on every frame. A miss of a full additional interval resets the schedule; there is no unbounded catch-up backlog. Disabled pacing jumps directly to the original presentation import.

The previous deadline lives at virtual address `0x1015AF400`, in zero-filled trailing padding of `__DATA`, beyond all declared sections and below the next segment. The installer verifies that these eight bytes are writable, zero-filled, and outside every section before applying the patch. No existing game variable, writable executable page, added Mach-O segment, or external library is used for this state.

## Fullscreen and presentation limits

The original game requests `SDL_WINDOW_FULLSCREEN_DESKTOP` (`0x1001`) and does not apply the selected resolution or refresh mode with `SDL_SetWindowDisplayMode`. v1.0.0 preserves desktop fullscreen. Simply replacing its flag with exclusive fullscreen would be unsafe because the existing path first sets a 320×240 window.

The observed desktop mode reported 120 Hz. Presentation submissions varied, with several traced intervals near 120/s. These values do not measure instantaneous adaptive display refresh. Shadow maps, texture atlases, and reduced-resolution effects have independent dimensions.

Internal resolution and the FPS cap are configured by the script and applied on the next launch. Monitor mode/refresh switching and the in-game resolution menu remain unresolved.

## Checks

The assembly tests cover fullscreen resize conversion, configured resolution overrides, ignored size-changed events, windowed passthrough, mouse mapping to a low-resolution UI on a Retina surface, 1×/2× and fractional mapping, negative coordinates, buttons and motion, keyboard and wheel passthrough, and null/no-event handling. Presentation tests cover disabled pacing, render/present cost, non-accumulating wake-up jitter, interrupted sleep, clock failures, backwards clock movement, long pauses, and argument/result preservation.

`tests/check_game_dispatch.py` inspects the original game's resize dispatch table and independently finds both direct SDL polling calls in its event-pump function. The exact injected bytes were also executed in a signed x86_64 Mach-O fixture under Rosetta during development. Installation, failed-signing rollback, idempotence, signature verification, and original-byte restoration were validated against the supported build.

Native fullscreen text and graphics were visually checked in the main menu, with runtime traces confirming 3024×1890 application and UI dimensions. Full gameplay and performance coverage remains limited.

## Original build fingerprints

| File | SHA-256 |
| --- | --- |
| Executable | `2968fee158b24c83f44486f7c37f6abae9fea0a9aa98060a672b6800acd8f894` |
| Info.plist | `69167bc7409791668da2d1ef2fba5964e921c77ab4a08f69a73842eb2d757cc4` |
| SDL | `5bd7441f290b37143c25c49dd436d1eedae6c3709429ebfcddef2c1728a20bbb` |
| MoltenVK | `7b02c6a7d854610395c70f4d1718d57126653b6c7a058987cb59b22229e91000` |

Findings come from local disassembly and runtime traces. Related API documentation: [SDL_CreateWindow](https://wiki.libsdl.org/SDL2/SDL_CreateWindow), [SDL_Vulkan_GetDrawableSize](https://wiki.libsdl.org/SDL2/SDL_Vulkan_GetDrawableSize), [SDL_SetWindowDisplayMode](https://wiki.libsdl.org/SDL2/SDL_SetWindowDisplayMode).
