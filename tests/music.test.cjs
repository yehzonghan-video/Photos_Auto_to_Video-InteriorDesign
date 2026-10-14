const test=require('node:test'),assert=require('node:assert/strict');
const M=require('../frontend/music.js'),{DraftState}=require('../frontend/draft-state.js');
test('BGM預設1秒線性淡出，短音樂不循環與0秒淡出',()=>{
  const m={...M.newMusic(),source:'audio'};assert.equal(m.fade_out,1);
  assert.equal(M.gainAt(m,.5,2.3,1),.5);assert.ok(Math.abs(M.gainAt(m,.5,2.3,1.8)-.25)<1e-9);
  assert.equal(M.gainAt(m,.5,2.3,2.3),0);assert.equal(M.gainAt({...m,loop:false},.5,3,.25),.25);
  assert.equal(M.gainAt({...m,fade_out:0},.5,3,2.9),.5);
  assert.ok(M.validate({...m,fade_out:NaN},{id:'audio'}));
});
test('BGM未同步音量／淡出保留，舊回覆不覆蓋新編輯，音樂替換只更新來源',()=>{
  const d=new DraftState(),rows=[{id:'p',labels:[],duration:3}],m={...M.newMusic(),source:'a'};
  d.receive(rows,'s',1,null,[],[],[],null,m);d.music.fade_out=2;d.touch(rows);
  const sent=d.snapshot('one');d.music.volume=.2;d.touch(rows);
  d.receive(rows,'s',2,{nonce:'one',ok:true},[],[],[],null,sent.music);
  assert.equal(d.music.volume,.2);assert.equal(d.music.fade_out,2);
  d.receive(rows,'s',3,null,[],[],[],null,{...m,source:'b'});assert.equal(d.music.source,'b');assert.equal(d.music.volume,.2);
  const restored=new DraftState();restored.restore(d.persisted(),'s');assert.equal(restored.music.fade_out,2);
  assert.ok(!JSON.stringify(d.persisted()).includes('base64'));
});
test('Web Audio排定淡出、循環位置與録製音軌，停止時清理節點（模擬AudioContext）',()=>{
  const commands=[],track={kind:'audio'},source={connect(){},disconnect(){commands.push('disconnect')},start:(...a)=>commands.push(['start',...a]),stop:(...a)=>commands.push(['stop',...a])};
  const gain={connect(){},disconnect(){},gain:{setValueAtTime:(...a)=>commands.push(['set',...a]),linearRampToValueAtTime:(...a)=>commands.push(['ramp',...a])}};
  const context={currentTime:10,destination:{},createBufferSource:()=>source,createGain:()=>gain,createMediaStreamDestination:()=>({stream:{getAudioTracks:()=>[track]}})};
  const player=new M.MusicPlayer(()=>context);player.context=context;player.asset={id:'a',duration:.5};player.buffer={duration:.5};
  const stream=player.start({...M.newMusic(),source:'a'},1,3,true);
  assert.equal(stream.getAudioTracks()[0],track);assert.ok(source.loop);
  assert.deepEqual(commands.find(v=>v[0]==='start'),['start',10,0]);
  assert.deepEqual(commands.find(v=>v[0]==='ramp'),['ramp',0,12]);
  player.stop();assert.equal(player.source,null);assert.ok(commands.includes('disconnect'));
});
