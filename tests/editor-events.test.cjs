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
const StudioLabelTiming=require('../frontend/label-timing.js');
const StudioVersion=require('../frontend/content-version.js');
function environment(storage=new Map()) {
  const elements=new Map(),messages=[],listeners={},frames=new Map(),downloads=[];let serial=0,draws=0;
  function element(tag='div') {
    const handlers={},ctx={font:'46px sans-serif',measureText:text=>({width:text.length*46}),
      roundRect(){},beginPath(){},fill(){},fillText(){},strokeText(){},fillRect(){},moveTo(){},lineTo(){},stroke(){},
      arc(){},rect(){},clip(){},save(){},restore(){},translate(){},rotate(){},strokeRect(){},setLineDash(){},drawImage(){draws++;}};
    return {tagName:tag,children:[],value:'',checked:true,disabled:false,hidden:false,width:1080,height:1920,
      paused:true,currentTime:0,readyState:2,seeking:false,videoWidth:220,videoHeight:110,play(){this.paused=false;return Promise.resolve();},pause(){this.paused=true;},load(){},
      classList:{toggle(){},add(){},remove(){}},dataset:{},style:{},
      getContext:()=>ctx,getBoundingClientRect:()=>({left:0,top:0,width:1080,height:1920}),
      querySelector:()=>null,
      replaceChildren(){this.children=[];},append(...children){this.children.push(...children);},
      addEventListener(name,fn){handlers[name]=fn;},removeAttribute(){},setPointerCapture(){},
      click(){if(this.tagName==='a')downloads.push({href:this.href,name:this.download});else this.onclick?.();},remove(){},
      dispatch(name,data={}){handlers[name]?.({preventDefault(){},pointerId:1,...data});}};
  }
  const document={activeElement:null,hidden:false,getElementById(id){if(!elements.has(id))elements.set(id,element(id==='canvas'?'canvas':'div'));return elements.get(id);},
    body:element('body'),createElement:element,createTextNode:text=>({textContent:text}),querySelector:()=>element(),querySelectorAll:()=>[...elements.values()],addEventListener(){},removeEventListener(){}};
  class FakeImage {constructor(){this.naturalWidth=220;this.naturalHeight=110;} set src(value){this._src=value;Promise.resolve().then(()=>this.onload?.());}get src(){return this._src;}}
  const window={parent:{postMessage(msg){messages.push(JSON.parse(JSON.stringify(msg)));}},addEventListener(name,fn){listeners[name]=fn;}};
  window.StudioTitle=require('../frontend/title-model.js');
  const context=vm.createContext({document,window,Image:FakeImage,ResizeObserver:class{observe(){}},
    StudioOutput:require('../frontend/output-controller.js'),StudioTitle:window.StudioTitle,
    StudioPairing:require('../frontend/pairing.js'),StudioPhotoHistory:require('../frontend/photo-history.js'),
    StudioTour:require('../frontend/tour-model.js'),
    StudioDraft:{DraftState,metadata},StudioVersion,StudioLabel,StudioPhoto,StudioAnimation,StudioAI,StudioTimeline,StudioOverlay,StudioComparison,StudioSafeArea,StudioMusic,StudioLabelTiming,crypto:webcrypto,console,
    requestAnimationFrame(fn){const id=++serial;frames.set(id,fn);return id;},cancelAnimationFrame(id){frames.delete(id);},
    setTimeout(){return ++serial;},clearTimeout(){},performance:{now:()=>0},URL:{revokeObjectURL(){}},
    sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}});
  vm.runInContext(fs.readFileSync('frontend/timeline-ui.js','utf8'),context);
  vm.runInContext(fs.readFileSync('frontend/png-editor.js','utf8'),context);
  vm.runInContext(fs.readFileSync('frontend/comparison-editor.js','utf8'),context);
  vm.runInContext(fs.readFileSync('frontend/tour-editor.js','utf8'),context);context.StudioTourUI=window.StudioTourUI;
  vm.runInContext(fs.readFileSync('frontend/cover-editor.js','utf8'),context);
  context.StudioCover=window.StudioCover;
  vm.runInContext(fs.readFileSync('frontend/body-editor.js','utf8'),context);
  context.StudioBody=window.StudioBody;
  context.StudioBody.configure(JSON.parse(fs.readFileSync('frontend/body-layout.json','utf8')));
  vm.runInContext(fs.readFileSync('frontend/quick-title.js','utf8'),context);context.StudioQuickTitle=window.StudioQuickTitle;
  context.StudioTimelineUI=window.StudioTimelineUI;context.StudioPNG=window.StudioPNG;context.StudioComparisonUI=window.StudioComparisonUI;
  vm.runInContext(fs.readFileSync('frontend/editor.js','utf8'),context);
  const rows=()=>[{id:'p1',content_hash:'hash',name:'first',image:'image1',tiles:{},labels:[],duration:4,zoom:1,crop_x:.5,crop_y:.5,fit:'contain'},
    {id:'p2',name:'second',image:'image2',tiles:{},labels:[],duration:4,zoom:1,crop_x:.5,crop_y:.5,fit:'contain'}];
  async function receive(extra={}){await listeners.message({source:window.parent,data:{type:'streamlit:render',args:{project:{photos:rows()},session:'session',revision:1,busy:false,...extra}}});}
  const changes=()=>messages.filter(m=>m.type==='streamlit:setComponentValue');
  return {elements,changes,receive,rows,context,storage,frames,downloads,get draws(){return draws;}};
}

test('第五階段：點圖建立共用房間、改名、未指定不沿用，刪除使用中的房間先提示且取消不改seq',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id);
  const project={photos:env.rows(),template_id:'tour',floor_plan:{id:'plan',image:'plan-image',width:220,height:110},tour_layout:require('../frontend/tour-layout.json')};
  await env.receive({project});assert.equal(run('draft.tour.clips.length'),2);get('tourRoomName').value='客廳';get('tourMap').dispatch('pointerdown',{clientX:540,clientY:960});
  const id=run('draft.tour.rooms[0].id');assert.equal(run('draft.tour.rooms[0].x'),.5);get('tourClipRoom').value=id;get('tourClipRoom').onchange();
  get('photos').children[1].onclick();assert.equal(run('photo().room_id'),null);get('tourClipRoom').value=id;get('tourClipRoom').onchange();get('tourRoomName').value='大客廳';get('tourRoomName').oninput();
  assert.equal(run('draft.tour.rooms[0].name'),'大客廳');const seq=run('draft.seq');get('tourRoomList').children[0].onclick();assert.equal(run('draft.seq'),seq);
  get('tourRoomDelete').onclick();assert.equal(get('tourDeleteConfirm').hidden,false);get('tourDeleteCancel').onclick();assert.equal(run('draft.seq'),seq);
  get('tourRoomDelete').onclick();get('tourDeleteConfirm').onclick();assert.equal(run('draft.tour.rooms.length'),0);assert.ok(run('draft.tour.clips.every(c=>c.room_id===null)'));assert.equal(env.changes().length,0);
});

test('第五階段：更換平面圖保留房名關聯且待定位，重建／seek保留設定、不新增內容版本',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id);
  const project={photos:env.rows(),template_id:'tour',floor_plan:{id:'plan',image:'plan-image',width:220,height:110},tour_layout:require('../frontend/tour-layout.json')};
  await env.receive({project});get('tourRoomName').value='廚房';get('tourMap').dispatch('pointerdown',{clientX:540,clientY:960});const id=run('draft.tour.rooms[0].id');get('tourClipRoom').value=id;get('tourClipRoom').onchange();
  await env.receive({project:{...project,floor_plan:{...project.floor_plan,id:'plan2',image:'plan2'}},revision:2});assert.equal(run('draft.tour.rooms[0].needs_review'),true);assert.equal(run('draft.tour.clips[0].room_id'),id);
  get('tourRoomList').children[0].onclick();get('tourMap').dispatch('pointerdown',{clientX:600,clientY:960});assert.equal(run('draft.tour.rooms[0].needs_review'),false);
  const rebuilt=environment(env.storage);await rebuilt.receive({project:{...project,floor_plan:{...project.floor_plan,id:'plan2',image:'plan2'}},revision:2});const r=s=>vm.runInContext(s,rebuilt.context),seq=r('draft.seq');
  rebuilt.elements.get('seek').value=5;rebuilt.elements.get('seek').oninput();assert.equal(r('draft.seq'),seq);assert.equal(r('draft.tour.rooms[0].name'),'廚房');assert.equal(rebuilt.changes().length,0);
  r('draft.dirty=false;draft.pending=null;draft.revision=3');
  await rebuilt.receive({project,revision:1});assert.equal(r('draft.tour.rooms[0].name'),'廚房');
});

test('第五階段：影片與照片混排、起訖與靜音本地更新，時間軸移動／裁切有效，輸出批次含最新tour',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id);
  const video={id:'vid',name:'walk.mp4',src:'/app/static/tour/video.mp4',poster:'poster',duration:8,width:220,height:110,has_audio:true};
  await env.receive({project:{photos:env.rows(),template_id:'tour',videos:[video],tour_layout:require('../frontend/tour-layout.json')}});assert.equal(run('draft.tour.clips.length'),3);
  get('photos').children[2].onclick();get('tourIn').value=2;get('tourOut').value=5;get('tourIn').onchange();get('tourMute').checked=false;get('tourMute').onchange();
  assert.equal(run('photo().duration'),3);assert.equal(run('photo().muted'),false);assert.equal(get('browserExport').disabled,true);
  run("const c=draft.tour.clips[2];StudioTimeline.edit(StudioTimeline.items(draft.tour.clips)[4]||{type:'video',source:c.id,id:c.id,start:8,duration:3},'move',-8,draft.tour.clips,[])");
  assert.equal(run('draft.tour.clips[0].kind'),'video');
  assert.equal(env.changes().length,0);
  vm.runInContext("synchronize('save_project')",env.context);const sent=env.changes()[0].value;assert.equal(sent.tour.clips.find(c=>c.kind==='video').in,2);assert.equal(sent.tour.clips.find(c=>c.kind==='video').muted,false);
});

test('第四階段：建議／拒絕不改草稿序號，接受衝突需明確確認且不覆蓋原片段',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id),rows=env.rows();
  rows[0].role='before';rows[1].role='after';rows.push({...rows[1],id:'p3',name:'third',image:'image3'});
  for(const p of rows)p.labels=[{id:'ai-'+p.id,source:'gemini',text:'客廳',description:'客廳有落地窗及橫梁',category:'其他特色',start:1,end:4,enter:.3,label_timing_version:1}];
  let serial=0;const clip=StudioComparison.make(rows[0],rows[1],()=>`existing-${++serial}`),before=JSON.stringify(clip);
  await env.receive({project:{photos:rows,template_id:'compare',comparisons:[clip]}});const seq=run('draft.seq');
  get('suggestPairs').onclick();assert.equal(run('draft.seq'),seq);assert.equal(run('draft.comparisons.length'),1);
  let card=get('pairSuggestions').children[0];card.children[5].onclick();assert.equal(run('draft.seq'),seq);
  run('comparisonEditor.rejected.clear()');get('suggestPairs').onclick();card=get('pairSuggestions').children[0];
  card.children[4].onclick();assert.equal(run('draft.comparisons.length'),1);assert.equal(run('draft.seq'),seq);
  card.children[3].children[0].checked=true;card.children[4].onclick();assert.equal(run('draft.comparisons.length'),2);
  assert.equal(JSON.stringify(run('draft.comparisons[0]')),before);assert.equal(run('draft.comparisons[1].after_id'),'p3');
  assert.equal(env.changes().length,0);
});

test('第四階段：更換前／後及交換保留片段ID時長動畫，分類不刪引用，單純選取不改seq',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id),rows=env.rows();rows[0].role='before';rows[1].role='after';rows.push({...rows[0],id:'p3',name:'other',role:'general'});
  await env.receive({project:{photos:rows,template_id:'compare'}});get('autoPair').onclick();const before=JSON.parse(run('JSON.stringify(photo())'));
  get('cmp_before_id').value='p3';get('cmp_before_id').oninput();assert.equal(run('photo().before_id'),'p3');
  get('cmp_after_id').value='p1';get('cmp_after_id').oninput();assert.equal(run('photo().after_id'),'p1');
  get('swapPair').onclick();assert.equal(run('photo().before_id'),'p1');assert.equal(run('photo().after_id'),'p3');
  assert.equal(run('photo().id'),before.id);assert.equal(run('photo().duration'),before.duration);assert.equal(run('photo().transition'),before.transition);
  run("photos[0].role='general';markEdited()");assert.equal(run('draft.comparisons.length'),1);
  const seq=run('draft.seq');get('viewComparison').onclick();assert.equal(run('draft.seq'),seq);assert.equal(env.changes().length,0);
});

test('第四階段：刪來源先提示／取消不改資料，確認移除配對，復原完整資料且不逐次rerun',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id),rows=env.rows();rows[0].role='before';rows[1].role='after';
  await env.receive({project:{photos:rows,template_id:'compare'}});get('autoPair').onclick();const before=run('JSON.stringify(StudioPhotoHistory.state(draft))'),seq=run('draft.seq');
  run("deleteSource('p1')");assert.equal(run('photos.length'),2);assert.equal(run('draft.seq'),seq);get('cancelPhotoDelete').onclick();assert.equal(run('photos.length'),2);
  run("deleteSource('p1')");get('confirmPhotoDelete').onclick();assert.equal(run('photos.length'),1);assert.equal(run('draft.comparisons.length'),0);
  get('undoPhoto').onclick();assert.equal(run('photos.length'),2);assert.equal(run('draft.comparisons.length'),1);
  assert.equal(run('JSON.stringify(StudioPhotoHistory.state(draft))'),before);assert.equal(env.changes().length,0);
});

test('第四階段：刪除同步後元件重建仍可復原，下一次批次帶來源ID；後續修改拒絕覆寫',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),rows=env.rows();await env.receive();
  run("deleteSource('p1')");assert.equal(run('photos.length'),1);
  const rebuilt=environment(env.storage),get=id=>rebuilt.elements.get(id),r=s=>vm.runInContext(s,rebuilt.context);
  await rebuilt.receive({project:{photos:[rows[1]]},revision:2,undo_photo:rows[0]});get('undoPhoto').onclick();
  assert.equal(r('photos.length'),2);vm.runInContext("synchronize('apply')",rebuilt.context);const sent=rebuilt.changes()[0].value;
  assert.equal(sent.restore_photo,'p1');assert.equal(sent.photos[0].id,'p1');
  const other=environment();await other.receive();vm.runInContext("deleteSource('p1');photos[0].duration=3;markEdited()",other.context);
  other.elements.get('undoPhoto').onclick();assert.equal(vm.runInContext('photos.length',other.context),1);assert.match(other.elements.get('deleteNotice').textContent,/無法安全復原/);
});
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

test('正文時間軸拖移與兩端裁切不送Python，字級可到240，切圖／rerun／輸出保存最新時間',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id);
  const cover={enabled:true,title:'老屋88萬',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  const project={photos:env.rows(),cover,cover_assets:{layout:JSON.parse(fs.readFileSync('frontend/cover-layout.json'))}};
  await env.receive({project});assert.equal(get('bodySize').value,100);assert.equal(get('bodyStart').value,.3);
  get('bodyEnd').value='6';get('bodyEnd').oninput();
  function drag(mode,delta){const hit=vm.runInContext('timeline.hits.find(h=>h.item.type==="body_title")',env.context);
    const tc=get('timelineCanvas'),px=vm.runInContext('timeline.px',env.context);
    const x=(mode==='left'?hit.x+2:mode==='right'?hit.x+hit.w-2:hit.x+hit.w/2)*1080/tc.width,y=(hit.y+10)*1920/tc.height;
    tc.dispatch('pointerdown',{clientX:x,clientY:y});
    for(let i=1;i<=100;i++)tc.dispatch('pointermove',{clientX:x+delta*px*1080/tc.width*i/100,clientY:y});tc.dispatch('pointerup');}
  drag('right',.5);drag('left',.5);drag('move',1);
  assert.ok(Math.abs(vm.runInContext('draft.cover.body.start',env.context)-1.8)<1e-8);
  assert.ok(Math.abs(vm.runInContext('draft.cover.body.end',env.context)-7.5)<1e-8);
  get('bodySize').value='240';get('bodySize').oninput();assert.equal(env.changes().length,0);
  get('photos').children[2].onclick();get('photos').children[1].onclick();
  await env.receive({project,revision:2});const rebuilt=environment(env.storage);await rebuilt.receive({project,revision:2});
  assert.equal(vm.runInContext('draft.cover.body.font_size',rebuilt.context),240);
  await rebuilt.receive({project,revision:2,export_request:'timed-title'});const sent=rebuilt.changes()[0].value;
  assert.equal(sent.cover.body.auto_timing,false);assert.ok(Math.abs(sent.cover.body.start-1.8)<1e-8);assert.ok(Math.abs(sent.cover.body.end-7.5)<1e-8);
  assert.equal(sent.photos[0].duration,4);assert.equal(sent.photos[1].duration,4);
});
test('正文畫布500次拖曳與方向鍵均本地，照片切換／重建／輸出保留位置，封面不移動',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id);
  const cover={enabled:true,title:'可移動正文',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  const project={photos:env.rows(),cover,cover_assets:{layout:JSON.parse(fs.readFileSync('frontend/cover-layout.json'))}};
  await env.receive({project});get('photos').children[1].onclick();
  const before=vm.runInContext('({...draft.cover.body})',env.context),r=vm.runInContext('bodyEditor.bounds()',env.context);
  get('canvas').dispatch('pointerdown',{clientX:r.x+30,clientY:r.y+30});
  assert.equal(vm.runInContext('dragging.type',env.context),'body');
  for(let i=0;i<500;i++)get('canvas').dispatch('pointermove',{clientX:r.x+30+i/5,clientY:r.y+30+i/2});get('canvas').dispatch('pointerup');
  get('canvas').dispatch('keydown',{key:'ArrowUp'});
  const position=vm.runInContext('({x:draft.cover.body.x,y:draft.cover.body.y})',env.context);
  assert.ok(position.x>before.x);assert.ok(position.y>before.y);assert.equal(env.changes().length,0);
  assert.equal(vm.runInContext('draft.cover.title',env.context),'可移動正文');
  get('photos').children[2].onclick();get('photos').children[1].onclick();await env.receive({project,revision:2});
  const rebuilt=environment(env.storage);await rebuilt.receive({project,revision:2});
  assert.equal(vm.runInContext('draft.cover.body.x',rebuilt.context),position.x);
  await rebuilt.receive({project,revision:2,export_request:'body-position'});const sent=rebuilt.changes()[0].value;
  assert.equal(sent.cover.body.x,position.x);assert.equal(sent.cover.body.y,position.y);assert.equal(sent.cover.body.follow_cover,true);
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
  assert.ok(get('safeAreaGuide').innerHTML.includes('y="273"'),'封面預覽採3:4標題安全區');
  assert.ok(get('safeAreaGuide').innerHTML.includes('y="602"'),'封面照片區不再垂直拉長');
  assert.ok(get('safeAreaGuide').innerHTML.includes('translate(0 240)'),'安全區與片頭一起置中');
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
test('前後標題拖曳共用位置、選取保留時間、舊草稿升級且rerun不送Python',async()=>{
  const env=environment(),rows=env.rows();rows[0].role='before';rows[1].role='after';
  const c=StudioComparison.make(...rows,webcrypto.randomUUID.bind(webcrypto));
  c.labels[0].text='原始空間';c.labels[0].x=.2;
  for(const l of c.labels){delete l.comparison_title_version;l.opacity=.88;l.radius=18;}
  c.labels[1].x=.57;c.labels[0].end=3;
  const project={photos:rows,comparisons:[c],template_id:'compare'};await env.receive({project});
  const get=id=>env.elements.get(id),clip=()=>vm.runInContext('photo()',env.context);
  assert.equal(clip().labels[0].text,'原始空間');assert.equal(clip().labels[0].opacity,0);
  assert.equal(clip().labels[1].x,.2);assert.equal(clip().labels[0].end,2);
  get('labels').children[1].onclick();assert.equal(vm.runInContext('time',env.context),0);
  get('seek').value=2.5;get('seek').oninput();
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
  get('seek').value=2;get('seek').oninput();
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
  get('duration').value=6;get('duration').oninput();get('labels').children[0].onclick();get('text').value='使用者修改施工文字';get('text').oninput();
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

test('照片標籤延後一次、新增預設1秒、正文100px／50%／24.5%，未同步草稿重建後不重複延後',async()=>{
  const env=environment(),rows=env.rows(),get=id=>env.elements.get(id);
  rows[0].labels=[{id:'legacy',text:'既有裝修',x:.2,y:.4,point_x:.5,point_y:.5,font_size:46,color:'#ffffff',background:'#222822',opacity:.88,radius:18,line:true,animation:'fade',start:.3,end:4,enter:.6}];
  const cover={enabled:false,title:'封面不變',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[],
    body:{...require('../frontend/body-editor.js').newBody(),font_size:120,x:.5,y:530/1920,version:3}};
  const project={photos:rows,cover};await env.receive({project});
  assert.equal(vm.runInContext('photos[0].labels[0].start',env.context),1.3);
  assert.equal(get('bodySize').value,100);assert.equal(get('bodyX').value,50);assert.equal(get('bodyY').value,24.5);
  get('labels').children[0].onclick();get('start').value='.5';get('start').oninput();get('addLabel').onclick();
  assert.equal(vm.runInContext('photos[0].labels[1].start',env.context),1);
  await env.receive({project,revision:2});const rebuilt=environment(env.storage);await rebuilt.receive({project,revision:2});
  assert.equal(rebuilt.changes().length,0);assert.equal(vm.runInContext('photos[0].labels[0].start',rebuilt.context),.5);
  await rebuilt.receive({project,revision:2,export_request:'delay-test'});
  const event=rebuilt.changes()[0].value;assert.deepEqual(event.photos[0].labels.map(l=>l.start),[.5,1]);
  assert.deepEqual([event.cover.body.font_size,event.cover.body.x,event.cover.body.y],[100,.5,.245]);
  assert.equal(event.cover.font_size,120,'封面字級不變');
});

test('儲存專案一次同步未套用的標籤／PNG／封面／正文，等待時新編輯不被舊快照覆蓋',async()=>{
  const env=environment(),get=id=>env.elements.get(id);
  const cover={enabled:true,title:'老屋88萬',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  const assets=[{id:'asset',name:'透明圖層',image:'png-image',width:220,height:110}];
  const cover_assets={layout:JSON.parse(fs.readFileSync('frontend/cover-layout.json'))};
  await env.receive({project:{photos:env.rows(),cover,cover_assets,assets,overlays:[]}});get('photos').children[1].onclick();
  get('addLabel').onclick();get('text').value='尚未套用的文字';get('text').oninput();
  get('assetLibrary').children[0].onclick();get('png_rotation').value='33';get('png_rotation').oninput();
  get('bodyX').value='44';get('bodyX').oninput();
  assert.equal(env.changes().length,0);
  const promise=vm.runInContext("synchronize('save_project')",env.context);assert.equal(env.changes().length,1);assert.ok(vm.runInContext('draft.pending',env.context));
  const event=env.changes()[0].value;
  assert.equal(event.action,'save_project');assert.equal(event.photos[0].labels[0].text,'尚未套用的文字');
  assert.equal(event.overlays[0].rotation,33);assert.equal(event.cover.body.x,.44);
  assert.equal(event.cover.title,'老屋88萬');
  vm.runInContext("photos[0].labels[0].text='儲存後繼續編輯';markEdited()",env.context);
  const rows=env.rows();rows.forEach((r,i)=>r.labels=event.photos[i].labels);
  await env.receive({project:{photos:rows,cover:event.cover,assets,overlays:event.overlays},revision:2,response:{nonce:event.nonce,ok:true}});await promise;
  assert.equal(vm.runInContext('photos[0].labels[0].text',env.context),'儲存後繼續編輯');assert.equal(env.changes().length,1);
  assert.equal(vm.runInContext('draft.pending',env.context),null);
  // 匯入即切換新session：即使相同照片ID，仍由匯入內容取代舊本地草稿。
  rows[0].labels[0]={...event.photos[0].labels[0],text:'匯入的專案文字',start:.2};
  await env.receive({session:'new-import-session',project:{photos:rows,cover:event.cover,assets,overlays:event.overlays},revision:3});
  assert.equal(vm.runInContext('photos[0].labels[0].text',env.context),'匯入的專案文字');
  assert.equal(vm.runInContext('photos[0].labels[0].start',env.context),.2);
});

test('LOGO時間軸拖移與左右裁切均本地，開關封面平移，重建與專案快照保留',async()=>{
  const env=environment(),get=id=>env.elements.get(id);
  const cover={enabled:true,title:'老屋88萬',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  const project={photos:env.rows(),cover,cover_assets:{layout:JSON.parse(fs.readFileSync('frontend/cover-layout.json'))}};
  await env.receive({project});assert.equal(get('logoAutoTime').checked,true);assert.equal(get('logoStart').value,.3);
  function drag(mode,delta){const hit=vm.runInContext('timeline.hits.find(h=>h.item.type==="body_logo")',env.context);
    const tc=get('timelineCanvas'),px=vm.runInContext('timeline.px',env.context);
    const x=(mode==='left'?hit.x+2:mode==='right'?hit.x+hit.w-2:hit.x+hit.w/2)*1080/tc.width,y=(hit.y+10)*1920/tc.height;
    tc.dispatch('pointerdown',{clientX:x,clientY:y});
    for(let i=1;i<=100;i++)tc.dispatch('pointermove',{clientX:x+delta*px*1080/tc.width*i/100,clientY:y});tc.dispatch('pointerup');}
  drag('right',-2);drag('left',1);drag('move',1);
  assert.ok(Math.abs(vm.runInContext('draft.cover.body.logo_start',env.context)-2.3)<1e-8);
  assert.ok(Math.abs(vm.runInContext('draft.cover.body.logo_end',env.context)-7.3)<1e-8);
  assert.equal(vm.runInContext('draft.cover.body.auto_timing',env.context),true);assert.equal(env.changes().length,0);
  get('coverEnabled').checked=false;get('coverEnabled').onchange();
  assert.ok(Math.abs(vm.runInContext('draft.cover.body.logo_start',env.context)-2)<1e-8);
  get('coverEnabled').checked=true;get('coverEnabled').onchange();get('photos').children[2].onclick();get('photos').children[1].onclick();
  const rebuilt=environment(env.storage);await rebuilt.receive({project,revision:2});
  assert.ok(Math.abs(vm.runInContext('draft.cover.body.logo_start',rebuilt.context)-2.3)<1e-8);
  const promise=vm.runInContext("synchronize('save_project')",rebuilt.context),event=rebuilt.changes()[0].value;
  assert.equal(event.action,'save_project');assert.equal(event.cover.body.logo_auto_timing,false);
  const rows=rebuilt.rows();await rebuilt.receive({project:{...project,photos:rows,cover:event.cover},revision:3,response:{nonce:event.nonce,ok:true}});await promise;
  rebuilt.elements.get('bodyLogo').checked=false;rebuilt.elements.get('bodyLogo').onchange();
  assert.equal(vm.runInContext('timeline.hits.some(h=>h.item.type==="body_logo")',rebuilt.context),false);
  rebuilt.elements.get('bodyLogo').checked=true;rebuilt.elements.get('bodyLogo').onchange();
  rebuilt.elements.get('logoAutoTime').checked=true;rebuilt.elements.get('logoAutoTime').onchange();
  assert.equal(rebuilt.elements.get('logoStart').value,.3);assert.equal(rebuilt.elements.get('logoEnd').value,8.3);
});

test('即時版本狀態不送Python，舊ACK不蓋新版本，工作區檢查只送一次且取消保留',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id);
  const schema=JSON.parse(fs.readFileSync('frontend/content-schema.json','utf8'));
  const context={schema,photos:{p1:'hash',p2:'hash2'},assets:[],music:null,width:1080,engine:'renderer'};
  const project={photos:env.rows()},initial=StudioVersion.digest(StudioVersion.document(project,context));
  const versions={context,synced:initial,mp4:initial,zip:initial,backup:initial};
  await env.receive({project,versions});assert.equal(get('applyChanges').disabled,true);
  assert.equal(vm.runInContext('draft.contentVersion',env.context),initial);
  get('addLabel').onclick();get('text').value='送出的標籤';get('text').oninput();
  const seq=vm.runInContext('draft.seq',env.context);get('text').onchange();assert.equal(vm.runInContext('draft.seq',env.context),seq);
  assert.equal(env.changes().length,0);assert.ok(get('versionStatus').textContent.includes('舊版本，需要重新輸出'));
  const pending=get('applyChanges').onclick(),sent=env.changes()[0].value;
  get('text').value='同步途中更新';get('text').oninput();const newest=vm.runInContext('draft.contentVersion',env.context);
  const remote=env.rows().map(row=>({...row,...sent.photos.find(p=>p.id===row.id)}));
  await env.receive({project:{...project,photos:remote},versions:{...versions,synced:sent.content_version},revision:2,
    response:{nonce:sent.nonce,ok:true,content_version:sent.content_version}});await pending;
  assert.equal(vm.runInContext('draft.contentVersion',env.context),newest);
  assert.equal(vm.runInContext('draft.rows[0].labels[0].text',env.context),'同步途中更新');
  await env.receive({project,versions:{...versions,synced:sent.content_version},revision:2,guard_request:{id:'guard-1',action:'clear',status:'checking'}});
  const probes=env.changes().filter(m=>m.value.action==='inspect_guard');assert.equal(probes.length,1);assert.equal(probes[0].value.content_version,newest);
  assert.equal(get('addLabel').disabled,true);
  await env.receive({project,versions:{...versions,synced:sent.content_version},revision:2,guard_request:{id:'guard-1',action:'clear',status:'confirm'}});
  assert.equal(env.changes().filter(m=>m.value.action==='inspect_guard').length,1);
  await env.receive({project,versions:{...versions,synced:sent.content_version},revision:2,guard_request:null});
  assert.equal(get('addLabel').disabled,false);assert.equal(vm.runInContext('draft.contentVersion',env.context),newest);
  assert.equal(vm.runInContext('draft.rows[0].labels[0].text',env.context),'同步途中更新');
  const rebuilt=environment(env.storage);await rebuilt.receive({project,versions:{...versions,synced:sent.content_version},revision:2});
  assert.equal(vm.runInContext('draft.contentVersion',rebuilt.context),newest);
});

test('暫停／seek維持動畫姿態與內容版本，未出現文字只可在清單編輯或明確定位',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id),run=s=>vm.runInContext(s,env.context);
  await env.receive();get('addLabel').onclick();
  const schema=JSON.parse(fs.readFileSync('frontend/content-schema.json','utf8'));
  const context={schema,photos:{p1:'hash',p2:'hash2'},assets:[],music:null,width:1080,engine:'renderer'};
  env.context.testContext=context;run('draft.configureVersions({context:testContext,synced:draft.contentVersion})');
  const seq=run('draft.seq'),version=run('draft.contentVersion');
  get('seek').value=.5;get('seek').oninput();
  assert.equal(run('canEdit()'),true);assert.equal(run('labelPose(photo(),photo().labels[0])'),null);
  get('labels').children[0].onclick();assert.equal(run('time'),.5);assert.equal(get('text').value,'裝修項目');
  get('edit').onclick();assert.equal(run('positioning'),true);assert.ok(run('posedBounds(photo(),label())'));
  get('edit').onclick();assert.equal(run('labelPose(photo(),label())'),null);
  get('seek').value=1.2;get('seek').oninput();
  assert.deepEqual({...run('labelPose(photo(),label())')},StudioAnimation.pose(run('label()'),1.2));
  assert.notEqual(run('labelPose(photo(),label()).x'),0,'暫停途中不能跳到進場完成位置');
  await get('play').onclick();assert.equal(run('playing'),true);assert.equal(run('canEdit()'),false);
  get('canvas').dispatch('pointerdown',{clientX:300,clientY:600});assert.equal(run('dragging'),null);
  await get('play').onclick();assert.equal(run('canEdit()'),true);assert.equal(run('time'),1.2);
  get('timelineZoom').value=2;get('timelineZoom').oninput();
  get('photos').children[1].onclick();assert.equal(get('selectionHeading').textContent,'目前片段：second');
  const hit=run('timeline.hits.find(h=>h.item.type==="photo")'),tc=get('timelineCanvas');
  tc.dispatch('pointerdown',{clientX:(hit.x+hit.w/2)*1080/tc.width,clientY:(hit.y+10)*1920/tc.height});tc.dispatch('pointerup');
  assert.equal(run('draft.seq'),seq);assert.equal(run('draft.currentVersion()'),version);
  assert.equal(env.changes().length,0);
});

test('暫停中按真正滑入位置拖曳文字，增量正確且不跳動畫／不送Python',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id),run=s=>vm.runInContext(s,env.context);
  await env.receive();get('addLabel').onclick();get('seek').value=1.2;get('seek').oninput();
  const b=run('posedBounds(photo(),label())'),x=run('label().x'),y=run('label().y');
  get('canvas').dispatch('pointerdown',{clientX:b.x+b.width/2,clientY:b.y+b.height/2});
  assert.equal(run('dragging.type'),'label');
  get('canvas').dispatch('pointermove',{clientX:b.x+b.width/2+50,clientY:b.y+b.height/2+40});get('canvas').dispatch('pointerup');
  assert.ok(Math.abs(run('label().x')-x-50/1080)<1e-8);assert.ok(Math.abs(run('label().y')-y-40/1920)<1e-8);
  assert.equal(run('time'),1.2);assert.equal(env.changes().length,0);
  assert.ok(get('selectionHeading').textContent.startsWith('文字：'));
});

test('暫停PNG依實際淡入與滑入姿態拖曳／縮放，選取不跳回起點，設定優先',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id),run=s=>vm.runInContext(s,env.context);
  const assets=[{id:'asset',name:'透明圖層',image:'png-image',width:220,height:110}];
  await env.receive({project:{photos:env.rows(),assets}});get('assetLibrary').children[0].onclick();
  get('png_animation').value='left';get('png_animation').oninput();
  get('seek').value=.2;get('seek').oninput();const g=run('pngEditor.posedGeometry(pngEditor.item())'),before=run('pngEditor.item().x');
  get('canvas').dispatch('pointerdown',{clientX:g.x,clientY:g.y});assert.equal(run('dragging.type'),'png');
  assert.equal(run('time'),.2);
  get('canvas').dispatch('pointermove',{clientX:g.x+60,clientY:g.y+20});get('canvas').dispatch('pointerup');
  assert.ok(Math.abs(run('pngEditor.item().x')-before-60/1080)<1e-8);
  const shown=run('pngEditor.posedGeometry(pngEditor.item())'),scale=run('pngEditor.item().scale');
  get('canvas').dispatch('pointerdown',{clientX:shown.x+shown.width/2,clientY:shown.y+shown.height/2});
  assert.equal(run('pngEditor.drag.mode'),'scale');
  get('canvas').dispatch('pointermove',{clientX:shown.x+shown.width,clientY:shown.y+shown.height});get('canvas').dispatch('pointerup');
  assert.ok(run('pngEditor.item().scale')>scale);assert.ok(get('selectionHeading').textContent.startsWith('PNG：'));
  assert.equal(env.changes().length,0);
});

test('替換目前照片只送非內容事件，未同步標籤與前後對比定位在媒體回覆後保留',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id),run=s=>vm.runInContext(s,env.context);
  await env.receive();get('addLabel').onclick();get('text').value='未同步人工標籤';get('text').oninput();
  const seq=run('draft.seq');get('photos').children[0].onclick();get('replacePhoto').onclick();
  const event=env.changes()[0].value;assert.equal(event.action,'replace_photo');assert.equal(event.photo_id,'p1');assert.equal(run('draft.seq'),seq);
  const rows=env.rows();rows[0]={...rows[0],content_hash:'new-image',name:'new.png',image:'replacement-image'};
  await env.receive({project:{photos:rows},revision:2});assert.equal(run('photos[0].labels[0].text'),'未同步人工標籤');assert.equal(run('photos[0].image'),'replacement-image');
  assert.equal(run('photos[0].id'),'p1');assert.equal(run('selectedPhoto'),'p1');assert.equal(run('selectedLabel'),null,'rerun仍保留照片選取，不改成第一個文字');
  get('photos').children[1].onclick();get('replacePhoto').onclick();assert.equal(env.changes()[1].value.photo_id,'p2');
});

test('播放跨照片後暫停同步設定，錄製結尾不開編輯框；時間軸微動不改自動時間',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id),run=s=>vm.runInContext(s,env.context);
  await env.receive();await get('play').onclick();run('tick(5000)');await get('play').onclick();
  assert.equal(run('selectedPhoto'),'p2');assert.equal(get('photoNumber').textContent,'2 / 2');assert.equal(run('canEdit()'),true);
  run('recording=true;playing=true;tick(9000)');assert.equal(run('editing'),false);assert.equal(run('canEdit()'),false);
  run('recording=false');
  {
  const env=environment(),get=id=>env.context.document.getElementById(id),run=s=>vm.runInContext(s,env.context);
  const cover={enabled:true,title:'Test',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[]};
  await env.receive({project:{photos:env.rows(),cover,cover_assets:{layout:JSON.parse(fs.readFileSync('frontend/cover-layout.json','utf8'))}}});
  const hit=run('timeline.hits.find(h=>h.item.type==="body_title")'),tc=get('timelineCanvas');
  const x=(hit.x+hit.w/2)*1080/tc.width,y=(hit.y+10)*1920/tc.height;
  tc.dispatch('pointerdown',{clientX:x,clientY:y});const seq=run('draft.seq');
  tc.dispatch('pointermove',{clientX:x+.01,clientY:y});tc.dispatch('pointerup');
  assert.equal(run('draft.cover.body.auto_timing'),true);assert.equal(run('draft.seq'),seq);
  }
});

test('替換媒體回覆不覆蓋人工定位，AI與對比引用標記待確認且舊回覆無效',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id),run=s=>vm.runInContext(s,env.context);
  const rows=env.rows();rows[0].role='before';rows[1].role='after';
  const clip=StudioComparison.make(...rows,webcrypto.randomUUID.bind(webcrypto));
  await env.receive({project:{photos:rows,template_id:'compare',comparisons:[clip]}});
  run("photos[0].labels.push({id:'ai',text:'木紋地板',source:'gemini',needs_review:false,point_x:.12,point_y:.8});draft.comparisons[0].labels[0].source='gemini';draft.comparisons[0].labels[0].needs_review=false;draft.dirty=true;");
  run("draft.tour={rooms:[],clips:[{kind:'photo',source:'p1',labels:[{source:'gemini',needs_review:false,point_x:.12}]}],overlays:[],seen_sources:[]}");
  const changed=rows.map(p=>({...p}));changed[0].content_hash='replacement';changed[0].image='new-image';
  await env.receive({project:{photos:changed,template_id:'compare',comparisons:[clip]},revision:2});
  assert.equal(run('photos[0].labels[0].needs_review'),true);assert.equal(run('photos[0].labels[0].point_x'),.12);
  assert.equal(run('draft.comparisons[0].labels[0].needs_review'),true);
  assert.equal(run('draft.tour.clips[0].labels[0].needs_review'),true);assert.equal(run('draft.tour.clips[0].labels[0].point_x'),.12);
  await env.receive({project:{photos:rows,template_id:'compare',comparisons:[clip]},revision:1});
  assert.equal(run('photos[0].content_hash'),'replacement');assert.equal(env.changes().length,0);
});

test('一鍵ZIP固定A、同步與背景處理仍可改B；精確ACK才啟動，完成／rerun／重建只下載一次',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id),run=s=>vm.runInContext(s,env.context);
  const context={schema:JSON.parse(fs.readFileSync('frontend/content-schema.json','utf8')),photos:{p1:'hash',p2:'hash2'},assets:[],music:null,width:1080,engine:'renderer'};
  const project={photos:env.rows()},initial=StudioVersion.digest(StudioVersion.document(project,context)),versions={context,synced:initial};
  await env.receive({project,versions});get('addLabel').onclick();get('text').value='客廳A';get('text').oninput();
  const pending=env.context.window.StudioOutputBridge.capture('zip',1080),sent=env.changes()[0].value;
  assert.equal(sent.photos[0].labels[0].text,'客廳A');assert.equal(sent.output_protocol,3);
  get('text').value='客廳B';get('text').oninput();const latest=run('draft.contentVersion');
  const accepted={photos:env.rows().map((row,i)=>({...row,...sent.photos[i]}))};
  await env.receive({project:accepted,versions:{...versions,synced:sent.content_version},revision:2,
    response:{nonce:sent.nonce,operation_id:sent.nonce,ok:true,seq:sent.seq,content_version:sent.content_version},
    output_status:{id:sent.nonce,phase:'prepared'}});await pending;
  assert.equal(env.changes()[1].value.action,'start_output');assert.equal(env.changes()[1].value.content_version,sent.content_version);
  assert.equal(run('draft.rows[0].labels[0].text'),'客廳B');assert.equal(run('canEdit()'),true);
  const finished={project:accepted,versions:{...versions,synced:sent.content_version,zip:sent.content_version},revision:2,busy:false,
    output_status:{id:sent.nonce,phase:'done'},zip_delivery:{request_id:sent.nonce,content_version:sent.content_version,url:'/app/static/downloads/'+('a'.repeat(64))+'.zip',filename:'project.zip',expires_at:9999999999}};
  await env.receive(finished);assert.equal(env.downloads.length,1);assert.equal(run('draft.contentVersion'),latest);
  assert.equal(env.changes().at(-1).value.action,'zip_download_requested');
  await env.receive(finished);assert.equal(env.downloads.length,1);
  const restored=environment(env.storage);await restored.receive(finished);assert.equal(restored.downloads.length,0);
  assert.equal(vm.runInContext('draft.rows[0].labels[0].text',restored.context),'客廳B');
});

test('輸出收到錯seq ACK拒絕且保留草稿，不使用舊資料開始渲染',async()=>{
  const env=environment(),get=id=>env.context.document.getElementById(id);
  const context={schema:JSON.parse(fs.readFileSync('frontend/content-schema.json','utf8')),photos:{p1:'hash',p2:'hash2'},assets:[],music:null,width:1080,engine:'renderer'};
  const project={photos:env.rows()},initial=StudioVersion.digest(StudioVersion.document(project,context));
  await env.receive({project,versions:{context,synced:initial}});get('addLabel').onclick();
  const pending=env.context.window.StudioOutputBridge.capture('mp4',1080).catch(error=>error),sent=env.changes()[0].value;
  get('text').value='不能遺失';get('text').oninput();
  await env.receive({project:{photos:env.rows().map((row,i)=>({...row,...sent.photos[i]}))},versions:{context,synced:sent.content_version},revision:2,
    response:{nonce:sent.nonce,operation_id:sent.nonce,ok:true,seq:sent.seq+1,content_version:sent.content_version},output_status:{id:sent.nonce,phase:'prepared'}});
  assert.ok((await pending).message.includes('確認不符'));
  assert.equal(env.changes().some(e=>e.value.action==='start_output'),false);
  assert.equal(vm.runInContext('draft.rows[0].labels[0].text',env.context),'不能遺失');
});

test('雙檔選項預設開啟、切換不改草稿seq與內容雜湊，重建後保留並傳入固定快照握手',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context);
  const context={schema:JSON.parse(fs.readFileSync('frontend/content-schema.json','utf8')),photos:{p1:'hash',p2:'hash2'},assets:[],music:null,width:1080,engine:'renderer'};
  const project={photos:env.rows()},initial=StudioVersion.digest(StudioVersion.document(project,context)),versions={context,synced:initial};
  await env.receive({project,versions});const bridge=env.context.window.StudioOutputBridge,seq=run('draft.seq'),version=run('draft.currentVersion()');
  assert.equal(bridge.status().zipBackup,true);bridge.setZipBackup(false);
  assert.equal(run('draft.seq'),seq);assert.equal(run('draft.currentVersion()'),version);
  const restored=environment(env.storage);await restored.receive({project,versions});assert.equal(restored.context.window.StudioOutputBridge.status().zipBackup,false);
  restored.context.window.StudioOutputBridge.capture('mp4',1080);assert.equal(restored.changes()[0].value.zip_backup,false);
});

function quickProject(env,follow=true){return {photos:env.rows(),cover_assets:{layout:require('../frontend/cover-layout.json')},cover:{enabled:true,title:'老屋超強收納',photo_id:'p1',color:'#ffffff',font_size:120,highlights:[],body:{...StudioBodyForQuick(),follow_cover:follow,title:follow?'老屋超強收納':'不同正文標題'}}};}
function StudioBodyForQuick(){return require('../frontend/body-editor.js').newBody();}

test('第六階段：快速入口／預覽與未修改欄位不增加seq，修改一次同步兩處且只改標題資料',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id),project=quickProject(env);
  await env.receive({project,ui_mode:'quick'});assert.equal(run('quickEditor.active'),true);const seq=run('draft.seq'),before=run('JSON.stringify(draft.rows)');
  get('qtBody').onclick();get('qtCover').onclick();get('qtCoverFont').value=120;get('qtCoverFont').oninput();get('qtCoverX').value=50;get('qtCoverX').oninput();
  assert.equal(run('draft.seq'),seq);assert.equal(run('draft.cover.shared_title'),undefined);
  get('qtTitle').value='18坪小宅超強收納';get('qtTitle').oninput();assert.equal(run('draft.cover.title'),'18坪小宅超強收納');assert.equal(run('draft.cover.body.title'),'18坪小宅超強收納');
  assert.equal(run('JSON.stringify(draft.rows)'),before);assert.equal(run('draft.cover.body.font_size'),100);assert.equal(env.changes().length,0);
});

test('第六階段：沒有明確關聯須確認固定ID，不以相同文字或一般標籤自動替換',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id),project=quickProject(env,false);
  await env.receive({project,ui_mode:'quick'});assert.equal(get('qtTitle').disabled,true);const seq=run('draft.seq');get('qtBody').onclick();assert.equal(run('draft.seq'),seq);
  get('qtTitleSource').value='body';get('qtConfirmLink').onclick();assert.equal(run('draft.cover.shared_title.cover_id'),'project-cover-title');assert.equal(run('draft.cover.title'),'不同正文標題');assert.equal(run('draft.cover.body.title'),'不同正文標題');
});

test('第六階段：分別反白換色／換行／字級／位置；畫布真正拖曳，無每次操作同步',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id);await env.receive({project:quickProject(env),ui_mode:'quick'});
  get('qtTitle').value='18坪小宅超強收納';get('qtTitle').oninput();get('qtTitle').selectionStart=5;get('qtTitle').selectionEnd=9;
  get('qtCoverHighlight').value='#ffff00';get('qtCoverApply').onclick();get('qtBodyHighlight').value='#00aaff';get('qtBodyApply').onclick();
  assert.equal(run('draft.cover.highlights[0].color'),'#ffff00');assert.equal(run('draft.cover.body.highlights[0].color'),'#00aaff');
  get('qtCoverWrap').value='18坪小宅\n超強收納';get('qtCoverWrap').oninput();assert.equal(run('draft.cover.body.title'),'18坪小宅超強收納');
  get('qtBodyFont').value=88;get('qtBodyFont').oninput();assert.equal(run('draft.cover.font_size'),120);
  const box=run('StudioTitle.coverBox(draft.cover)'),canvas=get('canvas');canvas.dispatch('pointerdown',{clientX:box.x+150,clientY:box.y+100});canvas.dispatch('pointermove',{clientX:box.x+190,clientY:box.y+130});canvas.dispatch('pointerup');
  assert.ok(run('draft.cover.shared_title.cover_x')>.5);assert.equal(run('draft.cover.body.x'),.5);assert.equal(env.changes().length,0);
  get('qtCoverX').value=0;get('qtCoverX').oninput();assert.match(get('qtCoverWarning').textContent,/超出/);
  // 播放與拖曳重繪共用同一文字圖，不在每一影格重新掃描像素。
  run("quickEditor.boundsCache=new WeakMap();var boundsCalls=0,priorBounds=StudioBody.alphaBounds;StudioBody.alphaBounds=(...args)=>{boundsCalls++;return priorBounds(...args);};var titleTile=coverEditor.tile();for(let i=0;i<30;i++)quickEditor.boundsWarning('cover',StudioTitle.coverBox(draft.cover),titleTile);StudioBody.alphaBounds=priorBounds;");
  assert.equal(run('boundsCalls'),1);
});

test('第六階段：原始比較只送唯讀影格請求、不能編輯，返回完整模式保留未同步修改',async()=>{
  const env=environment(),run=s=>vm.runInContext(s,env.context),get=id=>env.elements.get(id),project=quickProject(env);await env.receive({project,ui_mode:'quick'});
  get('qtTitle').value='快速修改完成';get('qtTitle').oninput();const seq=run('draft.seq');get('qtCompare').value='original';get('qtCompare').onchange();
  assert.equal(env.changes()[0].value.action,'quick_original');assert.equal(run('draft.seq'),seq);get('canvas').dispatch('keydown',{key:'ArrowLeft'});assert.equal(run('draft.seq'),seq);
  await env.receive({project,ui_mode:'quick',quick_frames:{'project-cover':{image:'original-frame',time:0,name:'原始封面'}}});assert.equal(run('quickEditor.image.src'),'original-frame');assert.equal(run('draft.cover.title'),'快速修改完成');
  get('qtFull').onclick();assert.equal(env.changes().at(-1).value.action,'set_edit_mode');await env.receive({project,ui_mode:'full'});
  assert.equal(run('quickEditor.active'),false);assert.equal(run('draft.cover.title'),'快速修改完成');assert.equal(run('draft.seq'),seq);
  assert.match(get('bodyFollowLabel').textContent,/樣式獨立/);
  get('bodyTitle').value='完整模式\n繼續修改';get('bodyTitle').oninput();
  assert.equal(run('draft.cover.shared_title.text'),'完整模式繼續修改');assert.equal(run('draft.cover.title'),'完整模式繼續修改');assert.equal(run('draft.cover.body.title'),'完整模式\n繼續修改');
});
