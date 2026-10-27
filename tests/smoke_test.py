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
g.quiz_clock = -1e9   # keep the math break out of the gameplay runs; it's tested at the end
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
        me = g.player_for_pad(pid).tank
        foes = [q.tank for q in g.players if q.tank and q.tank.alive and q.tank is not me]
        if me and foes and random.random() < 0.5:   # half the time, aim at the nearest enemy
            f = min(foes, key=lambda f: (f.x - me.x) ** 2 + (f.y - me.y) ** 2)
            pad.aim = tanks.math.atan2(f.y - me.y, f.x - me.x)
        pad.held = {"fire"} | ({"fire2"} if random.random() < 0.6 else set())   # also exercises the specials
        pad.pressed = {"fire2"} if random.random() < 0.05 else set()
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

# ---- special weapons
assert tanks.CRATE_RESPAWN == 9.0 and tanks.QUIZ_INTERVAL == 240.0


def open_arena():
    g.arena.grid = [[tanks.EMPTY] * tanks.COLS for _ in range(tanks.ROWS)]
    g.arena.ground = None


def run_missiles():
    for _ in range(300):
        g.update_missiles(1 / 60)
        if not g.missiles:
            return
    raise AssertionError("missile never landed")


# versus: only the players in last place get one, and it recharges every 7 s
for p, sc in zip(g.players, (2, 1, 0, 0, 1, 2)):
    p.score = sc
g.new_round()
for p in g.players:
    assert (p.tank.special is not None) == (p.score == 0), "only the last-placed players get a special"
    assert p.tank.special is None or p.tank.special_recharge == 7.0
for p in g.players:
    p.score = 0
g.new_round()
assert not any(p.tank.special for p in g.players), "nobody is last while everyone is level"

g.state = "play"
open_arena()
me, foe, other = (p.tank for p in g.players[:3])
for t in g.players[3:]:
    t.tank.alive = False
me.x, me.y, me.turret = 200, 300, 0.0
foe.x, foe.y, foe.hp = 600, 300, 3
other.x, other.y, other.hp = 600, 600, 3
me.special, me.special_recharge, me.special_charge = "rocket", 7.0, 0.0
g.fire_special(me)
run_missiles()
assert foe.hp == 1 and other.hp == 3 and me.hp == 3, "rocket: 2 damage in the blast area only"
assert me.special == "rocket" and me.special_charge == 7.0, "versus specials recharge"

# mortar flies over steel and lands on the red circle
g.arena.grid[(300 - tanks.HUD) // tanks.T][10] = tanks.STEEL
me.special, me.special_charge = "mortar", 0.0
foe.hp = 3
me.mortar_aim = 400
g.fire_special(me)
assert g.missiles and g.missiles[0].kind == "mortar"
run_missiles()
assert foe.hp == 1, "mortar should land on the target circle and do 2 damage"

# mortar aiming with the pad: hold to walk the circle out, release to fire
pad = g.pads[me.player.pad_id]
me.special_charge = 0.0
pad.move, pad.aim, pad.turret_rot = (0, 0), None, 0.0
pad.held, pad.pressed = {"fire2"}, {"fire2"}
for _ in range(30):
    g.update_tanks(1 / 60)
    pad.pressed = set()
assert me.mortar_aim > tanks.MORTAR_MIN
pad.held = set()
g.update_tanks(1 / 60)
assert me.mortar_aim is None and g.missiles, "releasing the button fires the mortar"
g.missiles.clear()

# co-op: one-shot special packets keep coming; the tesla zaps a chain of touching ghouls
g.to_lobby()
g.mode = "coop"
g.players = g.players[:2]
g.start_match()
g.state = "play"
open_arena()
lone, fallen = g.players[0].tank, g.players[1].tank
fallen.alive = False
g.ghouls = []
for _ in range(60 * 10):
    g.update_packet(1 / 60)
    if g.packet:
        break
assert g.packet, "no special packet for the lone survivor"
g.packet[2] = "tesla"
lone.x, lone.y = g.packet[0], g.packet[1]
g.update_packet(1 / 60)
assert lone.special == "tesla" and g.packet is None
lone.x, lone.y = 300, 300
chain = [tanks.Ghoul("zombie", 400, 300), tanks.Ghoul("mummy", 400 + 2 * tanks.GHOUL_R + 4, 300),
         tanks.Ghoul("ghost", 400 + 4 * tanks.GHOUL_R + 8, 300)]
loner = tanks.Ghoul("vampire", 300, 600)
for gh in chain + [loner]:
    gh.emerge = 0
g.ghouls = chain + [loner]
g.fire_special(lone)
assert all(gh.hp == tanks.GHOUL_HP - 1 for gh in chain), "every ghoul in the touching chain loses 1"
assert loner.hp == tanks.GHOUL_HP, "a ghoul not touching the chain is spared"
assert lone.special is None, "co-op packets are one shot"
g.packet_timer = 0
g.update_packet(1 / 60)
assert g.packet, "packets keep coming"
fallen.alive = True
g.packet = None
g.packet_timer = 0
g.update_packet(1 / 60)
assert g.packet, "packets come while several tanks are alive too"
g.packet = None
g.packet_timer = 0
lone.special = fallen.special = "rocket"
g.update_packet(1 / 60)
assert g.packet is None, "no packets while every live tank holds a special"
lone.special = fallen.special = None
g.players[0].score = g.players[1].score = 0
g.mode = "versus"
g.players = [tanks.Player(i, pid) for i, pid in enumerate(fake)]

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


# ---- bosses: every third wave, in order, ranged attacks only along rows and columns
g.to_lobby()
g.mode = "coop"
g.players = g.players[:2]
g.start_match()
g.state = "play"
for wave, kind in ((3, "knight"), (6, "spider"), (9, "snake"), (12, "witch"), (15, "knight")):
    g.wave = wave - 1
    g.bosses, g.ghouls = [], []
    g.start_wave()
    assert g.boss_pending and g.boss_pending[0] == kind and g.wave_to_spawn == wave, (wave, g.boss_pending)
assert g.boss_pending[1] == tanks.BOSS_HP + tanks.BOSS_HP_GROWTH, "the second knight is tougher"
g.wave, g.boss_pending = 1, None
g.start_wave()
assert g.boss_pending is None, "no boss on wave 2"


def open_field():
    """An empty arena with the two tanks parked out of the way, for testing one boss at a time."""
    g.arena.grid = [[tanks.STEEL if r in (0, tanks.ROWS - 1) or c in (0, tanks.COLS - 1) else tanks.EMPTY
                     for c in range(tanks.COLS)] for r in range(tanks.ROWS)]
    g.arena.brick_hp = {}
    g.arena.ground = None
    g.flow = None
    g.ghouls, g.bosses, g.boss_shots, g.pickups = [], [], [], []
    g.webs.clear()
    g.boss_pending, g.wave_to_spawn, g.wave_break = None, 0, 0
    for p in g.players:
        p.tank = g.make_tank(p)
        p.tank.invuln = 0
    a, b = g.players[0].tank, g.players[1].tank
    b.alive = False
    return a


def make_boss(kind, x, y):
    bs = tanks.Boss(kind, x, y, tanks.BOSS_HP)
    bs.emerge = 0
    g.bosses.append(bs)
    return bs


a = open_field()
a.x, a.y = tanks.tile_center(8, 8)
bs = make_boss("knight", *tanks.tile_center(20, 4))
assert g.boss_aim(bs, [a]) is None, "never thrown diagonally"
bs.x, bs.y = tanks.tile_center(20, 8)
aim = g.boss_aim(bs, [a])
assert aim and aim[0] == -1 and aim[1] == 0, aim

# each boss throws along its row: the shot stays on that row and hurts the tank
for kind in tanks.BOSS_KINDS:
    a = open_field()
    a.x, a.y = tanks.tile_center(6, 8)
    a.hp = a.max_hp = tanks.COOP_TANK_HP
    bs = make_boss(kind, *tanks.tile_center(16, 8))
    bs.cool = 0
    ys, hit_at = set(), None
    for i in range(400):
        a.x, a.y = tanks.tile_center(6, 8)   # parked
        a.invuln = min(a.invuln, 0.5)
        bs.x, bs.y = tanks.tile_center(16, 8)
        g.update_bosses(1 / 60)
        g.update_boss_shots(1 / 60)
        for sh in g.boss_shots:
            if sh.kind != "cat":
                ys.add(round(sh.y))
        if a.hp < a.max_hp and hit_at is None:
            hit_at = i
        g.draw()
    assert hit_at is not None, f"the {kind}'s ranged attack never hit"
    assert len(ys) <= 1, f"the {kind}'s shot left its row: {ys}"
    if kind == "knight":
        assert bs.armed or any(sh.kind == "sword" for sh in g.boss_shots), "the sword must come back"
    if kind == "spider":
        assert g.webs, "web balls leave webs"

# the knight gets his sword back after it returns
a = open_field()
a.x, a.y = tanks.tile_center(6, 8)
bs = make_boss("knight", *tanks.tile_center(16, 8))
bs.aim = (-1, 0, 400)
g.boss_throw(bs)
assert not bs.armed
for _ in range(400):
    g.update_boss_shots(1 / 60)
assert bs.armed and not g.boss_shots

# the spider leaves webs behind, and webs slow tanks
a = open_field()
a.x, a.y = tanks.tile_center(4, 4)
bs = make_boss("spider", *tanks.tile_center(25, 12))
for _ in range(240):
    a.x, a.y = tanks.tile_center(4, 4)
    g.update_bosses(1 / 60)
assert len(g.webs) >= 4, "the spider should web the tiles she walks over"
web = next(iter(g.webs))
g.state = "play"
pad = g.pads[a.player.pad_id]


def drive(x, y):
    a.x, a.y, a.angle = x, y, 0.0
    pad.move, pad.aim, pad.held, pad.pressed = (1.0, 0.0), None, set(), set()
    g.update_tanks(0.1)
    return a.x - x


free = drive(*tanks.tile_center(4, 4))
on_web = drive(*tanks.tile_center(*web))
assert on_web < free * 0.6, (on_web, free)
pad.move = (0, 0)

# the snake is long, and shooting its body hurts it
a = open_field()
a.x, a.y = tanks.tile_center(3, 3)
bs = make_boss("snake", *tanks.tile_center(28, 13))
for _ in range(300):
    a.x, a.y = tanks.tile_center(3, 3)
    g.update_bosses(1 / 60)
assert len(bs.segs) == tanks.SNAKE_SEGMENTS
assert math.dist(bs.segs[0], bs.segs[-1]) > 100, "the snake should stretch out behind its head"
tail = bs.segs[-2]
hp = bs.hp
g.bullets = [tanks.Bullet(a, tail[0] - 12, tail[1], 0)]
g.update_bullets(1 / 60)
assert bs.hp == hp - 1, "a shot to the body should hurt the snake"

# the witch's cats fly over walls and blow up next to the tank
a = open_field()
for c in range(8, 14):
    g.arena.grid[8][c] = tanks.STEEL
a.x, a.y = tanks.tile_center(5, 8)
bs = make_boss("witch", *tanks.tile_center(16, 8))
bs.aim = g.boss_aim(bs, [a])
assert bs.aim, "the witch throws over walls"
g.boss_throw(bs)
hp = a.hp
for _ in range(240):
    g.update_boss_shots(1 / 60)
assert a.hp == hp - 1 and not g.boss_shots

# killing the boss clears the wave, and a cleared wave repairs the tanks
a = open_field()
a.hp = 1
bs = make_boss("knight", *tanks.tile_center(20, 8))
for _ in range(bs.max_hp):
    g.hit_boss(bs, a.player, bs.x, bs.y)
assert bs.dead and not g.bosses and len(g.pickups) == 3
g.update_waves(1 / 60)
assert a.hp == a.max_hp, "every cleared wave repairs the tanks"

# losing to a boss shows its portrait with a taunt; losing to plain ghouls doesn't
for kind in tanks.BOSS_KINDS + (None,):
    a = open_field()
    if kind:
        make_boss(kind, *tanks.tile_center(20, 8))
    a.alive = False
    g.state, g.ending, g.taunt = "play", None, None
    for _ in range(120):
        g.update(1 / 60)
    assert g.state == "coopover" and bool(g.taunt) == bool(kind), kind
    g.draw()
g.state = "play"
print("bosses ok")

# ---- race: 6 bots follow the centerline and shoot whoever is close
g.to_lobby()
g.mode = "race"
g.players = [tanks.Player(i, pid) for i, pid in enumerate(fake)]
for _ in range(10):   # every track needs ramps and room for the whole grid
    g.new_round()
    assert g.track.ramps and len(g.spectators) > 20
    for p in g.players:
        assert g.track.onroad(p.tank.x, p.tank.y), "grid slot off the road"
g.start_match()
max_z = max_slide = 0.0
splats_before = 0
t0, frames = time.time(), 0
for i in range(60 * 120):
    tr = g.track
    for p in g.players:
        t, pad = p.tank, g.pads[p.pad_id]
        tx, ty = tr.pts[(t.seg + 9) % tr.n]
        d = math.hypot(tx - t.x, ty - t.y) or 1
        pad.move, pad.pressed, pad.held = ((tx - t.x) / d, (ty - t.y) / d), set(), set()
        o = min((q.tank for q in g.players if q.tank is not t), key=lambda o: (o.x - t.x) ** 2 + (o.y - t.y) ** 2)
        pad.aim = math.atan2(o.y - t.y, o.x - t.x)
        if math.hypot(o.x - t.x, o.y - t.y) < 150 and random.random() < 0.05:
            pad.held = {"fire"}
    g.update(1 / 60)
    g.draw()
    frames += 1
    for p in g.players:
        t = p.tank
        max_z = max(max_z, t.z)
        max_slide = max(max_slide, abs(-t.vx * math.sin(t.angle) + t.vy * math.cos(t.angle)))
        assert 0 <= t.ammo <= tanks.MAX_AMMO and t.hp == tanks.TANK_HP, "race shells must not damage"
    if shots and i == 600:
        pygame.image.save(g.screen, os.path.join(shots, "race.png"))
    if g.state == "roundover":
        break
fps = frames / (time.time() - t0)
splats = sum(p.kills for p in g.players)
print(f"race: frames={frames} fps={fps:.0f} winner={g.round_winner and g.round_winner.cname} time={g.race_time:.1f}s "
      f"max height={max_z:.0f} max slide={max_slide:.0f} splats={splats}")
assert g.state == "roundover" and g.round_winner and g.round_winner.tank.lap >= tanks.RACE_LAPS
assert max_z > 15, "nobody jumped"
assert max_slide > 40, "tanks never drifted"

# a shell only bumps: it pushes the target, no damage
g.new_round()
g.state = "play"
a, b = g.players[0].tank, g.players[1].tank
a.vx = a.vy = 0.0
shell = tanks.Bullet(b, a.x - 5, a.y, 0)
g.bump_tank(a, shell)
assert a.vx > 200 and a.hp == tanks.TANK_HP

# touching or shooting a spectator splatters it into limbs
gh = g.spectators[0]
b.x, b.y, b.z, b.vx, b.vy = gh.x, gh.y, 0.0, 100.0, 0.0
n_before, kills_before = len(g.spectators), b.player.kills
g.update_spectators(1 / 60)
assert gh not in g.spectators and len(g.spectators) == n_before - 1 and b.player.kills == kills_before + 1
assert g.gibs, "no limbs flew"
gh = g.spectators[0]
g.bullets = [tanks.Bullet(a, gh.x - 10, gh.y, 0)]
g.update_race_bullets(1 / 60)
assert gh not in g.spectators and not g.bullets
for _ in range(200):
    g.update_gibs(1 / 60)
assert not g.gibs, "limbs should land and stay as decals"


# the Ghost Rider lashes whoever tails him, dies to one shell and rides again 3 s later
g.new_round()
g.state = "play"
r = g.rider
g.update_rider(1 / 60)
a = g.players[0].tank
a.x, a.y = r.x - math.cos(r.ang) * 60, r.y - math.sin(r.ang) * 60
a.vx, a.vy, a.invuln, a.z = math.cos(r.ang) * 300, math.sin(r.ang) * 300, 0, 0.0
r.cool = 0
g.update_rider(1 / 60)
assert r.whip and math.hypot(a.vx, a.vy) < 120, "tailing the rider should get you lashed"
g.bullets = [tanks.Bullet(a, r.x - 15 * math.cos(r.ang), r.y - 15 * math.sin(r.ang), r.ang)]
g.update_race_bullets(1 / 60)
assert r.dead > 0 and not g.bullets
for _ in range(int(tanks.RIDER_RESPAWN * 60) + 2):
    g.update_rider(1 / 60)
assert r.dead <= 0, "the rider comes back"
ammo = a.ammo
a.cooldown = 0
g.fire(a)
assert a.ammo == ammo, "race shells are unlimited"
print("ghost rider ok")

# ---- math break: valid questions, appears only at a break, answerable with a pad
for _ in range(5000):
    text, ans, unit = tanks.make_question()
    assert isinstance(ans, int) and 0 <= ans < 10 ** tanks.QUIZ_DIGITS, (text, ans)
    assert len(g.wrap(text, g.font_med, 900)) <= 3, text
g.state, g.ending = "play", None
g.quiz_clock = tanks.QUIZ_INTERVAL + 1
g.update(1 / 60)
assert g.quiz is None, "the math break must not interrupt a race in progress"
g.state = "roundover"
g.update(1 / 60)
assert g.quiz is not None
q = g.quiz
pad = g.pads[fake[0]]


def press(*names):
    pad.pressed = set(names)
    g.update(1 / 60)
    pad.pressed = set()


timer = g.timer
press("a")   # 00000 is never the answer to these questions... unless it is
if q.answer != 0:
    assert g.quiz and q.tries == 1 and g.timer == timer, "a wrong answer keeps the game frozen"
for i, d in enumerate(f"{q.answer:0{tanks.QUIZ_DIGITS}d}"):   # dial the answer in with the stick
    while q.cursor > i:
        press("left")
    while q.cursor < i:
        press("right")
    while q.digits[i] != int(d):
        press("up")
press("a")
assert q.solved > 0
g.draw()
if shots:
    pygame.image.save(g.screen, os.path.join(shots, "quiz.png"))
for _ in range(120):
    g.update(1 / 60)
assert g.quiz is None and g.quiz_clock == 0, "solving resets the 5 minute clock"

# ---- browser drawing path: bushes baked into the ground still hide what's under them, decals included
g.to_lobby()
g.mode = "versus"
g.start_match()
g.arena.sway = False
g.arena.ground = None
bushes = [(c, r) for r in range(tanks.ROWS) for c in range(tanks.COLS) if g.arena.grid[r][c] == tanks.BUSH]
assert bushes, "this map has no bushes to test"
cx, cy = tanks.tile_center(*bushes[0])
g.draw()
bare = g.world.get_at((int(cx), int(cy)))
t = g.players[0].tank
t.x, t.y, t.invuln = cx, cy, 0
g.arena.decal(g.arena.scorch[34], cx, cy)
g.draw()
hidden = g.world.get_at((int(cx), int(cy)))
assert max(abs(a - b) for a, b in zip(hidden[:3], bare[:3])) < 24, "a tank or decal shows through a baked bush"
g.arena.sway = True
g.arena.ground = None
print("browser drawing path ok")


# ---- raw joystick layouts: Linux xpad and the browser's standard gamepad
class FakeJoy:
    def __init__(self, axes, buttons, hats=0):
        self.axes, self.buttons, self.hats = axes, buttons, hats

    def get_numaxes(self):
        return len(self.axes)

    def get_numbuttons(self):
        return len(self.buttons)

    def get_numhats(self):
        return self.hats

    def get_hat(self, i):
        return (0, 0)

    def get_axis(self, i):
        return self.axes[i]

    def get_button(self, i):
        return self.buttons[i]


saved = tanks.JOY_LAYOUT
tanks.JOY_LAYOUT = tanks.WEB_LAYOUT
web = FakeJoy([0.0, 0.0, 0.0, -1.0], [0] * 17)   # right stick pushed up
pad = tanks.Pad("web", "joy", web)
pad.poll(None)
assert pad.aim is not None and abs(pad.aim + math.pi / 2) < 0.01, "browser right stick must aim the turret"
assert not pad.held, "a resting browser pad presses nothing"
web.buttons[6] = 1   # LT
web.buttons[13] = 1  # D-pad down
pad.poll(None)
assert "fire2" in pad.held and pad.move[1] > 0.9, "browser LT is the special, D-pad drives"
tanks.JOY_LAYOUT = tanks.XPAD_LAYOUT
xpad = FakeJoy([0.0, 0.0, -1.0, 1.0, 0.0, -1.0], [0] * 11, hats=1)   # right stick pushed right, triggers at rest
pad = tanks.Pad("xpad", "joy", xpad)
pad.poll(None)
assert pad.aim is not None and abs(pad.aim) < 0.01 and not pad.held
xpad.axes[2] = 1.0   # LT
pad.poll(None)
assert "fire2" in pad.held
tanks.JOY_LAYOUT = saved
print("joystick layouts ok")
print("OK")
