# Tank Arena: notes for editing

A local multiplayer top-down tank shooter for Linux, Windows and the browser in a single Python file using pygame. There are no asset files: graphics and sounds are generated in code at startup.

## Files
- `tanks.py`: the whole game.
- `run.sh` / `run.bat`: Linux / Windows launchers; they check that pygame is installed and pass args through (`--windowed`).
- `.github/workflows/windows.yml`: on every push to `main`, GitHub runs the smoke test on Windows, builds `TankArena.exe` with
  PyInstaller, runs `TankArena.exe --check` (`Game.self_check`: a few seconds of every mode), and replaces the
  `latest` release with it. If the build fails, the old release stays. Check the Actions tab after pushing.
- `.github/workflows/web.yml`: on every push to `main`, builds the browser version with pygbag (the game copied in as
  `main.py`) and deploys it to GitHub Pages: https://poletko.github.io/tank-game/
- `tests/smoke_test.py`: headless test that runs the game with fake players and random inputs.
- `README.md`: player-facing docs (controls, rules). Keep it in sync when controls or rules change.

## Running
    ./run.sh --windowed        # play
    python3 tests/smoke_test.py # headless check; must print "OK" (takes about 30 s)

Always run the smoke test after changes. For visual changes, also look at the screenshots it saves
(`--shots DIR` writes `lobby.png` and `game.png`).

## Layout of tanks.py (top to bottom)
1. **Constants:** screen 1280x720, 40 px tiles, 32x17 grid under a 40 px HUD bar. Tuning values:
   `TANK_SPEED`, `FIRE_COOLDOWN`, `MAX_AMMO`, `CRATE_LIFE`, `CRATE_RESPAWN`, `WIN_SCORE`, `MAX_PLAYERS` (6).
   Race tuning is in the `RACE_*`, `TRACK_*`, `RAMP_*` constants.
   `PLAYER_COLORS` needs at least `MAX_PLAYERS` entries. `CORNER_SPAWNS` are used first, then `SIDE_SPAWNS`.
   `KB_MAPS` holds the two keyboard players' bindings.
2. **Helpers:** angle math, `add_glow` (additive light, cached per color and radius), `make_vignette`.
3. **`Sounds`:** procedural sound bank (`self.snd[name] = self.make(duration, fn(t), vol)`); play with `self.sounds.play(name)`.
4. **`Pad`:** one input device, read every frame by `poll()` into `move`, `aim`, `turret_rot`, `held`
   and `pressed` (edge-triggered). Kinds are `ctrl` (SDL GameController, the normal path for Xbox pads),
   `joy` (raw fallback assuming the xpad layout), and `kb1`/`kb2`. Button names used by game logic:
   `fire`, `a`, `b`, `start`, `back`.
5. **Sprite builders:** drawn at 3x (`SS`) and smooth-scaled down for antialiasing. Always call
   `.convert()` or `.convert_alpha()` on finished surfaces, because unconverted surfaces made the game
   drop below 120 FPS.
6. **`Arena`:** grid (`EMPTY, BRICK, STEEL, WATER, BUSH`), symmetric random map `generate()` with a
   connectivity check, tank-vs-wall collision. Rendering layers:
   - `static`: floor, steel and baked shadows; rebuilt each round.
   - `ground`: a cache of `static` plus bricks and the vignette. Set `arena.ground = None` whenever a
     brick changes so it gets rebuilt.
   - `decal()`: permanent marks (treads, scorch, wrecks). It paints into both `static` and `ground`.
   - Each frame: animated water, then (in `Game`) tanks, bullets, particles, then bushes on top.
7. **Entities:** `Player` (color, score, sprites, `pad_id`), `Tank`, `Bullet`.
8. **`Game`:**
   - **State machine:** `lobby → countdown → play → roundover → (new round | matchover → lobby)`,
     plus a `paused` flag.
   - **Update:** `update_tanks`, `update_bullets`, `update_crate` and `update_effects` each own their own concern.
   - **Effects lists:** `particles` (list-based: `[x, y, vx, vy, life, max_life, kind, size, (color)]`, where
     kind is `fire`, `smoke`, `spark` or `debris`), `rings`, `flashes`, `texts`, `wrecks`.
   - **Drawing:** `draw_world` (shaken by `self.shake`), then `draw_hud`, then `draw_overlay`; the lobby uses `draw_lobby`.
   - **Controller hot-plug:** handled in `run()` via `scan_pads()` and `remove_pad()`. In a match, a new
     pad pressing A takes over a player whose pad disconnected (`claim_orphans`).

## Co-op mode
- `Game.mode` is `'versus'`, `'coop'` or `'race'`. It's cycled in the lobby by the Y button (the `'y'` pad button) or Tab (handled as a KEYDOWN event, because both keyboard pads would otherwise toggle it twice).
- Tuning lives in the `COOP_*`, `GHOUL_*`, `WAVE_BREAK` and `AMMO_DROP*` constants. The user specified these rules, so keep them unless asked: wave N spawns N ghouls; ghouls take 5 hits, regenerate 1 hit per 10 s, slow to 50% for 3 s per hit, move at 60% of tank speed and chase the closest tank.
- `Ghoul` is the entity. The logic is in `update_waves` → `start_wave` / `spawn_ghoul`, then `update_ghouls`, `hit_ghoul`, `kill_ghoul` and `update_pickups`.
- Pathing: `compute_flow` is a Dijkstra distance field from all live tanks (bricks cost 6, steel and water are blocked), recomputed every 0.25 s. Walkers step to the downhill neighbour tile (`ghoul_step_target`) and claw bricks in the way. Ghosts ignore walls and are drawn above bushes.
- In co-op, bullets skip tanks entirely (no friendly fire) and don't cancel each other. The `coopover` state shows the results.

## Special weapons
- `Tank.special` is `'rocket'`, `'mortar'` or `'tesla'`. `special_recharge` is 0 for co-op packets (one shot, then
  the special is cleared) and `SPECIAL_RECHARGE` (7 s) for the versus catch-up weapon. `special_charge` counts down
  to ready. The user asked for these rules: co-op packets appear only while exactly one tank of 2+ players is alive
  (`update_packet`); in versus, the lowest-score players get a random rechargeable special in `new_round`, but
  only once someone is ahead.
- Input: the `'fire2'` pad button (LT/LB/X, keyboard F and `/`) goes to `special_input`. The mortar is
  hold-to-aim (`Tank.mortar_aim` grows by `MORTAR_AIM_SPEED`) and fires on release.
- `targets(owner)` lists what specials hurt: ghouls in co-op, enemy tanks in versus (never the shooter or allies).
  Rockets and mortars are `Missile`s in `self.missiles` and end in `explode()` (2 damage in the radius, and bricks).
  `tesla()` floods outward through touching targets; bolts live in `self.zaps`.

## Race mode
- `mode == 'race'` swaps the arena for a `Track` (built lazily in `new_race`): a closed Catmull-Rom loop resampled
  every `TRACK_STEP` px into `pts`/`ang`/`nx`/`ny`, rotated so index 0 is the start line on the straightest stretch.
  `valid()` rejects loops that leave the screen, have corners tighter than ~50 px radius, or come within
  `TRACK_W + 34` of themselves. `render()` bakes grass, curbs, asphalt, grid, ramps and tree shadows into
  `track.surface`; `track.decal()` paints skid marks, blood and limbs onto it. `track.mask` answers `onroad()`.
- Physics live in `update_race_tanks`: velocity `vx, vy` split into forward and sideways parts in the heading frame.
  Sideways decays at `RACE_GRIP` (times `RACE_DRIFT_GRIP` when turning hard at speed), and that lag is the drift.
- Pseudo-3D: `Tank.z`/`vz` are height. Anything at height z is drawn `z` px higher on screen, with its shadow left
  at ground level. Ramps (`(x, y, cos, sin, index)`) set z while a tank drives up them; leaving the lip sets
  `vz = forward speed * RAMP_KICK`. Ramps are drawn as wedges with that same projection (`Track.draw_ramp`).
- Progress: `Tank.seg` comes from a local search around the previous index (`Track.nearest`), so shortcuts gain
  nothing. `Tank.dist` accumulates the wrapped index deltas; `dist // n` is laps done. Far off track for
  `RACE_LOST_TIME` puts the tank back at `seg`.
- Shells inherit the tank's velocity, never damage, and call `bump_tank`. Spectators are `Ghoul` objects in
  `self.spectators` (static, shadows baked into the track). `kill_spectator` paints `make_blood_splat` and launches
  `self.gibs` (limbs from `make_gib_sprites`) that become decals when they land.
- Race tanks draw from `Player.race_sprite` (pre-rotated in 5 degree steps). Rotating them live each frame dropped
  the race below 120 FPS. They're only rotated live while airborne, because of the scaling.

## Math break
- `quiz_clock` counts seconds in `countdown`/`play`. Once it passes `QUIZ_INTERVAL` (240 s), `update()` opens a
  `Quiz` at the next `at_break()`: lobby, roundover, matchover, coopover, or an empty co-op wave break. While
  `self.quiz` is set, `update()` only runs `update_quiz`, so the game is frozen. The clock resets when a question
  is answered correctly. The user asked for this: keep it mandatory and never open it mid-action.
- `make_question()` returns `(text, answer, unit)` in Slovenian at the level of a finished 4th grade; answers must
  fit `QUIZ_DIGITS`. The smoke test checks 5000 random questions. Entry uses the pad's edge-triggered
  `up/down/left/right` buttons (derived from the stick and D-pad in `Pad.poll`), and keyboard digits come in as
  KEYDOWN events in `run()`.

## Browser version (pygbag)
- pygbag runs CPython and pygame-ce compiled to WebAssembly. `WEB` (`sys.platform == 'emscripten'`) gates the few
  differences: no fullscreen at start, no quit or F11 handling (the browser owns those), no frame limit in
  `clock.tick` (the browser paces frames), and `Arena.sway = False`.
- `run()` and `main()` are async: the browser only gets to show a frame at `await asyncio.sleep(0)`. Never add a
  blocking loop that runs across frames.
- Speed in the browser, measured: plain Python is about 3x slower than desktop, opaque blits about the same, but
  **alpha blits are 10-20x slower** (a full-screen alpha blit is ~60 ms, a full-screen `fill` ~4 ms). So: no
  full-screen alpha layers (`dim()` uses a `BLEND_RGB_MULT` fill), no full-screen fill under a world that covers
  the screen, static screens are cached as opaque surfaces (`lobby_cache`), sprites are pre-rotated
  (`Player.rotated`), and without sway, bushes are baked into `arena.ground` and redrawn only near moving things.
  Frame draw time in headless Chrome: versus ~7 ms, co-op ~10 ms, race ~12 ms. Keep it under ~12 ms.
- To test locally: `pip install pygbag`, copy `tanks.py` to `somedir/main.py`, run `python -m pygbag somedir`
  and open http://localhost:8000. Python output goes to the page's built-in terminal, not the JS console.

## Conventions
- Keep it a single file with no dependencies beyond pygame and no external assets.
- Match the existing style: plain classes, short comments only where something is non-obvious.
- Must work on Linux, Windows and in the browser: no shell calls, OS paths, threads, files or platform-specific APIs. Controller support relies on SDL's GameController
  mappings, so test new input features against `ctrl` pads first.
- Performance budget: 120 FPS. Avoid per-frame full-screen alpha blits and per-tile alpha blits;
  bake them into cached layers instead. Measure with the smoke test's FPS line.

## Delegating boilerplate
For large, low-judgment additions (new standalone files, test suites, docs), the `pi-delegate` skill
can hand the work to the local qwen3-coder-30b model. Always verify what it produces.
