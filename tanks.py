#!/usr/bin/env python3
# Public domain (The Unlicense, see LICENSE): do whatever you want with this.
"""Tank Arena - local multiplayer top-down tank shooter (Linux and Windows, Xbox controllers).

Left stick: drive   Right stick: aim turret   RT / RB / A: fire   LT / LB / X: special weapon
START: begin match / pause   B: leave lobby   BACK (in pause): quit to lobby
Y / TAB in the lobby cycles VERSUS, CO-OP (tanks vs waves of undead) and RACE.
Keyboard (two players): P1 WASD + Q/E turret + SPACE fire + F special + X leave,
P2 arrows + ,/. turret + RCTRL fire + / special + DELETE leave
ENTER starts / pauses. Up to 6 players in total.
F11 toggles fullscreen, ESC returns to lobby / quits.
Every 4 minutes of play a math question (Slovenian, end of 4th grade) appears at the next break between
rounds or waves. Stick/D-pad up/down changes a digit, left/right picks the digit, A or START answers.
"""
import asyncio
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

WEB = sys.platform == 'emscripten'   # running in a browser via pygbag

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
CRATE_RESPAWN = 9.0
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

# co-op bosses: one comes with every BOSS_EVERY-th wave, in BOSS_KINDS order, tougher each time round
BOSS_EVERY = 3
BOSS_KINDS = ('knight', 'spider', 'snake', 'witch')
BOSS_NAMES = {'knight': "PREKLETI VITEZ", 'spider': "PAJKOVA KRALJICA", 'snake': "VELIKA KAČA", 'witch': "ČAROVNICA"}
BOSS_COLORS = {'knight': (160, 120, 230), 'spider': (150, 50, 170), 'snake': (110, 190, 70), 'witch': (150, 230, 100)}
BOSS_TAUNTS = {   # shown on the game over portrait when a boss wins
    'knight': ("Tristo let prekletstva,\nvi pa ste le pločevinke.", "Moj meč se vedno vrne.\nVi se ne boste.",
               "Na kolena pred\nPrekletim vitezom!"),
    'spider': ("Ujeli ste se v mojo mrežo.\nČas je za večerjo.", "Osem nog, osem oči\nin nič usmiljenja.",
               "Kar ostanite.\nMreža je mehka."),
    'snake': ("Sssss... prepočasssni\nssste bili.", "Pogoltnila sssem vasss\nz gosenicami vred.",
              "Dolga sssem, lačna sssem,\nvi pa ssste bili kosssilo."),
    'witch': ("Hi-hi-hi! Moje mucke\nvas lepo pozdravljajo.", "Mijav... BUM!\nHi-hi-hi!",
              "Iz vaših tankov\nbom skuhala juho!"),
}
BOSS_HP = 14
BOSS_HP_GROWTH = 8          # extra hit points each time the bosses come round again
BOSS_R = 19
BOSS_SPEED = TANK_SPEED * 0.66
BOSS_ATTACK_CD = 3.0        # seconds between ranged attacks
BOSS_WINDUP = 0.5           # the boss glows and a line shows where it will throw, so players can dodge
BOSS_RANGE = 14 * T
BOSS_ALIGN = 22             # ranged attacks fly only along a row or column: a tank must be this close to one
SWORD_SPEED = 430
SPIT_SPEED = 380            # spider web balls and snake venom
WEB_LIFE = 15.0
WEB_SLOW = 0.45             # tank speed factor on a web
WEB_MAX = 24
WEB_STUCK = 1.0             # a web ball pins the tank it hits for this long
SNAKE_SEGMENTS = 12
SNAKE_TRAIL_STEP = 3        # px between remembered head positions; segments sit every 5th one
CAT_SPEED = 320
CAT_FUSE = 0.5              # a landed cat hisses this long, then explodes
CAT_RADIUS = 58

# special weapons: lone co-op survivors find one-shot packets, the last-placed versus player gets a rechargeable one
SPECIALS = ('rocket', 'mortar', 'tesla')
SPECIAL_NAMES = {'rocket': "RAKETA", 'mortar': "MINOMET", 'tesla': "TESLA"}
SPECIAL_COLORS = {'rocket': (255, 90, 60), 'mortar': (255, 170, 50), 'tesla': (110, 210, 255)}
SPECIAL_RECHARGE = 7.0
SPECIAL_PACKET_DELAY = 4.0  # co-op: seconds between special weapon packets
SPECIAL_PACKET_LIFE = 12.0
BLAST_DAMAGE = 2
ROCKET_SPEED = 900
ROCKET_RADIUS = 70
MORTAR_MIN, MORTAR_MAX = 90, 520
MORTAR_AIM_SPEED = 400      # how fast the target circle walks out while the button is held
MORTAR_FLIGHT = 1.0
MORTAR_RADIUS = 60
TESLA_RANGE = 180
TESLA_TOUCH = 10            # gap at which two targets count as touching

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
RIDER_SPEED = 285           # the Ghost Rider: a bit slower than a tank at full speed
RIDER_REACH = 150           # how far behind him he can lash
RIDER_LASH_CD = 1.0
RIDER_RESPAWN = 3.0
RIDER_R = 11
SPECTATORS = 50
TREES = 14
GRASS = (62, 110, 52)
ASPHALT = (66, 68, 74)
ORDINALS = ('1.', '2.', '3.', '4.', '5.', '6.')

# math break
QUIZ_INTERVAL = 180.0       # seconds of play between questions
QUIZ_DIGITS = 5
QUIZ_TRIES = 3              # wrong answers before the solution is shown and a new question asked
MAX_PLAYERS = 6

PLAYER_COLORS = [
    ((90, 200, 90), "ZELENI"),
    ((70, 140, 240), "MODRI"),
    ((240, 150, 40), "ORANŽNI"),
    ((220, 80, 200), "ROZA"),
    ((225, 65, 60), "RDEČI"),
    ((230, 210, 60), "RUMENI"),
]
CORNER_SPAWNS = [(2, 2), (COLS - 3, ROWS - 3), (COLS - 3, 2), (2, ROWS - 3)]
SIDE_SPAWNS = [(2, ROWS // 2), (COLS - 3, ROWS // 2)]   # used only with 5-6 players
SPAWNS = CORNER_SPAWNS + SIDE_SPAWNS

KB_MAPS = {
    'kb1': dict(up=pygame.K_w, down=pygame.K_s, left=pygame.K_a, right=pygame.K_d,
                ccw=pygame.K_q, cw=pygame.K_e, fire=pygame.K_SPACE, fire2=pygame.K_f, leave=pygame.K_x),
    'kb2': dict(up=pygame.K_UP, down=pygame.K_DOWN, left=pygame.K_LEFT, right=pygame.K_RIGHT,
                ccw=pygame.K_COMMA, cw=pygame.K_PERIOD, fire=pygame.K_RCTRL, fire2=pygame.K_SLASH, leave=pygame.K_DELETE),
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
    # mostly division and unit conversion, the rest keeps the other topics fresh
    kind = random.choice(('div', 'div', 'div', 'div', 'divword', 'divword', 'units', 'units', 'units', 'units',
                          'units', 'add', 'sub', 'table', 'mul', 'fraction', 'perimeter', 'order', 'round',
                          'missing', 'word'))
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
        q = random.choice((r(21, 9999 // b), r(11, 99), r(101, 999)))
        k = random.choice((1, 1, 10, 100))
        if q * b * k > 99999:
            k = 1
        return random.choice(((f"{fmt(q * b * k)} : {b} = ?", q * k),
                              (f"{fmt(q * b)} : □ = {fmt(q)}", b),
                              (f"{fmt(b * k * 10)} : {k * 10} = ?", b)))[0:2] + ("",)
    if kind == 'divword':
        b, q = r(2, 9), r(3, 25)
        return random.choice((
            (f"{q * b} bonbonov razdelimo med {b} otrok. Koliko bonbonov dobi vsak?", q, ""),
            (f"{q * b} jajc zložimo v škatle po {b}. Koliko škatel napolnimo?", q, ""),
            (f"Vrv dolgo {q * b} m razrežemo na {b} enakih kosov. Kako dolg je en kos?", q, "m"),
            (f"{b} enakih zvezkov stane {q * b} €. Koliko stane en zvezek?", q, "€"),
            (f"Kolesar v {b} urah prevozi {q * b} km. Koliko km prevozi v eni uri?", q, "km"),
            (f"Kolikokrat gre {b} v {q * b}?", q, ""),
            (f"Koliko je polovica od {2 * q * b}?", q * b, ""),
            (f"Koliko je četrtina od {4 * q * b}?", q * b, ""),
        ))
    if kind == 'fraction':
        d = r(2, 10)
        n = d * r(2, 12)
        return f"Koliko je 1/{d} od {n}?", n // d, ""
    if kind == 'units':
        a, b = r(2, 9), r(11, 99)
        return random.choice((
            (f"{a} m {b} cm = ? cm", a * 100 + b, "cm"),
            (f"{a * 100} cm = ? m", a, "m"),
            (f"{a} m = ? dm", a * 10, "dm"),
            (f"{a * 10} mm = ? cm", a, "cm"),
            (f"{a * 1000} m = ? km", a, "km"),
            (f"{a} km {b * 10} m = ? m", a * 1000 + b * 10, "m"),
            (f"{a} m = ? mm", a * 1000, "mm"),
            (f"{a} kg = ? g", a * 1000, "g"),
            (f"{a * 1000} g = ? kg", a, "kg"),
            (f"{a} kg {b * 10} g = ? g", a * 1000 + b * 10, "g"),
            (f"{a} dag = ? g", a * 10, "g"),
            (f"{a * 100} dag = ? kg", a, "kg"),
            (f"{a} t = ? kg", a * 1000, "kg"),
            (f"{a} l {b % 10} dl = ? dl", a * 10 + b % 10, "dl"),
            (f"{a * 10} dl = ? l", a, "l"),
            (f"{a} l = ? ml", a * 1000, "ml"),
            (f"{a} hl = ? l", a * 100, "l"),
            (f"{a % 4 + 1} h {b % 60} min = ? min", (a % 4 + 1) * 60 + b % 60, "min"),
            (f"{a * 60} min = ? h", a, "h"),
            (f"{a} min = ? s", a * 60, "s"),
            (f"{a * 60} s = ? min", a, "min"),
            (f"{a} dni = ? h", a * 24, "h"),
            (f"{a * 24} h = ? dni", a, "dni"),
            (f"{a} € {b} centov = ? centov", a * 100 + b, "centov"),
            (f"{a * 100} centov = ? €", a, "€"),
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
        n8 = lp_noise(0.2)
        self.snd['rocket'] = self.make(0.5, lambda t: n8() * 2.5 * min(1, t * 20) * e(-t * 5), 0.45)
        self.snd['mortar'] = self.make(0.35, lambda t: n3() * 4 * e(-t * 10) + math.sin(tau * 70 * t) * e(-t * 9), 0.55)
        self.snd['zap'] = self.make(0.4, lambda t: ((1 if math.sin(tau * 95 * t) > 0 else -1) * 0.4 + n5() * 1.2)
                                     * (0.6 + 0.4 * math.sin(t * 160)) * e(-t * 6), 0.35)
        self.snd['crate'] = self.make(0.6, lambda t: (math.sin(tau * 880 * t) + 0.5 * math.sin(tau * 1320 * t)) * e(-t * 6), 0.2)
        self.snd['throw'] = self.make(0.3, lambda t: n7() * 2 * math.sin(math.pi * t / 0.3) * (0.6 + 0.4 * math.sin(t * 90)), 0.35)
        self.snd['meow'] = self.make(0.45, lambda t: math.sin(tau * (700 + 500 * math.sin(math.pi * t / 0.45)) * t)
                                     * math.sin(math.pi * t / 0.45) * 0.6, 0.3)
        self.snd['boss'] = self.make(1.3, lambda t: (math.sin(tau * (70 + 10 * math.sin(t * 9)) * t) + n4() * 2)
                                     * min(1, t * 4) * e(-t * 1.8), 0.55)
        self.snd['lash'] = self.make(0.35, lambda t: n1() * 2 * e(-t * 12) + math.sin(tau * (900 - 1800 * t) * t) * e(-t * 9), 0.4)

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

# raw joystick layouts for pads without an SDL mapping: axis and button numbers
XPAD_LAYOUT = {'rx': 3, 'ry': 4, 'lt': 2, 'rt': 5, 'lt_b': None, 'rt_b': None, 'dpad': None,
               'a': 0, 'b': 1, 'x': 2, 'y': 3, 'lb': 4, 'rb': 5, 'back': 6, 'start': 7}
# browsers present pads in the W3C "standard gamepad" layout: triggers are buttons, the D-pad is buttons 12-15
WEB_LAYOUT = {'rx': 2, 'ry': 3, 'lt': None, 'rt': None, 'lt_b': 6, 'rt_b': 7, 'dpad': (12, 13, 14, 15),
              'a': 0, 'b': 1, 'x': 2, 'y': 3, 'lb': 4, 'rb': 5, 'back': 8, 'start': 9}
JOY_LAYOUT = WEB_LAYOUT if WEB else XPAD_LAYOUT


class Pad:
    """One input device: SDL game controller, raw joystick, or a keyboard half."""

    LABELS = {'ctrl': "Kontroler", 'joy': "Igralni plošček", 'kb1': "Tipkovnica WASD", 'kb2': "Tipkovnica puščice"}

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
            if (ax(pygame.CONTROLLER_AXIS_TRIGGERLEFT) > 0.35 or bt(pygame.CONTROLLER_BUTTON_LEFTSHOULDER)
                    or bt(pygame.CONTROLLER_BUTTON_X)):
                held.add('fire2')
            for name, b in (('a', pygame.CONTROLLER_BUTTON_A), ('b', pygame.CONTROLLER_BUTTON_B), ('y', pygame.CONTROLLER_BUTTON_Y),
                            ('start', pygame.CONTROLLER_BUTTON_START), ('back', pygame.CONTROLLER_BUTTON_BACK)):
                if bt(b):
                    held.add(name)
        elif self.kind == 'joy':
            # Fallback for pads SDL has no mapping for: the Linux xpad layout, or in a browser the W3C standard one
            j, lay = self.dev, JOY_LAYOUT
            na, nb = j.get_numaxes(), j.get_numbuttons()
            ax = lambda i: j.get_axis(i) if i is not None and i < na else 0.0
            bt = lambda i: j.get_button(i) if i is not None and i < nb else 0
            mx, my = ax(0), ax(1)
            rx, ry = ax(lay['rx']), ax(lay['ry'])
            if lay['dpad']:
                u, d, l, r = lay['dpad']
                hx, hy = bt(r) - bt(l), bt(u) - bt(d)
            else:
                hx, hy = j.get_hat(0) if j.get_numhats() else (0, 0)
            if hx or hy:
                mx, my = hx, -hy
            if math.hypot(rx, ry) > 0.5:
                aim = math.atan2(ry, rx)
            # trigger axes rest at -1
            if (lay['rt'] is not None and na > lay['rt'] and ax(lay['rt']) > 0.0) or bt(lay['rt_b']) or bt(lay['rb']) or bt(lay['a']):
                held.add('fire')
            if (lay['lt'] is not None and na > lay['lt'] and ax(lay['lt']) > 0.0) or bt(lay['lt_b']) or bt(lay['lb']) or bt(lay['x']):
                held.add('fire2')
            for name in ('a', 'b', 'y', 'start', 'back'):
                if bt(lay[name]):
                    held.add(name)
        else:
            k = KB_MAPS[self.kind]
            mx = keys[k['right']] - keys[k['left']]
            my = keys[k['down']] - keys[k['up']]
            rot = keys[k['cw']] - keys[k['ccw']]
            if keys[k['fire']]:
                held |= {'fire', 'a'}
            if keys[k['fire2']]:
                held.add('fire2')
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


def make_boss_sprites(kind, scale=1):
    """Bosses, drawn like the ghouls but bigger: {(state, facing): surface}, plus extra parts per kind.
    `scale` > 1 draws them that many times larger, for the game over portrait."""
    S = SS if scale == 1 else 2 * scale
    N = 58 if kind == 'witch' else 52
    s = pygame.Surface((N * S, N * S), pygame.SRCALPHA)

    def C(x, y, r, col):
        pygame.draw.circle(s, col, (x * S, y * S), r * S)

    def E(x, y, w, h, col):
        pygame.draw.ellipse(s, col, (x * S, y * S, w * S, h * S))

    def Rr(x, y, w, h, col, br=0):
        pygame.draw.rect(s, col, (x * S, y * S, w * S, h * S), border_radius=br * S)

    def P(pts, col):
        pygame.draw.polygon(s, col, [(x * S, y * S) for x, y in pts])

    def L(pts, col, w):
        pygame.draw.lines(s, col, False, [(x * S, y * S) for x, y in pts], int(w * S))

    extra = {}
    if kind == 'knight':
        steel, dark, light = (120, 118, 140), (70, 68, 88), (175, 175, 195)
        P([(14, 19), (38, 19), (43, 49), (9, 49)], (95, 20, 45))          # cape
        Rr(17, 37, 7, 12, dark, 2)
        Rr(28, 37, 7, 12, dark, 2)
        Rr(13, 21, 26, 20, steel, 6)
        Rr(15, 23, 22, 4, light, 2)
        pygame.draw.line(s, (170, 110, 240), (26 * S, 28 * S), (26 * S, 38 * S), S)   # cursed rune
        pygame.draw.line(s, (170, 110, 240), (22 * S, 32 * S), (30 * S, 32 * S), S)
        Rr(7, 23, 7, 14, dark, 3)
        Rr(38, 23, 7, 14, dark, 3)
        P([(17, 9), (9, 0), (20, 6)], (225, 215, 190))                   # horns
        P([(35, 9), (43, 0), (32, 6)], (225, 215, 190))
        C(26, 14, 10.5, steel)
        C(23, 10, 4, light)
        Rr(17, 12, 18, 4, (15, 12, 20), 1)                               # visor slit
        C(22, 14, 1.6, (255, 70, 60))
        C(30, 14, 1.6, (255, 70, 60))
        sw = pygame.Surface((36 * S, 36 * S), pygame.SRCALPHA)
        pygame.draw.polygon(sw, (205, 210, 228), [(16 * S, 5 * S), (18 * S, 0), (20 * S, 5 * S), (20 * S, 25 * S), (16 * S, 25 * S)])
        pygame.draw.line(sw, (160, 100, 235), (18 * S, 6 * S), (18 * S, 23 * S), S)
        pygame.draw.rect(sw, (205, 165, 60), (10 * S, 25 * S, 16 * S, 3 * S), border_radius=S)
        pygame.draw.rect(sw, (90, 55, 30), (17 * S, 28 * S, 2 * S, 5 * S))
        pygame.draw.circle(sw, (205, 165, 60), (18 * S, 34 * S), 2 * S)
        extra['sword'] = pygame.transform.smoothscale(sw, (36 * scale, 36 * scale)).convert_alpha()
    elif kind == 'spider':
        leg = (40, 22, 48)
        for side in (-1, 1):
            for i in range(4):
                kx, ky = 26 + side * (12 + i), 20 + i * 6
                fx, fy = 26 + side * (23 - abs(i - 1.5)), 26 + i * 8
                L([(26, 28), (kx, ky - 6), (fx, fy)], leg, 2.6)
        C(26, 33, 12, (62, 26, 78))                                      # abdomen
        P([(23, 28), (29, 28), (26, 33), (29, 38), (23, 38), (26, 33)], (215, 30, 40))
        C(26, 19, 8.5, (82, 38, 98))
        for ex, ey, er in ((22, 16, 1.8), (30, 16, 1.8), (24, 19.5, 1.3), (28, 19.5, 1.3), (20, 19, 1), (32, 19, 1)):
            C(ex, ey, er, (255, 60, 70))
        P([(23, 24), (25, 24), (24, 29)], (240, 240, 230))
        P([(27, 24), (29, 24), (28, 29)], (240, 240, 230))
    elif kind == 'snake':
        E(9, 13, 34, 26, (95, 175, 62))
        E(14, 15, 24, 9, (70, 140, 48))
        for x in (17, 26, 33):
            P([(x - 3, 19), (x, 16), (x + 3, 19), (x, 22)], (55, 115, 40))
        C(18, 24, 4, (250, 220, 60))
        C(34, 24, 4, (250, 220, 60))
        Rr(17.3, 21, 1.4, 6, (20, 20, 10))
        Rr(33.3, 21, 1.4, 6, (20, 20, 10))
        C(23, 33, 1, (30, 50, 20))
        C(29, 33, 1, (30, 50, 20))
        L([(26, 38), (26, 44), (23, 48)], (220, 40, 50), 1.4)
        L([(26, 44), (29, 48)], (220, 40, 50), 1.4)
        segs = []
        for i in range(SNAKE_SEGMENTS):
            r = 13 - 6 * i / (SNAKE_SEGMENTS - 1)
            n = int(r * 2 + 4)
            g = pygame.Surface((n * S, n * S), pygame.SRCALPHA)
            c = n * S / 2
            pygame.draw.circle(g, (60, 120, 42), (c, c), r * S)
            pygame.draw.circle(g, (95, 175, 62), (c, c), (r - 1.3) * S)
            pygame.draw.polygon(g, (55, 115, 40), [(c - r * 0.55 * S, c), (c, c - r * 0.55 * S), (c + r * 0.55 * S, c), (c, c + r * 0.55 * S)])
            pygame.draw.circle(g, (150, 210, 110), (c - r * 0.35 * S, c - r * 0.4 * S), r * 0.25 * S)
            segs.append(pygame.transform.smoothscale(g, (n * scale, n * scale)).convert_alpha())
        extra['segs'] = segs
        extra['segs_white'] = []
        for g in segs:
            w = g.copy()
            w.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
            extra['segs_white'].append(w)
    else:
        L([(5, 44), (54, 40)], (120, 80, 40), 3)                         # broom
        P([(0, 38), (10, 41), (11, 46), (1, 51)], (215, 185, 95))
        for k in range(4):
            pygame.draw.line(s, (170, 140, 60), (2 * S, (40 + k * 3) * S), (10 * S, (42 + k) * S), S)
        P([(23, 23), (37, 23), (42, 43), (19, 44)], (105, 40, 145))       # dress
        Rr(36, 27, 9, 4, (105, 40, 145), 2)                              # arm on the broom
        C(45, 30, 2.5, (150, 215, 110))
        C(30, 17, 7.5, (150, 215, 110))
        P([(36, 16), (41, 19), (36, 20)], (120, 185, 90))                # nose
        C(28, 15.5, 1.5, (20, 10, 30))
        C(33, 15.5, 1.5, (20, 10, 30))
        L([(23, 14), (19, 24)], (230, 110, 40), 2)                       # hair
        L([(25, 12), (21, 22)], (230, 110, 40), 2)
        E(16, 9, 29, 6, (28, 22, 34))                                    # hat brim
        P([(23, 11), (38, 11), (35, 3), (28, -1)], (28, 22, 34))
        P([(28, -1), (35, 3), (22, 2)], (28, 22, 34))
        Rr(23, 8, 15, 2.5, (120, 50, 160))
        cat = pygame.Surface((26 * S, 26 * S), pygame.SRCALPHA)
        fur = (32, 30, 38)
        pygame.draw.circle(cat, fur, (13 * S, 16 * S), 8 * S)
        pygame.draw.circle(cat, fur, (13 * S, 9 * S), 6 * S)
        pygame.draw.polygon(cat, fur, [(8 * S, 7 * S), (8 * S, 1 * S), (12 * S, 5 * S)])
        pygame.draw.polygon(cat, fur, [(18 * S, 7 * S), (18 * S, 1 * S), (14 * S, 5 * S)])
        pygame.draw.circle(cat, (200, 240, 80), (10.5 * S, 9 * S), 1.6 * S)
        pygame.draw.circle(cat, (200, 240, 80), (15.5 * S, 9 * S), 1.6 * S)
        pygame.draw.lines(cat, fur, False, [(20 * S, 20 * S), (24 * S, 16 * S), (24 * S, 10 * S)], int(2 * S))
        pygame.draw.circle(cat, (255, 170, 40), (24 * S, 9 * S), 1.8 * S)  # lit fuse
        extra['cat'] = pygame.transform.smoothscale(cat, (26 * scale, 26 * scale)).convert_alpha()

    base = pygame.transform.smoothscale(s, (N * scale, N * scale)).convert_alpha()
    white = base.copy()
    white.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
    out = dict(extra)
    for name, img in (('base', base), ('white', white)):
        out[(name, 1)] = img
        out[(name, -1)] = pygame.transform.flip(img, True, False)
    return out


def make_rider_sprite():
    """Top-down Ghost Rider on his motorcycle, facing +x."""
    S = SS
    s = pygame.Surface((38 * S, 24 * S), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (18, 18, 20), (1 * S, 8 * S, 11 * S, 8 * S))       # back wheel
    pygame.draw.ellipse(s, (18, 18, 20), (27 * S, 8.5 * S, 10 * S, 7 * S))    # front wheel
    pygame.draw.rect(s, (90, 20, 15), (8 * S, 8 * S, 22 * S, 8 * S), border_radius=3 * S)
    pygame.draw.rect(s, (190, 190, 200), (19 * S, 9.5 * S, 7 * S, 5 * S), border_radius=2 * S)   # chrome tank
    pygame.draw.line(s, (160, 160, 170), (28 * S, 3 * S), (28 * S, 21 * S), int(1.6 * S))          # handlebars
    pygame.draw.ellipse(s, (35, 28, 26), (11 * S, 4 * S, 11 * S, 16 * S))     # leather jacket
    pygame.draw.line(s, (35, 28, 26), (18 * S, 6 * S), (28 * S, 4 * S), int(2.4 * S))
    pygame.draw.line(s, (35, 28, 26), (18 * S, 18 * S), (28 * S, 20 * S), int(2.4 * S))
    pygame.draw.circle(s, (240, 235, 215), (18 * S, 12 * S), 4.2 * S)         # skull
    pygame.draw.circle(s, (20, 10, 10), (20 * S, 10.5 * S), 1 * S)
    pygame.draw.circle(s, (20, 10, 10), (20 * S, 13.5 * S), 1 * S)
    for k, col in enumerate(((255, 120, 20), (255, 200, 60))):              # flaming hair
        r = 4.5 - k * 1.8
        pygame.draw.polygon(s, col, [(15 * S, (12 - r) * S), (5 * S + k * 3 * S, 12 * S), (15 * S, (12 + r) * S)])
    return pygame.transform.smoothscale(s, (38, 24)).convert_alpha()


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


def draw_special_icon(s, kind, cx, cy, k):
    """Weapon symbol centred on (cx, cy), k = pixels per unit."""
    col = SPECIAL_COLORS[kind]
    if kind == 'rocket':
        pygame.draw.polygon(s, (230, 230, 235), [(cx - 6 * k, cy - 2 * k), (cx + 4 * k, cy - 2 * k), (cx + 8 * k, cy),
                                                 (cx + 4 * k, cy + 2 * k), (cx - 6 * k, cy + 2 * k)])
        pygame.draw.polygon(s, col, [(cx - 6 * k, cy - 2 * k), (cx - 9 * k, cy - 5 * k), (cx - 3 * k, cy - 2 * k)])
        pygame.draw.polygon(s, col, [(cx - 6 * k, cy + 2 * k), (cx - 9 * k, cy + 5 * k), (cx - 3 * k, cy + 2 * k)])
        pygame.draw.polygon(s, col, [(cx + 4 * k, cy - 2 * k), (cx + 8 * k, cy), (cx + 4 * k, cy + 2 * k)])
    elif kind == 'mortar':
        pygame.draw.circle(s, col, (cx, cy), 7 * k, max(1, int(1.6 * k)))
        pygame.draw.circle(s, col, (cx, cy), 2 * k)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pygame.draw.line(s, col, (cx + dx * 4 * k, cy + dy * 4 * k), (cx + dx * 9 * k, cy + dy * 9 * k), max(1, int(1.6 * k)))
    else:
        pygame.draw.polygon(s, col, [(cx + 2 * k, cy - 8 * k), (cx - 5 * k, cy + 1 * k), (cx, cy + 1 * k),
                                     (cx - 2 * k, cy + 8 * k), (cx + 5 * k, cy - 1 * k), (cx, cy - 1 * k)])


def make_special_sprites(kind):
    """(packet box, small icon) for a special weapon."""
    S = SS
    s = pygame.Surface((30 * S, 30 * S), pygame.SRCALPHA)
    col = SPECIAL_COLORS[kind]
    pygame.draw.rect(s, (40, 42, 50), (0, 0, 30 * S, 30 * S), border_radius=5 * S)
    pygame.draw.rect(s, (75, 80, 92), (2 * S, 2 * S, 26 * S, 26 * S), border_radius=4 * S)
    pygame.draw.rect(s, col, (2 * S, 2 * S, 26 * S, 26 * S), S, border_radius=4 * S)
    draw_special_icon(s, kind, 15 * S, 15 * S, 1.3 * S)
    box = pygame.transform.smoothscale(s, (30, 30)).convert_alpha()
    i = pygame.Surface((20 * S, 20 * S), pygame.SRCALPHA)
    draw_special_icon(i, kind, 10 * S, 10 * S, S)
    return box, pygame.transform.smoothscale(i, (20, 20)).convert_alpha()


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


def blob_outline(gc, gr):
    """Corners of the outline of a random blob of grid cells (in grid units), or None if this try failed.
    The blob has no holes and no cells touching only at a corner, so the outline is one simple loop."""
    cells = {(random.randrange(gc), random.randrange(gr))}
    size = random.randint(gc * gr // 2, gc * gr * 3 // 4)
    while len(cells) < size:
        c, r = random.choice(list(cells))
        dc, dr = random.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        if 0 <= c + dc < gc and 0 <= r + dr < gr:
            cells.add((c + dc, r + dr))
    if len({c for c, _ in cells}) < gc or len({r for _, r in cells}) < gr:
        return None   # use the whole screen
    outside = {(c, r) for c in range(-1, gc + 1) for r in range(-1, gr + 1)} - cells
    seen, stack = {(-1, -1)}, [(-1, -1)]
    while stack:
        c, r = stack.pop()
        for nb in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
            if nb in outside and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    if seen != outside:
        return None
    for c in range(-1, gc):
        for r in range(-1, gr):
            a, b, d, e = (c, r) in cells, (c + 1, r) in cells, (c, r + 1) in cells, (c + 1, r + 1) in cells
            if a == e and b == d and a != b:
                return None
    nxt = {}   # outline edges, walked with the blob on the left
    for c, r in cells:
        if (c, r - 1) not in cells:
            nxt[(c + 1, r)] = (c, r)
        if (c, r + 1) not in cells:
            nxt[(c, r + 1)] = (c + 1, r + 1)
        if (c - 1, r) not in cells:
            nxt[(c, r)] = (c, r + 1)
        if (c + 1, r) not in cells:
            nxt[(c + 1, r + 1)] = (c + 1, r)
    start = next(iter(nxt))
    loop, v = [start], nxt[start]
    while v != start:
        loop.append(v)
        v = nxt[v]
    n = len(loop)
    corners = [loop[i] for i in range(n) if (loop[i][0] - loop[i - 1][0], loop[i][1] - loop[i - 1][1])
               != (loop[(i + 1) % n][0] - loop[i][0], loop[(i + 1) % n][1] - loop[i][1])]
    return corners if len(corners) >= 8 else None


def fillet_loop(corners, max_r):
    """Round every corner of a polygon with right angles into a circular arc, as wide as the legs allow."""
    out, n = [], len(corners)
    for i in range(n):
        a, p, b = corners[i - 1], corners[i], corners[(i + 1) % n]
        la, lb = math.dist(a, p), math.dist(b, p)
        r = min(max_r, la * 0.48, lb * 0.48)
        da = ((a[0] - p[0]) / la, (a[1] - p[1]) / la)
        db = ((b[0] - p[0]) / lb, (b[1] - p[1]) / lb)
        cx, cy = p[0] + (da[0] + db[0]) * r, p[1] + (da[1] + db[1]) * r
        a0 = math.atan2(p[1] + da[1] * r - cy, p[0] + da[0] * r - cx)
        sweep = angle_diff(a0, math.atan2(p[1] + db[1] * r - cy, p[0] + db[0] * r - cx))
        steps = max(4, int(abs(sweep) * r / 3))   # fine enough that resampling doesn't see kinks
        for k in range(steps + 1):
            t = a0 + sweep * k / steps
            out.append((cx + math.cos(t) * r, cy + math.sin(t) * r))
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
        # browsers blit alpha sprites slowly, so there bushes don't sway: they're baked into `ground` and
        # only redrawn where something passes under them
        self.sway = not WEB
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
            if not self.sway:
                self.draw_bushes(self.ground, 0, [rect.center], rect.w / 2)

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
        if not self.sway:   # after the vignette, like bushes drawn each frame
            self.draw_bushes(gr, 0, None)
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

    def draw_bushes(self, dst, now, near=None, reach=30):
        """Draw bushes; without sway, only those within `reach` of a point in `near` (all of them when it's None)."""
        if not self.sway and near is not None:
            cells = {(int(x // T) + dc, int((y - HUD) // T) + dr) for x, y in near
                     for dc in range(-1 - int(reach // T), 2 + int(reach // T))
                     for dr in range(-1 - int(reach // T), 2 + int(reach // T))}
        else:
            cells = None
        for r in range(ROWS):
            for c in range(COLS):
                if self.grid[r][c] == BUSH and (cells is None or (c, r) in cells):
                    sway = math.sin(now * 1.6 + c * 0.8 + r * 0.5) * 1.2 if self.sway else 0
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
        pts = None
        for _ in range(500):
            pts = self.outline_track()
            if pts and self.valid(pts, TRACK_W / 2 + 14):
                break
        else:   # very unlikely: fall back to a simple round loop
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
        if not self.ramps:   # every track gets at least one jump
            return self.generate()

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
    def outline_track():
        """A street circuit: the outline of a random blob of cells on an uneven grid, corners rounded off."""
        gc, gr = random.choice(((8, 4), (7, 4), (6, 3)))
        corners = blob_outline(gc, gr)
        if not corners:
            return None
        m = TRACK_W / 2 + 30
        xs, ys = [0.0], [0.0]
        for _ in range(gc):
            xs.append(xs[-1] + random.uniform(0.85, 1.15))
        for _ in range(gr):
            ys.append(ys[-1] + random.uniform(0.88, 1.12))
        corners = [(m + xs[c] / xs[-1] * (W - 2 * m), HUD + m + ys[r] / ys[-1] * (H - HUD - 2 * m)) for c, r in corners]
        return resample_loop(fillet_loop(corners, random.uniform(60, 120)), TRACK_STEP)

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
        self.rot_cache = {}    # arena sprites, pre-rotated in 3 degree steps (rotating live is slow in browsers)

    def race_sprite(self, name, angle):
        step = round(angle / math.tau * 72) % 72
        img = self.race_cache.get((name, step))
        if img is None:
            src = self.sprites['bodies'][name] if isinstance(name, int) else self.sprites[name]
            img = self.race_cache[(name, step)] = pygame.transform.rotozoom(src, -step * 5, RACE_SCALE)
        return img

    def rotated(self, name, angle):
        step = round(angle / math.tau * 120) % 120
        img = self.rot_cache.get((name, step))
        if img is None:
            src = self.sprites['bodies'][name] if isinstance(name, int) else self.sprites[name]
            img = self.rot_cache[(name, step)] = pygame.transform.rotozoom(src, -step * 3, 1)
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
        self.special = None        # 'rocket' / 'mortar' / 'tesla'
        self.special_recharge = 0.0   # 0 = one shot, else seconds to recharge after use
        self.special_charge = 0.0     # seconds until ready
        self.mortar_aim = None     # target distance while the mortar button is held
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
        self.stuck = 0.0           # co-op: pinned by a spider's web ball


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


class Boss:
    """Co-op boss: bigger and faster than a ghoul, with a ranged attack thrown only along a row or column."""

    def __init__(self, kind, x, y, hp):
        self.kind = kind
        self.x, self.y = x, y
        self.hp = self.max_hp = hp
        self.flash = 0.0
        self.attack = 0.0            # melee cooldown
        self.cool = BOSS_ATTACK_CD   # ranged cooldown
        self.windup = 0.0
        self.aim = None              # (dx, dy, distance) of the throw being wound up
        self.claw = 0.0
        self.emerge = GHOUL_EMERGE * 1.5
        self.phase = 0.0
        self.face = 1
        self.dead = False
        self.armed = True            # knight: sword in hand
        self.trail = [(x, y)]        # snake: recent head positions, newest first
        self.segs = []               # snake: body segment positions, head to tail


class BossShot:
    """Sword (flies out and back along its line), web ball, venom, or a cat lobbed over walls that explodes."""

    def __init__(self, kind, owner, x, y, dx, dy, dist):
        self.kind, self.owner = kind, owner
        self.x, self.y = self.sx, self.sy = x, y
        self.dx, self.dy = dx, dy
        self.dist = max(dist, 1.0)   # how far it flies
        self.done = 0.0              # how far it has flown
        self.back = False            # sword on its way back
        self.fuse = None             # cat: seconds left once landed
        self.z = 0.0
        self.spin = 0.0
        self.hit = []                # tanks the sword already cut on this throw
        self.dead = False


class Rider:
    """Race mode's Ghost Rider: rides the track on a burning motorcycle and lashes anyone tailing him."""

    def __init__(self, idx):
        self.idx = float(idx)        # position along the track, in centerline samples
        self.lane = self.lane_to = 0.0
        self.x = self.y = self.ang = 0.0
        self.dead = 0.0              # seconds until he rides again
        self.cool = 0.0
        self.whip = None             # [x, y, time left] the chain lash being drawn


class Missile:
    """Rocket (flies straight) or mortar round (lobbed over walls to a target point)."""

    def __init__(self, kind, owner, x, y, a, dist=0.0):
        self.kind, self.owner = kind, owner
        self.x, self.y = self.sx, self.sy = x, y
        self.a = a
        self.vx, self.vy = math.cos(a) * ROCKET_SPEED, math.sin(a) * ROCKET_SPEED
        self.tx, self.ty = x + math.cos(a) * dist, y + math.sin(a) * dist
        self.t = 0.0
        self.dur = MORTAR_FLIGHT * (0.6 + 0.4 * dist / MORTAR_MAX)
        self.peak = 60 + dist * 0.3
        self.z = 0.0
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
        self.lobby_cache = None
        self.special_sprites = {k: make_special_sprites(k) for k in SPECIALS}
        self.boss_sprites = {k: make_boss_sprites(k) for k in BOSS_KINDS}
        self.boss_shadow = pygame.transform.smoothscale(self.ghoul_shadow, (40, 15))
        self.bosses = []
        self.boss_shots = []
        self.boss_pending = None   # (kind, hp) of the boss this wave still has to bring
        self.webs = {}             # (col, row) -> seconds left; spider webs slow tanks
        self.rider = None
        self.rider_sprite = make_rider_sprite()
        self.rider_cache = {}      # the rider pre-rotated in 5 degree steps
        self.missiles = []
        self.zaps = []           # [[(x, y), ...] chain points, time left] tesla bolts
        self.packet = None       # [x, y, kind, life, age] co-op special weapon packet
        self.packet_timer = 0.0
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
        self.taunt = None    # opaque full-screen boss portrait when a boss wave ends the co-op game

    # ---- devices

    def scan_pads(self):
        for i in range(pygame.joystick.get_count()):
            try:
                j = pygame.joystick.Joystick(i)
                pid = f"pad{j.get_instance_id()}"
                if pid in self.pads:
                    continue
                if sdl_ctrl and not WEB and sdl_ctrl.is_controller(i):   # browsers already remap pads to WEB_LAYOUT
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
                    self.ghouls, self.pickups, self.spectators, self.gibs, self.missiles, self.zaps,
                    self.bosses, self.boss_shots):
            lst.clear()
        self.webs.clear()
        self.boss_pending = None
        self.rider = None
        self.crate = None
        self.crate_timer = CRATE_RESPAWN
        self.packet = None
        self.packet_timer = 2.0
        self.flow = None
        self.banner = None

    def to_lobby(self):
        self.state = 'lobby'
        self.paused = False
        self.lobby_cache = None     # the arena behind it changed during the match
        self.taunt = None
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
        else:
            low = min(p.score for p in self.players)
            if any(p.score > low for p in self.players):   # nobody is "last" while everyone is level
                for p in self.players:
                    if p.score == low:
                        p.tank.special = random.choice(SPECIALS)
                        p.tank.special_recharge = SPECIAL_RECHARGE
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
        self.rider = Rider(tr.n * 0.3)   # waits a third of a lap ahead of the grid
        self.update_rider(0.0)
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
            self.update_missiles(dt)
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
            self.update_bosses(dt)
            self.update_boss_shots(dt)
            self.update_pickups(dt)
            self.update_packet(dt)
            if not any(p.tank and p.tank.alive for p in self.players) and self.ending is None:
                self.ending = 1.5
            if self.ending is not None:
                self.ending -= dt
                if self.ending <= 0:
                    self.best_wave = max(self.best_wave, self.wave)
                    self.state = 'coopover'
                    self.timer = 1.5
                    boss = self.bosses[0].kind if self.bosses else self.boss_pending and self.boss_pending[0]
                    if boss:
                        self.taunt = self.make_taunt_screen(boss)
                        self.sounds.play('boss')
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
            t.stuck -= dt
            if t.stuck > 0:   # pinned by a web ball
                mx = my = 0.0
            if can_act and (mx or my):
                target = math.atan2(my, mx)
                t.angle = approach_angle(t.angle, target, TURN_SPEED * dt)
                fwd = TANK_SPEED * min(1.0, math.hypot(mx, my)) * max(0.0, math.cos(angle_diff(t.angle, target)))
                if self.webs and self.arena.tile(t.x, t.y)[:2] in self.webs:
                    fwd *= WEB_SLOW
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
            t.special_charge -= dt
            if t.special and pad:
                self.special_input(t, pad, dt, can_act)
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
        race = self.mode == 'race'
        t.cooldown = FIRE_COOLDOWN
        if not race:   # races have unlimited shells
            t.ammo -= 1
        t.recoil = 5.0
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
                spot = self.free_spot()
                if spot:
                    x, y = spot
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
                self.texts.append(["POLNO STRELIVA", c[0], c[1] - 20, 0.0, (255, 220, 100)])
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

    def free_spot(self, away=3 * T):
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        spots = [tile_center(c, r) for r in range(ROWS) for c in range(COLS) if self.arena.grid[r][c] == EMPTY]
        far = [s for s in spots if all(math.hypot(s[0] - t.x, s[1] - t.y) > away for t in tanks)]
        return random.choice(far or spots) if spots else None

    # ---- special weapons

    def special_input(self, t, pad, dt, can_act):
        ready = can_act and t.special_charge <= 0
        if t.special == 'mortar':
            # hold to walk the target circle out, release to fire
            if 'fire2' in pad.held and ready:
                t.mortar_aim = MORTAR_MIN if t.mortar_aim is None else min(MORTAR_MAX, t.mortar_aim + MORTAR_AIM_SPEED * dt)
            elif t.mortar_aim is not None:
                if can_act:
                    self.fire_special(t)
                t.mortar_aim = None
        elif 'fire2' in pad.pressed and ready:
            self.fire_special(t)

    def fire_special(self, t):
        kind = t.special
        mx, my = t.x + math.cos(t.turret) * 25, t.y + math.sin(t.turret) * 25
        if kind == 'tesla':
            if not self.tesla(t):
                self.sounds.play('empty')
                return   # nothing in range: keep the charge
        elif kind == 'rocket':
            self.missiles.append(Missile('rocket', t, mx, my, t.turret))
            self.sounds.play('rocket')
        else:
            tx = clamp(t.x + math.cos(t.turret) * t.mortar_aim, 0, W)
            ty = clamp(t.y + math.sin(t.turret) * t.mortar_aim, HUD, H)
            self.missiles.append(Missile('mortar', t, t.x, t.y, t.turret, math.hypot(tx - t.x, ty - t.y)))
            self.sounds.play('mortar')
        t.recoil = 7.0
        for _ in range(10):
            a = t.turret + random.uniform(-0.6, 0.6)
            sp = random.uniform(60, 260)
            self.particles.append([mx, my, math.cos(a) * sp, math.sin(a) * sp, 0.18, 0.18, 'fire', random.uniform(4, 7)])
        self.rumble(t.player, 0.7, 0.7, 200)
        if t.special_recharge:
            t.special_charge = t.special_recharge
        else:
            t.special = None

    def targets(self, owner):
        """What specials can hurt: ghouls in co-op, enemy tanks in versus."""
        if self.mode == 'coop':
            out = [(g.x, g.y, GHOUL_R, g) for g in self.ghouls if not g.dead and g.emerge <= 0]
            for b in self.bosses:
                if not b.dead and b.emerge <= 0:
                    out.append((b.x, b.y, BOSS_R, b))
                    out += [(x, y, 10, b) for x, y in b.segs[1:]]   # the snake's body counts too
            return out
        return [(t.x, t.y, TANK_R, t) for t in (p.tank for p in self.players if p.tank and p.tank.alive) if t is not owner]

    def damage_target(self, obj, owner, x, y, n):
        for _ in range(n):
            if isinstance(obj, Ghoul):
                if obj.dead:
                    return
                self.hit_ghoul(obj, Bullet(owner, obj.x, obj.y, math.atan2(obj.y - y, obj.x - x)))
            elif isinstance(obj, Boss):
                if obj.dead:
                    return
                self.hit_boss(obj, owner.player, obj.x, obj.y)
            else:
                if not obj.alive:
                    return
                obj.invuln = 0.0
                self.hit_tank(obj, obj.x, obj.y)

    def tesla(self, t):
        """Zap the nearest target in range, then everything touching it, and so on down the chain."""
        tg = self.targets(t)
        seeds = [o for o in tg if math.hypot(o[0] - t.x, o[1] - t.y) < TESLA_RANGE]
        if not seeds:
            return False
        first = min(seeds, key=lambda o: math.hypot(o[0] - t.x, o[1] - t.y))
        hit, links, queue = [first], [((t.x, t.y), first)], [first]
        for o in tg:   # anything touching the tank itself is zapped too
            if o is not first and math.hypot(o[0] - t.x, o[1] - t.y) < o[2] + TANK_R + TESLA_TOUCH:
                hit.append(o)
                links.append(((t.x, t.y), o))
                queue.append(o)
        while queue:
            a = queue.pop()
            for b in tg:
                if b not in hit and math.hypot(a[0] - b[0], a[1] - b[1]) < a[2] + b[2] + TESLA_TOUCH:
                    hit.append(b)
                    links.append(((a[0], a[1]), b))
                    queue.append(b)
        for start, o in links:
            self.zaps.append([start, (o[0], o[1]), 0.35])
            self.flashes.append([o[0], o[1], 0.0, 0.25, 40])
        for obj in {id(o[3]): o[3] for o in hit}.values():   # a snake touched in several places is hit once
            self.damage_target(obj, t, t.x, t.y, 1)
        self.sounds.play('zap')
        self.shake = max(self.shake, 0.15)
        return True

    def explode(self, x, y, radius, owner):
        """Blast from a player's special (owner is their tank), or from a boss (owner None: it hurts tanks)."""
        if owner is None:
            for t in [p.tank for p in self.players if p.tank and p.tank.alive]:
                if math.hypot(t.x - x, t.y - y) < radius + TANK_R:
                    self.hurt_tank(t, x, y)
        else:
            hit = {}
            for ox, oy, r, obj in self.targets(owner):
                if math.hypot(ox - x, oy - y) < radius + r:
                    hit[id(obj)] = obj
            for obj in hit.values():
                self.damage_target(obj, owner, x, y, BLAST_DAMAGE)
        for r in range(int((y - radius - HUD) // T), int((y + radius - HUD) // T) + 1):
            for c in range(int((x - radius) // T), int((x + radius) // T) + 1):
                if 0 <= c < COLS and 0 <= r < ROWS and self.arena.grid[r][c] == BRICK:
                    bx, by = tile_center(c, r)
                    if math.hypot(bx - x, by - y) < radius:
                        self.damage_brick(c, r)
        self.arena.scorch_mark(x, y, big=True)
        for _ in range(30):
            a = random.uniform(0, math.tau)
            s = random.uniform(40, 260)
            life = random.uniform(0.3, 0.7)
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s, life, life, 'fire', random.uniform(6, 12)])
        for _ in range(12):
            a = random.uniform(0, math.tau)
            self.particles.append([x, y, math.cos(a) * 30, math.sin(a) * 30, 1.3, 1.3, 'smoke', random.uniform(7, 11)])
        self.rings.append([x, y, 0.0, 0.4])
        self.flashes.append([x, y, 0.0, 0.45, radius * 2])
        self.shake = max(self.shake, 0.5)
        self.sounds.play('explode')

    def update_missiles(self, dt):
        for m in self.missiles:
            if m.kind == 'rocket':
                steps = max(1, math.ceil(ROCKET_SPEED * dt / 6))
                for _ in range(steps):
                    nx, ny = m.x + m.vx * dt / steps, m.y + m.vy * dt / steps
                    hit = self.arena.bullet_hit(nx, ny) or not (0 <= nx <= W and HUD <= ny <= H)
                    hit = hit or any(math.hypot(ox - nx, oy - ny) < r + 4 for ox, oy, r, _ in self.targets(m.owner))
                    if hit:
                        self.explode(m.x, m.y, ROCKET_RADIUS, m.owner)
                        m.dead = True
                        break
                    m.x, m.y = nx, ny
                if not m.dead:
                    self.particles.append([m.x - m.vx * 0.02, m.y - m.vy * 0.02, random.uniform(-20, 20), random.uniform(-20, 20),
                                           0.5, 0.5, 'smoke', random.uniform(3, 5)])
                    self.particles.append([m.x - m.vx * 0.012, m.y - m.vy * 0.012, 0, 0, 0.1, 0.1, 'fire', 5])
            else:
                m.t += dt
                k = min(1.0, m.t / m.dur)
                m.x = m.sx + (m.tx - m.sx) * k
                m.y = m.sy + (m.ty - m.sy) * k
                m.z = 4 * m.peak * k * (1 - k)
                if k >= 1:
                    self.explode(m.tx, m.ty, MORTAR_RADIUS, m.owner)
                    m.dead = True
        self.missiles = [m for m in self.missiles if not m.dead]
        for z in self.zaps:
            z[2] -= dt
        self.zaps = [z for z in self.zaps if z[2] > 0]

    def update_packet(self, dt):
        """Co-op: special weapon packets keep turning up while some live tank has no special."""
        alive = [p.tank for p in self.players if p.tank and p.tank.alive]
        if self.packet:
            pk = self.packet
            pk[3] -= dt
            pk[4] += dt
            for t in alive:
                if math.hypot(t.x - pk[0], t.y - pk[1]) < TANK_R + CRATE_R:
                    t.special, t.special_recharge, t.special_charge = pk[2], 0.0, 0.0
                    self.texts.append([SPECIAL_NAMES[pk[2]] + "!", pk[0], pk[1] - 20, 0.0, SPECIAL_COLORS[pk[2]]])
                    self.sparks(pk[0], pk[1], SPECIAL_COLORS[pk[2]], 18)
                    self.sounds.play('pickup')
                    self.rumble(t.player, 0.3, 0.7, 200)
                    pk[3] = 0
                    break
            if pk[3] <= 0:
                self.packet = None
                self.packet_timer = SPECIAL_PACKET_DELAY
        elif any(not t.special for t in alive):
            self.packet_timer -= dt
            if self.packet_timer <= 0:
                spot = self.free_spot()
                if spot:
                    self.packet = [spot[0], spot[1], random.choice(SPECIALS), SPECIAL_PACKET_LIFE, 0.0]
                    self.rings.append([spot[0], spot[1], 0.0, 0.4])
                    self.sounds.play('crate')

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
                    for bs in self.bosses:
                        if b.dead or bs.dead or bs.emerge > 0:
                            continue
                        if ((bs.x - b.x) ** 2 + (bs.y - b.y) ** 2 < (BOSS_R + BULLET_R) ** 2
                                or any((x - b.x) ** 2 + (y - b.y) ** 2 < (10 + BULLET_R) ** 2 for x, y in bs.segs[1:])):
                            self.hit_boss(bs, b.owner.player, b.x, b.y)
                            b.dead = True
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

    def hurt_tank(self, t, x, y):
        """Monster damage: one hit, then a moment of invulnerability."""
        if t.alive and t.invuln <= 0:
            t.invuln = TANK_HIT_INVULN
            self.hit_tank(t, x, y)

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
        if self.wave_to_spawn > 0 or self.boss_pending:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                if self.boss_pending:
                    self.spawn_boss(tanks)
                else:
                    self.spawn_ghoul(tanks)
                    self.wave_to_spawn -= 1
                self.spawn_timer = max(0.5, 1.6 - 0.06 * self.wave)
        elif not self.ghouls and not self.bosses:
            self.wave_break = WAVE_BREAK
            self.banner = [f"VAL {self.wave} OČIŠČEN", 2.5]
            self.sounds.play('pickup')
            for t in tanks:   # every cleared wave repairs the tanks
                if t.hp < t.max_hp:
                    t.hp = t.max_hp
                    self.texts.append(["POPRAVLJEN", t.x, t.y - 24, 0.0, (120, 230, 120)])

    def start_wave(self):
        self.wave += 1
        self.wave_to_spawn = self.wave      # wave N brings N ghouls
        self.spawn_timer = 0.6
        self.banner = [f"VAL {self.wave}", 2.0]
        if self.wave % BOSS_EVERY == 0:     # ...and every third one a boss as well
            k = self.wave // BOSS_EVERY - 1
            self.boss_pending = (BOSS_KINDS[k % len(BOSS_KINDS)], BOSS_HP + BOSS_HP_GROWTH * (k // len(BOSS_KINDS)))
            self.banner = [f"VAL {self.wave}: BOSS", 2.0]
        self.sounds.play('wave')
        for p in self.players:
            if not (p.tank and p.tank.alive):
                p.tank = self.make_tank(p)
                p.tank.invuln = 2.0
                self.rings.append([p.tank.x, p.tank.y, 0.0, 0.4])
            p.tank.ammo = MAX_AMMO

    def spawn_spot(self, tanks):
        """A reachable empty tile, preferably at the edge and far from every tank."""
        if self.flow is None:
            self.flow = self.compute_flow(tanks)
        g = self.arena.grid
        cand = [(c, r) for r in range(1, ROWS - 1) for c in range(1, COLS - 1)
                if g[r][c] == EMPTY and self.flow[r][c] < math.inf]
        far = [cr for cr in cand if all(math.hypot(tile_center(*cr)[0] - t.x, tile_center(*cr)[1] - t.y) > 7 * T for t in tanks)]
        edge = [cr for cr in far if cr[0] in (1, COLS - 2) or cr[1] in (1, ROWS - 2)]
        pool = edge or far or cand
        return tile_center(*random.choice(pool)) if pool else None

    def spawn_ghoul(self, tanks):
        spot = self.spawn_spot(tanks)
        if not spot:
            return
        x, y = spot
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

    def spawn_boss(self, tanks):
        kind, hp = self.boss_pending
        spot = self.spawn_spot(tanks)
        if not spot:
            return
        self.boss_pending = None
        b = Boss(kind, spot[0], spot[1], hp)
        self.bosses.append(b)
        self.banner = [BOSS_NAMES[kind], 2.5]
        if kind != 'witch':
            self.arena.scorch_mark(b.x, b.y, big=True)
        for _ in range(20):
            self.particles.append([b.x + random.uniform(-16, 16), b.y + random.uniform(-10, 14), random.uniform(-25, 25),
                                   random.uniform(-50, -15), 1.3, 1.3, 'smoke', random.uniform(6, 11)])
        self.rings.append([b.x, b.y, 0.0, 0.6])
        self.shake = max(self.shake, 0.4)
        self.sounds.play('boss')

    def boss_aim(self, b, tanks):
        """A tank lined up with the boss on a row or column: (dx, dy, distance). Never diagonal."""
        for t in sorted(tanks, key=lambda t: (t.x - b.x) ** 2 + (t.y - b.y) ** 2):
            dx, dy = t.x - b.x, t.y - b.y
            if abs(dy) < BOSS_ALIGN and T < abs(dx) < BOSS_RANGE:
                ax, ay, d = math.copysign(1, dx), 0, abs(dx)
            elif abs(dx) < BOSS_ALIGN and T < abs(dy) < BOSS_RANGE:
                ax, ay, d = 0, math.copysign(1, dy), abs(dy)
            else:
                continue
            if b.kind != 'witch':   # her cats are lobbed over walls; everything else needs a clear line
                if any(self.arena.bullet_hit(b.x + ax * k, b.y + ay * k) for k in range(BOSS_R, int(d), 10)):
                    continue
            return ax, ay, d
        return None

    def boss_throw(self, b):
        ax, ay, d = b.aim
        x, y = b.x + ax * BOSS_R, b.y + ay * BOSS_R
        kind = {'knight': 'sword', 'spider': 'web', 'snake': 'spit', 'witch': 'cat'}[b.kind]
        dist = {'sword': min(BOSS_RANGE, d + 3 * T), 'web': d + T, 'spit': BOSS_RANGE, 'cat': d}[kind]
        self.boss_shots.append(BossShot(kind, b, x, y, ax, ay, dist))
        if b.kind == 'knight':
            b.armed = False
        b.face = int(ax) or b.face
        b.cool = BOSS_ATTACK_CD
        self.sounds.play('meow' if kind == 'cat' else 'throw')

    def witch_target(self, b, t):
        """She keeps her distance and tries to line up with a tank, from wherever is closest."""
        d = 5 * T
        spots = [(t.x + d, t.y), (t.x - d, t.y), (t.x, t.y + d), (t.x, t.y - d)]
        spots = [(clamp(x, T, W - T), clamp(y, HUD + T, H - T)) for x, y in spots]
        return min(spots, key=lambda p: (p[0] - b.x) ** 2 + (p[1] - b.y) ** 2)

    def update_bosses(self, dt):
        for k in list(self.webs):
            self.webs[k] -= dt
            if self.webs[k] <= 0:
                del self.webs[k]
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        if tanks and self.flow is None:
            self.flow = self.compute_flow(tanks)
        for b in self.bosses:
            b.flash -= dt
            b.attack -= dt
            if b.emerge > 0:
                b.emerge -= dt
                continue
            if not tanks:
                continue
            nearest = min(tanks, key=lambda t: (t.x - b.x) ** 2 + (t.y - b.y) ** 2)
            flying = b.kind == 'witch'
            b.phase += dt * 8
            if b.windup > 0:   # stands still while winding up the throw
                b.windup -= dt
                if b.windup <= 0:
                    self.boss_throw(b)
            else:
                b.cool -= dt
                if b.cool <= 0 and b.armed:
                    b.aim = self.boss_aim(b, tanks)
                    if b.aim:
                        b.windup = BOSS_WINDUP
                if flying:
                    tx, ty, brick = *self.witch_target(b, nearest), None
                else:
                    tx, ty, brick = self.ghoul_step_target(b, nearest)
                dx, dy = tx - b.x, ty - b.y
                d = math.hypot(dx, dy)
                if d > 1:
                    step = min(d, BOSS_SPEED * dt)
                    b.x += dx / d * step
                    b.y += dy / d * step
                    if abs(dx) > 2:
                        b.face = 1 if dx > 0 else -1
                if not flying:
                    b.x, b.y = self.arena.collide_circle(b.x, b.y, BOSS_R)
                    if brick and d < T / 2 + BOSS_R + 4:
                        b.claw -= dt
                        if b.claw <= 0:
                            b.claw = 0.8
                            self.damage_brick(*brick)
            if b.kind == 'spider':   # webs wherever she walks
                c, r, v = self.arena.tile(b.x, b.y)
                if v in (EMPTY, BUSH) and (c, r) not in self.webs:
                    if len(self.webs) >= WEB_MAX:
                        del self.webs[min(self.webs, key=self.webs.get)]
                    self.webs[(c, r)] = WEB_LIFE
            if b.kind == 'snake':
                if math.dist((b.x, b.y), b.trail[0]) >= SNAKE_TRAIL_STEP:
                    b.trail.insert(0, (b.x, b.y))
                    del b.trail[SNAKE_SEGMENTS * 5:]
                b.segs = [(b.x, b.y)] + [b.trail[min(len(b.trail) - 1, k * 5)] for k in range(1, SNAKE_SEGMENTS)]
            for t in tanks:
                dx, dy = b.x - t.x, b.y - t.y
                d = math.hypot(dx, dy) or 0.01
                if d < TANK_R + BOSS_R:
                    if not flying:
                        b.x = t.x + dx / d * (TANK_R + BOSS_R)
                        b.y = t.y + dy / d * (TANK_R + BOSS_R)
                    if b.attack <= 0 and t.invuln <= 0:
                        b.attack = GHOUL_ATTACK_CD
                        self.hurt_tank(t, (t.x + b.x) / 2, (t.y + b.y) / 2)
                for x, y in b.segs[1:]:   # the snake's body is solid
                    dx, dy = t.x - x, t.y - y
                    d = math.hypot(dx, dy) or 0.01
                    if d < TANK_R + 10:
                        t.x, t.y = x + dx / d * (TANK_R + 10), y + dy / d * (TANK_R + 10)
                        t.x, t.y = self.arena.collide_circle(t.x, t.y, TANK_R)
            tanks = [t for t in tanks if t.alive]

    def update_boss_shots(self, dt):
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        for s in self.boss_shots:
            if s.kind == 'cat':   # lobbed in an arc over everything, then hisses and goes off
                if s.fuse is None:
                    s.done = min(s.dist, s.done + CAT_SPEED * dt)
                    k = s.done / s.dist
                    s.x, s.y = s.sx + s.dx * s.done, s.sy + s.dy * s.done
                    s.z = 4 * (30 + s.dist * 0.2) * k * (1 - k)
                    s.spin += dt * 12
                    if k >= 1:
                        s.fuse = CAT_FUSE
                else:
                    s.fuse -= dt
                    if s.fuse <= 0:
                        self.explode(s.x, s.y, CAT_RADIUS, None)
                        s.dead = True
                continue
            speed = SWORD_SPEED if s.kind == 'sword' else SPIT_SPEED
            s.spin += dt * 18
            steps = max(1, math.ceil(speed * dt / 6))
            for _ in range(steps):
                sd = speed * dt / steps
                if s.back:   # the sword returns along the line it flew out on
                    s.done -= sd
                    s.x, s.y = s.sx + s.dx * s.done, s.sy + s.dy * s.done
                    if s.done <= 0:
                        s.dead = True
                        s.owner.armed = True
                        break
                else:
                    nx, ny = s.x + s.dx * sd, s.y + s.dy * sd
                    hit = self.arena.bullet_hit(nx, ny)
                    if hit or s.done + sd >= s.dist or not (0 < nx < W and HUD < ny < H):
                        if hit and hit[2] == BRICK:
                            self.damage_brick(hit[0], hit[1])
                        self.shot_ends(s)
                        break
                    s.x, s.y = nx, ny
                    s.done += sd
                for t in tanks:
                    if (t.x - s.x) ** 2 + (t.y - s.y) ** 2 < (TANK_R + 9) ** 2 and t not in s.hit:
                        s.hit.append(t)
                        self.hurt_tank(t, s.x, s.y)
                        if s.kind == 'web':
                            t.stuck = WEB_STUCK
                        if s.kind != 'sword':
                            self.shot_ends(s)
                        break
                if s.dead:
                    break
        self.boss_shots = [s for s in self.boss_shots if not s.dead]

    def shot_ends(self, s):
        """A shot reached its range or hit something: swords turn back, web balls leave a web, venom splashes."""
        if s.kind == 'sword':
            s.back = True
            self.sparks(s.x, s.y, (220, 220, 240), 6)
            return
        s.dead = True
        if s.kind == 'web':
            c, r, v = self.arena.tile(s.x - s.dx * 4, s.y - s.dy * 4)
            if v in (EMPTY, BUSH):
                self.webs[(c, r)] = WEB_LIFE
        col = (235, 235, 245) if s.kind == 'web' else (150, 230, 60)
        self.sparks(s.x, s.y, col, 10)

    def hit_boss(self, b, player, x, y):
        if b.dead:
            return
        b.hp -= 1
        b.flash = 0.1
        self.sparks(x, y, BOSS_COLORS[b.kind], 10)
        if b.hp <= 0:
            self.kill_boss(b, player)
        else:
            self.sounds.play('ghoulhit')

    def kill_boss(self, b, player):
        b.dead = True
        self.bosses.remove(b)
        player.kills += 1
        col = BOSS_COLORS[b.kind]
        for x, y in b.segs[1:] or [(b.x, b.y)]:
            for _ in range(6):
                a = random.uniform(0, math.tau)
                sp = random.uniform(40, 220)
                self.particles.append([x, y, math.cos(a) * sp, math.sin(a) * sp, 0.8, 0.8, 'debris', random.uniform(3, 7), col])
        for _ in range(40):
            a = random.uniform(0, math.tau)
            sp = random.uniform(40, 260)
            life = random.uniform(0.4, 0.9)
            self.particles.append([b.x, b.y, math.cos(a) * sp, math.sin(a) * sp, life, life, 'fire', random.uniform(6, 13)])
        if b.kind != 'witch':
            self.arena.scorch_mark(b.x, b.y, big=True)
        self.rings.append([b.x, b.y, 0.0, 0.6])
        self.flashes.append([b.x, b.y, 0.0, 0.6, 180])
        self.shake = max(self.shake, 0.8)
        self.banner = ["BOSS PREMAGAN", 2.5]
        self.sounds.play('explode')
        self.rumble(player, 1.0, 1.0, 500)
        for k in range(3):   # loot
            a = k * math.tau / 3
            x, y = self.arena.collide_circle(b.x + math.cos(a) * 24, b.y + math.sin(a) * 24, 8)
            self.pickups.append([x, y, 12.0])

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
        self.update_rider(dt)
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
            self.banner = [f"{p.cname} ZMAGA!", 2.5]
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
                    self.sounds.play('pickup')
                    self.texts.append([f"KROG {lap + 1}", t.x, t.y - 20, 0.0, t.player.color])
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
                r = self.rider
                if r and r.dead <= 0 and b.z < 16 and (r.x - b.x) ** 2 + (r.y - b.y) ** 2 < (RIDER_R + BULLET_R) ** 2:
                    self.kill_rider()
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

    def update_rider(self, dt):
        r, tr = self.rider, self.track
        if r is None:
            return
        r.cool -= dt
        if r.whip:
            r.whip[2] -= dt
            if r.whip[2] <= 0:
                r.whip = None
        if r.dead > 0:
            r.dead -= dt
            if r.dead <= 0:   # back from the dead in a burst of flame
                for _ in range(24):
                    a = random.uniform(0, math.tau)
                    sp = random.uniform(30, 160)
                    self.particles.append([r.x, r.y, math.cos(a) * sp, math.sin(a) * sp, 0.5, 0.5, 'fire', random.uniform(4, 9)])
                self.rings.append([r.x, r.y, 0.0, 0.4])
                self.sounds.play('rocket')
            return
        if self.state == 'play':
            r.idx = (r.idx + RIDER_SPEED * dt / TRACK_STEP) % tr.n
            if random.random() < dt * 0.6:
                r.lane_to = random.uniform(-TRACK_W / 4, TRACK_W / 4)
            r.lane += (r.lane_to - r.lane) * min(1.0, dt * 1.5)
        i = int(r.idx)
        j, f = (i + 1) % tr.n, r.idx - i
        x = tr.pts[i][0] + (tr.pts[j][0] - tr.pts[i][0]) * f
        y = tr.pts[i][1] + (tr.pts[j][1] - tr.pts[i][1]) * f
        r.x, r.y, r.ang = x + tr.nx[i] * r.lane, y + tr.ny[i] * r.lane, tr.ang[i]
        if self.state != 'play':
            return
        ca, sa = math.cos(r.ang), math.sin(r.ang)
        if random.random() < dt * 50:   # the bike is on fire
            self.particles.append([r.x - ca * 16 + random.uniform(-4, 4), r.y - sa * 16 + random.uniform(-4, 4),
                                   -ca * 60 + random.uniform(-20, 20), -sa * 60 + random.uniform(-20, 20), 0.35, 0.35, 'fire', random.uniform(3, 6)])
        if r.cool > 0:
            return
        for t in (p.tank for p in self.players if p.tank):
            if t.finished or t.z > 12 or t.invuln > 0:
                continue
            dx, dy = t.x - r.x, t.y - r.y
            along, side = dx * ca + dy * sa, -dx * sa + dy * ca
            if -RIDER_REACH < along < -8 and abs(side) < 36:   # tailing him: he lashes back with his chain
                r.cool = RIDER_LASH_CD
                r.whip = [t.x, t.y, 0.25]
                t.vx *= 0.3
                t.vy *= 0.3
                t.angle += random.choice((-1, 1)) * random.uniform(1.2, 2.0)
                if t.z <= 0 and t.ramp is None:
                    t.z, t.vz = 0.01, 150.0
                t.flash = 0.15
                t.invuln = 1.2
                for _ in range(14):
                    a = random.uniform(0, math.tau)
                    self.particles.append([t.x, t.y, math.cos(a) * 90, math.sin(a) * 90, 0.4, 0.4, 'fire', random.uniform(3, 6)])
                self.shake = max(self.shake, 0.2)
                self.sounds.play('lash')
                self.rumble(t.player, 0.8, 0.8, 300)
                break

    def kill_rider(self):
        r = self.rider
        r.dead = RIDER_RESPAWN
        r.whip = None
        for _ in range(30):
            a = random.uniform(0, math.tau)
            sp = random.uniform(40, 220)
            life = random.uniform(0.3, 0.7)
            self.particles.append([r.x, r.y, math.cos(a) * sp, math.sin(a) * sp, life, life, 'fire', random.uniform(5, 10)])
        self.flashes.append([r.x, r.y, 0.0, 0.4, 90])
        self.texts.append(["IZGNAN!", r.x, r.y - 20, 0.0, (255, 150, 50)])
        self.shake = max(self.shake, 0.3)
        self.sounds.play('explode')

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
        self.texts.append([random.choice(("ŠPLAT!", "ČVAK!", "UPS!")), gh.x, gh.y - 20, 0.0, (230, 40, 40)])
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
        pl = t.player
        white = t.flash > 0
        body = 'body_white' if white else int(t.tread_phase / 1.2) % 4
        blit_center(dst, pl.rotated('shadow', t.angle), t.x + 4, t.y + 5)
        blit_center(dst, pl.rotated(body, t.angle), t.x, t.y)
        rx = t.x - math.cos(t.turret) * t.recoil
        ry = t.y - math.sin(t.turret) * t.recoil
        blit_center(dst, pl.rotated('turret_white' if white else 'turret', t.turret), rx, ry)

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

    def draw_webs(self, w):
        for (c, r), life in self.webs.items():
            col = lerp_color(FLOOR, (215, 215, 225), min(1.0, life / 3))   # fades out at the end
            x, y = tile_center(c, r)
            h = T / 2 - 2
            for dx, dy in ((h, 0), (0, h), (h * 0.7, h * 0.7), (h * 0.7, -h * 0.7)):
                pygame.draw.line(w, col, (x - dx, y - dy), (x + dx, y + dy))
            for k in (0.4, 0.8):
                pygame.draw.polygon(w, col, [(x + math.cos(a * math.pi / 4) * h * k, y + math.sin(a * math.pi / 4) * h * k)
                                             for a in range(8)], 1)

    def draw_boss(self, w, b):
        spr = self.boss_sprites[b.kind]
        glow = b.windup > 0 and int(self.now * 16) % 2
        state = 'white' if b.flash > 0 or glow else 'base'
        scale = 1.0 - max(0.0, b.emerge) / (GHOUL_EMERGE * 1.5)
        if scale <= 0.05:
            return
        if b.windup > 0 and b.aim:   # where the throw will go: always straight along a row or column
            ax, ay, d = b.aim
            for k in range(BOSS_R + 6, int(d), 22):
                x, y = b.x + ax * k, b.y + ay * k
                pygame.draw.line(w, (255, 70, 50), (x, y), (x + ax * 10, y + ay * 10), 3)
        flying = b.kind == 'witch'
        if b.kind == 'snake':
            segs = spr['segs_white' if b.flash > 0 else 'segs']
            for k in range(len(b.segs) - 1, 0, -1):
                blit_center(w, segs[k], b.segs[k][0], b.segs[k][1])
        bob = math.sin(self.now * 3 + b.phase * 0.1) * 4 - 14 if flying else -abs(math.sin(b.phase)) * 2
        blit_center(w, self.boss_shadow, b.x, b.y + (26 if flying else 20))
        if b.kind == 'knight':
            add_glow(w, (40, 20, 70), b.x, b.y, 44)
        img = spr[(state, b.face)]
        if scale < 1:
            img = pygame.transform.rotozoom(img, 0, scale)
        blit_center(w, img, b.x, b.y - 4 + bob)
        if b.kind == 'knight' and b.armed and scale >= 1:
            sw = spr['sword'] if b.face > 0 else pygame.transform.flip(spr['sword'], True, False)
            blit_center(w, sw, b.x + b.face * 22, b.y - 6 + bob)

    def draw_boss_shots(self, w):
        for s in self.boss_shots:
            if s.kind == 'sword':
                img = pygame.transform.rotate(self.boss_sprites['knight']['sword'], -math.degrees(s.spin))
                add_glow(w, (50, 30, 80), s.x, s.y, 26)
                blit_center(w, img, s.x, s.y)
            elif s.kind == 'web':
                pygame.draw.circle(w, (235, 235, 245), (s.x, s.y), 7)
                for k in range(3):
                    a = s.spin + k * math.pi / 3
                    pygame.draw.line(w, (170, 170, 185), (s.x - math.cos(a) * 9, s.y - math.sin(a) * 9),
                                     (s.x + math.cos(a) * 9, s.y + math.sin(a) * 9))
            elif s.kind == 'spit':
                add_glow(w, (40, 90, 10), s.x, s.y, 20)
                pygame.draw.circle(w, (150, 230, 60), (s.x, s.y), 6)
                pygame.draw.circle(w, (220, 255, 160), (s.x - 2, s.y - 2), 2)
            else:
                cat = self.boss_sprites['witch']['cat']
                blit_center(w, self.ghoul_shadow, s.x, s.y + 8)
                if s.fuse is not None:
                    if int(s.fuse * 12) % 2:
                        pygame.draw.circle(w, (255, 60, 40), (s.x, s.y), CAT_RADIUS, 2)
                    blit_center(w, cat, s.x, s.y - 4)
                else:
                    blit_center(w, pygame.transform.rotate(cat, -math.degrees(s.spin)), s.x, s.y - s.z)
                add_glow(w, (120, 60, 10), s.x + 9, s.y - s.z - 9, 12)   # the fuse

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
        if self.rider and self.rider.dead <= 0:
            objs.append((self.rider.y, 3, self.rider))
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
            elif kind == 3:
                self.draw_rider(w, o)
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

    def draw_rider(self, w, r):
        step = round(r.ang / math.tau * 72) % 72
        img = self.rider_cache.get(step)
        if img is None:
            img = self.rider_cache[step] = pygame.transform.rotozoom(self.rider_sprite, -step * 5, 1)
        blit_center(w, self.spec_shadow, r.x + 2, r.y + 4)
        add_glow(w, (130, 50, 10), r.x, r.y, 30)
        blit_center(w, img, r.x, r.y)
        if r.whip:   # burning chain
            pts = [(r.x + (r.whip[0] - r.x) * k / 6 + random.uniform(-4, 4), r.y + (r.whip[1] - r.y) * k / 6 + random.uniform(-4, 4))
                   for k in range(7)]
            pygame.draw.lines(w, (255, 140, 40), False, pts, 3)
            pygame.draw.lines(w, (255, 230, 150), False, pts, 1)

    def draw_specials(self, w, tanks):
        for t in tanks:
            if t.mortar_aim is not None:   # red target circle on the ground
                tx = clamp(t.x + math.cos(t.turret) * t.mortar_aim, 0, W)
                ty = clamp(t.y + math.sin(t.turret) * t.mortar_aim, HUD, H)
                pulse = 2 * math.sin(self.now * 12)
                pygame.draw.circle(w, (230, 40, 40), (tx, ty), MORTAR_RADIUS + pulse, 3)
                pygame.draw.circle(w, (255, 90, 80), (tx, ty), 6, 2)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    pygame.draw.line(w, (230, 40, 40), (tx + dx * 12, ty + dy * 12), (tx + dx * 24, ty + dy * 24), 2)
                for i in range(1, 8):   # dotted path
                    k = i / 8
                    pygame.draw.circle(w, (255, 120, 110), (t.x + (tx - t.x) * k, t.y + (ty - t.y) * k - 4 * 30 * k * (1 - k)), 2)
            if t.special:   # held weapon: icon with a recharge arc
                ix, iy = t.x + 22, t.y - 22
                pygame.draw.circle(w, (20, 22, 28), (ix, iy), 12)
                icon = self.special_sprites[t.special][1]
                if t.special_charge > 0:
                    frac = 1 - t.special_charge / t.special_recharge
                    pygame.draw.arc(w, (150, 150, 160), (ix - 12, iy - 12, 24, 24), math.pi / 2, math.pi / 2 + math.tau * frac, 2)
                    icon = icon.copy()
                    icon.set_alpha(90)
                else:
                    pygame.draw.circle(w, SPECIAL_COLORS[t.special], (ix, iy), 12, 2)
                blit_center(w, icon, ix, iy)
        for m in self.missiles:
            if m.kind == 'rocket':
                add_glow(w, (170, 80, 25), m.x, m.y, 30)
                img = pygame.transform.rotozoom(self.special_sprites['rocket'][1], -math.degrees(m.a), 1.7)
                blit_center(w, img, m.x, m.y)
            else:
                pygame.draw.circle(w, (230, 40, 40), (m.tx, m.ty), MORTAR_RADIUS * (1 - 0.3 * m.t / m.dur), 2)
                sh = 4 + 4 * (1 - m.z / (m.peak + 1))
                pygame.draw.ellipse(w, (20, 20, 20), (m.x - sh, m.y - sh / 2, sh * 2, sh))
                pygame.draw.circle(w, (20, 20, 22), (m.x, m.y - m.z), 8 + m.z / 40)
                pygame.draw.circle(w, (150, 150, 160), (m.x, m.y - m.z), 6 + m.z / 40)
                pygame.draw.circle(w, (230, 230, 240), (m.x - 2, m.y - m.z - 2), 2 + m.z / 80)
        for (x0, y0), (x1, y1), life in self.zaps:   # jagged bolts, re-randomised every frame so they crackle
            d = math.hypot(x1 - x0, y1 - y0) or 1
            nx, ny = -(y1 - y0) / d, (x1 - x0) / d
            pts = [(x0, y0)]
            for i in range(1, 8):
                k, off = i / 8, random.uniform(-9, 9)
                pts.append((x0 + (x1 - x0) * k + nx * off, y0 + (y1 - y0) * k + ny * off))
            pts.append((x1, y1))
            pygame.draw.lines(w, (90, 170, 255), False, pts, 5)
            pygame.draw.lines(w, (230, 245, 255), False, pts, 2)
            add_glow(w, (40, 80, 140), x1, y1, 26)

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
            self.screen.fill((0, 0, 0))     # only a shaken world leaves edges uncovered; full fills are slow in browsers
        self.screen.blit(w, (ox, oy))

    def draw_arena_world(self, w):
        self.arena.draw_ground(w, self.now)
        if self.crate:
            self.draw_crate(w)
        tanks = [p.tank for p in self.players if p.tank and p.tank.alive]
        for pk in self.pickups:
            if pk[2] > 2 or int(pk[2] * 8) % 2:
                blit_center(w, pygame.transform.rotozoom(self.crate_sprite, math.sin(self.now * 3) * 8, 0.6), pk[0], pk[1])
        if self.packet:
            x, y, kind, life, age = self.packet
            if life > 2 or int(life * 8) % 2:
                col = SPECIAL_COLORS[kind]
                add_glow(w, tuple(c // 2 for c in col), x, y, 36 + int(4 * math.sin(self.now * 6)))
                blit_center(w, self.crate_shadow, x + 4, y + 5)
                pop = min(1.0, age / 0.25)
                blit_center(w, pygame.transform.rotozoom(self.special_sprites[kind][0], math.sin(self.now * 3) * 8,
                                                         max(0.05, pop * (1.1 + 0.08 * math.sin(self.now * 7)))), x, y - 2)
                pygame.draw.arc(w, col, (x - 24, y - 26, 48, 48), math.pi / 2, math.pi / 2 + math.tau * life / SPECIAL_PACKET_LIFE, 2)
        if self.webs:
            self.draw_webs(w)
        for gh in self.ghouls:
            if gh.kind != 'ghost':
                self.draw_ghoul(w, gh)
        for b in self.bosses:
            if b.kind != 'witch':
                self.draw_boss(w, b)
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
        self.draw_specials(w, tanks)
        for x, y, t, mt, rad in self.flashes:
            k = 1 - t / mt
            add_glow(w, (int(255 * k), int(200 * k), int(120 * k)), x, y, rad)
        for t in tanks:   # ammo warnings, drawn under bushes so hiding still works
            if t.ammo == 0:
                if int(self.now * 4) % 2:
                    self.text("PRAZNO", self.font_tiny, (255, 90, 80), (t.x, t.y - 27), w, shadow=True)
            elif t.ammo <= 3:
                self.text(str(t.ammo), self.font_tiny, (255, 215, 90), (t.x, t.y - 27), w, shadow=True)
        near = None
        if not self.arena.sway:   # bushes are in the ground layer; redraw only those over something
            near = [(t.x, t.y) for t in tanks] + [(g.x, g.y) for g in self.ghouls] + [(b.x, b.y) for b in self.bullets]
            near += [(b.x, b.y) for b in self.bosses] + [p for b in self.bosses for p in b.segs] + [(s.x, s.y) for s in self.boss_shots]
            near += [(p[0], p[1]) for p in self.pickups] + [(m.x, m.y) for m in self.missiles]
            if self.crate:
                near.append(self.crate[:2])
            if self.packet:
                near.append(self.packet[:2])
        self.arena.draw_bushes(w, self.now, near)
        for gh in self.ghouls:   # ghosts float above walls and bushes
            if gh.kind == 'ghost':
                self.draw_ghoul(w, gh)
        for b in self.bosses:    # and so does the witch
            if b.kind == 'witch':
                self.draw_boss(w, b)
        if self.boss_shots:
            self.draw_boss_shots(w)
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
                info = "CILJ" if t and t.finished else f"KROG {lap}/{RACE_LAPS}"
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
            elif t and t.alive and t.special:
                ready = t.special_charge <= 0
                label = SPECIAL_NAMES[t.special] if ready else f"{SPECIAL_NAMES[t.special]} {math.ceil(t.special_charge)}"
                self.screen.blit(self.render(self.font_tiny, label, SPECIAL_COLORS[t.special] if ready else (120, 120, 128)),
                                 (x0 + 134, 27))
            for i in range(self.win_score() if self.mode != 'coop' else 0):
                cx = x0 + 134 + i * 14
                if i < p.score:
                    pygame.draw.circle(self.screen, p.color, (cx, HUD // 2), 5)
                else:
                    pygame.draw.circle(self.screen, (90, 90, 95), (cx, HUD // 2), 5, 2)
            if p.pad_id not in self.pads and int(self.now * 2) % 2:
                img = self.render(self.font_tiny, "NI PADA", (255, 80, 80))
                self.screen.fill((22, 24, 28), (x0 + 60, 2, 66, HUD - 4))
                self.screen.blit(img, img.get_rect(center=(x0 + 92, HUD // 2)))

    def draw_overlay(self):
        cy = HUD + ROWS * T // 2
        if self.mode == 'coop' and self.state in ('countdown', 'play'):
            left = len(self.ghouls) + self.wave_to_spawn + len(self.bosses) + bool(self.boss_pending)
            if self.wave:
                self.text(f"VAL {self.wave}   •   ŠE {left}", self.font_hud, (230, 220, 200), (W // 2, HUD + 18))
            for k, b in enumerate(self.bosses):   # boss health bars
                y = HUD + 44 + k * 34
                self.text(BOSS_NAMES[b.kind], self.font_tiny, BOSS_COLORS[b.kind], (W // 2, y))
                self.screen.fill((20, 20, 24), (W // 2 - 182, y + 9, 364, 12))
                self.screen.fill((200, 40, 50), (W // 2 - 180, y + 11, int(360 * b.hp / b.max_hp), 8))
            if self.banner and self.state == 'play':
                self.text(self.banner[0], self.font_big, (200, 255, 170) if "OČIŠČEN" in self.banner[0] else (255, 120, 90), (W // 2, cy))
        if self.mode == 'race' and self.state in ('countdown', 'play'):
            m, s = divmod(self.race_time, 60)
            self.text(f"{int(m)}:{s:04.1f}", self.font_hud, (230, 230, 230), (W // 2, HUD + 18))
            if self.banner and self.state == 'play':
                self.text(self.banner[0], self.font_big, self.round_winner.color if self.round_winner else (255, 255, 255), (W // 2, cy))
        if self.state == 'coopover':
            self.dim(170)
            self.text("TANKI SO PADLI", self.font_med, (255, 110, 90), (W // 2, cy - 80))
            total = sum(p.kills for p in self.players)
            self.text(f"Dosežen val {self.wave}   •   uničenih pošasti: {total}",
                      self.font_small, (230, 230, 230), (W // 2, cy - 20))
            parts = [(f"{p.cname} {p.kills}", p.color) for p in self.players]
            imgs = [self.font_small.render(t, True, c) for t, c in parts]
            x = W // 2 - (sum(i.get_width() for i in imgs) + 40 * (len(imgs) - 1)) // 2
            for img in imgs:
                self.screen.blit(img, (x, cy + 25))
                x += img.get_width() + 40
            if self.timer <= 0:
                self.text("Pritisni A za nadaljevanje", self.font_small, (220, 220, 220), (W // 2, cy + 90))
            return
        if self.state == 'countdown':
            n = max(1, math.ceil(self.timer))
            self.text(str(n), self.font_big, (255, 255, 255), (W // 2, cy))
        elif self.state == 'play' and self.go_timer > 0:
            self.text("GREMO!", self.font_big, (255, 230, 120), (W // 2, cy))
        elif self.state == 'roundover':
            self.dim(120)
            if self.round_winner:
                what = "DIRKO" if self.mode == 'race' else "RUNDO"
                self.text(f"{self.round_winner.cname} ZMAGA {what}", self.font_med, self.round_winner.color, (W // 2, cy - 30))
                if self.mode == 'race':
                    m, s = divmod(self.race_time, 60)
                    splats = sum(p.kills for p in self.players)
                    self.text(f"{int(m)}:{s:04.1f}   •   povoženih gledalcev: {splats}",
                              self.font_hud, (220, 220, 220), (W // 2, cy + 10))
            else:
                self.text("NEODLOČENO!" if len(self.players) > 1 else "KONEC RUNDE", self.font_med, (230, 230, 230), (W // 2, cy - 30))
            self.draw_scores(cy + 50)
        elif self.state == 'matchover':
            self.dim(160)
            best = max(self.players, key=lambda p: p.score)
            self.text(f"{best.cname} ZMAGA TEKMO!", self.font_med, best.color, (W // 2, cy - 60))
            self.draw_scores(cy + 10)
            if self.timer <= 0:
                self.text("Pritisni A za nadaljevanje", self.font_small, (220, 220, 220), (W // 2, cy + 90))
        if self.paused:
            self.dim(150)
            self.text("PAVZA", self.font_big, (255, 255, 255), (W // 2, cy - 30))
            self.text("START nadaljuj   •   BACK / B nazaj v meni", self.font_small, (220, 220, 220), (W // 2, cy + 50))

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
        # same as blitting black at `alpha`, but a multiply fill skips the alpha blit (very slow in browsers)
        k = 255 - alpha
        self.screen.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)

    def draw_lobby(self):
        # everything but the spinning tanks and the blinking prompts is drawn once into an opaque cache:
        # browsers blit text and other alpha surfaces very slowly
        bw, bh, gap = 184, 220, 15
        x0 = (W - (MAX_PLAYERS * bw + (MAX_PLAYERS - 1) * gap)) // 2
        by = 270
        joined = {p.idx: p for p in self.players}
        n_pads = sum(1 for p in self.pads.values() if p.kind in ('ctrl', 'joy'))
        labels = tuple((i, self.pads[p.pad_id].label if p.pad_id in self.pads else "?") for i, p in sorted(joined.items()))
        key = (self.mode, labels, n_pads)
        if self.lobby_cache is None or self.lobby_cache[0] != key:
            self.lobby_cache = (key, self.render_lobby(key, joined, n_pads, x0, by, bw, bh, gap))
        self.screen.blit(self.lobby_cache[1], (0, 0))
        for i in range(MAX_PLAYERS):
            x = x0 + i * (bw + gap)
            p = joined.get(i)
            if p:
                ang = self.now * 1.5 + i
                body = pygame.transform.rotozoom(p.sprites['body'], -math.degrees(ang), 1.6)
                tur = pygame.transform.rotozoom(p.sprites['turret'], -math.degrees(ang), 1.6)
                blit_center(self.screen, body, x + bw // 2, by + 115)
                blit_center(self.screen, tur, x + bw // 2, by + 115)
            elif int(self.now * 2) % 2:
                self.text("Pritisni A", self.font_hud, (170, 170, 175), (x + bw // 2, by + 120), shadow=False)

    def render_lobby(self, key, joined, n_pads, x0, by, bw, bh, gap):
        bg = pygame.Surface((W, H)).convert()
        self.arena.draw_ground(bg, 0)
        self.arena.draw_bushes(bg, 0)
        screen, self.screen = self.screen, bg     # draw with the usual helpers, but into the cache
        self.dim(170)
        self.text("TANK ARENA", self.font_big, (240, 220, 120), (W // 2, 130))
        self.text("Leva palica: vožnja   •   Desna palica: merjenje   •   RT / RB / A: strel   •   LT / LB / X: posebno orožje", self.font_small, (200, 200, 200), (W // 2, 200))
        ammo = "na dirki neomejeno" if self.mode == 'race' else "poberi zaboje s strelivom za polnjenje"
        self.text(f"{MAX_AMMO} granat na tank - {ammo}", self.font_hud, (230, 200, 110), (W // 2, 236))
        labels = dict(key[1])
        for i in range(MAX_PLAYERS):
            x = x0 + i * (bw + gap)
            p = joined.get(i)
            color = PLAYER_COLORS[i][0]
            rect = pygame.Rect(x, by, bw, bh)
            pygame.draw.rect(bg, (30, 32, 36), rect, border_radius=12)
            pygame.draw.rect(bg, color if p else (70, 72, 78), rect, 3, border_radius=12)
            self.text(f"P{i + 1}", self.font_med, color if p else (110, 110, 115), (rect.centerx, by + 35))
            if p:
                self.text(labels[i], self.font_tiny, (200, 200, 200), (rect.centerx, by + 190), shadow=False)

        if self.mode == 'versus':
            self.text("NAČIN:  BOJ  -  zmaga zadnji preživeli tank", self.font_small, (240, 220, 120), (W // 2, 522))
        elif self.mode == 'coop':
            self.text("NAČIN:  SODELOVANJE  -  skupaj preživite nemrtve", self.font_small, (255, 120, 90), (W // 2, 522))
        else:
            self.text("NAČIN:  DIRKA  -  skoki, drsenje in granate, ki le odbijajo", self.font_small, (120, 210, 255), (W // 2, 522))
        self.text("Y / TAB zamenja način", self.font_tiny, (170, 170, 175), (W // 2, 548), shadow=False)
        self.text(f"Povezani kontrolerji: {n_pads}", self.font_tiny, (150, 150, 155), (W // 2, 568), shadow=False)
        if joined:
            msg = ("Pritisni START za začetek" if len(joined) > 1 or self.mode != 'versus'
                   else "Pritisni START za vadbo (za tekmo sta potrebna vsaj 2 igralca)")
            self.text(msg, self.font_small, (255, 255, 255), (W // 2, 590))
        self.text("Tipkovnica P1: WASD vožnja, Q/E merjenje, SPACE vstop+strel, F posebno, X izstop   •   P2: puščice, , . merjenje, R-CTRL vstop+strel, / posebno, DEL izstop   •   ENTER začetek",
                  self.font_tiny, (150, 150, 155), (W // 2, 630), shadow=False)
        goal = {'versus': f"Zmaga, kdor prvi dobi {WIN_SCORE} rund", 'coop': "Val N prinese N pošasti",
                'race': f"{RACE_LAPS} krogov, zmaga, kdor prvi dobi {RACE_WIN_SCORE} dirke"}[self.mode]
        quit_hint = "" if WEB else "   •   ESC izhod"
        self.text(f"{goal}   •   B izstop   •   F11 celozaslonsko{quit_hint}",
                  self.font_hud, (150, 150, 155), (W // 2, 660), shadow=False)
        self.screen = screen
        return bg

    def make_taunt_screen(self, kind):
        """The boss that beat the tanks, large, with a gloat. Built once and drawn as one opaque blit."""
        bg = pygame.Surface((W, H)).convert()
        col = BOSS_COLORS[kind]
        dark = (10, 8, 14)
        bg.fill(dark)
        cx, cy = 390, 380
        glow = 0.65 if kind == 'spider' else 0.45     # her legs are dark
        for r in range(520, 0, -8):    # glow behind the boss, opaque rings fading out
            k = (1 - r / 520) ** 2 * glow
            pygame.draw.circle(bg, [int(d + (c - d) * k) for c, d in zip(col, dark)], (cx, cy), r)
        big = make_boss_sprites(kind, 9)
        if kind == 'spider':
            for i in range(14):    # a web stretched across the corner behind her
                a = math.pi / 2 * i / 13
                pygame.draw.line(bg, (70, 70, 82), (0, 0), (math.cos(a) * 640, math.sin(a) * 640), 2)
            for r in range(80, 640, 80):
                pts = [(math.cos(math.pi / 2 * i / 13) * r, math.sin(math.pi / 2 * i / 13) * r) for i in range(14)]
                pygame.draw.lines(bg, (70, 70, 82), False, pts, 2)
        elif kind == 'witch':
            pygame.draw.circle(bg, (235, 230, 190), (cx + 60, cy - 90), 200)    # full moon
            pygame.draw.circle(bg, (215, 210, 170), (cx + 10, cy - 140), 36)
            pygame.draw.circle(bg, (215, 210, 170), (cx + 140, cy - 40), 24)
        pygame.draw.ellipse(bg, (5, 4, 8), (cx - 230, cy + 190, 460, 70))       # shadow
        if kind == 'snake':
            coil = []    # the body coiled up on the ground around her, drawn back to front
            for i, img in enumerate(big['segs']):
                a = 1.3 + i * 0.6
                rr = 1 - 0.3 * i / len(big['segs'])
                img = pygame.transform.smoothscale(img, (img.get_width() * 2 // 3, img.get_height() * 2 // 3))
                coil.append((cy + 150 + math.sin(a) * 70 * rr, cx + math.cos(a) * 230 * rr, img))
            for y, x, img in sorted(coil, key=lambda c: c[0]):
                blit_center(bg, img, x, y)
        blit_center(bg, big[('base', 1)], cx, cy)
        if kind == 'knight':
            blit_center(bg, big['sword'], cx + 250, cy - 10)
        elif kind == 'witch':
            for x, y in ((cx - 260, cy + 180), (cx + 230, cy + 220)):
                blit_center(bg, big['cat'], x, y)

        tx = 960
        font = pygame.font.Font(None, 52)
        self.text(BOSS_NAMES[kind], self.font_med, col, (tx, 150), bg)
        lines = random.choice(BOSS_TAUNTS[kind]).split("\n")
        for i, line in enumerate(lines):
            y = 300 - (len(lines) - 1) * 28 + i * 56
            for dx, dy, c in ((3, 3, (0, 0, 0)), (0, 0, (255, 235, 200))):
                img = font.render(("„" if i == 0 else "") + line + ("“" if i == len(lines) - 1 else ""), True, c)
                bg.blit(img, img.get_rect(center=(tx + dx, y + dy)))
        self.text("TANKI SO PADLI", self.font_small, (255, 110, 90), (tx, 450), bg)
        total = sum(p.kills for p in self.players)
        self.text(f"Dosežen val {self.wave}   •   uničenih pošasti: {total}", self.font_hud, (210, 210, 210), (tx, 490), bg)
        return bg

    def draw(self):
        if self.state == 'coopover' and self.taunt:
            self.screen.blit(self.taunt, (0, 0))
            if self.timer <= 0 and int(self.now * 2) % 2:
                self.text("Pritisni A za nadaljevanje", self.font_small, (220, 220, 220), (960, 640))
        elif self.state == 'lobby':
            self.draw_lobby()
        else:
            self.draw_world()
            self.draw_hud()
            self.draw_overlay()
        if self.quiz:
            self.draw_quiz()

    # ---- main loop

    def self_check(self):
        """Play a few seconds of every mode with idle keyboard players, then return."""
        self.players = [Player(0, 'kb1'), Player(1, 'kb2')]
        for mode in ('versus', 'coop', 'race'):
            self.mode = mode
            self.start_match()
            for _ in range(240):
                self.update(1 / 60)
                self.draw()
        self.quiz = Quiz()
        self.draw()

    async def run(self):
        added = {pygame.JOYDEVICEADDED, getattr(pygame, 'CONTROLLERDEVICEADDED', -1)}
        removed = {pygame.JOYDEVICEREMOVED, getattr(pygame, 'CONTROLLERDEVICEREMOVED', -1)}
        while True:
            # in a browser the frame rate comes from the display refresh; ticking with a limit would wait a second frame
            dt = min(self.clock.tick(0 if WEB else FPS) / 1000.0, 1 / 30)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                if e.type in added:
                    self.scan_pads()
                elif e.type in removed:
                    self.remove_pad(e.instance_id)
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_F11:
                        if not WEB:     # in a browser, F11 already makes the page fullscreen
                            pygame.display.toggle_fullscreen()
                    elif self.quiz and len(e.unicode) == 1 and e.unicode in "0123456789":   # top row and keypad
                        self.quiz.type_digit(int(e.unicode))
                    elif self.quiz and e.key == pygame.K_BACKSPACE:
                        self.quiz.backspace()
                    elif e.key == pygame.K_TAB and self.state == 'lobby' and not self.quiz:
                        self.toggle_mode()
                    elif e.key == pygame.K_ESCAPE:
                        if self.state == 'lobby':
                            if not WEB:     # a browser tab can't be quit
                                return
                        self.to_lobby()
            keys = pygame.key.get_pressed()
            for pad in list(self.pads.values()):
                pad.poll(keys)
            self.update(dt)
            self.draw()
            pygame.display.flip()
            await asyncio.sleep(0)  # the browser only gets to run (and show the frame) here


async def main():
    pygame.mixer.pre_init(22050, -16, 2, 512)
    pygame.init()
    if sdl_ctrl:
        sdl_ctrl.init()
    game = Game(fullscreen='--windowed' not in sys.argv and not WEB)
    if '--check' in sys.argv:   # the Windows build runs this to prove the bundled .exe starts
        game.self_check()
    else:
        await game.run()
    pygame.quit()


if __name__ == '__main__':
    asyncio.run(main())
