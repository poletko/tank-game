# Tank Arena: notes for editing

A local multiplayer top-down tank shooter for Linux in a single Python file using pygame. There are no asset files: graphics and sounds are generated in code at startup.

## Files
- `tanks.py`: the whole game.
- `run.sh`: launcher; checks that pygame is installed and passes args through (`--windowed`).
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

## Conventions
- Keep it a single file with no dependencies beyond pygame and no external assets.
- Match the existing style: plain classes, short comments only where something is non-obvious.
- Linux-only (the game exits on other platforms). Controller support relies on SDL's GameController
  mappings, so test new input features against `ctrl` pads first.
- Performance budget: 120 FPS. Avoid per-frame full-screen alpha blits and per-tile alpha blits;
  bake them into cached layers instead. Measure with the smoke test's FPS line.

## Delegating boilerplate
For large, low-judgment additions (new standalone files, test suites, docs), the `pi-delegate` skill
can hand the work to the local qwen3-coder-30b model. Always verify what it produces.
