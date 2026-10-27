// 快速模式只是一個較小的操作面板；草稿、畫布、同步與輸出仍共用原編輯器。
(function(root){
  const $=id=>document.getElementById(id),T=root.StudioTitle;
  class QuickTitleEditor{
    constructor(h){this.h=h;this.active=false;this.original=false;this.frames={};this.requested=new Set();this.session=null;this.message='';this.boundsCache=new WeakMap();
      this.image=document.createElement('img');this.image.id='quickOriginalImage';this.image.alt='匯入時原始版本預覽';this.image.hidden=true;document.querySelector('.canvas-stage').append(this.image);
      for(const [id,value] of [['qtCoverElement',T.ids.cover],['qtBodyElement',T.ids.body],['qtTitleSource','cover']])if(!$(id).value)$(id).value=value;
      $('qtFull').onclick=()=>{if(!h.locked())h.full();};
      $('qtConfirmLink').onclick=()=>{if(h.locked())return;try{if($('qtCoverElement').value!==T.ids.cover||$('qtBodyElement').value!==T.ids.body)throw new Error('請確認專案已定義的封面與正文標題元素。');const c=h.cover(),dropped=T.ensure(c,$('qtTitleSource').value,true);this.message='已確認專案封面與正文標題關聯；其他文字未修改。'+(dropped?`${dropped}組舊重點字無法可靠對應，請重新確認。`:'');h.change();}catch(e){this.error(e);}};
      $('qtTitle').oninput=()=>this.edit(()=>{const result=T.setText(h.cover(),$('qtTitle').value);this.message=result.dropped?`${result.dropped}組重點字無法可靠對應，已移除，請重新確認。`:'文字已同步；原有顏色只在能可靠對應時保留，請檢查換行。';return result.changed;});
      const capture=()=>{this.selection=root.StudioCover.selection($('qtTitle'),this.selection);$('qtSelection').textContent=this.selection?'已選：'+Array.from(this.selection.value).slice(this.selection.start,this.selection.end).join(''):'先反白上方影片標題中要改色的文字。';};
      for(const event of ['select','pointerup','keyup','blur'])$('qtTitle')['on'+event]=capture;
      for(const side of ['cover','body']){const tag=side==='cover'?'Cover':'Body',style=()=>side==='cover'?h.cover():h.cover().body;
        const effective=()=>side==='body'&&h.cover().body.follow_cover?{...h.cover(),font_size:h.cover().body.font_size}:style();
        $('qt'+tag+'Wrap').oninput=()=>this.edit(()=>{const text=$('qt'+tag+'Wrap').value;if(effective().title===text)return false;T.setBreaks(h.cover(),side,text);return true;});
        $('qt'+tag+'Color').oninput=()=>this.edit(()=>{const value=$('qt'+tag+'Color').value;if(effective().color.toLowerCase()===value.toLowerCase())return false;T.ensure(h.cover());style().color=value;return true;});
        $('qt'+tag+'Font').oninput=()=>this.edit(()=>{const n=Number($('qt'+tag+'Font').value);if(!Number.isInteger(n)||n<36||n>(side==='cover'?160:240))throw new Error('請輸入有效的整數字級。');if(style().font_size===n)return false;T.ensure(h.cover());style().font_size=n;return true;});
        for(const axis of ['X','Y'])$('qt'+tag+axis).oninput=()=>this.edit(()=>{const n=Number($('qt'+tag+axis).value)/100;if(!Number.isFinite(n)||n<0||n>1)throw new Error('位置需為0～100%。');const prior=side==='cover'?(h.cover().shared_title?.['cover_'+axis.toLowerCase()]??(axis==='X'?.5:659/1920)):style()[axis.toLowerCase()];if(Math.abs(prior-n)<1e-5)return false;T.ensure(h.cover());if(side==='cover')h.cover().shared_title['cover_'+axis.toLowerCase()]=n;else style()[axis.toLowerCase()]=n;return true;});
        $('qt'+tag+'Apply').onclick=()=>this.edit(()=>{capture();if(!this.selection)throw new Error('請先反白選取影片標題中的文字。');const r=this.selection,prior=effective(),mapped=T.remap(r.value,prior.title,[{start:r.start,end:r.end,color:$('qt'+tag+'Highlight').value}]);
          if(mapped.ranges.every(r=>prior.highlights.some(p=>p.start===r.start&&p.end===r.end&&p.color.toLowerCase()===r.color.toLowerCase())))return false;
          if(prior.highlights.length>=80)throw new Error('重點字色最多80組。');T.ensure(h.cover());style().highlights.push(...mapped.ranges);return true;});
        $('qt'+tag+'Clear').onclick=()=>this.edit(()=>{if(!effective().highlights.length)return false;T.ensure(h.cover());style().highlights=[];return true;});
      }
      $('qtCover').onclick=()=>h.choose('cover');$('qtBody').onclick=()=>h.choose('body');$('qtClip').onchange=()=>h.choose('body',$('qtClip').value);
      $('qtCompare').onchange=()=>{this.original=$('qtCompare').value==='original';if(this.original)this.requested.delete(h.scene()?.id);h.pause();this.refresh();h.redraw();};
    }
    error(e){this.message=e.message;$('qtMessage').textContent=this.message;this.h.status(this.message,true);}
    edit(fn){if(this.h.locked()||this.original)return;try{const changed=fn();if(changed)this.h.change();}catch(e){this.error(e);}}
    receive(args){const changed=this.session!==args.session;this.session=args.session;if(changed){this.original=false;this.frames={};this.requested.clear();this.message='';}
      const entering=!this.active&&args.ui_mode==='quick';this.active=args.ui_mode==='quick';this.frames=args.quick_frames||{};this.originalScenes=args.quick_scenes||[];
      if(args.quick_error)this.message=args.quick_error;
      document.querySelector('.studio').classList.toggle('quick-mode',this.active);$('quickTitlePanel').hidden=$('quickSettings').hidden=!this.active;
      if(!this.active){this.original=false;this.image.hidden=true;}else if(entering)this.h.choose(this.h.hasCover()?'cover':'body');
      $('qtCompare').value=this.original?'original':'edited';this.refresh();
    }
    refresh(){if(!this.active)return;const h=this.h,c=h.cover();if(!c?.body)return;const linked=!!c.shared_title||c.body.follow_cover;
      $('qtLinkPanel').hidden=linked;$('qtLinkHint').textContent=`此專案沒有明確共用關聯。封面：「${c.title}」；正文：「${c.body.title}」。請確認元素並選擇共同文字來源。`;
      $('qtTitle').disabled=!linked||this.original||h.locked();if(document.activeElement!==$('qtTitle'))$('qtTitle').value=T.title(c);
      for(const side of ['cover','body']){const tag=side==='cover'?'Cover':'Body',s=side==='cover'?c:(c.body.follow_cover?{...c,...{font_size:c.body.font_size}}:c.body);
        for(const [suffix,value] of [['Wrap',s.title],['Color',s.color],['Font',s.font_size],['X',100*(side==='cover'?(c.shared_title?.cover_x??.5):c.body.x)],['Y',100*(side==='cover'?(c.shared_title?.cover_y??659/1920):c.body.y)]]){const input=$('qt'+tag+suffix);if(document.activeElement!==input)input.value=typeof value==='number'?Number(value.toFixed(3)):value;input.disabled=!linked||this.original||h.locked();}
        for(const suffix of ['Apply','Clear','Highlight'])$('qt'+tag+suffix).disabled=!linked||this.original||h.locked();
      }
      const chosen=$('qtClip').value;$('qtClip').replaceChildren();for(const c of h.clips()){const option=document.createElement('option');option.value=c.id;option.textContent=c.name;$('qtClip').append(option);}$('qtClip').value=h.scene()?.type==='cover'?(chosen||h.clips()[0]?.id||''):(h.scene()?.id||chosen);
      $('qtCover').disabled=!h.hasCover();$('qtBody').disabled=!h.clips().length;
      $('play').disabled=$('seek').disabled=this.original;
      $('qtMessage').textContent=this.message;this.compare();
    }
    compare(){this.image.hidden=!this.active||!this.original;if(!this.active)return;
      const id=this.h.scene()?.id,row=this.frames[id];
      if(this.original){if(row){this.image.src=row.image;$('qtCompareHint').textContent=`原始匯入快照 · ${row.name} · 全片 ${row.time.toFixed(2)}秒（固定比較影格）。`;}else{
          this.image.removeAttribute('src');$('qtCompareHint').textContent='正在產生原始快照影格；不修改專案內容。';
          if(id&&!this.requested.has(id)){this.requested.add(id);this.h.original(id);}
        }}else $('qtCompareHint').textContent='修改後版本：畫布顯示目前時間的實際照片／影片、轉場與標題；可播放或移動預覽指針。';
    }
    boundsWarning(side,box,tile,metrics){if(!this.active)return;let r=this.boundsCache.get(tile);if(!r){r=root.StudioBody.alphaBounds(tile);this.boundsCache.set(tile,r);}const safe={left:125,top:205,right:955,bottom:1716};
      const b={left:box.x+r[0],top:box.y+r[1],right:box.x+r[2],bottom:box.y+r[3]},messages=[];
      if(b.left<0||b.top<0||b.right>1080||b.bottom>1920)messages.push('文字超出影片畫面，請調整位置。');
      if(b.left<safe.left||b.top<safe.top||b.right>safe.right||b.bottom>safe.bottom)messages.push('文字超出內圈安全區，請檢查。');
      if(metrics?.font_size<(side==='cover'?this.h.cover():this.h.cover().body).font_size)messages.push(`文字較長，已自動縮至約${metrics.font_size}px，請檢查字級與換行。`);
      if(side==='body'&&!this.h.cover().body.enabled)messages.push('原專案未啟用正文標題；如需新增，請進入完整編輯器。');
      if(side==='cover'&&!this.h.hasCover())messages.push('原專案沒有啟用的照片封面；快速模式不會自動新增封面。');
      $('qt'+(side==='cover'?'Cover':'Body')+'Warning').textContent=messages.join('\n');
    }
  }
  root.StudioQuickTitle={QuickTitleEditor};
})(typeof window!=='undefined'?window:this);
