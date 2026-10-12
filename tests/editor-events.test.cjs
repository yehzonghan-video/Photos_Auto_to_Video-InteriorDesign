// 執行真正 editor.js 的事件處理器；這是合成 DOM 測試，不宣稱實體滑鼠效能。
const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const {DraftState}=require('../frontend/draft-state.js');
const StudioLabel=require('../frontend/label-raster.js');
const StudioPhoto=require('../frontend/photo-layout.js');
const StudioAnimation=require('../frontend/animation.js');
const StudioAI=require('../frontend/ai-import.js');
function environment(storage=new Map()) {
  const elements=new Map(),messages=[],listeners={},frames=new Map();let serial=0,draws=0;
  function element(tag='div') {
    const handlers={},ctx={font:'46px sans-serif',measureText:text=>({width:text.length*46}),
      roundRect(){},beginPath(){},fill(){},fillText(){},fillRect(){},moveTo(){},lineTo(){},stroke(){},
      arc(){},save(){},restore(){},strokeRect(){},setLineDash(){},drawImage(){draws++;}};
    return {tagName:tag,children:[],value:'',checked:true,disabled:false,hidden:false,width:1080,height:1920,
      classList:{toggle(){},add(){},remove(){}},dataset:{},
      getContext:()=>ctx,getBoundingClientRect:()=>({left:0,top:0,width:1080,height:1920}),
      replaceChildren(){this.children=[];},append(...children){this.children.push(...children);},
      addEventListener(name,fn){handlers[name]=fn;},removeAttribute(){},setPointerCapture(){},
      dispatch(name,data={}){handlers[name]?.({preventDefault(){},pointerId:1,...data});}};
  }
  const document={activeElement:null,hidden:false,getElementById(id){if(!elements.has(id))elements.set(id,element(id==='canvas'?'canvas':'div'));return elements.get(id);},
    createElement:element,querySelector:()=>element(),querySelectorAll:()=>[...elements.values()],addEventListener(){},removeEventListener(){}};
  class FakeImage {constructor(){this.naturalWidth=220;this.naturalHeight=110;} set src(value){this._src=value;Promise.resolve().then(()=>this.onload?.());}get src(){return this._src;}}
  const window={parent:{postMessage(msg){messages.push(JSON.parse(JSON.stringify(msg)));}},addEventListener(name,fn){listeners[name]=fn;}};
  const context=vm.createContext({document,window,Image:FakeImage,ResizeObserver:class{observe(){}},
    StudioDraft:{DraftState},StudioLabel,StudioPhoto,StudioAnimation,StudioAI,crypto:webcrypto,console,
    requestAnimationFrame(fn){const id=++serial;frames.set(id,fn);return id;},cancelAnimationFrame(id){frames.delete(id);},
    setTimeout(){return ++serial;},clearTimeout(){},performance:{now:()=>0},URL:{revokeObjectURL(){}},
    sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}});
  vm.runInContext(fs.readFileSync('frontend/editor.js','utf8'),context);
  const rows=()=>[{id:'p1',content_hash:'hash',name:'first',image:'image1',tiles:{},labels:[],duration:4,zoom:1,crop_x:.5,crop_y:.5,fit:'contain'},
    {id:'p2',name:'second',image:'image2',tiles:{},labels:[],duration:4,zoom:1,crop_x:.5,crop_y:.5,fit:'contain'}];
  async function receive(extra={}){await listeners.message({source:window.parent,data:{type:'streamlit:render',args:{project:{photos:rows()},session:'session',revision:1,busy:false,...extra}}});}
  const changes=()=>messages.filter(m=>m.type==='streamlit:setComponentValue');
  return {elements,changes,receive,rows,context,storage,frames,get draws(){return draws;}};
}
test('真正事件處理器：連續新增10個、500次移動、修改、刪除與切換照片均不送 Python',async()=>{
  const env=environment();await env.receive();const get=id=>env.elements.get(id);
  for(let i=0;i<10;i++)get('addLabel').onclick();
  assert.equal(get('labels').children.length,10);assert.equal(env.changes().length,0);
  assert.ok(vm.runInContext('tileFor(label()).width',env.context)>100);
  for(let index=0;index<5;index++) {
    get('labels').children[index].onclick();
    const start=vm.runInContext('({x:bounds(label()).x+30,y:bounds(label()).y+30})',env.context);
    get('canvas').dispatch('pointerdown',{clientX:start.x,clientY:start.y});
    for(let i=0;i<100;i++)get('canvas').dispatch('pointermove',{clientX:start.x+i,clientY:start.y+i});
    get('canvas').dispatch('pointerup');
  }
  assert.equal(env.changes().length,0);assert.equal(env.frames.size,1,'多次拖曳共用下一個繪製影格');
  get('text').value='最新標籤';get('text').oninput();get('font_size').value='72';get('font_size').oninput();
  get('background').value='#123456';get('background').oninput();get('opacity').value='.4';get('opacity').oninput();
  get('animation').value='scale';get('animation').onchange();
  get('deleteLabel').onclick();assert.equal(get('labels').children.length,9);
  get('photos').children[1].onclick();get('addLabel').onclick();get('photos').children[0].onclick();
  assert.equal(get('labels').children.length,9);assert.equal(env.changes().length,0);
  const rebuilt=environment(env.storage);await rebuilt.receive();assert.equal(rebuilt.elements.get('labels').children.length,9);
  const promise=rebuilt.elements.get('applyChanges').onclick();
  assert.equal(rebuilt.changes().length,1);
  const sent=rebuilt.changes()[0].value;assert.equal(sent.photos[1].labels.length,1);
  const rows=rebuilt.rows();rows.forEach((row,i)=>row.labels=sent.photos[i].labels);
  await rebuilt.receive({project:{photos:rows},revision:2,response:{nonce:sent.nonce,ok:true}});await promise;
  assert.equal(rebuilt.elements.get('labels').children.length,9);assert.equal(rebuilt.changes().length,1);
});
test('AI 整批匯入保留未同步人工標籤，rerun 與元件重建不重複，輸出帶最新AI標籤',async()=>{
  const env=environment();await env.receive();env.elements.get('addLabel').onclick();
  env.elements.get('text').value='人工草稿';env.elements.get('text').oninput();
  const batch={id:'batch',photo_id:'p1',content_hash:'hash',items:[{label:'木紋地板',description:'可見木紋',category:'地板',box_2d:[.5,0,1,1],anchor_x:.5,anchor_y:.75,suggested_label_x:.1,suggested_label_y:.6,confidence_level:'中',needs_review:true,ai_item_id:'item'}]};
  await env.receive({ai_imports:[batch]});
  assert.equal(env.elements.get('labels').children.length,2);assert.equal(env.changes().length,0);
  assert.equal(vm.runInContext('photos[0].labels[0].text',env.context),'人工草稿');
  await env.receive({ai_imports:[batch]});assert.equal(env.elements.get('labels').children.length,2);
  env.elements.get('photos').children[1].onclick();env.elements.get('photos').children[0].onclick();
  assert.equal(env.elements.get('labels').children.length,2);
  const rebuilt=environment(env.storage);await rebuilt.receive({ai_imports:[batch]});
  assert.equal(rebuilt.elements.get('labels').children.length,2);assert.equal(rebuilt.changes().length,0);
  await rebuilt.receive({ai_imports:[batch],export_request:'export-ai'});
  const event=rebuilt.changes()[0].value;
  assert.equal(event.photos[0].labels[1].text,'木紋地板');assert.deepEqual(event.imported_batches,['batch']);
});
test('輸出請求先傳送最新完整草稿，完成後解除鎖定',async()=>{
  const env=environment();await env.receive();env.elements.get('addLabel').onclick();
  env.elements.get('text').value='輸出用的新文字';env.elements.get('text').oninput();
  await env.receive({export_request:'request'});
  assert.equal(env.changes().length,1);const sent=env.changes()[0].value;
  assert.equal(sent.action,'export');assert.equal(sent.photos[0].labels[0].text,'輸出用的新文字');
  assert.equal(env.elements.get('addLabel').disabled,true);
  const rows=env.rows();rows[0].labels=sent.photos[0].labels;
  await env.receive({project:{photos:rows},revision:2,response:{nonce:sent.nonce,ok:true},busy:true});
  await env.receive({project:{photos:rows},revision:2,response:{nonce:sent.nonce,ok:true},busy:false});
  assert.equal(env.elements.get('addLabel').disabled,false);assert.equal(env.changes().length,1);
  env.elements.get('text').value='';env.elements.get('text').oninput();
  await env.receive({project:{photos:rows},revision:2,export_request:'invalid-request'});
  await Promise.resolve();await Promise.resolve();
  assert.equal(env.changes().length,2);
  assert.equal(env.changes()[1].value.action,'cancel_export','無效設定要取消等待，不讓後端輸出按鈕卡住');
  assert.equal(env.elements.get('text').value,'','無效草稿保留供使用者修正');
});
