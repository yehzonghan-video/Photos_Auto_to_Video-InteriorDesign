const test=require('node:test'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const C=require('../frontend/comparison-model.js'),T=require('../frontend/timeline-model.js');
let serial=0;const id=()=>String(++serial),photos=[{id:'b',role:'before',labels:[],duration:4},{id:'a',role:'after',labels:[],duration:4}];
test('前後自動配對保留未配對來源，手動可重複使用，重按不重複加入',()=>{
  const p=[...photos,{...photos[0],id:'b2'}],clips=[];const r=C.pair(p,clips,id);assert.equal(r.unmatched,1);assert.equal(clips.length,1);
  C.pair(p,clips,id);assert.equal(clips.length,1);clips.push(C.make(p[2],p[1],id));clips.push(C.make(p[0],p[1],id));assert.equal(C.validate(clips,p),null);assert.equal(p.length,3);
});
test('現有時間軸投影對比片段、標籤、跨片段PNG；重排與裁切同步後續開始',()=>{
  const clips=[C.make(...photos,id),C.make(...photos,id)],png=[{id:'png',type:'png',start:3,duration:4,enter:.3,exit:.3}];
  let items=T.items(clips,png);assert.equal(items[1].type,'label');assert.equal(items.find(i=>i.id===clips[1].id).start,5);
  T.edit(items[0],'right',-3,clips,png);assert.equal(clips[0].duration,2);assert.equal(T.items(clips).find(i=>i.id===clips[1].id).start,2);
  const first=clips[0].id;T.edit(T.items(clips)[0],'move',3,clips,png);assert.equal(clips[1].id,first);
  const labelItem=T.items(clips).find(i=>i.type==='label');T.edit(labelItem,'right',-.1,clips,png);assert.equal(clips[0].labels[0].auto_timing,false);
  assert.equal(C.validate(clips,photos),null);assert.equal(png[0].start,3);
});
test('對比逐幀姿態與Python一致，真正遮罩包括兩種揭露方向與滑動起訖',()=>{
  const rows=[];for(const mode of ['switch','split','reveal'])for(const direction of ['ltr','rtl'])for(const t of [0,1.9,2,2.1,2.5,2.9,3,5])rows.push({c:{...C.make(...photos,id),mode,direction,split:.37},t});
  const python=execFileSync('.venv/Scripts/python.exe',['-c','import json,sys;from studio.comparison import comparison_pose;r=json.load(sys.stdin);print(json.dumps([comparison_pose(x["c"],x["t"]) for x in r]))'],{input:JSON.stringify(rows),encoding:'utf8'});
  const expected=JSON.parse(python);rows.forEach((r,i)=>{const actual=C.pose(r.c,r.t);for(const key of Object.keys(actual))assert.ok(Math.abs(actual[key]-expected[i][key])<1e-8,`${i} ${key}`);});
});
test('施工後來源標籤換算獨立裁切／左右分割座標，裁切外標記人工確認',()=>{
  const c=C.make(...photos,id);c.mode='split';const image={naturalWidth:1080,naturalHeight:1920};
  const mapped=C.mapPoint(c,{fit:'contain',zoom:1,crop_x:.5,crop_y:.5},image,.5,.5);
  assert.equal(mapped.x,.75);assert.equal(mapped.y,.5);assert.equal(mapped.review,false);
  c.mode='switch';c.after_crop={fit:'cover',zoom:3,crop_x:1,crop_y:.5};
  assert.equal(C.mapPoint(c,{fit:'contain'},image,.1,.5).review,true);
});
