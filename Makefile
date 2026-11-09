PYTHON ?= python3
CC = clang
BUILD_DIR = build

.PHONY: all test verify-game clean

all: pixel_events.bin

pixel_events.bin: pixel_events.S build_pixel_events.py retina_fix.py
	$(PYTHON) build_pixel_events.py --output $@

$(BUILD_DIR)/pixel_events_test: tests/pixel_events_test.c pixel_events.S
	mkdir -p $(BUILD_DIR)
	$(CC) -arch x86_64 -Wall -Wextra -Werror tests/pixel_events_test.c pixel_events.S -o $@

test: all $(BUILD_DIR)/pixel_events_test
	./$(BUILD_DIR)/pixel_events_test
	$(PYTHON) -c 'import ast; from pathlib import Path; [ast.parse(p.read_text(), filename=str(p)) for p in Path(".").rglob("*.py")]'
	/bin/zsh -n Run_Game_Diagnostics.command
	/bin/zsh -n Run_Display_Probe.command

# Example: make verify-game GAME_EXECUTABLE='/path/to/original/executable'
verify-game:
	@test -n "$(GAME_EXECUTABLE)" || { echo 'Set GAME_EXECUTABLE to the original, unpatched game executable.' >&2; exit 1; }
	$(PYTHON) tests/check_game_dispatch.py "$(GAME_EXECUTABLE)"

clean:
	rm -f pixel_events.bin display_probe libPlanetfallDisplayTrace.dylib
	rm -rf $(BUILD_DIR)
