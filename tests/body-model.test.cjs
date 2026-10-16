const test=require('node:test'),assert=require('node:assert/strict');
const B=require('../frontend/body-editor.js'),C=require('../frontend/cover-editor.js');
const T=require('../frontend/timeline-model.js');
const {DraftState}=require('../frontend/draft-state.js');
const cover=()=>({enabled:true,title:'翻新🏠88萬',photo_id:'p',color:'#ffffff',font_size:120,
  highlights:[{start:3,end:5,color:'#ff0000'}],body:B.newBody()});
test('正文時間軸使用全片時間，整段與左右邊界可拖曳，排除封面且自動跟隨片長',()=>{
  const c=cover(),p=[{id:'p',duration:4,labels:[]},{id:'q',duration:4,labels:[]}];
  assert.equal(c.body.font_size,100);assert.equal(B.item(c,.3,8.3).duration,8);
  let item=B.item(c,.3,8.3);assert.equal(T.items(p,[],.3,item).filter(i=>i.type==='body_title').length,1);
  T.edit(item,'right',-2,p,[],.3,c.body);assert.ok(Math.abs(c.body.end-6.3)<1e-8);assert.equal(c.body.auto_timing,false);
  item=B.item(c,.3,8.3);T.edit(item,'move',1,p,[],.3,c.body);assert.ok(Math.abs(c.body.start-1.3)<1e-8);assert.ok(Math.abs(c.body.end-7.3)<1e-8);
  item=B.item(c,.3,8.3);T.edit(item,'left',1,p,[],.3,c.body);assert.ok(Math.abs(c.body.start-2.3)<1e-8);
  B.fit(c.body,.3,3.3);assert.equal(c.body.end,3.3);assert.equal(p[0].duration,4);
  c.body.auto_timing=true;assert.equal(B.item(c,.3,12.3).duration,12);
});
test('正文預覽時間包含起點不含終點，舊預設升級一次且保留人工字級',()=>{
  const b={...B.newBody(),auto_timing:false,start:.6,end:1.5};
  assert.equal(B.visible(b,.5,.3,2.3),false);assert.equal(B.visible(b,.6,.3,2.3),true);assert.equal(B.visible(b,1.5,.3,2.3),false);
  const old={font_size:88};assert.equal(B.upgrade(old),true);assert.equal(old.font_size,100);assert.equal(B.upgrade(old),false);
  const manual={font_size:180};B.upgrade(manual);assert.equal(manual.font_size,180);
  const legacy={font_size:120,x:.5,y:530/1920,version:3};B.upgrade(legacy);
  assert.deepEqual([legacy.font_size,legacy.x,legacy.y],[100,.5,.245]);
  legacy.font_size=120;legacy.y=.7;assert.equal(B.upgrade(legacy),false);assert.equal(legacy.font_size,120);assert.equal(legacy.y,.7);
});
test('正文位置以中心比例儲存，預設100px／50%／24.5%，既有位置升級時保留',()=>{
  const b=B.newBody();assert.equal(B.box(b).x,142);assert.equal(B.box(b).y,290);
  const old={font_size:140,version:2,start:2,end:5,auto_timing:false};B.upgrade(old);
  assert.equal(old.font_size,140);assert.equal(old.start,2);assert.equal(B.box(old).y,290);
  const manual={...old,x:.4,y:.7,version:2};B.upgrade(manual);assert.equal(manual.x,.4);assert.equal(manual.y,.7);
  const c=cover();c.body.x=NaN;assert.ok(B.validate(c));c.body.x=.5;c.body.y=1.1;assert.ok(B.validate(c));
});
test('正文連動封面文字及Unicode局部色彩，取消連動複製後可獨立編輯',()=>{
  const c=cover();assert.equal(B.validate(c),null);
  assert.equal(B.effective(c).title,c.title);assert.equal(C.colors(B.effective(c))[3],'#ff0000');
  c.title='封面更新';c.highlights=[{start:0,end:2,color:'#ffff00'}];assert.equal(C.colors(B.effective(c))[0],'#ffff00');
  B.detach(c);assert.equal(c.body.title,'封面更新');assert.equal(c.body.highlights[0].color,'#ffff00');
  c.title='封面再更新';c.highlights[0].color='#00ff00';assert.equal(B.effective(c).title,'封面更新');assert.equal(c.body.highlights[0].color,'#ffff00');
  c.body.highlights[0].end=99;assert.ok(B.validate(c));
});
test('正文未同步設定及連動模式經舊回覆／重建後保留，整批輸出包含最新樣式',()=>{
  const d=new DraftState(),rows=[{id:'p',duration:2,labels:[]}],c=cover();d.receive(rows,'s',1,null,[],[],[],c);
  B.detach(d.cover);d.cover.body.title='正文獨立';d.cover.body.highlights=[];d.touch(rows);
  const sent=d.snapshot('one');d.cover.body.color='#ffff00';d.touch(rows);
  d.receive(rows,'s',2,{nonce:'one',ok:true},[],[],[],sent.cover);
  assert.equal(d.cover.body.color,'#ffff00');const restored=new DraftState();assert.ok(restored.restore(d.persisted(),'s'));
  const latest=restored.snapshot('two','export','r');assert.equal(latest.cover.body.title,'正文獨立');assert.equal(latest.cover.body.follow_cover,false);assert.equal(latest.cover.body.color,'#ffff00');
});
