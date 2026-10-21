'use strict';
const $ = id => document.getElementById(id);
const W = 1080, H = 1920, ctx = $('canvas').getContext('2d');
let photos = [], selectedPhoto = null, selectedLabel = null, imageCache = new Map(), tileCache = new Map();
let assetMeta=new Map(),assetCache=new Map();
let musicAsset=null,musicPreparing=false,playGeneration=0;
const musicPlayer=new StudioMusic.MusicPlayer();
let editing = true, playing = false, time = 0, startClock = 0, raf = 0, dragging = null;
// 編輯權限與動畫姿態分離；定位輔助僅作用於明確選取的文字，不進入專案資料。
let positioning=false,settingsFocus=null;
const canEdit=()=>!playing&&!recording&&!preparing&&!serverBusy;
let showSafeArea=true,guideKind=null;
let bodySelected=false,logoSelected=false;
let recording = false, recorder = null, recordedURL = null, renderGeneration = 0;
const draft = new StudioDraft.DraftState(), storageKey='interior-studio-draft';
const waiters=new Map();
let photoDragId=null, editRaf=0, serverBusy=false, preparing=false;
let lastRevision=null, recordingFailure=null, activeExportRequest=null, receivedSession=null, storageFailed=false;
let guardLocked=false,lastGuardRequest=null;
let sessionLost=false;
const deletionHistory=new StudioPhotoHistory.History();
let recoverableMedia=[],pendingDeletion=null;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const isCompare=()=>draft.template==='compare';
const isTour=()=>draft.template==='tour';
const bodySequence=()=>isTour()?(draft.tour?.clips||[]):isCompare()?draft.comparisons:photos;
const coverDuration=()=>photos.length?StudioCover.duration(draft.cover):0;
const coverScene=()=>({id:'project-cover',type:'cover',name:'片頭封面',duration:coverDuration(),labels:[],image:photos.find(p=>p.id===draft.cover?.photo_id)?.image});
const sequence=()=>coverDuration()?[coverScene(),...bodySequence()]:bodySequence();
const projectOverlays=()=>isTour()?draft.tour.overlays:isCompare()?draft.comparisonOverlays:draft.overlays;
const photo = () => sequence().find(p => p.id === selectedPhoto) || sequence()[0];
const cropPhoto=()=>isTour()?photo()?.crop:isCompare()?photo()?.[comparisonEditor.cropSide+'_crop']:photo();
const label = () => photo()?.labels.find(l => l.id === selectedLabel);
const total = () => sequence().reduce((sum, p) => sum + Number(p.duration), 0);
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
function post(type, extra = {}) { window.parent.postMessage({isStreamlitMessage:true, type, ...extra}, '*'); }
function resize() { post('streamlit:setFrameHeight', {height:Math.ceil(document.querySelector('.studio').getBoundingClientRect().height) + 8}); }
new ResizeObserver(resize).observe(document.querySelector('.studio'));
function metadata() { return photos.map(({image, tiles, ...row}) => row); }
function validProject() {
  const musicError=StudioMusic.validate(draft.music,musicAsset);if(musicError){status(musicError,true);return false;}
  const coverError=StudioCover.validate(draft.cover,photos);if(coverError){status(coverError,true);return false;}
  const bodyError=StudioBody.validate(draft.cover);if(bodyError){status(bodyError,true);return false;}
  if (total() > 120) { status('影片總長最多 120 秒，請縮短照片秒數。', true); return false; }
  const comparisonError=StudioComparison.validate(draft.comparisons,photos);
  if(comparisonError){status(comparisonError,true);return false;}
  for (const p of [...photos,...draft.comparisons,...(draft.tour?.clips||[])]) {
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
  draft.coverSeconds=StudioCover.duration(draft.cover);
  try {sessionStorage.setItem(storageKey,JSON.stringify(draft.persisted({selectedPhoto,selectedLabel,selectedOverlay:pngEditor.selected,time,showSafeArea,bodySelected,logoSelected,outputs:outputs.persisted(),deletion:deletionHistory.persisted()})));storageFailed=false;}
  catch(error){storageFailed=true;status('此瀏覽器無法暫存草稿；離開前請下載ZIP備份。',true);}
}
window.addEventListener('pagehide',()=>{persistDraft();musicPlayer.stop();});
function syncStatus() {
  if(guardLocked)status('正在確認工作區操作；按「取消操作」可返回目前草稿。');
  else if(outputs.busy())status(outputs.status().message);
  else if(preparing)status('輸出前正在套用最新設定…');
  else if(draft.pending)status('正在同步草稿，可繼續編輯…');
  else status(draft.dirty?'草稿已暫存；下載ZIP或輸出影片會自動準備。':'草稿已同步；同步不等於備份。');
  if(sessionLost)$('status').textContent+=' 工作階段已重建，請重新上傳素材或匯入ZIP；分頁暫存不是永久保存。';
  if(storageFailed){$('status').textContent+=' 此瀏覽器無法暫存草稿，離開前請下載ZIP。';$('status').classList.add('error');}
  $('applyChanges').disabled=!draft.dirty||!!draft.pending||recording||preparing||serverBusy;
  showVersions();
}
function showVersions(){
  const versions=draft.versions,current=draft.contentVersion;if(!versions||!current){$('versionStatus').textContent='';return;}
  const mp4=versions.mp4?(versions.mp4===current?'與草稿相同':'舊版本，需要重新輸出'):'尚無可確認版本的成片';
  const zip=versions.zip?(versions.zip===current?'與草稿相同':'舊版本，非目前草稿備份'):'尚未產生';
  $('versionStatus').textContent=`${current===versions.synced?'草稿已同步':'草稿已暫存'} · MP4：${mp4} · ZIP：${zip} · `+
    (versions.backup===current?'此版本已確認備份。':'目前修改尚未備份。');
}
function markEdited(persist=true) {
  const priorPhoto=selectedPhoto;
  clearBrowserResult();
  comparisonEditor.prune();
  if(draft.tour){const ids=new Set(photos.map(p=>p.id));draft.tour.clips=draft.tour.clips.filter(c=>c.kind!=='photo'||ids.has(c.source));StudioTimeline.clampOverlays(draft.tour.overlays,StudioTimeline.total(draft.tour.clips)+coverDuration());}
  StudioCover.ensureSource(draft.cover,photos);
  if(draft.cover?.body?.enabled)bodyEditor.position(draft.cover.body.x,draft.cover.body.y);
  StudioBody.fit(draft.cover?.body,coverDuration(),total());
  StudioTimeline.clampOverlays(draft.overlays,StudioTimeline.total(photos)+coverDuration());
  StudioTimeline.clampOverlays(draft.comparisonOverlays,StudioTimeline.total(draft.comparisons)+coverDuration());
  if(!sequence().some(p=>p.id===selectedPhoto)){selectedPhoto=sequence()[0]?.id;selectedLabel=photo()?.labels[0]?.id;}
  time=clamp(time,0,Math.max(0,total()-1/30));
  const active=pngEditor.item();
  if(editing&&bodySelected&&draft.cover?.body?.enabled){const range=StudioBody.span(draft.cover.body,coverDuration(),total());
    if(time<range.start||time>=range.end){time=range.start;selectedPhoto=locate(time).photo?.id;}}
  else if(editing&&logoSelected&&draft.cover?.body?.logo_enabled){const range=StudioBody.logoSpan(draft.cover.body,coverDuration(),total());
    if(time<range.start||time>=range.end){time=range.start;selectedPhoto=locate(time).photo?.id;}}
  else if(editing&&active&&!pngEditor.active(active)){time=active.start;selectedPhoto=locate(time).photo?.id;}
  else if(editing&&!active&&photo())time=clamp(time,photoOffset(photo().id),photoOffset(photo().id)+photo().duration-1/30);
  if(selectedPhoto!==priorPhoto){selectedLabel=photo()?.labels[0]?.id;buildLabels();buildPhotos();}
  draft.touch(photos);
  if(persist)persistDraft();
  syncStatus();timeline.draw();
}
function queueDraw(){if(!editRaf)editRaf=requestAnimationFrame(()=>{editRaf=0;info();draw();});}
function synchronize(action='apply',request=null,width=null,outputOptions={}) {
  if(!validProject())return Promise.reject(new Error('請先修正標籤文字與時間設定。'));
  if(draft.pending)return Promise.reject(new Error('正在套用上一批變更，請稍候再試。'));
  const event=draft.snapshot(width===null?crypto.randomUUID():request,action,request);
  if(deletionHistory.restored)event.restore_photo=deletionHistory.restored;
  if(deletionHistory.entry)event.deleted_photo=deletionHistory.entry.id;
  if(width!==null){event.output_protocol=3;event.width=width;event.zip_backup=action==='export'&&outputOptions.zip_backup===true;draft.pending.output=true;draft.pending.version=event.content_version;}
  persistDraft();syncStatus();
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{
      waiters.delete(event.nonce);
      if(draft.pending?.nonce===event.nonce){draft.pending=null;draft.dirty=true;persistDraft();syncStatus();}
      reject(new Error('同步逾時，草稿已保留；請重新按下載ZIP或輸出影片。'));
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
    if(draft.session===args.session&&args.revision<draft.revision)return;
    let rows = [...args.project.photos];
    StudioCover.configure(args.project.cover_assets?.layout);
    StudioBody.configure(args.project.body_assets?.layout);
    StudioSafeArea.configure(args.project.safe_area);StudioSafeArea.mount($('safeAreaGuide'));
    guideKind=null;
    if(receivedSession!==args.session) {
      try {const saved=JSON.parse(sessionStorage.getItem(storageKey)||'null');
        if(saved?.session&&saved.session!==args.session)sessionLost=true;
        outputs.restore(saved?.session===args.session?saved.selection?.outputs:null);
        deletionHistory.load(saved?.session===args.session?saved.selection?.deletion:null);
        if(draft.restore(saved,args.session)){
          selectedPhoto=saved.selection?.selectedPhoto;selectedLabel=saved.selection?.selectedLabel;
          pngEditor.selected=saved.selection?.selectedOverlay||null;time=saved.selection?.time||0;
          showSafeArea=saved.selection?.showSafeArea??true;$('showSafeArea').checked=showSafeArea;
          bodySelected=saved.selection?.bodySelected??false;
          logoSelected=saved.selection?.logoSelected??false;
          if(draft.pending&&args.response?.nonce!==draft.pending.nonce){draft.pending=null;draft.dirty=true;}
        }
      }catch(error){sessionStorage.removeItem(storageKey);}
      receivedSession=args.session;
    }
    const templateChanged=draft.template!==(args.project.template_id||'items');
    recoverableMedia=rows.concat(args.undo_photo?[args.undo_photo]:[]);
    if(deletionHistory.restored&&args.undo_photo?.id===deletionHistory.restored&&!rows.some(p=>p.id===deletionHistory.restored))rows.push(args.undo_photo);
    const legacyCover=draft.session===args.session&&draft.cover===null&&(draft.dirty||draft.pending);
    const priorCoverSeconds=draft.cover?.enabled?(draft.coverSeconds??.5):0;
    const localCoverTiming=draft.session===args.session&&(draft.dirty||draft.pending);
    const keepTour=draft.session===args.session&&(draft.dirty||draft.pending)&&!(draft.pending&&args.response?.nonce===draft.pending.nonce&&args.response.ok&&draft.seq===draft.pending.seq);
    if(!keepTour)draft.tour=JSON.parse(JSON.stringify(args.project.tour||StudioTour.fresh()));
    const result=draft.receive(rows,args.session,args.revision,args.response,args.project.overlays||[],
                              args.project.comparisons||[],args.project.comparison_overlays||[],args.project.cover||null,args.project.music||null);
    if(result.stale)return;
    if(draft.cover&&!draft.cover.body)draft.cover.body=StudioBody.newBody();
    if(StudioBody.upgrade(draft.cover?.body))draft.touch(draft.rows);
    draft.music??=StudioMusic.newMusic();
    const newMusicAsset=args.project.music_asset||null;
    if(musicAsset?.id!==newMusicAsset?.id){stopPlayback();clearBrowserResult();$('musicPanel').open=!!newMusicAsset;}
    musicAsset=newMusicAsset;musicPlayer.setAsset(musicAsset);
    photos=draft.rows;
    let delayed=false;
    for(const p of [...photos,...draft.comparisons])for(const l of p.labels||[])
      if(StudioLabelTiming.delay(l,p.duration))delayed=true;
    if(delayed)draft.touch(photos);
    draft.template=args.project.template_id||'items';
    draft.tour??=StudioTour.fresh();
    await tourEditor.receive(args.project.floor_plan,args.project.videos||[],args.project.tour_layout,loadImage);
    if(generation!==renderGeneration)return;
    if(isTour()&&StudioTour.reconcile(draft.tour,draft.rows,args.project.videos||[],()=>crypto.randomUUID()))draft.touch(draft.rows);
    if(legacyCover&&draft.cover?.enabled){for(const slot of [draft.overlays,draft.comparisonOverlays])for(const o of slot)o.start+=coverDuration();time+=coverDuration();draft.touch(photos);}
    else if(localCoverTiming&&draft.dirty&&draft.cover?.enabled&&priorCoverSeconds!==coverDuration()){
      const delta=coverDuration()-priorCoverSeconds;
      for(const slot of [draft.overlays,draft.comparisonOverlays])for(const o of slot)o.start=Math.max(0,o.start+delta);
      for(const k of ['','logo_'])if(draft.cover.body?.[k+'auto_timing']===false){draft.cover.body[k+'start']=Math.max(0,draft.cover.body[k+'start']+delta);draft.cover.body[k+'end']=Math.max(0,draft.cover.body[k+'end']+delta);}
      time=Math.max(0,time+delta);draft.touch(photos);
    }
    StudioBody.fit(draft.cover?.body,coverDuration(),total());
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
    const bodyAssets=args.project.body_assets||{};
    const bodyTemplate=bodyAssets.template?(bodyEditor.template?.src===bodyAssets.template?bodyEditor.template:await loadImage(bodyAssets.template)):null;
    const bodyTitle=bodyAssets.title?(bodyEditor.calibrated?.image.src===bodyAssets.title?bodyEditor.calibrated.image:await loadImage(bodyAssets.title)):null;
    await Promise.all(assets.map(async asset=>pngImages.set(asset.id,assetCache.get(asset.id)||await loadImage(asset.image))));
    if (generation !== renderGeneration) return;
    imageCache = images; tileCache = tiles;
    coverEditor.template=coverTemplate;coverEditor.calibrated=coverTitle?{image:coverTitle,key:StudioCover.key(args.project.cover)}:null;
    bodyEditor.template=bodyTemplate;bodyEditor.calibrated=bodyTitle?{image:bodyTitle,key:StudioBody.key(args.project.cover),bounds:bodyAssets.bounds}:null;
    assetMeta=new Map(assets.map(asset=>[asset.id,asset]));assetCache=pngImages;
    if(lastRevision!==null && args.revision!==lastRevision) {
      clearBrowserResult();
      if(recording && recorder?.state==='recording') {recordingFailure='錄製期間專案內容改變，請重新錄製。';recorder.stop();}
    }
    lastRevision=args.revision;
    guardLocked=!!args.guard_request;
    serverBusy=guardLocked; // 背景輸出使用固定快照，不鎖住文字／PNG／時間軸。
    photos=draft.rows;
    draft.configureVersions(args.versions);
    if(!recording&&!preparing&&!serverBusy&&!draft.pending) {
      const imported=StudioAI.importBatches(draft,args.ai_imports,imageCache,StudioPhoto.layout,()=>crypto.randomUUID());
      if(imported.added){markEdited();editing=true;stopPlayback();}
      if(imported.messages.length)$('aiStatus').textContent=imported.messages.join(' ');
    }
    if (!sequence().some(p => p.id === selectedPhoto)) selectedPhoto = sequence()[0]?.id;
    if (selectedLabel&&!photo()?.labels.some(l => l.id === selectedLabel)) selectedLabel=null;
    time=clamp(time,0,Math.max(0,total()-1/30));
    pngEditor.library();comparisonEditor.library();buildPhotos(); buildLabels(); fillForm(); draw(); support();$('undoPhoto').hidden=!deletionHistory.entry;
    lockEditor(recording||preparing||serverBusy);if(!recording&&!preparing)syncStatus();
    persistDraft();resize();
    if(args.guard_request&&lastGuardRequest!==args.guard_request.id){
      lastGuardRequest=args.guard_request.id;stopPlayback();persistDraft();
      post('streamlit:setComponentValue',{value:{action:'inspect_guard',nonce:crypto.randomUUID(),session:draft.session,
        request:lastGuardRequest,base_revision:draft.revision,seq:draft.seq,content_version:draft.currentVersion()},dataType:'json'});
    }
    if(!args.guard_request)lastGuardRequest=null;
    if(result.matched) {
      if(result.success)outputs.ack(args.response);else if(outputs.intent?.id===args.response.nonce)outputs.fail(result.error);
      const waiter=waiters.get(args.response.nonce);
      if(waiter){clearTimeout(waiter.timer);waiters.delete(args.response.nonce);
        if(result.success)waiter.resolve();else waiter.reject(new Error(result.error));}
      if(result.error)status(result.error+' 草稿仍保留在此頁。',true);
    }
    outputs.receive(args.output_status,args.zip_delivery,args.response,args.mp4_delivery);
    syncStatus();persistDraft();
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
  if(coverDuration())$('photos').append(button(`封面 · ${coverDuration()}秒`,()=>selectMaterial({type:'cover',source:'project-cover',id:'project-cover',start:0}),'photo'+(selectedPhoto==='project-cover'?' active':'')));
  const active=bodySequence();active.forEach((p, index) => {
    const item = button('', () => selectMaterial({type:'photo',id:p.id,source:p.id,start:photoOffset(p.id)}), 'photo' + (p.id === selectedPhoto ? ' active' : ''));
    item.draggable = true; item.dataset.photoId = p.id; item.title = p.name;
    const img = document.createElement('img'); img.src = p.image||photos.find(row=>row.id===(isTour()?p.source:p.after_id))?.image||tourEditor.videos.get(p.source)?.poster||''; img.alt = p.name;
    const caption = document.createElement('span'); caption.textContent = `${index+1} · ${Number(p.duration.toFixed(2))}s · ${p.name}`;
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
  $('total').textContent = `${active.length} ${isTour()?'個導覽片段':isCompare()?'組對比':'張'} · ${total().toFixed(1)} 秒`;
  $('seek').max = Math.max(0, total() - 1/30);
}
function buildLabels() {
  $('labels').replaceChildren();
  const p=photo(); if(!p)return;
  if (!p.labels.length) $('labels').textContent = p.type==='cover'?'封面標題使用上方設定。':'尚無標籤，先新增一個裝修項目。';
  p.labels.forEach(l => $('labels').append(button(l.text, () => {
    stopPlayback();if(selectedPhoto!==p.id){selectedPhoto=p.id;time=photoOffset(p.id);}
    positioning=false;bodySelected=false;logoSelected=false;pngEditor.selected=null;selectedLabel=l.id;
    persistDraft();buildLabels(); fillForm(); draw();}, l.id===selectedLabel?'active':'')));
  $('labelForm').hidden = !label();
  focusSettings();
  $('addLabel').disabled = p.type==='cover'||p.labels.length >= 12 || recording||preparing||serverBusy;
}
const labelFields = ['text','font_size','color','background','opacity','radius','line','animation','start','end','enter','layer'];
function fillMusic(){
  const m=draft.music||StudioMusic.newMusic();$('musicName').textContent=musicAsset?`${musicAsset.name} · ${musicAsset.duration.toFixed(1)}秒`:'請先在上方加入BGM。';
  for(const [id,field] of [['musicEnabled','enabled'],['musicLoop','loop']])$(id).checked=m[field];
  if(document.activeElement!==$('musicVolume'))$('musicVolume').value=m.volume*100;
  if(document.activeElement!==$('musicFade'))$('musicFade').value=m.fade_out;
  $('musicVolumeText').textContent=`${Math.round(m.volume*100)}%`;
  for(const id of ['musicEnabled','musicVolume','musicFade','musicLoop'])$(id).disabled=!musicAsset||recording||preparing||serverBusy;
}
for(const [id,field] of [['musicEnabled','enabled'],['musicLoop','loop'],['musicVolume','volume'],['musicFade','fade_out']]){
  $(id).oninput=()=>{if(recording||preparing||serverBusy||!musicAsset)return;stopPlayback();
    draft.music[field]=['enabled','loop'].includes(field)?$(id).checked:Number($(id).value)/(field==='volume'?100:1);
    markEdited();fillMusic();support();draw();};
  $(id).onchange=()=>persistDraft();
}
function fillForm() {
  fillMusic();
  coverEditor.refresh();
  bodyEditor.refresh();
  if(bodySelected||logoSelected)$('bodyPanel').open=true;
  comparisonEditor.refresh();
  tourEditor.refresh();
  $('deletePhoto').textContent=isTour()?'刪除導覽片段':isCompare()?'刪除對比片段':'刪除照片';
  $('edit').textContent=positioning?'結束文字定位輔助':'定位選取文字';
  $('edit').disabled=!label()||!canEdit();
  const target=replacementSource();
  $('replacePhoto').disabled=!target||!canEdit();
  $('replacePhoto').textContent=isCompare()?`替換${comparisonEditor.cropSide==='before'?'施工前':'施工後'}照片`:'替換照片';
  $('replacementHint').textContent=target?`目前來源：${target.name}；保留時長、標籤及配對。`:'';
  focusSettings();
  for(const key of ['duration','fit','zoom','crop_x','crop_y','moveLeft','moveRight','deletePhoto','addLabel'])$(key).disabled=!photo()||photo().type==='cover'||recording||preparing||serverBusy;
  const p=photo(); if(!p){$('labelForm').hidden=true;$('overlayForm').hidden=true;return;}
  if(p.type==='cover'){$('labelForm').hidden=true;$('duration').value=coverDuration();$('photoNumber').textContent='片頭封面';pngEditor.refresh();return;}
  if(document.activeElement!==$('duration'))$('duration').value=Number(p.duration.toFixed(3)); $('photoNumber').textContent=`${sequence().findIndex(row=>row.id===p.id)+1} / ${sequence().length}`;
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
function focusSettings(){
  const kind=pngEditor.item()?'overlayForm':bodySelected||logoSelected?'bodyPanel':label()?'labelSettings':photo()?.type==='cover'?'coverPanel':'photoSettings';
  const key=kind+':'+(pngEditor.selected||selectedLabel||selectedPhoto||'');
  for(const id of ['overlayForm','bodyPanel','labelSettings','coverPanel','photoSettings','comparisonForm'])
    $(id).classList.toggle('focused-settings',id===kind||(kind==='photoSettings'&&id==='comparisonForm'&&isCompare()));
  $('selectionHeading').textContent=kind==='overlayForm'?`PNG：${pngEditor.item().name}`:kind==='labelSettings'?`文字：${label().text}`:kind==='bodyPanel'?'正文標題／LOGO':`目前片段：${photo()?.name||'尚無'}`;
  // 只在選取對象改變時定位設定區，不重建節點、不重設 details 展開狀態。
  if(settingsFocus!==key){$('settingsPanel').scrollTop=0;settingsFocus=key;}
}
function replacementSource(){
  const p=photo();if(!p||p.type==='cover'||isTour()&&p.kind==='video')return null;
  return isTour()?photos.find(row=>row.id===p.source):isCompare()?photos.find(row=>row.id===p[comparisonEditor.cropSide+'_id']):p;
}
$('replacePhoto').onclick=()=>{
  const p=replacementSource();if(!p||!canEdit()||draft.pending)return;
  persistDraft();post('streamlit:setComponentValue',{value:{action:'replace_photo',nonce:crypto.randomUUID(),session:draft.session,
    base_revision:draft.revision,photo_id:p.id},dataType:'json'});
};
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
function labelPose(p,l){
  if(positioning&&!playing&&!recording&&l.id===selectedLabel)return {x:0,y:0,scale:1,alpha:1};
  return StudioAnimation.pose(l,time-photoOffset(p.id));
}
function posedBounds(p,l){const pose=labelPose(p,l);if(!pose||pose.alpha<=.001)return null;const b=bounds(l);
  return {...b,x:b.x+pose.x*W+b.width*(1-pose.scale)/2,y:b.y+pose.y*H+b.height*(1-pose.scale)/2,width:b.width*pose.scale,height:b.height*pose.scale};}
function visibleEditLabel(p,l){return !!posedBounds(p,l)&&(!isCompare()||StudioComparison.visibleTitle(p,l,time-photoOffset(p.id),comparisonEditor.view)||positioning&&l.id===selectedLabel);}
function updateSafeArea(){
  const current=editing?photo():locate(time).photo;
  const kind=current?.type==='cover'?'cover':'body';
  if(kind!==guideKind){if(kind==='cover')StudioCover.mountGuide($('safeAreaGuide'));else {StudioSafeArea.mount($('safeAreaGuide'));StudioBody.mountGuide($('safeAreaGuide'),draft.cover);}guideKind=kind;}
  $('safeAreaGuide').hidden=!showSafeArea||recording;
}
$('showSafeArea').onchange=()=>{showSafeArea=$('showSafeArea').checked;updateSafeArea();persistDraft();};
function draw() {
  updateSafeArea();
  const state=editing?{photo:photo(),local:time-photoOffset(photo()?.id)}:locate(time), p=state.photo;
  ctx.fillStyle='#000000';ctx.fillRect(0,0,W,H); if(!p){$('clock').textContent='0.0 / 0.0 s';$('seek').value=0;timeline.draw();return;}
  const image=imageCache.get(p.id);
  if(!isTour()||p.kind!=='video')tourEditor.stop();
  if(p.type==='cover')coverEditor.draw(ctx);
  else if(isTour()){
    if(p.kind==='video')tourEditor.drawVideo(ctx,p,state.local,playing);
    else{const im=imageCache.get(p.source);if(im){const b=StudioPhoto.layout(im.naturalWidth,im.naturalHeight,W,H,p.crop);ctx.drawImage(im,b.sx,b.sy,b.sw,b.sh,b.dx,b.dy,b.dw,b.dh);}}
  }
  else if(isCompare())comparisonEditor.draw(ctx,p,state.local,editing);
  else if(image) {
    const box=StudioPhoto.layout(image.naturalWidth,image.naturalHeight,W,H,p);
    ctx.drawImage(image,box.sx,box.sy,box.sw,box.sh,box.dx,box.dy,box.dw,box.dh);
  }
  if(p.type!=='cover')bodyEditor.draw(ctx,time,editing&&bodySelected);
  const materials=p.labels.map((l,index)=>({layer:l.layer??10,index,label:l})).concat(projectOverlays().map((o,index)=>({layer:o.layer,index:p.labels.length+index,overlay:o})));
  for(const item of materials.sort((a,b)=>a.layer-b.layer||a.index-b.index)) {
    if(item.overlay){pngEditor.draw(ctx,item.overlay,time,canEdit());continue;}
    const l=item.label;
    if(editing&&!visibleEditLabel(p,l))continue;
    const position=labelPose(p,l);
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
      const shown=posedBounds(p,l);if(shown){ctx.save();ctx.strokeStyle='#eac181';ctx.lineWidth=5;ctx.setLineDash([12,8]);ctx.strokeRect(shown.x-6,shown.y-6,shown.width+12,shown.height+12);ctx.setLineDash([]);
      if(l.line){ctx.beginPath();ctx.arc(l.point_x*W,l.point_y*H,25,0,Math.PI*2);ctx.stroke();}ctx.restore();}
    }
  }
  if(isTour()&&p.type!=='cover')tourEditor.drawPlan(ctx,p);
  $('mode').textContent=playing?'動畫播放中':positioning?'文字定位輔助（不影響影片時間）':'已暫停 · 可直接編輯'; $('clock').textContent=`${time.toFixed(1)} / ${total().toFixed(1)} s`;
  $('seek').value=time;
  timeline.draw();
}
function coords(e) {const r=$('canvas').getBoundingClientRect();return {x:(e.clientX-r.left)*W/r.width,y:(e.clientY-r.top)*H/r.height};}
$('canvas').addEventListener('pointerdown',e=>{
  if(!canEdit())return;
  const xy=coords(e),p=photo();if(!p)return;
  const visible=p.labels.filter(l=>visibleEditLabel(p,l));
  const hitLayer=Math.max(-1,...visible.filter(l=>{const b=posedBounds(p,l);return (l.line&&!l.comparison_side&&Math.hypot(xy.x-l.point_x*W,xy.y-l.point_y*H)<42)||(xy.x>=b.x&&xy.x<=b.x+b.width&&xy.y>=b.y&&xy.y<=b.y+b.height);}).map(l=>l.layer??10));
  if(pngEditor.down(xy,hitLayer)){e.preventDefault();dragging={type:'png'};$('canvas').setPointerCapture(e.pointerId);draw();return;}
  if(hitLayer<0&&p.type!=='cover'&&bodyEditor.hit(xy,time)){
    const placed=bodyEditor.bounds().tile;dragging={type:'body',dx:xy.x-placed.x,dy:xy.y-placed.y};
    e.preventDefault();bodySelected=true;logoSelected=false;pngEditor.selected=null;selectedLabel=null;$('canvas').setPointerCapture(e.pointerId);fillForm();draw();return;}
  if(hitLayer<0&&comparisonEditor.dividerDown(xy)){e.preventDefault();dragging={type:'divider'};$('canvas').setPointerCapture(e.pointerId);return;}
  // 優先選取目前標籤的定位點，避免與其他文字碰撞時難以拖曳。
  const ordered=[...visible].reverse().sort((a,b)=>Number(b.id===selectedLabel)-Number(a.id===selectedLabel));
  for(const l of ordered) {
    const b=posedBounds(p,l),base=bounds(l);
    if(l.line&&!l.comparison_side&&Math.hypot(xy.x-l.point_x*W,xy.y-l.point_y*H)<42) {dragging={type:'point',id:l.id,dx:0,dy:0};break;}
    if(xy.x>=b.x&&xy.x<=b.x+b.width&&xy.y>=b.y&&xy.y<=b.y+b.height) {dragging={type:'label',id:l.id,dx:xy.x-base.x,dy:xy.y-base.y};break;}
  }
  if(dragging) {e.preventDefault();bodySelected=false;logoSelected=false;pngEditor.selected=null;selectedLabel=dragging.id;$('canvas').setPointerCapture(e.pointerId);buildLabels();fillForm();draw();}
});
$('canvas').addEventListener('pointermove',e=>{
  if(!dragging||recording||preparing||serverBusy)return;const xy=coords(e);
  if(dragging.type==='png'){pngEditor.move(xy);markEdited(false);queueDraw();return;}
  if(dragging.type==='body'){const size=StudioBody.box(draft.cover.body);
    bodyEditor.position((xy.x-dragging.dx+size.width/2)/W,(xy.y-dragging.dy+size.height/2)/H);
    bodyEditor.refresh();markEdited(false);queueDraw();return;}
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
  if(editing&&!recording&&!preparing&&!serverBusy&&bodySelected&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){
    e.preventDefault();const b=draft.cover.body,step=e.shiftKey?30:6;
    bodyEditor.position(b.x+(e.key==='ArrowLeft'?-step:e.key==='ArrowRight'?step:0)/W,b.y+(e.key==='ArrowUp'?-step:e.key==='ArrowDown'?step:0)/H);
    markEdited();fillForm();draw();return;}
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
function followPlayhead(){const p=locate(time).photo;if(p&&p.id!==selectedPhoto){selectedPhoto=p.id;selectedLabel=null;bodySelected=false;logoSelected=false;pngEditor.selected=null;buildPhotos();buildLabels();fillForm();}}
function stopPlayback(){const wasPlaying=playing;playGeneration++;playing=false;editing=!recording;musicPreparing=false;musicPlayer.stop();tourEditor.stop();cancelAnimationFrame(raf);$('play').textContent='▶ 預覽影片';if(wasPlaying)followPlayhead();}
function tick(now) {
  time=(now-startClock)/1000;
  if(time>=total()) {time=Math.max(0,total()-1/30);stopPlayback();fillForm();draw();persistDraft();if(recording&&recorder?.state==='recording')recorder.stop();else syncStatus();return;}
  draw();if(recording)$('recordProgress').value=time/total();
  raf=requestAnimationFrame(tick);
}
$('play').onclick=async()=>{if(recording||serverBusy||preparing)return;if(playing||musicPreparing){stopPlayback();fillForm();draw();persistDraft();syncStatus();return;}
  const generation=++playGeneration;
  if(time>=total()-1/30)time=0;
  if(StudioMusic.active(draft.music,musicAsset)){
    musicPreparing=true;status('正在準備BGM…');
    try{await musicPlayer.prepare();if(!musicPreparing||generation!==playGeneration)return;musicPlayer.start(draft.music,time,total());}
    catch(error){status(error.message,true);musicPreparing=false;return;}musicPreparing=false;
  }
  positioning=false;comparisonEditor.view='combined';editing=false;playing=true;startClock=performance.now()-time*1000;$('play').textContent='❚❚ 暫停';raf=requestAnimationFrame(tick);fillForm();
  status(StudioMusic.active(draft.music,musicAsset)?'正在預覽影片（含BGM）…':'正在預覽影片…');
};
$('edit').onclick=()=>{if(!canEdit()||!label())return;positioning=!positioning;fillForm();draw();};
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
  pngEditor.selected=null;bodySelected=false;logoSelected=false;
  const l={id:crypto.randomUUID(),text:'裝修項目',x:.12,y:.28,point_x:.58,point_y:.52,font_size:46,color:'#ffffff',background:'#222822',opacity:.88,radius:18,line:true,animation:'left',start:0,enter:.6,end:p.duration};
  StudioLabelTiming.delay(l,p.duration);
  p.labels.push(l);selectedLabel=l.id;editing=true;stopPlayback();buildLabels();fillForm();draw();markEdited();
};
$('deleteLabel').onclick=()=>{const p=photo();p.labels=p.labels.filter(l=>l.id!==selectedLabel);tileCache.delete(selectedLabel);selectedLabel=p.labels[0]?.id;buildLabels();fillForm();draw();markEdited();};
function refreshAfterDelete(){selectedPhoto=sequence()[0]?.id;selectedLabel=photo()?.labels[0]?.id;buildPhotos();buildLabels();fillForm();draw();comparisonEditor.library();$('undoPhoto').hidden=!deletionHistory.entry;}
function deleteSource(id,confirmed=false){if(!canEdit()||draft.pending)return;
  const use=StudioPhotoHistory.impact(draft,id);if(!use)return;
  if(!confirmed&&(use.clips||use.tour_clips||use.cover||use.labels)){
    pendingDeletion=id;$('deleteNotice').textContent=`刪除影響：${use.clips}組前後對比、${use.tour_clips}個導覽片段、${use.cover?'封面來源':'不涉及封面'}、${use.labels}個來源附屬文字。相關配對與導覽片段將移除，獨立PNG保留（超出新片長部分截短）；可復原最近一次刪除。`;
    $('confirmPhotoDelete').hidden=$('cancelPhotoDelete').hidden=false;return;
  }
  draft.rows=photos;if(!deletionHistory.begin(draft,id))return;
  draft.deleted.push(id);photos=photos.filter(p=>p.id!==id);draft.rows=photos;
  pendingDeletion=null;$('confirmPhotoDelete').hidden=$('cancelPhotoDelete').hidden=true;
  markEdited();deletionHistory.finish(draft);persistDraft();refreshAfterDelete();$('deleteNotice').textContent='已刪除，可復原最近一次；若繼續改內容，復原將保守停止以保護新編輯。';
}
$('confirmPhotoDelete').onclick=()=>{if(pendingDeletion)deleteSource(pendingDeletion,true);};
$('cancelPhotoDelete').onclick=()=>{pendingDeletion=null;$('confirmPhotoDelete').hidden=$('cancelPhotoDelete').hidden=true;$('deleteNotice').textContent='已取消刪除，內容保留。';};
$('undoPhoto').onclick=()=>{if(!canEdit()||draft.pending)return;
  try{deletionHistory.restore(draft,recoverableMedia);photos=draft.rows;markEdited();refreshAfterDelete();$('deleteNotice').textContent='已復原照片、順序、標籤及相關設定。';}
  catch(error){$('deleteNotice').textContent=error.message;}
};
$('deletePhoto').onclick=()=>{if(!canEdit())return;if(isTour()){const i=draft.tour.clips.findIndex(c=>c.id===selectedPhoto);if(i>=0){draft.tour.clips.splice(i,1);markEdited();refreshAfterDelete();}}else if(isCompare()){const i=draft.comparisons.findIndex(c=>c.id===selectedPhoto);if(i>=0){draft.comparisons.splice(i,1);markEdited();refreshAfterDelete();}}
  else deleteSource(selectedPhoto);};
$('applyChanges').onclick=()=>synchronize().catch(error=>status(error.message,true));
function movePhoto(delta) {
  const rows=bodySequence(),index=rows.findIndex(p=>p.id===selectedPhoto),next=index+delta;if(index<0||next<0||next>=rows.length)return;
  [rows[index],rows[next]]=[rows[next],rows[index]];buildPhotos();markEdited();
}
$('moveLeft').onclick=()=>movePhoto(-1);$('moveRight').onclick=()=>movePhoto(1);
function supportedMime() {
  if(!window.MediaRecorder||!$('canvas').captureStream)return null;
  const choices=StudioMusic.active(draft.music,musicAsset)?['video/mp4;codecs=avc1.42E028,mp4a.40.2','video/mp4;codecs=avc1,mp4a.40.2']:['video/mp4;codecs=avc1.42E028','video/mp4;codecs=avc1'];
  return choices.find(m=>MediaRecorder.isTypeSupported(m))||null;
}
function support() {
  if(isTour()){$('browserExport').disabled=true;$('support').textContent='空間導覽請使用下方FFmpeg輸出，確保影片原音與平面圖完整。';return;}
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
  if(!locked){support();buildLabels();fillForm();$('applyChanges').disabled=!draft.dirty||!!draft.pending;}
}
$('browserExport').onclick=async()=>{
  if(!bodySequence().length){status('請先加入照片或新增一組前後配對。',true);return;}
  if(!validProject()||draft.pending||serverBusy||preparing)return;
  const mime=supportedMime();if(!mime){status('此瀏覽器不支援 H.264 MP4，請使用 FFmpeg。',true);return;}
  preparing=true;lockEditor(true);
  if(StudioMusic.active(draft.music,musicAsset)){
    try{await musicPlayer.prepare();}catch(error){preparing=false;lockEditor(false);status(error.message,true);return;}
  }
  try{await ensureSynced();}catch(error){preparing=false;lockEditor(false);status(error.message,true);return;}
  preparing=false;
  clearBrowserResult();stopPlayback();recording=true;editing=false;time=0;draw();lockEditor(true);
  $('recordProgress').hidden=false;$('recordProgress').value=0;
  let stream, visibility=null, timer=null;
  recordingFailure=null;
  try {
    stream=$('canvas').captureStream(30);
    if(StudioMusic.active(draft.music,musicAsset)){
      const audio=musicPlayer.start(draft.music,0,total(),true);for(const track of audio?.getAudioTracks()||[])stream.addTrack(track);
    }
    recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:8_000_000,audioBitsPerSecond:192_000});
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
function seekTime(value){if(recording||preparing||serverBusy)return;stopPlayback();positioning=false;comparisonEditor.view='combined';time=clamp(StudioTimeline.snap(value),0,Math.max(0,total()-1/30));
  followPlayhead();fillForm();draw();persistDraft();}
function selectMaterial(item){if(recording||preparing||serverBusy)return;stopPlayback();editing=true;
  positioning=false;comparisonEditor.view='combined';
  bodySelected=item.type==='body_title';
  logoSelected=item.type==='body_logo';
  if(item.type==='png'){pngEditor.selected=item.id;selectedLabel=null;if(!pngEditor.active(item))seekTime(item.start);selectedPhoto=locate(time).photo?.id;pngEditor.selected=item.id;}
  else if(['body_title','body_logo'].includes(item.type)){pngEditor.selected=null;seekTime(item.start,true);selectedLabel=null;}
  else {pngEditor.selected=null;selectedPhoto=item.source;selectedLabel=item.type==='label'?item.id:null;time=item.start;}
  bodySelected=item.type==='body_title';logoSelected=item.type==='body_logo';
  buildPhotos();buildLabels();fillForm();draw();persistDraft();}
const tourEditor=new StudioTourUI.TourEditor({data:()=>draft.tour||StudioTour.fresh(),photos:()=>photos,prefix:coverDuration,active:isTour,current:photo,locked:()=>!canEdit(),status,redraw:queueDraw,change:()=>{stopPlayback();markEdited();buildPhotos();buildLabels();fillForm();draw();}});
const comparisonEditor=new StudioComparisonUI.ComparisonEditor({photos:()=>photos,clips:()=>draft.comparisons,current:()=>photo()?.type==='cover'?null:photo(),
  active:isCompare,prefix:coverDuration,images:()=>imageCache,locked:()=>recording||preparing||serverBusy,status,
  replace:id=>{if(!canEdit())return;persistDraft();post('streamlit:setComponentValue',{value:{action:'replace_photo',nonce:crypto.randomUUID(),session:draft.session,base_revision:draft.revision,photo_id:id},dataType:'json'});},
  choose:id=>{if(id)selectMaterial({id,source:id,type:'comparison',start:photoOffset(id)});},
  removeSource:id=>deleteSource(id),
  refresh:()=>{editing=true;stopPlayback();fillForm();draw();},
  change:()=>{editing=true;stopPlayback();markEdited();buildPhotos();buildLabels();fillForm();draw();}});
const pngEditor=new StudioPNG.PNGEditor({overlays:projectOverlays,assets:()=>assetMeta,images:()=>assetCache,
  locked:()=>recording||preparing||serverBusy,total,time:()=>time,status,
  select:o=>selectMaterial(o),changed:()=>{editing=true;stopPlayback();markEdited();fillForm();draw();}});
const coverEditor=new StudioCover.CoverEditor({cover:()=>draft.cover,photos:()=>photos,images:()=>imageCache,slots:()=>[draft.overlays,draft.comparisonOverlays,...(draft.tour?[draft.tour.overlays]:[])],
  viewing:()=>photo()?.type==='cover',
  locked:()=>recording||preparing||serverBusy,status,choose:()=>selectMaterial({type:'cover',id:'project-cover',source:'project-cover',start:0}),
  change:()=>{stopPlayback();bodySelected=false;logoSelected=false;editing=true;selectedPhoto=coverDuration()?'project-cover':bodySequence()[0]?.id;selectedLabel=photo()?.labels[0]?.id;pngEditor.selected=null;time=0;markEdited();buildPhotos();buildLabels();fillForm();draw();}});
const bodyEditor=new StudioBody.BodyEditor({cover:()=>draft.cover,prefix:coverDuration,length:total,locked:()=>recording||preparing||serverBusy,status,
  change:(type='body_title')=>{stopPlayback();bodySelected=type==='body_title';logoSelected=type==='body_logo';editing=true;guideKind=null;
    if(photo()?.type==='cover'&&bodySequence().length){selectedPhoto=bodySequence()[0].id;selectedLabel=photo()?.labels[0]?.id;pngEditor.selected=null;time=coverDuration();buildPhotos();buildLabels();}
    markEdited();fillForm();draw();}});
const timeline=new StudioTimelineUI.TimelineUI($('timelineCanvas'),{photos:bodySequence,offset:coverDuration,overlays:projectOverlays,time:()=>time,
  body:()=>draft.cover?.body,title:()=>StudioBody.item(draft.cover,coverDuration(),total()),logo:()=>StudioBody.logoItem(draft.cover,coverDuration(),total()),
  locked:()=>recording||preparing||serverBusy,seek:seekTime,select:selectMaterial,
  selected:item=>item.type==='body_logo'?logoSelected:item.type==='body_title'?bodySelected:item.type==='png'?item.id===pngEditor.selected:item.type==='label'?item.id===selectedLabel:item.id===selectedPhoto,
  change:persist=>{stopPlayback();editing=true;markEdited(persist);buildPhotos();fillForm();draw();}});
$('timelineZoom').oninput=()=>{timeline.zoom=Number($('timelineZoom').value);timeline.draw();};
function stack(front){if(recording||preparing||serverBusy)return;const selected=pngEditor.item()||label();if(!selected)return;
  const all=[...sequence().flatMap(p=>p.labels),...projectOverlays()].sort((a,b)=>(a.layer??10)-(b.layer??10));
  const order=all.filter(o=>o!==selected);if(front)order.push(selected);else order.unshift(selected);
  order.forEach((o,i)=>o.layer=i);markEdited();fillForm();draw();}
$('bringFront').onclick=()=>stack(true);$('sendBack').onclick=()=>stack(false);
const outputs=new StudioOutput.OutputController({uuid:()=>crypto.randomUUID(),pending:()=>!!draft.pending,
  seq:()=>draft.seq,version:()=>draft.currentVersion(),current:()=>draft.contentVersion,persist:persistDraft,sync:synchronize,
  post:value=>post('streamlit:setComponentValue',{value:{...value,session:draft.session},dataType:'json'}),
  download:delivery=>{
    if(!/^\/[A-Za-z0-9_./-]*app\/static\/downloads\/[0-9a-f]{64}\.(zip|mp4)$/.test(delivery.url))throw new Error('下載網址不正確。');
    const a=document.createElement('a');a.href=delivery.url;a.download=delivery.filename;document.body.append(a);a.click();a.remove();
  }});
window.StudioOutputBridge={session:()=>draft.session,status:()=>outputs.status(),capture:(kind,width)=>{
  if(guardLocked||recording||preparing||!['zip','mp4'].includes(kind))return Promise.reject(new Error('目前無法輸出，請稍候。'));
  if(draft.versionContext&&draft.versionContext.width!==width)return Promise.reject(new Error('解析度設定尚未更新，請稍候再試。'));
  return outputs.request(kind,width);
},setZipBackup:value=>outputs.setZipBackup(value),retryZip:()=>outputs.retryZip(),downloadRequested:(kind='zip')=>{
  const d=kind==='mp4'?outputs.mp4Delivery:outputs.delivery;
  if(d)post('streamlit:setComponentValue',{value:{action:'downloads_requested',session:draft.session,nonce:crypto.randomUUID(),downloads:[{kind,operation_id:d.request_id,content_version:d.content_version}]},dataType:'json'});
}};
post('streamlit:componentReady',{apiVersion:1});resize();
