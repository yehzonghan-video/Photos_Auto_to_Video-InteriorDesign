// 不保存照片內容；草稿僅含目前工作階段的編輯資料。
(function (root) {
  const clone = value => JSON.parse(JSON.stringify(value));
  const metadata = rows => rows.map(({image, tiles, ...row}) => clone(row));
  function merge(local, remote) {
    const live = new Map(remote.map(row => [row.id, row]));
    const old = new Map(local.map(row => [row.id, row]));
    // 本地排序／刪除保留，新上傳的照片加在最後；後端刪除的照片不復活。
    return [...local.filter(row => live.has(row.id)).map(row => ({...live.get(row.id), ...row,
      name:live.get(row.id).name,image:live.get(row.id).image, tiles:live.get(row.id).tiles})),
      ...remote.filter(row => !old.has(row.id))];
  }
  class DraftState {
    constructor() {this.session=null;this.revision=-1;this.seq=0;this.dirty=false;this.pending=null;this.rows=[];this.deleted=[];}
    restore(saved, session) {
      if (!saved || saved.session!==session || !Array.isArray(saved.rows)) return false;
      Object.assign(this, saved); this.rows=clone(saved.rows);return true;
    }
    touch(rows) {this.rows=rows;this.seq++;this.dirty=true;}
    snapshot(nonce, action='apply', request=null) {
      if(this.pending)throw new Error('正在套用上一批變更，請稍候。');
      this.pending={nonce,seq:this.seq};
      return {session:this.session,base_revision:this.revision,nonce,action,request,seq:this.seq,photos:metadata(this.rows)};
    }
    receive(rows, session, revision, response) {
      if(this.session!==session) {
        this.session=session;this.revision=revision;this.seq=0;this.dirty=false;this.pending=null;this.deleted=[];this.rows=rows;
        return {fresh:true};
      }
      if(revision<this.revision)return {stale:true};
      const matched=this.pending&&response?.nonce===this.pending.nonce;
      const success=matched&&response.ok;
      const newer=matched&&this.seq!==this.pending.seq;
      if(success&&!newer) {this.rows=rows;this.dirty=false;this.deleted=[];}
      else if(this.dirty||this.pending) {
        this.rows=merge(this.rows,rows.filter(row=>!this.deleted.includes(row.id)));
      }else this.rows=rows;
      this.revision=revision;
      if(matched&&!response.ok)this.dirty=true;
      if(matched)this.pending=null;
      return {matched,success,newer,error:matched&&!response.ok?response.message:null};
    }
    persisted(selection={}) {
      return {session:this.session,revision:this.revision,seq:this.seq,dirty:this.dirty,pending:this.pending,
        deleted:this.deleted,rows:metadata(this.rows),selection};
    }
  }
  const api={DraftState,metadata};
  if(typeof module!=='undefined')module.exports=api;else root.StudioDraft=api;
})(typeof window!=='undefined'?window:this);
