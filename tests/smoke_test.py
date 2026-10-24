#!/usr/bin/env python3
"""Headless smoke test: 6 fake players, many random rounds. Prints OK on success.

Usage: python3 tests/smoke_test.py [--shots DIR]
"""
import os
import random
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pygame  # noqa: E402
import tanks   # noqa: E402

shots = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
pygame.mixer.pre_init(22050, -16, 2, 512)
pygame.init()
if tanks.sdl_ctrl:
    tanks.sdl_ctrl.init()
random.seed(1)

g = tanks.Game(False)
fake = [f"fake{i}" for i in range(tanks.MAX_PLAYERS)]
for pid in fake:
    g.pads[pid] = tanks.Pad(pid, "kb1")
g.players = [tanks.Player(i, pid) for i, pid in enumerate(fake)]
g.draw()
if shots:
    pygame.image.save(g.screen, os.path.join(shots, "lobby.png"))

# spawns must be clear of walls and of each other on every map
for _ in range(30):
    g.new_round()
    pos = set()
    for p in g.players:
        t = p.tank
        assert g.arena.collide_circle(t.x, t.y, tanks.TANK_R) == (t.x, t.y), "tank spawned inside a wall"
        pos.add((round(t.x), round(t.y)))
    assert len(pos) == len(g.players), "two tanks share a spawn"

g.start_match()
crates = kills = frames = 0
t0 = time.time()
for i in range(6000):
    for pid in fake:
        pad = g.pads[pid]
        pad.move = (random.uniform(-1, 1), random.uniform(-1, 1))
        pad.aim = random.uniform(-3.2, 3.2)
        pad.held, pad.pressed = {"fire"}, set()
    had_crate = g.crate
    alive_before = sum(1 for p in g.players if p.tank and p.tank.alive)
    g.update(1 / 60)
    g.draw()
    frames += 1
    crates += bool(g.crate and not had_crate)
    if g.state == "play":
        kills += max(0, alive_before - sum(1 for p in g.players if p.tank and p.tank.alive))
    if shots and i == 400:
        pygame.image.save(g.screen, os.path.join(shots, "game.png"))
    for p in g.players:
        assert p.tank is None or 0 <= p.tank.ammo <= tanks.MAX_AMMO
fps = frames / (time.time() - t0)
print(f"versus: frames={frames} fps={fps:.0f} crates={crates} kills={kills} scores={[p.score for p in g.players]}")
assert crates > 0, "no ammo crate ever spawned"
assert kills > 0, "no tank was ever destroyed"

# ---- co-op: bots shoot the nearest ghoul at close range
import math  # noqa: E402
g.to_lobby()
g.mode = "coop"
g.players = g.players[:2]
g.start_match()
assert all(p.tank.hp == tanks.COOP_TANK_HP for p in g.players)
wave_sizes = {}
for i in range(60 * 240):
    for p in g.players:
        pad, t = g.pads[p.pad_id], p.tank
        pad.pressed, pad.move, pad.held, pad.aim = set(), (0, 0), set(), None
        if t and t.alive and g.ghouls:
            gh = min(g.ghouls, key=lambda q: (q.x - t.x) ** 2 + (q.y - t.y) ** 2)
            pad.aim = math.atan2(gh.y - t.y, gh.x - t.x)
            if math.hypot(gh.x - t.x, gh.y - t.y) < 200:
                pad.held = {"fire"}
    before = g.wave
    g.update(1 / 60)
    if i % 4 == 0:
        g.draw()
    if shots and len(g.ghouls) >= 3 and not os.path.exists(os.path.join(shots, "coop.png")):
        g.draw()
        pygame.image.save(g.screen, os.path.join(shots, "coop.png"))
    if g.wave != before:
        wave_sizes[g.wave] = g.wave_to_spawn
    if g.state == "coopover":
        break
ghoul_kills = sum(p.kills for p in g.players)
print(f"co-op: reached wave {g.wave}, wave sizes {wave_sizes}, ghoul kills {ghoul_kills}")
assert all(n == w for w, n in wave_sizes.items()), "wave N must bring N ghouls"
assert g.wave >= 2 and ghoul_kills > 0

# ghoul rules: 60% speed, 50% slow for 3 s per hit, regen 1 hit / 10 s, 5 hits to kill
g.state = "play"
for p in g.players:
    p.tank = g.make_tank(p)
t = g.players[0].tank
g.players[1].tank.alive = False
gh = tanks.Ghoul("ghost", t.x + 300, t.y)   # ghosts ignore walls, so speed is measurable anywhere
gh.emerge = 0
g.ghouls = [gh]


def speed(dt=0.1):
    x, y = gh.x, gh.y
    g.update_ghouls(dt)
    return math.hypot(gh.x - x, gh.y - y) / dt


assert abs(speed() - tanks.TANK_SPEED * 0.6) < 1
g.hit_ghoul(gh, tanks.Bullet(t, gh.x, gh.y, 0))
assert gh.hp == tanks.GHOUL_HP - 1
assert abs(speed() - tanks.TANK_SPEED * 0.3) < 1
for _ in range(30):
    g.update_ghouls(0.1)
assert abs(speed(0.02) - tanks.TANK_SPEED * 0.6) < 1, "slow should wear off after 3 s"
gh.x, gh.y = t.x + 600, t.y
for _ in range(100):
    gh.x, gh.y = t.x + 600, t.y   # keep it away from the tank
    g.update_ghouls(0.1)
assert gh.hp == tanks.GHOUL_HP, "ghoul should regenerate a hit in 10 s"
for _ in range(tanks.GHOUL_HP):
    g.hit_ghoul(gh, tanks.Bullet(t, gh.x, gh.y, 0))
assert gh.dead and not g.ghouls
print("OK")
