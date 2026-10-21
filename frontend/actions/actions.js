'use strict';
let args={},localBusy=false,lastHeight=null;
const $=id=>document.getElementById(id);
function peer(){
  // 明確的應用程式介面；不查詢或點擊Streamlit內部DOM。
  for(let i=0;i<window.parent.frames.length;i++){
    try{const bridge=window.parent.frames[i].StudioOutputBridge;if(bridge?.session()===args.session)return bridge;}catch(error){}
  }
  return null;
}
function refresh(){
  const bridge=peer(),state=bridge?.status(),locked=!bridge||!!args.locked||localBusy||state?.busy;
  $('mp4').disabled=locked;$('zip').disabled=locked;
  $('zipBackup').disabled=!bridge||!!args.locked||localBusy;
  if(bridge)$('zipBackup').checked=state.zipBackup!==false;
  if(!localBusy){$('status').textContent=state?.message||'正在連接編輯器…';$('status').className=state?.error?'error':'';}
  for(const [id,delivery] of [['fallback',state?.delivery],['mp4Fallback',state?.mp4Delivery]]){
    const ready=delivery&&delivery.expires_at>Date.now()/1000?delivery:null;$(id).hidden=!ready;
    if(ready){$(id).href=ready.url;$(id).download=ready.filename;$(id).textContent=`備用下載${id==='fallback'?'ZIP':'MP4'}（版本 ${ready.content_version.slice(4,16)}）`;}
    if(delivery&&!ready&&!state.busy)$('status').textContent+=' 短效連結已過期，請使用下方原生下載。';
  }
  $('retryZip').hidden=!state?.retryZip;$('retryZip').disabled=locked;
  const height=Math.max(90,Math.ceil(document.body.getBoundingClientRect().height)+8);
  if(height!==lastHeight){lastHeight=height;window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height},'*');}
}
async function request(kind){
  if(localBusy)return;const bridge=peer();if(!bridge)return;
  localBusy=true;$('status').textContent='正在取得最新草稿…';refresh();
  try{await bridge.capture(kind,args.width);}catch(error){$('status').textContent=error.message;$('status').className='error';}
  finally{localBusy=false;refresh();}
}
$('zip').onclick=()=>request('zip');$('mp4').onclick=()=>request('mp4');
$('zipBackup').onchange=()=>peer()?.setZipBackup($('zipBackup').checked);
$('retryZip').onclick=()=>{try{peer()?.retryZip();}catch(error){$('status').textContent=error.message;}refresh();};
$('fallback').onclick=()=>peer()?.downloadRequested();
$('mp4Fallback').onclick=()=>peer()?.downloadRequested('mp4');
window.addEventListener('message',event=>{if(event.source===window.parent&&event.data?.type==='streamlit:render'){args=event.data.args;refresh();}});
setInterval(refresh,500);
window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
