"""Integration checks against the running localhost server, no browser credentials used."""
import io,json,unittest,os
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from PIL import Image
BASE=os.environ.get('TEST_BASE_URL','http://127.0.0.1:8770')
def call(path,body=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urlopen(req,timeout=30) as r:return r.status,json.load(r)
    except HTTPError as e:return e.code,json.load(e)
class APITests(unittest.TestCase):
    def test_two_players_share_authoritative_state(self):
        status,a=call('/api/create',{'mode':'pvp'});self.assertEqual(status,200)
        self.assertEqual(call('/api/spawn',{'room':a['room'],'unit':'infantry','lane':0},a['token'])[0],400)
        status,b=call('/api/join',{'room':a['room']});self.assertEqual(status,200)
        self.assertEqual(call('/api/join',{'room':a['room']})[0],400)
        self.assertEqual(call('/api/state?room='+a['room'],token='forged')[0],400)
        status,_=call('/api/spawn',{'room':a['room'],'unit':'infantry','lane':0,'side':1,'energy':999},a['token']);self.assertEqual(status,200)
        _,sa=call('/api/state?room='+a['room'],token=a['token']);_,sb=call('/api/state?room='+a['room'],token=b['token'])
        self.assertEqual(sa['role'],0);self.assertEqual(sb['role'],1)
        self.assertEqual(sa['units'][0]['id'],sb['units'][0]['id']);self.assertEqual(sa['units'][0]['side'],0)
        self.assertLess(sa['energy'][0],5);self.assertGreaterEqual(sa['energy'][1],5)
        self.assertEqual(call('/api/spawn',{'room':a['room'],'unit':'armored_chariot','lane':1},b['token'])[0],400)
        call('/api/leave',{'room':a['room']},a['token']);_,s=call('/api/state?room='+a['room'],token=b['token']);self.assertEqual(s['winner'],1)
    def test_public_lobby_preserves_invites_and_removes_joined_or_closed_rooms(self):
        _,host=call('/api/create',{'mode':'pvp'})
        _,bot=call('/api/create',{'mode':'bot'})
        _,listing=call('/api/rooms')
        item=next(r for r in listing['rooms'] if r['room']==host['room'])
        self.assertEqual(item['players'],1);self.assertNotIn(host['token'],str(listing))
        self.assertNotIn(bot['room'],[r['room'] for r in listing['rooms']])
        _,guest=call('/api/join',{'room':host['room']})
        self.assertNotIn(host['room'],[r['room'] for r in call('/api/rooms')[1]['rooms']])
        self.assertEqual(call('/api/join',{'room':host['room']})[0],400)
        call('/api/leave',{'room':host['room']},host['token'])
        call('/api/leave',{'room':bot['room']},bot['token'])
        _,closed=call('/api/create',{'mode':'pvp'})
        call('/api/leave',{'room':closed['room']},closed['token'])
        self.assertNotIn(closed['room'],[r['room'] for r in call('/api/rooms')[1]['rooms']])

    def test_all_nine_sprite_atlases(self):
        status,config=call('/api/config');self.assertEqual(status,200);self.assertEqual(len(config['units']),9)
        for kind in config['units']:
            with self.subTest(kind=kind):
                with urlopen(BASE+'/atlas/'+kind+'/0.png',timeout=30) as r:
                    im=Image.open(io.BytesIO(r.read()));self.assertEqual(im.size,(896,896));self.assertEqual(im.mode,'RGBA')
                    for row,col in ((0,0),(0,1),(3,4),(6,6)):
                        self.assertIsNotNone(im.crop((col*128,row*128,(col+1)*128,(row+1)*128)).getbbox())
if __name__=='__main__':unittest.main(verbosity=2)
