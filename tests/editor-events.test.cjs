// 執行真正 editor.js 的事件處理器；這是合成 DOM 測試，不宣稱實體滑鼠效能。
const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const {DraftState,metadata}=require('../frontend/draft-state.js');
const StudioLabel=require('../frontend/label-raster.js');
const StudioPhoto=require('../frontend/photo-layout.js');
const StudioAnimation=require('../frontend/animation.js');
const StudioAI=require('../frontend/ai-import.js');
const StudioTimeline=require('../frontend/timeline-model.js');
const StudioOverlay=require('../frontend/overlay-model.js');
const StudioComparison=require('../frontend/comparison-model.js');
const StudioSafeArea=require('../frontend/safe-area.js');
const StudioMusic=require('../frontend/music.js');
function environment(storage=new Map()) {
  const elements=new Map(),messages=[],listeners={},frames=new Map();let serial=0,draws=0;
  function element(tag='div') {
    const handlers={},ctx={font:'46px sans-serif',measureText:text=>({width:text.length*46}),
      roundRect(){},beginPath(){},fill(){},fillText(){},strokeText(){},fillRect(){},moveTo(){},lineTo(){},stroke(){},
      arc(){},rect(){},clip(){},save(){},restore(){},translate(){},rotate(){},strokeRect(){},setLineDash(){},drawImage(){draws++;}};
    return {tagName:tag,children:[],value:'',checked:true,disabled:false,hidden:false,width:1080,height:1920,
      classList:{toggle(){},add(){},remove(){}},dataset:{},style:{},
      getContext:()=>ctx,getBoundingClientRect:()=>({left:0,top:0,width:1080,height:1920}),
      querySelector:()=>null,
      replaceChildren(){this.children=[];},append(...children){this.children.push(...children);},
      addEventListener(name,fn){handlers[name]=fn;},removeAttribute(){},setPointerCapture(){},
      dispatch(name,data={}){handlers[name]?.({preventDefault(){},pointerId:1,...data});}};
  }
  const document={activeElement:null,hidden:false,getElementById(id){if(!elements.has(id))elements.set(id,element(id==='canvas'?'canvas':'div'));return elements.get(id);},
    createElement:element,querySelector:()=>element(),querySelectorAll:()=>[...elements.values()],addEventListener(){},removeEventListener(){}};
  class FakeImage {constructor(){this.naturalWidth=220;this.naturalHeight=110;} set src(value){this._src=value;Promise.resolve().then(()=>this.onload?.());}get src(){return this._src;}}
  const window={parent:{postMessage(msg){messages.push(JSON.parse(JSON.stringify(msg)));}},addEventListener(name,fn){listeners[name]=fn;}};
  const context=vm.createContext({document,window,Image:FakeImage,ResizeObserver:class{observe(){}},
    StudioDraft:{DraftState,metadata},StudioLabel,StudioPhoto,StudioAnimation,StudioAI,StudioTimeline,StudioOverlay,StudioComparison,StudioSafeArea,StudioMusic,crypto:webcrypto,console,
    requestAnimationFrame(fn){const id=++serial;frames.set(id,fn);return id;},cancelAnimationFrame(id){frames.delete(id);},
    setTimeout(){return ++serial;},clearTimeout(){},performance:{now:()=>0},URL:{revokeObjectURL(){}},
    sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}});
  vm.runInContext(fs.readFileSync('frontend/timeline-ui.js','utf8'),context);
  vm.runInContext(fs.readFileSync('frontend/png-editor.js','utf8'),context);
  vm.runInContext(fs.readFileSync('frontend/comparison-editor.js','utf8'),context);
  vm.runInContext(fs.readFileSync('frontend/cover-editor.js','utf8'),context);
  context.StudioCover=window.StudioCover;
  vm.runInContext(fs.readFileSync('frontend/body-editor.js','utf8'),context);
  context.StudioBody=window.StudioBody;
  context.StudioBody.configure(JSON.parse(fs.readFileSync('frontend/body-layout.json','utf8')));
  context.StudioTimelineUI=window.StudioTimelineUI;context.StudioPNG=window.StudioPNG;context.StudioComparisonUI=window.StudioComparisonUI;
  vm.runInContext(fs.readFileSync('frontend/editor.js','utf8'),context);
  const rows=()=>[{id:'p1',content_hash:'hash',name:'first',image:'image1',tiles:{},labels:[],duration:4,zoom:1,crop_x:.5,crop_y:.5,fit:'contain'},
    {id:'p2',name:'second',image:'image2',tiles:{},labels:[],duration:4,zoom:1,crop_x:.5,crop_y:.5,fit:'contain'}];
  async function receive(extra={}){await listeners.message({source:window.parent,data:{type:'streamlit:render',args:{project:{photos:rows()},session:'session',revision:1,busy:false,...extra}}});}
  const changes=()=>messages.filter(m=>m.type==='streamlit:setComponentValue');
  return {elements,changes,receive,rows,context,storage,frames,get draws(){return draws;}};
}
test('BGM音量與淡出連續修改不送Python，rerun／重建保留，輸出批次使用最新音樂設定',async()=>{
  const env=environment(),m={...StudioMusic.newMusic(),source:'audio'},project={photos:env.rows(),music:m,music_asset:{id:'audio',name:'tone.wav',duration:2,src:'data:audio/wav;base64,mock'}};
  await env.receive({project});const get=id=>env.elements.get(id);
  assert.equal(get('musicFade').value,1);
  for(let i=0;i<100;i++){get('musicVolume').value='30';get('musicVolume').oninput();get('musicFade').value='2';get('musicFade').oninput();}
  assert.equal(env.changes().length,0);assert.equal(vm.runInContext('draft.music.volume',env.context),.3);
  await env.receive({project,revision:2});assert.equal(vm.runInContext('draft.music.fade_out',env.context),2);
  const rebuilt=environment(env.storage);await rebuilt.receive({project,revision:2});assert.equal(vm.runInContext('draft.music.fade_out',rebuilt.context),2);
  await rebuilt.receive({project,revision:2,export_request:'r'});const sent=rebuilt.changes()[0].value;
  assert.equal(sent.music.volume,.3);assert.equal(sent.music.fade_out,2);assert.equal(sent.music.source,'audio');
});

test('正文跟隨封面文字／字色、100次独立修改均本地，rerun／重建保留並批次輸出',async()=>{
  const env=environment(),get=id=>env.elements.get(id);
  const cover={enabled:true,title:'老屋88萬',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  const project={photos:env.rows(),cover,cover_assets:{layout:JSON.parse(fs.readFileSync('frontend/cover-layout.json'))}};
  await env.receive({project});assert.equal(get('bodyFollow').checked,true);
  get('coverTitle').value='翻新88萬';get('coverTitle').oninput();get('coverTitle').selectionStart=2;get('coverTitle').selectionEnd=4;get('coverTitle').onselect();
  env.context.document.getElementById('coverSelectedColor').value='#ff0000';get('coverApplyColor').onclick();
  assert.equal(get('bodyTitle').value,'翻新88萬');assert.equal(get('bodyColorPreview').children[2].style.color,'#ff0000');
  get('bodyFollow').checked=false;get('bodyFollow').onchange();assert.equal(get('bodyTitle').disabled,false);
  for(let i=0;i<100;i++){get('bodyTitle').value='正文獨立88萬';get('bodyTitle').oninput();get('bodySize').value='100';get('bodySize').oninput();}
  get('bodyTitle').selectionStart=4;get('bodyTitle').selectionEnd=6;get('bodyTitle').onselect();env.context.document.getElementById('bodySelectedColor').value='#ffff00';get('bodyApplyColor').onclick();
  get('coverTitle').value='封面再修改';get('coverTitle').oninput();assert.equal(get('bodyTitle').value,'正文獨立88萬');assert.equal(env.changes().length,0);
  await env.receive({project,revision:2});const rebuilt=environment(env.storage);await rebuilt.receive({project,revision:2});
  assert.equal(rebuilt.elements.get('bodyTitle').value,'正文獨立88萬');assert.equal(rebuilt.elements.get('bodyFollow').checked,false);
  await rebuilt.receive({project,revision:2,export_request:'body-export'});const sent=rebuilt.changes()[0].value;
  assert.equal(sent.cover.body.title,'正文獨立88萬');assert.equal(sent.cover.body.highlights[0].color,'#ffff00');assert.equal(sent.cover.body.font_size,100);
});

test('連動正文可反白换色，色盤失焦不丟選取，封面同步且不送Python',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id);
  const cover={enabled:true,title:'翻新88萬',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  const project={photos:env.rows(),cover,cover_assets:{layout:JSON.parse(fs.readFileSync('frontend/cover-layout.json'))}};
  await env.receive({project});assert.equal(get('bodyTitle').disabled,false);assert.equal(get('bodyTitle').readOnly,true);
  assert.equal(get('bodyApplyColor').disabled,false);
  get('bodyTitle').selectionStart=2;get('bodyTitle').selectionEnd=4;get('bodyTitle').onpointerup();
  get('bodyTitle').selectionStart=get('bodyTitle').selectionEnd=0;get('bodyTitle').onblur();get('bodyTitle').onselect();
  get('bodySelectedColor').value='#ff0000';get('bodyApplyColor').onclick();
  assert.equal(get('bodyColorPreview').children[2].style.color,'#ff0000');assert.equal(get('coverColorPreview').children[2].style.color,'#ff0000');
  assert.equal(env.changes().length,0);
  const rebuilt=environment(env.storage);await rebuilt.receive({project,revision:2});
  assert.equal(rebuilt.elements.get('bodyColorPreview').children[2].style.color,'#ff0000');
  await rebuilt.receive({project,revision:2,export_request:'color-export'});const sent=rebuilt.changes()[0].value;
  assert.deepEqual(sent.cover.highlights,[{start:2,end:4,color:'#ff0000'}]);assert.equal(sent.cover.body.follow_cover,true);
});

test('封面選字在色盤失焦後仍能套用，未重新選字的改標題不能誤用舊範圍',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id);
  const cover={enabled:true,title:'翻新88萬',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  const project={photos:env.rows(),cover,cover_assets:{layout:JSON.parse(fs.readFileSync('frontend/cover-layout.json'))}};
  await env.receive({project});get('coverTitle').selectionStart=2;get('coverTitle').selectionEnd=4;get('coverTitle').onkeyup();
  get('coverTitle').selectionStart=get('coverTitle').selectionEnd=0;get('coverTitle').onblur();get('coverTitle').onselect();
  get('coverSelectedColor').value='#00ff00';get('coverApplyColor').onclick();assert.equal(get('coverColorPreview').children[2].style.color,'#00ff00');
  get('coverTitle').value='改完文字';get('coverTitle').oninput();get('coverApplyColor').onclick();
  assert.equal(vm.runInContext('draft.cover.highlights.length',env.context),0);assert.equal(env.changes().length,0);
});

test('封面照片、反白局部字色、0.3秒時間軸與開關偏移全部本地；同步包含最新封面',async()=>{
  const env=environment(),rows=env.rows(),layout=JSON.parse(fs.readFileSync('frontend/cover-layout.json'));
  const cover={enabled:true,title:'老屋88萬',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  const o={id:'o',type:'png',source:'a',start:1,duration:2,x:.5,y:.5,width:.2,scale:1,rotation:0,opacity:1,layer:20,animation:'none',exit_animation:'none',enter:0,exit:0};
  const project={photos:rows,cover,cover_assets:{layout},assets:[{id:'a',image:'png',width:100,height:100}],overlays:[o]};
  await env.receive({project});const get=id=>env.elements.get(id);
  assert.equal(vm.runInContext('total()',env.context),8.3);assert.equal(get('photos').children.length,3);
  get('coverTitle').value='翻新88萬';get('coverTitle').oninput();
  get('coverTitle').selectionStart=2;get('coverTitle').selectionEnd=4;get('coverTitle').onselect();env.context.document.getElementById('coverSelectedColor').value='#ff0000';get('coverApplyColor').onclick();
  get('coverPhoto').value='p2';get('coverPhoto').oninput();assert.equal(env.changes().length,0);
  get('seek').value='0';get('seek').oninput();
  assert.equal(get('safeAreaGuide').hidden,false,'封面動畫預覽顯示安全框');
  assert.ok(get('safeAreaGuide').innerHTML.includes('x="246"'));
  get('play').onclick();assert.equal(get('safeAreaGuide').hidden,false,'播放仍顯示安全框');
  get('seek').value='1';get('seek').oninput();
  assert.equal(get('safeAreaGuide').hidden,false,'正文預覽仍顯示安全框');
  assert.ok(!get('safeAreaGuide').innerHTML.includes('x="246"'),'依播放畫面切換正文安全區');
  vm.runInContext('recording=true;draw()',env.context);assert.equal(get('safeAreaGuide').hidden,true,'錄製隱藏提示');
  vm.runInContext('recording=false;draw()',env.context);assert.equal(get('safeAreaGuide').hidden,false);
  assert.equal(vm.runInContext('draft.cover.highlights[0].end',env.context),4);
  get('coverEnabled').checked=false;get('coverEnabled').onchange();assert.equal(vm.runInContext('draft.overlays[0].start',env.context),.7);
  get('coverEnabled').checked=true;get('coverEnabled').onchange();assert.equal(vm.runInContext('draft.overlays[0].start',env.context),1);
  await env.receive({project,revision:2});assert.equal(vm.runInContext('draft.cover.title',env.context),'翻新88萬');
  const promise=get('applyChanges').onclick(),event=env.changes()[0].value;
  assert.equal(event.cover.photo_id,'p2');assert.equal(event.cover.highlights[0].color,'#ff0000');
  await env.receive({project:{...project,cover:event.cover,overlays:event.overlays},revision:3,response:{nonce:event.nonce,ok:true}});await promise;
  assert.equal(env.changes().length,1);
});
test('舊0.5秒封面的未套用草稿保留文字與PNG，縮短時間只遷移一次且不送Python',async()=>{
  const env=environment(),layout=JSON.parse(fs.readFileSync('frontend/cover-layout.json'));
  const cover={enabled:true,title:'原標題',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  const png={id:'o',type:'png',source:'a',start:1,duration:2,x:.5,y:.5,width:.2,scale:1,rotation:0,opacity:1,layer:20,animation:'none',exit_animation:'none',enter:0,exit:0};
  const project={photos:env.rows(),cover,cover_assets:{layout},assets:[{id:'a',image:'png',width:100,height:100}],overlays:[png]};
  await env.receive({project});env.elements.get('coverTitle').value='未套用標題';env.elements.get('coverTitle').oninput();
  const saved=JSON.parse(env.storage.get('interior-studio-draft'));delete saved.coverSeconds;
  saved.selection.time=1;saved.selection.selectedPhoto='p1';env.storage.set('interior-studio-draft',JSON.stringify(saved));
  const rebuilt=environment(env.storage),remote={...project,overlays:[{...png,start:.8}]};
  await rebuilt.receive({project:remote,revision:2});
  assert.equal(vm.runInContext('draft.cover.title',rebuilt.context),'未套用標題');
  assert.equal(vm.runInContext('draft.overlays[0].start',rebuilt.context),.8);
  assert.equal(vm.runInContext('time',rebuilt.context),.8);
  await rebuilt.receive({project:remote,revision:2});
  assert.equal(vm.runInContext('draft.overlays[0].start',rebuilt.context),.8);
  assert.equal(rebuilt.changes().length,0);
});

test('安全框開關與預覽只處理DOM；標題可拖出內框、rerun和重建保留人工位置',async()=>{
  const env=environment(),rows=env.rows();rows[0].role='before';rows[1].role='after';
  const c=StudioComparison.make(...rows,webcrypto.randomUUID.bind(webcrypto));
  const project={photos:rows,comparisons:[c],template_id:'compare'},get=id=>env.elements.get(id);
  await env.receive({project});assert.equal(get('safeAreaGuide').hidden,false);
  assert.ok(get('safeAreaGuide').innerHTML.includes('viewBox="0 0 1080 1920"'));
  for(let i=0;i<100;i++){get('showSafeArea').checked=false;get('showSafeArea').onchange();get('showSafeArea').checked=true;get('showSafeArea').onchange();}
  assert.equal(vm.runInContext('draft.dirty',env.context),false,'構圖提示不改影片資料');
  get('showSafeArea').checked=false;get('showSafeArea').onchange();assert.equal(get('safeAreaGuide').hidden,true);
  const b=vm.runInContext('bounds(label())',env.context);
  get('canvas').dispatch('pointerdown',{clientX:b.x+30,clientY:b.y+30});
  get('canvas').dispatch('pointermove',{clientX:30,clientY:30});get('canvas').dispatch('pointerup');
  assert.equal(vm.runInContext('photo().labels[0].x',env.context),0);assert.equal(vm.runInContext('photo().labels[1].y',env.context),0);
  assert.equal(env.changes().length,0);await env.receive({project,revision:2});
  assert.equal(vm.runInContext('photo().labels[0].x',env.context),0);
  const rebuilt=environment(env.storage);await rebuilt.receive({project,revision:2});
  assert.equal(rebuilt.elements.get('showSafeArea').checked,false);assert.equal(vm.runInContext('photo().labels[0].x',rebuilt.context),0);
  get('showSafeArea').checked=true;get('showSafeArea').onchange();get('seek').value='0';get('seek').oninput();
  assert.equal(get('safeAreaGuide').hidden,false,'動畫預覽顯示安全框');
  get('showSafeArea').checked=false;get('showSafeArea').onchange();assert.equal(get('safeAreaGuide').hidden,true,'預覽可關閉提示');
  get('showSafeArea').checked=true;get('showSafeArea').onchange();get('edit').onclick();assert.equal(get('safeAreaGuide').hidden,false);
  assert.equal(env.changes().length,0);
});
test('前後標題拖曳共用位置、選取自動跳至對應時間、舊草稿升級且rerun不送Python',async()=>{
  const env=environment(),rows=env.rows();rows[0].role='before';rows[1].role='after';
  const c=StudioComparison.make(...rows,webcrypto.randomUUID.bind(webcrypto));
  c.labels[0].text='原始空間';c.labels[0].x=.2;
  for(const l of c.labels){delete l.comparison_title_version;l.opacity=.88;l.radius=18;}
  c.labels[1].x=.57;c.labels[0].end=3;
  const project={photos:rows,comparisons:[c],template_id:'compare'};await env.receive({project});
  const get=id=>env.elements.get(id),clip=()=>vm.runInContext('photo()',env.context);
  assert.equal(clip().labels[0].text,'原始空間');assert.equal(clip().labels[0].opacity,0);
  assert.equal(clip().labels[1].x,.2);assert.equal(clip().labels[0].end,2);
  get('labels').children[1].onclick();assert.equal(vm.runInContext('time',env.context),2);
  assert.equal(vm.runInContext('visibleEditLabel(photo(),photo().labels[0])',env.context),false);
  const b=vm.runInContext('bounds(label())',env.context);
  get('canvas').dispatch('pointerdown',{clientX:b.x+30,clientY:b.y+30});
  for(let i=0;i<300;i++)get('canvas').dispatch('pointermove',{clientX:b.x+30+i/10,clientY:b.y+50});
  get('canvas').dispatch('pointerup');
  assert.deepEqual([clip().labels[0].x,clip().labels[0].y],[clip().labels[1].x,clip().labels[1].y]);
  assert.ok(clip().labels[0].x>.2);assert.equal(env.changes().length,0);
  await env.receive({project,revision:2});assert.ok(clip().labels[0].x>.2,'後端舊位置不得蓋掉拖曳草稿');
  const rebuilt=environment(env.storage);await rebuilt.receive({project,revision:2});
  assert.ok(vm.runInContext('photo().labels[0].x>.2',rebuilt.context));assert.equal(rebuilt.changes().length,0);
  const promise=rebuilt.elements.get('applyChanges').onclick(),sent=rebuilt.changes()[0].value;
  assert.equal(sent.comparisons[0].labels[0].opacity,0);assert.equal(sent.comparisons[0].labels[0].comparison_title_version,2);
  await rebuilt.receive({project:{...project,comparisons:sent.comparisons},revision:3,response:{nonce:sent.nonce,ok:true}});await promise;
});
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
test('PNG新增、500次畫布移動、時間軸拖曳、指針跳轉與跨rerun均無Python事件，輸出含最新PNG',async()=>{
  const env=environment(),assets=[{id:'asset',name:'透明PNG',image:'png-image',width:220,height:110}];
  await env.receive({project:{photos:env.rows(),assets,overlays:[]}});
  env.elements.get('assetLibrary').children[0].onclick();env.elements.get('assetLibrary').children[0].onclick();
  assert.equal(vm.runInContext('draft.overlays.length',env.context),2);
  env.elements.get('assetLibrary').children[0].onclick();
  env.elements.get('deleteOverlay').onclick();
  assert.equal(vm.runInContext('draft.overlays.length',env.context),2,'刪除只移除選取的PNG');
  assert.equal(env.changes().length,0);
  vm.runInContext('pngEditor.select(draft.overlays[1].id)',env.context);
  env.elements.get('canvas').dispatch('pointerdown',{clientX:540,clientY:960});
  for(let i=0;i<500;i++)env.elements.get('canvas').dispatch('pointermove',{clientX:540+i/10,clientY:960+i/10});
  env.elements.get('canvas').dispatch('pointerup');assert.equal(env.changes().length,0);
  const hit=vm.runInContext('timeline.hits.find(h=>h.item.type==="png")',env.context);
  // 使用邏輯Canvas像素換算到測試DOM的固定1080×1920矩形。
  const tc=env.elements.get('timelineCanvas'),x=(hit.x+hit.w/2)*1080/tc.width,y=(hit.y+10)*1920/tc.height;
  tc.dispatch('pointerdown',{clientX:x,clientY:y});
  for(let i=0;i<100;i++)tc.dispatch('pointermove',{clientX:x+i,clientY:y});tc.dispatch('pointerup');
  assert.equal(env.changes().length,0);assert.ok(vm.runInContext('draft.overlays[0].start',env.context)>0);
  tc.dispatch('pointerdown',{clientX:400,clientY:5});
  tc.dispatch('pointermove',{clientX:500,clientY:5});tc.dispatch('pointerup');
  assert.equal(env.changes().length,0,'播放指針拖曳也不送Python');
  env.elements.get('png_rotation').value='45';env.elements.get('png_rotation').oninput();
  env.elements.get('png_scale').value='1.5';env.elements.get('png_scale').oninput();
  env.elements.get('photos').children[1].onclick();env.elements.get('photos').children[0].onclick();
  const rebuilt=environment(env.storage);await rebuilt.receive({project:{photos:rebuilt.rows(),assets,overlays:[]}});
  assert.equal(vm.runInContext('draft.overlays.length',rebuilt.context),2);
  await rebuilt.receive({project:{photos:rebuilt.rows(),assets,overlays:[]},export_request:'png-export'});
  const sent=rebuilt.changes()[0].value;assert.equal(sent.overlays.length,2);assert.equal(sent.schema_version,4);
  assert.equal(sent.overlays[0].rotation,45);assert.equal(sent.overlays[0].scale,1.5);
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

test('對比自動／重複配對、裁切、分割線500次拖曳、PNG及模板切換全部本地，输出使用最新片段',async()=>{
  const env=environment(),get=id=>env.elements.get(id),rows=env.rows();rows[0].role='before';rows[1].role='after';
  const assets=[{id:'asset',name:'透明圖層',image:'png-image',width:220,height:110}];
  const originalOverlay={id:'items-png',type:'png',source:'asset',start:0,duration:3,enter:.5,exit:.5,layer:20};
  const project=()=>({photos:rows,template_id:'compare',comparisons:[],comparison_overlays:[],assets,overlays:[originalOverlay]});
  await env.receive({project:project()});get('autoPair').onclick();assert.equal(vm.runInContext('draft.comparisons.length',env.context),1);
  get('autoPair').onclick();assert.equal(vm.runInContext('draft.comparisons.length',env.context),1);
  get('addPair').onclick();assert.equal(vm.runInContext('draft.comparisons.length',env.context),2);
  get('cmp_mode').value='split';get('cmp_mode').oninput();
  get('canvas').dispatch('pointerdown',{clientX:540,clientY:1200});
  for(let i=0;i<500;i++)get('canvas').dispatch('pointermove',{clientX:540+i/4,clientY:1200});get('canvas').dispatch('pointerup');
  assert.ok(vm.runInContext('photo().split',env.context)>.6);assert.equal(env.changes().length,0);
  get('viewBefore').onclick();get('fit').value='cover';get('fit').onchange();get('zoom').value=2;get('zoom').oninput();get('crop_x').value=.8;get('crop_x').oninput();
  assert.equal(vm.runInContext('photo().before_crop.zoom',env.context),2);assert.equal(vm.runInContext('photo().after_crop.zoom',env.context),1);
  get('cmp_mode').value='reveal';get('cmp_mode').oninput();get('cmp_direction').value='rtl';get('cmp_direction').oninput();
  get('duration').value=6;get('duration').oninput();get('text').value='使用者修改施工文字';get('text').oninput();
  get('assetLibrary').children[0].onclick();get('png_start').value=3;get('png_start').oninput();get('png_duration').value=4;get('png_duration').oninput();
  assert.equal(env.changes().length,0);assert.equal(vm.runInContext('draft.overlays[0].id',env.context),'items-png');
  const tc=get('timelineCanvas'),hit=vm.runInContext('timeline.hits.find(h=>h.item.type==="comparison")',env.context),x=(hit.x+hit.w/2)*1080/tc.width,y=(hit.y+10)*1920/tc.height;
  tc.dispatch('pointerdown',{clientX:x,clientY:y});for(let i=0;i<100;i++)tc.dispatch('pointermove',{clientX:x+i,clientY:y});tc.dispatch('pointerup');
  const saved=JSON.parse(env.storage.get('interior-studio-draft'));assert.equal(saved.comparisons.length,2);assert.equal(saved.comparisonOverlays.length,1);assert.equal(saved.rows[0].image,undefined);
  await env.receive({project:{...project(),template_id:'items'}});assert.equal(vm.runInContext('sequence().length',env.context),2);
  await env.receive({project:project()});assert.equal(vm.runInContext('draft.comparisons.length',env.context),2);
  const rebuilt=environment(env.storage);await rebuilt.receive({project:project()});assert.equal(vm.runInContext('draft.comparisonOverlays.length',rebuilt.context),1);
  await rebuilt.receive({project:project(),export_request:'compare-export'});const sent=rebuilt.changes()[0].value;
  assert.equal(sent.template_id,'compare');assert.equal(sent.comparisons.length,2);assert.equal(sent.comparison_overlays.length,1);assert.equal(sent.overlays.length,1);
  const edited=sent.comparisons.find(c=>c.mode==='reveal');assert.equal(edited.direction,'rtl');assert.equal(edited.duration,6);assert.equal(edited.before_crop.crop_x,.8);
  assert.ok(edited.labels.some(l=>l.text==='使用者修改施工文字'));
});

test('對比刪除片段不刪來源照片；加入施工後標籤保留原標籤且去重',async()=>{
  const env=environment(),rows=env.rows();rows[0].role='before';rows[1].role='after';
  rows[1].labels=[{id:'ai',text:'來源AI標籤',x:.2,y:.4,point_x:.5,point_y:.5,font_size:46,color:'#ffffff',background:'#222822',opacity:.88,radius:18,line:true,animation:'fade',start:0,end:4,enter:.3}];
  await env.receive({project:{photos:rows,template_id:'compare'}});env.elements.get('autoPair').onclick();env.elements.get('copyAfterLabels').onclick();env.elements.get('copyAfterLabels').onclick();
  assert.equal(vm.runInContext('photo().labels.length',env.context),3);assert.equal(vm.runInContext('photos[1].labels.length',env.context),1);
  env.elements.get('deletePhoto').onclick();assert.equal(vm.runInContext('draft.comparisons.length',env.context),0);assert.equal(vm.runInContext('photos.length',env.context),2);assert.equal(env.changes().length,0);
});
