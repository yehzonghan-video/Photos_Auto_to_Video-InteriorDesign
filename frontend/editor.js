'use strict';
const $ = id => document.getElementById(id);
const W = 1080, H = 1920, ctx = $('canvas').getContext('2d');
let photos = [], selectedPhoto = null, selectedLabel = null, imageCache = new Map(), tileCache = new Map();
let editing = true, playing = false, time = 0, startClock = 0, raf = 0, dragging = null;
let recording = false, recorder = null, recordedURL = null, renderGeneration = 0;
let pending = false, localDirty = false, lastSent = null, photoDragId = null;
let saveTimer = null;
let lastRevision = null, recordingFailure = null;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const photo = () => photos.find(p => p.id === selectedPhoto) || photos[0];
const label = () => photo()?.labels.find(l => l.id === selectedLabel);
const total = () => photos.reduce((sum, p) => sum + Number(p.duration), 0);
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
function post(type, extra = {}) { window.parent.postMessage({isStreamlitMessage:true, type, ...extra}, '*'); }
function resize() { post('streamlit:setFrameHeight', {height:Math.ceil(document.querySelector('.studio').getBoundingClientRect().height) + 8}); }
new ResizeObserver(resize).observe(document.querySelector('.studio'));
function metadata() { return photos.map(({image, tiles, ...row}) => row); }
function validProject() {
  if (total() > 120) { status('影片總長最多 120 秒，請縮短照片秒數。', true); return false; }
  for (const p of photos) {
    if (!Number.isFinite(p.duration) || p.duration < 1 || p.duration > 20) {status('每張照片需為 1～20 秒。', true); return false;}
    for (const l of p.labels) {
      if (!l.text.trim() || l.text.length > 80 || !Number.isFinite(l.start) || !Number.isFinite(l.end) || !Number.isFinite(l.enter) ||
          l.start < 0 || l.end > p.duration || l.end <= l.start || l.enter < 0 || l.enter > 3 || l.enter > l.end-l.start) {
        status('請確認標籤文字，以及出現／消失時間與進場時長。', true); return false;
      }
    }
  }
  return true;
}
function save(action = 'update', target = null) {
  clearTimeout(saveTimer);
  if (!validProject()) return false;
  clearBrowserResult();
  localDirty = false;
  pending = true;
  lastSent = crypto.randomUUID();
  status('正在同步編輯…');
  post('streamlit:setComponentValue', {value:{nonce:lastSent, photos:metadata(), action, target}, dataType:'json'});
  return true;
}
function queueSave() {clearTimeout(saveTimer);saveTimer=setTimeout(()=>save(),350);}
function loadImage(src) {
  return new Promise((resolve, reject) => {const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('圖片載入失敗，請重新上傳。')); image.src = src;});
}
window.addEventListener('message', async event => {
  if (event.source !== window.parent || event.data?.type !== 'streamlit:render') return;
  const args = event.data.args;
  const generation = ++renderGeneration;
  try {
    const rows = args.project.photos;
    const images = new Map(), tiles = new Map();
    await Promise.all(rows.map(async p => {
      images.set(p.id, imageCache.get(p.id)?.src === p.image ? imageCache.get(p.id) : await loadImage(p.image));
      for (const [id, data] of Object.entries(p.tiles)) {
        const current = tileCache.get(id);
        tiles.set(id, current?.src === data.src ? current : await loadImage(data.src));
      }
    }));
    if (generation !== renderGeneration) return;
    imageCache = images; tileCache = tiles;
    // 若伺服器回覆較早的操作，不覆蓋使用者尚未同步的較新操作。
    if (pending && args.ack !== lastSent) return;
    if(lastRevision!==null && args.revision!==lastRevision) {
      clearBrowserResult();
      if(recording && recorder?.state==='recording') {recordingFailure='錄製期間專案內容改變，請重新錄製。';recorder.stop();}
    }
    lastRevision=args.revision;
    if (!localDirty) photos = rows;
    pending = false;
    if (!photos.some(p => p.id === selectedPhoto)) selectedPhoto = photos[0]?.id;
    if (!photo()?.labels.some(l => l.id === selectedLabel)) selectedLabel = photo()?.labels[0]?.id;
    if(!recording)status(localDirty ? '目前欄位尚未同步，請確認輸入值。' : '已同步到目前工作階段');
    buildPhotos(); buildLabels(); fillForm(); draw(); support(); if(recording)lockEditor(true); resize();
  } catch (error) { status(error.message, true); }
});
function button(text, fn, className = '') {
  const element = document.createElement('button'); element.textContent = text; element.className = className; element.onclick = fn; return element;
}
function buildPhotos() {
  $('photos').replaceChildren();
  photos.forEach((p, index) => {
    const item = button('', () => {if(recording)return; stopPlayback(); editing=true; selectedPhoto=p.id; selectedLabel=p.labels[0]?.id; buildPhotos(); buildLabels(); fillForm(); draw();}, 'photo' + (p.id === selectedPhoto ? ' active' : ''));
    item.draggable = true; item.dataset.photoId = p.id; item.title = p.name;
    const img = document.createElement('img'); img.src = p.image; img.alt = p.name;
    const caption = document.createElement('span'); caption.textContent = `${index+1} · ${p.duration}s · ${p.name}`;
    item.append(img, caption);
    item.ondragstart = e => {if(recording){e.preventDefault();return;} photoDragId=p.id; e.dataTransfer.setData('text/plain',p.id);};
    item.ondragover = e => {e.preventDefault(); item.classList.add('drag-over');};
    item.ondragleave = () => item.classList.remove('drag-over');
    item.ondrop = e => {
      e.preventDefault(); item.classList.remove('drag-over');
      const source = photos.findIndex(row => row.id === photoDragId), target = photos.findIndex(row => row.id === p.id);
      if (source < 0 || target < 0 || recording) return;
      const [moved] = photos.splice(source,1); photos.splice(target,0,moved);
      stopPlayback(); editing=true; buildPhotos(); save();
    };
    $('photos').append(item);
  });
  $('total').textContent = `${photos.length} 張 · ${total().toFixed(1)} 秒`;
  $('seek').max = Math.max(0, total() - 1/30);
}
function buildLabels() {
  $('labels').replaceChildren();
  const p=photo(); if(!p)return;
  if (!p.labels.length) $('labels').textContent = '尚無標籤，先新增一個裝修項目。';
  p.labels.forEach(l => $('labels').append(button(l.text, () => {selectedLabel=l.id; buildLabels(); fillForm(); draw();}, l.id===selectedLabel?'active':'')));
  $('labelForm').hidden = !label();
  $('addLabel').disabled = p.labels.length >= 12 || recording;
}
const labelFields = ['text','font_size','color','background','opacity','radius','line','animation','start','end','enter'];
function fillForm() {
  const p=photo(); if(!p)return;
  if(document.activeElement!==$('duration'))$('duration').value=p.duration; $('photoNumber').textContent=`${photos.findIndex(row=>row.id===p.id)+1} / ${photos.length}`;
  for (const key of ['zoom','crop_x','crop_y']) $(key).value=p[key];
  $('fit').value=p.fit || 'contain';
  for (const key of ['zoom','crop_x','crop_y']) $(key).disabled=recording || $('fit').value==='contain';
  const l=label(); $('labelForm').hidden=!l;
  if(l) {
    for(const key of labelFields) {if(document.activeElement===$(key))continue;if(key==='line')$(key).checked=l[key];else $(key).value=l[key];}
    $('start').max=p.duration; $('end').max=p.duration;
    info();
  }
}
function info() {
  const l=label(); if(!l)return;
  $('hold').textContent=`停留時間 ${Math.max(0,l.end-l.start-l.enter).toFixed(1)} 秒；時間以此張照片開始為基準`;
  $('position').textContent=`標籤 ${l.x.toFixed(2)}, ${l.y.toFixed(2)} · 定位點 ${l.point_x.toFixed(2)}, ${l.point_y.toFixed(2)}`;
}
function locate(t) {
  let offset=0;
  for(let i=0;i<photos.length;i++) {if(t<offset+photos[i].duration || i===photos.length-1)return {photo:photos[i],local:t-offset}; offset+=photos[i].duration;}
  return {photo:null,local:0};
}
function bounds(l) {
  const tile=tileCache.get(l.id), width=tile?.naturalWidth || 280, height=tile?.naturalHeight || 110;
  return {width,height,x:Math.min(l.x*W,W-width),y:Math.min(l.y*H,H-height)};
}
function draw() {
  const state=editing?{photo:photo(),local:0}:locate(time), p=state.photo;
  ctx.fillStyle='#000000';ctx.fillRect(0,0,W,H); if(!p)return;
  const image=imageCache.get(p.id);
  if(image) {
    const box=StudioPhoto.layout(image.naturalWidth,image.naturalHeight,W,H,p);
    ctx.drawImage(image,box.sx,box.sy,box.sw,box.sh,box.dx,box.dy,box.dw,box.dh);
  }
  for(const l of p.labels) {
    const position=editing?{x:0,y:0,scale:1,alpha:1}:StudioAnimation.pose(l,state.local);
    if(!position)continue;
    const b=bounds(l), x=b.x+position.x*W,y=b.y+position.y*H,tile=tileCache.get(l.id);
    ctx.save();ctx.globalAlpha=position.alpha;
    if(l.line) {
      ctx.strokeStyle='rgba(255,255,255,.824)';ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(x+b.width/2,y+b.height/2);ctx.lineTo(l.point_x*W,l.point_y*H);ctx.stroke();
      ctx.fillStyle='white';ctx.beginPath();ctx.arc(l.point_x*W,l.point_y*H,10,0,Math.PI*2);ctx.fill();
    }
    if(tile)ctx.drawImage(tile,x+b.width*(1-position.scale)/2,y+b.height*(1-position.scale)/2,b.width*position.scale,b.height*position.scale);
    else {ctx.fillStyle=l.background;ctx.fillRect(x,y,b.width,b.height);ctx.fillStyle=l.color;ctx.font=`${l.font_size}px sans-serif`;ctx.fillText(l.text,x+24,y+70);}
    ctx.restore();
    if(editing&&l.id===selectedLabel) {
      ctx.save();ctx.strokeStyle='#eac181';ctx.lineWidth=5;ctx.setLineDash([12,8]);ctx.strokeRect(b.x-6,b.y-6,b.width+12,b.height+12);ctx.setLineDash([]);
      ctx.beginPath();ctx.arc(l.point_x*W,l.point_y*H,25,0,Math.PI*2);ctx.stroke();ctx.restore();
    }
  }
  $('mode').textContent=editing?'構圖與標籤編輯':'動畫預覽'; $('clock').textContent=`${time.toFixed(1)} / ${total().toFixed(1)} s`;
  $('seek').value=time;
}
function coords(e) {const r=$('canvas').getBoundingClientRect();return {x:(e.clientX-r.left)*W/r.width,y:(e.clientY-r.top)*H/r.height};}
$('canvas').addEventListener('pointerdown',e=>{
  if(!editing||recording)return;
  const xy=coords(e),p=photo();if(!p)return;
  // 優先選取目前標籤的定位點，避免與其他文字碰撞時難以拖曳。
  const ordered=[...p.labels].reverse().sort((a,b)=>Number(b.id===selectedLabel)-Number(a.id===selectedLabel));
  for(const l of ordered) {
    const b=bounds(l);
    if(Math.hypot(xy.x-l.point_x*W,xy.y-l.point_y*H)<42) {dragging={type:'point',id:l.id,dx:0,dy:0};break;}
    if(xy.x>=b.x&&xy.x<=b.x+b.width&&xy.y>=b.y&&xy.y<=b.y+b.height) {dragging={type:'label',id:l.id,dx:xy.x-b.x,dy:xy.y-b.y};break;}
  }
  if(dragging) {e.preventDefault();selectedLabel=dragging.id;$('canvas').setPointerCapture(e.pointerId);buildLabels();fillForm();draw();}
});
$('canvas').addEventListener('pointermove',e=>{
  if(!dragging)return;const xy=coords(e),l=label();if(!l)return;
  if(dragging.type==='point') {l.point_x=clamp(xy.x/W,0,1);l.point_y=clamp(xy.y/H,0,1);}
  else {const b=bounds(l);l.x=clamp(xy.x-dragging.dx,0,W-b.width)/W;l.y=clamp(xy.y-dragging.dy,0,H-b.height)/H;}
  info();draw();
});
function finishDrag(){if(dragging){dragging=null;save();}}
$('canvas').addEventListener('pointerup',finishDrag);$('canvas').addEventListener('pointercancel',finishDrag);
$('canvas').addEventListener('keydown',e=>{
  const l=label();if(!editing||!l||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
  e.preventDefault();const step=e.shiftKey?30:6,b=bounds(l);
  l.x=clamp(b.x+(e.key==='ArrowLeft'?-step:e.key==='ArrowRight'?step:0),0,W-b.width)/W;
  l.y=clamp(b.y+(e.key==='ArrowUp'?-step:e.key==='ArrowDown'?step:0),0,H-b.height)/H;draw();info();save();
});
function stopPlayback(){playing=false;cancelAnimationFrame(raf);$('play').textContent='▶ 預覽影片';}
function tick(now) {
  time=(now-startClock)/1000;
  if(time>=total()) {time=Math.max(0,total()-1/30);draw();stopPlayback();if(recording&&recorder?.state==='recording')recorder.stop();return;}
  draw();if(recording)$('recordProgress').value=time/total();
  raf=requestAnimationFrame(tick);
}
$('play').onclick=()=>{if(recording)return;if(playing){stopPlayback();return;}editing=false;playing=true;if(time>=total()-1/30)time=0;startClock=performance.now()-time*1000;$('play').textContent='❚❚ 暫停';raf=requestAnimationFrame(tick);};
$('edit').onclick=()=>{if(recording)return;stopPlayback();editing=true;draw();};
$('seek').oninput=()=>{if(recording)return;stopPlayback();editing=false;time=Number($('seek').value);draw();};
$('duration').onchange=()=>{
  const p=photo(),value=Number($('duration').value); if(value<1||value>20||!Number.isFinite(value)){status('每張照片需為 1～20 秒。',true);return;}
  p.duration=value;
  for(const l of p.labels){l.start=Math.min(l.start,value-.1);l.end=Math.min(l.end,value);l.enter=Math.min(l.enter,l.end-l.start);}
  buildPhotos();fillForm();save();
};
$('duration').oninput=()=>{
  localDirty=true;clearBrowserResult();
  const p=photo(),value=Number($('duration').value);
  if(value<1||value>20||!Number.isFinite(value)){status('每張照片需為 1～20 秒。',true);return;}
  p.duration=value;
  for(const l of p.labels){l.start=Math.min(l.start,value-.1);l.end=Math.min(l.end,value);l.enter=Math.min(l.enter,l.end-l.start);}
  buildPhotos();queueSave();
};
$('fit').onchange=()=>{photo().fit=$('fit').value;editing=true;stopPlayback();fillForm();draw();save();};
for(const key of ['zoom','crop_x','crop_y']) {
  $(key).oninput=()=>{localDirty=true;photo()[key]=Number($(key).value);editing=true;stopPlayback();clearBrowserResult();draw();queueSave();};
  $(key).onchange=()=>save();
}
for(const key of labelFields) {
  $(key).oninput=()=> {
    const l=label();if(!l)return;
    localDirty=true;clearBrowserResult();
    l[key]=key==='line'?$(key).checked:['text','color','background','animation'].includes(key)?$(key).value:Number($(key).value);
    info();status('正在編輯，稍後自動同步…');queueSave();
  };
  $(key).onchange=()=> {
    const l=label();if(!l)return;
    l[key]=key==='line'?$(key).checked:['text','color','background','animation'].includes(key)?$(key).value:Number($(key).value);
    info();save();draw();
  };
}
$('addLabel').onclick=()=>{
  const p=photo();if(!p||p.labels.length>=12)return;
  const l={id:crypto.randomUUID(),text:'裝修項目',x:.12,y:.28,point_x:.58,point_y:.52,font_size:46,color:'#ffffff',background:'#222822',opacity:.88,radius:18,line:true,animation:'left',start:0,enter:.6,end:p.duration};
  p.labels.push(l);selectedLabel=l.id;editing=true;stopPlayback();buildLabels();fillForm();draw();save();
};
$('deleteLabel').onclick=()=>{const p=photo();p.labels=p.labels.filter(l=>l.id!==selectedLabel);selectedLabel=p.labels[0]?.id;buildLabels();fillForm();draw();save();};
$('deletePhoto').onclick=()=>{save('delete_photo',selectedPhoto);};
function movePhoto(delta) {
  const index=photos.findIndex(p=>p.id===selectedPhoto),next=index+delta;if(next<0||next>=photos.length)return;
  [photos[index],photos[next]]=[photos[next],photos[index]];buildPhotos();save();
}
$('moveLeft').onclick=()=>movePhoto(-1);$('moveRight').onclick=()=>movePhoto(1);
function supportedMime() {
  if(!window.MediaRecorder||!$('canvas').captureStream)return null;
  return ['video/mp4;codecs=avc1.42E028','video/mp4;codecs=avc1'].find(m=>MediaRecorder.isTypeSupported(m))||null;
}
function support() {
  const mime=supportedMime();$('browserExport').disabled=!mime||pending||localDirty;
  $('support').textContent=mime?'本機錄製，請保持頁面前景':'此瀏覽器未提供 H.264 MP4，請使用下方 FFmpeg 輸出';
}
function clearBrowserResult() {
  if(recordedURL){URL.revokeObjectURL(recordedURL);recordedURL=null;}
  $('browserResult').hidden=true;$('browserVideo').removeAttribute('src');
}
function lockEditor(locked) {
  for(const element of document.querySelectorAll('button,input,select,textarea'))element.disabled=locked;
  if(!locked){support();buildLabels();fillForm();}
}
$('browserExport').onclick=async()=>{
  if(!validProject()||pending||localDirty)return;
  const mime=supportedMime();if(!mime){status('此瀏覽器不支援 H.264 MP4，請使用 FFmpeg。',true);return;}
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
post('streamlit:componentReady',{apiVersion:1});resize();
