const test=require('node:test'),assert=require('node:assert/strict');
const {OutputController}=require('../frontend/output-controller.js');
function setup(saved){
  let serial=0,resolve,reject,version='A';const sent=[],files=[],stored=[];
  const c=new OutputController({uuid:()=>`id-${++serial}`,pending:()=>false,version:()=>version,
    persist:()=>stored.push(JSON.parse(JSON.stringify(c.persisted()))),
    sync:(action,id,width)=>new Promise((yes,no)=>{resolve=yes;reject=no;sent.push({action,id,width,version});}),
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
