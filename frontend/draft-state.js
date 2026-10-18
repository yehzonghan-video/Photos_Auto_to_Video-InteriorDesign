// 不保存照片內容；草稿僅含目前工作階段的編輯資料。
(function (root) {
  const V=typeof module!=='undefined'?require('./content-version.js'):root.StudioVersion;
  const clone = value => JSON.parse(JSON.stringify(value));
  const metadata = rows => rows.map(({image, tiles, ...row}) => clone(row));
  function merge(local, remote) {
    const live = new Map(remote.map(row => [row.id, row]));
    const old = new Map(local.map(row => [row.id, row]));
    // 本地排序／刪除保留，新上傳的照片加在最後；後端刪除的照片不復活。
    return [...local.filter(row => live.has(row.id)).map(row => ({...live.get(row.id), ...row,
      name:live.get(row.id).name,image:live.get(row.id).image, tiles:live.get(row.id).tiles,
      labels:row.content_hash&&row.content_hash!==live.get(row.id).content_hash
        ?row.labels.map(l=>l.source==='gemini'?{...l,needs_review:true}:l):row.labels,
      content_hash:live.get(row.id).content_hash})),
      ...remote.filter(row => !old.has(row.id))];
  }
  class DraftState {
    constructor() {this.session=null;this.revision=-1;this.seq=0;this.dirty=false;this.pending=null;this.rows=[];this.deleted=[];this.imported=[];this.overlays=[];this.comparisons=[];this.comparisonOverlays=[];this.template='items';this.cover=null;this.coverSeconds=null;this.music=null;}
    restore(saved, session) {
      if (!saved || saved.session!==session || !Array.isArray(saved.rows)) return false;
      Object.assign(this, saved); this.rows=clone(saved.rows);return true;
    }
    currentVersion(){if(!this.versionContext)return null;V.configure(this.versionContext.schema);return V.version(this,this.versionContext);}
    configureVersions(versions){
      if(!versions?.context)return;
      V.configure(versions.context.schema);this.versionContext=versions.context;this.versions=versions;
      this.contentVersion=this.currentVersion();this.dirty=this.contentVersion!==versions.synced;
    }
    touch(rows) {this.rows=rows;const version=this.currentVersion();
      if(version&&version===this.contentVersion)return;
      this.contentVersion=version;this.seq++;this.dirty=version?version!==this.versions?.synced:true;}
    snapshot(nonce, action='apply', request=null) {
      if(this.pending)throw new Error('正在套用上一批變更，請稍候。');
      this.pending={nonce,seq:this.seq};
      return {session:this.session,base_revision:this.revision,nonce,action,request,seq:this.seq,
        ...(this.currentVersion()?{content_version:this.currentVersion()}:{}),photos:metadata(this.rows),
        overlays:clone(this.overlays),comparisons:metadata(this.comparisons),comparison_overlays:clone(this.comparisonOverlays),
        cover:clone(this.cover),music:clone(this.music),template_id:this.template,schema_version:4,imported_batches:[...this.imported]};
    }
    receive(rows, session, revision, response, overlays=[], comparisons=[], comparisonOverlays=[],cover=null,music=null) {
      if(this.session!==session) {
        this.session=session;this.revision=revision;this.seq=0;this.dirty=false;this.pending=null;this.deleted=[];this.imported=[];this.rows=rows;this.overlays=clone(overlays);this.comparisons=comparisons;this.comparisonOverlays=clone(comparisonOverlays);
        this.cover=clone(cover);this.music=clone(music);this.versionContext=null;this.versions=null;this.contentVersion=null;return {fresh:true};
      }
      if(revision<this.revision)return {stale:true};
      const matched=this.pending&&response?.nonce===this.pending.nonce;
      const success=matched&&response.ok;
      const newer=matched&&this.seq!==this.pending.seq;
      if((success&&!newer)||(!this.dirty&&!this.pending)||this.cover===null)this.cover=clone(cover);
      if((success&&!newer)||(!this.dirty&&!this.pending)||this.music===null)this.music=clone(music);
      else if(music)this.music.source=music.source; // 上傳／移除採伺服器來源，未套用音量與淡出仍保留。
      if(success&&!newer) {this.rows=rows;this.overlays=clone(overlays);this.comparisons=comparisons;this.comparisonOverlays=clone(comparisonOverlays);this.dirty=false;this.deleted=[];}
      else if(this.dirty||this.pending) {
        const changed=new Set(this.rows.filter(p=>p.content_hash&&rows.some(r=>r.id===p.id&&r.content_hash!==p.content_hash)).map(p=>p.id));
        for(const c of this.comparisons)if(changed.has(c.before_id)||changed.has(c.after_id))
          for(const l of c.labels)if(l.source==='gemini')l.needs_review=true;
        this.rows=merge(this.rows,rows.filter(row=>!this.deleted.includes(row.id)));
      }else {this.rows=rows;this.overlays=clone(overlays);this.comparisons=comparisons;this.comparisonOverlays=clone(comparisonOverlays);}
      this.revision=revision;
      if(matched&&!response.ok)this.dirty=true;
      if(matched)this.pending=null;
      return {matched,success,newer,error:matched&&!response.ok?response.message:null};
    }
    persisted(selection={}) {
      return {session:this.session,revision:this.revision,seq:this.seq,dirty:this.dirty,pending:this.pending,
        deleted:this.deleted,imported:this.imported,rows:metadata(this.rows),overlays:clone(this.overlays),
        comparisons:metadata(this.comparisons),comparisonOverlays:clone(this.comparisonOverlays),cover:clone(this.cover),coverSeconds:this.coverSeconds,music:clone(this.music),template:this.template,
        versionContext:this.versionContext,versions:this.versions,contentVersion:this.contentVersion,selection};
    }
  }
  const api={DraftState,metadata};
  if(typeof module!=='undefined')module.exports=api;else root.StudioDraft=api;
})(typeof window!=='undefined'?window:this);
