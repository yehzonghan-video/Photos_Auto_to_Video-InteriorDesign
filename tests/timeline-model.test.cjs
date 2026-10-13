const test=require('node:test'),assert=require('node:assert/strict');
const T=require('../frontend/timeline-model.js');
const photos=()=>[{id:'a',name:'A',duration:4,labels:[{id:'text',text:'標籤',start:1,end:4,enter:.6}]},{id:'b',name:'B',duration:4,labels:[]}];
test('3-1：照片與標籤共用全片投影，PNG 可跨照片並重疊',()=>{
  const p=photos(),o=[{id:'png',type:'png',source:'asset',start:3,duration:3,layer:20}];
  const items=T.items(p,o);assert.equal(items[2].start,4);assert.equal(items[1].start,1);assert.equal(items[3].duration,3);
  assert.equal(T.lanes([...o,{...o[0],id:'second'}]).rows,2);
});
test('3-1：標籤拖曳／左右裁切在所屬照片內，PNG 跨越下一張',()=>{
  const p=photos(),o=[{id:'png',type:'png',source:'asset',start:3,duration:3,enter:.5,exit:.5}];
  T.edit(T.items(p,o).find(i=>i.id==='text'),'move',-10,p,o);assert.equal(p[0].labels[0].start,0);
  T.edit(T.items(p,o).find(i=>i.id==='png'),'right',1,p,o);assert.equal(o[0].duration,4);
  T.edit(T.items(p,o).find(i=>i.id==='png'),'left',1,p,o);assert.equal(o[0].start,4);assert.equal(o[0].duration,3);
});
test('3-1：照片縮短截標籤、PNG 絕對時間不隨照片排序移動',()=>{
  const p=photos(),o=[{start:5,duration:3,enter:.5,exit:.5}];
  T.photoDuration(p[0],2);T.clampOverlays(o,T.total(p));assert.equal(p[0].labels[0].end,2);assert.equal(o[0].start,5);assert.equal(o[0].duration,1);
  T.edit(T.items(p).find(i=>i.id==='a'),'move',3,p,o);assert.equal(p[0].id,'b');assert.equal(o[0].start,5);
});
