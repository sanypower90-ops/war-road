import unittest
from unittest.mock import patch
from simulation import Room
from server import waiting_rooms,ROOMS,SEEN,WAITING_TIMEOUT

class LobbyTests(unittest.TestCase):
 def make(self,code,created,bot=False):
  r=Room(code,bot=bot);r.created=created;return r
 def test_only_live_waiting_human_rooms_are_public(self):
  a=self.make('WAIT01',90);b=self.make('PLAY01',90);b.join()
  c=self.make('DONE01',90);c.finish(None,'done');d=self.make('BOT001',90,True)
  old=self.make('OLD001',0)
  with patch.dict(ROOMS,{r.code:r for r in (a,b,c,d,old)},clear=True),patch.dict(SEEN,{a.tokens[0]:99},clear=True):
   self.assertEqual(waiting_rooms(100),[dict(room='WAIT01',players=1,max_players=2,waiting_seconds=10)])
 def test_public_list_contains_no_auth_tokens(self):
  a=self.make('WAIT01',99)
  with patch.dict(ROOMS,{a.code:a},clear=True),patch.dict(SEEN,{},clear=True):
   result=waiting_rooms(100)[0]
   self.assertNotIn(a.tokens[0],str(result));self.assertEqual(set(result),{'room','players','max_players','waiting_seconds'})
 def test_newest_room_first_and_join_removes_room(self):
  a=self.make('WAIT01',90);b=self.make('WAIT02',95)
  with patch.dict(ROOMS,{a.code:a,b.code:b},clear=True),patch.dict(SEEN,{},clear=True):
   self.assertEqual([r['room'] for r in waiting_rooms(100)],['WAIT02','WAIT01']);b.join()
   self.assertEqual([r['room'] for r in waiting_rooms(100)],['WAIT01'])
 def test_host_poll_keeps_long_waiting_room_visible(self):
  a=self.make('WAIT01',0)
  with patch.dict(ROOMS,{a.code:a},clear=True),patch.dict(SEEN,{a.tokens[0]:100},clear=True):
   self.assertEqual(len(waiting_rooms(100)),1);self.assertEqual(waiting_rooms(100+WAITING_TIMEOUT+1),[])
if __name__=='__main__':unittest.main()
