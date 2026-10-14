// 正文標題沿用封面的Unicode色彩索引與文字光柵器，所有設定只更新本地草稿。
(function(root){
  const C=typeof module!=='undefined'?require('./cover-editor.js'):root.StudioCover;
  let layout=typeof module!=='undefined'?require('./body-layout.json'):null;
  const $=id=>document.getElementById(id),clone=v=>JSON.parse(JSON.stringify(v));
  function configure(value){if(value)layout=value;}
  function newBody(){return {enabled:true,logo_enabled:true,follow_cover:true,title:'室內設計案例',color:'#ffffff',highlights:[],font_size:88};}
  function effective(cover){const b=cover.body,s=b.follow_cover?cover:b;return {title:s.title,color:s.color,highlights:s.highlights,font_size:b.font_size};}
  function detach(cover){const style=clone(effective(cover));Object.assign(cover.body,style,{follow_cover:false});}
  function validate(cover){const b=cover?.body;if(!b)return null;
    if(['enabled','logo_enabled','follow_cover'].some(k=>typeof b[k]!=='boolean'))return '正文標題與LOGO設定格式不正確。';
    const check=(s,required)=>C.validate({...s,enabled:required,photo_id:''},[]);
    const stored=check(b,b.enabled&&!b.follow_cover);
    if(stored)return stored.replace(/封面/g,'正文');
    const error=check(effective(cover),b.enabled);return error?.replace(/封面/g,'正文')||null;}
  function key(cover){return C.key(effective(cover));}
  function mountGuide(element,cover){if(!cover?.body?.enabled)return;
    const b=layout.title,svg=element.querySelector('svg');if(!svg)return;
    const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');
    for(const [k,v] of Object.entries({x:b.x,y:b.y,width:b.width,height:b.height,fill:'none',stroke:'#ffd34e','stroke-width':4,'stroke-dasharray':'12 8'}))rect.setAttribute(k,v);
    svg.append(rect);}
  class BodyEditor{
    constructor(hooks){this.hooks=hooks;this.template=null;this.calibrated=null;this.local=null;this.selection=null;
      for(const [id,field] of [['bodyEnabled','enabled'],['bodyLogo','logo_enabled']])$(id).onchange=()=>{if(hooks.locked())return;hooks.cover().body[field]=$(id).checked;hooks.change();};
      $('bodyFollow').onchange=()=>{if(hooks.locked())return;const c=hooks.cover();if(!$('bodyFollow').checked)detach(c);else c.body.follow_cover=true;hooks.change();};
      $('bodyTitle').oninput=()=>{if(hooks.locked()||hooks.cover().body.follow_cover)return;const b=hooks.cover().body;b.title=$('bodyTitle').value;b.highlights=[];this.selection=null;hooks.change();};
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
      for(const [id,k] of [['bodyTitle','title'],['bodyColor','color'],['bodySize','font_size']])if(document.activeElement!==$(id)&&String($(id).value)!==String(s[k]))$(id).value=s[k];
      $('bodyTitle').readOnly=b.follow_cover; // 唯讀可反白，disabled則無法選字。
      for(const id of ['bodyTitle','bodyColor','bodySelectedColor','bodyApplyColor','bodyClearColors'])$(id).disabled=this.hooks.locked();
      this.selection=C.selection($('bodyTitle'),this.selection);
      const selected=this.selection?'已選：'+Array.from(this.selection.value).slice(this.selection.start,this.selection.end).join('')+'。':'';
      $('bodySelection').textContent=selected+(b.follow_cover?'可在正文輸入框反白換色，顏色會同步封面；修改文字請到封面，或取消連動。':'在正文輸入框反白要改色的文字，再選色並套用。');
      $('bodyColorPreview').replaceChildren();const palette=C.colors(s);Array.from(s.title).forEach((char,i)=>{const span=document.createElement('span');span.textContent=char;span.style.color=palette[i];$('bodyColorPreview').append(span);});
    }
    draw(ctx){const c=this.hooks.cover(),b=c?.body;if(!b)return;
      if(b.logo_enabled&&this.template){const scale=Math.min(1080/this.template.naturalWidth,1920/this.template.naturalHeight),w=this.template.naturalWidth*scale;
        ctx.drawImage(this.template,(1080-w)/2,0,w,this.template.naturalHeight*scale);}
      if(!b.enabled)return;const titleKey=key(c);let tile=this.calibrated?.key===titleKey?this.calibrated.image:null;
      if(!tile){if(this.local?.key!==titleKey)this.local={key:titleKey,image:C.raster(effective(c),()=>document.createElement('canvas'),layout.title)};tile=this.local.image;}
      const box=layout.title;ctx.drawImage(tile,box.x,box.y,box.width,box.height);
    }
  }
  const api={configure,newBody,effective,detach,validate,key,mountGuide,BodyEditor};
  if(typeof module!=='undefined')module.exports=api;else root.StudioBody=api;
})(typeof window!=='undefined'?window:this);
