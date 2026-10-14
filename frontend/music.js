// BGM使用Web Audio共用時間基準；音量／淡出只改本地草稿。
(function(root){
  const newMusic=()=>({enabled:true,source:null,volume:.5,fade_out:1,loop:true});
  function validate(m,asset){
    if(!m||typeof m.enabled!=='boolean'||typeof m.loop!=='boolean'||!Number.isFinite(m.volume)||m.volume<0||m.volume>1||!Number.isFinite(m.fade_out)||m.fade_out<0||m.fade_out>10)return 'BGM設定不正確。';
    if(m.source!==null&&m.source!==asset?.id)return 'BGM已替換或移除，請重新套用目前音樂。';return null;
  }
  const active=(m,asset)=>!!(m?.enabled&&asset&&m.source===asset.id);
  const end=(m,sourceDuration,total)=>m.loop?total:Math.min(sourceDuration,total);
  function gainAt(m,sourceDuration,total,time){
    if(!m.enabled||!m.source||time<0)return 0;const finish=end(m,sourceDuration,total);if(time>=finish)return 0;
    const fade=Math.min(m.fade_out,finish);return m.volume*(fade?Math.min(1,(finish-time)/fade):1);
  }
  class MusicPlayer{
    constructor(createContext=()=>{const C=window.AudioContext||window.webkitAudioContext;if(!C)throw new Error('此瀏覽器不支援BGM預覽，請使用FFmpeg輸出。');return new C();}){
      this.createContext=createContext;this.context=null;this.asset=null;this.buffer=null;this.source=null;this.gain=null;this.destination=null;this.generation=0;
    }
    setAsset(asset){if(this.asset?.id!==asset?.id){this.stop();this.buffer=null;this.generation++;}this.asset=asset;}
    async prepare(){
      if(!this.asset)return;this.context??=this.createContext();await this.context.resume();
      if(this.buffer)return;const generation=this.generation;
      try{const response=await fetch(this.asset.src),buffer=await this.context.decodeAudioData(await response.arrayBuffer());
        if(generation!==this.generation)throw new Error('音樂已更新，請重新播放。');this.buffer=buffer;
      }catch(error){throw new Error('瀏覽器無法播放此BGM，請用FFmpeg輸出後播放，或先關閉BGM。');}
    }
    start(m,time,total,record=false){
      this.stop();if(!active(m,this.asset)||!this.buffer)return null;
      const finish=end(m,this.asset.duration,total),ctx=this.context,now=ctx.currentTime;
      if(record)this.destination=ctx.createMediaStreamDestination();
      if(time>=finish)return this.destination?.stream||null;
      const source=ctx.createBufferSource(),gain=ctx.createGain();this.source=source;this.gain=gain;
      source.buffer=this.buffer;source.loop=m.loop;source.connect(gain);gain.connect(ctx.destination);
      if(record)gain.connect(this.destination);
      gain.gain.setValueAtTime(gainAt(m,this.asset.duration,total,time),now);
      const fade=Math.min(m.fade_out,finish),fadeStart=finish-fade;
      if(fade){if(time<fadeStart)gain.gain.setValueAtTime(m.volume,now+fadeStart-time);gain.gain.linearRampToValueAtTime(0,now+finish-time);}
      source.start(now,m.loop?time%this.buffer.duration:time);source.stop(now+finish-time);
      return this.destination?.stream||null;
    }
    stop(){if(this.source){try{this.source.stop();}catch(error){}this.source.disconnect();this.source=null;}
      if(this.gain){this.gain.disconnect();this.gain=null;}this.destination=null;}
  }
  const api={newMusic,validate,active,end,gainAt,MusicPlayer};if(typeof module!=='undefined')module.exports=api;else root.StudioMusic=api;
})(typeof window!=='undefined'?window:this);
