const test=require('node:test');
const assert=require('node:assert/strict');
const AI=require('../frontend/ai-import.js');
const {layout}=require('../frontend/photo-layout.js');
const {DraftState}=require('../frontend/draft-state.js');
const item={label:'地板',description:'可見外觀',category:'地板',box_2d:[.5,0,1,1],anchor_x:.5,anchor_y:.75,suggested_label_x:.1,suggested_label_y:.6,confidence_level:'高',needs_review:false,ai_item_id:'item'};
const photo=()=>({id:'p',name:'測試',content_hash:'hash',fit:'contain',duration:4,zoom:1,crop_x:.5,crop_y:.5,labels:[]});
test('橫圖完整留黑換算物件與文字座標',()=>{
  const l=AI.convert(item,photo(),{naturalWidth:2000,naturalHeight:1000},layout,()=> 'id');
  assert.equal(l.point_x,.5);assert.equal(l.point_y,(690+405)/1920);
  assert.equal(l.x,.1);assert.equal(l.y,(690+324)/1920);
});
test('自動套用在剩餘容量內加入，保留全部人工標籤，超出數量明確顯示',()=>{
  const draft=new DraftState();draft.rows=[photo()];
  draft.rows[0].labels=Array.from({length:10},(_,i)=>({id:`manual-${i}`,text:`人工 ${i}`}));
  const images=new Map([['p',{naturalWidth:2000,naturalHeight:1000}]]);
  const batch={id:'auto',photo_id:'p',content_hash:'hash',automatic:true,
    items:Array.from({length:4},(_,i)=>({...item,ai_item_id:`auto-${i}`}))};let i=0;
  const result=AI.importBatches(draft,[batch],images,layout,()=> `id-${i++}`);
  assert.equal(result.added,2);assert.equal(draft.rows[0].labels.length,12);
  assert.equal(draft.rows[0].labels[0].text,'人工 0');assert.match(result.messages[0],/2 個因12個標籤上限/);
  assert.equal(AI.importBatches(draft,[batch],images,layout,()=> 'id').added,0);
});
test('使用最新裁切縮放，裁切外略過、部分可見修正定位點並待確認',()=>{
  const p={...photo(),fit:'cover',zoom:2,crop_x:1,crop_y:.5};
  const hidden={...item,box_2d:[0,0,.1,.1],anchor_x:.05,anchor_y:.05};
  assert.equal(AI.convert(hidden,p,{naturalWidth:2000,naturalHeight:1000},layout,()=> 'id'),null);
  const visible=AI.convert(item,p,{naturalWidth:2000,naturalHeight:1000},layout,()=> 'id');
  assert.ok(visible.needs_review);assert.ok(visible.point_x>=0&&visible.point_x<=1);
});
test('批次去重、容量限制及照片替換保護',()=>{
  const draft=new DraftState();draft.rows=[photo()];
  const images=new Map([['p',{naturalWidth:2000,naturalHeight:1000}]]);
  const batch={id:'b',photo_id:'p',content_hash:'hash',items:[item]};
  assert.equal(AI.importBatches(draft,[batch],images,layout,()=> 'id').added,1);
  assert.equal(AI.importBatches(draft,[batch,{...batch,id:'b2'}],images,layout,()=> 'id').added,0);
  draft.rows[0].labels=Array.from({length:12},()=>({id:'manual'}));
  assert.equal(AI.importBatches(draft,[{...batch,id:'b3'}],images,layout,()=> 'id').added,0);
  assert.equal(draft.rows[0].labels.length,12);
  assert.equal(AI.importBatches(draft,[{...batch,id:'b4',content_hash:'replaced'}],images,layout,()=> 'id').added,0);
});
