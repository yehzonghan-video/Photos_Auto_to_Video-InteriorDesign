(function(root){
  const $=id=>document.getElementById(id);
  class TourEditor{
    constructor(h){this.h=h;this.tags=new Map();this.videos=new Map();this.selectedRoom=null;this.lastPlan=undefined;
      $('tourAddClip').onclick=()=>{if(h.locked())return;const id=$('tourSource').value,p=h.photos().find(p=>p.id===id)||this.videos.get(id);if(!p)return;
        const c=StudioTour.make(p,this.videos.has(id)?'video':'photo',()=>crypto.randomUUID());if(h.data().clips.length>=40||h.data().clips.reduce((n,c)=>n+c.duration,0)+c.duration+h.prefix()>120){h.status('最多40個片段、含封面120秒。',true);return;}h.data().clips.push(c);h.change();};
      $('tourMap').addEventListener('pointerdown',e=>this.point(e));
      $('tourRoomNew').onclick=()=>{this.selectedRoom=null;$('tourRoomName').value='新房間';this.refresh();};
      $('tourRoomName').oninput=()=>{const r=h.data().rooms.find(r=>r.id===this.selectedRoom);if(r&&$('tourRoomName').value.trim()){r.name=$('tourRoomName').value.slice(0,40);h.change();}};
      $('tourRoomDelete').onclick=()=>{if(!this.selectedRoom)return;const n=h.data().clips.filter(c=>c.room_id===this.selectedRoom).length;
        if(n){$('tourDeleteHint').textContent=`${n}個片段使用此房間，刪除後改為未指定。`;$('tourDeleteConfirm').hidden=$('tourDeleteCancel').hidden=false;}else this.removeRoom();};
      $('tourDeleteConfirm').onclick=()=>this.removeRoom();$('tourDeleteCancel').onclick=()=>{$('tourDeleteConfirm').hidden=$('tourDeleteCancel').hidden=true;};
      for(const [id,key] of [['tourVisible','visible'],['tourSize','size'],['tourOpacity','opacity'],['tourDot','dot_size']])$(id).oninput=()=>{if(h.locked())return;h.data()[key]=id==='tourVisible'?$(id).checked:Number($(id).value);h.change();};
      $('tourClipRoom').onchange=()=>{const c=h.current();if(c?.type==='tour_clip'&&!h.locked()){c.room_id=$('tourClipRoom').value||null;h.change();}};
      for(const id of ['tourIn','tourOut'])$(id).onchange=()=>{const c=h.current(),v=this.videos.get(c?.source);if(!v||h.locked())return;try{StudioTour.trim(c,Number($('tourIn').value),Number($('tourOut').value),v.duration);h.change();}catch(error){h.status(error.message,true);this.refresh();}};
      $('tourMute').onchange=()=>{const c=h.current();if(c?.kind==='video'&&!h.locked()){c.muted=$('tourMute').checked;h.change();}};
      $('tourVolume').oninput=()=>{const c=h.current();if(c?.kind==='video'&&!h.locked()){c.volume=Number($('tourVolume').value);h.change();}};
    }
    async receive(plan,videos,layout,loadImage){const generation=(this.generation||0)+1;this.generation=generation;StudioTour.configure(layout);
      if(this.h.data().plan_id&&this.h.data().plan_id!==plan?.id)for(const r of this.h.data().rooms)r.needs_review=true;
      this.h.data().plan_id=plan?.id||null;
      const image=plan?(this.planImage?.src===plan.image?this.planImage:await loadImage(plan.image)):null;if(generation!==this.generation)return;
      this.plan=plan;this.lastPlan=plan?.id;this.planImage=image;this.videos=new Map(videos.map(v=>[v.id,v]));
      for(const [id,tag] of this.tags)if(!this.videos.has(id)){tag.pause();tag.removeAttribute('src');tag.load?.();this.tags.delete(id);}
      for(const v of videos){let tag=this.tags.get(v.id);if(!tag){tag=document.createElement('video');tag.preload='auto';tag.playsInline=true;tag.muted=true;tag.crossOrigin='anonymous';tag.addEventListener('seeked',()=>this.h.redraw());tag.addEventListener('loadeddata',()=>this.h.redraw());tag.addEventListener('error',()=>this.h.status('影片預覽無法讀取，請用上方「重新整理素材連結」，或下方FFmpeg輸出。',true));this.tags.set(v.id,tag);}if(tag.src!==v.src)tag.src=v.src;}
      for(const c of this.h.data().clips)if(c.kind==='video')c.source_duration=this.videos.get(c.source)?.duration||c.out;
    }
    removeRoom(){if(this.h.locked())return;const t=this.h.data(),id=this.selectedRoom;t.rooms=t.rooms.filter(r=>r.id!==id);for(const c of t.clips)if(c.room_id===id)c.room_id=null;this.selectedRoom=null;$('tourDeleteConfirm').hidden=$('tourDeleteCancel').hidden=true;$('tourDeleteHint').textContent='房間已刪除，片段保留並改為未指定。';this.h.change();}
    point(e){if(!this.planImage||this.h.locked())return;const canvas=$('tourMap'),r=canvas.getBoundingClientRect(),b=this.mapBox,x=(e.clientX-r.left)*canvas.width/r.width,y=(e.clientY-r.top)*canvas.height/r.height;
      if(!b||x<b.x||y<b.y||x>b.x+b.w||y>b.y+b.h)return;const t=this.h.data();let room=t.rooms.find(r=>r.id===this.selectedRoom);
      if(!room){const name=$('tourRoomName').value.trim();if(!name||t.rooms.length>=30){this.h.status('請輸入房名；最多30個房間。',true);return;}room={id:crypto.randomUUID(),name:name.slice(0,40)};t.rooms.push(room);this.selectedRoom=room.id;}
      Object.assign(room,{x:(x-b.x)/b.w,y:(y-b.y)/b.h,needs_review:false});this.h.change();}
    refresh(){const h=this.h,t=h.data();$('tourPanel').hidden=!h.active();$('tourClipSettings').hidden=!h.active()||h.current()?.type!=='tour_clip';if(!h.active())return;
      const chosen=$('tourSource').value;$('tourSource').replaceChildren();for(const p of [...h.photos(),...this.videos.values()]){const o=document.createElement('option');o.value=p.id;o.textContent=p.name;$('tourSource').append(o);}$('tourSource').value=chosen||h.photos()[0]?.id||this.videos.keys().next().value||'';
      for(const [id,key] of [['tourVisible','visible'],['tourSize','size'],['tourOpacity','opacity'],['tourDot','dot_size']]){if(id==='tourVisible')$(id).checked=t[key];else $(id).value=t[key];}
      $('tourRoomList').replaceChildren();for(const r of t.rooms){const b=document.createElement('button');b.textContent=`${r.name}${r.needs_review?' · 待定位':''} · ${t.clips.filter(c=>c.room_id===r.id).length}片段`;b.onclick=()=>{this.selectedRoom=r.id;$('tourRoomName').value=r.name;this.refresh();};$('tourRoomList').append(b);}$('tourRoomDelete').disabled=!this.selectedRoom;
      $('tourUsage').textContent=this.selectedRoom?'使用片段：'+(t.clips.map((c,i)=>c.room_id===this.selectedRoom?`${i+1}. ${c.name}`:null).filter(Boolean).join('、')||'尚未指定'):'';
      const omitted=[...h.photos(),...this.videos.values()].filter(s=>!t.seen_sources.includes(s.id)&&!t.clips.some(c=>c.source===s.id));
      $('tourSourceHint').textContent=omitted.length?`${omitted.length}個來源尚未加入時間軸（最多40片段、含封面120秒）。可縮短片段後，從上方重用來源加入。`:'';
      const canvas=$('tourMap'),ctx=canvas.getContext('2d');ctx.fillStyle='#e9e5dc';ctx.fillRect(0,0,canvas.width,canvas.height);
      if(this.planImage){const im=this.planImage,s=Math.min(canvas.width/im.naturalWidth,canvas.height/im.naturalHeight),w=im.naturalWidth*s,h=im.naturalHeight*s,x=(canvas.width-w)/2,y=(canvas.height-h)/2;this.mapBox={x,y,w,h};ctx.drawImage(im,x,y,w,h);for(const r of t.rooms){ctx.beginPath();ctx.fillStyle=r.needs_review?'#888':'#e43f35';ctx.arc(x+r.x*w,y+r.y*h,7,0,Math.PI*2);ctx.fill();ctx.fillStyle='#111';ctx.fillText(r.name,x+r.x*w+9,y+r.y*h);}}
      else{this.mapBox=null;ctx.fillStyle='#555';ctx.fillText('請先在上方上傳平面圖',16,30);}
      const c=h.current();if(c?.type==='tour_clip'){$('tourClipRoom').replaceChildren();for(const r of [{id:'',name:'未指定（不顯示位置點）'},...t.rooms]){const o=document.createElement('option');o.value=r.id;o.textContent=r.name+(r.needs_review?' · 待定位':'');$('tourClipRoom').append(o);}$('tourClipRoom').value=c.room_id||'';$('tourVideoSettings').hidden=c.kind!=='video';$('tourIn').value=Number(c.in.toFixed(3));$('tourOut').value=Number(c.out.toFixed(3));$('tourMute').checked=c.muted;$('tourVolume').value=c.volume;}
    }
    stop(except=null){for(const [id,v] of this.tags)if(id!==except){v.pause();v.muted=true;}}
    drawVideo(ctx,c,t,playing){const tag=this.tags.get(c.source);this.stop(c.source);if(!tag)return;const target=Math.min(c.out-1/30,c.in+Math.max(0,t));tag.muted=!playing||c.muted;tag.volume=c.volume;
      if(Math.abs(tag.currentTime-target)>(playing ? .15 : 1/60))tag.currentTime=target;if(playing&&tag.paused)tag.play()?.catch(()=>this.h.status('影片預覽播放受阻，請重按播放或使用下方FFmpeg輸出。',true));else if(!playing)tag.pause();
      if(tag.readyState<2||tag.seeking)return;const b=StudioPhoto.layout(tag.videoWidth,tag.videoHeight,1080,1920,c.crop);ctx.drawImage(tag,b.sx,b.sy,b.sw,b.sh,b.dx,b.dy,b.dw,b.dh);}
    drawPlan(ctx,c){const t=this.h.data();if(!this.planImage||!t.visible)return;const b=StudioTour.box(this.plan,t),p=b.pad,r=StudioTour.room(t,c.room_id);
      const key=JSON.stringify([this.plan.id,b,t.dot_size,r]);
      if(key!==this.layerKey){const canvas=document.createElement('canvas');canvas.width=1080;canvas.height=1920;const layer=canvas.getContext('2d');
        layer.fillStyle='rgba(255,255,255,.843137)';layer.beginPath();layer.roundRect(b.x-p,b.y-p,b.w+p*2,b.h+p*2,12);layer.fill();layer.drawImage(this.planImage,b.x,b.y,b.w,b.h);
        if(r){layer.beginPath();layer.arc(b.x+r.x*b.w,b.y+r.y*b.h,t.dot_size,0,Math.PI*2);layer.fillStyle='#e43f35';layer.fill();layer.strokeStyle='white';layer.lineWidth=3;layer.stroke();}this.layer=canvas;this.layerKey=key;}
      ctx.save();ctx.globalAlpha=t.opacity;ctx.drawImage(this.layer,0,0);ctx.restore();}
  }
  root.StudioTourUI={TourEditor};
})(typeof window!=='undefined'?window:this);
