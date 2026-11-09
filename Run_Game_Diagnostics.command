#!/bin/zsh
set -eu
fix_dir="${0:A:h}"
launch_log="$fix_dir/game_diagnostics_launch.log"
exec > >(/usr/bin/tee "$launch_log") 2>&1
trap 'diagnostic_exit_code=$?; if (( diagnostic_exit_code != 0 )); then print -u2 "Diagnostics stopped (exit $diagnostic_exit_code). Launch log: $launch_log"; fi' EXIT
print "Diagnostic launcher started: $(/bin/date -u '+%Y-%m-%dT%H:%M:%SZ')"
game_app="$fix_dir/../Age of Wonders - Planetfall.app"
if [[ ! -d "$game_app" ]]; then
  game_app='/Applications/Age of Wonders Planetfall/Age of Wonders - Planetfall.app'
fi
game_app="${game_app:A}"
game_executable="$game_app/Contents/MacOS/Age of Wonders - Planetfall"
if [[ ! -x "$game_executable" ]]; then
  print -u2 'Planetfall executable not found.'
  exit 1
fi
if [[ -n "$(/bin/ps -axo comm= | /usr/bin/grep -F "$game_executable" || true)" ]]; then
  print -u2 'Quit Planetfall before starting a diagnostic session.'
  exit 1
fi
frameworks="$game_app/Contents/Frameworks"
if [[ "${1:-}" == '--update' ]]; then
  python3 "$fix_dir/build_pixel_events.py" --output "$fix_dir/pixel_events.bin"
  python3 "$fix_dir/retina_fix.py" update --app "$game_app"
fi
clang -arch x86_64 -dynamiclib -O2 -Wall -Wextra \
  -framework AppKit -framework QuartzCore \
  "$fix_dir/display_trace.m" "$frameworks/libSDL2.dylib" "$frameworks/libMoltenVK.dylib" \
  -Wl,-headerpad_max_install_names,-install_name,@rpath/libPlanetfallDisplayTrace.dylib \
  -o "$fix_dir/libPlanetfallDisplayTrace.dylib"
/usr/bin/install_name_tool \
  -change /usr/local/opt/sdl2/lib/libSDL2-2.0.0.dylib "$frameworks/libSDL2.dylib" \
  -change @rpath/libMoltenVK.dylib "$frameworks/libMoltenVK.dylib" \
  "$fix_dir/libPlanetfallDisplayTrace.dylib"
/usr/bin/codesign --force --sign - --timestamp=none "$fix_dir/libPlanetfallDisplayTrace.dylib"
trace_path="$fix_dir/game_display_trace.log"
if [[ -f "$trace_path" ]]; then
  /bin/mv -f "$trace_path" "$fix_dir/game_display_trace.previous.log"
fi
print 'Launching Planetfall with temporary display diagnostics.'
print 'Open Video options, load a map briefly, then quit normally.'
print "Log: $trace_path"
cd -- "${game_app:h}"
PF_DISPLAY_TRACE="$trace_path" \
DYLD_INSERT_LIBRARIES="$fix_dir/libPlanetfallDisplayTrace.dylib" \
  "$game_executable"
if [[ ! -s "$trace_path" ]] || ! /usr/bin/grep -q 'Planetfall display trace v' "$trace_path"; then
  print -u2 'The game exited without initializing the diagnostic library.'
  print -u2 "Keep this launch log for investigation: $launch_log"
  exit 1
fi
print "Finished. Log: $trace_path"
