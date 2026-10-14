'use strict';
const $ = id => document.getElementById(id);
const W = 1080, H = 1920, ctx = $('canvas').getContext('2d');
let photos = [], selectedPhoto = null, selectedLabel = null, imageCache = new Map(), tileCache = new Map();
let assetMeta=new Map(),assetCache=new Map();
let editing = true, playing = false, time = 0, startClock = 0, raf = 0, dragging = null;
let showSafeArea=true,guideKind=null;
let recording = false, recorder = null, recordedURL = null, renderGeneration = 0;
const draft = new StudioDraft.DraftState(), storageKey='interior-studio-draft';
const waiters=new Map();
let photoDragId=null, editRaf=0, serverBusy=false, preparing=false;
let lastRevision=null, recordingFailure=null, activeExportRequest=null, receivedSession=null, storageFailed=false;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const isCompare=()=>draft.template==='compare';
const bodySequence=()=>isCompare()?draft.comparisons:photos;
const coverDuration=()=>photos.length?StudioCover.duration(draft.cover):0;
const coverScene=()=>({id:'project-cover',type:'cover',name:'片頭封面',duration:.5,labels:[],image:photos.find(p=>p.id===draft.cover?.photo_id)?.image});
const sequence=()=>coverDuration()?[coverScene(),...bodySequence()]:bodySequence();
const projectOverlays=()=>isCompare()?draft.comparisonOverlays:draft.overlays;
const photo = () => sequence().find(p => p.id === selectedPhoto) || sequence()[0];
const cropPhoto=()=>isCompare()?photo()?.[comparisonEditor.cropSide+'_crop']:photo();
const label = () => photo()?.labels.find(l => l.id === selectedLabel);
const total = () => sequence().reduce((sum, p) => sum + Number(p.duration), 0);
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
function post(type, extra = {}) { window.parent.postMessage({isStreamlitMessage:true, type, ...extra}, '*'); }
function resize() { post('streamlit:setFrameHeight', {height:Math.ceil(document.querySelector('.studio').getBoundingClientRect().height) + 8}); }
new ResizeObserver(resize).observe(document.querySelector('.studio'));
function metadata() { return photos.map(({image, tiles, ...row}) => row); }
function validProject() {
  const coverError=StudioCover.validate(draft.cover,photos);if(coverError){status(coverError,true);return false;}
  if (total() > 120) { status('影片總長最多 120 秒，請縮短照片秒數。', true); return false; }
  const comparisonError=StudioComparison.validate(draft.comparisons,photos);
  if(comparisonError){status(comparisonError,true);return false;}
  for (const p of [...photos,...draft.comparisons]) {
    if (!Number.isFinite(p.duration) || p.duration < 1 || p.duration > 20) {status('每張照片需為 1～20 秒。', true); return false;}
    for (const l of p.labels) {
      if (!l.text.trim() || l.text.length > 80 || !Number.isFinite(l.start) || !Number.isFinite(l.end) || !Number.isFinite(l.enter) ||
          l.start < 0 || l.end > p.duration || (l.end <= l.start && !(l.comparison_side==='before'&&l.auto_timing&&l.start===0&&l.end===0&&l.enter===0)) || l.enter < 0 || l.enter > 3 || l.enter > l.end-l.start ||
          !Number.isInteger(l.layer??10)||(l.layer??10)<0||(l.layer??10)>1000) {
        status('請確認標籤文字，以及出現／消失時間與進場時長。', true); return false;
      }
    }
  }
  if(projectOverlays().length>32){status('全片最多32個PNG圖層。',true);return false;}
  for(const o of projectOverlays()){
    if(!assetMeta.has(o.source)||o.duration<1/30-1e-8||o.start<0||o.start+o.duration>total()+1e-7||o.enter+o.exit>o.duration+1e-7){
      status('請確認PNG素材、開始與結束時間及進出場時長。',true);return false;}
  }
  return true;
}
function persistDraft() {
  if(!draft.session)return;
  try {sessionStorage.setItem(storageKey,JSON.stringify(draft.persisted({selectedPhoto,selectedLabel,selectedOverlay:pngEditor.selected,time,showSafeArea})));storageFailed=false;}
  catch(error){storageFailed=true;status('此瀏覽器無法暫存草稿；請在離開此頁前套用變更。',true);}
}
window.addEventListener('pagehide',persistDraft);
function syncStatus() {
  if(serverBusy)status('正在輸出已套用的影片設定…');
  else if(preparing)status('輸出前正在套用最新設定…');
  else if(draft.pending)status('正在套用變更，可繼續編輯…');
  else status(draft.dirty?'有未套用變更；切換照片會保留，輸出前會自動套用。':'已套用變更，預覽已與輸出設定對齊。');
  if(storageFailed){$('status').textContent+=' 此瀏覽器無法暫存草稿，離開前請先套用。';$('status').classList.add('error');}
  $('applyChanges').disabled=!!draft.pending||recording||preparing||serverBusy;
}
function markEdited(persist=true) {
  const priorPhoto=selectedPhoto;
  draft.touch(photos);clearBrowserResult();
  comparisonEditor.prune();
  StudioCover.ensureSource(draft.cover,photos);
  StudioTimeline.clampOverlays(draft.overlays,StudioTimeline.total(photos)+coverDuration());
  StudioTimeline.clampOverlays(draft.comparisonOverlays,StudioTimeline.total(draft.comparisons)+coverDuration());
  if(!sequence().some(p=>p.id===selectedPhoto)){selectedPhoto=sequence()[0]?.id;selectedLabel=photo()?.labels[0]?.id;}
  time=clamp(time,0,Math.max(0,total()-1/30));
  const active=pngEditor.item();
  if(editing&&active&&!pngEditor.active(active)){time=active.start;selectedPhoto=locate(time).photo?.id;}
  else if(editing&&!active&&photo())time=clamp(time,photoOffset(photo().id),photoOffset(photo().id)+photo().duration-1/30);
  if(selectedPhoto!==priorPhoto){selectedLabel=photo()?.labels[0]?.id;buildLabels();buildPhotos();}
  if(persist)persistDraft();
  syncStatus();timeline.draw();
}
function queueDraw(){if(!editRaf)editRaf=requestAnimationFrame(()=>{editRaf=0;info();draw();});}
function synchronize(action='apply',request=null) {
  if(!validProject())return Promise.reject(new Error('請先修正標籤文字與時間設定。'));
  if(draft.pending)return Promise.reject(new Error('正在套用上一批變更，請稍候再試。'));
  const event=draft.snapshot(crypto.randomUUID(),action,request);persistDraft();syncStatus();
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{
      waiters.delete(event.nonce);
      if(draft.pending?.nonce===event.nonce){draft.pending=null;draft.dirty=true;persistDraft();syncStatus();}
      reject(new Error('同步逾時，草稿已保留；請再次按「套用變更」。'));
    },20000);
    waiters.set(event.nonce,{resolve,reject,timer});
    post('streamlit:setComponentValue',{value:event,dataType:'json'});
  });
}
async function ensureSynced(){
  while(draft.dirty||draft.pending) {
    if(draft.pending)throw new Error('正在套用上一批變更，請稍候再輸出。');
    await synchronize();
  }
}
function loadImage(src) {
  return new Promise((resolve, reject) => {const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('圖片載入失敗，請重新上傳。')); image.src = src;});
}
window.addEventListener('message', async event => {
  if (event.source !== window.parent || event.data?.type !== 'streamlit:render') return;
  const args = event.data.args;
  const generation = ++renderGeneration;
  try {
    const rows = args.project.photos;
    StudioCover.configure(args.project.cover_assets?.layout);
    StudioSafeArea.configure(args.project.safe_area);StudioSafeArea.mount($('safeAreaGuide'));
    guideKind=null;
    if(receivedSession!==args.session) {
      try {const saved=JSON.parse(sessionStorage.getItem(storageKey)||'null');
        if(draft.restore(saved,args.session)){
          selectedPhoto=saved.selection?.selectedPhoto;selectedLabel=saved.selection?.selectedLabel;
          pngEditor.selected=saved.selection?.selectedOverlay||null;time=saved.selection?.time||0;
          showSafeArea=saved.selection?.showSafeArea??true;$('showSafeArea').checked=showSafeArea;
          if(draft.pending&&args.response?.nonce!==draft.pending.nonce){draft.pending=null;draft.dirty=true;}
        }
      }catch(error){sessionStorage.removeItem(storageKey);}
      receivedSession=args.session;
    }
    const templateChanged=draft.template!==(args.project.template_id||'items');
    const legacyCover=draft.session===args.session&&draft.cover===null&&(draft.dirty||draft.pending);
    const result=draft.receive(rows,args.session,args.revision,args.response,args.project.overlays||[],
                              args.project.comparisons||[],args.project.comparison_overlays||[],args.project.cover||null);
    if(result.stale)return;
    photos=draft.rows;
    draft.template=args.project.template_id||'items';
    if(legacyCover&&draft.cover?.enabled){for(const slot of [draft.overlays,draft.comparisonOverlays])for(const o of slot)o.start+=.5;time+=.5;draft.touch(photos);}
    if(StudioCover.ensureSource(draft.cover,photos))draft.touch(photos);
    comparisonEditor.prune();
    // 舊工作階段的標題只升級一次；沿用草稿同步，避免覆蓋未套用的人工內容。
    let upgraded=false;for(const c of draft.comparisons)if(StudioComparison.upgradeTitles(c))upgraded=true;
    if(upgraded)draft.touch(photos);
    if(templateChanged){stopPlayback();editing=true;time=0;selectedPhoto=sequence()[0]?.id;selectedLabel=photo()?.labels[0]?.id;pngEditor.selected=null;comparisonEditor.view='combined';}
    const images = new Map(), tiles = new Map();
    await Promise.all(rows.map(async p => {
      images.set(p.id, imageCache.get(p.id)?.src === p.image ? imageCache.get(p.id) : await loadImage(p.image));
      for (const [id, data] of Object.entries(p.tiles)) {
        const current = tileCache.get(id), key=StudioLabel.key(data.style);
        tiles.set(id, current?.src===data.src?current:{image:await loadImage(data.src),key,src:data.src});
      }
    }));
    for(const p of args.project.comparisons||[])for(const [id,data] of Object.entries(p.tiles||{})){
      const current=tileCache.get(id),key=StudioLabel.key(data.style);
      tiles.set(id,current?.src===data.src?current:{image:await loadImage(data.src),key,src:data.src});
    }
    const assets=args.project.assets||[],pngImages=new Map();
    const coverAssets=args.project.cover_assets||{};
    const coverTemplate=coverAssets.template?(coverEditor.template?.src===coverAssets.template?coverEditor.template:await loadImage(coverAssets.template)):null;
    const coverTitle=coverAssets.title?(coverEditor.calibrated?.image.src===coverAssets.title?coverEditor.calibrated.image:await loadImage(coverAssets.title)):null;
    await Promise.all(assets.map(async asset=>pngImages.set(asset.id,assetCache.get(asset.id)||await loadImage(asset.image))));
    if (generation !== renderGeneration) return;
    imageCache = images; tileCache = tiles;
    coverEditor.template=coverTemplate;coverEditor.calibrated=coverTitle?{image:coverTitle,key:StudioCover.key(args.project.cover)}:null;
    assetMeta=new Map(assets.map(asset=>[asset.id,asset]));assetCache=pngImages;
    if(lastRevision!==null && args.revision!==lastRevision) {
      clearBrowserResult();
      if(recording && recorder?.state==='recording') {recordingFailure='錄製期間專案內容改變，請重新錄製。';recorder.stop();}
    }
    lastRevision=args.revision;
    serverBusy=!!args.busy;
    photos=draft.rows;
    if(!recording&&!preparing&&!serverBusy&&!draft.pending) {
      const imported=StudioAI.importBatches(draft,args.ai_imports,imageCache,StudioPhoto.layout,()=>crypto.randomUUID());
      if(imported.added){markEdited();editing=true;stopPlayback();}
      if(imported.messages.length)$('aiStatus').textContent=imported.messages.join(' ');
    }
    if (!sequence().some(p => p.id === selectedPhoto)) selectedPhoto = sequence()[0]?.id;
    if (!photo()?.labels.some(l => l.id === selectedLabel)) selectedLabel = photo()?.labels[0]?.id;
    time=clamp(time,0,Math.max(0,total()-1/30));
    pngEditor.library();comparisonEditor.library();buildPhotos(); buildLabels(); fillForm(); draw(); support();
    lockEditor(recording||preparing||serverBusy);if(!recording&&!preparing)syncStatus();
    persistDraft();resize();
    if(result.matched) {
      const waiter=waiters.get(args.response.nonce);
      if(waiter){clearTimeout(waiter.timer);waiters.delete(args.response.nonce);
        if(result.success)waiter.resolve();else waiter.reject(new Error(result.error));}
      if(result.error)status(result.error+' 草稿仍保留在此頁。',true);
    }
    if(args.export_request&&args.export_request!==activeExportRequest&&!draft.pending) {
      activeExportRequest=args.export_request;preparing=true;lockEditor(true);
      synchronize('export',args.export_request).catch(error=>{
        status(error.message,true);
        post('streamlit:setComponentValue',{value:{nonce:crypto.randomUUID(),session:draft.session,
          action:'cancel_export',request:args.export_request},dataType:'json'});
      })
        .finally(()=>{preparing=false;lockEditor(serverBusy||recording);});
    }
  } catch (error) { status(error.message, true); }
});
function button(text, fn, className = '') {
  const element = document.createElement('button'); element.textContent = text; element.className = className; element.onclick = fn; return element;
}
function buildPhotos() {
  $('photos').replaceChildren();
  if(coverDuration())$('photos').append(button('封面 · 0.5秒',()=>selectMaterial({type:'cover',source:'project-cover',id:'project-cover',start:0}),'photo'+(selectedPhoto==='project-cover'?' active':'')));
  const active=bodySequence();active.forEach((p, index) => {
    const item = button('', () => selectMaterial({type:'photo',id:p.id,source:p.id,start:photoOffset(p.id)}), 'photo' + (p.id === selectedPhoto ? ' active' : ''));
    item.draggable = true; item.dataset.photoId = p.id; item.title = p.name;
    const img = document.createElement('img'); img.src = p.image||photos.find(row=>row.id===p.after_id)?.image||''; img.alt = p.name;
    const caption = document.createElement('span'); caption.textContent = `${index+1} · ${p.duration}s · ${p.name}`;
    item.append(img, caption);
    item.ondragstart = e => {if(recording||preparing||serverBusy){e.preventDefault();return;} photoDragId=p.id; e.dataTransfer.setData('text/plain',p.id);};
    item.ondragover = e => {e.preventDefault(); item.classList.add('drag-over');};
    item.ondragleave = () => item.classList.remove('drag-over');
    item.ondrop = e => {
      e.preventDefault(); item.classList.remove('drag-over');
      const source = active.findIndex(row => row.id === photoDragId), target = active.findIndex(row => row.id === p.id);
      if (source < 0 || target < 0 || recording||preparing||serverBusy) return;
      const [moved] = active.splice(source,1); active.splice(target,0,moved);
      stopPlayback(); editing=true; buildPhotos(); markEdited();
    };
    $('photos').append(item);
  });
  $('total').textContent = `${active.length} ${isCompare()?'組對比':'張'} · ${total().toFixed(1)} 秒`;
  $('seek').max = Math.max(0, total() - 1/30);
}
function buildLabels() {
  $('labels').replaceChildren();
  const p=photo(); if(!p)return;
  if (!p.labels.length) $('labels').textContent = p.type==='cover'?'封面標題使用上方設定。':'尚無標籤，先新增一個裝修項目。';
  p.labels.forEach(l => $('labels').append(button(l.text, () => {
    pngEditor.selected=null;selectedLabel=l.id;
    if(isCompare()&&l.comparison_side){stopPlayback();editing=true;comparisonEditor.view='combined';
      time=photoOffset(p.id)+(l.comparison_side==='before'?0:p.before_time);}
    persistDraft();buildLabels(); fillForm(); draw();}, l.id===selectedLabel?'active':'')));
  $('labelForm').hidden = !label();
  $('addLabel').disabled = p.type==='cover'||p.labels.length >= 12 || recording||preparing||serverBusy;
}
const labelFields = ['text','font_size','color','background','opacity','radius','line','animation','start','end','enter','layer'];
function fillForm() {
  coverEditor.refresh();
  comparisonEditor.refresh();
  $('deletePhoto').textContent=isCompare()?'刪除對比片段':'刪除照片';
  $('edit').textContent=isCompare()?'編輯對比片段':'編輯目前照片';
  for(const key of ['duration','fit','zoom','crop_x','crop_y','moveLeft','moveRight','deletePhoto','addLabel'])$(key).disabled=!photo()||photo().type==='cover'||recording||preparing||serverBusy;
  const p=photo(); if(!p){$('labelForm').hidden=true;$('overlayForm').hidden=true;return;}
  if(p.type==='cover'){$('labelForm').hidden=true;$('duration').value=.5;$('photoNumber').textContent='片頭封面';$('edit').textContent='編輯封面';pngEditor.refresh();return;}
  if(document.activeElement!==$('duration'))$('duration').value=p.duration; $('photoNumber').textContent=`${sequence().findIndex(row=>row.id===p.id)+1} / ${sequence().length}`;
  for (const key of ['zoom','crop_x','crop_y']) $(key).value=cropPhoto()[key];
  $('fit').value=cropPhoto().fit || 'contain';
  for (const key of ['zoom','crop_x','crop_y']) $(key).disabled=recording || $('fit').value==='contain';
  const l=label(); $('labelForm').hidden=!l;
  if(l) {
    l.layer??=10;
    for(const key of labelFields) {if(document.activeElement===$(key))continue;if(key==='line')$(key).checked=l[key];else $(key).value=l[key];}
    $('start').max=p.duration; $('end').max=p.duration;
    info();
  }
  pngEditor.refresh();
}
function info() {
  const l=label(); if(!l)return;
  $('hold').textContent=`停留時間 ${Math.max(0,l.end-l.start-l.enter).toFixed(1)} 秒；時間以此張照片開始為基準`;
  $('position').textContent=`標籤 ${l.x.toFixed(2)}, ${l.y.toFixed(2)} · 定位點 ${l.point_x.toFixed(2)}, ${l.point_y.toFixed(2)}`;
}
function locate(t) {
  let offset=0;
  const rows=sequence();for(let i=0;i<rows.length;i++) {if(t<offset+rows[i].duration || i===rows.length-1)return {photo:rows[i],local:t-offset}; offset+=rows[i].duration;}
  return {photo:null,local:0};
}
function tileFor(l) {
  const key=StudioLabel.key(l), current=tileCache.get(l.id);
  if(current?.key===key)return current.image;
  const image=StudioLabel.raster(l,()=>document.createElement('canvas'));
  tileCache.set(l.id,{image,key});return image;
}
function bounds(l) {
  const tile=tileFor(l), width=tile.naturalWidth || tile.width, height=tile.naturalHeight || tile.height;
  return {width,height,x:Math.min(l.x*W,W-width),y:Math.min(l.y*H,H-height)};
}
function visibleEditLabel(p,l){return !isCompare()||StudioComparison.visibleTitle(p,l,time-photoOffset(p.id),comparisonEditor.view);}
function updateSafeArea(){
  const current=editing?photo():locate(time).photo;
  const kind=current?.type==='cover'?'cover':'body';
  if(kind!==guideKind){if(kind==='cover')StudioCover.mountGuide($('safeAreaGuide'));else StudioSafeArea.mount($('safeAreaGuide'));guideKind=kind;}
  $('safeAreaGuide').hidden=!showSafeArea||recording;
}
$('showSafeArea').onchange=()=>{showSafeArea=$('showSafeArea').checked;updateSafeArea();persistDraft();};
function draw() {
  updateSafeArea();
  const state=editing?{photo:photo(),local:time-photoOffset(photo()?.id)}:locate(time), p=state.photo;
  ctx.fillStyle='#000000';ctx.fillRect(0,0,W,H); if(!p){$('clock').textContent='0.0 / 0.0 s';$('seek').value=0;timeline.draw();return;}
  const image=imageCache.get(p.id);
  if(p.type==='cover')coverEditor.draw(ctx);
  else if(isCompare())comparisonEditor.draw(ctx,p,state.local,editing);
  else if(image) {
    const box=StudioPhoto.layout(image.naturalWidth,image.naturalHeight,W,H,p);
    ctx.drawImage(image,box.sx,box.sy,box.sw,box.sh,box.dx,box.dy,box.dw,box.dh);
  }
  const materials=p.labels.map((l,index)=>({layer:l.layer??10,index,label:l})).concat(projectOverlays().map((o,index)=>({layer:o.layer,index:p.labels.length+index,overlay:o})));
  for(const item of materials.sort((a,b)=>a.layer-b.layer||a.index-b.index)) {
    if(item.overlay){pngEditor.draw(ctx,item.overlay,time,editing);continue;}
    const l=item.label;
    if(editing&&!visibleEditLabel(p,l))continue;
    const position=editing?{x:0,y:0,scale:1,alpha:1}:StudioAnimation.pose(l,state.local);
    if(!position)continue;
    const b=bounds(l), x=b.x+position.x*W,y=b.y+position.y*H,tile=tileFor(l);
    ctx.save();ctx.globalAlpha=position.alpha;
    if(l.line) {
      ctx.strokeStyle='rgba(255,255,255,.824)';ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(x+b.width/2,y+b.height/2);ctx.lineTo(l.point_x*W,l.point_y*H);ctx.stroke();
      ctx.fillStyle='white';ctx.beginPath();ctx.arc(l.point_x*W,l.point_y*H,10,0,Math.PI*2);ctx.fill();
    }
    if(tile)ctx.drawImage(tile,x+b.width*(1-position.scale)/2,y+b.height*(1-position.scale)/2,b.width*position.scale,b.height*position.scale);
    else {ctx.fillStyle=l.background;ctx.fillRect(x,y,b.width,b.height);ctx.fillStyle=l.color;ctx.font=`${l.font_size}px sans-serif`;ctx.fillText(l.text,x+24,y+70);}
    ctx.restore();
    if(editing&&l.id===selectedLabel&&!l.comparison_side) {
      ctx.save();ctx.strokeStyle='#eac181';ctx.lineWidth=5;ctx.setLineDash([12,8]);ctx.strokeRect(b.x-6,b.y-6,b.width+12,b.height+12);ctx.setLineDash([]);
      ctx.beginPath();ctx.arc(l.point_x*W,l.point_y*H,25,0,Math.PI*2);ctx.stroke();ctx.restore();
    }
  }
  $('mode').textContent=editing?'構圖與標籤編輯':'動畫預覽'; $('clock').textContent=`${time.toFixed(1)} / ${total().toFixed(1)} s`;
  $('seek').value=time;
  timeline.draw();
}
function coords(e) {const r=$('canvas').getBoundingClientRect();return {x:(e.clientX-r.left)*W/r.width,y:(e.clientY-r.top)*H/r.height};}
$('canvas').addEventListener('pointerdown',e=>{
  if(!editing||recording||preparing||serverBusy)return;
  const xy=coords(e),p=photo();if(!p)return;
  const visible=p.labels.filter(l=>visibleEditLabel(p,l));
  const hitLayer=Math.max(-1,...visible.filter(l=>{const b=bounds(l);return (!l.comparison_side&&Math.hypot(xy.x-l.point_x*W,xy.y-l.point_y*H)<42)||(xy.x>=b.x&&xy.x<=b.x+b.width&&xy.y>=b.y&&xy.y<=b.y+b.height);}).map(l=>l.layer??10));
  if(pngEditor.down(xy,hitLayer)){e.preventDefault();dragging={type:'png'};$('canvas').setPointerCapture(e.pointerId);draw();return;}
  if(hitLayer<0&&comparisonEditor.dividerDown(xy)){e.preventDefault();dragging={type:'divider'};$('canvas').setPointerCapture(e.pointerId);return;}
  // 優先選取目前標籤的定位點，避免與其他文字碰撞時難以拖曳。
  const ordered=[...visible].reverse().sort((a,b)=>Number(b.id===selectedLabel)-Number(a.id===selectedLabel));
  for(const l of ordered) {
    const b=bounds(l);
    if(!l.comparison_side&&Math.hypot(xy.x-l.point_x*W,xy.y-l.point_y*H)<42) {dragging={type:'point',id:l.id,dx:0,dy:0};break;}
    if(xy.x>=b.x&&xy.x<=b.x+b.width&&xy.y>=b.y&&xy.y<=b.y+b.height) {dragging={type:'label',id:l.id,dx:xy.x-b.x,dy:xy.y-b.y};break;}
  }
  if(dragging) {e.preventDefault();pngEditor.selected=null;selectedLabel=dragging.id;$('canvas').setPointerCapture(e.pointerId);buildLabels();fillForm();draw();}
});
$('canvas').addEventListener('pointermove',e=>{
  if(!dragging||recording||preparing||serverBusy)return;const xy=coords(e);
  if(dragging.type==='png'){pngEditor.move(xy);markEdited(false);queueDraw();return;}
  if(dragging.type==='divider'){photo().split=clamp(xy.x/W,.1,.9);comparisonEditor.refresh();markEdited(false);queueDraw();return;}
  const l=label();if(!l)return;
  if(dragging.type==='point') {l.point_x=clamp(xy.x/W,0,1);l.point_y=clamp(xy.y/H,0,1);}
  else {const b=bounds(l);l.x=clamp(xy.x-dragging.dx,0,W-b.width)/W;l.y=clamp(xy.y-dragging.dy,0,H-b.height)/H;}
  if(l.comparison_side)StudioComparison.alignTitles(photo(),l);
  markEdited(false);queueDraw();
});
function finishDrag(){if(dragging){dragging=null;pngEditor.drag=null;persistDraft();}}
$('canvas').addEventListener('pointerup',finishDrag);$('canvas').addEventListener('pointercancel',finishDrag);
$('canvas').addEventListener('keydown',e=>{
  if(editing&&!recording&&!preparing&&!serverBusy&&pngEditor.item()){
    if(e.key==='Delete'){e.preventDefault();pngEditor.remove();return;}
    if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();const o=pngEditor.item(),step=e.shiftKey?30:6;
      o.x+=((e.key==='ArrowLeft'?-step:e.key==='ArrowRight'?step:0)/W);o.y+=((e.key==='ArrowUp'?-step:e.key==='ArrowDown'?step:0)/H);pngEditor.clampPosition(o);pngEditor.refresh();draw();markEdited();return;}
  }
  const l=label();if(!editing||recording||preparing||serverBusy||!l||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
  e.preventDefault();const step=e.shiftKey?30:6,b=bounds(l);
  l.x=clamp(b.x+(e.key==='ArrowLeft'?-step:e.key==='ArrowRight'?step:0),0,W-b.width)/W;
  l.y=clamp(b.y+(e.key==='ArrowUp'?-step:e.key==='ArrowDown'?step:0),0,H-b.height)/H;
  if(l.comparison_side)StudioComparison.alignTitles(photo(),l);
  draw();info();markEdited();
});
function stopPlayback(){playing=false;cancelAnimationFrame(raf);$('play').textContent='▶ 預覽影片';}
function tick(now) {
  time=(now-startClock)/1000;
  if(time>=total()) {time=Math.max(0,total()-1/30);draw();stopPlayback();if(recording&&recorder?.state==='recording')recorder.stop();return;}
  draw();if(recording)$('recordProgress').value=time/total();
  raf=requestAnimationFrame(tick);
}
$('play').onclick=()=>{if(recording)return;if(playing){stopPlayback();return;}editing=false;playing=true;if(time>=total()-1/30)time=0;startClock=performance.now()-time*1000;$('play').textContent='❚❚ 暫停';raf=requestAnimationFrame(tick);};
$('edit').onclick=()=>{if(recording)return;stopPlayback();const p=locate(time).photo;if(p){selectedPhoto=p.id;selectedLabel=p.labels[0]?.id;}editing=true;buildPhotos();buildLabels();fillForm();draw();};
$('seek').oninput=()=>seekTime(Number($('seek').value));
$('duration').onchange=()=>{
  const p=photo(),value=Number($('duration').value);if(p?.type==='cover')return; if(value<1||value>20||!Number.isFinite(value)){status('每張照片需為 1～20 秒。',true);return;}
  StudioTimeline.photoDuration(p,value);
  buildPhotos();fillForm();markEdited();
};
$('duration').oninput=()=>{
  clearBrowserResult();
  const p=photo(),value=Number($('duration').value);
  if(p?.type==='cover')return;
  if(value<1||value>20||!Number.isFinite(value)){status('每張照片需為 1～20 秒。',true);return;}
  StudioTimeline.photoDuration(p,value);
  buildPhotos();markEdited();
};
$('fit').onchange=()=>{if(!cropPhoto())return;cropPhoto().fit=$('fit').value;editing=true;stopPlayback();fillForm();draw();markEdited();};
for(const key of ['zoom','crop_x','crop_y']) {
  $(key).oninput=()=>{if(!cropPhoto())return;cropPhoto()[key]=Number($(key).value);editing=true;stopPlayback();draw();markEdited();};
  $(key).onchange=()=>persistDraft();
}
for(const key of labelFields) {
  $(key).oninput=()=> {
    const l=label();if(!l)return;
    l[key]=key==='line'?$(key).checked:['text','color','background','animation'].includes(key)?$(key).value:Number($(key).value);
    if(['start','end','enter'].includes(key)&&l.comparison_side){l.auto_timing=false;l.exit=Math.min(l.exit||0,Math.max(0,l.end-l.start));}
    buildLabels();editing=true;stopPlayback();info();draw();markEdited();
  };
  $(key).onchange=()=> {
    const l=label();if(!l)return;
    l[key]=key==='line'?$(key).checked:['text','color','background','animation'].includes(key)?$(key).value:Number($(key).value);
    if(['start','end','enter'].includes(key)&&l.comparison_side){l.auto_timing=false;l.exit=Math.min(l.exit||0,Math.max(0,l.end-l.start));}
    buildLabels();info();draw();markEdited();
  };
}
$('addLabel').onclick=()=>{
  const p=photo();if(!p||p.type==='cover'||p.labels.length>=12)return;
  pngEditor.selected=null;
  const l={id:crypto.randomUUID(),text:'裝修項目',x:.12,y:.28,point_x:.58,point_y:.52,font_size:46,color:'#ffffff',background:'#222822',opacity:.88,radius:18,line:true,animation:'left',start:0,enter:.6,end:p.duration};
  p.labels.push(l);selectedLabel=l.id;editing=true;stopPlayback();buildLabels();fillForm();draw();markEdited();
};
$('deleteLabel').onclick=()=>{const p=photo();p.labels=p.labels.filter(l=>l.id!==selectedLabel);tileCache.delete(selectedLabel);selectedLabel=p.labels[0]?.id;buildLabels();fillForm();draw();markEdited();};
$('deletePhoto').onclick=()=>{if(isCompare()){const i=draft.comparisons.findIndex(c=>c.id===selectedPhoto);if(i>=0)draft.comparisons.splice(i,1);}
  else{draft.deleted.push(selectedPhoto);photos=photos.filter(p=>p.id!==selectedPhoto);}
  selectedPhoto=sequence()[0]?.id;selectedLabel=photo()?.labels[0]?.id;markEdited();buildPhotos();buildLabels();fillForm();draw();comparisonEditor.library();};
$('applyChanges').onclick=()=>synchronize().catch(error=>status(error.message,true));
function movePhoto(delta) {
  const rows=bodySequence(),index=rows.findIndex(p=>p.id===selectedPhoto),next=index+delta;if(index<0||next<0||next>=rows.length)return;
  [rows[index],rows[next]]=[rows[next],rows[index]];buildPhotos();markEdited();
}
$('moveLeft').onclick=()=>movePhoto(-1);$('moveRight').onclick=()=>movePhoto(1);
function supportedMime() {
  if(!window.MediaRecorder||!$('canvas').captureStream)return null;
  return ['video/mp4;codecs=avc1.42E028','video/mp4;codecs=avc1'].find(m=>MediaRecorder.isTypeSupported(m))||null;
}
function support() {
  const mime=supportedMime();$('browserExport').disabled=!mime||!!draft.pending||serverBusy||preparing;
  $('support').textContent=mime?'本機錄製，請保持頁面前景':'此瀏覽器未提供 H.264 MP4，請使用下方 FFmpeg 輸出';
}
function clearBrowserResult() {
  if(recordedURL){URL.revokeObjectURL(recordedURL);recordedURL=null;}
  $('browserResult').hidden=true;$('browserVideo').removeAttribute('src');
}
function lockEditor(locked) {
  if(locked&&dragging){dragging=null;persistDraft();}
  for(const element of document.querySelectorAll('button,input,select,textarea'))element.disabled=locked;
  if(!locked){support();buildLabels();fillForm();$('applyChanges').disabled=!!draft.pending;}
}
$('browserExport').onclick=async()=>{
  if(!bodySequence().length){status('請先加入照片或新增一組前後配對。',true);return;}
  if(!validProject()||draft.pending||serverBusy||preparing)return;
  const mime=supportedMime();if(!mime){status('此瀏覽器不支援 H.264 MP4，請使用 FFmpeg。',true);return;}
  preparing=true;lockEditor(true);
  try{await ensureSynced();}catch(error){preparing=false;lockEditor(false);status(error.message,true);return;}
  preparing=false;
  clearBrowserResult();stopPlayback();recording=true;editing=false;time=0;draw();lockEditor(true);
  $('recordProgress').hidden=false;$('recordProgress').value=0;
  let stream, visibility=null, timer=null;
  recordingFailure=null;
  try {
    stream=$('canvas').captureStream(30);
    recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:8_000_000});
    const chunks=[];
    recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
    const done=new Promise((resolve,reject)=>{recorder.onstop=resolve;recorder.onerror=e=>reject(new Error(e.error?.message||'瀏覽器編碼失敗。'));});
    visibility=()=>{if(document.hidden&&recorder.state==='recording'){recordingFailure='頁面進入背景，錄製已停止。請保持前景重試，或使用 FFmpeg。';recorder.stop();}};
    document.addEventListener('visibilitychange',visibility);
    recorder.start(1000);status('正在本機錄製；需等待影片實際長度，請保持此頁前景。');
    timer=setTimeout(()=>{if(recorder.state==='recording'){recordingFailure='瀏覽器錄製逾時，請使用 FFmpeg。';recorder.stop();}},(total()+15)*1000);
    playing=true;startClock=performance.now();raf=requestAnimationFrame(tick);
    await done;
    if(recordingFailure)throw new Error(recordingFailure);
    const blob=new Blob(chunks,{type:recorder.mimeType});
    if(blob.size<1000||!blob.type.includes('mp4'))throw new Error('瀏覽器沒有產生有效 MP4，請使用 FFmpeg。');
    recordedURL=URL.createObjectURL(blob);$('browserDownload').href=recordedURL;$('browserVideo').src=recordedURL;$('browserResult').hidden=false;
    $('recordProgress').value=1;status('瀏覽器 MP4 已完成，可播放與下載；需要固定 30 FPS 時請使用 FFmpeg。');
  }catch(error){status(`${error.message} 可使用下方免費 FFmpeg 輸出。`,true);}
  finally{clearTimeout(timer);if(visibility)document.removeEventListener('visibilitychange',visibility);recording=false;stopPlayback();if(recorder?.state==='recording')recorder.stop();stream?.getTracks().forEach(track=>track.stop());lockEditor(false);resize();}
};
function photoOffset(id){let t=0;for(const p of sequence()){if(p.id===id)return t;t+=p.duration;}return 0;}
function seekTime(value,edit=false){if(recording||preparing||serverBusy)return;stopPlayback();time=clamp(StudioTimeline.snap(value),0,Math.max(0,total()-1/30));editing=edit;
  const p=locate(time).photo;if(p&&p.id!==selectedPhoto){selectedPhoto=p.id;selectedLabel=p.labels[0]?.id;buildPhotos();buildLabels();fillForm();}draw();persistDraft();}
function selectMaterial(item){if(recording||preparing||serverBusy)return;stopPlayback();editing=true;
  if(item.type==='png'){pngEditor.selected=item.id;selectedLabel=null;seekTime(item.start,true);}
  else {pngEditor.selected=null;selectedPhoto=item.source;selectedLabel=item.type==='label'?item.id:photo()?.labels[0]?.id;time=item.start;}
  buildPhotos();buildLabels();fillForm();draw();persistDraft();}
const comparisonEditor=new StudioComparisonUI.ComparisonEditor({photos:()=>photos,clips:()=>draft.comparisons,current:()=>photo()?.type==='cover'?null:photo(),
  active:isCompare,images:()=>imageCache,locked:()=>recording||preparing||serverBusy,status,
  choose:id=>{if(id)selectMaterial({id,source:id,type:'comparison',start:photoOffset(id)});},
  removeSource:id=>{draft.deleted.push(id);const i=photos.findIndex(p=>p.id===id);if(i>=0)photos.splice(i,1);},
  refresh:()=>{editing=true;stopPlayback();fillForm();draw();},
  change:()=>{editing=true;stopPlayback();markEdited();buildPhotos();buildLabels();fillForm();draw();}});
const pngEditor=new StudioPNG.PNGEditor({overlays:projectOverlays,assets:()=>assetMeta,images:()=>assetCache,
  locked:()=>recording||preparing||serverBusy,total,time:()=>time,status,
  select:o=>selectMaterial(o),changed:()=>{editing=true;stopPlayback();markEdited();fillForm();draw();}});
const coverEditor=new StudioCover.CoverEditor({cover:()=>draft.cover,photos:()=>photos,images:()=>imageCache,slots:()=>[draft.overlays,draft.comparisonOverlays],
  viewing:()=>photo()?.type==='cover',
  locked:()=>recording||preparing||serverBusy,status,choose:()=>selectMaterial({type:'cover',id:'project-cover',source:'project-cover',start:0}),
  change:()=>{stopPlayback();editing=true;selectedPhoto=coverDuration()?'project-cover':bodySequence()[0]?.id;selectedLabel=photo()?.labels[0]?.id;pngEditor.selected=null;time=0;markEdited();buildPhotos();buildLabels();fillForm();draw();}});
const timeline=new StudioTimelineUI.TimelineUI($('timelineCanvas'),{photos:bodySequence,offset:coverDuration,overlays:projectOverlays,time:()=>time,
  locked:()=>recording||preparing||serverBusy,seek:seekTime,select:selectMaterial,
  selected:item=>item.type==='png'?item.id===pngEditor.selected:item.type==='label'?item.id===selectedLabel:item.id===selectedPhoto,
  change:persist=>{stopPlayback();editing=true;markEdited(persist);buildPhotos();fillForm();draw();}});
$('timelineZoom').oninput=()=>{timeline.zoom=Number($('timelineZoom').value);timeline.draw();};
function stack(front){if(recording||preparing||serverBusy)return;const selected=pngEditor.item()||label();if(!selected)return;
  const all=[...sequence().flatMap(p=>p.labels),...projectOverlays()].sort((a,b)=>(a.layer??10)-(b.layer??10));
  const order=all.filter(o=>o!==selected);if(front)order.push(selected);else order.unshift(selected);
  order.forEach((o,i)=>o.layer=i);markEdited();fillForm();draw();}
$('bringFront').onclick=()=>stack(true);$('sendBack').onclick=()=>stack(false);
post('streamlit:componentReady',{apiVersion:1});resize();
