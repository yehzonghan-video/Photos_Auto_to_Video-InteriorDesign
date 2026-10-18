// PNG 素材庫／畫布控制，透過 hooks 使用原有前端草稿與批次同步。
(function(root){
  const $=id=>document.getElementById(id),clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const fields=['start','duration','x','y','scale','rotation','opacity','layer','animation','exit_animation','enter','exit'];
  class PNGEditor{
    constructor(hooks){
      this.hooks=hooks;this.selected=null;this.drag=null;
      for(const key of [...fields,'end'])$('png_'+key).oninput=()=>this.changeField(key);
      $('deleteOverlay').onclick=()=>this.remove();
    }
    item(){return this.hooks.overlays().find(o=>o.id===this.selected);}
    select(id){this.selected=id;const o=this.item();if(o)this.hooks.select(o);this.refresh();}
    add(asset){
      if(this.hooks.locked())return;
      const overlays=this.hooks.overlays(),length=this.hooks.total();
      if(!length||overlays.length>=32){this.hooks.status('全片最多32個PNG圖層；請先加入照片或刪除不需要的圖層。',true);return;}
      const start=clamp(StudioTimeline.snap(this.hooks.time()),0,length-1/30);
      const o={id:crypto.randomUUID(),type:'png',source:asset.id,name:asset.name,start,duration:Math.min(3,length-start),
        layer:Math.min(1000,Math.max(20,...overlays.map(o=>o.layer+1))),x:.5,y:.5,width:.3,scale:1,rotation:0,opacity:1,
        animation:'fade',exit_animation:'fade',enter:.5,exit:.5};
      StudioTimeline.fitAnimations(o);overlays.push(o);this.select(o.id);this.hooks.changed();
    }
    library(){
      $('assetLibrary').replaceChildren();
      for(const asset of this.hooks.assets().values()){
        const b=document.createElement('button'),img=document.createElement('img'),caption=document.createElement('span');
        b.title=`加入 ${asset.name}`;img.src=asset.image;img.alt=asset.name;caption.textContent=asset.name;
        b.append(img,caption);b.onclick=()=>this.add(asset);$('assetLibrary').append(b);
      }
      if(!this.hooks.assets().size)$('assetLibrary').textContent='尚無PNG，請使用上方上傳素材。';
    }
    refresh(){
      const o=this.item();$('overlayForm').hidden=!o;
      if(!o)return;
      $('labelForm').hidden=true;$('overlayName').textContent=o.name;
      for(const key of fields)if(document.activeElement!==$('png_'+key))$('png_'+key).value=typeof o[key]==='number'?Number(o[key].toFixed(6)):o[key];
      if(document.activeElement!==$('png_end'))$('png_end').value=Number((o.start+o.duration).toFixed(6));
    }
    changeField(key){
      const o=this.item();if(!o||this.hooks.locked())return;
      const raw=$('png_'+key).value,value=['animation','exit_animation'].includes(key)?raw:Number(raw);
      if(typeof value==='number'&&!Number.isFinite(value)){this.hooks.status('PNG數值不正確。',true);return;}
      const length=this.hooks.total();
      if(key==='end'){if(value<=o.start)return;o.duration=clamp(StudioTimeline.snap(value-o.start),1/30,length-o.start);}
      else if(key==='start')o.start=clamp(StudioTimeline.snap(value),0,length-1/30);
      else if(key==='duration')o.duration=clamp(StudioTimeline.snap(value),1/30,length-o.start);
      else if(key==='x'||key==='y'||key==='opacity')o[key]=clamp(value,0,1);
      else if(key==='scale')o.scale=clamp(value,.1,5);
      else if(key==='rotation')o.rotation=clamp(value,-180,180);
      else if(key==='layer')o.layer=Math.round(clamp(value,0,1000));
      else if(key==='enter'||key==='exit')o[key]=clamp(value,0,3);
      else o[key]=value;
      StudioTimeline.clampOverlays(this.hooks.overlays(),length);this.clampPosition(o);this.refresh();this.hooks.changed();
    }
    clampPosition(o){const g=this.geometry(o);if(g){o.x=g.x/1080;o.y=g.y/1920;}}
    geometry(o){const asset=this.hooks.assets().get(o.source);return asset?StudioOverlay.geometry(o,asset):null;}
    posedGeometry(o,time=this.hooks.time()){
      const g=this.geometry(o),pose=StudioAnimation.overlayPose(o,time);
      return g&&pose&&pose.alpha*o.opacity>.001?{...g,x:g.x+pose.x*1080,y:g.y+pose.y*1920,width:g.width*pose.scale,height:g.height*pose.scale}:null;
    }
    active(o){const t=this.hooks.time();return t>=o.start&&t<o.start+o.duration;}
    world(g,o,x,y){const a=o.rotation*Math.PI/180;return {x:g.x+x*Math.cos(a)-y*Math.sin(a),y:g.y+x*Math.sin(a)+y*Math.cos(a)};}
    draw(ctx,o,time,editing){
      if(time<o.start||time>=o.start+o.duration)return;
      const g=this.geometry(o),image=this.hooks.images().get(o.source);if(!g||!image)return;
      const pose=StudioAnimation.overlayPose(o,time);if(!pose)return;
      ctx.save();ctx.globalAlpha=o.opacity*pose.alpha;ctx.translate(g.x+pose.x*1080,g.y+pose.y*1920);ctx.rotate(o.rotation*Math.PI/180);
      ctx.drawImage(image,-g.width*pose.scale/2,-g.height*pose.scale/2,g.width*pose.scale,g.height*pose.scale);ctx.restore();
      const shown=this.posedGeometry(o,time);
      if(editing&&o.id===this.selected&&shown){
        ctx.save();ctx.translate(shown.x,shown.y);ctx.rotate(o.rotation*Math.PI/180);ctx.strokeStyle='#e8bd78';ctx.lineWidth=5;
        ctx.strokeRect(-shown.width/2,-shown.height/2,shown.width,shown.height);ctx.fillStyle='#e8bd78';ctx.fillRect(shown.width/2-14,shown.height/2-14,28,28);
        ctx.beginPath();ctx.moveTo(0,-shown.height/2);ctx.lineTo(0,-shown.height/2-60);ctx.stroke();ctx.beginPath();ctx.arc(0,-shown.height/2-60,16,0,Math.PI*2);ctx.fill();ctx.restore();
      }
    }
    down(pos,minLayer=-1){
      const selected=this.item();
      if(selected&&this.active(selected)){
        const g=this.posedGeometry(selected);if(g){
          for(const [mode,point] of [['scale',this.world(g,selected,g.width/2,g.height/2)],['rotate',this.world(g,selected,0,-g.height/2-60)]]){
            if(Math.hypot(pos.x-point.x,pos.y-point.y)<34){this.drag={mode,id:selected.id,g,scale:selected.scale,rotation:selected.rotation,
              distance:Math.hypot(pos.x-g.x,pos.y-g.y),angle:Math.atan2(pos.y-g.y,pos.x-g.x)};return true;}
          }
        }
      }
      for(const o of [...this.hooks.overlays()].reverse().filter(o=>this.active(o)&&o.layer>=minLayer).sort((a,b)=>b.layer-a.layer)){
        const g=this.posedGeometry(o);if(!g)continue;const a=-o.rotation*Math.PI/180,dx=pos.x-g.x,dy=pos.y-g.y;
        if(Math.abs(dx*Math.cos(a)-dy*Math.sin(a))<=g.width/2&&Math.abs(dx*Math.sin(a)+dy*Math.cos(a))<=g.height/2){
          const base=this.geometry(o);this.select(o.id);this.drag={mode:'move',id:o.id,dx:pos.x-base.x,dy:pos.y-base.y};return true;
        }
      }
      return false;
    }
    move(pos){
      const d=this.drag,o=this.hooks.overlays().find(o=>o.id===d?.id);if(!o)return;
      if(d.mode==='move'){o.x=clamp((pos.x-d.dx)/1080,0,1);o.y=clamp((pos.y-d.dy)/1920,0,1);}
      if(d.mode==='scale')o.scale=clamp(d.scale*Math.hypot(pos.x-d.g.x,pos.y-d.g.y)/Math.max(1,d.distance),.1,5);
      if(d.mode==='rotate'){let angle=d.rotation+(Math.atan2(pos.y-d.g.y,pos.x-d.g.x)-d.angle)*180/Math.PI;o.rotation=((angle+540)%360)-180;}
      this.clampPosition(o);this.refresh();
    }
    remove(){if(this.hooks.locked())return;const rows=this.hooks.overlays(),index=rows.findIndex(o=>o.id===this.selected);if(index<0)return;
      rows.splice(index,1);this.selected=null;this.refresh();this.hooks.changed();}
  }
  if(typeof module!=='undefined')module.exports={PNGEditor};else root.StudioPNG={PNGEditor};
})(typeof window!=='undefined'?window:this);
