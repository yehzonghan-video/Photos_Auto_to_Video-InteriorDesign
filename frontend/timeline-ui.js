// Canvas 多軌時間軸；所有 Pointer 事件僅操作呼叫者的前端草稿。
(function(root){
  class TimelineUI{
    constructor(canvas,hooks){
      this.canvas=canvas;this.hooks=hooks;this.hits=[];this.drag=null;this.zoom=1;
      canvas.addEventListener('pointerdown',e=>this.down(e));
      canvas.addEventListener('pointermove',e=>this.move(e));
      canvas.addEventListener('pointerup',()=>this.finish());canvas.addEventListener('pointercancel',()=>this.finish());
      canvas.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)&&!hooks.locked()){
        e.preventDefault();hooks.seek(hooks.time()+(e.key==='ArrowLeft'?-1:1)/30);}});
    }
    draw(){
      const h=this.hooks,p=h.photos(),prefix=h.offset?.()||0,length=StudioTimeline.total(p)+prefix,all=StudioTimeline.items(p,h.overlays(),prefix,h.title?.(),h.logo?.());
      this.length=length;this.width=Math.round(Math.max(600,this.canvas.parentElement?.clientWidth||900)*this.zoom);
      const tracks=[{name:p[0]?.type==='comparison'?'對比':'照片',color:'#5d7760',rows:1,clips:all.filter(i=>['photo','comparison','cover'].includes(i.type)).map(item=>({item,lane:0}))},
        {name:'正文',color:'#a34b63',...StudioTimeline.lanes(all.filter(i=>i.type==='body_title'))},
        {name:'LOGO',color:'#467e8d',...StudioTimeline.lanes(all.filter(i=>i.type==='body_logo'))},
        {name:'文字',color:'#b37b44',...StudioTimeline.lanes(all.filter(i=>i.type==='label'))},
        {name:'PNG',color:'#6b6caa',...StudioTimeline.lanes(all.filter(i=>i.type==='png'))}];
      const height=32+tracks.reduce((n,t)=>n+t.rows*36,0);
      if(this.canvas.width!==this.width)this.canvas.width=this.width;if(this.canvas.height!==height)this.canvas.height=height;
      if(this.canvas.style){this.canvas.style.width=this.width+'px';this.canvas.style.height=height+'px';}
      const ctx=this.canvas.getContext('2d');ctx.fillStyle='#faf8f3';ctx.fillRect(0,0,this.width,height);
      ctx.font='12px "Microsoft JhengHei",sans-serif';this.px=(this.width-92)/Math.max(length,1);this.hits=[];
      ctx.fillStyle='#4c5148';const step=length>60?5:length>24?2:1;
      for(let t=0;t<=length+.001;t+=step){const x=84+t*this.px;ctx.fillText(`${t}s`,x+2,16);ctx.strokeStyle='#ddd7cc';ctx.beginPath();ctx.moveTo(x,22);ctx.lineTo(x,height);ctx.stroke();}
      let top=32;
      for(const track of tracks){
        ctx.fillStyle='#e9e5dc';ctx.fillRect(0,top,80,track.rows*36-2);ctx.fillStyle='#43483e';ctx.fillText(track.name,10,top+22);
        for(const {item,lane} of track.clips){
          const x=84+item.start*this.px,y=top+lane*36+3,w=Math.max(3,item.duration*this.px),selected=h.selected(item);
          ctx.fillStyle=selected?'#283d31':track.color;ctx.fillRect(x,y,w,29);
          ctx.fillStyle='#fff';if(w>35)ctx.fillText(String(item.name).slice(0,Math.max(1,Math.floor(w/13)-1)),x+8,y+19);
          ctx.fillStyle='#fff9';ctx.fillRect(x,y,4,29);ctx.fillRect(x+w-4,y,4,29);
          this.hits.push({item,x,y,w,height:29});
        }
        top+=track.rows*36;
      }
      const cursor=84+h.time()*this.px;ctx.strokeStyle='#ca4e3c';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(cursor,0);ctx.lineTo(cursor,height);ctx.stroke();
      ctx.fillStyle='#ca4e3c';ctx.fillRect(cursor-5,0,10,9);
    }
    xy(e){const r=this.canvas.getBoundingClientRect();return {x:(e.clientX-r.left)*this.canvas.width/r.width,y:(e.clientY-r.top)*this.canvas.height/r.height};}
    down(e){
      if(this.hooks.locked())return;const pos=this.xy(e);
      const hit=pos.y>=32?this.hits.find(r=>pos.x>=r.x-3&&pos.x<=r.x+r.w+3&&pos.y>=r.y&&pos.y<=r.y+r.height):null;
      this.canvas.setPointerCapture(e.pointerId);e.preventDefault();
      if(!hit){this.drag={seek:true};this.hooks.seek((pos.x-84)/this.px);return;}
      this.hooks.select(hit.item);
      if(hit.item.type==='cover'){this.draw();return;}
      const mode=pos.x-hit.x<7?'left':hit.x+hit.w-pos.x<7?'right':'move';
      this.drag={item:{...hit.item},mode,x:pos.x,px:this.px,
        photos:StudioDraft.metadata(this.hooks.photos()),overlays:JSON.parse(JSON.stringify(this.hooks.overlays())),
        bodyTiming:this.hooks.body?.()?Object.fromEntries(['start','end','auto_timing','logo_start','logo_end','logo_auto_timing'].map(k=>[k,this.hooks.body()[k]])):null};
      this.draw();
    }
    move(e){
      if(!this.drag||this.hooks.locked())return;const pos=this.xy(e),d=this.drag;
      if(d.seek){this.hooks.seek((pos.x-84)/this.px);return;}
      const delta=StudioTimeline.snap((pos.x-d.x)/d.px);
      if(delta===0&&!d.changed)return;
      d.changed=true;
      const current=new Map(this.hooks.photos().map(p=>[p.id,p]));
      const p=this.hooks.photos();p.splice(0,p.length,...d.photos.map(row=>Object.assign(current.get(row.id),JSON.parse(JSON.stringify(row)))));
      const overlays=this.hooks.overlays();overlays.splice(0,overlays.length,...JSON.parse(JSON.stringify(d.overlays)));
      if(d.bodyTiming)Object.assign(this.hooks.body(),d.bodyTiming);
      if(delta!==0)StudioTimeline.edit(d.item,d.mode,delta,p,overlays,this.hooks.offset?.()||0,this.hooks.body?.());
      this.hooks.change(false);this.draw();
    }
    finish(){if(this.drag){const changed=!!this.drag.changed;this.drag=null;if(changed)this.hooks.change(true);}}
  }
  if(typeof module!=='undefined')module.exports={TimelineUI};else root.StudioTimelineUI={TimelineUI};
})(typeof window!=='undefined'?window:this);
