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
  if(!localBusy){$('status').textContent=state?.message||'正在連接編輯器…';$('status').className=state?.error?'error':'';}
  const ready=state?.delivery&&state.delivery.expires_at>Date.now()/1000?state.delivery:null;$('fallback').hidden=!ready;
  if(state?.delivery&&!ready&&!state.busy)$('status').textContent='短效連結已過期；請用下方備用下載，或重新產生ZIP。';
  if(ready){$('fallback').href=ready.url;$('fallback').download=ready.filename;}
  const height=ready?118:90;
  if(height!==lastHeight){lastHeight=height;window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height},'*');}
}
async function request(kind){
  if(localBusy)return;const bridge=peer();if(!bridge)return;
  localBusy=true;$('status').textContent='正在取得最新草稿…';refresh();
  try{await bridge.capture(kind,args.width);}catch(error){$('status').textContent=error.message;$('status').className='error';}
  finally{localBusy=false;refresh();}
}
$('zip').onclick=()=>request('zip');$('mp4').onclick=()=>request('mp4');
$('fallback').onclick=()=>peer()?.downloadRequested();
window.addEventListener('message',event=>{if(event.source===window.parent&&event.data?.type==='streamlit:render'){args=event.data.args;refresh();}});
setInterval(refresh,500);
window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
