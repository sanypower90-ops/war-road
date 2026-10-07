import unittest
from simulation import Room, RuleError, DEFS, MATCH_SECONDS

class CombatTests(unittest.TestCase):
    def room(self):
        r=Room('TEST01',seed=3);r.join();return r
    def advance(self,r,seconds):
        for _ in range(round(seconds/.04)):r.tick(.04)
    def test_waiting_and_authentication(self):
        r=Room('TEST01');r.tick(1);self.assertEqual(r.t,0)
        with self.assertRaises(RuleError):r.spawn(0,'infantry',1)
        with self.assertRaises(RuleError):r.role('forged')
        token=r.join();self.assertEqual(r.role(token),1)
        with self.assertRaises(RuleError):r.join()
    def test_energy_cost_regeneration_cap_and_validation(self):
        r=self.room();r.spawn(0,'infantry',0);self.assertEqual(r.energy[0],5)
        r.spawn(0,'infantry',0)
        self.advance(r,.6)
        before=r.energy[0]
        r.spawn(0,'infantry',0)
        with self.assertRaises(RuleError):r.spawn(0,'infantry',True)
        self.assertEqual(r.energy[0],before)
        self.advance(r,20);self.assertEqual(r.energy[0],10)
    def test_opponent_view_mirrors_lane(self):
        r=self.room();u=r.spawn(1,'infantry',0)
        self.assertEqual(u.lane,2);self.assertEqual(u.direction,16)
    def test_counters_and_air(self):
        r=self.room();r.energy=[10,10];horse=r.spawn(1,'cavalry',0)
        hp=horse.hp;r.damage('spearman',0,('unit',horse.id),24,horse.x,horse.y)
        self.assertAlmostEqual(hp-horse.hp,24*1.8*.92)
        r.t=1;r.energy[1]=10;fly=r.spawn(1,'flying_dino',1)
        r.damage('infantry',0,('unit',fly.id),50,fly.x,fly.y);self.assertEqual(fly.hp,150)
        r.damage('archer',0,('unit',fly.id),18,fly.x,fly.y);self.assertEqual(fly.hp,132)
    def test_melee_damage_occurs_after_windup(self):
        r=self.room();a=r.spawn(0,'infantry',1);b=r.spawn(1,'infantry',1)
        a.y=250;b.y=215;r.tick(.04);self.assertEqual(b.hp,100)
        self.advance(r,.6);self.assertLess(b.hp,100);self.assertLess(a.hp,100)
    def test_ranged_projectile_then_damage(self):
        r=self.room();a=r.spawn(0,'archer',1);b=r.spawn(1,'infantry',1)
        a.y=300;b.y=180;self.advance(r,.64);self.assertTrue(r.projectiles);self.assertEqual(b.hp,100)
        self.advance(r,.4);self.assertLess(b.hp,100)
    def test_base_damage_and_winner(self):
        r=self.room();a=r.spawn(0,'infantry',1);a.y=60;r.bases[1]=10
        self.advance(r,1);self.assertEqual(r.status,'finished');self.assertEqual(r.winner,0)
        t=r.t;r.tick(1);self.assertEqual(r.t,t)
    def test_time_limit_and_draw(self):
        r=self.room();r.t=MATCH_SECONDS-.04;r.tick(.05);self.assertEqual(r.status,'finished');self.assertIsNone(r.winner)
        r=self.room();r.bases[0]=1300;r.t=MATCH_SECONDS-.04;r.tick(.05);self.assertEqual(r.winner,1)
    def test_all_troops_can_complete_battle(self):
        for kind in DEFS:
            with self.subTest(kind=kind):
                r=self.room();r.energy=[10,10];r.spawn(0,kind,1);r.spawn(1,'infantry',1)
                self.advance(r,90.1);self.assertEqual(r.status,'finished')
                self.assertTrue(all(0<=hp<=1400 for hp in r.bases))
    def test_bot_summons_and_attacks(self):
        r=Room('BOT001',bot=True,seed=7);self.advance(r,30)
        self.assertTrue(r.units);self.assertLess(r.bases[0],1400)

if __name__=='__main__':unittest.main(verbosity=2)
