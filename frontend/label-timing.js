// 人工、AI及舊草稿共用延後規則；不傳送任何Streamlit事件。
(function(root){
  function delay(label,duration){
    if(label.label_timing_version===1||['before','after'].includes(label.comparison_side))return false;
    let start=label.start??0,end=label.end??duration;
    if(![start,end,duration].every(Number.isFinite)||start<0||end<=start||end>duration)return false;
    end=Math.max(end,Math.min(duration,1/30));
    Object.assign(label,{start:Math.min(start+1,Math.max(0,end-1/30)),end,label_timing_version:1});
    label.enter=Math.min(label.enter??.6,end-label.start);
    if(label.exit!=null)label.exit=Math.min(label.exit,end-label.start);
    if(end-label.start<=1/30+1e-8){label.enter=0;if(label.exit!=null)label.exit=0;}
    return true;
  }
  if(typeof module!=='undefined')module.exports={delay};else root.StudioLabelTiming={delay};
})(typeof window!=='undefined'?window:this);
