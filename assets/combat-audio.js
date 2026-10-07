// Original WAV samples are unlocked by a menu click and played once per attack impact.
const WarAudio=(()=>{
 let context,master,muted=localStorage.getItem('war-road-muted')==='1',loading,voices=0,activated=false,scene='lobby';
 const music={lobby:document.querySelector('#lobbyBgm'),battle:document.querySelector('#battleBgm')};
 for(const audio of Object.values(music)){audio.volume=.23;audio.muted=muted}
 function setScene(next){scene=next;for(const [name,audio] of Object.entries(music)){audio.muted=muted;if(name!==scene){audio.pause();audio.currentTime=0}else if(activated&&!muted){audio.play().catch(()=>{});}}update();}
 const buffers=new Map(),seen=new Map(),lastKind=new Map();
 const kinds=['infantry','spearman','archer','cavalry','shieldman','ground_dino','flying_dino','wood_chariot','armored_chariot'];
 function update(){for(const b of [document.querySelector('#sound'),document.querySelector('#lobbySound')]){if(!b)continue;b.textContent=!activated?'음악 켜기':muted?'소리 꺼짐':'소리 켜짐';b.setAttribute('aria-label',!activated?'음악 켜기':muted?'배경음악과 효과음 켜기':'배경음악과 효과음 끄기');b.setAttribute('aria-pressed',String(activated&&!muted));b.dataset.loaded=String(buffers.size);b.dataset.context=context?.state||'locked';b.dataset.bgm=scene}}
 async function unlock(){
  activated=true;setScene(scene);
  const AudioClass=window.AudioContext||window.webkitAudioContext;if(!AudioClass)return;
  if(!context){context=new AudioClass();master=context.createGain();master.gain.value=muted?0:.30;
   const limiter=context.createDynamicsCompressor();limiter.threshold.value=-15;limiter.ratio.value=6;limiter.attack.value=.003;limiter.release.value=.12;master.connect(limiter);limiter.connect(context.destination)}
  await context.resume();context.onstatechange=update;
  if(!loading)loading=Promise.all(kinds.map(async k=>{try{const r=await fetch('/assets/'+k+'-attack.wav');if(!r.ok)throw Error('sound asset');buffers.set(k,await context.decodeAudioData(await r.arrayBuffer()));update()}catch(e){console.warn('공격 효과음을 불러오지 못했습니다:',k)}}));
  update();
 }
 function play(kind,x,friendly=true){
  if(muted||!context||context.state!=='running'||!buffers.has(kind)||voices>=6)return;
  const now=context.currentTime;if(now-(lastKind.get(kind)??-1)<.07)return;lastKind.set(kind,now);
  const source=context.createBufferSource(),gain=context.createGain(),pan=context.createStereoPanner();
  source.buffer=buffers.get(kind);gain.gain.value=friendly?.65:.45;pan.pan.value=Math.max(-.65,Math.min(.65,(x/390-.5)*1.3));source.connect(gain);gain.connect(pan);pan.connect(master);
  const button=document.querySelector('#sound');if(button){button.dataset.played=String(Number(button.dataset.played||0)+1);button.dataset.last=kind}
  voices++;source.onended=()=>{voices--;source.disconnect();gain.disconnect();pan.disconnect()};source.start();
 }
 function observe(s){const next=s.status==='playing'?'battle':'lobby';if(next!==scene)setScene(next);if(s.status!=='playing')return;for(const u of s.units){const hit=u.attack_start+u.attack_duration*.60;if(u.attack_start<0||s.time<hit||seen.get(u.id)===u.attack_start)continue;seen.set(u.id,u.attack_start);if(s.time-hit<.25)play(u.kind,s.role===1?390-u.x:u.x,u.side===s.role)}}
 async function toggle(){if(activated)muted=!muted;else muted=false;localStorage.setItem('war-road-muted',muted?'1':'0');await unlock();if(master)master.gain.setTargetAtTime(muted?0:.30,context.currentTime,.02);setScene(scene);update();}
 function reset(){seen.clear();lastKind.clear()}
 return{unlock,observe,toggle,reset,update,setScene};
})();
