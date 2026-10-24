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
print(f"frames={frames} fps={fps:.0f} crates={crates} kills={kills} scores={[p.score for p in g.players]}")
assert crates > 0, "no ammo crate ever spawned"
assert kills > 0, "no tank was ever destroyed"
print("OK")
