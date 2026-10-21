const test=require('node:test'),assert=require('node:assert/strict');
const {OutputController}=require('../frontend/output-controller.js');
function setup(saved){
  let serial=0,resolve,reject,version='A';const sent=[],files=[],stored=[];
  const c=new OutputController({uuid:()=>`id-${++serial}`,pending:()=>false,version:()=>version,
    persist:()=>stored.push(JSON.parse(JSON.stringify(c.persisted()))),
    sync:(action,id,width,options)=>new Promise((yes,no)=>{resolve=yes;reject=no;sent.push({action,id,width,version,options});}),
    post:e=>sent.push(e),download:d=>files.push(d)});
  if(saved)c.restore(saved);
  return {c,sent,files,stored,change:v=>version=v,resolve:()=>resolve(),reject:e=>reject(e)};
}
test('精確ACK後才啟動固定版本，期間新修改不混入且快速連點只送一次',async()=>{
  const x=setup(),p=x.c.request('zip',1080),id=x.c.intent.id;
  await assert.rejects(x.c.request('zip',1080));assert.equal(x.sent.length,1);x.change('B');
  x.c.ack({nonce:'old',ok:true,content_version:'A',operation_id:'old'});assert.equal(x.sent.length,1);
  x.c.ack({nonce:id,ok:true,content_version:'A',operation_id:id});x.resolve();await p;
  assert.equal(x.sent[1].action,'start_output');assert.equal(x.sent[1].content_version,'A');
  x.c.receive({id,phase:'prepared'},null);assert.equal(x.sent.length,2);
});
test('錯版本ACK不啟動，取消準備並允許重新要求；同步失敗不觸發下載',async()=>{
  const x=setup(),p=x.c.request('mp4',360),id=x.c.intent.id;
  x.c.ack({nonce:id,ok:true,content_version:'B',operation_id:id});x.resolve();await p;
  assert.equal(x.sent.filter(e=>e.action==='start_output').length,0);
  assert.equal(x.sent[1].action,'cancel_output');assert.equal(x.c.status().error,true);
  const retry=x.c.request('zip',360);x.reject(new Error('同步失敗'));await assert.rejects(retry);
  assert.equal(x.files.length,0);assert.ok(x.c.status().message.includes('同步失敗'));
});
test('ZIP完整且版本符合才自動下載，rerun與元件重建不重複，收據先保存',async()=>{
  const x=setup(),p=x.c.request('zip',1080),id=x.c.intent.id;
  x.c.ack({nonce:id,ok:true,operation_id:id,content_version:'A'});x.resolve();await p;
  const done={id,phase:'done'},d={request_id:id,content_version:'wrong',url:'/file.zip',filename:'a.zip'};
  x.c.receive(done,d);assert.equal(x.files.length,0);
  d.content_version='A';x.c.receive(done,d);assert.equal(x.files.length,1);
  assert.ok(x.stored.at(-1).receipts.includes(id));x.c.receive(done,d);assert.equal(x.files.length,1);
  const rebuilt=setup(x.c.persisted());rebuilt.c.receive(done,d);assert.equal(rebuilt.files.length,0);
  assert.equal(x.sent.at(-1).action,'zip_download_requested');
  assert.equal('backup_confirmed_version' in x.c.persisted(),false);
});
test('自動下載阻擋保留備援連結、不重複嘗試，工作重建可續接已確認的準備',async()=>{
  const x=setup(),p=x.c.request('zip',1080),id=x.c.intent.id;
  x.c.ack({nonce:id,ok:true,operation_id:id,content_version:'A'});x.resolve();await p;
  const restarted=setup(x.c.persisted());restarted.c.receive({id,phase:'prepared'},null);
  assert.equal(restarted.sent[0].action,'start_output');
  restarted.c.h.download=()=>{throw new Error('blocked');};
  const d={request_id:id,content_version:'A'};restarted.c.receive({id,phase:'done'},d);
  assert.ok(restarted.c.status().message.includes('備用下載'));assert.equal(restarted.c.status().delivery,d);
  restarted.c.receive({id,phase:'done'},d);assert.equal(restarted.c.receipts.length,1);
});

test('ACK清除pending後元件恰好重建，可用精確seq與版本續接；取消遺失可安全補送',async()=>{
  const x=setup(),p=x.c.request('zip',1080),id=x.c.intent.id;
  const rebuilt=setup(x.c.persisted());
  rebuilt.c.receive({id,phase:'prepared',version:'A'},null,{nonce:id,operation_id:id,ok:true,content_version:'A'});
  assert.equal(rebuilt.sent[0].action,'start_output');
  const lost=setup(x.c.persisted());lost.c.receive(null,null);
  assert.equal(lost.c.status().error,true);assert.equal(lost.c.busy(),false);
  const interrupted=setup(x.c.persisted());interrupted.c.fail('cancelled');
  const retry=setup(interrupted.c.persisted());retry.c.receive({id,phase:'prepared',version:'A'},null);
  assert.equal(retry.sent[0].action,'cancel_output');retry.c.receive({id,phase:'prepared',version:'A'},null);
  assert.equal(retry.sent.length,1);
  x.resolve();await p;
});

test('ZIP備份預設勾選、取消後重建保留，輸出選項只傳握手不改內容版本',async()=>{
  const x=setup();assert.equal(x.c.status().zipBackup,true);x.c.setZipBackup(false);
  const y=setup(x.c.persisted());assert.equal(y.c.status().zipBackup,false);
  const p=y.c.request('mp4',360);assert.equal(y.sent[0].options.zip_backup,false);assert.equal(y.c.intent.version,'A');y.resolve();await p;
  const z=setup(),q=z.c.request('mp4',360);assert.equal(z.sent[0].options.zip_backup,true);z.resolve();await q;
});

test('MP4與ZIP分檔去重、先存收據，連續rerun／重建不再下載且收據合併送出',async()=>{
  const x=setup(),p=x.c.request('mp4',360),id=x.c.intent.id;
  x.c.ack({nonce:id,ok:true,content_version:'A',operation_id:id});x.resolve();await p;x.change('B');
  const status={id,phase:'done',artifacts:{mp4:{phase:'done'},zip:{phase:'done'}}};
  const zip={request_id:id,content_version:'A',filename:'a.zip'},mp4={request_id:id,content_version:'A',filename:'a.mp4'};
  x.c.receive(status,zip,null,mp4);assert.deepEqual(x.files.map(f=>f.filename),['a.mp4','a.zip']);
  assert.ok(x.c.receipts.includes(id)&&x.c.receipts.includes(id+':mp4'));assert.equal(x.sent.at(-1).action,'downloads_requested');assert.equal(x.sent.at(-1).downloads.length,2);
  x.c.receive(status,zip,null,mp4);assert.equal(x.files.length,2);
  const rebuilt=setup(x.c.persisted());rebuilt.c.receive(status,zip,null,mp4);assert.equal(rebuilt.files.length,0);
  assert.equal(x.c.status().zipBackup,true);assert.equal('backup_confirmed_version' in x.c.persisted(),false);
});

test('單檔被阻擋不阻止另一檔，錯版本與舊成果不冒充本次下載',async()=>{
  const x=setup(),p=x.c.request('mp4',360),id=x.c.intent.id;
  x.c.ack({nonce:id,ok:true,content_version:'A',operation_id:id});x.resolve();await p;
  x.c.h.download=d=>{if(d.filename.endsWith('.mp4'))throw new Error('blocked');x.files.push(d);};
  const zip={request_id:id,content_version:'A',filename:'a.zip'},mp4={request_id:id,content_version:'wrong',filename:'a.mp4'};
  const done={id,phase:'done',artifacts:{zip:{phase:'done'},mp4:{phase:'done'}}};
  x.c.receive(done,zip,null,mp4);assert.equal(x.files.length,1);mp4.content_version='A';x.c.receive(done,zip,null,mp4);
  assert.ok(x.c.status().message.includes('備用下載'));assert.equal(x.c.status().mp4Delivery,mp4);
  x.c.receive(done,zip,null,mp4);assert.equal(x.files.length,1);
});

test('部分失敗只下載成功檔、ZIP重試鎖定原版本且不重新捕捉草稿',async()=>{
  const x=setup(),p=x.c.request('mp4',360),id=x.c.intent.id;
  x.c.ack({nonce:id,ok:true,content_version:'A',operation_id:id});x.resolve();await p;x.change('B');
  const zip={request_id:'old',content_version:'old'},mp4={request_id:id,content_version:'A',filename:'a.mp4'};
  x.c.receive({id,phase:'done',retry_zip:true,artifacts:{mp4:{phase:'done'},zip:{phase:'error',message:'ZIP失敗'}}},zip,null,mp4);
  assert.equal(x.files.length,1);assert.equal(x.files[0],mp4);assert.equal(x.c.status().retryZip,true);assert.equal(x.c.status().error,true);
  x.c.retryZip();const retry=x.sent.at(-1);assert.equal(retry.action,'retry_output_zip');assert.equal(retry.operation_id,id);assert.equal(retry.content_version,'A');assert.notEqual(retry.nonce,id);
  assert.equal(x.c.intent.version,'A');assert.equal(x.c.intent.kind,'zip');assert.equal(x.sent.filter(e=>e.action==='export').length,1);
});

test('ZIP成功但MP4失敗仍可自動下載ZIP，兩者失敗不下載舊成果',async()=>{
  for(const zipOk of [true,false]){
    const x=setup(),p=x.c.request('mp4',360),id=x.c.intent.id;
    x.c.ack({nonce:id,ok:true,content_version:'A',operation_id:id});x.resolve();await p;
    x.c.receive({id,phase:zipOk?'done':'error',message:'本次失敗',retry_zip:!zipOk,artifacts:{mp4:{phase:'error',message:'MP4故障'},zip:{phase:zipOk?'done':'error',message:'ZIP故障'}}},
      {request_id:id,content_version:'A',filename:'a.zip'},null,{request_id:'previous',content_version:'previous',filename:'old.mp4'});
    assert.equal(x.files.length,zipOk?1:0);if(zipOk)assert.equal(x.files[0].filename,'a.zip');
    assert.equal(x.c.status().error,true);
  }
});
