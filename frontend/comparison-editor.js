// 配對與對比畫面只操作既有草稿；來源照片與片段分離但共用同一素材庫。
(function(root){
  const $=id=>document.getElementById(id),clone=v=>JSON.parse(JSON.stringify(v));
  const fields=['before_id','after_id','name','mode','transition','direction','before_time','transition_time','after_time','split','show_line'];
  class ComparisonEditor{
    constructor(hooks){this.hooks=hooks;this.cropSide='after';this.view='combined';
      $('autoPair').onclick=()=>{if(hooks.locked())return;const r=StudioComparison.pair(hooks.photos(),hooks.clips(),()=>crypto.randomUUID());
        hooks.change();hooks.choose(hooks.clips()[0]?.id);hooks.status(`新增${r.added}組配對；兩邊數量差${r.unmatched}張，來源照片全部保留。${r.skipped?'部分配對超過片段／時間上限，請手動調整。':''}`);};
      $('addPair').onclick=()=>this.add();
      for(const key of fields)$('cmp_'+key).oninput=()=>this.change(key);
      $('cmp_crop_side').onchange=()=>{this.cropSide=$('cmp_crop_side').value;this.view=this.cropSide;hooks.refresh();};
      $('viewComparison').onclick=()=>{this.view='combined';hooks.refresh();};
      for(const side of ['before','after'])$(side==='before'?'viewBefore':'viewAfter').onclick=()=>{this.cropSide=side;this.view=side;hooks.refresh();};
      $('copyAfterLabels').onclick=()=>this.importLabels();
      $('addComparisonTitle').onclick=()=>{const c=hooks.current();if(!c||c.labels.length>=12||hooks.locked())return;
        const l={...clone(c.labels[0]||{font_size:46,color:'#ffffff',background:'#222822',opacity:.88,radius:18,layer:10}),
          id:crypto.randomUUID(),text:c.name,x:.06,y:.2,point_x:.5,point_y:.5,line:false,animation:'fade',enter:.3,start:0,end:c.duration};
        delete l.comparison_side;delete l.auto_timing;delete l.comparison_title_version;delete l.exit;delete l.label_timing_version;
        StudioLabelTiming.delay(l,c.duration);c.labels.push(l);hooks.change();};
    }
    options(select,role,value){const previous=value??select.value;select.replaceChildren();
      const empty=document.createElement('option');empty.value='';empty.textContent='請選擇照片';select.append(empty);
      for(const p of this.hooks.photos().filter(p=>p.role===role)){const o=document.createElement('option');o.value=p.id;o.textContent=p.name;select.append(o);}
      const rows=this.hooks.photos().filter(p=>p.role===role);select.value=rows.some(p=>p.id===previous)?previous:(rows[0]?.id||'');}
    library(){const h=this.hooks;$('comparisonBank').hidden=!h.active();if(!h.active())return;
      this.options($('newBefore'),'before');this.options($('newAfter'),'after');$('sourceBank').replaceChildren();
      const used=new Set(h.clips().flatMap(c=>[c.before_id,c.after_id]));let unpaired=0;
      for(const [role,title] of [['before','施工前'],['after','施工後'],['general','未分類（原有照片）']]){
        const group=document.createElement('section'),heading=document.createElement('h4'),list=document.createElement('div');heading.textContent=title;list.className='source-list';group.append(heading,list);
        const rows=h.photos().filter(p=>(p.role||'general')===role);
        for(const p of rows){const card=document.createElement('div'),img=document.createElement('img'),name=document.createElement('span'),controls=document.createElement('div'),select=document.createElement('select');
          card.className='source-card';img.src=p.image;img.alt=p.name;name.textContent=p.name+(used.has(p.id)?' · 已配對':' · 未配對');if(!used.has(p.id))unpaired++;
          for(const [value,text] of [['general','未分類'],['before','施工前'],['after','施工後']]){const o=document.createElement('option');o.value=value;o.textContent=text;select.append(o);}select.value=role;select.setAttribute?.('aria-label',`分類 ${p.name}`);
          select.onchange=()=>{if(h.locked())return;p.role=select.value;this.prune();h.change();this.library();};
          for(const [text,delta] of [['←',-1],['→',1]]){const b=document.createElement('button');b.textContent=text;b.title=`${p.name} ${text==='←'?'前移':'後移'}`;b.onclick=()=>{if(h.locked())return;const all=h.photos(),indices=all.map((row,i)=>({row,i})).filter(v=>(v.row.role||'general')===role),index=indices.findIndex(v=>v.row.id===p.id),other=indices[index+delta];if(!other)return;
            const i=indices[index].i,j=other.i;[all[i],all[j]]=[all[j],all[i]];h.change();this.library();};controls.append(b);}
          const remove=document.createElement('button');remove.textContent='刪除來源';remove.className='danger';remove.title='同時移除引用此照片的配對';remove.onclick=()=>{if(h.locked())return;h.removeSource(p.id);this.prune();h.change();this.library();};
          const replace=document.createElement('button');replace.textContent='替換照片';replace.onclick=()=>{if(!h.locked())h.replace(p.id);};
          controls.append(replace,remove);card.append(img,name,select,controls);list.append(card);}
        if(!rows.length){const empty=document.createElement('p');empty.textContent='尚無照片';list.append(empty);} $('sourceBank').append(group);}
      $('pairSummary').textContent=`${h.clips().length}組配對 · ${unpaired}張來源未配對；多餘照片保留。每張來源可直接替換；分類／刪除來源會移除引用它的配對。`;
    }
    prune(){const h=this.hooks,b=new Map(h.photos().map(p=>[p.id,p])),rows=h.clips();
      for(let i=rows.length-1;i>=0;i--)if(b.get(rows[i].before_id)?.role!=='before'||b.get(rows[i].after_id)?.role!=='after')rows.splice(i,1);}
    add(){const h=this.hooks;if(h.locked())return;
      const b=h.photos().find(p=>p.id===$('newBefore').value),a=h.photos().find(p=>p.id===$('newAfter').value);
      if(!b||!a){h.status('請先選擇施工前與施工後照片。',true);return;}
      if(h.clips().length>=24||h.clips().reduce((n,c)=>n+c.duration,0)+5>120){h.status('最多24組配對、總長120秒，請先調整片段。',true);return;}
      const c=StudioComparison.make(b,a,()=>crypto.randomUUID());h.clips().push(c);h.choose(c.id);h.change();this.library();}
    refresh(){const c=this.hooks.current();$('comparisonForm').hidden=!this.hooks.active()||!c;if(!c||!this.hooks.active())return;
      let start=0;for(const row of this.hooks.clips()){if(row.id===c.id)break;start+=row.duration;}
      $('comparisonClock').textContent=`全片 ${start.toFixed(2)}～${(start+c.duration).toFixed(2)} 秒`;
      this.options($('cmp_before_id'),'before',c.before_id);this.options($('cmp_after_id'),'after',c.after_id);
      for(const key of fields){if(['before_id','after_id'].includes(key)||document.activeElement===$('cmp_'+key))continue;
        const value=key==='after_time'?c.duration-c.before_time-c.transition_time:c[key];
        if(key==='show_line')$('cmp_'+key).checked=value;else $('cmp_'+key).value=typeof value==='number'?Number(value.toFixed(6)):value;}
      $('cmp_crop_side').value=this.cropSide;$('cmp_transition').disabled=this.hooks.locked()||c.mode!=='switch';
      $('cmp_split').disabled=this.hooks.locked()||c.mode!=='split';
      $('cmp_direction').disabled=this.hooks.locked()||c.mode==='split'||(c.mode==='switch'&&c.transition!=='slide');
      for(const key of ['before_time','after_time'])$('cmp_'+key).disabled=this.hooks.locked()||c.mode==='split';
      $('cmp_transition_time').disabled=this.hooks.locked()||c.mode==='split'||(c.mode==='switch'&&c.transition==='cut');}
    change(key){const h=this.hooks,c=h.current();if(!c||h.locked())return;const next=clone(c),e=$('cmp_'+key);
      if(key==='show_line')next.show_line=e.checked;
      else if(['before_id','after_id','name','mode','transition','direction'].includes(key))next[key]=e.value;
      else{const value=Number(e.value);if(!Number.isFinite(value)||value<0){h.status('請輸入有效的對比時間／比例。',true);return;}
        if(key==='split')next.split=Math.max(.1,Math.min(.9,value));
        else{const after=next.duration-next.before_time-next.transition_time;
          if(key==='after_time')next.duration=next.before_time+next.transition_time+Math.round(value*30)/30;
          else{next[key]=Math.round(value*30)/30;next.duration=next.before_time+next.transition_time+after;}}}
      if(key==='before_id'||key==='after_id'){const p=h.photos().find(p=>p.id===next[key]);if(p)next[key==='before_id'?'before_crop':'after_crop']=StudioComparison.crop(p);}
      if(next.mode==='switch'&&next.transition==='cut'){next.duration-=next.transition_time;next.transition_time=0;}
      else if(next.transition_time<1/30&&(next.mode==='reveal'||(next.mode==='switch'&&next.transition!=='cut'))){next.transition_time=1;next.duration+=1;}
      const error=StudioComparison.validate([next],h.photos());if(error){h.status(error,true);return;}
      // 分割模式同時顯示兩側文字；切回順序播放則共用施工前文字的位置。
      if(key==='mode'&&next.mode==='split'&&c.mode!=='split'){
        const title=next.labels.find(l=>l.comparison_side==='after');if(title)title.x=.57;}
      StudioComparison.resize(next,next.duration);Object.assign(c,next);h.change();this.refresh();if(['before_id','after_id'].includes(key))this.library();}
    importLabels(){const h=this.hooks,c=h.current();if(!c||h.locked())return;const p=h.photos().find(p=>p.id===c.after_id);let count=0;
      for(const original of p?.labels||[]){if(c.labels.length>=12)break;if(c.labels.some(l=>l.origin_label_id===original.id))continue;
        const l=clone(original);l.id=crypto.randomUUID();l.origin_label_id=original.id;l.start=Math.min(c.before_time+l.start,c.duration-1/30);l.end=Math.max(l.start+1/30,Math.min(c.before_time+l.end,c.duration));l.enter=Math.min(l.enter,l.end-l.start);
        const image=h.images().get(p.id);if(image){const anchor=StudioComparison.mapPoint(c,p,image,l.point_x,l.point_y),position=StudioComparison.mapPoint(c,p,image,l.x,l.y);l.point_x=anchor.x;l.point_y=anchor.y;l.x=position.x;l.y=position.y;if(anchor.review&&l.source==='gemini')l.needs_review=true;}
        c.labels.push(l);count++;}
      h.change();h.status(`已加入${count}個施工後標籤，既有內容保留；裁切或左右分割後請確認定位點。`);}
    draw(ctx,c,t,editing){const h=this.hooks;
      const side=(name,x=0,width=1080)=>{ctx.fillStyle='#000000';ctx.fillRect(x,0,width,1920);const image=h.images().get(c[name+'_id']);if(!image)return;const box=StudioPhoto.layout(image.naturalWidth,image.naturalHeight,width,1920,c[name+'_crop']);ctx.drawImage(image,box.sx,box.sy,box.sw,box.sh,box.dx+x,box.dy,box.dw,box.dh);};
      if(editing&&this.view!=='combined'){side(this.view);return;}
      const p=StudioComparison.pose(c,t);let divider=null;
      if(c.mode==='split'){side('before',0,p.split);side('after',p.split,1080-p.split);divider=p.split;}
      else if(c.mode==='reveal'){side('before');if(p.reveal_width){ctx.save();ctx.beginPath();ctx.rect(p.reveal_left,0,p.reveal_width,1920);ctx.clip();side('after');ctx.restore();}if(p.progress>0&&p.progress<1)divider=p.divider;}
      else if(c.transition==='fade'){side('before');ctx.save();ctx.globalAlpha=p.progress;side('after');ctx.restore();}
      else if(c.transition==='slide'){side('before',p.before_x);side('after',p.after_x);}
      else side(t<c.before_time?'before':'after');
      if(divider!==null&&c.show_line){ctx.fillStyle='#f4f0e8';ctx.fillRect(divider-2,0,4,1920);}}
    dividerDown(pos){const c=this.hooks.current();return this.hooks.active()&&c?.mode==='split'&&this.view==='combined'&&Math.abs(pos.x-c.split*1080)<30;}
  }
  if(typeof module!=='undefined')module.exports={ComparisonEditor};else root.StudioComparisonUI={ComparisonEditor};
})(typeof window!=='undefined'?window:this);
