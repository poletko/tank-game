#!/usr/bin/env python3
# Public domain (The Unlicense, see LICENSE): do whatever you want with this.
"""Tank Arena - local multiplayer top-down tank shooter (Linux, Xbox controllers).

Left stick: drive   Right stick: aim turret   RT / RB / A: fire
START: begin match / pause   B: leave lobby   BACK (in pause): quit to lobby
Y / TAB in the lobby cycles VERSUS, CO-OP (tanks vs waves of undead) and RACE.
Keyboard (two players): P1 WASD + Q/E turret + SPACE fire + X leave, P2 arrows + ,/. turret + RCTRL fire + DELETE leave
ENTER starts / pauses. Up to 6 players in total.
F11 toggles fullscreen, ESC returns to lobby / quits.
Every 5 minutes of play a math question (Slovenian, end of 4th grade) appears at the next break between
rounds or waves. Stick/D-pad up/down changes a digit, left/right picks the digit, A or START answers.
"""
import heapq
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

# co-op mode
COOP_TANK_HP = 5
GHOUL_KINDS = ('mummy', 'zombie', 'vampire', 'ghost')
GHOUL_HP = 5
GHOUL_REGEN = 10.0          # seconds per regenerated hit
GHOUL_SPEED = TANK_SPEED * 0.6
GHOUL_SLOW = 0.5            # speed factor while slowed
GHOUL_SLOW_TIME = 3.0
GHOUL_R = 13
GHOUL_EMERGE = 0.8
GHOUL_ATTACK_CD = 1.0
TANK_HIT_INVULN = 1.0
WAVE_BREAK = 4.0
AMMO_DROP_CHANCE = 0.35
AMMO_DROP = 3
GHOUL_COLORS = {'mummy': (215, 200, 155), 'zombie': (100, 160, 70), 'vampire': (160, 25, 40), 'ghost': (220, 230, 255)}

# race mode
RACE_SCALE = 0.55           # race tanks are drawn smaller so the track has room
RACE_TANK_R = 9
RACE_SPEED = 330
RACE_OFFROAD_SPEED = 140
RACE_ACCEL = 420
RACE_BRAKE = 520
RACE_TURN = 5.0
RACE_GRIP = 6.0             # how fast sideways velocity dies; lower = more drift
RACE_DRIFT_GRIP = 0.45      # grip factor while turning hard at speed
RACE_LAPS = 5
RACE_WIN_SCORE = 3
RACE_BUMP = 230             # speed a shell hit adds to the tank it hits
RACE_BULLET_LIFE = 1.2
RACE_LOST_TIME = 2.0        # seconds far off the track before a tank is put back
TRACK_W = 84
TRACK_STEP = 8              # spacing of the centerline samples (px)
RAMP_LEN = 40
RAMP_H = 12
RAMP_KICK = 0.55            # take-off vertical speed per unit of forward speed
GRAVITY = 900
SPECTATORS = 50
TREES = 14
GRASS = (62, 110, 52)
ASPHALT = (66, 68, 74)
ORDINALS = ('1st', '2nd', '3rd', '4th', '5th', '6th')

# math break
QUIZ_INTERVAL = 300.0       # seconds of play between questions
QUIZ_DIGITS = 5
QUIZ_TRIES = 3              # wrong answers before the solution is shown and a new question asked
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


# ---------------------------------------------------------------- math questions

def fmt(n):
    """Slovenian style: thousands separated by a space."""
    return f"{n:,}".replace(",", " ")


def make_question():
    """A math question at the level of a finished 4th grade in Slovenia: (text, answer, unit)."""
    r = random.randint
    kind = random.choice(('add', 'sub', 'table', 'mul', 'div', 'fraction', 'units', 'perimeter',
                          'order', 'round', 'missing', 'word', 'word'))
    if kind == 'add':
        a = r(1000, 8999)
        b = r(100, 9999 - a)
        return f"{fmt(a)} + {fmt(b)} = ?", a + b, ""
    if kind == 'sub':
        a = r(1000, 10000)
        b = r(100, a - 1)
        return f"{fmt(a)} - {fmt(b)} = ?", a - b, ""
    if kind == 'table':
        a, b = r(2, 10), r(2, 10)
        return random.choice(((f"{a} · {b} = ?", a * b), (f"{a * b} : {b} = ?", a)))[0:2] + ("",)
    if kind == 'mul':
        b = r(2, 9)
        a = r(101, 9999 // b)
        return f"{fmt(a)} · {b} = ?", a * b, ""
    if kind == 'div':
        b = r(2, 9)
        q = r(21, 9999 // b)
        return f"{fmt(q * b)} : {b} = ?", q, ""
    if kind == 'fraction':
        d = r(2, 10)
        n = d * r(2, 12)
        return f"Koliko je 1/{d} od {n}?", n // d, ""
    if kind == 'units':
        a, b = r(2, 9), r(11, 99)
        return random.choice((
            (f"{a} m {b} cm = ? cm", a * 100 + b, "cm"),
            (f"{a} kg = ? g", a * 1000, "g"),
            (f"{a} kg {b * 10} g = ? g", a * 1000 + b * 10, "g"),
            (f"{a} l {b % 10} dl = ? dl", a * 10 + b % 10, "dl"),
            (f"{a % 4 + 1} h {b % 60} min = ? min", (a % 4 + 1) * 60 + b % 60, "min"),
            (f"{a} km = ? m", a * 1000, "m"),
            (f"{a} dm = ? cm", a * 10, "cm"),
            (f"{a} cm = ? mm", a * 10, "mm"),
            (f"{a} € {b} centov = ? centov", a * 100 + b, "centov"),
        ))
    if kind == 'perimeter':
        a, b = r(2, 20), r(2, 20)
        if a == b:
            return f"Kvadrat ima stranico {a} cm. Koliko meri njegov obseg?", 4 * a, "cm"
        return f"Pravokotnik ima stranici {a} cm in {b} cm. Koliko meri njegov obseg?", 2 * (a + b), "cm"
    if kind == 'order':
        a, b, c = r(2, 50), r(2, 10), r(2, 10)
        return random.choice(((f"{a} + {b} · {c} = ?", a + b * c),
                              (f"{b * c} : {c} + {a} = ?", b + a),
                              (f"({a % 20 + 1} + {b}) · {c} = ?", (a % 20 + 1 + b) * c)))[0:2] + ("",)
    if kind == 'round':
        n = r(1001, 9999)
        name, p = random.choice((("desetice", 10), ("stotice", 100), ("tisočice", 1000)))
        return f"Zaokroži število {fmt(n)} na {name}.", (n + p // 2) // p * p, ""
    if kind == 'missing':
        a, b = r(100, 899), r(100, 899)
        k, m = r(2, 10), r(2, 10)
        return random.choice(((f"Katero število manjka?   □ + {b} = {a + b}", a),
                              (f"Katero število manjka?   {k} · □ = {k * m}", m),
                              (f"Katero število manjka?   {a + b} - □ = {a}", b)))[0:2] + ("",)
    k, m = r(2, 6), r(5, 8)
    a, b, c = r(30, 90), r(5, 25), r(5, 25)
    p, n = r(2, 9), r(5, 12)
    pages, read = r(120, 400), r(20, 110)
    return random.choice((
        (f"V razredu je {k * m} učencev. Učiteljica jih razdeli v skupine po {k}. Koliko je skupin?", m, ""),
        (f"Zvezek stane {p} €. Koliko stane {n} zvezkov?", p * n, "€"),
        (f"Na kmetiji je {n} krav. Koliko nog imajo vse krave skupaj?", 4 * n, ""),
        (f"Na dvorišču je {n} kokoši. Koliko nog imajo vse kokoši skupaj?", 2 * n, ""),
        (f"Jan je imel {a} sličic. Prijatelju jih je podaril {b}. Koliko sličic mu je ostalo?", a - b, ""),
        (f"Na avtobusu je {a} potnikov. Na postaji jih {b} izstopi in {c} vstopi. Koliko potnikov je zdaj na avtobusu?",
         a - b + c, ""),
        (f"Teden ima 7 dni. Koliko dni je v {n} tednih?", 7 * n, ""),
        (f"Knjiga ima {pages} strani. Lana je prebrala {read} strani. Koliko strani mora še prebrati?", pages - read, ""),
        (f"Mama je kupila {n} jabolk po {p * 10} centov. Koliko centov je plačala?", n * p * 10, "centov"),
    ))


class Quiz:
    """A math question answered on a row of digit wheels, so any controller can enter it."""

    def __init__(self):
        self.new_question()

    def new_question(self):
        self.text, self.answer, self.unit = make_question()
        self.digits = [0] * QUIZ_DIGITS
        self.cursor = QUIZ_DIGITS - 1
        self.tries = 0
        self.solved = 0.0       # counts down after a correct answer, then the game resumes

    def value(self):
        return int("".join(map(str, self.digits)))

    def type_digit(self, d):   # keyboard: digits shift in from the right like a calculator
        self.digits = self.digits[1:] + [d]

    def backspace(self):
        self.digits = [0] + self.digits[:-1]


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
        n4, n5 = lp_noise(0.08), lp_noise(0.3)
        self.snd['groan'] = self.make(0.7, lambda t: (math.sin(tau * (150 - 70 * t + 8 * math.sin(t * 30)) * t) * 0.6
                                                      + n4() * 2) * min(1, t * 10) * e(-t * 2.5), 0.3)
        self.snd['splat'] = self.make(0.3, lambda t: n5() * 2 * e(-t * 14) + math.sin(tau * 90 * t) * e(-t * 20), 0.5)
        self.snd['ghoulhit'] = self.make(0.09, lambda t: n5() * 1.5 * e(-t * 50) + math.sin(tau * 180 * t) * e(-t * 40), 0.4)
        self.snd['wave'] = self.make(0.8, lambda t: (math.sin(tau * (220 if t < 0.35 else 165) * t)
                                                     + 0.4 * math.sin(tau * (440 if t < 0.35 else 330) * t)) * e(-t * 2.5), 0.3)
        n6, n7 = lp_noise(0.1), lp_noise(0.25)
        self.snd['bump'] = self.make(0.18, lambda t: (math.sin(tau * 310 * t) + 0.6 * math.sin(tau * 467 * t) + n2()) * e(-t * 22), 0.35)
        self.snd['land'] = self.make(0.3, lambda t: n6() * 3 * e(-t * 14) + math.sin(tau * 55 * t) * e(-t * 12), 0.55)
        self.snd['jump'] = self.make(0.35, lambda t: n7() * 1.5 * math.sin(math.pi * t / 0.35) ** 2, 0.3)
        self.snd['cheer'] = self.make(1.4, lambda t: n4() * 3 * (0.7 + 0.3 * math.sin(t * 37)) * min(1, t * 6) * e(-t * 1.6), 0.35)
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
            for name, b in (('a', pygame.CONTROLLER_BUTTON_A), ('b', pygame.CONTROLLER_BUTTON_B), ('y', pygame.CONTROLLER_BUTTON_Y),
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
            for name, b in (('a', 0), ('b', 1), ('y', 3), ('start', 7), ('back', 6)):
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
        if mx < -0.6:   # directions as buttons, for menus (the math break)
            held.add('left')
        elif mx > 0.6:
            held.add('right')
        if my < -0.6:
            held.add('up')
        elif my > 0.6:
            held.add('down')
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


def make_ghoul_sprites(kind):
    """Front-facing chibi monsters; returns {(state, facing): surface} for base/white/slow."""
    S = SS
    N = 34
    s = pygame.Surface((N * S, N * S), pygame.SRCALPHA)

    def C(x, y, r, col):
        pygame.draw.circle(s, col, (x * S, y * S), r * S)

    def E(x, y, w, h, col):
        pygame.draw.ellipse(s, col, (x * S, y * S, w * S, h * S))

    def Rr(x, y, w, h, col, br=0):
        pygame.draw.rect(s, col, (x * S, y * S, w * S, h * S), border_radius=br * S)

    def P(pts, col):
        pygame.draw.polygon(s, col, [(x * S, y * S) for x, y in pts])

    if kind == 'mummy':
        band, dark = (222, 208, 165), (160, 145, 105)
        Rr(2, 15, 9, 4, band, 2)
        Rr(23, 15, 9, 4, band, 2)
        E(8, 12, 18, 20, band)
        C(17, 11, 8, band)
        for y in (5, 9, 15, 20, 25, 29):
            pygame.draw.line(s, dark, (9 * S, y * S), (25 * S, (y + 2) * S), S)
        Rr(10, 9, 14, 4, (45, 32, 20), 2)
        C(14, 11, 1.6, (255, 230, 80))
        C(20, 11, 1.6, (255, 230, 80))
    elif kind == 'zombie':
        skin, shirt, dark = (125, 170, 95), (70, 85, 130), (40, 50, 80)
        Rr(1, 17, 9, 4, skin, 2)
        Rr(24, 14, 9, 4, skin, 2)
        Rr(8, 15, 18, 16, shirt, 5)
        P([(9, 31), (12, 26), (15, 31)], dark)
        P([(19, 31), (23, 25), (25, 31)], dark)
        Rr(15, 17, 2, 9, dark)
        C(17, 11, 8, skin)
        C(12, 6, 3, (60, 95, 45))
        C(21, 5, 2.5, (60, 95, 45))
        C(14, 10, 2.3, (240, 240, 215))
        C(20, 11, 1.7, (240, 240, 215))
        C(14, 10, 1, (20, 0, 0))
        C(20, 11, 0.8, (20, 0, 0))
        pygame.draw.line(s, (70, 30, 30), (13 * S, 15 * S), (21 * S, 14 * S), S)
    elif kind == 'vampire':
        cape, lining, skin = (30, 20, 40), (150, 20, 35), (225, 220, 235)
        P([(17, 7), (32, 32), (2, 32)], cape)
        P([(17, 15), (25, 32), (9, 32)], lining)
        P([(7, 3), (12, 13), (5, 16)], lining)
        P([(27, 3), (22, 13), (29, 16)], lining)
        C(17, 11, 7, skin)
        P([(10, 10), (11, 4), (17, 2), (23, 4), (24, 10), (17, 7)], (15, 10, 20))
        C(14, 11, 1.6, (230, 20, 30))
        C(20, 11, 1.6, (230, 20, 30))
        P([(15, 15), (16, 15), (15.5, 17)], (255, 255, 255))
        P([(18, 15), (19, 15), (18.5, 17)], (255, 255, 255))
    else:
        body = (235, 240, 255, 205)
        C(6, 17, 3, body)
        C(28, 15, 3, body)
        C(17, 13, 10, body)
        Rr(7, 13, 20, 13, body)
        for x in (9, 14, 19, 24):
            C(x + 0.5, 26, 2.8, body)
        eye = (20, 20, 45, 235)
        E(11.5, 9, 4, 6, eye)
        E(18.5, 9, 4, 6, eye)
        E(15, 16, 4, 5, eye)

    base = pygame.transform.smoothscale(s, (N, N)).convert_alpha()
    white = base.copy()
    white.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
    slow = base.copy()
    slow.fill((140, 185, 255, 255), special_flags=pygame.BLEND_RGBA_MULT)
    out = {}
    for name, img in (('base', base), ('white', white), ('slow', slow)):
        out[(name, 1)] = img
        out[(name, -1)] = pygame.transform.flip(img, True, False)
    return out


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


def make_tree_sprite(seed):
    rnd = random.Random(seed + 100)
    S = SS
    s = pygame.Surface((36 * S, 46 * S), pygame.SRCALPHA)
    pygame.draw.rect(s, (85, 60, 35), (15 * S, 26 * S, 6 * S, 18 * S), border_radius=2 * S)
    blobs = [(rnd.uniform(9, 27), rnd.uniform(10, 24), rnd.uniform(7, 10)) for _ in range(6)]
    for col, dx, dy, k in (((25, 70, 30), 1, 2, 1.0), ((40, 105, 42), 0, 0, 0.95), ((70, 145, 60), -1.5, -2, 0.55)):
        for x, y, r in blobs:
            pygame.draw.circle(s, col, ((x + dx) * S, (y + dy) * S), r * k * S)
    return pygame.transform.smoothscale(s, (36, 46)).convert_alpha()


def make_gib_sprites(kind):
    """Severed limbs for splattered spectators: head, two arms, two legs, a bone."""
    skin, cloth = {'mummy': ((222, 208, 165), (200, 185, 140)), 'zombie': ((125, 170, 95), (70, 85, 130)),
                   'vampire': ((225, 220, 235), (30, 20, 40)), 'ghost': ((235, 240, 255), (215, 222, 245))}[kind]
    blood = (150, 10, 15)
    S = SS

    def piece(w, h, col, stump=True):
        s = pygame.Surface((w * S, h * S), pygame.SRCALPHA)
        pygame.draw.rect(s, col, (0, 0, w * S, h * S), border_radius=int(h * S / 2))
        if stump:
            pygame.draw.circle(s, blood, (int((w - h / 2) * S), int(h * S / 2)), int(h * S / 2))
        return pygame.transform.smoothscale(s, (w, h)).convert_alpha()

    head = pygame.Surface((10 * S, 11 * S), pygame.SRCALPHA)
    pygame.draw.circle(head, skin, (5 * S, 5 * S), 5 * S)
    pygame.draw.ellipse(head, blood, (2 * S, 8 * S, 6 * S, 3 * S))
    for ex in (3.3, 6.7):
        pygame.draw.circle(head, (20, 10, 10), (ex * S, 4.5 * S), S)
    bone = pygame.Surface((10 * S, 4 * S), pygame.SRCALPHA)
    pygame.draw.rect(bone, (235, 230, 215), (1.5 * S, 1.2 * S, 7 * S, 1.6 * S))
    for x in (1.5, 8.5):
        for y in (1.2, 2.8):
            pygame.draw.circle(bone, (235, 230, 215), (x * S, y * S), 1.2 * S)
    return [pygame.transform.smoothscale(head, (10, 11)).convert_alpha(),
            piece(9, 3, skin), piece(9, 3, skin), piece(10, 4, cloth), piece(10, 4, cloth),
            pygame.transform.smoothscale(bone, (10, 4)).convert_alpha()]


def make_blood_splat(dx, dy):
    """A red stain sprayed in the direction (dx, dy) the victim was hit from."""
    s = pygame.Surface((90, 90), pygame.SRCALPHA)
    c = 45
    for _ in range(6):
        pygame.draw.circle(s, (random.randint(110, 150), 8, 12, 210), (c + random.uniform(-7, 7), c + random.uniform(-7, 7)),
                           random.uniform(5, 10))
    base = math.atan2(dy, dx)
    for _ in range(22):
        a = base + random.gauss(0, 0.45)
        d = random.uniform(6, 42)
        r = max(1.0, 5.5 - d / 9 + random.uniform(-1, 1))
        pygame.draw.circle(s, (random.randint(100, 160), 5, 10, 200), (c + math.cos(a) * d, c + math.sin(a) * d), r)
    return s.convert_alpha()


def catmull_loop(ctrl, per=24):
    out, n = [], len(ctrl)
    for i in range(n):
        p0, p1, p2, p3 = ctrl[i - 1], ctrl[i], ctrl[(i + 1) % n], ctrl[(i + 2) % n]
        for k in range(per):
            t = k / per
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[j] + (p2[j] - p0[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (3 * p1[j] - p0[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    return out


def resample_loop(pts, step):
    """Equally spaced points along a closed polyline."""
    out, need = [pts[0]], step
    for a, b in zip(pts, pts[1:] + pts[:1]):
        d, pos = math.dist(a, b), 0.0
        while d - pos >= need:
            pos += need
            k = pos / d
            out.append((a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k))
            need = step
        need -= d - pos
    if math.dist(out[-1], out[0]) < step / 2:
        out.pop()
    return out


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


class Track:
    """Race circuit: a closed spline sampled every TRACK_STEP px, with ramps, trees and spectator spots.

    Index 0 of `pts` is the start/finish line; tanks race in increasing index order.
    """

    def __init__(self, vignette):
        self.vignette = vignette
        self.tree_sprites = [make_tree_sprite(i) for i in range(3)]
        self.tree_shadow = pygame.Surface((34, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(self.tree_shadow, (0, 0, 0, 80), (0, 0, 34, 14))
        self.skid = pygame.Surface((3, 3), pygame.SRCALPHA)
        self.skid.fill((18, 18, 20, 70))
        self.generate()

    def generate(self):
        m = TRACK_W / 2 + 26
        cx, cy = W / 2, (HUD + H) / 2
        rx, ry = W / 2 - m, (H - HUD) / 2 - m
        for _ in range(500):
            n = random.randint(7, 11)
            ctrl = []
            for i in range(n):
                a = (i + random.uniform(-0.3, 0.3)) / n * math.tau
                k = random.uniform(0.35, 1.0)
                ctrl.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
            pts = resample_loop(catmull_loop(ctrl), TRACK_STEP)
            if self.valid(pts, TRACK_W / 2 + 14):
                break
        if random.random() < 0.5:
            pts.reverse()
        n = len(pts)
        ang = [math.atan2(pts[(i + 1) % n][1] - pts[i][1], pts[(i + 1) % n][0] - pts[i][0]) for i in range(n)]
        curv = [abs(angle_diff(ang[i], ang[(i + 1) % n])) for i in range(n)]
        # start on the straightest stretch, with a straight run-up behind it for the grid
        start = min(range(n), key=lambda i: sum(curv[(i + k) % n] for k in range(-18, 6)))
        self.pts = pts[start:] + pts[:start]
        self.ang = ang[start:] + ang[:start]
        curv = curv[start:] + curv[:start]
        self.n = n
        self.nx = [-math.sin(a) for a in self.ang]
        self.ny = [math.cos(a) for a in self.ang]

        # ramps on straights, with room to land
        cands = sorted(range(int(n * 0.2), int(n * 0.85)), key=lambda i: sum(curv[i - 4:i + 28]))
        self.ramps = []
        for i in cands:
            if sum(curv[i - 4:i + 28]) > 0.6 or len(self.ramps) == 3:
                break
            if all(min(abs(i - r[4]), n - abs(i - r[4])) > n / 5 for r in self.ramps):
                x, y = self.pts[i]
                self.ramps.append((x, y, math.cos(self.ang[i]), math.sin(self.ang[i]), i))

        self.trees = []
        for _ in range(400):
            if len(self.trees) == TREES:
                break
            x, y = random.uniform(20, W - 20), random.uniform(HUD + 30, H - 10)
            if self.dist2(x, y) > (TRACK_W / 2 + 60) ** 2 and all(math.dist((x, y), t[:2]) > 45 for t in self.trees):
                self.trees.append((x, y, random.randrange(3)))

        # spectators stand in small crowds just outside the curbs
        self.spots = []
        ci = side = 0
        for k in range(3000):
            if len(self.spots) == SPECTATORS:
                break
            if k % 8 == 0:
                ci, side = random.randrange(n), random.choice((-1, 1))
            i = (ci + random.randint(-6, 6)) % n
            off = TRACK_W / 2 + random.uniform(16, 36)
            x, y = self.pts[i][0] + self.nx[i] * side * off, self.pts[i][1] + self.ny[i] * side * off
            if not (14 < x < W - 14 and HUD + 24 < y < H - 8):
                continue
            if self.dist2(x, y) < (TRACK_W / 2 + 13) ** 2:
                continue
            if any((x - a) ** 2 + (y - b) ** 2 < 15 ** 2 for a, b in self.spots):
                continue
            if any((x - a) ** 2 + (y - b) ** 2 < 24 ** 2 for a, b, _ in self.trees):
                continue
            self.spots.append((x, y))
        self.render()

    @staticmethod
    def valid(pts, margin):
        if any(not (margin < x < W - margin and HUD + margin < y < H - margin) for x, y in pts):
            return False
        n = len(pts)
        for i in range(n):   # no corner tighter than ~50 px radius
            a0 = math.atan2(pts[(i + 1) % n][1] - pts[i][1], pts[(i + 1) % n][0] - pts[i][0])
            a1 = math.atan2(pts[(i + 2) % n][1] - pts[(i + 1) % n][1], pts[(i + 2) % n][0] - pts[(i + 1) % n][0])
            if abs(angle_diff(a0, a1)) > TRACK_STEP / 50:
                return False
        # separate parts of the loop must not touch (checked on every other sample)
        p = pts[::2]
        m = len(p)
        skip = 200 // (TRACK_STEP * 2)
        gap = (TRACK_W + 34) ** 2
        for i in range(m):
            xi, yi = p[i]
            for j in range(i + skip, min(m, i + m - skip + 1)):
                if (p[j][0] - xi) ** 2 + (p[j][1] - yi) ** 2 < gap:
                    return False
        return True

    def dist2(self, x, y):
        return min((px - x) ** 2 + (py - y) ** 2 for px, py in self.pts)

    def nearest(self, x, y, seg, span=24):
        """Closest centerline index near `seg` (a local search, so shortcuts don't count)."""
        best, bd = seg, 1e18
        for k in range(seg - span, seg + span + 1):
            px, py = self.pts[k % self.n]
            d = (px - x) ** 2 + (py - y) ** 2
            if d < bd:
                best, bd = k % self.n, d
        return best, bd

    def onroad(self, x, y):
        xi, yi = int(x), int(y)
        return 0 <= xi < W and 0 <= yi < H and self.mask.get_at((xi, yi))

    def grid_pos(self, k):
        """Starting slot k: two abreast, staggered, behind the line. Returns x, y, angle, index, progress."""
        row, col = divmod(k, 2)
        back = 4 + row * 5 + col * 2
        i = -back % self.n
        side = (col * 2 - 1) * 17
        return self.pts[i][0] + self.nx[i] * side, self.pts[i][1] + self.ny[i] * side, self.ang[i], i, -back

    def decal(self, surf, x, y):
        self.surface.blit(surf, surf.get_rect(center=(round(x), round(y))))

    def render(self):
        s = pygame.Surface((W, H))
        s.fill(GRASS)
        for i in range(-H, W + H, 70):   # mowing stripes
            pygame.draw.polygon(s, lerp_color(GRASS, (255, 255, 255), 0.05), [(i, HUD), (i + 35, HUD), (i + 35 + H, H), (i + H, H)])
        for _ in range(2500):
            sh = random.randint(-16, 10)
            s.fill(lerp_color(GRASS, (0, 0, 0) if sh < 0 else (255, 255, 255), abs(sh) / 100),
                   (random.randint(0, W), random.randint(HUD, H), 2, 2))
        hw = TRACK_W / 2
        for x, y in self.pts:   # dirt verge
            pygame.draw.circle(s, (104, 92, 64), (x, y), hw + 7)
        n = self.n
        for i in range(n):      # red and white curbs
            j = (i + 1) % n
            col = (215, 40, 35) if (i // 2) % 2 else (235, 235, 235)
            for side in (-1, 1):
                quad = [(self.pts[a][0] + self.nx[a] * side * r, self.pts[a][1] + self.ny[a] * side * r)
                        for a, r in ((i, hw - 5), (i, hw + 2), (j, hw + 2), (j, hw - 5))]
                pygame.draw.polygon(s, col, quad)
        road = pygame.Surface((W, H), pygame.SRCALPHA)
        for x, y in self.pts:
            pygame.draw.circle(s, ASPHALT, (x, y), hw - 5)
            pygame.draw.circle(road, (255, 255, 255), (x, y), hw)
        self.mask = pygame.mask.from_surface(road)
        for _ in range(5000):
            x, y = random.randint(0, W - 1), random.randint(HUD, H - 1)
            if self.mask.get_at((x, y)):
                sh = random.randint(-10, 12)
                s.fill(lerp_color(ASPHALT, (0, 0, 0) if sh < 0 else (255, 255, 255), abs(sh) / 100), (x, y, 2, 2))
        for k in range(MAX_PLAYERS):   # grid slot markings
            x, y, a, _, _ = self.grid_pos(k)
            ca, sa = math.cos(a), math.sin(a)
            fx, fy = x + ca * 10, y + sa * 10
            pygame.draw.line(s, (220, 220, 220), (fx + sa * 9, fy - ca * 9), (fx - sa * 9, fy + ca * 9), 2)
        cs = pygame.Surface((8, TRACK_W - 8))
        for yy in range(0, TRACK_W - 8, 4):
            for xx in (0, 4):
                cs.fill((240, 240, 240) if (xx // 4 + yy // 4) % 2 else (20, 20, 20), (xx, yy, 4, 4))
        blit_center(s, pygame.transform.rotate(cs, -math.degrees(self.ang[0])), *self.pts[0])
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        for rp in self.ramps:
            self.draw_ramp(s, shade, rp)
        for x, y, _ in self.trees:
            s.blit(self.tree_shadow, (x - 9, y - 5))
        s.blit(self.vignette, (0, HUD))
        self.surface = s.convert()

    def draw_ramp(self, s, shade, rp):
        """Pseudo-3D wedge: raised points are drawn `height` px higher on screen."""
        x, y, c, sn, _ = rp
        hw = TRACK_W / 2 - 3
        nx, ny = -sn, c
        L0, L1 = (x - nx * hw, y - ny * hw), (x + nx * hw, y + ny * hw)
        G0 = (L0[0] + c * RAMP_LEN, L0[1] + sn * RAMP_LEN)
        G1 = (L1[0] + c * RAMP_LEN, L1[1] + sn * RAMP_LEN)
        H0, H1 = (G0[0], G0[1] - RAMP_H), (G1[0], G1[1] - RAMP_H)
        shade.fill((0, 0, 0, 0))
        pygame.draw.polygon(shade, (0, 0, 0, 90), [L0, L1, (G1[0] + RAMP_H * 0.6, G1[1] + RAMP_H * 0.5),
                                                   (G0[0] + RAMP_H * 0.6, G0[1] + RAMP_H * 0.5)])
        s.blit(shade, (0, 0))
        # vertical faces that point down-screen are visible
        if sn > 0:
            pygame.draw.polygon(s, (70, 66, 60), [G0, G1, H1, H0])
        if c < 0:
            pygame.draw.polygon(s, (95, 90, 80), [L0, G0, H0])
        if c > 0:
            pygame.draw.polygon(s, (95, 90, 80), [L1, G1, H1])
        for k in range(6):   # hazard-striped slope, brighter towards the lip
            a, b = k / 6, (k + 1) / 6
            quad = [(L0[0] + (H0[0] - L0[0]) * a, L0[1] + (H0[1] - L0[1]) * a),
                    (L1[0] + (H1[0] - L1[0]) * a, L1[1] + (H1[1] - L1[1]) * a),
                    (L1[0] + (H1[0] - L1[0]) * b, L1[1] + (H1[1] - L1[1]) * b),
                    (L0[0] + (H0[0] - L0[0]) * b, L0[1] + (H0[1] - L0[1]) * b)]
            base = (225, 185, 40) if k % 2 == 0 else (45, 42, 40)
            pygame.draw.polygon(s, lerp_color(base, (255, 255, 255), 0.04 * k), quad)
        pygame.draw.line(s, (255, 240, 180), H0, H1, 2)


# ---------------------------------------------------------------- entities

class Player:
    def __init__(self, idx, pad_id):
        self.idx, self.pad_id = idx, pad_id
        self.color, self.cname = PLAYER_COLORS[idx]
        self.sprites = make_tank_sprites(self.color)
        self.score = 0
        self.kills = 0
        self.spawn = None
        self.tank = None
        self.race_cache = {}   # small race-mode sprites, pre-rotated in 5 degree steps

    def race_sprite(self, name, angle):
        step = round(angle / math.tau * 72) % 72
        img = self.race_cache.get((name, step))
        if img is None:
            src = self.sprites['bodies'][name] if isinstance(name, int) else self.sprites[name]
            img = self.race_cache[(name, step)] = pygame.transform.rotozoom(src, -step * 5, RACE_SCALE)
        return img


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
        self.max_hp = TANK_HP
        self.invuln = 0.0
        # race mode
        self.vx = self.vy = 0.0
        self.z = self.vz = 0.0     # height above the ground, for ramps and jumps
        self.ramp = None
        self.seg = 0               # nearest centerline index
        self.dist = 0              # race progress in centerline samples (laps * n + seg)
        self.lap = 0
        self.finished = False
        self.place = 1
        self.lost = 0.0


class Ghoul:
    def __init__(self, kind, x, y):
        self.kind = kind
        self.x, self.y = x, y
        self.hp = GHOUL_HP
        self.regen = 0.0
        self.slow = 0.0
        self.flash = 0.0
        self.attack = 0.0
        self.claw = 0.0
        self.emerge = GHOUL_EMERGE
        self.phase = random.uniform(0, math.tau)
        self.face = 1
        self.dead = False


class Bullet:
    def __init__(self, owner, x, y, a):
        self.owner = owner
        self.x, self.y = x, y
        self.vx, self.vy = math.cos(a) * BULLET_SPEED, math.sin(a) * BULLET_SPEED
        self.age = 0.0
        self.bounces = BULLET_BOUNCES
        self.bounced = False
        self.dead = False
        self.z = 0.0


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
        self.mode = 'versus'
        self.ghouls = []
        self.pickups = []    # [x, y, life] small ammo drops in co-op
        self.ghoul_sprites = {k: make_ghoul_sprites(k) for k in GHOUL_KINDS}
        self.ghoul_shadow = pygame.Surface((26, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(self.ghoul_shadow, (0, 0, 0, 90), (0, 0, 26, 10))
        self.splats = {}
        for kind in ('mummy', 'zombie', 'vampire'):
            sp = pygame.Surface((40, 40), pygame.SRCALPHA)
            col = tuple(int(c * 0.6) for c in GHOUL_COLORS[kind]) + (150,)
            for _ in range(7):
                pygame.draw.circle(sp, col, (random.randint(10, 30), random.randint(10, 30)), random.randint(3, 8))
            self.splats[kind] = sp
        self.text_cache = {}
        self.quiz = None
        self.quiz_clock = 0.0    # seconds played since the last math question
        self.quiz_msg = None     # [text, color]
        self.track = None
        self.spectators = []
        self.gibs = []       # [x, y, vx, vy, z, vz, angle, spin, surf] flying limbs
        self.race_time = 0.0
        self.finishers = 0
        self.spec_sprites = {k: {f: pygame.transform.smoothscale(self.ghoul_sprites[k][('base', f)], (25, 25))
                                 for f in (1, -1)} for k in GHOUL_KINDS}
        self.gib_sprites = {k: make_gib_sprites(k) for k in GHOUL_KINDS}
        self.blood_dot = pygame.Surface((10, 10), pygame.SRCALPHA)
        pygame.draw.circle(self.blood_dot, (130, 8, 12, 180), (5, 5), 4)
        self.spec_shadow = pygame.transform.smoothscale(self.ghoul_shadow, (18, 7))
        self.flow = None
        self.flow_timer = 0.0
        self.wave = 0
        self.wave_break = 0.0
        self.wave_to_spawn = 0
        self.spawn_timer = 0.0
        self.banner = None   # [text, time_left]
        self.best_wave = 0
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
        for lst in (self.bullets, self.particles, self.rings, self.flashes, self.texts, self.wrecks,
                    self.ghouls, self.pickups, self.spectators, self.gibs):
            lst.clear()
        self.crate = None
        self.crate_timer = CRATE_RESPAWN
        self.flow = None
        self.banner = None

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
            p.kills = 0
        self.new_round()

    def make_tank(self, p):
        t = Tank(p, *p.spawn)
        if self.mode == 'coop':
            t.hp = t.max_hp = COOP_TANK_HP
        return t

    def win_score(self):
        return RACE_WIN_SCORE if self.mode == 'race' else WIN_SCORE

    def new_round(self):
        self.round_winner = None
        if self.mode == 'race':
            self.new_race()
            return
        self.arena.generate()
        self.clear_entities()
        corners, sides = CORNER_SPAWNS[:], SIDE_SPAWNS[:]
        random.shuffle(corners)
        random.shuffle(sides)
        spawns = corners + sides
        cx, cy = W / 2, HUD + ROWS * T / 2
        for p, (c, r) in zip(self.players, spawns):
            x, y = tile_center(c, r)
            p.spawn = (x, y, math.atan2(cy - y, cx - x))
            p.tank = self.make_tank(p)
        if self.mode == 'coop':
            self.wave = 0
            self.wave_break = 0.5
            self.wave_to_spawn = 0
        self.start_countdown()

    def new_race(self):
        if self.track is None:
            self.track = Track(self.arena.vignette)
        else:
            self.track.generate()
        self.clear_entities()
        tr = self.track
        for k, p in enumerate(self.players):
            x, y, a, i, prog = tr.grid_pos(k)
            p.spawn = (x, y, a)
            t = p.tank = self.make_tank(p)
            t.seg, t.dist = i, prog
        for x, y in tr.spots:
            gh = Ghoul(random.choice(GHOUL_KINDS), x, y)
            gh.emerge = 0
            gh.face = random.choice((1, -1))
            self.spectators.append(gh)
            tr.decal(self.spec_shadow, x, y + 1)   # spectators stay put, so bake their shadows
        self.race_time = 0.0
        self.finishers = 0
        self.start_countdown()

    def start_countdown(self):
        self.state = 'countdown'
        self.timer = 3.0
        self.last_count = 4
        self.ending = None
        self.paused = False

    # ---- update

    def update(self, dt):
        self.now += dt
        self.shake = max(0.0, self.shake - dt * 1.8)
        if self.quiz:
            self.update_quiz(dt)
            return
        if self.quiz_clock >= QUIZ_INTERVAL and self.at_break():
            self.quiz = Quiz()
            self.quiz_msg = None
            self.sounds.play('wave')
            return

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
        if self.state in ('countdown', 'play'):
            self.quiz_clock += dt

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
                if any(p.score >= self.win_score() for p in self.players):
                    self.state = 'matchover'
                    self.timer = 1.5
                else:
                    self.new_round()
        elif self.state in ('matchover', 'coopover'):
            self.timer -= dt
            if self.timer <= 0 and any(('a' in pd.pressed or 'start' in pd.pressed) for pd in self.pads.values()):
                self.to_lobby()

        self.go_timer = max(0.0, self.go_timer - dt)
        if self.mode == 'race':
            self.update_race(dt)
        else:
            self.update_tanks(dt)
            self.update_bullets(dt)
        self.update_effects(dt)

        if self.banner:
            self.banner[1] -= dt
            if self.banner[1] <= 0:
                self.banner = None
        if self.mode == 'race':
            pass   # update_race handles the finish
        elif self.state == 'play' and self.mode == 'coop':
            self.update_crate(dt)
            self.update_waves(dt)
            self.update_ghouls(dt)
            self.update_pickups(dt)
            if not any(p.tank and p.tank.alive for p in self.players) and self.ending is None:
                self.ending = 1.5
            if self.ending is not None:
                self.ending -= dt
                if self.ending <= 0:
                    self.best_wave = max(self.best_wave, self.wave)
                    self.state = 'coopover'
                    self.timer = 1.5
        elif self.state == 'play':
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

    def at_break(self):
        """Moments where a math question doesn't interrupt the action."""
        if self.state in ('lobby', 'roundover', 'matchover', 'coopover'):
            return True
        return (self.mode == 'coop' and self.state == 'play' and self.wave_break > 0
                and not self.ghouls and self.wave_to_spawn == 0 and self.ending is None)

    def update_quiz(self, dt):
        q = self.quiz
        if q.solved > 0:
            q.solved -= dt
            if q.solved <= 0:
                self.quiz = None
                self.quiz_clock = 0.0
            return
        # anyone can answer: every connected pad and both keyboard halves
        for pad in self.pads.values():
            pr = pad.pressed
            if 'up' in pr:
                q.digits[q.cursor] = (q.digits[q.cursor] + 1) % 10
            if 'down' in pr:
                q.digits[q.cursor] = (q.digits[q.cursor] - 1) % 10
            if 'left' in pr:
                q.cursor = max(0, q.cursor - 1)
            if 'right' in pr:
                q.cursor = min(QUIZ_DIGITS - 1, q.cursor + 1)
            if pr & {'up', 'down', 'left', 'right'}:
                self.sounds.play('empty')
            if pr & {'a', 'start'}:
                self.submit_quiz()
                return

    def submit_quiz(self):
        q = self.quiz
        if q.value() == q.answer:
            q.solved = 1.5
            self.quiz_msg = [random.choice(("Pravilno! Bravo!", "Odlično!", "Pravilno, kar tako naprej!")), (120, 230, 120)]
            self.sounds.play('pickup')
            return
        q.tries += 1
        self.sounds.play('hit')
        if q.tries >= QUIZ_TRIES:
            unit = f" {q.unit}" if q.unit else ""
            self.quiz_msg = [f"Pravilni odgovor je {fmt(q.answer)}{unit}. Poskusi še to nalogo.", (255, 200, 90)]
            q.new_question()
        else:
            left = QUIZ_TRIES - q.tries
            self.quiz_msg = [f"Ni pravilno. Poskusi znova! Še {left} poskus{'a' if left == 2 else ''}.", (255, 110, 90)]

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
            if 'y' in pad.pressed:
                self.toggle_mode()
            if 'start' in pad.pressed and self.players and (pl or pad.kind.startswith('kb')):
                self.start_match()
                return

    def toggle_mode(self):
        self.mode = {'versus': 'coop', 'coop': 'race', 'race': 'versus'}[self.mode]
        self.sounds.play({'coop': 'groan', 'race': 'go'}.get(self.mode, 'join'))

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
            t.invuln -= dt
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
        race = self.mode == 'race'
        reach = 25 * (RACE_SCALE if race else 1)
        tx = t.x + math.cos(t.turret) * reach
        ty = t.y + math.sin(t.turret) * reach
        blocked = None if race else self.arena.bullet_hit(tx, ty)
        if blocked:
            if blocked[2] == BRICK:
                self.damage_brick(blocked[0], blocked[1])
            self.sparks(tx, ty, (255, 220, 140), 6)
        else:
            b = Bullet(t, tx, ty, t.turret)
            if race:
                b.vx += t.vx
                b.vy += t.vy
                b.z = t.z
            self.bullets.append(b)
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
                if self.mode == 'coop':
                    for gh in self.ghouls:
                        if not gh.dead and gh.emerge <= 0 and (gh.x - b.x) ** 2 + (gh.y - b.y) ** 2 < (GHOUL_R + BULLET_R) ** 2:
                            self.hit_ghoul(gh, b)
                            b.dead = True
                            break
                    if b.dead:
                        break
                    continue
                for t in tanks:
                    if not t.alive or (t is b.owner and not b.bounced):
                        continue
                    if (t.x - b.x) ** 2 + (t.y - b.y) ** 2 < (TANK_R + BULLET_R) ** 2:
                        self.hit_tank(t, b.x, b.y)
                        b.dead = True
                        break
                if b.dead:
                    break
            if not b.dead:
                self.particles.append([b.x, b.y, 0, 0, 0.16, 0.16, 'spark', 2.6, b.owner.player.color])
        # bullets cancel each other out (versus only: teammates shouldn't block each other)
        live = [b for b in self.bullets if not b.dead] if self.mode == 'versus' else []
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                if not a.dead and not b.dead and (a.x - b.x) ** 2 + (a.y - b.y) ** 2 < (BULLET_R * 2.5) ** 2:
                    a.dead = b.dead = True
                    self.sparks((a.x + b.x) / 2, (a.y + b.y) / 2, (255, 255, 200), 10)
                    self.sounds.play('bounce')
        self.bullets = [b for b in self.bullets if not b.dead]

    def hit_tank(self, t, x, y):
        t.hp -= 1
        t.flash = 0.12
        self.sparks(x, y, (255, 230, 150), 12)
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

    # ---- co-op

    def update_waves(self, dt):
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        if not tanks:
            return
        if self.wave_break > 0:
            self.wave_break -= dt
            if self.wave_break <= 0:
                self.start_wave()
            return
        if self.wave_to_spawn > 0:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                self.spawn_ghoul(tanks)
                self.wave_to_spawn -= 1
                self.spawn_timer = max(0.5, 1.6 - 0.06 * self.wave)
        elif not self.ghouls:
            self.wave_break = WAVE_BREAK
            self.banner = [f"WAVE {self.wave} CLEARED", 2.5]
            self.sounds.play('pickup')

    def start_wave(self):
        self.wave += 1
        self.wave_to_spawn = self.wave      # wave N brings N ghouls
        self.spawn_timer = 0.6
        self.banner = [f"WAVE {self.wave}", 2.0]
        self.sounds.play('wave')
        for p in self.players:
            if not (p.tank and p.tank.alive):
                p.tank = self.make_tank(p)
                p.tank.invuln = 2.0
                self.rings.append([p.tank.x, p.tank.y, 0.0, 0.4])
            p.tank.ammo = MAX_AMMO

    def spawn_ghoul(self, tanks):
        if self.flow is None:
            self.flow = self.compute_flow(tanks)
        g = self.arena.grid
        cand = [(c, r) for r in range(1, ROWS - 1) for c in range(1, COLS - 1)
                if g[r][c] == EMPTY and self.flow[r][c] < math.inf]
        far = [cr for cr in cand if all(math.hypot(tile_center(*cr)[0] - t.x, tile_center(*cr)[1] - t.y) > 7 * T for t in tanks)]
        edge = [cr for cr in far if cr[0] in (1, COLS - 2) or cr[1] in (1, ROWS - 2)]
        pool = edge or far or cand
        if not pool:
            return
        x, y = tile_center(*random.choice(pool))
        kind = random.choice(GHOUL_KINDS)
        self.ghouls.append(Ghoul(kind, x, y))
        if kind != 'ghost':
            self.arena.scorch_mark(x, y)
        for _ in range(10):
            self.particles.append([x + random.uniform(-10, 10), y + random.uniform(-6, 10), random.uniform(-15, 15),
                                   random.uniform(-40, -10), 1.0, 1.0, 'smoke', random.uniform(4, 8)])
        self.sounds.play('groan')

    def compute_flow(self, tanks):
        """Dijkstra distance field from every live tank: walkers step downhill, so each follows its closest tank.
        Bricks are passable at a high cost (ghouls claw through them), steel and water are not."""
        g = self.arena.grid
        dist = [[math.inf] * COLS for _ in range(ROWS)]
        heap = []
        for t in tanks:
            c, r, _ = self.arena.tile(t.x, t.y)
            if 0 <= c < COLS and 0 <= r < ROWS:
                dist[r][c] = 0
                heap.append((0, c, r))
        heapq.heapify(heap)
        while heap:
            d, c, r = heapq.heappop(heap)
            if d > dist[r][c]:
                continue
            for nc, nr in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
                v = g[nr][nc]
                if v in (STEEL, WATER):
                    continue
                nd = d + (6 if v == BRICK else 1)
                if nd < dist[nr][nc]:
                    dist[nr][nc] = nd
                    heapq.heappush(heap, (nd, nc, nr))
        return dist

    def ghoul_step_target(self, gh, nearest):
        """Where a walker heads next: straight at a close tank, else the downhill neighbour tile (maybe a brick)."""
        if math.hypot(nearest.x - gh.x, nearest.y - gh.y) < 1.5 * T:
            return nearest.x, nearest.y, None
        g = self.arena.grid
        c, r, _ = self.arena.tile(gh.x, gh.y)
        if not (0 < c < COLS - 1 and 0 < r < ROWS - 1) or self.flow[r][c] == math.inf:
            return nearest.x, nearest.y, None
        best, bd = None, self.flow[r][c]
        open_ = (EMPTY, BUSH)
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nc, nr = c + dc, r + dr
            if dc and dr and (g[r][nc] not in open_ or g[nr][c] not in open_):
                continue   # no corner cutting
            if self.flow[nr][nc] < bd:
                best, bd = (nc, nr), self.flow[nr][nc]
        if best is None:
            return nearest.x, nearest.y, None
        x, y = tile_center(*best)
        return x, y, best if g[best[1]][best[0]] == BRICK else None

    def update_ghouls(self, dt):
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        for gh in self.ghouls:
            gh.flash -= dt
            gh.slow -= dt
            gh.attack -= dt
            if gh.hp < GHOUL_HP:
                gh.regen += dt
                if gh.regen >= GHOUL_REGEN:
                    gh.regen = 0.0
                    gh.hp += 1
                    self.texts.append(["+1", gh.x, gh.y - 22, 0.0, (120, 230, 120)])
            else:
                gh.regen = 0.0
            if gh.emerge > 0:
                gh.emerge -= dt
                continue
        if not tanks:
            return
        self.flow_timer -= dt
        if self.flow is None or self.flow_timer <= 0:
            self.flow = self.compute_flow(tanks)
            self.flow_timer = 0.25

        for gh in self.ghouls:
            if gh.emerge > 0:
                continue
            speed = GHOUL_SPEED * (GHOUL_SLOW if gh.slow > 0 else 1.0)
            gh.phase += dt * 9 * speed / GHOUL_SPEED
            nearest = min(tanks, key=lambda t: (t.x - gh.x) ** 2 + (t.y - gh.y) ** 2)
            if gh.kind == 'ghost':
                tx, ty, brick = nearest.x, nearest.y, None
            else:
                tx, ty, brick = self.ghoul_step_target(gh, nearest)
            dx, dy = tx - gh.x, ty - gh.y
            d = math.hypot(dx, dy)
            if d > 1:
                gh.x += dx / d * speed * dt
                gh.y += dy / d * speed * dt
                if abs(dx) > 2:
                    gh.face = 1 if dx > 0 else -1
            if gh.kind != 'ghost':
                gh.x, gh.y = self.arena.collide_circle(gh.x, gh.y, GHOUL_R)
                if brick and d < T / 2 + GHOUL_R + 4:
                    gh.claw -= dt
                    if gh.claw <= 0:
                        gh.claw = 1.2
                        self.damage_brick(*brick)
            for t in tanks:
                dx, dy = gh.x - t.x, gh.y - t.y
                d = math.hypot(dx, dy) or 0.01
                if d < TANK_R + GHOUL_R:
                    gh.x = t.x + dx / d * (TANK_R + GHOUL_R)
                    gh.y = t.y + dy / d * (TANK_R + GHOUL_R)
                    if gh.attack <= 0 and t.invuln <= 0 and t.alive:
                        gh.attack = GHOUL_ATTACK_CD
                        t.invuln = TANK_HIT_INVULN
                        self.hit_tank(t, (t.x + gh.x) / 2, (t.y + gh.y) / 2)
                        tanks = [tk for tk in tanks if tk.alive]
                        if not tanks:
                            return
        # ghouls shouldn't stack on top of each other
        for i, a in enumerate(self.ghouls):
            for b in self.ghouls[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                if 0 < d < GHOUL_R * 2:
                    push = (GHOUL_R * 2 - d) / 2
                    a.x -= dx / d * push
                    a.y -= dy / d * push
                    b.x += dx / d * push
                    b.y += dy / d * push
        for gh in self.ghouls:
            if gh.kind != 'ghost':
                gh.x, gh.y = self.arena.collide_circle(gh.x, gh.y, GHOUL_R)

    def hit_ghoul(self, gh, b):
        gh.hp -= 1
        gh.slow = GHOUL_SLOW_TIME
        gh.flash = 0.1
        gh.x += b.vx * 0.012   # small knockback
        gh.y += b.vy * 0.012
        if gh.kind != 'ghost':
            gh.x, gh.y = self.arena.collide_circle(gh.x, gh.y, GHOUL_R)
        self.sparks(b.x, b.y, GHOUL_COLORS[gh.kind], 10)
        for _ in range(4):
            self.particles.append([gh.x + random.uniform(-8, 8), gh.y + random.uniform(-8, 8), random.uniform(-20, 20),
                                   random.uniform(-20, 20), 0.5, 0.5, 'spark', 2.5, (150, 200, 255)])
        if gh.hp <= 0:
            self.kill_ghoul(gh, b.owner.player)
        else:
            self.sounds.play('ghoulhit')

    def kill_ghoul(self, gh, player):
        gh.dead = True
        self.ghouls.remove(gh)
        player.kills += 1
        col = GHOUL_COLORS[gh.kind]
        if gh.kind in self.splats:
            self.arena.decal(self.splats[gh.kind], gh.x, gh.y)
        for _ in range(22):
            a = random.uniform(0, math.tau)
            sp = random.uniform(40, 200)
            self.particles.append([gh.x, gh.y, math.cos(a) * sp, math.sin(a) * sp, 0.7, 0.7, 'debris', random.uniform(3, 6), col])
        for _ in range(8):
            self.particles.append([gh.x, gh.y, random.uniform(-30, 30), random.uniform(-40, 0), 1.0, 1.0, 'smoke', random.uniform(5, 9)])
        self.flashes.append([gh.x, gh.y, 0.0, 0.25, 50])
        self.sounds.play('splat')
        self.rumble(player, 0.3, 0.4, 120)
        if random.random() < AMMO_DROP_CHANCE:
            self.pickups.append([gh.x, gh.y, 8.0])

    def update_pickups(self, dt):
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        for pk in self.pickups:
            pk[2] -= dt
            for t in tanks:
                if math.hypot(t.x - pk[0], t.y - pk[1]) < TANK_R + 10:
                    t.ammo = min(MAX_AMMO, t.ammo + AMMO_DROP)
                    pk[2] = 0
                    self.sounds.play('pickup')
                    self.texts.append([f"+{AMMO_DROP}", pk[0], pk[1] - 16, 0.0, (255, 220, 100)])
                    break
        self.pickups = [pk for pk in self.pickups if pk[2] > 0]

    # ---- race

    def update_race(self, dt):
        if self.state == 'play':
            self.race_time += dt
        self.update_race_tanks(dt)
        self.update_race_bullets(dt)
        self.update_spectators(dt)
        self.update_gibs(dt)
        tanks = [p.tank for p in self.players if p.tank]
        live = sorted((t for t in tanks if not t.finished), key=lambda t: -t.dist)
        for k, t in enumerate(live):
            t.place = self.finishers + k + 1
        if self.state == 'play' and self.ending is not None:
            self.ending -= dt
            if self.ending <= 0:
                self.state = 'roundover'
                self.timer = 3.0

    def finish(self, t):
        t.finished = True
        self.finishers += 1
        t.place = self.finishers
        p = t.player
        if self.finishers == 1:
            self.round_winner = p
            p.score += 1
            self.banner = [f"{p.cname} WINS!", 2.5]
            self.sounds.play('cheer')
            self.ending = 4.0 if len(self.players) > 1 else 2.0
            for gh in self.spectators:
                gh.attack = 2.0
        else:
            self.texts.append([ORDINALS[t.place - 1], t.x, t.y - 20, 0.0, p.color])
        if self.finishers == len(self.players):
            self.ending = min(self.ending, 1.5)
        self.rumble(p, 0.4, 0.6, 300)

    def update_race_tanks(self, dt):
        can_act = self.state == 'play'
        tr = self.track
        n = tr.n
        tanks = [p.tank for p in self.players if p.tank]
        for t in tanks:
            pad = self.pads.get(t.player.pad_id)
            t.cooldown -= dt
            t.flash -= dt
            t.recoil = max(0.0, t.recoil - 30 * dt)
            t.invuln -= dt
            mx, my = pad.move if pad and can_act and not t.finished else (0.0, 0.0)
            airborne = t.ramp is None and t.z > 0
            road = tr.onroad(t.x, t.y)
            if not airborne:
                mag = min(1.0, math.hypot(mx, my))
                diff = 0.0
                if mag:
                    target = math.atan2(my, mx)
                    t.angle = approach_angle(t.angle, target, RACE_TURN * dt)
                    diff = angle_diff(t.angle, target)
                # velocity in the (new) heading frame: the sideways part is what drifts
                ca, sa = math.cos(t.angle), math.sin(t.angle)
                fwd = t.vx * ca + t.vy * sa
                lat = -t.vx * sa + t.vy * ca
                c = math.cos(diff)
                if mag and c > 0:
                    fwd += RACE_ACCEL * mag * c * dt
                elif mag and c < -0.5 and fwd > 0:
                    fwd = max(0.0, fwd - RACE_BRAKE * mag * dt)
                else:
                    fwd -= math.copysign(min(abs(fwd), 90 * dt), fwd)
                cap = RACE_SPEED if road else RACE_OFFROAD_SPEED
                if fwd > cap:
                    fwd = max(cap, fwd - (200 if road else 600) * dt)
                fwd = max(fwd, -RACE_OFFROAD_SPEED)
                grip = RACE_GRIP * (1.0 if road else 0.7)
                if mag and abs(diff) > 0.5 and abs(fwd) > 180:
                    grip *= RACE_DRIFT_GRIP
                lat *= math.exp(-grip * dt)
                t.vx, t.vy = ca * fwd - sa * lat, sa * fwd + ca * lat
                moved = math.hypot(t.vx, t.vy) * dt
                t.tread_phase += moved
                if t.z <= 0:
                    if abs(lat) > 70:   # skid marks and tyre smoke
                        for side in (-1, 1):
                            tr.decal(tr.skid, t.x - ca * 6 - sa * 6 * side, t.y - sa * 6 + ca * 6 * side)
                        if abs(lat) > 120 and random.random() < dt * 30:
                            self.particles.append([t.x - ca * 8, t.y - sa * 8, random.uniform(-15, 15), random.uniform(-15, 15),
                                                   0.6, 0.6, 'smoke', random.uniform(3, 5)])
                    if not road and moved > 1.5 and random.random() < dt * 25:
                        self.particles.append([t.x - ca * 8, t.y - sa * 8, -t.vx * 0.2 + random.uniform(-20, 20),
                                               -t.vy * 0.2 + random.uniform(-20, 20), 0.4, 0.4, 'debris', 3, (95, 75, 45)])
            else:
                t.vz -= GRAVITY * dt
                t.z += t.vz * dt
                if t.z <= 0:
                    t.z = 0.0
                    if t.vz < -120:
                        self.sounds.play('land')
                        self.shake = max(self.shake, min(0.3, -t.vz / 900))
                        self.rumble(t.player, 0.5, 0.3, 150)
                        for _ in range(10):
                            a = random.uniform(0, math.tau)
                            self.particles.append([t.x, t.y, math.cos(a) * 60, math.sin(a) * 60, 0.5, 0.5, 'smoke', random.uniform(3, 6)])
                    t.vz = 0.0
            t.x += t.vx * dt
            t.y += t.vy * dt

            # ramps lift a tank while it drives up them and launch it off the lip
            on = None
            if t.z <= RAMP_H + 4:
                for rp in tr.ramps:
                    dx, dy = t.x - rp[0], t.y - rp[1]
                    al = dx * rp[2] + dy * rp[3]
                    if 0 <= al <= RAMP_LEN and abs(dy * rp[2] - dx * rp[3]) <= TRACK_W / 2:
                        h = al / RAMP_LEN * RAMP_H
                        if t.vx * rp[2] + t.vy * rp[3] > 30 and t.z <= h + 4:
                            on = (rp, h)
            if on:
                t.ramp, t.z, t.vz = on[0], on[1], 0.0
            elif t.ramp is not None:
                rp, t.ramp = t.ramp, None
                along = t.vx * rp[2] + t.vy * rp[3]
                if (t.x - rp[0]) * rp[2] + (t.y - rp[1]) * rp[3] > RAMP_LEN - 4 and along > 60:
                    t.vz = along * RAMP_KICK
                    self.sounds.play('jump')
                    for gh in self.spectators:
                        if (gh.x - t.x) ** 2 + (gh.y - t.y) ** 2 < 250 ** 2:
                            gh.attack = 1.2

            if t.z < 20:   # trees
                for x, y, _ in tr.trees:
                    dx, dy = t.x - x, t.y - y
                    d = math.hypot(dx, dy) or 0.01
                    if d < RACE_TANK_R + 9:
                        nx, ny = dx / d, dy / d
                        t.x, t.y = x + nx * (RACE_TANK_R + 9), y + ny * (RACE_TANK_R + 9)
                        vn = t.vx * nx + t.vy * ny
                        if vn < 0:
                            t.vx -= 1.4 * vn * nx
                            t.vy -= 1.4 * vn * ny
                            if vn < -100:
                                self.sounds.play('bump')
                                self.sparks(x + nx * 9, y + ny * 9, (120, 90, 50), 6)
            r = RACE_TANK_R
            if not r <= t.x <= W - r:
                t.x, t.vx = clamp(t.x, r, W - r), -t.vx * 0.4
            if not HUD + r <= t.y <= H - r:
                t.y, t.vy = clamp(t.y, HUD + r, H - r), -t.vy * 0.4

            # progress along the track (local search, so cutting across the infield gains nothing)
            i, d2 = tr.nearest(t.x, t.y, t.seg)
            t.dist += (i - t.seg + n // 2) % n - n // 2
            t.seg = i
            lap = t.dist // n
            if lap > t.lap and not t.finished:
                t.lap = lap
                if lap >= RACE_LAPS:
                    self.finish(t)
                else:
                    t.ammo = MAX_AMMO
                    self.sounds.play('pickup')
                    self.texts.append([f"LAP {lap + 1}", t.x, t.y - 20, 0.0, t.player.color])
            far = d2 > (TRACK_W / 2 + 60) ** 2 and t.z <= 0
            t.lost = t.lost + dt if far else 0.0
            if t.lost > RACE_LOST_TIME:
                t.x, t.y = tr.pts[t.seg]
                t.angle = t.turret = tr.ang[t.seg]
                t.vx = t.vy = t.vz = t.z = 0.0
                t.lost = 0.0
                t.invuln = 1.5
                self.rings.append([t.x, t.y, 0.0, 0.35])
                self.sounds.play('join')

            if pad and pad.aim is not None:
                t.turret = approach_angle(t.turret, pad.aim, TURRET_SPEED * dt)
            elif pad and pad.turret_rot:
                t.turret += pad.turret_rot * KB_TURRET_SPEED * dt
            if can_act and not t.finished and pad and 'fire' in pad.held and t.cooldown <= 0:
                if t.ammo <= 0:
                    t.cooldown = FIRE_COOLDOWN
                    self.sounds.play('empty')
                elif sum(1 for b in self.bullets if b.owner is t) < MAX_BULLETS:
                    self.fire(t)

        # tanks bounce off each other (equal masses, slightly elastic)
        for i, a in enumerate(tanks):
            for b in tanks[i + 1:]:
                if abs(a.z - b.z) > 12:
                    continue
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                if 0 < d < RACE_TANK_R * 2:
                    nx, ny = dx / d, dy / d
                    push = (RACE_TANK_R * 2 - d) / 2
                    a.x, a.y = a.x - nx * push, a.y - ny * push
                    b.x, b.y = b.x + nx * push, b.y + ny * push
                    rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
                    if rel < 0:
                        j = rel * 0.85
                        a.vx, a.vy = a.vx + nx * j, a.vy + ny * j
                        b.vx, b.vy = b.vx - nx * j, b.vy - ny * j
                        if rel < -120:
                            self.sounds.play('bump')
                            self.sparks(a.x + nx * RACE_TANK_R, a.y + ny * RACE_TANK_R, (255, 220, 150), 5)

    def update_race_bullets(self, dt):
        tanks = [p.tank for p in self.players if p.tank]
        trees = self.track.trees
        for b in self.bullets:
            b.age += dt
            if b.age > RACE_BULLET_LIFE or not (0 <= b.x <= W and HUD <= b.y <= H):
                b.dead = True
                continue
            steps = max(1, math.ceil(math.hypot(b.vx, b.vy) * dt / 5))
            sdt = dt / steps
            for _ in range(steps):
                b.x += b.vx * sdt
                b.y += b.vy * sdt
                if b.z < 20 and any((b.x - x) ** 2 + (b.y - y) ** 2 < 81 for x, y, _ in trees):
                    self.sparks(b.x, b.y, (150, 120, 70), 6)
                    b.dead = True
                    break
                for gh in self.spectators:
                    if b.z < 16 and (gh.x - b.x) ** 2 + (gh.y - b.y) ** 2 < (8 + BULLET_R) ** 2:
                        self.kill_spectator(gh, b.owner.player, b.vx, b.vy)
                        b.dead = True
                        break
                if b.dead:
                    break
                for t in tanks:
                    if t is b.owner or abs(t.z - b.z) > 12:
                        continue
                    if (t.x - b.x) ** 2 + (t.y - b.y) ** 2 < (RACE_TANK_R + BULLET_R) ** 2:
                        self.bump_tank(t, b)
                        b.dead = True
                        break
                if b.dead:
                    break
            if not b.dead:
                self.particles.append([b.x, b.y - b.z, 0, 0, 0.12, 0.12, 'spark', 2.0, b.owner.player.color])
        self.bullets = [b for b in self.bullets if not b.dead]

    def bump_tank(self, t, b):
        """Race hits do no damage: they shove the tank, spin it a little and pop it off the ground."""
        sp = math.hypot(b.vx, b.vy) or 1.0
        t.vx += b.vx / sp * RACE_BUMP
        t.vy += b.vy / sp * RACE_BUMP
        t.angle += random.uniform(-0.6, 0.6)
        if t.z <= 0 and t.ramp is None:
            t.z, t.vz = 0.01, 110.0
        t.flash = 0.12
        self.sparks(b.x, b.y - b.z, (255, 230, 150), 10)
        self.shake = max(self.shake, 0.1)
        self.sounds.play('bump')
        self.rumble(t.player, 0.5, 0.7, 180)

    def update_spectators(self, dt):
        tanks = [p.tank for p in self.players if p.tank]
        for gh in self.spectators[:]:
            gh.attack -= dt
            near, nd = None, 170 ** 2
            for t in tanks:
                d = (t.x - gh.x) ** 2 + (t.y - gh.y) ** 2
                if t.z < 10 and d < (RACE_TANK_R + 8) ** 2:
                    self.kill_spectator(gh, t.player, t.vx, t.vy)
                    t.vx *= 0.85
                    t.vy *= 0.85
                    break
                if d < nd:
                    near, nd = t, d
            else:
                if near:   # cheer at passing tanks
                    gh.attack = max(gh.attack, 0.4)
                    gh.face = 1 if near.x > gh.x else -1

    def kill_spectator(self, gh, player, vx, vy):
        self.spectators.remove(gh)
        player.kills += 1
        sp = math.hypot(vx, vy)
        dx, dy = (vx / sp, vy / sp) if sp > 1 else (random.uniform(-1, 1), random.uniform(-1, 1))
        self.track.decal(make_blood_splat(dx, dy), gh.x, gh.y)
        base = math.atan2(dy, dx)
        for surf in self.gib_sprites[gh.kind]:
            a = base + random.uniform(-1.2, 1.2)
            s = random.uniform(70, 220)
            self.gibs.append([gh.x, gh.y, math.cos(a) * s, math.sin(a) * s, 6.0, random.uniform(120, 260),
                              random.uniform(0, 360), random.uniform(-900, 900), surf])
        for _ in range(16):
            a = base + random.gauss(0, 0.8)
            s = random.uniform(60, 240)
            self.particles.append([gh.x, gh.y - 6, math.cos(a) * s, math.sin(a) * s, 0.35, 0.35, 'spark',
                                   random.uniform(1.5, 3), (190, 15, 20)])
        self.texts.append([random.choice(("SPLAT!", "SQUISH!", "OOPS!")), gh.x, gh.y - 20, 0.0, (230, 40, 40)])
        self.sounds.play('splat')
        self.rumble(player, 0.3, 0.4, 120)
        for other in self.spectators:   # the crowd notices
            if (other.x - gh.x) ** 2 + (other.y - gh.y) ** 2 < 120 ** 2:
                other.attack = 1.0

    def update_gibs(self, dt):
        tr = self.track
        for g in self.gibs:
            g[0] += g[2] * dt
            g[1] += g[3] * dt
            g[5] -= GRAVITY * dt
            g[4] += g[5] * dt
            g[6] += g[7] * dt
            if random.random() < dt * 20:
                self.particles.append([g[0], g[1] - g[4], 0, 0, 0.25, 0.25, 'spark', 1.5, (170, 10, 15)])
            if g[4] <= 0:
                g[4] = 0.0
                tr.decal(self.blood_dot, g[0], g[1])
                if g[5] < -150:   # bounce once
                    g[5] *= -0.3
                    g[2] *= 0.5
                    g[3] *= 0.5
                    g[7] *= 0.5
                else:
                    tr.decal(pygame.transform.rotate(g[8], g[6]), g[0], g[1])
                    g[5] = None
        self.gibs = [g for g in self.gibs if g[5] is not None]

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

    def render(self, font, s, color):
        """Font rendering is slow, so labels drawn every frame are cached."""
        key = (id(font), s, color)
        img = self.text_cache.get(key)
        if img is None:
            if len(self.text_cache) > 400:
                self.text_cache.clear()
            img = self.text_cache[key] = font.render(s, True, color)
        return img

    def text(self, s, font, color, center, dst=None, shadow=True):
        dst = dst or self.screen
        img = self.render(font, s, color)
        rect = img.get_rect(center=center)
        if shadow:
            dst.blit(self.render(font, s, (0, 0, 0)), rect.move(3, 3))
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

    def draw_ghoul(self, w, gh):
        spr = self.ghoul_sprites[gh.kind]
        state = 'white' if gh.flash > 0 else 'slow' if gh.slow > 0 else 'base'
        img = spr[(state, gh.face)]
        ghost = gh.kind == 'ghost'
        bob = math.sin(self.now * 3 + gh.phase) * 3 if ghost else -abs(math.sin(gh.phase)) * 2
        ang = 0 if ghost else math.sin(gh.phase) * 8
        scale = 1.0 - max(0.0, gh.emerge) / GHOUL_EMERGE
        if scale <= 0.05:
            return
        sh = self.ghoul_shadow if not ghost else pygame.transform.rotozoom(self.ghoul_shadow, 0, 0.7)
        blit_center(w, sh, gh.x, gh.y + (16 if ghost else 13))
        blit_center(w, pygame.transform.rotozoom(img, ang, scale), gh.x, gh.y - 2 + bob)
        if gh.hp < GHOUL_HP and gh.emerge <= 0:
            for i in range(GHOUL_HP):
                self.world.fill((220, 60, 50) if i < gh.hp else (60, 60, 65), (gh.x - 14 + i * 6, gh.y - 26, 5, 4))

    def draw_race_tank(self, dst, t):
        p = t.player
        white = t.flash > 0
        body = 'body_white' if white else int(t.tread_phase / 1.2) % 4
        turret = 'turret_white' if white else 'turret'
        y = t.y - t.z
        rx = t.x - math.cos(t.turret) * t.recoil * RACE_SCALE
        ry = y - math.sin(t.turret) * t.recoil * RACE_SCALE
        if t.z < 1:
            blit_center(dst, p.race_sprite(body, t.angle), t.x, y)
            blit_center(dst, p.race_sprite(turret, t.turret), rx, ry)
        else:   # airborne tanks grow as they get closer to the camera
            sc = RACE_SCALE * (1 + t.z / 70)
            src = p.sprites['bodies'][body] if isinstance(body, int) else p.sprites[body]
            blit_center(dst, pygame.transform.rotozoom(src, -math.degrees(t.angle), sc), t.x, y)
            blit_center(dst, pygame.transform.rotozoom(p.sprites[turret], -math.degrees(t.turret), sc), rx, ry)

    def draw_race_world(self, w):
        tr = self.track
        w.blit(tr.surface, (0, 0))
        tanks = [p.tank for p in self.players if p.tank]
        # shadows first: they stay on the ground while things above them jump
        for t in tanks:
            blit_center(w, t.player.race_sprite('shadow', t.angle), t.x + 2 + t.z * 0.35, t.y + 3 + t.z * 0.2)
        for g in self.gibs:
            pygame.draw.circle(w, (30, 40, 25), (g[0] + g[4] * 0.3, g[1] + 1), 3)
        # everything standing on the ground is drawn back to front
        objs = [(y, 0, (x, y, v)) for x, y, v in tr.trees]
        objs += [(gh.y, 1, gh) for gh in self.spectators]
        air = []
        for t in tanks:
            if t.invuln > 0 and t.flash <= 0 and int(self.now * 12) % 2:
                continue
            (air if t.z > RAMP_H + 2 else objs).append((t.y, 2, t))
        objs.sort(key=lambda o: o[0])
        for _, kind, o in objs:
            if kind == 0:
                img = tr.tree_sprites[o[2]]
                w.blit(img, (o[0] - 18, o[1] - 42))
            elif kind == 1:
                ghost = o.kind == 'ghost'
                if o.attack > 0:
                    hop = abs(math.sin(self.now * 11 + o.phase)) * 7
                else:
                    hop = abs(math.sin(self.now * 2 + o.phase)) * 1.5
                if ghost:
                    hop += 4 + math.sin(self.now * 3 + o.phase) * 2
                blit_center(w, self.spec_sprites[o.kind][o.face], o.x, o.y - 10 - hop)
            else:
                self.draw_race_tank(w, o)
        for b in self.bullets:
            col = b.owner.player.color
            y = b.y - b.z
            add_glow(w, tuple(c // 2 for c in col), b.x, y, 12)
            pygame.draw.circle(w, col, (b.x, y), BULLET_R)
            pygame.draw.circle(w, (255, 255, 255), (b.x, y), 2)
        self.draw_particles(w)
        for g in self.gibs:
            blit_center(w, pygame.transform.rotate(g[8], g[6]), g[0], g[1] - g[4])
        for _, _, t in sorted(air, key=lambda o: o[0]):
            self.draw_race_tank(w, t)
        for x, y, t, mt, rad in self.flashes:
            k = 1 - t / mt
            add_glow(w, (int(255 * k), int(200 * k), int(120 * k)), x, y, rad)
        for t in tanks:   # place above each tank
            if self.state in ('play', 'roundover') and len(tanks) > 1:
                self.text(str(t.place), self.font_tiny, t.player.color, (t.x, t.y - t.z - 17), w, shadow=True)
        for x, y, t, mt in self.rings:
            k = t / mt
            pygame.draw.circle(w, lerp_color((255, 255, 255), (150, 200, 255), k), (x, y), 6 + 40 * k, max(1, int(5 * (1 - k))))
        for s, x, y, t, col in self.texts:
            img = self.font_hud.render(s, True, col)
            img.set_alpha(int(255 * (1 - t)))
            w.blit(img, img.get_rect(center=(round(x), round(y))))

    def draw_world(self):
        w = self.world
        if self.mode == 'race':
            self.draw_race_world(w)
        else:
            self.draw_arena_world(w)
        ox = oy = 0
        if self.shake > 0:
            amp = self.shake * 14
            ox, oy = random.uniform(-amp, amp), random.uniform(-amp, amp)
        self.screen.fill((0, 0, 0))
        self.screen.blit(w, (ox, oy))

    def draw_arena_world(self, w):
        self.arena.draw_ground(w, self.now)
        if self.crate:
            self.draw_crate(w)
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        for pk in self.pickups:
            if pk[2] > 2 or int(pk[2] * 8) % 2:
                blit_center(w, pygame.transform.rotozoom(self.crate_sprite, math.sin(self.now * 3) * 8, 0.6), pk[0], pk[1])
        for gh in self.ghouls:
            if gh.kind != 'ghost':
                self.draw_ghoul(w, gh)
        for t in tanks:
            if t.invuln > 0 and t.flash <= 0 and int(self.now * 12) % 2:
                continue
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
        for gh in self.ghouls:   # ghosts float above walls and bushes
            if gh.kind == 'ghost':
                self.draw_ghoul(w, gh)
        for x, y, t, mt in self.rings:
            k = t / mt
            pygame.draw.circle(w, lerp_color((255, 220, 150), (255, 90, 30), k), (x, y), 10 + 90 * k, max(1, int(7 * (1 - k))))
        for s, x, y, t, col in self.texts:
            img = self.font_hud.render(s, True, col)
            img.set_alpha(int(255 * (1 - t)))
            w.blit(img, img.get_rect(center=(round(x), round(y))))

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
            self.screen.blit(self.render(self.font_hud, f"P{p.idx + 1}", p.color), (x0 + 30, 11))
            t = p.tank
            hp = t.hp if t and t.alive else 0
            ammo = t.ammo if t and t.alive else 0
            if self.mode == 'race':
                lap = clamp(t.lap + 1, 1, RACE_LAPS) if t else 1
                info = "DONE" if t and t.finished else f"LAP {lap}/{RACE_LAPS}"
                self.screen.blit(self.render(self.font_tiny, info, (225, 225, 225)), (x0 + 62, 3))
                if t and len(self.players) > 1:
                    self.screen.blit(self.render(self.font_tiny, ORDINALS[t.place - 1], p.color), (x0 + 128, 3))
            else:
                for i in range(t.max_hp if t else TANK_HP):
                    col = (230, 70, 60) if i < hp else (70, 70, 75)
                    self.screen.fill(col, (x0 + 62 + i * 14, 6, 11, 10))
            empty_flash = t and t.alive and ammo == 0 and int(self.now * 4) % 2
            for i in range(MAX_AMMO):
                col = (230, 185, 70) if i < ammo else ((150, 50, 45) if empty_flash else (60, 60, 65))
                self.screen.fill(col, (x0 + 62 + i * 6, 21, 4, 12))
            if self.mode == 'coop':
                self.screen.blit(self.render(self.font_hud, f"x{p.kills}", (230, 230, 230)), (x0 + 140, 11))
            if self.mode == 'race':
                self.screen.blit(self.render(self.font_tiny, f"x{p.kills}", (230, 60, 55)), (x0 + 184, 13))
            for i in range(self.win_score() if self.mode != 'coop' else 0):
                cx = x0 + 134 + i * 14
                if i < p.score:
                    pygame.draw.circle(self.screen, p.color, (cx, HUD // 2), 5)
                else:
                    pygame.draw.circle(self.screen, (90, 90, 95), (cx, HUD // 2), 5, 2)
            if p.pad_id not in self.pads and int(self.now * 2) % 2:
                img = self.render(self.font_tiny, "NO PAD", (255, 80, 80))
                self.screen.fill((22, 24, 28), (x0 + 60, 2, 66, HUD - 4))
                self.screen.blit(img, img.get_rect(center=(x0 + 92, HUD // 2)))

    def draw_overlay(self):
        cy = HUD + ROWS * T // 2
        if self.mode == 'coop' and self.state in ('countdown', 'play'):
            left = len(self.ghouls) + self.wave_to_spawn
            if self.wave:
                self.text(f"WAVE {self.wave}   •   {left} LEFT", self.font_hud, (230, 220, 200), (W // 2, HUD + 18))
            if self.banner and self.state == 'play':
                self.text(self.banner[0], self.font_big, (200, 255, 170) if "CLEARED" in self.banner[0] else (255, 120, 90), (W // 2, cy))
        if self.mode == 'race' and self.state in ('countdown', 'play'):
            m, s = divmod(self.race_time, 60)
            self.text(f"{int(m)}:{s:04.1f}", self.font_hud, (230, 230, 230), (W // 2, HUD + 18))
            if self.banner and self.state == 'play':
                self.text(self.banner[0], self.font_big, self.round_winner.color if self.round_winner else (255, 255, 255), (W // 2, cy))
        if self.state == 'coopover':
            self.dim(170)
            self.text("THE TANKS HAVE FALLEN", self.font_med, (255, 110, 90), (W // 2, cy - 80))
            total = sum(p.kills for p in self.players)
            self.text(f"Reached wave {self.wave}   •   {total} ghoul{'s' if total != 1 else ''} destroyed",
                      self.font_small, (230, 230, 230), (W // 2, cy - 20))
            parts = [(f"{p.cname} {p.kills}", p.color) for p in self.players]
            imgs = [self.font_small.render(t, True, c) for t, c in parts]
            x = W // 2 - (sum(i.get_width() for i in imgs) + 40 * (len(imgs) - 1)) // 2
            for img in imgs:
                self.screen.blit(img, (x, cy + 25))
                x += img.get_width() + 40
            if self.timer <= 0:
                self.text("Press A to continue", self.font_small, (220, 220, 220), (W // 2, cy + 90))
            return
        if self.state == 'countdown':
            n = max(1, math.ceil(self.timer))
            self.text(str(n), self.font_big, (255, 255, 255), (W // 2, cy))
        elif self.state == 'play' and self.go_timer > 0:
            self.text("GO!", self.font_big, (255, 230, 120), (W // 2, cy))
        elif self.state == 'roundover':
            self.dim(120)
            if self.round_winner:
                what = "RACE" if self.mode == 'race' else "ROUND"
                self.text(f"{self.round_winner.cname} WINS THE {what}", self.font_med, self.round_winner.color, (W // 2, cy - 30))
                if self.mode == 'race':
                    m, s = divmod(self.race_time, 60)
                    splats = sum(p.kills for p in self.players)
                    self.text(f"{int(m)}:{s:04.1f}   •   {splats} spectator{'s' if splats != 1 else ''} splattered so far",
                              self.font_hud, (220, 220, 220), (W // 2, cy + 10))
            else:
                self.text("DRAW!" if len(self.players) > 1 else "ROUND OVER", self.font_med, (230, 230, 230), (W // 2, cy - 30))
            self.draw_scores(cy + 50)
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

    def wrap(self, s, font, width):
        lines, cur = [], ""
        for word in s.split(" "):
            test = f"{cur} {word}" if cur else word
            if font.size(test)[0] > width and cur:
                lines.append(cur)
                cur = word
            else:
                cur = test
        return lines + [cur]

    def draw_quiz(self):
        q = self.quiz
        self.dim(190)
        panel = pygame.Rect(W // 2 - 500, 110, 1000, 500)
        pygame.draw.rect(self.screen, (28, 32, 44), panel, border_radius=18)
        pygame.draw.rect(self.screen, (240, 210, 110), panel, 3, border_radius=18)
        self.text("MATEMATIČNI ODMOR", self.font_med, (240, 210, 110), (W // 2, 160))
        lines = self.wrap(q.text, self.font_med, 900)
        y = 250 - (len(lines) - 1) * 24
        for line in lines:
            self.text(line, self.font_med, (255, 255, 255), (W // 2, y))
            y += 50
        bw, bh, gap = 64, 84, 12
        unit_w = self.font_med.size(q.unit)[0] + 20 if q.unit else 0
        x0 = W // 2 - (QUIZ_DIGITS * bw + (QUIZ_DIGITS - 1) * gap + unit_w) // 2
        by = 360
        lead = True   # leading zeros are drawn dimmed, so the entered number reads naturally
        for i, d in enumerate(q.digits):
            lead = lead and d == 0 and i < QUIZ_DIGITS - 1
            rect = pygame.Rect(x0 + i * (bw + gap), by, bw, bh)
            sel = i == q.cursor and q.solved <= 0
            pygame.draw.rect(self.screen, (50, 56, 72) if sel else (38, 42, 56), rect, border_radius=10)
            pygame.draw.rect(self.screen, (255, 230, 120) if sel else (90, 96, 112), rect, 3, border_radius=10)
            self.text(str(d), self.font_med, (110, 115, 130) if lead else (255, 255, 255), rect.center, shadow=False)
            if sel and int(self.now * 3) % 2 == 0:
                for sgn in (-1, 1):   # up / down arrows on the selected digit
                    ty = rect.centery + sgn * (bh // 2 + 12)
                    pygame.draw.polygon(self.screen, (255, 230, 120),
                                        [(rect.centerx - 9, ty - sgn * 5), (rect.centerx + 9, ty - sgn * 5), (rect.centerx, ty + sgn * 5)])
        if q.unit:
            self.text(q.unit, self.font_med, (220, 220, 220), (x0 + QUIZ_DIGITS * (bw + gap) + unit_w // 2 - 4, by + bh // 2), shadow=False)
        if self.quiz_msg:
            self.text(self.quiz_msg[0], self.font_small, self.quiz_msg[1], (W // 2, 500))
        self.text("Gor / dol: spremeni števko   •   Levo / desno: izberi mesto   •   A ali START: potrdi",
                  self.font_hud, (190, 190, 200), (W // 2, 550), shadow=False)
        self.text("Tipkovnica: številke 0-9, Backspace briše, Enter potrdi", self.font_tiny, (150, 150, 160), (W // 2, 582), shadow=False)

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
        ammo = "refilled every lap" if self.mode == 'race' else "grab the ammo crates to reload"
        self.text(f"{MAX_AMMO} shells per tank - {ammo}", self.font_hud, (230, 200, 110), (W // 2, 236))

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

        if self.mode == 'versus':
            self.text("MODE:  VERSUS  -  last tank standing", self.font_small, (240, 220, 120), (W // 2, 522))
        elif self.mode == 'coop':
            self.text("MODE:  CO-OP  -  survive the undead together", self.font_small, (255, 120, 90), (W // 2, 522))
        else:
            self.text("MODE:  RACE  -  jumps, drifts, and shells that only bump", self.font_small, (120, 210, 255), (W // 2, 522))
        self.text("Y / TAB to switch mode", self.font_tiny, (170, 170, 175), (W // 2, 548), shadow=False)
        n_pads = sum(1 for p in self.pads.values() if p.kind in ('ctrl', 'joy'))
        self.text(f"{n_pads} controller{'s' if n_pads != 1 else ''} connected", self.font_tiny, (150, 150, 155), (W // 2, 568), shadow=False)
        if self.players:
            msg = ("Press START to begin" if len(self.players) > 1 or self.mode != 'versus'
                   else "Press START for solo practice (2+ players for a match)")
            self.text(msg, self.font_small, (255, 255, 255), (W // 2, 590))
        self.text("Keyboard P1: WASD drive, Q/E aim, SPACE join+fire, X leave   •   P2: arrows drive, , . aim, R-CTRL join+fire, DEL leave   •   ENTER start",
                  self.font_tiny, (150, 150, 155), (W // 2, 630), shadow=False)
        goal = {'versus': f"First to {WIN_SCORE} round wins", 'coop': "Wave N brings N ghouls",
                'race': f"{RACE_LAPS} laps, first to {RACE_WIN_SCORE} race wins"}[self.mode]
        self.text(f"{goal}   •   B leave   •   F11 fullscreen   •   ESC quit",
                  self.font_hud, (150, 150, 155), (W // 2, 660), shadow=False)

    def draw(self):
        if self.state == 'lobby':
            self.draw_lobby()
        else:
            self.draw_world()
            self.draw_hud()
            self.draw_overlay()
        if self.quiz:
            self.draw_quiz()

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
                    elif self.quiz and len(e.unicode) == 1 and e.unicode in "0123456789":   # top row and keypad
                        self.quiz.type_digit(int(e.unicode))
                    elif self.quiz and e.key == pygame.K_BACKSPACE:
                        self.quiz.backspace()
                    elif e.key == pygame.K_TAB and self.state == 'lobby' and not self.quiz:
                        self.toggle_mode()
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
