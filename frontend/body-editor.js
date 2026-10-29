// 正文標題沿用封面的Unicode色彩索引與文字光柵器，所有設定只更新本地草稿。
(function(root){
  const C=typeof module!=='undefined'?require('./cover-editor.js'):root.StudioCover;
  const T=typeof module!=='undefined'?require('./title-model.js'):root.StudioTitle;
  let layout=typeof module!=='undefined'?require('./body-layout.json'):null;
  const $=id=>document.getElementById(id),clone=v=>JSON.parse(JSON.stringify(v));
  function configure(value){if(value)layout=value;}
  const MIN=1/30,clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  function newBody(){return {enabled:true,logo_enabled:true,follow_cover:true,title:'室內設計案例',color:'#ffffff',highlights:[],...layout.defaults,auto_timing:true,start:0,end:null,logo_auto_timing:true,logo_start:0,logo_end:null,version:5};}
  function upgrade(b){if(!b||(b.version??0)>=5)return false;
    if((b.version??0)<4){
    if(b.font_size===120||((b.version??0)<2&&b.font_size===88))b.font_size=layout.defaults.font_size;
    if((b.x??.5)===.5&&[(350+180)/1920,(410+180)/1920].includes(b.y))b.y=layout.defaults.y;
    b.font_size??=newBody().font_size;b.auto_timing??=true;b.start??=0;b.end??=null;b.x??=newBody().x;b.y??=newBody().y;}
    b.logo_auto_timing??=true;b.logo_start??=0;b.logo_end??=null;b.version=5;return true;}
  function box(b){const size=layout.title;return {x:Math.round((b.x??.5)*1080-size.width/2),
    y:Math.round((b.y??newBody().y)*1920-size.height/2),width:size.width,height:size.height};}
  function alphaBounds(image){const canvas=image.getContext?image:document.createElement('canvas');
    if(canvas!==image){canvas.width=layout.title.width;canvas.height=layout.title.height;canvas.getContext('2d').drawImage(image,0,0);}
    const ctx=canvas.getContext('2d');if(!ctx.getImageData)return [0,0,canvas.width,canvas.height];
    const {data}=ctx.getImageData(0,0,canvas.width,canvas.height);let left=canvas.width,right=0,top=canvas.height,bottom=0;
    for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++)if(data[(y*canvas.width+x)*4+3]){left=Math.min(left,x);right=Math.max(right,x+1);top=Math.min(top,y);bottom=Math.max(bottom,y+1);}
    return right>left?[left,top,right,bottom]:[canvas.width/2,canvas.height/2,canvas.width/2,canvas.height/2];}
  function span(b,prefix,length){if(length-prefix<MIN-1e-8)return {start:prefix,end:prefix};
    if(b.auto_timing??true)return {start:prefix,end:length};
    const start=clamp(b.start,prefix,length-MIN),end=clamp(b.end,start+MIN,length);return {start,end};}
  function logoTiming(b){return {enabled:b.logo_enabled,auto_timing:b.logo_auto_timing??true,start:b.logo_start??0,end:b.logo_end??null};}
  function logoSpan(b,prefix,length){return span(logoTiming(b),prefix,length);}
  function logoVisible(b,time,prefix,length){return visible(logoTiming(b),time,prefix,length);}
  function fit(b,prefix,length){if(!b||length-prefix<MIN-1e-8)return;
    if(!b.auto_timing)Object.assign(b,span(b,prefix,length));
    if(b.logo_auto_timing===false){const range=logoSpan(b,prefix,length);b.logo_start=range.start;b.logo_end=range.end;}}
  function visible(b,time,prefix,length){const range=span(b,prefix,length);return b.enabled&&time+1e-8>=range.start&&time<range.end-1e-8;}
  function item(cover,prefix,length){const b=cover?.body;if(!b?.enabled)return null;const range=span(b,prefix,length);
    return range.end>range.start?{id:'project-body-title',source:'project-body-title',type:'body_title',name:effective(cover).title,start:range.start,duration:range.end-range.start,layer:0}:null;}
  function logoItem(cover,prefix,length){const b=cover?.body;if(!b?.logo_enabled)return null;const range=logoSpan(b,prefix,length);
    return range.end>range.start?{id:'project-body-logo',source:'project-body-logo',type:'body_logo',name:'正文LOGO',start:range.start,duration:range.end-range.start,layer:0}:null;}
  function effective(cover){const b=cover.body,s=b.follow_cover?cover:b;return {title:s.title,color:s.color,highlights:s.highlights,font_size:b.font_size};}
  function detach(cover){const style=clone(effective(cover));Object.assign(cover.body,style,{follow_cover:false});}
  function validate(cover){const b=cover?.body;if(!b)return null;
    if(['enabled','logo_enabled','follow_cover'].some(k=>typeof b[k]!=='boolean'))return '正文標題與LOGO設定格式不正確。';
    for(const field of ['x','y'])if(b[field]!=null&&(!Number.isFinite(b[field])||b[field]<0||b[field]>1))return '正文位置需為0～100%。';
    if(typeof (b.auto_timing??true)!=='boolean'||!Number.isFinite(b.start??0)||(b.start??0)<0||(b.start??0)>120||
      (b.end!=null&&(!Number.isFinite(b.end)||b.end<0||b.end>120))||b.auto_timing===false&&(b.end==null||b.end-b.start<MIN-1e-8))return '請確認正文標題開始與結束時間，至少一影格。';
    if(typeof (b.logo_auto_timing??true)!=='boolean'||!Number.isFinite(b.logo_start??0)||(b.logo_start??0)<0||(b.logo_start??0)>120||
      (b.logo_end!=null&&(!Number.isFinite(b.logo_end)||b.logo_end<0||b.logo_end>120))||b.logo_auto_timing===false&&(b.logo_end==null||b.logo_end-b.logo_start<MIN-1e-8))return '請確認正文LOGO開始與結束時間，至少一影格。';
    const check=(s,required)=>C.validate({...s,enabled:required,photo_id:''},[],240);
    const stored=check(b,b.enabled&&!b.follow_cover);
    if(stored)return stored.replace(/封面/g,'正文');
    const error=check(effective(cover),b.enabled);return error?.replace(/封面/g,'正文')||null;}
  function key(cover){return JSON.stringify([C.key(effective(cover)),layout?.title]);}
  function mountGuide(element,cover){if(!cover?.body?.enabled)return;
    const b=layout.title,svg=element.querySelector('svg');if(!svg)return;
    const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');
    for(const [k,v] of Object.entries({x:b.x,y:b.y,width:b.width,height:b.height,fill:'none',stroke:'#ffd34e','stroke-width':4,'stroke-dasharray':'12 8'}))rect.setAttribute(k,v);
    svg.append(rect);}
  class BodyEditor{
    constructor(hooks){this.hooks=hooks;this.template=null;this.calibrated=null;this.local=null;this.selection=null;
      for(const [id,field] of [['bodyEnabled','enabled'],['bodyLogo','logo_enabled']])$(id).onchange=()=>{if(hooks.locked())return;hooks.cover().body[field]=$(id).checked;hooks.change(field==='logo_enabled'?'body_logo':'body_title');};
      $('logoAutoTime').onchange=()=>{if(hooks.locked())return;const b=hooks.cover().body,range=logoSpan(b,hooks.prefix(),hooks.length());
        b.logo_auto_timing=$('logoAutoTime').checked;if(!b.logo_auto_timing){b.logo_start=range.start;b.logo_end=range.end;}hooks.change('body_logo');};
      for(const [id,field] of [['logoStart','logo_start'],['logoEnd','logo_end']])$(id).oninput=()=>{if(hooks.locked())return;
        const b=hooks.cover().body,range=logoSpan(b,hooks.prefix(),hooks.length()),value=Number($(id).value);if(!Number.isFinite(value))return;
        Object.assign(b,{logo_auto_timing:false,logo_start:range.start,logo_end:range.end,[field]:Math.round(value*30)/30});fit(b,hooks.prefix(),hooks.length());hooks.change('body_logo');};
      for(const [id,field] of [['bodyX','x'],['bodyY','y']])$(id).oninput=()=>{if(hooks.locked())return;const b=hooks.cover().body,value=Number($(id).value)/100;if(!Number.isFinite(value))return;
        this.position(field==='x'?value:b.x,field==='y'?value:b.y);hooks.change();};
      $('bodyResetPosition').onclick=()=>{if(hooks.locked())return;const b=hooks.cover().body;Object.assign(b,{x:newBody().x,y:newBody().y});hooks.change();};
      $('bodyAutoTime').onchange=()=>{if(hooks.locked())return;const b=hooks.cover().body,range=span(b,hooks.prefix(),hooks.length());
        b.auto_timing=$('bodyAutoTime').checked;if(!b.auto_timing)Object.assign(b,range);hooks.change();};
      for(const [id,field] of [['bodyStart','start'],['bodyEnd','end']])$(id).oninput=()=>{if(hooks.locked())return;
        const b=hooks.cover().body,range=span(b,hooks.prefix(),hooks.length()),value=Number($(id).value);if(!Number.isFinite(value))return;
        Object.assign(b,range,{auto_timing:false,[field]:Math.round(value*30)/30});fit(b,hooks.prefix(),hooks.length());hooks.change();};
      $('bodyFollow').onchange=()=>{if(hooks.locked()||hooks.cover().shared_title)return;const c=hooks.cover();if(!$('bodyFollow').checked)detach(c);else c.body.follow_cover=true;hooks.change();};
      $('bodyTitle').oninput=()=>{if(hooks.locked()||hooks.cover().body.follow_cover)return;const c=hooks.cover(),b=c.body;
        if(c.shared_title){try{T.setDisplay(c,'body',$('bodyTitle').value);}catch(e){hooks.status(e.message,true);return;}}else {b.title=$('bodyTitle').value;b.highlights=[];}
        this.selection=null;hooks.change();};
      const capture=()=>{this.selection=C.selection($('bodyTitle'),this.selection);
        $('bodySelection').textContent=this.selection?'已選：'+Array.from(this.selection.value).slice(this.selection.start,this.selection.end).join(''):'請在正文標題輸入框反白要改色的文字';};
      for(const event of ['select','pointerup','keyup','blur'])$('bodyTitle')['on'+event]=capture;
      for(const [id,field] of [['bodyColor','color'],['bodySize','font_size']])$(id).oninput=()=>{if(hooks.locked())return;const c=hooks.cover(),target=field==='color'&&c.body.follow_cover?c:c.body;target[field]=field==='font_size'?Number($(id).value):$(id).value;hooks.change();};
      $('bodyApplyColor').onclick=()=>{const c=hooks.cover();if(hooks.locked())return;capture();const r=this.selection,target=c.body.follow_cover?c:c.body;
        if(!r||r.end<=r.start){hooks.status('請先反白選取要改色的正文文字。',true);return;}
        if(target.highlights.length>=80){hooks.status('局部字色最多80組，請先清除後重新設定。',true);return;}
        target.highlights.push({start:r.start,end:r.end,color:$('bodySelectedColor').value});hooks.change();};
      $('bodyClearColors').onclick=()=>{const c=hooks.cover();if(hooks.locked())return;const target=c.body.follow_cover?c:c.body;target.highlights=[];hooks.change();};
    }
    refresh(){const c=this.hooks.cover();$('bodyPanel').hidden=!c?.body;if(!c?.body)return;const b=c.body,s=effective(c);
      for(const [id,k] of [['bodyEnabled','enabled'],['bodyLogo','logo_enabled'],['bodyFollow','follow_cover']])$(id).checked=b[k];
      $('bodyFollow').disabled=this.hooks.locked()||!!c.shared_title;
      $('bodyFollowLabel').textContent=c.shared_title?'已共用影片標題文字；兩邊樣式獨立':'連動封面文字與顏色（預設）';
      const range=span(b,this.hooks.prefix(),this.hooks.length());$('bodyAutoTime').checked=b.auto_timing??true;
      for(const [id,k] of [['bodyStart','start'],['bodyEnd','end']]){if(document.activeElement!==$(id))$(id).value=Number(range[k].toFixed(3));
        $(id).min=this.hooks.prefix();$(id).max=this.hooks.length();$(id).disabled=this.hooks.locked()||range.end===range.start;}
      $('bodyTiming').textContent=`全片 ${range.start.toFixed(2)}～${range.end.toFixed(2)} 秒 · 持續 ${(range.end-range.start).toFixed(2)} 秒`;
      const logo=logoSpan(b,this.hooks.prefix(),this.hooks.length());$('logoAutoTime').checked=b.logo_auto_timing??true;
      for(const [id,k] of [['logoStart','start'],['logoEnd','end']]){if(document.activeElement!==$(id))$(id).value=Number(logo[k].toFixed(3));
        $(id).min=this.hooks.prefix();$(id).max=this.hooks.length();$(id).disabled=this.hooks.locked()||logo.end===logo.start;}
      $('logoTiming').textContent=`LOGO全片 ${logo.start.toFixed(2)}～${logo.end.toFixed(2)} 秒 · 持續 ${(logo.end-logo.start).toFixed(2)} 秒`;
      for(const [id,k] of [['bodyTitle','title'],['bodyColor','color'],['bodySize','font_size']])if(document.activeElement!==$(id)&&String($(id).value)!==String(s[k]))$(id).value=s[k];
      $('bodyTitle').readOnly=b.follow_cover; // 唯讀可反白，disabled則無法選字。
      for(const id of ['bodyTitle','bodyColor','bodySelectedColor','bodyApplyColor','bodyClearColors'])$(id).disabled=this.hooks.locked();
      this.selection=C.selection($('bodyTitle'),this.selection);
      const selected=this.selection?'已選：'+Array.from(this.selection.value).slice(this.selection.start,this.selection.end).join('')+'。':'';
      $('bodySelection').textContent=selected+(b.follow_cover?'可在正文輸入框反白換色，顏色會同步封面；修改文字請到封面，或取消連動。':(c.shared_title?'修改文字會同步封面；字色與換行只調整正文。':'')+'在正文輸入框反白要改色的文字，再選色並套用。');
      $('bodyColorPreview').replaceChildren();const palette=C.colors(s);Array.from(s.title).forEach((char,i)=>{const span=document.createElement('span');span.textContent=char;span.style.color=palette[i];$('bodyColorPreview').append(span);});
      $('bodySizeValue').textContent=`${b.font_size}px`;
      for(const [id,k] of [['bodyX','x'],['bodyY','y']])if(document.activeElement!==$(id))$(id).value=Number((b[k]*100).toFixed(2));
    }
    tile(){const c=this.hooks.cover(),titleKey=key(c);if(this.calibrated?.key===titleKey)return this.calibrated;
      if(this.local?.key!==titleKey){const image=C.raster(effective(c),()=>document.createElement('canvas'),layout.title,240);this.local={key:titleKey,image,bounds:alphaBounds(image)};}
      return this.local;}
    bounds(){const placed=box(this.hooks.cover().body),r=this.tile().bounds||[0,0,placed.width,placed.height];
      return {x:placed.x+r[0],y:placed.y+r[1],width:r[2]-r[0],height:r[3]-r[1],tile:placed};}
    hit(xy,time){const b=this.hooks.cover()?.body;if(!b||!visible(b,time,this.hooks.prefix(),this.hooks.length()))return false;
      const r=this.bounds();return xy.x>=r.x&&xy.x<=r.x+r.width&&xy.y>=r.y&&xy.y<=r.y+r.height;}
    position(x,y){const b=this.hooks.cover().body,r=this.tile().bounds||[0,0,layout.title.width,layout.title.height],size=layout.title;
      b.x=clamp(x,Math.max(0,(size.width/2-r[0])/1080),Math.min(1,(1080+size.width/2-r[2])/1080));
      b.y=clamp(y,Math.max(0,(size.height/2-r[1])/1920),Math.min(1,(1920+size.height/2-r[3])/1920));}
    draw(ctx,time=0,selected=false){const c=this.hooks.cover(),b=c?.body;if(!b)return;
      if(logoVisible(b,time,this.hooks.prefix(),this.hooks.length())&&this.template){const scale=Math.min(1080/this.template.naturalWidth,1920/this.template.naturalHeight),w=this.template.naturalWidth*scale;
        ctx.drawImage(this.template,(1080-w)/2,0,w,this.template.naturalHeight*scale);}
      if(!visible(b,time,this.hooks.prefix(),this.hooks.length()))return;const placed=box(b),tile=this.tile().image;ctx.drawImage(tile,placed.x,placed.y,placed.width,placed.height);
      if(selected){const r=this.bounds();ctx.save();ctx.strokeStyle='#eac181';ctx.lineWidth=4;ctx.setLineDash([12,8]);ctx.strokeRect(r.x-6,r.y-6,r.width+12,r.height+12);ctx.restore();}
    }
  }
  const api={configure,newBody,upgrade,box,span,fit,visible,item,logoTiming,logoSpan,logoVisible,logoItem,effective,detach,validate,key,mountGuide,alphaBounds,BodyEditor};
  if(typeof module!=='undefined')module.exports=api;else root.StudioBody=api;
})(typeof window!=='undefined'?window:this);
