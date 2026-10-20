// 單次刪除交易：只留設定，不把圖片／音訊放進歷史；後續內容改動時保守拒絕覆寫。
(function(root){
  const clone=v=>JSON.parse(JSON.stringify(v));
  const clean=p=>{const {image,tiles,...row}=p;return clone(row);};
  function state(d){return {rows:d.rows.map(clean),comparisons:d.comparisons.map(clean),cover:clone(d.cover),overlays:clone(d.overlays),comparisonOverlays:clone(d.comparisonOverlays),tour:clone(d.tour??null)};}
  const canonical=v=>v&&typeof v==='object'?(Array.isArray(v)?v.map(canonical):Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]))):v;
  const signature=d=>d.currentVersion?.()||JSON.stringify(canonical(state(d)));
  function impact(d,id){const p=d.rows.find(p=>p.id===id);if(!p)return null;
    return {clips:d.comparisons.filter(c=>c.before_id===id||c.after_id===id).length,tour_clips:(d.tour?.clips||[]).filter(c=>c.kind==='photo'&&c.source===id).length,cover:d.cover?.photo_id===id,labels:p.labels.length};}
  class History{
    constructor(){this.entry=null;this.preview=null;this.restored=null;}
    begin(d,id){const p=d.rows.find(p=>p.id===id);if(!p)return false;this.entry={id,before:state(d),after:null};this.preview=p;this.restored=null;return true;}
    finish(d){this.entry.after=state(d);this.entry.afterVersion=signature(d);}
    restore(d,media){const e=this.entry;if(!e)throw new Error('目前沒有可復原的刪除。');
      if(d.rows.length>=12)throw new Error('已達12張來源上限，無法復原；目前內容保留。');
      if(signature(d)!==e.afterVersion)throw new Error('刪除後內容已變更，為避免覆蓋新編輯，無法安全復原。');
      const p=media.find(p=>p.id===e.id)||this.preview;
      if(!p?.image)throw new Error('復原來源已失效，請從ZIP還原或重新上傳。');
      const images=new Map(d.rows.concat([p]).map(p=>[p.id,p]));
      d.rows=e.before.rows.map(row=>({...images.get(row.id),...clone(row)}));
      for(const k of ['comparisons','cover','overlays','comparisonOverlays'])d[k]=clone(e.before[k]);if(e.before.tour)d.tour=clone(e.before.tour);
      d.deleted=d.deleted.filter(id=>id!==e.id);this.restored=e.id;this.entry=null;this.preview=null;return e.id;
    }
    persisted(){return {entry:this.entry,restored:this.restored};}
    load(saved){this.entry=saved?.entry||null;this.restored=saved?.restored||null;this.preview=null;}
  }
  const api={History,impact,state};if(typeof module!=='undefined')module.exports=api;else root.StudioPhotoHistory=api;
})(typeof window!=='undefined'?window:this);
