"""Run with the bundled Python runtime; listens only on this computer."""
import io
import os
import json
import re
import secrets
import threading
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from PIL import Image
from simulation import Room, RuleError, DEFS, MATCH_SECONDS, BASE_HP, MAX_ENERGY, REGEN, UPGRADE_COSTS

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT.parent / 'troop-army' / 'refined'
SPRITES = ROOT / 'sprites'
HOST = os.environ.get('HOST', '0.0.0.0' if os.environ.get('PORT') else '127.0.0.1')
PORT = int(os.environ.get('PORT', '8770'))
MAX_ROOMS = int(os.environ.get('MAX_ROOMS', '20'))
ROOMS, SEEN = {}, {}
LOCK, IMAGE_LOCK = threading.RLock(), threading.Lock()
STOP = threading.Event()
WAITING_TIMEOUT = 45


@lru_cache(maxsize=128)
def atlas(unit, direction):
    packed=SPRITES/unit/f'{direction}.png'
    if packed.is_file():return packed.read_bytes()
    with IMAGE_LOCK:
        board = Image.new('RGBA', (896,896))
        i = 0
        for action in ('idle','walk','attack'):
            for phase in range(1 if action == 'idle' else 24):
                p = ASSETS / unit / 'frames' / action / f'{unit}_{action}_d{direction:02}_f{phase:02}.png'
                with Image.open(p) as im:
                    board.paste(im.resize((128,128),Image.Resampling.LANCZOS), (i%7*128,i//7*128))
                i += 1
        out=io.BytesIO();board.save(out,format='PNG',compress_level=2)
        return out.getvalue()


@lru_cache(maxsize=9)
def thumb(unit):
    packed=SPRITES/unit/'thumb.png'
    if packed.is_file():return packed.read_bytes()
    with Image.open(ASSETS/unit/'frames'/'idle'/f'{unit}_idle_d20_f00.png') as im:
        out=io.BytesIO();im.resize((96,96),Image.Resampling.LANCZOS).save(out,format='PNG')
        return out.getvalue()


def waiting_rooms(now):
    """Public room information only; never expose player credentials."""
    return [dict(room=room.code, players=1, max_players=2,
                 waiting_seconds=max(0,int(now-room.created)))
            for room in sorted(ROOMS.values(),key=lambda r:r.created,reverse=True)
            if not room.bot and room.status=='waiting' and room.tokens[1] is None
            and now-SEEN.get(room.tokens[0],room.created)<=WAITING_TIMEOUT]


def run_simulation():
    last=time.monotonic()
    while not STOP.wait(.04):
        now=time.monotonic();dt=min(.12,now-last);last=now
        with LOCK:
            for code,room in list(ROOMS.items()):
                room.tick(dt)
                if room.status=='waiting' and now-SEEN.get(room.tokens[0],room.created)>WAITING_TIMEOUT:
                    room.finish(None,'대기방 연결 종료')
                if not room.bot and room.status == 'playing':
                    for side,token in enumerate(room.tokens):
                        if token and now-SEEN.get(token,now)>25:
                            room.finish(1-side,'상대 연결 종료')
                if room.status=='finished' and not hasattr(room,'ended_at'):
                    room.ended_at=now
                if now-room.created > 600 or (room.status=='finished' and now-room.ended_at>60):
                    for token in room.tokens:
                        SEEN.pop(token,None)
                    del ROOMS[code]


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def send(self, data, content='application/json; charset=utf-8', status=200, cache=False):
        if isinstance(data,(dict,list)):
            data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',content)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','public, max-age=86400' if cache else 'no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass

    def player(self, code):
        room=ROOMS.get(code)
        if not room:raise RuleError('방을 찾을 수 없습니다. 새 방을 만들어 주세요.')
        header=self.headers.get('Authorization','')
        token=header[7:] if header.startswith('Bearer ') else ''
        role=room.role(token);SEEN[token]=time.monotonic()
        return room,role

    def do_GET(self):
        path=urlsplit(self.path)
        try:
            if path.path == '/healthz':
                return self.send({'ok':True})
            if path.path == '/':
                return self.send((ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
            asset=re.fullmatch(r'/assets/([a-z0-9_-]+\.(?:png|webp|wav|mp3|js))',path.path)
            if asset:
                file=ROOT/'assets'/asset[1]
                if file.is_file():
                    content={'.png':'image/png','.webp':'image/webp','.wav':'audio/wav','.mp3':'audio/mpeg','.js':'text/javascript; charset=utf-8'}[file.suffix]
                    return self.send(file.read_bytes(),content,cache=True)
                return self.send({'error':'자료를 찾을 수 없습니다.'},status=404)
            if path.path == '/api/config':
                units={}
                for u,d in DEFS.items():
                    if SPRITES.is_dir():
                        anchor=json.loads((SPRITES/'metadata.json').read_text())[u]['anchor']
                    else:
                        anchor=json.loads((ASSETS/u/'manifest.json').read_text())['ground_anchor'][1]/512
                    units[u]={**d,'anchor':anchor}
                return self.send(dict(units=units,duration=MATCH_SECONDS,base_hp=BASE_HP,max_energy=MAX_ENERGY,regen=REGEN,upgrade_costs=UPGRADE_COSTS))
            if path.path == '/api/rooms':
                with LOCK:
                    return self.send(dict(rooms=waiting_rooms(time.monotonic())))
            if path.path == '/api/state':
                with LOCK:
                    room,role=self.player(parse_qs(path.query).get('room',[''])[0])
                    return self.send(room.snapshot(role))
            match=re.fullmatch(r'/atlas/([a-z_]+)/([0-9]{1,2})\.png',path.path)
            if match and match[1] in DEFS and int(match[2])<32:
                return self.send(atlas(match[1],int(match[2])),'image/png',cache=True)
            match=re.fullmatch(r'/thumb/([a-z_]+)\.png',path.path)
            if match and match[1] in DEFS:
                return self.send(thumb(match[1]),'image/png',cache=True)
            self.send({'error':'페이지를 찾을 수 없습니다.'},status=404)
        except RuleError as e:
            self.send({'error':str(e)},status=400)
        except Exception:
            self.send({'error':'자료를 불러오지 못했습니다.'},status=500)

    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=4096:raise RuleError('요청 크기를 확인해 주세요.')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise RuleError('요청 형식이 올바르지 않습니다.')
            with LOCK:
                path=urlsplit(self.path).path
                if path == '/api/create':
                    if sum(r.status!='finished' for r in ROOMS.values())>=MAX_ROOMS:raise RuleError('진행 중인 방이 많습니다. 잠시 후 다시 시도해 주세요.')
                    code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
                    while code in ROOMS:code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
                    room=Room(code,bot=body.get('mode')=='bot');room.created=time.monotonic();ROOMS[code]=room
                    SEEN[room.tokens[0]]=room.created
                    return self.send(dict(room=code,token=room.tokens[0],role=0))
                if path == '/api/join':
                    code=str(body.get('room','')).strip().upper();room=ROOMS.get(code)
                    if not room:raise RuleError('방 코드를 다시 확인해 주세요.')
                    now=time.monotonic()
                    if room.status=='waiting' and now-SEEN.get(room.tokens[0],room.created)>WAITING_TIMEOUT:
                        room.finish(None,'대기방 연결 종료')
                        raise RuleError('방장이 나간 방입니다. 다른 대기방을 선택해 주세요.')
                    token=room.join();SEEN[token]=time.monotonic()
                    SEEN[room.tokens[0]]=time.monotonic()
                    return self.send(dict(room=code,token=token,role=1))
                room,role=self.player(body.get('room',''))
                if path == '/api/spawn':
                    u=room.spawn(role,body.get('unit'),body.get('lane'))
                    return self.send(dict(ok=True,id=u.id))
                if path == '/api/upgrade':
                    level=room.upgrade(role,body.get('unit'),body.get('stat'))
                    return self.send(dict(ok=True,level=level))
                if path == '/api/leave':
                    room.finish(1-role if not room.bot else None,'상대 퇴장' if not room.bot else '연습 종료')
                    return self.send(dict(ok=True))
                self.send({'error':'요청을 찾을 수 없습니다.'},status=404)
        except (RuleError,ValueError,TypeError) as e:
            self.send({'error':str(e)},status=400)
        except Exception:
            self.send({'error':'요청을 처리하지 못했습니다.'},status=500)


if __name__=='__main__':
    threading.Thread(target=run_simulation,daemon=True).start()
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    server.daemon_threads=True
    print(f'War Road server listening on {HOST}:{PORT}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:STOP.set();server.server_close()
