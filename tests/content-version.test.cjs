const test=require('node:test');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const V=require('../frontend/content-version.js');
const {DraftState}=require('../frontend/draft-state.js');
const schema=require('../frontend/content-schema.json');
const context={schema,photos:{p:'media-hash'},assets:[],music:null,width:1080,engine:'renderer'};
function initialized(){
  const d=new DraftState();d.receive([{id:'p',name:'照片😀',duration:4,labels:[],image:'preview'}],'s',1);
  const version=V.version(d,context);d.configureVersions({context,synced:version,mp4:version,zip:version,backup:version});return d;
}

test('SHA256與Node標準實作一致，Unicode與長文字可正確雜湊',()=>{
  for(const value of ['', 'abc','😀繁體中文\n','a'.repeat(10000)])assert.equal(V.sha256(value),crypto.createHash('sha256').update(value).digest('hex'));
  assert.equal(V.digest({a:1,b:-0}),V.digest({b:0,a:1.0}));
});

test('相同內容不增加草稿序號，媒體及輸出設定變更會改版本，重建保持',()=>{
  const d=initialized(),first=d.contentVersion,seq=d.seq;
  for(let i=0;i<100;i++)d.touch(d.rows);
  assert.equal(d.seq,seq);assert.equal(d.dirty,false);
  d.rows[0].name='新照片';d.touch(d.rows);assert.notEqual(d.contentVersion,first);assert.equal(d.dirty,true);
  const saved=JSON.parse(JSON.stringify(d.persisted()));assert.equal(JSON.stringify(saved).includes('preview'),false);
  const restored=new DraftState();restored.restore(saved,'s');assert.equal(restored.currentVersion(),d.currentVersion());
  const current=d.currentVersion();d.configureVersions({...d.versions,context:{...context,width:720}});assert.notEqual(d.currentVersion(),current);
  assert.notEqual(V.version(d,{...context,photos:{p:'replaced-media'}}),V.version(d,context));
});

test('舊同步回應不覆蓋較新草稿與版本；還原到既有內容取得相同版本',()=>{
  const d=initialized(),initial=d.contentVersion;
  d.rows[0].duration=5;d.touch(d.rows);const submitted=d.currentVersion(),sent=d.snapshot('n');
  d.rows[0].duration=6;d.touch(d.rows);const newest=d.currentVersion();
  d.receive(sent.photos,'s',2,{nonce:'n',ok:true,content_version:submitted});
  d.configureVersions({...d.versions,synced:submitted});
  assert.equal(d.currentVersion(),newest);assert.equal(d.contentVersion,newest);assert.equal(d.dirty,true);
  assert.equal(d.receive([], 's',1).stale,true);assert.equal(d.currentVersion(),newest);
  d.rows[0].duration=4;d.touch(d.rows);assert.equal(d.currentVersion(),initial);
});
