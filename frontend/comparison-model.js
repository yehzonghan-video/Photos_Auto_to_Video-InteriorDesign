// 與 Python 相同的複合片段模型與逐幀姿態，開始時間由現有時間軸推導。
(function(root){
  const Photo=typeof module!=='undefined'?require('./photo-layout.js'):root.StudioPhoto;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v)),snap=v=>Math.round(v*30)/30;
  const crop=p=>({fit:p.fit||'contain',zoom:p.zoom??1,crop_x:p.crop_x??.5,crop_y:p.crop_y??.5});
  function titleTimes(c){for(const l of c.labels){if(!l.auto_timing||!l.comparison_side)continue;
    l.start=c.mode==='split'||l.comparison_side==='before'?0:c.before_time;
    l.end=c.mode==='split'||l.comparison_side==='after'?c.duration:c.before_time;
    // 前停留可為0：空區間不會繪製，也不會多留一影格與施工後重疊。
    l.end=Math.max(l.start,l.end);l.enter=Math.min(l.enter,l.end-l.start);}
    alignTitles(c);}
  function alignTitles(c,source){if(c.mode==='split')return;
    const titles=c.labels.filter(l=>l.comparison_side),base=source||titles.find(l=>l.comparison_side==='before')||titles[0];
    if(base)for(const l of titles){l.x=base.x;l.y=base.y;}}
  function upgradeTitles(c){let changed=false;
    for(const l of c.labels){if(!l.comparison_side||l.comparison_title_version===1)continue;
      Object.assign(l,{opacity:0,radius:0,line:false,animation:'none',enter:0,comparison_title_version:1});changed=true;}
    if(changed)titleTimes(c);return changed;}
  function visibleTitle(c,l,t,view='combined'){
    if(!l.comparison_side)return true;
    if(view!=='combined')return l.comparison_side===view;
    return c.mode==='split'||l.comparison_side===(t<c.before_time?'before':'after');}
  function make(before,after,id){const c={id:id(),type:'comparison',before_id:before.id,after_id:after.id,name:`${before.name||'施工前'} → ${after.name||'施工後'}`.slice(0,80),
    mode:'switch',transition:'fade',direction:'ltr',duration:5,before_time:2,transition_time:1,split:.5,show_line:true,
    before_crop:crop(before),after_crop:crop(after),labels:[]};
    for(const [side,text] of [['before','施工前'],['after','施工後']])c.labels.push({id:id(),text,x:.06,y:.08,
      point_x:.5,point_y:.5,font_size:46,color:'#ffffff',background:'#222822',opacity:0,radius:0,line:false,
      animation:'none',start:0,end:5,enter:0,layer:10,comparison_side:side,auto_timing:true,comparison_title_version:1});
    titleTimes(c);return c;}
  function resize(c,value){const length=clamp(snap(value),1,20),ratio=length/c.duration;
    c.before_time*=ratio;c.transition_time*=ratio;c.duration=length;
    const phase=c.before_time+c.transition_time;if(phase>length-1/30){const factor=(length-1/30)/phase;c.before_time*=factor;c.transition_time*=factor;}
    for(const l of c.labels){l.start=Math.min(l.start,length-1/30);l.end=clamp(l.end,l.start+1/30,length);l.enter=Math.min(l.enter,l.end-l.start);}
    titleTimes(c);}
  function pair(photos,clips,id){const b=photos.filter(p=>p.role==='before'),a=photos.filter(p=>p.role==='after');let added=0,skipped=0;
    for(let i=0;i<Math.min(b.length,a.length);i++){
      if(clips.some(c=>c.before_id===b[i].id&&c.after_id===a[i].id))continue;
      if(clips.length>=24||clips.reduce((n,c)=>n+c.duration,0)+5>120){skipped++;continue;}
      clips.push(make(b[i],a[i],id));added++;}
    return {added,unmatched:Math.abs(b.length-a.length),skipped};}
  function pose(c,t,width=1080){const f=c.transition_time?clamp((t-c.before_time)/c.transition_time,0,1):Number(t>=c.before_time),p=f*f*(3-2*f);
    const count=Math.round(width*p),rtl=c.direction==='rtl';return {progress:p,split:Math.round(width*c.split),
      reveal_left:rtl?width-count:0,reveal_width:count,divider:rtl?width-count:count,
      before_x:rtl?-count:count,after_x:rtl?width-count:count-width};}
  function validate(clips,photos){if(clips.length>24)return '最多24組對比片段。';const bank=new Map(photos.map(p=>[p.id,p])),ids=new Set();
    if(clips.reduce((n,c)=>n+c.duration,0)>120)return '對比影片最多120秒。';
    for(const c of clips){if(c.type!=='comparison'||!c.name?.trim()||c.name.length>80)return '對比名稱需為1～80字。';if(ids.has(c.id)||bank.get(c.before_id)?.role!=='before'||bank.get(c.after_id)?.role!=='after')return '對比照片已刪除或分類改變，請重新配對。';ids.add(c.id);
      if(!['switch','split','reveal'].includes(c.mode)||!['cut','fade','slide'].includes(c.transition)||!['ltr','rtl'].includes(c.direction))return '對比動畫設定不正確。';
      if(![c.duration,c.before_time,c.transition_time,c.split].every(Number.isFinite)||c.duration<1||c.duration>20||c.before_time<0||c.transition_time<0||c.before_time+c.transition_time>c.duration-1/30+1e-7||c.split<.1||c.split>.9||
        (c.mode==='reveal'&&c.transition_time<1/30-1e-7)||(c.mode==='switch'&&c.transition==='cut'&&c.transition_time!==0))return '請確認對比停留時間、轉場與分割比例。';
      for(const side of ['before','after']){const p=c[side+'_crop'];if(!p||!['contain','cover'].includes(p.fit)||!Number.isFinite(p.zoom)||p.zoom<1||p.zoom>3||!Number.isFinite(p.crop_x)||p.crop_x<0||p.crop_x>1||!Number.isFinite(p.crop_y)||p.crop_y<0||p.crop_y>1)return '對比裁切設定不正確。';}}
    return null;}
  function mapPoint(c,source,image,x,y){const w=image.naturalWidth,h=image.naturalHeight,
    old=Photo.layout(w,h,1080,1920,source),split=c.mode==='split'?Math.round(c.split*1080):0,
    box=Photo.layout(w,h,1080-split,1920,c.after_crop),px=old.sx+(x*1080-old.dx)/old.dw*old.sw,py=old.sy+(y*1920-old.dy)/old.dh*old.sh;
    const tx=split+box.dx+(px-box.sx)/box.sw*box.dw,ty=box.dy+(py-box.sy)/box.sh*box.dh;
    return {x:clamp(tx,split,1080)/1080,y:clamp(ty,0,1920)/1920,review:px<box.sx||px>box.sx+box.sw||py<box.sy||py>box.sy+box.sh};}
  const api={make,crop,resize,titleTimes,alignTitles,upgradeTitles,visibleTitle,pair,pose,mapPoint,validate};if(typeof module!=='undefined')module.exports=api;else root.StudioComparison=api;
})(typeof window!=='undefined'?window:this);
