// 封面與局部字色只操作本地草稿；套用／輸出時沿用既有整批同步。
(function(root){
  let layout=typeof module!=='undefined'?require('./cover-layout.json'):null;
  const T=typeof module!=='undefined'?require('./title-model.js'):root.StudioTitle;
  const $=id=>document.getElementById(id),duration=c=>c?.enabled===true ? layout.duration : 0;
  function configure(value){if(value)layout=value;}
  function key(c){return JSON.stringify([c.title,c.color,c.font_size,c.highlights,2,layout?.title]);}
  function colors(c){const result=Array.from(c.title,()=>c.color);for(const r of c.highlights)for(let i=r.start;i<r.end;i++)result[i]=r.color;return result;}
  function selection(input,previous){
    const start=Array.from(input.value.slice(0,input.selectionStart||0)).length,end=Array.from(input.value.slice(0,input.selectionEnd||0)).length;
    // 色盤取得焦點後，瀏覽器可能回報收合選取；保留同一段文字的有效範圍。
    if(end>start)return {start,end,value:input.value};
    return previous?.value===input.value?previous:null;
  }
  function ensureSource(c,photos){if(!c||photos.some(p=>p.id===c.photo_id))return false;
    c.photo_id=(photos.find(p=>p.role==='after')||photos[0])?.id||'';return true;}
  function validate(c,photos,maxFontSize=160){if(!c)return null;
    if(typeof c.enabled!=='boolean'||typeof c.title!=='string'||(c.enabled&&!c.title.trim())||Array.from(c.title.replace(/\n/g,'')).length>80||c.title.split('\n').length>6)return '封面標題需為1～80字，最多6行。';
    if(c.enabled&&photos.length&&!photos.some(p=>p.id===c.photo_id))return '請選擇封面照片。';
    const hex=v=>/^#[0-9a-fA-F]{6}$/.test(v);
    if(!hex(c.color)||!Number.isInteger(c.font_size)||c.font_size<36||c.font_size>maxFontSize||!Array.isArray(c.highlights)||c.highlights.length>80)return '封面樣式設定不正確。';
    for(const r of c.highlights)if(!Number.isInteger(r.start)||!Number.isInteger(r.end)||r.start<0||r.end<=r.start||r.end>Array.from(c.title).length||!hex(r.color))return '請重新選取要改色的標題文字。';
    return null;}
  function raster(c,createCanvas,box=layout.title,maxFontSize=160){const canvas=createCanvas();canvas.width=box.width;canvas.height=box.height;
    const ctx=canvas.getContext('2d'),chars=Array.from(c.title);let size=Number.isFinite(c.font_size)?Math.max(12,Math.min(maxFontSize,c.font_size)):120,lines,step;
    while(true){ctx.font=`${size}px "Microsoft JhengHei", "Noto Sans CJK TC", sans-serif`;lines=[];let line=[];
      chars.forEach((char,index)=>{if(char==='\n'){lines.push(line);line=[];return;}
        if(line.length&&ctx.measureText(line.map(v=>v.char).join('')+char).width>box.width-24){lines.push(line);line=[];}line.push({char,index});});lines.push(line);
      step=Math.trunc(size*1.35);if(lines.length*step<=box.height-24||size<=12)break;size--;}
    const palette=colors(c);ctx.textBaseline='alphabetic';ctx.strokeStyle='#000000';ctx.lineWidth=4;ctx.lineJoin='round';
    lines.forEach((line,row)=>{const left=(box.width-ctx.measureText(line.map(v=>v.char).join('')).width)/2;let prefix='';
      for(const {char,index} of line){const x=left+ctx.measureText(prefix).width,y=(box.height-lines.length*step)/2+row*step+size;
        ctx.strokeText(char,x,y);ctx.fillStyle=palette[index];ctx.fillText(char,x,y);prefix+=char;}});canvas.titleMetrics={font_size:size,lines:lines.length};return canvas;}
  function mountGuide(element){element.innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920" aria-hidden="true"><g transform="translate(${layout.origin.x} ${layout.origin.y})" fill="none" stroke="white" stroke-opacity=".8" stroke-width="8">${[layout.title,layout.photo].map(b=>`<rect x="${b.x}" y="${b.y}" width="${b.width}" height="${b.height}"/>`).join('')}</g></svg>`;}
  class CoverEditor{
    constructor(hooks){this.hooks=hooks;this.template=null;this.calibrated=null;this.local=null;this.selection=null;this.scene=null;
      $('coverEnabled').onchange=()=>{const c=hooks.cover();if(!c||hooks.locked())return;const prior=duration(c);c.enabled=$('coverEnabled').checked;
        const delta=duration(c)-prior;for(const slot of hooks.slots())for(const o of slot)o.start=Math.max(0,o.start+delta);
        for(const k of ['','logo_'])if(c.body?.[k+'auto_timing']===false){c.body[k+'start']=Math.max(0,c.body[k+'start']+delta);c.body[k+'end']=Math.max(0,c.body[k+'end']+delta);}
        hooks.change();};
      $('coverTitle').oninput=()=>{const c=hooks.cover();if(!c||hooks.locked())return;
        if(c.shared_title){try{T.setDisplay(c,'cover',$('coverTitle').value);}catch(e){hooks.status(e.message,true);return;}}else {c.title=$('coverTitle').value;c.highlights=[];}
        this.selection=null;hooks.change();};
      const capture=()=>{this.selection=selection($('coverTitle'),this.selection);
        $('coverSelection').textContent=this.selection?'已選：'+Array.from(this.selection.value).slice(this.selection.start,this.selection.end).join(''):'先在標題輸入框反白要改色的文字';};
      for(const event of ['select','pointerup','keyup','blur'])$('coverTitle')['on'+event]=capture;
      for(const [id,field] of [['coverPhoto','photo_id'],['coverColor','color'],['coverSize','font_size']])$(id).oninput=()=>{const c=hooks.cover();if(!c||hooks.locked())return;c[field]=field==='font_size'?Number($(id).value):$(id).value;hooks.change();};
      $('coverApplyColor').onclick=()=>{const c=hooks.cover();if(!c||hooks.locked())return;capture();const r=this.selection;
        if(!r||r.end<=r.start){hooks.status('請先反白選取要改色的標題文字。',true);return;}
        if(c.highlights.length>=80){hooks.status('局部字色最多80組，請先清除後重新設定。',true);return;}
        c.highlights.push({start:r.start,end:r.end,color:$('coverSelectedColor').value});hooks.change();};
      $('coverClearColors').onclick=()=>{const c=hooks.cover();if(!c||hooks.locked())return;c.highlights=[];hooks.change();};
      $('editCover').onclick=()=>{if(hooks.cover()?.enabled&&!hooks.locked())hooks.choose();};
    }
    refresh(){const c=this.hooks.cover();$('coverPanel').hidden=!c;if(!c)return;
      const viewing=this.hooks.viewing?.()||false;if(viewing!==this.scene){$('coverPanel').open=viewing;this.scene=viewing;}
      $('coverEnabled').checked=c.enabled;
      for(const [id,field] of [['coverTitle','title'],['coverColor','color'],['coverSize','font_size']])if(document.activeElement!==$(id)&&String($(id).value)!==String(c[field]))$(id).value=c[field];
      $('coverPhoto').replaceChildren();for(const p of this.hooks.photos()){const option=document.createElement('option');option.value=p.id;option.textContent=p.name;$('coverPhoto').append(option);}$('coverPhoto').value=c.photo_id;
      $('coverColorPreview').replaceChildren();const palette=colors(c);Array.from(c.title).forEach((char,i)=>{const span=document.createElement('span');span.textContent=char;span.style.color=palette[i];$('coverColorPreview').append(span);});
    }
    tile(){const c=this.hooks.cover(),titleKey=key(c);if(this.calibrated?.key===titleKey)return this.calibrated.image;
      if(this.local?.key!==titleKey)this.local={key:titleKey,image:raster(c,()=>document.createElement('canvas'))};return this.local.image;}
    draw(ctx){const c=this.hooks.cover();if(!c)return;
      ctx.save();ctx.translate(layout.origin.x,layout.origin.y);
      if(this.template){const scale=Math.min(layout.width/this.template.naturalWidth,layout.height/this.template.naturalHeight);ctx.drawImage(this.template,(layout.width-this.template.naturalWidth*scale)/2,0,this.template.naturalWidth*scale,this.template.naturalHeight*scale);}
      const image=this.hooks.images().get(c.photo_id),box=layout.photo;
      if(image){const fit=StudioPhoto.layout(image.naturalWidth,image.naturalHeight,box.width,box.height,{fit:'contain',zoom:1,crop_x:.5,crop_y:.5});ctx.drawImage(image,fit.sx,fit.sy,fit.sw,fit.sh,box.x+fit.dx,box.y+fit.dy,fit.dw,fit.dh);}
      const tile=this.tile();
      const placed=c.shared_title?T.coverBox(c):{...layout.title,x:layout.title.x+layout.origin.x,y:layout.title.y+layout.origin.y};
      ctx.drawImage(tile,placed.x-layout.origin.x,placed.y-layout.origin.y,layout.title.width,layout.title.height);
      ctx.restore();
    }
  }
  const api={configure,duration,key,colors,selection,ensureSource,validate,raster,mountGuide,CoverEditor};
  if(typeof module!=='undefined')module.exports=api;else root.StudioCover=api;
})(typeof window!=='undefined'?window:this);
