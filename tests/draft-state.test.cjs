const assert=require('node:assert/strict');
const test=require('node:test');
const {DraftState}=require('../frontend/draft-state.js');
const remote=()=>[{id:'p1',name:'first',image:'image1',tiles:{},labels:[],duration:4},{id:'p2',name:'second',image:'image2',tiles:{},labels:[],duration:4}];
function initialized(){const state=new DraftState();state.receive(remote(),'session',1);return state;}
test('PNG 草稿跨重建保存，同步期間的新旋轉不被舊回覆覆蓋',()=>{
  const state=initialized();state.overlays=[{id:'png',source:'asset',rotation:0,start:1,duration:3}];state.touch(state.rows);
  const snapshot=state.snapshot('png-nonce');state.overlays[0].rotation=45;state.touch(state.rows);
  state.receive(remote(),'session',2,{nonce:'png-nonce',ok:true},snapshot.overlays);
  assert.equal(state.overlays[0].rotation,45);assert.equal(state.dirty,true);
  const restored=new DraftState();restored.restore(state.persisted(),'session');restored.receive(remote(),'session',2,null,[]);
  assert.equal(restored.overlays[0].rotation,45);
  assert.equal(JSON.stringify(restored.persisted()).includes('image1'),false);
});
test('十個標籤、跨照片切換及元件重建保留草稿；草稿不含照片內容',()=>{
  const state=initialized();for(let i=0;i<10;i++){state.rows[0].labels.push({id:`l${i}`,text:`標籤${i}`,x:i/20});state.touch(state.rows);}
  state.rows[1].labels.push({id:'second',text:'另一張'});state.touch(state.rows);
  const saved=JSON.parse(JSON.stringify(state.persisted({selectedPhoto:'p2'})));
  assert.equal(saved.rows[0].image,undefined);
  const restored=new DraftState();assert.equal(restored.restore(saved,'session'),true);
  restored.receive(remote(),'session',1);
  assert.equal(restored.rows[0].labels.length,10);assert.equal(restored.rows[1].labels[0].text,'另一張');
  assert.equal(restored.rows[0].image,'image1');assert.equal(restored.dirty,true);
});
test('同步回覆不覆蓋提交後的新文字、位置、刪除與樣式',()=>{
  const state=initialized();state.rows[0].labels=[{id:'l1',text:'old',x:.1,color:'#ffffff'},{id:'l2',text:'delete'}];state.touch(state.rows);
  const sent=state.snapshot('nonce');
  state.rows[0].labels[0]={id:'l1',text:'latest',x:.8,color:'#00ff00'};state.rows[0].labels.pop();state.touch(state.rows);
  const rows=remote();rows[0].labels=sent.photos[0].labels;
  state.receive(rows,'session',2,{nonce:'nonce',ok:true});
  assert.equal(state.rows[0].labels.length,1);assert.equal(state.rows[0].labels[0].text,'latest');assert.equal(state.dirty,true);
  assert.equal(state.rows[0].labels[0].x,.8);assert.equal(state.rows[0].labels[0].color,'#00ff00');
});
test('相同批次的成功回覆整批替換，不重複附加；較舊 revision 不覆蓋',()=>{
  const state=initialized();state.rows[0].labels=[{id:'label',text:'唯一'}];state.touch(state.rows);
  const sent=state.snapshot('nonce');const rows=remote();rows[0].labels=sent.photos[0].labels;
  state.receive(rows,'session',2,{nonce:'nonce',ok:true});state.receive(rows,'session',2,{nonce:'nonce',ok:true});
  assert.equal(state.rows[0].labels.length,1);assert.equal(state.dirty,false);
  assert.equal(state.receive(remote(),'session',1).stale,true);assert.equal(state.rows[0].labels.length,1);
});
test('上傳、替換與刪除照片時保留其他照片草稿和排序',()=>{
  const state=initialized();state.rows.reverse();state.rows[1].labels=[{id:'l',text:'保留'}];state.touch(state.rows);
  const rows=remote();rows[0].image='replacement';rows.push({id:'p3',image:'new',tiles:{},labels:[]});
  state.receive(rows,'session',2);
  assert.deepEqual(state.rows.map(p=>p.id),['p2','p1','p3']);assert.equal(state.rows[1].labels[0].text,'保留');assert.equal(state.rows[1].image,'replacement');
  state.deleted=['p2'];state.rows=state.rows.filter(p=>p.id!=='p2');state.touch(state.rows);state.receive(rows,'session',3);
  assert.deepEqual(state.rows.map(p=>p.id),['p1','p3']);
});
test('失敗回覆保留草稿，新工作階段不載入舊草稿',()=>{
  const state=initialized();state.rows[0].labels=[{id:'l',text:'pending'}];state.touch(state.rows);state.snapshot('n');
  const result=state.receive(remote(),'session',2,{nonce:'n',ok:false,message:'conflict'});
  assert.equal(result.error,'conflict');assert.equal(state.rows[0].labels[0].text,'pending');assert.equal(state.pending,null);
  const saved=state.persisted();const fresh=new DraftState();assert.equal(fresh.restore(saved,'different-session'),false);
  state.receive(remote(),'different-session',0);assert.equal(state.rows[0].labels.length,0);
});

test('對比片段與各模板PNG在同步等待中新編輯不被舊回覆覆蓋，重建草稿不含素材內容',()=>{
  const state=new DraftState(),photos=[{id:'b',image:'photo-bytes',tiles:{},labels:[],duration:4,role:'before'},{id:'a',image:'photo-bytes',tiles:{},labels:[],duration:4,role:'after'}];
  const clip={id:'c',type:'comparison',before_id:'b',after_id:'a',duration:5,name:'原名稱',labels:[],tiles:{},image:'do-not-store'};
  state.receive(photos,'s',1,null,[],[clip],[]);state.template='compare';state.touch(photos);const old=state.snapshot('pending');
  state.comparisons[0].name='使用者新名稱';state.comparisonOverlays.push({id:'png',start:2,duration:2});state.touch(photos);
  state.receive(photos,'s',2,{nonce:'pending',ok:true},[],old.comparisons,old.comparison_overlays);
  assert.equal(state.comparisons[0].name,'使用者新名稱');assert.equal(state.comparisonOverlays.length,1);assert.equal(state.pending,null);
  const saved=state.persisted();assert.equal(saved.comparisons[0].image,undefined);assert.equal(saved.rows[0].image,undefined);
  const restored=new DraftState();assert.equal(restored.restore(saved,'s'),true);assert.equal(restored.comparisons[0].name,'使用者新名稱');assert.equal(restored.comparisonOverlays.length,1);
});
