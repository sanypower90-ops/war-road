"""Authoritative, dependency-free combat simulation for the local prototype."""
import math
import random
import secrets
from dataclasses import dataclass, asdict

WIDTH, HEIGHT, LANES = 390, 600, (84, 195, 306)
MATCH_SECONDS, BASE_HP, MAX_ENERGY, REGEN = 90, 1400, 10, 1.25

UPGRADE_COSTS = (2, 4, 6, 8, 10)

# Balance values are prototype settings, not claims about a finished game.
DEFS = {
    'infantry': dict(name='보병', cost=2, hp=100, damage=18, speed=33, reach=24, cooldown=.95, radius=12, size=85, air=False, anti_air=False, shot=None, armor=0, tip='무료로 소환하는 근접 병력'),
    'spearman': dict(name='창병', cost=3, hp=120, damage=24, speed=29, reach=40, cooldown=1.15, radius=12, size=85, air=False, anti_air=False, shot=None, armor=0, tip='기마병에게 피해 1.8배'),
    'archer': dict(name='궁수', cost=3, hp=75, damage=18, speed=28, reach=135, cooldown=1.35, radius=11, size=85, air=False, anti_air=True, shot='arrow', armor=0, tip='지상·공중을 원거리 공격'),
    'cavalry': dict(name='기마병', cost=5, hp=185, damage=30, speed=52, reach=26, cooldown=1, radius=17, size=112, air=False, anti_air=False, shot=None, armor=.08, tip='빠르게 접근하는 돌격 병력'),
    'shieldman': dict(name='방패병', cost=4, hp=260, damage=10, speed=22, reach=23, cooldown=1.3, radius=15, size=91, air=False, anti_air=False, shot=None, armor=.25, tip='피해 25% 감소 · 전열 보호'),
    'ground_dino': dict(name='지상 공룡', cost=7, hp=410, damage=55, speed=26, reach=34, cooldown=1.65, radius=21, size=124, air=False, anti_air=False, shot=None, armor=.1, tip='높은 체력과 강한 근접 공격'),
    'flying_dino': dict(name='공중 공룡', cost=6, hp=150, damage=23, speed=40, reach=105, cooldown=1.4, radius=15, size=115, air=True, anti_air=True, shot='magic', armor=0, tip='근접 병력의 공격을 받지 않음'),
    'wood_chariot': dict(name='나무전차', cost=6, hp=195, damage=42, speed=20, reach=175, cooldown=2, radius=19, size=124, air=False, anti_air=True, shot='bolt', armor=.05, tip='긴 사거리 · 공중 공격 가능'),
    'armored_chariot': dict(name='철갑전차', cost=8, hp=300, damage=54, speed=17, reach=185, cooldown=2.3, radius=21, size=130, air=False, anti_air=False, shot='cannon', armor=.2, tip='지상 병력에 범위 피해'),
}


class RuleError(Exception):
    pass


@dataclass
class Unit:
    id: int
    kind: str
    side: int
    lane: int
    x: float
    y: float
    hp: float
    born: float
    direction: int
    vx: float = 0
    vy: float = 0
    action: str = 'walk'
    attack_start: float = -10
    attack_duration: float = 1
    next_attack: float = 0
    pending: tuple | None = None
    hit_at: float = 0


class Room:
    def __init__(self, code, bot=False, seed=None):
        self.code, self.bot = code, bot
        self.rng = random.Random(seed)
        self.tokens = [secrets.token_urlsafe(24), None]
        self.status = 'playing' if bot else 'waiting'
        self.energy = [0., 0.]
        self.upgrades = [{k:dict(attack=0, defense=0) for k in DEFS} for _ in range(2)]
        self.bases = [float(BASE_HP), float(BASE_HP)]
        self.units, self.projectiles, self.effects = [], [], []
        self.t = 0.
        self.winner, self.reason = None, ''
        self.next_id = 1
        self.bot_at = 2.1

    def join(self):
        if self.bot or self.status != 'waiting' or self.tokens[1]:
            raise RuleError('참가할 수 없는 방입니다.')
        self.tokens[1] = secrets.token_urlsafe(24)
        self.status = 'playing'
        return self.tokens[1]

    def role(self, token):
        if token and token in self.tokens:
            return self.tokens.index(token)
        raise RuleError('참가 정보가 유효하지 않습니다.')

    def spawn(self, side, kind, visible_lane):
        if self.status != 'playing':
            raise RuleError('대전이 시작되지 않았습니다.')
        if kind not in DEFS or type(visible_lane) is not int or visible_lane not in range(3):
            raise RuleError('병력 또는 길을 다시 선택해 주세요.')
        d = DEFS[kind]
        if sum(u.side == side and u.hp > 0 for u in self.units) >= 30:
            raise RuleError('전장에 병력이 가득합니다.')
        lane = visible_lane if side == 0 else 2 - visible_lane
        u = Unit(self.next_id, kind, side, lane, LANES[lane] + self.rng.uniform(-15, 15),
                 HEIGHT - 77 if side == 0 else 77, d['hp'], self.t, 0 if side == 0 else 16)
        self.next_id += 1
        self.units.append(u)
        return u

    def upgrade(self, side, kind, stat):
        if self.status != 'playing':
            raise RuleError('대전이 시작되지 않았습니다.')
        if kind not in DEFS or stat not in ('attack','defense'):
            raise RuleError('강화할 병력과 능력을 확인해 주세요.')
        level = self.upgrades[side][kind][stat]
        if level >= len(UPGRADE_COSTS):
            raise RuleError('최대 강화 단계입니다.')
        cost = UPGRADE_COSTS[level]
        if self.energy[side] + 1e-7 < cost:
            raise RuleError('강화 에너지가 부족합니다.')
        self.energy[side] -= cost
        self.upgrades[side][kind][stat] += 1
        return self.upgrades[side][kind][stat]

    def can_hit(self, attacker, defender):
        return not DEFS[defender.kind]['air'] or DEFS[attacker.kind]['anti_air']

    def position(self, target, attacker):
        if target[0] == 'base':
            return (attacker.x, 42 if target[1] == 1 else HEIGHT - 42)
        u = next((u for u in self.units if u.id == target[1] and u.hp > 0), None)
        return (u.x, u.y) if u else None

    def choose_target(self, u):
        d = DEFS[u.kind]
        enemies = [v for v in self.units if v.hp > 0 and v.side != u.side and self.can_hit(u, v)
                   and math.hypot(v.x-u.x, v.y-u.y) <= d['reach'] + 70]
        if enemies:
            v = min(enemies, key=lambda v: math.hypot(v.x-u.x, v.y-u.y) + (25 if v.lane != u.lane else 0))
            return ('unit', v.id)
        return ('base', 1-u.side)

    def finish(self, winner, reason):
        if self.status == 'finished':
            return
        self.status, self.winner, self.reason = 'finished', winner, reason

    def damage(self, attacker_kind, side, target, amount, x, y):
        if target[0] == 'base':
            self.bases[target[1]] = max(0, self.bases[target[1]] - amount)
        else:
            v = next((v for v in self.units if v.id == target[1] and v.hp > 0), None)
            if not v or v.side == side:
                return
            if DEFS[v.kind]['air'] and not DEFS[attacker_kind]['anti_air']:
                return
            if attacker_kind == 'spearman' and v.kind == 'cavalry':
                amount *= 1.8
            v.hp -= amount * (1-DEFS[v.kind]['armor']) * (1-.08*self.upgrades[v.side][v.kind]['defense'])
        self.effects.append(dict(x=x, y=y, at=self.t, kind='hit'))

    def launch(self, u, target):
        pos = self.position(target, u)
        if not pos:
            return
        d = DEFS[u.kind]
        x, y = pos
        amount = d['damage'] * (1+.15*self.upgrades[u.side][u.kind]['attack'])
        if d['shot']:
            self.projectiles.append(dict(id=self.next_id, kind=d['shot'], attacker=u.kind, side=u.side,
                                         target=target, damage=amount, fx=u.x, fy=u.y,
                                         tx=x, ty=y, x=u.x, y=u.y, born=self.t,
                                         duration=max(.15, math.hypot(x-u.x, y-u.y)/330)))
            self.next_id += 1
        else:
            self.damage(u.kind, u.side, target, amount, x, y)

    def tick(self, dt):
        if self.status != 'playing':
            return
        self.t += dt
        self.energy = [min(MAX_ENERGY, e+REGEN*dt) for e in self.energy]
        if self.bot and self.t >= self.bot_at:
            self.bot_at = self.t + self.rng.uniform(1.7, 2.8)
            available = list(DEFS)
            choices = [(k,stat) for k in DEFS for stat in ('attack','defense') if self.upgrades[1][k][stat]<5 and UPGRADE_COSTS[self.upgrades[1][k][stat]]<=self.energy[1]]
            if choices:
                self.upgrade(1,*self.rng.choice(choices))
            weights = [3 if k in ('infantry','archer','shieldman') else 1 for k in available]
            if any(DEFS[u.kind]['air'] for u in self.units if u.side == 0):
                weights = [w*3 if DEFS[k]['anti_air'] else w for k,w in zip(available,weights)]
            if available:
                lane = min(range(3), key=lambda lane: sum(u.side == 1 and u.lane == 2-lane for u in self.units))
                try:
                    self.spawn(1, self.rng.choices(available, weights)[0], lane)
                except RuleError:
                    pass
        for u in self.units:
            if u.hp <= 0:
                continue
            d = DEFS[u.kind]
            u.vx = u.vy = 0
            if u.pending and self.t >= u.hit_at:
                self.launch(u, u.pending)
                u.pending = None
            if self.t < u.attack_start + u.attack_duration:
                u.action = 'attack'
                continue
            target = self.choose_target(u)
            pos = self.position(target, u)
            if not pos:
                u.action = 'idle'
                continue
            dx, dy = pos[0]-u.x, pos[1]-u.y
            distance = math.hypot(dx, dy)
            extra = 0 if target[0] == 'base' else d['radius'] + 12
            if distance <= d['reach'] + extra:
                u.direction = round((math.atan2(dx, -dy) % math.tau) / math.tau * 32) % 32
                u.action = 'idle'
                if self.t >= u.next_attack:
                    u.attack_start = self.t
                    u.attack_duration = min(1, d['cooldown'])
                    u.next_attack = self.t+d['cooldown']
                    u.pending, u.hit_at = target, self.t+u.attack_duration*.60
                    u.action = 'attack'
            else:
                # Hold a lane; ranged attacks can aim into an adjacent lane.
                dy = -1 if u.side == 0 else 1
                friends = [v for v in self.units if v.id != u.id and v.side == u.side and v.hp > 0
                           and v.lane == u.lane and DEFS[v.kind]['air'] == d['air']
                           and 0 < (v.y-u.y)*dy < d['radius']+DEFS[v.kind]['radius']+3
                           and abs(v.x-u.x) < d['radius']+DEFS[v.kind]['radius']]
                u.action = 'idle' if friends else 'walk'
                if not friends:
                    u.vy = dy*d['speed']
                    u.y += u.vy*dt
                u.direction = 0 if u.side == 0 else 16
        remaining = []
        for p in self.projectiles:
            f = min(1, (self.t-p['born'])/p['duration'])
            p['x'], p['y'] = p['fx']+(p['tx']-p['fx'])*f, p['fy']+(p['ty']-p['fy'])*f
            if f < 1:
                remaining.append(p)
                continue
            self.damage(p['attacker'], p['side'], p['target'], p['damage'], p['tx'], p['ty'])
            if p['kind'] == 'cannon':
                for v in self.units:
                    if v.side != p['side'] and v.hp > 0 and not DEFS[v.kind]['air'] and ('unit',v.id) != p['target'] and math.hypot(v.x-p['tx'], v.y-p['ty']) < 42:
                        self.damage(p['attacker'], p['side'], ('unit',v.id), p['damage']*.6, v.x, v.y)
                self.effects.append(dict(x=p['tx'], y=p['ty'], at=self.t, kind='blast'))
        self.projectiles = remaining
        for u in self.units:
            if u.hp <= 0:
                self.effects.append(dict(x=u.x, y=u.y, at=self.t, kind='death'))
        self.units = [u for u in self.units if u.hp > 0]
        self.effects = [e for e in self.effects if self.t-e['at'] < .55]
        if min(self.bases) <= 0:
            self.finish(0 if self.bases[1] <= 0 else 1, '상대 기지 파괴')
        elif self.t >= MATCH_SECONDS:
            self.finish(None if abs(self.bases[0]-self.bases[1]) < 1e-6 else int(self.bases[1] > self.bases[0]), '시간 종료 · 기지 체력 비교')

    def snapshot(self, role):
        return dict(room=self.code, role=role, bot=self.bot, status=self.status, time=self.t,
                    energy=self.energy[:], upgrades=self.upgrades, bases=self.bases[:], winner=self.winner, reason=self.reason,
                    units=[asdict(u) for u in self.units],
                    projectiles=[{k:v for k,v in p.items() if k not in ('target', 'damage', 'attacker')} for p in self.projectiles],
                    effects=self.effects[:])
