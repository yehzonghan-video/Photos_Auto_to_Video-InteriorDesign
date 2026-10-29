// Streamlit Cloud may need longer than one rerun to return a component ACK.
// Reposting the same nonce is safe because Python deduplicates editor events.
(function(root){
  const RETRY_DELAYS=Object.freeze([15000,45000]);
  const HARD_TIMEOUT=120000;

  function watch({retry,onSlow,onTimeout,setTimer=setTimeout,clearTimer=clearTimeout,
                  retryDelays=RETRY_DELAYS,timeout=HARD_TIMEOUT}){
    let active=true;
    const timers=retryDelays.map((delay,index)=>setTimer(()=>{
      if(!active)return;
      onSlow?.(index+1,delay);
      retry?.(index+1);
    },delay));
    timers.push(setTimer(()=>{if(active){active=false;onTimeout?.();}},timeout));
    return {cancel(){if(!active)return;active=false;for(const timer of timers)clearTimer(timer);}};
  }

  const api={RETRY_DELAYS,HARD_TIMEOUT,watch};
  if(typeof module!=='undefined')module.exports=api;else root.StudioSyncTransport=api;
})(typeof window!=='undefined'?window:this);
