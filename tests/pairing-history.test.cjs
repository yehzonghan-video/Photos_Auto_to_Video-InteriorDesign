const test=require('node:test'),assert=require('node:assert/strict');
const P=require('../frontend/pairing.js'),H=require('../frontend/photo-history.js'),C=require('../frontend/comparison-model.js');
const p=(id,role,name='照片',description='客廳有落地窗及橫梁')=>({id,role,name,image:`image-${id}`,duration:4,labels:[{id:`label-${id}`,source:'gemini',text:'裝修特色',description,category:'其他特色'}]});
test('既有AI說明及分類可建議同空間，多角度保留候選，不呼叫API也不動專案',()=>{
  const rows=[p('b','before'),p('a','after'),p('a2','after')],before=JSON.stringify(rows),clips=[];
  const r=P.suggest(rows,clips);assert.equal(r.length,2);assert.ok(r.every(x=>x.confidence==='低'));assert.ok(r[0].reason.includes('落地窗'));
  assert.equal(JSON.stringify(rows),before);assert.deepEqual(clips,[]);
});
test('不同空間、缺資料、只有相同泛用裝修、不明前後均不強制配對',()=>{
  assert.equal(P.suggest([p('b','before'),p('a','after','照片','浴室有落地窗')],[]).length,0);
  assert.equal(P.suggest([p('b','before','照片','木紋地板'),p('a','after','照片','木紋地板')],[]).length,0);
  assert.equal(P.suggest([p('b','general'),p('a','general')],[]).length,0);
});
test('明確檔名前後／案例識別可輔助，信心最高中；既有配對只報衝突不覆蓋',()=>{
  const rows=[p('b','general','客廳01_before.png'),p('a','general','客廳01_after.png'),p('c','after')];
  const clips=[{before_id:'b',after_id:'c',duration:7}],old=JSON.stringify(clips);
  const r=P.suggest(rows,clips);assert.equal(r.length,1);assert.equal(r[0].confidence,'中');assert.equal(r[0].conflict,true);
  assert.equal(JSON.stringify(clips),old);
});
test('建議上限12，不看相鄰順序；分類含混空間不提高信心',()=>{
  const rows=Array.from({length:12},(_,i)=>p(String(i),i%2?'after':'before'));
  assert.equal(P.suggest(rows,[]).length,12);assert.deepEqual(P.suggest(rows,[]).map(x=>x.id),P.suggest(rows.slice().reverse(),[]).map(x=>x.id));
  assert.equal(P.evidence(p('x','before','圖','客廳與廚房')).room,null);
});
function draft(){const rows=[p('b','before'),p('a','after')];let n=0;return {rows,comparisons:[C.make(...rows,()=>String(++n))],cover:{photo_id:'b'},overlays:[],comparisonOverlays:[],deleted:[]};}
test('單次完整復原照片、原順序、片段、裁切、文字、封面與PNG時間；不保存圖片歷史',()=>{
  const d=draft(),h=new H.History(),old=H.state(d),media=d.rows.slice();d.overlays=[{start:3,duration:4}];
  assert.deepEqual(H.impact(d,'b'),{clips:1,tour_clips:0,cover:true,labels:1});h.begin(d,'b');
  const before=H.state(d);d.rows.splice(0,1);d.comparisons=[];d.cover.photo_id='a';d.overlays[0].duration=1;d.deleted.push('b');h.finish(d);
  const persisted=JSON.stringify(h.persisted());assert.ok(!persisted.includes('image-b'));
  const rebuilt=new H.History();rebuilt.load(JSON.parse(persisted));rebuilt.restore(d,media);
  assert.deepEqual(H.state(d),before);assert.equal(rebuilt.restored,'b');assert.equal(rebuilt.entry,null);
  assert.throws(()=>rebuilt.restore(d,media),/沒有可復原/);
});
test('後續內容修改、失效媒體、滿12張時拒絕復原，資料完全保留',()=>{
  for(const mode of ['changed','missing','limit']){const d=draft(),h=new H.History();h.begin(d,'b');d.rows.shift();d.comparisons=[];h.finish(d);
    h.preview=null;if(mode==='changed')d.cover.photo_id='changed';if(mode==='limit')while(d.rows.length<12)d.rows.push(p(String(d.rows.length),'general'));
    const before=JSON.stringify(d);assert.throws(()=>h.restore(d,[]));assert.equal(JSON.stringify(d),before);assert.ok(h.entry);
  }
});
test('交換來源分類不影響合法引用，缺來源／同張配對仍拒絕',()=>{
  const d=draft(),c=d.comparisons[0];[c.before_id,c.after_id]=[c.after_id,c.before_id];assert.equal(C.validate([c],d.rows),null);
  d.rows[0].role='general';assert.equal(C.validate([c],d.rows),null);c.after_id=c.before_id;assert.ok(C.validate([c],d.rows));
});
