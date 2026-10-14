const test=require('node:test'),assert=require('node:assert/strict');
const C=require('../frontend/cover-editor.js'),T=require('../frontend/timeline-model.js');
const {DraftState}=require('../frontend/draft-state.js');
const cover=()=>({enabled:true,title:'老屋88萬',photo_id:'p',color:'#ffffff',font_size:120,highlights:[]});
test('封面局部顏色以Unicode字元索引，後套用範圍優先且無效索引被拒絕',()=>{
  const c=cover();c.highlights=[{start:2,end:4,color:'#ff0000'},{start:3,end:5,color:'#ffff00'}];
  assert.deepEqual(C.colors(c),['#ffffff','#ffffff','#ff0000','#ffff00','#ffff00']);
  assert.equal(C.validate(c,[{id:'p'}]),null);c.highlights.push({start:0,end:99,color:'#00ff00'});assert.ok(C.validate(c,[{id:'p'}]));
});
test('單一時間軸包含固定0.3秒片頭；照片與文字偏移、PNG使用全片時間',()=>{
  const photos=[{id:'p',duration:2,name:'案例',labels:[{id:'l',text:'地板',start:.2,end:1.5,enter:.2}]}],png=[{id:'o',type:'png',start:.7,duration:1,enter:0,exit:0}];
  const prefix=C.duration(cover());assert.equal(prefix,.3);
  const clips=T.items(photos,png,prefix);assert.equal(clips[0].type,'cover');assert.equal(clips[0].duration,.3);
  assert.equal(clips[1].start,.3);assert.equal(clips[2].start,.5);assert.equal(clips[3].start,.7);
  T.edit(clips[0],'right',4,photos,png,prefix);assert.equal(photos[0].duration,2);
  T.edit(clips[2],'move',.2,photos,png,prefix);assert.ok(Math.abs(photos[0].labels[0].start-.4)<1e-9);
});
test('封面未同步字色在旧回覆與重建後保留，確認成功的整批設定可繼續改字',()=>{
  const d=new DraftState(),rows=[{id:'p',labels:[],duration:2}],c=cover();d.receive(rows,'s',1,null,[],[],[],c);
  d.cover.title='新標題';d.touch(rows);const sent=d.snapshot('one');d.cover.color='#ffff00';d.touch(rows);
  d.receive(rows,'s',2,{nonce:'one',ok:true},[],[],[],sent.cover);assert.equal(d.cover.color,'#ffff00');
  const restored=new DraftState();assert.ok(restored.restore(d.persisted(),'s'));assert.equal(restored.cover.title,'新標題');assert.equal(restored.cover.color,'#ffff00');
});
