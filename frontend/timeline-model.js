// 時間軸只投影既有照片／標籤資料；PNG 的開始與長度為全片時間。
(function(root){
  const Comparison=typeof module!=='undefined'?require('./comparison-model.js'):root.StudioComparison;
  const FPS=30,MIN=1/FPS,clamp=(v,a,b)=>Math.max(a,Math.min(b,v)),snap=v=>Math.round(v*FPS)/FPS;
  const total=photos=>photos.reduce((n,p)=>n+p.duration,0);
  function items(photos,overlays=[],prefix=0,bodyTitle=null,bodyLogo=null){
    let offset=prefix;const result=prefix?[{id:'project-cover',type:'cover',source:'project-cover',start:0,duration:prefix,layer:0,name:'片頭封面'}]:[];
    for(const p of photos){
      result.push({id:p.id,type:p.type==='comparison'?'comparison':'photo',source:p.id,start:offset,duration:p.duration,layer:0,name:p.name});
      for(const l of p.labels)if(l.end>l.start)result.push({id:l.id,type:'label',source:p.id,start:offset+l.start,
        duration:l.end-l.start,layer:l.layer??10,name:l.text});
      offset+=p.duration;
    }
    if(bodyTitle)result.push(bodyTitle);
    if(bodyLogo)result.push(bodyLogo);
    return result.concat(overlays.map(o=>({...o,name:o.name||'PNG'})));
  }
  function fitAnimations(o){
    const sum=o.enter+o.exit;if(sum>o.duration){o.enter*=o.duration/sum;o.exit*=o.duration/sum;}
  }
  function clampOverlays(overlays,length){
    if(length<MIN){overlays.splice(0);return;}
    for(const o of overlays){o.start=clamp(o.start,0,length-MIN);o.duration=clamp(o.duration,MIN,length-o.start);fitAnimations(o);}
  }
  function photoDuration(p,value){
    if(p.type==='comparison'){Comparison.resize(p,value);return;}
    p.duration=clamp(snap(value),1,20);
    for(const l of p.labels){l.start=Math.min(l.start,p.duration-MIN);l.end=Math.max(l.start+MIN,Math.min(l.end,p.duration));l.enter=Math.min(l.enter,l.end-l.start);}
  }
  function edit(item,mode,delta,photos,overlays,prefix=0,body=null){
    if(item.type==='cover')return;
    const bodyItem=['body_title','body_logo'].includes(item.type);
    if(bodyItem&&!body)return;
    delta=snap(delta);
    const p=photos.find(p=>p.id===item.source);
    if(['photo','comparison'].includes(item.type)){
      if(mode==='move'){
        const t=clamp(item.start+delta,prefix,total(photos)+prefix-MIN),tracks=items(photos,[],prefix).filter(i=>['photo','comparison'].includes(i.type));
        const target=Math.max(0,tracks.findIndex(i=>t<i.start+i.duration)),index=photos.findIndex(p=>p.id===item.id);
        if(index!==target){const [moved]=photos.splice(index,1);photos.splice(target,0,moved);}
      }else if(mode==='right')photoDuration(p,item.duration+delta);
      else{
        const index=photos.indexOf(p),previous=photos[index-1];
        if(previous){const pair=previous.duration+p.duration,d=clamp(delta,Math.max(1-previous.duration,p.duration-20),Math.min(20-previous.duration,p.duration-1));
          photoDuration(previous,previous.duration+d);photoDuration(p,pair-previous.duration);}
      }
      clampOverlays(overlays,total(photos)+prefix);return;
    }
    const startBound=bodyItem?prefix:item.type==='label'?items(photos,[],prefix).find(i=>['photo','comparison'].includes(i.type)&&i.id===p.id).start:0;
    const endBound=item.type==='label'?startBound+p.duration:total(photos)+prefix;
    let start=item.start,end=item.start+item.duration;
    if(mode==='move'){start=clamp(start+delta,startBound,endBound-item.duration);end=start+item.duration;}
    else if(mode==='left')start=clamp(start+delta,startBound,end-MIN);
    else end=clamp(end+delta,start+MIN,endBound);
    if(item.type==='label'){const l=p.labels.find(l=>l.id===item.id);l.start=start-startBound;l.end=end-startBound;l.enter=Math.min(l.enter,l.end-l.start);if(l.exit)l.exit=Math.min(l.exit,l.end-l.start);if(l.comparison_side)l.auto_timing=false;}
    else if(item.type==='body_title'){body.auto_timing=false;body.start=start;body.end=end;}
    else if(item.type==='body_logo'){body.logo_auto_timing=false;body.logo_start=start;body.logo_end=end;}
    else {const o=overlays.find(o=>o.id===item.id);o.start=start;o.duration=end-start;fitAnimations(o);}
  }
  function lanes(clips){
    const ends=[],result=[];
    for(const item of [...clips].sort((a,b)=>a.start-b.start)){
      let lane=ends.findIndex(end=>end<=item.start+1e-6);if(lane<0)lane=ends.length;
      ends[lane]=item.start+item.duration;result.push({item,lane});
    }
    return {rows:Math.max(1,ends.length),clips:result};
  }
  const api={FPS,MIN,snap,total,items,photoDuration,clampOverlays,fitAnimations,edit,lanes};
  if(typeof module!=='undefined')module.exports=api;else root.StudioTimeline=api;
})(typeof window!=='undefined'?window:this);
