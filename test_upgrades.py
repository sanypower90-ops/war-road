import unittest
from simulation import Room, RuleError, UPGRADE_COSTS
class UpgradeTests(unittest.TestCase):
 def room(self):
  r=Room('UPTEST');r.join();return r
 def test_free_summon_without_any_delay(self):
  r=self.room();r.energy[0]=0
  for _ in range(3):
   for kind in r.upgrades[0]:r.spawn(0,kind,0)
  self.assertEqual(len(r.units),27);self.assertEqual(r.t,0);self.assertEqual(r.energy[0],0)
  for _ in range(3):r.spawn(0,'infantry',0)
  with self.assertRaises(RuleError):r.spawn(0,'infantry',0)
 def test_costs_limit_and_isolation(self):
  r=self.room()
  for level,cost in enumerate(UPGRADE_COSTS):
   r.energy[0]=10;r.upgrade(0,'infantry','attack');self.assertEqual(r.energy[0],10-cost)
  with self.assertRaises(RuleError):r.upgrade(0,'infantry','attack')
  self.assertEqual(r.upgrades[1]['infantry']['attack'],0)
  self.assertEqual(r.upgrades[0]['archer']['attack'],0)
  r.energy[0]=0
  with self.assertRaises(RuleError):r.upgrade(0,'infantry','defense')
 def test_existing_units_receive_attack_and_defense(self):
  r=self.room();a=r.spawn(0,'infantry',0);b=r.spawn(1,'infantry',0)
  r.upgrade(0,'infantry','attack');r.upgrade(1,'infantry','defense')
  r.launch(a,('unit',b.id));self.assertAlmostEqual(b.hp,100-18*1.15*.92)
 def test_validation_and_reset(self):
  r=Room('WAIT')
  with self.assertRaises(RuleError):r.upgrade(0,'infantry','attack')
  r.join()
  for k,s in [('fake','attack'),('infantry','hp')]:
   with self.assertRaises(RuleError):r.upgrade(0,k,s)
  r.upgrade(0,'infantry','attack');self.assertEqual(self.room().upgrades[0]['infantry']['attack'],0)
