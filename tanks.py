#!/usr/bin/env python3
# Public domain (The Unlicense, see LICENSE): do whatever you want with this.
"""Tank Arena - local multiplayer top-down tank shooter (Linux, Xbox controllers).

Left stick: drive   Right stick: aim turret   RT / RB / A: fire
START: begin match / pause   B: leave lobby   BACK (in pause): quit to lobby
Keyboard (two players): P1 WASD + Q/E turret + SPACE fire + X leave, P2 arrows + ,/. turret + RCTRL fire + DELETE leave
ENTER starts / pauses. Up to 6 players in total.
F11 toggles fullscreen, ESC returns to lobby / quits.
"""
import math
import random
import sys
from array import array

import pygame

try:
    from pygame._sdl2 import controller as sdl_ctrl
except Exception:  # very old pygame / missing SDL2 GameController support
    sdl_ctrl = None

W, H = 1280, 720
T = 40                      # tile size
COLS, ROWS = 32, 17
HUD = 40                    # height of the top status bar
FPS = 120

EMPTY, BRICK, STEEL, WATER, BUSH = range(5)
TANK_SOLID = (BRICK, STEEL, WATER)
BULLET_SOLID = (BRICK, STEEL)

TANK_R = 15
TANK_SPEED = 150
TURN_SPEED = 7.0
TURRET_SPEED = 14.0
KB_TURRET_SPEED = 3.5
BULLET_SPEED = 480
BULLET_R = 4
BULLET_LIFE = 4.0
BULLET_BOUNCES = 1
FIRE_COOLDOWN = 0.35
MAX_BULLETS = 4
TANK_HP = 3
BRICK_HP = 2
WIN_SCORE = 5
MAX_AMMO = 10
CRATE_LIFE = 7.0
CRATE_RESPAWN = 10.0
CRATE_R = 15
DEADZONE = 0.25
MAX_PLAYERS = 6

PLAYER_COLORS = [
    ((90, 200, 90), "GREEN"),
    ((70, 140, 240), "BLUE"),
    ((240, 150, 40), "ORANGE"),
    ((220, 80, 200), "PINK"),
    ((225, 65, 60), "RED"),
    ((230, 210, 60), "YELLOW"),
]
CORNER_SPAWNS = [(2, 2), (COLS - 3, ROWS - 3), (COLS - 3, 2), (2, ROWS - 3)]
SIDE_SPAWNS = [(2, ROWS // 2), (COLS - 3, ROWS // 2)]   # used only with 5-6 players
SPAWNS = CORNER_SPAWNS + SIDE_SPAWNS

KB_MAPS = {
    'kb1': dict(up=pygame.K_w, down=pygame.K_s, left=pygame.K_a, right=pygame.K_d,
                ccw=pygame.K_q, cw=pygame.K_e, fire=pygame.K_SPACE, leave=pygame.K_x),
    'kb2': dict(up=pygame.K_UP, down=pygame.K_DOWN, left=pygame.K_LEFT, right=pygame.K_RIGHT,
                ccw=pygame.K_COMMA, cw=pygame.K_PERIOD, fire=pygame.K_RCTRL, leave=pygame.K_DELETE),
}
FLOOR = (58, 60, 52)



# ---------------------------------------------------------------- helpers

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp_color(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def angle_diff(a, b):
    return (b - a + math.pi) % (2 * math.pi) - math.pi


def approach_angle(a, target, step):
    d = angle_diff(a, target)
    if abs(d) <= step:
        return target
    return a + math.copysign(step, d)


def apply_deadzone(x, y, dz=DEADZONE):
    m = math.hypot(x, y)
    if m < dz:
        return 0.0, 0.0
    s = min(1.0, (m - dz) / (1 - dz)) / m
    return x * s, y * s


def blit_center(dst, surf, x, y):
    dst.blit(surf, surf.get_rect(center=(round(x), round(y))))


def tile_center(c, r):
    return c * T + T / 2, HUD + r * T + T / 2


_glow_cache = {}


def add_glow(dst, color, x, y, radius):
    """Additive radial light. Sprites are cached per (color, radius)."""
    radius = max(2, int(radius))
    key = (color, radius)
    s = _glow_cache.get(key)
    if s is None:
        s = pygame.Surface((radius * 2, radius * 2))
        for i in range(radius, 0, -1):
            k = (1 - i / radius) ** 2
            pygame.draw.circle(s, (int(color[0] * k), int(color[1] * k), int(color[2] * k)), (radius, radius), i)
        s = s.convert()
        _glow_cache[key] = s
    dst.blit(s, (x - radius, y - radius), special_flags=pygame.BLEND_RGB_ADD)


def make_vignette():
    v = pygame.Surface((64, 36), pygame.SRCALPHA)
    for y in range(36):
        for x in range(64):
            d = math.hypot((x - 31.5) / 32, (y - 17.5) / 18)
            v.set_at((x, y), (0, 0, 0, int(clamp((d - 0.55) / 0.65, 0, 1) ** 1.5 * 160)))
    return pygame.transform.smoothscale(v, (W, H - HUD)).convert_alpha()


# ---------------------------------------------------------------- sound

class Sounds:
    """Tiny procedural sound bank, so the game needs no asset files."""

    def __init__(self):
        self.snd = {}
        init = pygame.mixer.get_init()
        if not init or init[1] != -16:
            return
        self.freq, _, self.ch = init
        tau = 2 * math.pi
        e = math.exp

        def lp_noise(alpha):
            st = [0.0]

            def f():
                st[0] += alpha * (random.uniform(-1, 1) - st[0])
                return st[0]
            return f

        n1, n2, n3 = lp_noise(0.35), lp_noise(0.5), lp_noise(0.06)
        self.snd['shot'] = self.make(0.22, lambda t: n1() * 1.6 * e(-t * 22) + math.sin(tau * 120 * t) * e(-t * 18) * 0.8)
        self.snd['bounce'] = self.make(0.12, lambda t: math.sin(tau * (1300 - 2500 * t) * t) * e(-t * 35), 0.3)
        self.snd['brick'] = self.make(0.2, lambda t: n2() * 1.5 * e(-t * 20), 0.45)
        self.snd['hit'] = self.make(0.22, lambda t: (1 if math.sin(tau * (240 - 300 * t) * t) > 0 else -1) * 0.5 * e(-t * 12), 0.35)
        self.snd['explode'] = self.make(1.1, lambda t: n3() * 5 * e(-t * 3.2), 0.7)
        self.snd['beep'] = self.make(0.15, lambda t: math.sin(tau * 660 * t) * e(-t * 12), 0.35)
        self.snd['go'] = self.make(0.4, lambda t: math.sin(tau * 990 * t) * e(-t * 6), 0.35)
        self.snd['join'] = self.make(0.2, lambda t: math.sin(tau * (523 if t < 0.08 else 784) * t) * e(-t * 8), 0.35)
        arp = (523, 659, 784, 1047)
        self.snd['pickup'] = self.make(0.3, lambda t: math.sin(tau * arp[min(3, int(t / 0.05))] * t) * e(-t * 5), 0.35)
        self.snd['empty'] = self.make(0.05, lambda t: n2() * e(-t * 90), 0.5)
        self.snd['crate'] = self.make(0.6, lambda t: (math.sin(tau * 880 * t) + 0.5 * math.sin(tau * 1320 * t)) * e(-t * 6), 0.2)

    def make(self, dur, fn, vol=0.5):
        buf = array('h')
        for i in range(int(self.freq * dur)):
            s = int(clamp(fn(i / self.freq), -1, 1) * 32767 * vol)
            buf.extend((s,) * self.ch)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, name):
        s = self.snd.get(name)
        if s:
            s.play()


# ---------------------------------------------------------------- input

class Pad:
    """One input device: SDL game controller, raw joystick, or a keyboard half."""

    LABELS = {'ctrl': "Controller", 'joy': "Gamepad", 'kb1': "Keyboard WASD", 'kb2': "Keyboard Arrows"}

    def __init__(self, pid, kind, dev=None):
        self.pid, self.kind, self.dev = pid, kind, dev
        self.label = self.LABELS[kind]
        self.held, self.pressed = set(), set()
        self.move = (0.0, 0.0)
        self.aim = None
        self.turret_rot = 0.0

    def poll(self, keys):
        held = set()
        mx = my = rot = 0.0
        aim = None
        if self.kind == 'ctrl':
            d = self.dev
            ax = lambda a: d.get_axis(a) / 32767.0
            bt = d.get_button
            mx, my = ax(pygame.CONTROLLER_AXIS_LEFTX), ax(pygame.CONTROLLER_AXIS_LEFTY)
            rx, ry = ax(pygame.CONTROLLER_AXIS_RIGHTX), ax(pygame.CONTROLLER_AXIS_RIGHTY)
            dx = bt(pygame.CONTROLLER_BUTTON_DPAD_RIGHT) - bt(pygame.CONTROLLER_BUTTON_DPAD_LEFT)
            dy = bt(pygame.CONTROLLER_BUTTON_DPAD_DOWN) - bt(pygame.CONTROLLER_BUTTON_DPAD_UP)
            if dx or dy:
                mx, my = dx, dy
            if math.hypot(rx, ry) > 0.5:
                aim = math.atan2(ry, rx)
            if (ax(pygame.CONTROLLER_AXIS_TRIGGERRIGHT) > 0.35 or bt(pygame.CONTROLLER_BUTTON_RIGHTSHOULDER)
                    or bt(pygame.CONTROLLER_BUTTON_A)):
                held.add('fire')
            for name, b in (('a', pygame.CONTROLLER_BUTTON_A), ('b', pygame.CONTROLLER_BUTTON_B),
                            ('start', pygame.CONTROLLER_BUTTON_START), ('back', pygame.CONTROLLER_BUTTON_BACK)):
                if bt(b):
                    held.add(name)
        elif self.kind == 'joy':
            # Fallback for pads SDL has no mapping for; assumes the Linux xpad layout.
            j = self.dev
            na, nb = j.get_numaxes(), j.get_numbuttons()
            ax = lambda i: j.get_axis(i) if i < na else 0.0
            bt = lambda i: j.get_button(i) if i < nb else 0
            mx, my = ax(0), ax(1)
            rx, ry = ax(3), ax(4)
            if j.get_numhats():
                hx, hy = j.get_hat(0)
                if hx or hy:
                    mx, my = hx, -hy
            if math.hypot(rx, ry) > 0.5:
                aim = math.atan2(ry, rx)
            if (na > 5 and ax(5) > 0.0) or bt(5) or bt(0):
                held.add('fire')
            for name, b in (('a', 0), ('b', 1), ('start', 7), ('back', 6)):
                if bt(b):
                    held.add(name)
        else:
            k = KB_MAPS[self.kind]
            mx = keys[k['right']] - keys[k['left']]
            my = keys[k['down']] - keys[k['up']]
            rot = keys[k['cw']] - keys[k['ccw']]
            if keys[k['fire']]:
                held |= {'fire', 'a'}
            if keys[k['leave']]:
                held |= {'b', 'back'}
            if keys[pygame.K_RETURN] or keys[pygame.K_KP_ENTER]:
                held.add('start')
        self.move = apply_deadzone(mx, my)
        self.aim = aim
        self.turret_rot = rot
        self.pressed = held - self.held
        self.held = held

    def rumble(self, low, high, ms):
        if self.kind in ('ctrl', 'joy'):
            try:
                self.dev.rumble(low, high, ms)
            except Exception:
                pass


# ---------------------------------------------------------------- graphics

SS = 3   # sprites are drawn at 3x and smooth-scaled down for antialiased edges


def make_tank_sprites(color):
    dark = tuple(int(c * 0.5) for c in color)
    shade = tuple(int(c * 0.75) for c in color)
    light = tuple(min(255, int(c * 1.2) + 35) for c in color)
    S = SS

    def R(x, y, w, h):
        return (x * S, y * S, w * S, h * S)

    def body_frame(phase):
        b = pygame.Surface((40 * S, 40 * S), pygame.SRCALPHA)
        for ty in (2, 29):
            pygame.draw.rect(b, (28, 28, 32), R(1, ty, 38, 9), border_radius=3 * S)
            for x in range(-4, 44, 4):
                xx = x - phase
                if 2 <= xx <= 37:
                    pygame.draw.rect(b, (78, 78, 84), R(xx, ty + 1, 1.5, 7))
            pygame.draw.rect(b, (60, 60, 66), R(1, ty, 38, 9), S, border_radius=3 * S)
            for wx in (6, 14, 22, 30):   # road wheels peeking through
                pygame.draw.circle(b, (50, 50, 56), (wx * S + S, (ty + 4.5) * S), 2 * S)
        pygame.draw.rect(b, dark, R(4, 7, 32, 26), border_radius=5 * S)
        pygame.draw.rect(b, color, R(5, 8, 30, 24), border_radius=5 * S)
        pygame.draw.rect(b, light, R(6, 9, 28, 4), border_radius=3 * S)
        pygame.draw.rect(b, shade, R(6, 27, 28, 4), border_radius=3 * S)
        for i in range(4):   # engine grille at the back
            pygame.draw.rect(b, dark, R(8 + i * 2.5, 14, 1.2, 12))
        pygame.draw.rect(b, light, R(31, 11, 3, 18), border_radius=S)
        pygame.draw.circle(b, (255, 245, 200), (33 * S, 12 * S), S)   # headlights
        pygame.draw.circle(b, (255, 245, 200), (33 * S, 28 * S), S)
        return pygame.transform.smoothscale(b, (40, 40)).convert_alpha()

    turret = pygame.Surface((60 * S, 60 * S), pygame.SRCALPHA)
    c = 30 * S
    pygame.draw.rect(turret, dark, (c, c - 3 * S, 22 * S, 6 * S), border_radius=S)
    pygame.draw.rect(turret, shade, (c, c - 2 * S, 21 * S, 2 * S))
    pygame.draw.rect(turret, (40, 40, 46), (c + 19 * S, c - 4 * S, 6 * S, 8 * S), border_radius=S)
    pygame.draw.circle(turret, dark, (c, c), 11 * S)
    pygame.draw.circle(turret, color, (c, c), 9.5 * S)
    pygame.draw.circle(turret, light, (c - 2 * S, c - 2 * S), 5 * S)
    pygame.draw.circle(turret, color, (c - S, c - S), 4.5 * S)
    pygame.draw.circle(turret, dark, (c - 3 * S, c + 3 * S), 2.5 * S)   # hatch
    turret = pygame.transform.smoothscale(turret, (60, 60)).convert_alpha()

    def tinted(src, rgba, flag):
        s = src.copy()
        s.fill(rgba, special_flags=flag)
        return s

    bodies = [body_frame(p) for p in range(4)]
    body = bodies[0]
    return {
        'bodies': bodies,
        'body': body,
        'turret': turret,
        'shadow': tinted(body, (0, 0, 0, 90), pygame.BLEND_RGBA_MIN),
        'body_white': tinted(body, (255, 255, 255, 0), pygame.BLEND_RGBA_MAX),
        'turret_white': tinted(turret, (255, 255, 255, 0), pygame.BLEND_RGBA_MAX),
        'wreck': tinted(body, (70, 62, 55, 255), pygame.BLEND_RGBA_MULT),
        'wreck_turret': tinted(turret, (70, 62, 55, 255), pygame.BLEND_RGBA_MULT),
    }


def make_crate_sprite():
    S = SS
    s = pygame.Surface((30 * S, 30 * S), pygame.SRCALPHA)
    pygame.draw.rect(s, (80, 50, 25), (0, 0, 30 * S, 30 * S), border_radius=3 * S)
    pygame.draw.rect(s, (160, 112, 60), (2 * S, 2 * S, 26 * S, 26 * S), border_radius=2 * S)
    for y in (10, 19):
        pygame.draw.rect(s, (120, 80, 40), (2 * S, y * S, 26 * S, S))
    pygame.draw.rect(s, (200, 155, 95), (2 * S, 2 * S, 26 * S, S))
    for x, y in ((4, 4), (25, 4), (4, 25), (25, 25)):
        pygame.draw.circle(s, (70, 70, 75), (x * S + S // 2, y * S + S // 2), S)
    for i in (-1, 0, 1):   # three shells
        x = 15 * S + i * 6 * S
        pygame.draw.rect(s, (60, 40, 20), (x - 2.5 * S, 9 * S, 5 * S, 14 * S), border_radius=2 * S)
        pygame.draw.rect(s, (230, 185, 70), (x - 2 * S, 12 * S, 4 * S, 10 * S))
        pygame.draw.circle(s, (205, 110, 60), (x, 12 * S), 2 * S)
        pygame.draw.rect(s, (255, 230, 140), (x - 1.5 * S, 13 * S, S, 8 * S))
    return pygame.transform.smoothscale(s, (30, 30)).convert_alpha()


def make_brick_tile(cracked):
    s = pygame.Surface((T, T))
    s.fill((85, 45, 32))
    for row in range(4):
        y = row * 10
        off = 0 if row % 2 == 0 else 10
        for x in range(-20 + off, T, 20):
            r = pygame.Rect(x + 1, y + 1, 18, 8).clip(s.get_rect())
            sh = random.randint(-14, 14)
            s.fill((165 + sh, 80 + sh // 2, 52), r)
            s.fill((195 + sh // 2, 110, 75), (r.x, r.y, r.w, 1))
            s.fill((125 + sh, 58, 38), (r.x, r.bottom - 1, r.w, 1))
    pygame.draw.rect(s, (60, 32, 22), (0, 0, T, T), 1)
    if cracked:
        dark = pygame.Surface((T, T), pygame.SRCALPHA)
        dark.fill((0, 0, 0, 70))
        s.blit(dark, (0, 0))
        for _ in range(3):
            x, y = random.randint(5, 35), random.randint(5, 35)
            pts = [(x, y)]
            for _ in range(3):
                x += random.randint(-8, 8)
                y += random.randint(-8, 8)
                pts.append((clamp(x, 0, T - 1), clamp(y, 0, T - 1)))
            pygame.draw.lines(s, (40, 20, 15), False, pts, 2)
    return s.convert()


def make_steel_tile():
    s = pygame.Surface((T, T))
    s.fill((70, 74, 82))
    pygame.draw.rect(s, (135, 140, 150), (2, 2, T - 4, T - 4))
    pygame.draw.line(s, (195, 200, 210), (2, 2), (T - 3, 2), 2)
    pygame.draw.line(s, (195, 200, 210), (2, 2), (2, T - 3), 2)
    pygame.draw.line(s, (90, 94, 102), (2, T - 3), (T - 3, T - 3), 2)
    pygame.draw.line(s, (90, 94, 102), (T - 3, 2), (T - 3, T - 3), 2)
    pygame.draw.rect(s, (120, 125, 135), (10, 10, T - 20, T - 20))
    for x, y in ((7, 7), (T - 8, 7), (7, T - 8), (T - 8, T - 8)):
        pygame.draw.circle(s, (80, 84, 92), (x, y), 2)
    return s.convert()


def make_bush_tile(seed):
    rnd = random.Random(seed)
    s = pygame.Surface((T + 12, T + 12), pygame.SRCALPHA)
    for _ in range(14):
        col = rnd.choice([(40, 110, 45), (55, 135, 55), (35, 95, 40), (70, 150, 60)])
        pygame.draw.circle(s, col + (240,), (rnd.randint(10, T + 2), rnd.randint(10, T + 2)), rnd.randint(7, 11))
    return s.convert_alpha()


# ---------------------------------------------------------------- arena

class Arena:
    def __init__(self):
        self.brick_tiles = [make_brick_tile(True), make_brick_tile(False)]
        self.steel_tile = make_steel_tile()
        self.bush_tiles = [make_bush_tile(i) for i in range(3)]
        self.tread_dot = pygame.Surface((4, 4), pygame.SRCALPHA)
        self.tread_dot.fill((25, 25, 20, 45))
        self.shadow = pygame.Surface((T, T), pygame.SRCALPHA)
        self.shadow.fill((0, 0, 0, 85))
        self.vignette = make_vignette()
        self.ground = None
        self.scorch = {}
        for rad in (10, 34):
            s = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
            for i in range(rad, 0, -1):
                pygame.draw.circle(s, (15, 12, 10, int(150 * (1 - i / rad) ** 0.7)), (rad, rad), i)
            self.scorch[rad] = s
        self.generate()

    def generate(self):
        hc, hr = COLS // 2, ROWS // 2
        for _ in range(500):
            g = [[EMPTY] * COLS for _ in range(ROWS)]

            def fill(c0, r0, w, h, v):
                for r in range(r0, r0 + h):
                    for c in range(c0, c0 + w):
                        if 1 <= c < hc and 1 <= r <= hr:
                            g[r][c] = v

            for _ in range(random.randint(7, 11)):
                kind = random.choices(['brick', 'steel', 'water', 'bush', 'lwall'], [5, 3, 1.2, 1.5, 2])[0]
                c, r = random.randint(1, hc - 1), random.randint(1, hr)
                if kind == 'brick':
                    fill(c, r, random.randint(1, 3), random.randint(1, 3), BRICK)
                elif kind == 'steel':
                    fill(c, r, *random.choice([(1, 1), (2, 1), (1, 2)]), STEEL)
                elif kind == 'water':
                    fill(c, r, random.randint(2, 3), random.randint(1, 2), WATER)
                elif kind == 'bush':
                    fill(c, r, random.randint(2, 3), random.randint(2, 3), BUSH)
                else:
                    fill(c, r, random.randint(3, 4), 1, BRICK)
                    fill(c, r, 1, random.randint(2, 3), BRICK)

            # mirror the top-left quadrant into a 4-way symmetric arena
            for r in range(hr + 1):
                for c in range(hc):
                    v = g[r][c]
                    g[r][COLS - 1 - c] = g[ROWS - 1 - r][c] = g[ROWS - 1 - r][COLS - 1 - c] = v
            for c in range(COLS):
                g[0][c] = g[ROWS - 1][c] = STEEL
            for r in range(ROWS):
                g[r][0] = g[r][COLS - 1] = STEEL
            for sc, sr in SPAWNS:
                for r in range(sr - 1, sr + 2):
                    for c in range(sc - 1, sc + 2):
                        g[r][c] = EMPTY

            if self.connected(g):
                break
        self.grid = g
        self.brick_hp = {(c, r): BRICK_HP for r in range(ROWS) for c in range(COLS) if g[r][c] == BRICK}
        self.render_static()

    @staticmethod
    def connected(g):
        """All spawns reachable (bricks count as passable, they can be shot) and enough open floor."""
        start = SPAWNS[0]
        seen = {start}
        stack = [start]
        while stack:
            c, r = stack.pop()
            for nc, nr in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
                if (nc, nr) not in seen and g[nr][nc] not in (STEEL, WATER):
                    seen.add((nc, nr))
                    stack.append((nc, nr))
        open_tiles = sum(1 for row in g for v in row if v in (EMPTY, BUSH))
        return all(s in seen for s in SPAWNS) and open_tiles > (COLS - 2) * (ROWS - 2) * 0.6

    def render_static(self):
        s = pygame.Surface((W, H))
        s.fill(FLOOR)
        # concrete slabs, 2x2 tiles each, slightly different shades
        for r in range(0, ROWS, 2):
            for c in range(0, COLS, 2):
                k = random.uniform(-0.06, 0.06)
                col = lerp_color(FLOOR, (0, 0, 0) if k < 0 else (255, 255, 255), abs(k))
                s.fill(col, (c * T + 1, HUD + r * T + 1, 2 * T - 2, 2 * T - 2))
                s.fill(lerp_color(col, (255, 255, 255), 0.06), (c * T + 1, HUD + r * T + 1, 2 * T - 2, 1))
        for _ in range(2500):
            x, y = random.randint(0, W), random.randint(HUD, H)
            sh = random.randint(-14, 8)
            s.fill(lerp_color(FLOOR, (0, 0, 0) if sh < 0 else (255, 255, 255), abs(sh) / 100), (x, y, 2, 2))
        for _ in range(10):   # oil stains
            st = pygame.Surface((90, 60), pygame.SRCALPHA)
            for _ in range(5):
                pygame.draw.ellipse(st, (20, 20, 18, 22), (random.randint(0, 40), random.randint(0, 25), random.randint(30, 50), random.randint(20, 35)))
            s.blit(st, (random.randint(0, W - 90), random.randint(HUD, H - 60)))
        for _ in range(14):   # cracks
            x, y = random.randint(0, W), random.randint(HUD, H)
            pts = [(x, y)]
            for _ in range(random.randint(3, 6)):
                x += random.randint(-14, 14)
                y += random.randint(-14, 14)
                pts.append((x, y))
            pygame.draw.lines(s, lerp_color(FLOOR, (0, 0, 0), 0.25), False, pts, 1)

        g = self.grid
        is_water = lambda c, r: 0 <= c < COLS and 0 <= r < ROWS and g[r][c] == WATER
        for r in range(ROWS):
            for c in range(COLS):
                x, y = c * T, HUD + r * T
                if g[r][c] == WATER:
                    s.fill((70, 66, 52), (x - 3, y - 3, T + 6, T + 6))   # muddy shore
        for r in range(ROWS):
            for c in range(COLS):
                x, y = c * T, HUD + r * T
                v = g[r][c]
                if v == WATER:
                    s.fill((28, 72, 140), (x, y, T, T))
                    if not is_water(c, r - 1):   # darker depth band under the top edge
                        s.fill((22, 58, 115), (x, y, T, 6))
                    if not is_water(c - 1, r):
                        s.fill((22, 58, 115), (x, y, 5, T))
                elif v in (STEEL, BUSH):
                    s.blit(self.shadow, (x + 6, y + 6))
        for r in range(ROWS):
            for c in range(COLS):
                if g[r][c] == STEEL:
                    s.blit(self.steel_tile, (c * T, HUD + r * T))
        self.static = s.convert()
        self.ground = None

    def decal(self, surf, x, y):
        """Permanently paint onto the floor (and the cached ground layer, so no rebuild is needed)."""
        rect = surf.get_rect(center=(round(x), round(y)))
        self.static.blit(surf, rect)
        if self.ground:
            self.ground.blit(surf, rect)

    def scorch_mark(self, x, y, big=False):
        self.decal(self.scorch[34 if big else 10], x, y)

    def tile(self, x, y):
        c, r = int(x // T), int((y - HUD) // T)
        if 0 <= c < COLS and 0 <= r < ROWS:
            return c, r, self.grid[r][c]
        return c, r, STEEL

    def bullet_hit(self, x, y):
        t = self.tile(x, y)
        return t if t[2] in BULLET_SOLID else None

    def collide_circle(self, x, y, rad):
        for _ in range(2):
            for r in range(int((y - rad - HUD) // T), int((y + rad - HUD) // T) + 1):
                for c in range(int((x - rad) // T), int((x + rad) // T) + 1):
                    if 0 <= c < COLS and 0 <= r < ROWS and self.grid[r][c] not in TANK_SOLID:
                        continue
                    rx, ry = c * T, HUD + r * T
                    dx, dy = x - clamp(x, rx, rx + T), y - clamp(y, ry, ry + T)
                    d2 = dx * dx + dy * dy
                    if d2 >= rad * rad:
                        continue
                    if d2 > 1e-9:
                        d = math.sqrt(d2)
                        x += dx / d * (rad - d)
                        y += dy / d * (rad - d)
                    else:  # centre inside the tile: push out along the shortest axis
                        opts = [(rx - rad - x, 0), (rx + T + rad - x, 0), (0, ry - rad - y), (0, ry + T + rad - y)]
                        px, py = min(opts, key=lambda o: abs(o[0]) + abs(o[1]))
                        x, y = x + px, y + py
        return x, y

    def tread_mark(self, x, y, a):
        for side in (-1, 1):
            px = x + math.cos(a + math.pi / 2) * 12 * side
            py = y + math.sin(a + math.pi / 2) * 12 * side
            self.decal(self.tread_dot, px, py)

    def build_ground(self):
        gr = self.static.copy()
        g = self.grid
        for r in range(ROWS):
            for c in range(COLS):
                if g[r][c] == BRICK and g[r][c + 1] != STEEL and g[r + 1][c] != STEEL:
                    gr.blit(self.shadow, (c * T + 6, HUD + r * T + 6))
        for r in range(ROWS):
            for c in range(COLS):
                if g[r][c] == BRICK:
                    gr.blit(self.brick_tiles[self.brick_hp[(c, r)] - 1], (c * T, HUD + r * T))
        gr.blit(self.vignette, (0, HUD))
        self.ground = gr

    def draw_ground(self, dst, now):
        if self.ground is None:
            self.build_ground()
        dst.blit(self.ground, (0, 0))
        g = self.grid
        for r in range(ROWS):
            for c in range(COLS):
                if g[r][c] == WATER:
                    x, y = c * T, HUD + r * T
                    ph = now * 2.2 + (c + r) * 0.9
                    for k in range(2):
                        yy = y + 13 + k * 15 + math.sin(ph + k * 1.7) * 3
                        xo = math.sin(ph * 0.7 + k) * 4
                        pygame.draw.line(dst, (80, 140, 215), (x + 8 + xo, yy), (x + T - 10 + xo, yy), 2)
                    if math.sin(now * 3 + c * 2.3 + r * 1.7) > 0.93:   # glint
                        pygame.draw.circle(dst, (200, 230, 255), (x + 12 + (c * 7) % 16, y + 10 + (r * 5) % 18), 2)

    def draw_bushes(self, dst, now):
        for r in range(ROWS):
            for c in range(COLS):
                if self.grid[r][c] == BUSH:
                    sway = math.sin(now * 1.6 + c * 0.8 + r * 0.5) * 1.2
                    dst.blit(self.bush_tiles[(c * 7 + r * 13) % 3], (c * T - 6 + sway, HUD + r * T - 6))


# ---------------------------------------------------------------- entities

class Player:
    def __init__(self, idx, pad_id):
        self.idx, self.pad_id = idx, pad_id
        self.color, self.cname = PLAYER_COLORS[idx]
        self.sprites = make_tank_sprites(self.color)
        self.score = 0
        self.tank = None


class Tank:
    def __init__(self, player, x, y, angle):
        self.player = player
        self.x, self.y = x, y
        self.angle = self.turret = angle
        self.hp = TANK_HP
        self.alive = True
        self.cooldown = 0.0
        self.flash = 0.0
        self.tread = 0.0
        self.tread_phase = 0.0
        self.recoil = 0.0
        self.smoke = 0.0
        self.ammo = MAX_AMMO


class Bullet:
    def __init__(self, owner, x, y, a):
        self.owner = owner
        self.x, self.y = x, y
        self.vx, self.vy = math.cos(a) * BULLET_SPEED, math.sin(a) * BULLET_SPEED
        self.age = 0.0
        self.bounces = BULLET_BOUNCES
        self.bounced = False
        self.dead = False


# ---------------------------------------------------------------- game

class Game:
    def __init__(self, fullscreen):
        flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else 0)
        self.screen = pygame.display.set_mode((W, H), flags)
        pygame.display.set_caption("Tank Arena")
        pygame.mouse.set_visible(False)
        self.world = pygame.Surface((W, H))
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.Font(None, 120)
        self.font_med = pygame.font.Font(None, 56)
        self.font_small = pygame.font.Font(None, 32)
        self.font_hud = pygame.font.Font(None, 30)
        self.font_tiny = pygame.font.Font(None, 22)
        self.sounds = Sounds()
        self.arena = Arena()
        self.crate_sprite = make_crate_sprite()
        self.crate_shadow = pygame.Surface((30, 30), pygame.SRCALPHA)
        pygame.draw.rect(self.crate_shadow, (0, 0, 0, 90), (0, 0, 30, 30), border_radius=4)
        self.pads = {'kb1': Pad('kb1', 'kb1'), 'kb2': Pad('kb2', 'kb2')}
        self.scan_pads()
        self.players = []
        self.bullets = []
        self.particles = []
        self.rings = []
        self.flashes = []    # [x, y, t, max_t, radius] additive light bursts
        self.texts = []      # [text, x, y, t, color] floating labels
        self.wrecks = []     # [x, y, burn_time] burning hulks emitting smoke
        self.crate = None    # [x, y, life, age]
        self.crate_timer = CRATE_RESPAWN
        self.shake = 0.0
        self.now = 0.0
        self.state = 'lobby'
        self.paused = False
        self.timer = 0.0
        self.ending = None
        self.round_winner = None
        self.go_timer = 0.0

    # ---- devices

    def scan_pads(self):
        for i in range(pygame.joystick.get_count()):
            try:
                j = pygame.joystick.Joystick(i)
                pid = f"pad{j.get_instance_id()}"
                if pid in self.pads:
                    continue
                if sdl_ctrl and sdl_ctrl.is_controller(i):
                    self.pads[pid] = Pad(pid, 'ctrl', sdl_ctrl.Controller(i))
                else:
                    j.init()
                    self.pads[pid] = Pad(pid, 'joy', j)
            except Exception:   # pygame.error or the _sdl2 error type
                pass

    def remove_pad(self, instance_id):
        pid = f"pad{instance_id}"
        self.pads.pop(pid, None)
        if self.state == 'lobby':
            self.players = [p for p in self.players if p.pad_id != pid]

    def player_for_pad(self, pid):
        return next((p for p in self.players if p.pad_id == pid), None)

    def rumble(self, player, low, high, ms):
        pad = self.pads.get(player.pad_id)
        if pad:
            pad.rumble(low, high, ms)

    # ---- flow

    def clear_entities(self):
        for lst in (self.bullets, self.particles, self.rings, self.flashes, self.texts, self.wrecks):
            lst.clear()
        self.crate = None
        self.crate_timer = CRATE_RESPAWN

    def to_lobby(self):
        self.state = 'lobby'
        self.paused = False
        self.clear_entities()
        for p in self.players:
            p.score = 0
            p.tank = None

    def start_match(self):
        for p in self.players:
            p.score = 0
        self.new_round()

    def new_round(self):
        self.arena.generate()
        self.clear_entities()
        corners, sides = CORNER_SPAWNS[:], SIDE_SPAWNS[:]
        random.shuffle(corners)
        random.shuffle(sides)
        spawns = corners + sides
        cx, cy = W / 2, HUD + ROWS * T / 2
        for p, (c, r) in zip(self.players, spawns):
            x, y = tile_center(c, r)
            p.tank = Tank(p, x, y, math.atan2(cy - y, cx - x))
        self.state = 'countdown'
        self.timer = 3.0
        self.last_count = 4
        self.ending = None
        self.paused = False

    # ---- update

    def update(self, dt):
        self.now += dt
        self.shake = max(0.0, self.shake - dt * 1.8)

        if self.state == 'lobby':
            self.update_lobby()
            return

        self.claim_orphans()
        if self.state in ('countdown', 'play', 'roundover'):
            for pad in self.pads.values():
                if self.player_for_pad(pad.pid):
                    if 'start' in pad.pressed:
                        self.paused = not self.paused
                    elif self.paused and ('back' in pad.pressed or 'b' in pad.pressed):
                        self.to_lobby()
                        return
        if self.paused:
            return

        if self.state == 'countdown':
            self.timer -= dt
            n = math.ceil(self.timer)
            if n < self.last_count and n > 0:
                self.sounds.play('beep')
            self.last_count = n
            if self.timer <= 0:
                self.state = 'play'
                self.go_timer = 0.8
                self.sounds.play('go')
        elif self.state == 'roundover':
            self.timer -= dt
            if self.timer <= 0:
                if any(p.score >= WIN_SCORE for p in self.players):
                    self.state = 'matchover'
                    self.timer = 1.5
                else:
                    self.new_round()
        elif self.state == 'matchover':
            self.timer -= dt
            if self.timer <= 0 and any(('a' in pd.pressed or 'start' in pd.pressed) for pd in self.pads.values()):
                self.to_lobby()

        self.go_timer = max(0.0, self.go_timer - dt)
        self.update_tanks(dt)
        self.update_bullets(dt)
        self.update_effects(dt)

        if self.state == 'play':
            self.update_crate(dt)
            alive = [p for p in self.players if p.tank and p.tank.alive]
            limit = 1 if len(self.players) > 1 else 0
            if len(alive) <= limit and self.ending is None:
                self.ending = 1.2   # grace period: in-flight bullets can still trade
            if self.ending is not None:
                self.ending -= dt
                if self.ending <= 0:
                    alive = [p for p in self.players if p.tank and p.tank.alive]
                    self.round_winner = alive[0] if len(alive) == 1 and len(self.players) > 1 else None
                    if self.round_winner:
                        self.round_winner.score += 1
                    self.state = 'roundover'
                    self.timer = 3.0

    def update_lobby(self):
        for pad in self.pads.values():
            pl = self.player_for_pad(pad.pid)
            if 'a' in pad.pressed and not pl and len(self.players) < MAX_PLAYERS:
                used = {p.idx for p in self.players}
                idx = next(i for i in range(MAX_PLAYERS) if i not in used)
                self.players.append(Player(idx, pad.pid))
                self.players.sort(key=lambda p: p.idx)
                self.sounds.play('join')
                pad.rumble(0.3, 0.5, 150)
            elif 'b' in pad.pressed and pl:
                self.players.remove(pl)
            if 'start' in pad.pressed and self.players and (pl or pad.kind.startswith('kb')):
                self.start_match()
                return

    def claim_orphans(self):
        """A reconnected controller (new instance id) takes over a player whose pad vanished."""
        for pad in self.pads.values():
            if 'a' in pad.pressed and not self.player_for_pad(pad.pid):
                orphan = next((p for p in self.players if p.pad_id not in self.pads), None)
                if orphan:
                    orphan.pad_id = pad.pid
                    pad.rumble(0.3, 0.5, 150)

    def update_tanks(self, dt):
        can_act = self.state == 'play'
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        for t in tanks:
            pad = self.pads.get(t.player.pad_id)
            t.cooldown -= dt
            t.flash -= dt
            t.recoil = max(0.0, t.recoil - 30 * dt)
            if not pad:
                continue
            mx, my = pad.move
            if can_act and (mx or my):
                target = math.atan2(my, mx)
                t.angle = approach_angle(t.angle, target, TURN_SPEED * dt)
                fwd = TANK_SPEED * min(1.0, math.hypot(mx, my)) * max(0.0, math.cos(angle_diff(t.angle, target)))
                ox, oy = t.x, t.y
                t.x += math.cos(t.angle) * fwd * dt
                t.y += math.sin(t.angle) * fwd * dt
                t.x, t.y = self.arena.collide_circle(t.x, t.y, TANK_R)
                moved = math.hypot(t.x - ox, t.y - oy)
                t.tread += moved
                t.tread_phase += moved
                if t.tread > 6:
                    t.tread = 0
                    self.arena.tread_mark(t.x, t.y, t.angle)
            if pad.aim is not None:
                t.turret = approach_angle(t.turret, pad.aim, TURRET_SPEED * dt)
            elif pad.turret_rot:
                t.turret += pad.turret_rot * KB_TURRET_SPEED * dt
            if can_act and 'fire' in pad.held and t.cooldown <= 0:
                if t.ammo <= 0:
                    t.cooldown = FIRE_COOLDOWN
                    self.sounds.play('empty')
                elif sum(1 for b in self.bullets if b.owner is t) < MAX_BULLETS:
                    self.fire(t)
            if t.hp == 1:
                t.smoke -= dt
                if t.smoke <= 0:
                    t.smoke = 0.08
                    self.particles.append([t.x, t.y, random.uniform(-10, 10), random.uniform(-30, -10),
                                           1.0, 1.0, 'smoke', random.uniform(4, 7)])

        # keep tanks from overlapping each other
        for i, a in enumerate(tanks):
            for b in tanks[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                if 0 < d < TANK_R * 2:
                    push = (TANK_R * 2 - d) / 2
                    a.x -= dx / d * push
                    a.y -= dy / d * push
                    b.x += dx / d * push
                    b.y += dy / d * push
                    a.x, a.y = self.arena.collide_circle(a.x, a.y, TANK_R)
                    b.x, b.y = self.arena.collide_circle(b.x, b.y, TANK_R)

    def fire(self, t):
        t.cooldown = FIRE_COOLDOWN
        t.ammo -= 1
        t.recoil = 5.0
        tx = t.x + math.cos(t.turret) * 25
        ty = t.y + math.sin(t.turret) * 25
        blocked = self.arena.bullet_hit(tx, ty)
        if blocked:
            if blocked[2] == BRICK:
                self.damage_brick(blocked[0], blocked[1])
            self.sparks(tx, ty, (255, 220, 140), 6)
        else:
            self.bullets.append(Bullet(t, tx, ty, t.turret))
        for _ in range(8):
            a = t.turret + random.uniform(-0.45, 0.45)
            sp = random.uniform(60, 220)
            self.particles.append([tx, ty, math.cos(a) * sp, math.sin(a) * sp, 0.14, 0.14, 'fire', random.uniform(3, 6)])
        for _ in range(3):
            self.particles.append([tx, ty, math.cos(t.turret) * 40 + random.uniform(-15, 15),
                                   math.sin(t.turret) * 40 + random.uniform(-15, 15), 0.6, 0.6, 'smoke', random.uniform(3, 5)])
        self.flashes.append([tx, ty, 0.0, 0.09, 34])
        self.sounds.play('shot')
        self.rumble(t.player, 0.0, 0.3, 60)

    def update_crate(self, dt):
        if self.crate is None:
            self.crate_timer -= dt
            if self.crate_timer <= 0:
                tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
                spots = [tile_center(c, r) for r in range(ROWS) for c in range(COLS) if self.arena.grid[r][c] == EMPTY]
                far = [s for s in spots if all(math.hypot(s[0] - t.x, s[1] - t.y) > 3 * T for t in tanks)]
                if far or spots:
                    x, y = random.choice(far or spots)
                    self.crate = [x, y, CRATE_LIFE, 0.0]
                    self.rings.append([x, y, 0.0, 0.4])
                    self.sounds.play('crate')
            return
        c = self.crate
        c[2] -= dt
        c[3] += dt
        for t in (p.tank for p in self.players if p.tank and p.tank.alive):
            if math.hypot(t.x - c[0], t.y - c[1]) < TANK_R + CRATE_R:
                t.ammo = MAX_AMMO
                self.sounds.play('pickup')
                self.rumble(t.player, 0.2, 0.6, 150)
                self.texts.append(["AMMO FULL", c[0], c[1] - 20, 0.0, (255, 220, 100)])
                self.sparks(c[0], c[1], (255, 220, 120), 18)
                self.flashes.append([c[0], c[1], 0.0, 0.3, 60])
                self.crate = None
                break
        else:
            if c[2] <= 0:
                for _ in range(6):
                    self.particles.append([c[0], c[1], random.uniform(-25, 25), random.uniform(-25, 25), 0.7, 0.7, 'smoke', 6])
                self.crate = None
        if self.crate is None:
            self.crate_timer = CRATE_RESPAWN

    def damage_brick(self, c, r):
        self.arena.brick_hp[(c, r)] -= 1
        self.arena.ground = None
        x, y = tile_center(c, r)
        if self.arena.brick_hp[(c, r)] <= 0:
            self.arena.grid[r][c] = EMPTY
            for _ in range(14):
                a = random.uniform(0, math.tau)
                sp = random.uniform(40, 160)
                self.particles.append([x, y, math.cos(a) * sp, math.sin(a) * sp, 0.6, 0.6, 'debris',
                                       random.uniform(3, 6), (150 + random.randint(-20, 20), 75, 50)])
            for _ in range(5):
                self.particles.append([x, y, random.uniform(-20, 20), random.uniform(-20, 20), 0.9, 0.9, 'smoke', 8])
        self.sounds.play('brick')

    def update_bullets(self, dt):
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        for b in self.bullets:
            b.age += dt
            if b.age > BULLET_LIFE:
                b.dead = True
                continue
            steps = max(1, math.ceil(BULLET_SPEED * dt / 5))
            sdt = dt / steps
            for _ in range(steps):
                nx, ny = b.x + b.vx * sdt, b.y + b.vy * sdt
                hx = self.arena.bullet_hit(nx, b.y)
                hy = self.arena.bullet_hit(b.x, ny)
                if not hx and not hy:
                    hx = hy = self.arena.bullet_hit(nx, ny)   # exact corner
                if hx or hy:
                    bricks = {h[:2] for h in (hx, hy) if h and h[2] == BRICK}
                    if bricks:
                        for c, r in bricks:
                            self.damage_brick(c, r)
                        self.sparks(b.x, b.y, (255, 200, 120), 8)
                        self.arena.scorch_mark(b.x, b.y)
                        b.dead = True
                        break
                    if b.bounces > 0:
                        b.bounces -= 1
                        b.bounced = True
                        if hx:
                            b.vx = -b.vx
                        if hy:
                            b.vy = -b.vy
                        self.sparks(b.x, b.y, (220, 230, 255), 5)
                        self.sounds.play('bounce')
                        continue
                    self.sparks(b.x, b.y, (220, 230, 255), 8)
                    self.arena.scorch_mark(b.x, b.y)
                    b.dead = True
                    break
                b.x, b.y = nx, ny
                for t in tanks:
                    if not t.alive or (t is b.owner and not b.bounced):
                        continue
                    if (t.x - b.x) ** 2 + (t.y - b.y) ** 2 < (TANK_R + BULLET_R) ** 2:
                        self.hit_tank(t, b)
                        b.dead = True
                        break
                if b.dead:
                    break
            if not b.dead:
                self.particles.append([b.x, b.y, 0, 0, 0.16, 0.16, 'spark', 2.6, b.owner.player.color])
        # bullets cancel each other out
        live = [b for b in self.bullets if not b.dead]
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                if not a.dead and not b.dead and (a.x - b.x) ** 2 + (a.y - b.y) ** 2 < (BULLET_R * 2.5) ** 2:
                    a.dead = b.dead = True
                    self.sparks((a.x + b.x) / 2, (a.y + b.y) / 2, (255, 255, 200), 10)
                    self.sounds.play('bounce')
        self.bullets = [b for b in self.bullets if not b.dead]

    def hit_tank(self, t, b):
        t.hp -= 1
        t.flash = 0.12
        self.sparks(b.x, b.y, (255, 230, 150), 12)
        self.shake = max(self.shake, 0.15)
        if t.hp <= 0:
            self.kill(t)
        else:
            self.sounds.play('hit')
            self.rumble(t.player, 0.6, 0.8, 220)

    def kill(self, t):
        t.alive = False
        sp = t.player.sprites
        deg = -math.degrees(t.angle)
        self.arena.scorch_mark(t.x, t.y, big=True)
        self.arena.decal(pygame.transform.rotozoom(sp['wreck'], deg, 1), t.x, t.y)
        self.arena.decal(pygame.transform.rotozoom(sp['wreck_turret'], -math.degrees(t.turret), 1), t.x, t.y)
        for _ in range(34):
            a = random.uniform(0, math.tau)
            s = random.uniform(30, 230)
            life = random.uniform(0.3, 0.8)
            self.particles.append([t.x, t.y, math.cos(a) * s, math.sin(a) * s, life, life, 'fire', random.uniform(6, 13)])
        for _ in range(18):
            a = random.uniform(0, math.tau)
            s = random.uniform(10, 60)
            life = random.uniform(0.8, 1.7)
            self.particles.append([t.x, t.y, math.cos(a) * s, math.sin(a) * s, life, life, 'smoke', random.uniform(7, 12)])
        dark = tuple(int(c * 0.5) for c in t.player.color)
        for _ in range(12):
            a = random.uniform(0, math.tau)
            s = random.uniform(80, 260)
            self.particles.append([t.x, t.y, math.cos(a) * s, math.sin(a) * s, 0.7, 0.7, 'debris', random.uniform(3, 6), dark])
        self.rings.append([t.x, t.y, 0.0, 0.45])
        self.flashes.append([t.x, t.y, 0.0, 0.5, 150])
        self.wrecks.append([t.x, t.y, 6.0])
        self.shake = max(self.shake, 0.6)
        self.sounds.play('explode')
        self.rumble(t.player, 1.0, 1.0, 600)

    def sparks(self, x, y, color, n):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            s = random.uniform(50, 220)
            life = random.uniform(0.1, 0.3)
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s, life, life, 'spark', random.uniform(1.5, 3), color])

    def update_effects(self, dt):
        drag = 0.04 ** dt
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= drag
            p[3] *= drag
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for r in self.rings:
            r[2] += dt
        self.rings = [r for r in self.rings if r[2] < r[3]]
        for f in self.flashes:
            f[2] += dt
        self.flashes = [f for f in self.flashes if f[2] < f[3]]
        for tx in self.texts:
            tx[2] -= 28 * dt
            tx[3] += dt
        self.texts = [tx for tx in self.texts if tx[3] < 1.0]
        for wr in self.wrecks:
            wr[2] -= dt
            if random.random() < dt * 14:
                self.particles.append([wr[0] + random.uniform(-8, 8), wr[1] + random.uniform(-8, 8),
                                       random.uniform(-8, 8), random.uniform(-35, -15), 1.4, 1.4, 'smoke', random.uniform(5, 9)])
            if wr[2] > 2 and random.random() < dt * 10:
                self.particles.append([wr[0] + random.uniform(-7, 7), wr[1] + random.uniform(-7, 7),
                                       0, random.uniform(-25, -10), 0.4, 0.4, 'fire', random.uniform(3, 6)])
        self.wrecks = [wr for wr in self.wrecks if wr[2] > 0]

    # ---- drawing

    def text(self, s, font, color, center, dst=None, shadow=True):
        dst = dst or self.screen
        img = font.render(s, True, color)
        rect = img.get_rect(center=center)
        if shadow:
            dst.blit(font.render(s, True, (0, 0, 0)), rect.move(3, 3))
        dst.blit(img, rect)

    def draw_tank(self, dst, t):
        sp = t.player.sprites
        white = t.flash > 0
        deg = -math.degrees(t.angle)
        body = sp['body_white'] if white else sp['bodies'][int(t.tread_phase / 1.2) % 4]
        blit_center(dst, pygame.transform.rotozoom(sp['shadow'], deg, 1), t.x + 4, t.y + 5)
        blit_center(dst, pygame.transform.rotozoom(body, deg, 1), t.x, t.y)
        rx = t.x - math.cos(t.turret) * t.recoil
        ry = t.y - math.sin(t.turret) * t.recoil
        blit_center(dst, pygame.transform.rotozoom(sp['turret_white' if white else 'turret'],
                                                   -math.degrees(t.turret), 1), rx, ry)

    def draw_particles(self, dst):
        glows = []
        for p in self.particles:
            k = p[4] / p[5]
            kind = p[6]
            if kind == 'fire':
                pygame.draw.circle(dst, lerp_color((150, 40, 10), (255, 240, 150), k), (p[0], p[1]), max(1, p[7] * k))
                glows.append((p[0], p[1], p[7] * k * 2.5))
            elif kind == 'smoke':
                pygame.draw.circle(dst, lerp_color(FLOOR, (115, 115, 112), k), (p[0], p[1]), p[7] * (1.6 - 0.6 * k))
            elif kind == 'spark':
                pygame.draw.circle(dst, p[8], (p[0], p[1]), max(1, p[7] * k))
            else:
                sz = max(1, p[7] * (0.4 + 0.6 * k))
                dst.fill(p[8], (p[0] - sz / 2, p[1] - sz / 2, sz, sz))
        for x, y, rad in glows:
            if rad >= 4:
                add_glow(dst, (150, 70, 15), x, y, int(rad / 2) * 2)

    def draw_crate(self, w):
        x, y, life, age = self.crate
        if life < 2 and int(life * 8) % 2 == 0:
            return
        pop = min(1.0, age / 0.25)
        scale = pop * (1.25 - 0.25 * pop) * (1 + 0.05 * math.sin(self.now * 6))
        add_glow(w, (110, 85, 20), x, y, 34 + int(3 * math.sin(self.now * 5)))
        blit_center(w, self.crate_shadow, x + 4, y + 5)
        blit_center(w, pygame.transform.rotozoom(self.crate_sprite, math.sin(self.now * 2) * 6, max(0.05, scale)), x, y - 2)
        frac = life / CRATE_LIFE
        pygame.draw.arc(w, (255, 215, 90), (x - 23, y - 25, 46, 46), math.pi / 2, math.pi / 2 + math.tau * frac, 2)

    def draw_world(self):
        w = self.world
        self.arena.draw_ground(w, self.now)
        if self.crate:
            self.draw_crate(w)
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        for t in tanks:
            self.draw_tank(w, t)
        for b in self.bullets:
            col = b.owner.player.color
            add_glow(w, tuple(c // 2 for c in col), b.x, b.y, 16)
            pygame.draw.line(w, col, (b.x, b.y), (b.x - b.vx * 0.012, b.y - b.vy * 0.012), 5)
            pygame.draw.circle(w, col, (b.x, b.y), BULLET_R + 1)
            pygame.draw.circle(w, (255, 255, 255), (b.x, b.y), 2.5)
        self.draw_particles(w)
        for x, y, t, mt, rad in self.flashes:
            k = 1 - t / mt
            add_glow(w, (int(255 * k), int(200 * k), int(120 * k)), x, y, rad)
        for t in tanks:   # ammo warnings, drawn under bushes so hiding still works
            if t.ammo == 0:
                if int(self.now * 4) % 2:
                    self.text("EMPTY", self.font_tiny, (255, 90, 80), (t.x, t.y - 27), w, shadow=True)
            elif t.ammo <= 3:
                self.text(str(t.ammo), self.font_tiny, (255, 215, 90), (t.x, t.y - 27), w, shadow=True)
        self.arena.draw_bushes(w, self.now)
        for x, y, t, mt in self.rings:
            k = t / mt
            pygame.draw.circle(w, lerp_color((255, 220, 150), (255, 90, 30), k), (x, y), 10 + 90 * k, max(1, int(7 * (1 - k))))
        for s, x, y, t, col in self.texts:
            img = self.font_hud.render(s, True, col)
            img.set_alpha(int(255 * (1 - t)))
            w.blit(img, img.get_rect(center=(round(x), round(y))))

        ox = oy = 0
        if self.shake > 0:
            amp = self.shake * 14
            ox, oy = random.uniform(-amp, amp), random.uniform(-amp, amp)
        self.screen.fill((0, 0, 0))
        self.screen.blit(w, (ox, oy))

    def draw_hud(self):
        self.screen.fill((22, 24, 28), (0, 0, W, HUD))
        pygame.draw.line(self.screen, (60, 64, 70), (0, HUD - 1), (W, HUD - 1))
        slot = W // MAX_PLAYERS
        for p in self.players:
            x0 = p.idx * slot + 8
            icon = pygame.transform.rotozoom(p.sprites['body'], 0, 0.7)
            self.screen.blit(icon, icon.get_rect(center=(x0 + 14, HUD // 2)))
            tur = pygame.transform.rotozoom(p.sprites['turret'], 0, 0.7)
            self.screen.blit(tur, tur.get_rect(center=(x0 + 14, HUD // 2)))
            self.screen.blit(self.font_hud.render(f"P{p.idx + 1}", True, p.color), (x0 + 30, 11))
            t = p.tank
            hp = t.hp if t and t.alive else 0
            ammo = t.ammo if t and t.alive else 0
            for i in range(TANK_HP):
                col = (230, 70, 60) if i < hp else (70, 70, 75)
                self.screen.fill(col, (x0 + 62 + i * 14, 6, 11, 10))
            empty_flash = t and t.alive and ammo == 0 and int(self.now * 4) % 2
            for i in range(MAX_AMMO):
                col = (230, 185, 70) if i < ammo else ((150, 50, 45) if empty_flash else (60, 60, 65))
                self.screen.fill(col, (x0 + 62 + i * 6, 21, 4, 12))
            for i in range(WIN_SCORE):
                cx = x0 + 134 + i * 14
                if i < p.score:
                    pygame.draw.circle(self.screen, p.color, (cx, HUD // 2), 5)
                else:
                    pygame.draw.circle(self.screen, (90, 90, 95), (cx, HUD // 2), 5, 2)
            if p.pad_id not in self.pads and int(self.now * 2) % 2:
                img = self.font_tiny.render("NO PAD", True, (255, 80, 80))
                self.screen.fill((22, 24, 28), (x0 + 60, 2, 66, HUD - 4))
                self.screen.blit(img, img.get_rect(center=(x0 + 92, HUD // 2)))

    def draw_overlay(self):
        cy = HUD + ROWS * T // 2
        if self.state == 'countdown':
            n = max(1, math.ceil(self.timer))
            self.text(str(n), self.font_big, (255, 255, 255), (W // 2, cy))
        elif self.state == 'play' and self.go_timer > 0:
            self.text("GO!", self.font_big, (255, 230, 120), (W // 2, cy))
        elif self.state == 'roundover':
            self.dim(120)
            if self.round_winner:
                self.text(f"{self.round_winner.cname} WINS THE ROUND", self.font_med, self.round_winner.color, (W // 2, cy - 30))
            else:
                self.text("DRAW!" if len(self.players) > 1 else "ROUND OVER", self.font_med, (230, 230, 230), (W // 2, cy - 30))
            self.draw_scores(cy + 40)
        elif self.state == 'matchover':
            self.dim(160)
            best = max(self.players, key=lambda p: p.score)
            self.text(f"{best.cname} WINS THE MATCH!", self.font_med, best.color, (W // 2, cy - 60))
            self.draw_scores(cy + 10)
            if self.timer <= 0:
                self.text("Press A to continue", self.font_small, (220, 220, 220), (W // 2, cy + 90))
        if self.paused:
            self.dim(150)
            self.text("PAUSED", self.font_big, (255, 255, 255), (W // 2, cy - 30))
            self.text("START resume   •   BACK / B quit to lobby", self.font_small, (220, 220, 220), (W // 2, cy + 50))

    def draw_scores(self, y):
        parts = [(f"{p.cname} {p.score}", p.color) for p in self.players]
        imgs = [self.font_small.render(s, True, c) for s, c in parts]
        total = sum(i.get_width() for i in imgs) + 40 * (len(imgs) - 1)
        x = W // 2 - total // 2
        for img in imgs:
            self.screen.blit(img, (x, y))
            x += img.get_width() + 40

    def dim(self, alpha):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        s.fill((0, 0, 0, alpha))
        self.screen.blit(s, (0, 0))

    def draw_lobby(self):
        self.arena.draw_ground(self.screen, self.now)
        self.arena.draw_bushes(self.screen, self.now)
        self.dim(170)
        self.text("TANK ARENA", self.font_big, (240, 220, 120), (W // 2, 130))
        self.text("Left stick drive   •   Right stick aim   •   RT / RB / A fire", self.font_small, (200, 200, 200), (W // 2, 200))
        self.text(f"{MAX_AMMO} shells per tank - grab the ammo crates to reload", self.font_hud, (230, 200, 110), (W // 2, 236))

        bw, bh, gap = 184, 220, 15
        x0 = (W - (MAX_PLAYERS * bw + (MAX_PLAYERS - 1) * gap)) // 2
        by = 270
        for i in range(MAX_PLAYERS):
            x = x0 + i * (bw + gap)
            p = next((pl for pl in self.players if pl.idx == i), None)
            color = PLAYER_COLORS[i][0]
            rect = pygame.Rect(x, by, bw, bh)
            pygame.draw.rect(self.screen, (30, 32, 36), rect, border_radius=12)
            pygame.draw.rect(self.screen, color if p else (70, 72, 78), rect, 3, border_radius=12)
            self.text(f"P{i + 1}", self.font_med, color if p else (110, 110, 115), (rect.centerx, by + 35))
            if p:
                ang = self.now * 1.5 + i
                body = pygame.transform.rotozoom(p.sprites['body'], -math.degrees(ang), 1.6)
                tur = pygame.transform.rotozoom(p.sprites['turret'], -math.degrees(ang), 1.6)
                blit_center(self.screen, body, rect.centerx, by + 115)
                blit_center(self.screen, tur, rect.centerx, by + 115)
                pad = self.pads.get(p.pad_id)
                self.text(pad.label if pad else "?", self.font_tiny, (200, 200, 200), (rect.centerx, by + 190), shadow=False)
            else:
                if int(self.now * 2) % 2:
                    self.text("Press A to join", self.font_hud, (170, 170, 175), (rect.centerx, by + 120), shadow=False)

        n_pads = sum(1 for p in self.pads.values() if p.kind in ('ctrl', 'joy'))
        self.text(f"{n_pads} controller{'s' if n_pads != 1 else ''} connected", self.font_hud, (150, 150, 155), (W // 2, 540), shadow=False)
        if self.players:
            msg = "Press START to begin" if len(self.players) > 1 else "Press START for solo practice (2+ players for a match)"
            self.text(msg, self.font_small, (255, 255, 255), (W // 2, 590))
        self.text("Keyboard P1: WASD drive, Q/E aim, SPACE join+fire, X leave   •   P2: arrows drive, , . aim, R-CTRL join+fire, DEL leave   •   ENTER start",
                  self.font_tiny, (150, 150, 155), (W // 2, 630), shadow=False)
        self.text(f"First to {WIN_SCORE} round wins   •   B leave   •   F11 fullscreen   •   ESC quit",
                  self.font_hud, (150, 150, 155), (W // 2, 660), shadow=False)

    def draw(self):
        if self.state == 'lobby':
            self.draw_lobby()
        else:
            self.draw_world()
            self.draw_hud()
            self.draw_overlay()

    # ---- main loop

    def run(self):
        added = {pygame.JOYDEVICEADDED, getattr(pygame, 'CONTROLLERDEVICEADDED', -1)}
        removed = {pygame.JOYDEVICEREMOVED, getattr(pygame, 'CONTROLLERDEVICEREMOVED', -1)}
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                if e.type in added:
                    self.scan_pads()
                elif e.type in removed:
                    self.remove_pad(e.instance_id)
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_F11:
                        pygame.display.toggle_fullscreen()
                    elif e.key == pygame.K_ESCAPE:
                        if self.state == 'lobby':
                            return
                        self.to_lobby()
            keys = pygame.key.get_pressed()
            for pad in list(self.pads.values()):
                pad.poll(keys)
            self.update(dt)
            self.draw()
            pygame.display.flip()


def main():
    if not sys.platform.startswith('linux'):
        sys.exit("Tank Arena is built for Linux.")
    pygame.mixer.pre_init(22050, -16, 2, 512)
    pygame.init()
    if sdl_ctrl:
        sdl_ctrl.init()
    Game(fullscreen='--windowed' not in sys.argv).run()
    pygame.quit()


if __name__ == '__main__':
    main()
