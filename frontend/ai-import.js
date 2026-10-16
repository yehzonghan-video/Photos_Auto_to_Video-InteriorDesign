// AI 座標以完整原圖為基準，使用現有照片構圖模組換算；不接觸後端或 API。
(function(root) {
  const timing=typeof module!=='undefined'?require('./label-timing.js'):root.StudioLabelTiming;
  const clamp=v=>Math.max(0,Math.min(1,v));
  function convert(item, photo, image, layout, uuid) {
    const W=1080,H=1920,iw=image.naturalWidth,ih=image.naturalHeight;
    const b=layout(iw,ih,W,H,photo);
    const [y0,x0,y1,x1]=item.box_2d;
    const left=Math.max(x0*iw,b.sx),right=Math.min(x1*iw,b.sx+b.sw);
    const top=Math.max(y0*ih,b.sy),bottom=Math.min(y1*ih,b.sy+b.sh);
    if(right<=left||bottom<=top)return null;
    let ax=item.anchor_x*iw,ay=item.anchor_y*ih,review=item.needs_review;
    if(ax<left||ax>right||ay<top||ay>bottom){ax=(left+right)/2;ay=(top+bottom)/2;review=true;}
    const position=(x,y)=>({x:clamp((b.dx+(x-b.sx)*b.dw/b.sw)/W),y:clamp((b.dy+(y-b.sy)*b.dh/b.sh)/H)});
    const anchor=position(ax,ay),text=position(item.suggested_label_x*iw,item.suggested_label_y*ih);
    const label={id:uuid(),text:item.label,description:item.description,category:item.category,
      confidence_level:item.confidence_level,needs_review:review,source:'gemini',ai_item_id:item.ai_item_id,
      x:text.x,y:text.y,point_x:anchor.x,point_y:anchor.y,font_size:46,color:'#ffffff',background:'#222822',
      opacity:.88,radius:18,line:true,animation:'left',start:0,enter:Math.min(.6,photo.duration),end:photo.duration};
    timing.delay(label,photo.duration);return label;
  }
  function importBatches(draft,batches,images,layout,uuid) {
    let added=0;const messages=[];
    draft.imported ||= [];
    for(const batch of batches||[]) {
      if(draft.imported.includes(batch.id))continue;
      const photo=draft.rows.find(p=>p.id===batch.photo_id),image=images.get(batch.photo_id);
      // 拒絕的批次也去重；使用者可減少選取後再次送出新的批次。
      draft.imported.push(batch.id);
      if(!photo||!image||photo.content_hash!==batch.content_hash){messages.push('照片已刪除或替換，AI 建議未匯入。');continue;}
      const existing=new Set(photo.labels.map(l=>l.ai_item_id));let outside=0;
      const labels=batch.items.filter(item=>!existing.has(item.ai_item_id)).map(item=> {
        const label=convert(item,photo,image,layout,uuid);if(!label)outside++;return label;
      }).filter(Boolean);
      const room=Math.max(0,12-photo.labels.length);
      if(labels.length>room&&!batch.automatic){messages.push(`${photo.name}：此批超出12個標籤上限，未匯入；請減少選取後重送。`);continue;}
      const accepted=labels.slice(0,room),overflow=labels.length-accepted.length;
      photo.labels.push(...accepted);added+=accepted.length;
      messages.push(`${photo.name}：新增 ${accepted.length} 個 AI 標籤${outside?`；${outside} 個物件在裁切外，未匯入`:''}${overflow?`；${overflow} 個因12個標籤上限未加入，請刪除不需要的標籤後重新分析`:''}。`);
    }
    return {added,messages};
  }
  const api={convert,importBatches};
  if(typeof module!=='undefined')module.exports=api;else root.StudioAI=api;
})(typeof window!=='undefined'?window:this);
