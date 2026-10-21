// 一次點擊固定一版：精確ACK才啟動工作，下載收據先保存再觸發。
(function(root){
  class OutputController{
    constructor(hooks){this.h=hooks;this.intent=null;this.receipts=[];this.server=null;this.delivery=null;this.mp4Delivery=null;this.sentStart=null;this.sentCancel=null;this.zipBackup=true;}
    busy(){return !!this.intent&&['syncing','working'].includes(this.intent.phase)||['prepared','working'].includes(this.server?.phase);}
    save(){this.h.persist();}
    restore(value){const saved=JSON.parse(JSON.stringify(value||{}));this.intent=saved.intent||null;this.receipts=saved.receipts||[];this.zipBackup=saved.zipBackup!==false;this.sentStart=null;this.sentCancel=null;}
    persisted(){return {intent:this.intent,receipts:this.receipts,zipBackup:this.zipBackup};}
    setZipBackup(value){this.zipBackup=value===true;this.save();}
    async request(kind,width){
      if(this.busy()||this.h.pending())throw new Error('上一個輸出或同步尚未完成，請稍候。');
      const id=this.h.uuid();this.intent={id,kind,width,zipBackup:kind==='mp4'&&this.zipBackup,seq:this.h.seq?.(),version:this.h.version(),phase:'syncing',verified:false,startNonce:this.h.uuid()};this.save();
      try{await this.h.sync(kind==='zip'?'save_project':'export',id,width,{zip_backup:this.intent.zipBackup});}
      catch(error){this.fail(error.message);throw error;}
    }
    ack(response){
      const i=this.intent;if(!i||i.phase!=='syncing'||response.nonce!==i.id)return;
      if(!response.ok||response.operation_id!==i.id||response.content_version!==i.version||response.seq!==i.seq){this.fail('同步版本確認失敗，草稿保留，請重試。');return;}
      i.verified=true;this.start();
    }
    start(){
      const i=this.intent;if(!i?.verified||i.phase==='error'||this.h.pending()||this.sentStart===i.id)return;
      this.sentStart=i.id;i.phase='working';this.save();
      this.h.post({action:'start_output',nonce:i.startNonce,operation_id:i.id,content_version:i.version});
    }
    receive(server,delivery,response,mp4Delivery){
      this.server=server;this.delivery=delivery;this.mp4Delivery=mp4Delivery;const i=this.intent;
      if(server?.id===i?.id&&i){
        i.artifacts=server.artifacts;i.retryZip=!!server.retry_zip;
        if(server.phase==='prepared'&&i.phase==='syncing'&&response&&server.version===i.version&&!this.h.pending())this.ack(response);
        if(server.phase==='prepared'&&i.phase==='error')this.fail(i.message);
        if(server.phase==='error')this.fail(server.message||'本次處理失敗，請重試。');
        else if(server.phase==='prepared'&&i.verified)this.start();
        else if(server.phase==='working'){i.phase='working';this.save();}
        else if(server.phase==='done'){
          i.phase='done';this.save();
          this.downloadReady(i,delivery,mp4Delivery);
        }
      }
      if(i?.phase==='syncing'&&!this.h.pending())this.fail('同步確認已中斷，草稿保留，請重新按下載ZIP或輸出影片。');
    }
    downloadReady(i,zip,mp4){
      const requested=[];
      for(const [kind,d] of [['mp4',mp4],['zip',zip]]){
        if(kind==='mp4'&&i.kind!=='mp4'||kind==='zip'&&i.kind!=='zip'&&!i.zipBackup)continue;
        if(i.artifacts&&i.artifacts[kind]?.phase!=='done')continue;
        const key=kind==='zip'?i.id:i.id+':mp4';
        if(!d||d.request_id!==i.id||d.content_version!==i.version||d.requested||this.receipts.includes(key))continue;
        // 先保存每一檔的收據，重建或rerun不再次點擊；不代表已存到電腦。
        this.receipts=[...this.receipts,key].slice(-60);this.save();
        try{this.h.download(d);(i.downloads??={})[kind]='已提出下載請求';requested.push({kind,operation_id:i.id,content_version:i.version});}
        catch(error){(i.downloads??={})[kind]='自動下載未能觸發，請使用備用下載';i.message='瀏覽器未能自動下載，請按旁邊「備用下載」。';}
        this.save();
      }
      if(requested.length===1&&requested[0].kind==='zip')this.h.post({action:'zip_download_requested',nonce:this.h.uuid(),operation_id:i.id,content_version:i.version});
      else if(requested.length)this.h.post({action:'downloads_requested',nonce:this.h.uuid(),downloads:requested});
    }
    retryZip(){
      if(this.busy()||!this.intent?.retryZip)throw new Error('目前沒有可重試的ZIP快照。');
      const prior=this.intent,id=this.h.uuid();this.intent={id,kind:'zip',version:prior.version,phase:'working',verified:true};this.save();
      this.h.post({action:'retry_output_zip',nonce:id,operation_id:prior.id,content_version:prior.version});
    }
    fail(message){if(this.intent){this.intent.phase='error';this.intent.message=message;this.save();
      if(this.sentCancel!==this.intent.id){this.sentCancel=this.intent.id;this.h.post({action:'cancel_output',nonce:this.h.uuid(),operation_id:this.intent.id});}}}
    status(){
      const i=this.intent;let message='下載ZIP與輸出影片會自動準備最新草稿。';
      if(i?.phase==='syncing')message='正在同步指定版本…可繼續編輯。';
      if(i?.phase==='working')message=i.kind==='zip'?'正在產生ZIP…可繼續編輯。':'正在輸出MP4…可繼續編輯。';
      if(i?.phase==='done')message=i.kind==='zip'?'ZIP已準備完成；請確認檔案已保存。':'MP4已完成；後續修改需另行輸出。';
      if(i?.artifacts&&['done','error'].includes(i.phase))message=Object.entries(i.artifacts).map(([kind,a])=>`${kind.toUpperCase()}：${a.phase==='done'?(i.downloads?.[kind]||'已產生，請使用備用下載'):'失敗，'+a.message}`).join('；')+'。瀏覽器可能阻擋多檔下載，請確認檔案已保存。';
      if(i?.message)message=i.artifacts?i.message+' '+message:i.message;
      if(i?.phase==='done'&&this.h.current&&i.version!==this.h.current())message+=' 此檔是舊版本，後續修改尚未包含。';
      return {busy:this.busy(),message,error:i?.phase==='error'||Object.values(i?.artifacts||{}).some(a=>a.phase==='error'),delivery:this.delivery,mp4Delivery:this.mp4Delivery,zipBackup:this.zipBackup,retryZip:!!i?.retryZip};
    }
  }
  if(typeof module!=='undefined')module.exports={OutputController};else root.StudioOutput={OutputController};
})(typeof window!=='undefined'?window:this);
