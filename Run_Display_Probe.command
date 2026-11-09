#!/bin/zsh
set -eu
set -o pipefail
cd -- "${0:A:h}"
game_app='../Age of Wonders - Planetfall.app'
if [[ ! -d "$game_app" ]]; then
  game_app='/Applications/Age of Wonders Planetfall/Age of Wonders - Planetfall.app'
fi
if [[ ! -d "$game_app" ]]; then
  print -u2 'Put this directory beside Age of Wonders - Planetfall.app, or edit game_app in this script.'
  exit 1
fi
game_app="${game_app:A}"
clang -arch x86_64 -Wno-deprecated-declarations \
  -framework AppKit -framework CoreVideo -framework CoreGraphics \
  -Wl,-sectcreate,__TEXT,__info_plist,"$PWD/probe.plist" \
  probe.m -o display_probe
./display_probe \
  "$game_app/Contents/Frameworks/libSDL2.dylib" \
  "$game_app/Contents/Frameworks/libMoltenVK.dylib" 2>&1 | tee display_probe.log
