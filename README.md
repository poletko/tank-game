# Tank Arena

A local multiplayer top-down tank shooter for Linux. Up to 6 players (any mix of controllers and the two keyboard slots) fight on one static screen.

## Run
    ./run.sh              # fullscreen
    ./run.sh --windowed   # in a window

Needs Python 3 and pygame (`sudo apt install python3-pygame`).

## Controls (Xbox controller)
| Input | Action |
|---|---|
| A | join (lobby) / fire |
| Left stick / D-pad | drive |
| Right stick | aim turret |
| RT / RB / A | fire |
| START | start match / pause |
| B | leave lobby; in pause: quit to lobby |
| BACK | in pause: quit to lobby |

Two players can share the keyboard:
- **P1:** WASD drive, Q/E turret, Space join/fire, X leave
- **P2:** arrows drive, `,` `.` turret, Right Ctrl join/fire, Delete leave
- **Both:** Enter starts or pauses.

F11 toggles fullscreen. ESC returns to the lobby, or quits from the lobby.

## Rules
- Each tank has 3 HP. The last tank standing wins the round, and the first to 5 round wins takes the match. With 5-6 players the extra tanks spawn at the middle of the left and right edges.
- Bricks break after 2 hits. Shells bounce once off steel, so they can hit you on the rebound. Water blocks tanks but not shells. Bushes hide tanks.
- Each tank carries 10 shells. An ammo crate appears at a random spot for 7 s (it blinks near the end, and a ring shows the time left). Driving over it refills you to 10. Once it's picked up or gone, the next one appears 10 s later.
- Each round gets a new random map with 4-way symmetry.
- Controllers can be plugged in at any time. If one disconnects mid-match, press A on any free pad to take over that player.
