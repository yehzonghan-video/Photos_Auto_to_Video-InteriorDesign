const test=require('node:test'),assert=require('node:assert/strict');
const B=require('../frontend/body-editor.js'),C=require('../frontend/cover-editor.js');
const {DraftState}=require('../frontend/draft-state.js');
const cover=()=>({enabled:true,title:'翻新🏠88萬',photo_id:'p',color:'#ffffff',font_size:120,
  highlights:[{start:3,end:5,color:'#ff0000'}],body:B.newBody()});
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
