# Tank Arena

A local multiplayer top-down tank shooter for Linux, Windows and the browser. Up to 6 players (any mix of controllers and the two keyboard slots) fight on one static screen. The game's on-screen text is in Slovenian.

## Run
**Browser:** open [poletko.github.io/tank-game](https://poletko.github.io/tank-game/) and click once to start (browsers only allow sound after a click). It runs best in Chrome or Edge. The first load takes a few seconds. Press F11 for fullscreen. Controllers work if you press a button on them after the page has loaded. The browser version is a bit lighter on effects (bushes don't sway) and may run slower than the desktop versions on older computers.

**Windows:** download [TankArena.exe](https://github.com/poletko/tank-game/releases/latest/download/TankArena.exe) and double-click it. Nothing needs installing. It's built automatically from the latest code. The first time, Windows may say it "protected your PC" because the app isn't signed: click **More info**, then **Run anyway**.

**Linux:**

    ./run.sh              # fullscreen
    ./run.sh --windowed   # in a window

Needs Python 3 and pygame (`sudo apt install python3-pygame`). On Windows you can also run from source with Python and `pip install pygame`, then `run.bat`.

## Controls (Xbox controller)
| Input | Action |
|---|---|
| A | join (lobby) / fire |
| Left stick / D-pad | drive |
| Right stick | aim turret |
| RT / RB / A | fire |
| LT / LB / X | special weapon (when you have one) |
| START | start match / pause |
| B | leave lobby; in pause: quit to lobby |
| BACK | in pause: quit to lobby |

Two players can share the keyboard:
- **P1:** WASD drive, Q/E turret, Space join/fire, F special weapon, X leave
- **P2:** arrows drive, `,` `.` turret, Right Ctrl join/fire, `/` special weapon, Delete leave
- **Both:** Enter starts or pauses.

F11 toggles fullscreen. ESC returns to the lobby, or quits from the lobby.

## Rules
- Each tank has 3 HP. The last tank standing wins the round, and the first to 5 round wins takes the match. With 5-6 players the extra tanks spawn at the middle of the left and right edges.
- Bricks break after 2 hits. Shells bounce once off steel, so they can hit you on the rebound. Water blocks tanks but not shells. Bushes hide tanks.
- Each tank carries 10 shells. An ammo crate appears at a random spot for 7 s (it blinks near the end, and a ring shows the time left). Driving over it refills you to 10. Once it's picked up or gone, the next one appears 9 s later.
- Each round gets a new random map with 4-way symmetry.
- Catch-up weapon: whoever is in last place (lowest score, once someone is ahead) gets a random special weapon for the round, fired with LT / LB / X. It recharges 7 s after each use.
- Controllers can be plugged in at any time. If one disconnects mid-match, press A on any free pad to take over that player.

## Co-op mode
Press **Y** (controller) or **Tab** (keyboard) in the lobby to cycle through VERSUS, CO-OP and RACE. All the tanks team up against waves of mummies, zombies, vampires and ghosts.
- Wave 1 has one ghoul, and each cleared wave adds one more (wave N brings N ghouls).
- A ghoul takes 5 hits to kill and regenerates 1 hit every 10 s. Each hit slows it to half speed for 3 s.
- Ghouls move at 60% of tank speed and chase the closest tank. Walkers go around walls and claw through bricks if they have to. Ghosts float straight through walls.
- A ghoul's touch costs a tank 1 HP. Tanks have 5 HP in co-op, and there's no friendly fire.
- Ammo refills at the start of each wave, crates still appear, and killed ghouls sometimes drop a +3 ammo box.
- Special weapon packets keep appearing on the map. Each packet gives one shot of a special weapon to whoever drives over it first, and a new one shows up a few seconds after it's picked up or fades, as long as some tank has no special.
- Every cleared wave fully repairs all surviving tanks. Fallen tanks come back at the next wave. When every tank is down the game ends and shows the wave you reached and each player's kills.

### Bosses
Every third wave brings a boss along with its ghouls. A health bar at the top shows how it's doing. Bosses are bigger and faster than ghouls, take 17 hits, and aren't slowed by hits. Each has a ranged attack that only ever flies straight along a row or a column, never diagonally. Before it throws, the boss flashes and a red dashed line shows exactly where the attack will go, so get out of line. A killed boss drops three ammo boxes.
1. **Wave 3, the Cursed Knight:** throws his sword, which flies out and comes back along the same line. He can't throw again until he's caught it.
2. **Wave 6, the Spider Queen:** leaves sticky webs on every tile she walks over. Webs slow tanks to under half speed and fade after 15 s. She also spits web balls that pin a tank in place for a second.
3. **Wave 9, the Great Snake:** long. Its body blocks tanks, and a shot anywhere on it counts. Spits venom.
4. **Wave 12, the Witch:** flies on her broom over walls, keeps her distance and lines up with you. She lobs cats over walls; a cat lands, hisses for half a second, then explodes.

After the witch the order starts again from the knight, with 10 more hits each time round.

If the tanks fall while a boss is still alive, that boss fills the screen and gloats (in Slovenian).

## Special weapons
Fired with LT / LB / X (keyboard: F or `/`). An icon next to your tank shows the weapon and its recharge.
- **Rocket:** flies fast in a straight line and explodes on the first wall, ghoul or tank it hits. Everything in the blast takes 2 damage, and bricks in it are damaged too.
- **Mortar:** hold the button and a red target circle walks out in front of your turret; let go to fire. The round arcs over walls and does 2 damage to everything in the circle.
- **Tesla coil:** zaps the nearest target within range, then jumps to every ghoul (or tank) touching it, and on down the chain. Each one loses 1 health. If nothing is in range, the charge isn't used.

## Race mode
The third mode in the lobby. Smaller, faster tanks race around a randomly generated street circuit (hairpins, chicanes and long straights) that fills the whole screen.
- 5 laps; the first tank across the line wins the race, and the first to 3 race wins takes the match. A new track is generated for every race.
- Tanks accelerate quickly and drift: steer hard at speed and the back slides out, leaving skid marks. Grass slows you down.
- It's pseudo-3D: yellow-and-black ramps launch tanks into the air, where they can't steer, and they get bigger as they rise, with their shadow left on the ground. Hit a ramp faster to fly further.
- Shells don't do damage. They knock the tank they hit sideways and pop it off the ground, so use them to push rivals off the track. Shells are unlimited.
- The crowd lining the track is ghouls. Hit one with a shell or touch it with your tank and it bursts into a red stain and scattered limbs that stay for the rest of the race. The HUD keeps count.
- **The Ghost Rider** haunts every race on a burning motorcycle, a bit slower than a tank at full speed. Get stuck behind him and he lashes back with a flaming chain that spins you round and kills your speed. One shell banishes him, but he rides again 3 s later. Overtake fast, or shoot first.
- Cutting across the grass doesn't count as progress. A tank that stays far off the track for 2 s is put back on it.

## Math break
After every 4 minutes of play, a math question appears at the next pause in the action: the end of a round or race, the gap between co-op waves, or the lobby. It never pops up mid-fight. The questions match a finished 4th grade in Slovenia and are in Slovenian: adding and subtracting up to 10 000, the times tables, multiplying and dividing by a one-digit number, order of operations, 1/n of a number, unit conversions, perimeter, rounding, missing numbers and short word problems.
- Any player can answer. The answer goes into five digit boxes: stick or D-pad **up/down** changes the selected digit, **left/right** moves between digits, and **A** or **START** submits. On the keyboard you can also type the digits, use Backspace, and press Enter.
- The game stays frozen until the answer is right. After 3 wrong tries the solution is shown and a new question is asked.

## License
Public domain ([The Unlicense](LICENSE)). Anyone can do whatever they want with this game: copy it, change it, share it or sell it, with no conditions and no credit needed.
