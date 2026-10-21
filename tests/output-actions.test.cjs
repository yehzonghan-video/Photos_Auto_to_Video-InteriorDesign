// 真actions.js搭配合成DOM；實際下載及版面仍由瀏覽器驗收。
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('輸出列預設備份、rerun保留選項、兩種備用入口與高度更新不循環增加',async()=>{
  const html=fs.readFileSync('frontend/actions/index.html','utf8');assert.match(html,/<input id="zipBackup"[^>]*checked/);
  const elements=new Map(),messages=[],listeners={},captured=[];let timer;
  const state={zipBackup:true,busy:false,message:'完成',delivery:{url:'/zip',filename:'x.zip',expires_at:9999999999,content_version:'cv1-ABC'},mp4Delivery:{url:'/mp4',filename:'x.mp4',expires_at:9999999999,content_version:'cv1-ABC'}};
  const bridge={session:()=> 'test',status:()=>state,setZipBackup:v=>state.zipBackup=v,capture:async(...args)=>captured.push(args),downloadRequested(){},retryZip(){}};
  const parent={frames:[{StudioOutputBridge:bridge}],postMessage:e=>messages.push(e)};
  const document={body:{getBoundingClientRect:()=>({height:168})},getElementById:id=>{if(!elements.has(id))elements.set(id,{checked:true});return elements.get(id);}};
  const context=vm.createContext({document,window:{parent,addEventListener:(n,fn)=>listeners[n]=fn},Date,setInterval:fn=>timer=fn});
  vm.runInContext(fs.readFileSync('frontend/actions/actions.js','utf8'),context);
  const render=()=>listeners.message({source:parent,data:{type:'streamlit:render',args:{session:'test',width:360}}});render();
  assert.equal(elements.get('zipBackup').checked,true);elements.get('zipBackup').checked=false;elements.get('zipBackup').onchange();render();assert.equal(elements.get('zipBackup').checked,false);
  for(let n=0;n<100;n++)timer();assert.equal(messages.filter(e=>e.type==='streamlit:setFrameHeight').length,1);
  assert.equal(elements.get('fallback').hidden,false);assert.equal(elements.get('mp4Fallback').hidden,false);
  assert.match(elements.get('fallback').textContent,/ABC/);await elements.get('mp4').onclick();await elements.get('zip').onclick();
  assert.deepEqual(captured,[['mp4',360],['zip',360]]);
});
