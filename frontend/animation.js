(function (root) {
  function pose(label, time) {
    if (time < label.start || time >= label.end) return null;
    const p = label.enter ? Math.min(1, (time - label.start) / label.enter) : 1;
    const ease = 1 - Math.pow(1 - p, 3), remaining = 1 - ease;
    let x = 0, y = 0, scale = 1, alpha = 1;
    if (label.animation === 'left') x = -.22 * remaining;
    if (label.animation === 'right') x = .22 * remaining;
    if (label.animation === 'up') y = -.16 * remaining;
    if (label.animation === 'down') y = .16 * remaining;
    if (label.animation === 'fade') alpha = ease;
    if (label.animation === 'scale') { scale = .65 + .35 * ease; alpha = ease; }
    if (!['none', 'fade', 'scale'].includes(label.animation)) alpha = ease;
    // 文字換字使用淡出，不移動位置；PNG 的出場仍由 overlayPose 處理。
    if(label.exit&&time>label.end-label.exit){
      const q=Math.min(1,(label.end-time)/label.exit);
      alpha*=1-Math.pow(1-q,3);
    }
    return {x, y, scale, alpha};
  }
  function overlayPose(item,time){
    const end=item.start+item.duration;
    let entry=pose({start:item.start,end,enter:item.enter,animation:item.animation},time);
    if(!entry)return null;
    if(item.exit&&time>end-item.exit){
      const leaving=pose({start:0,end:item.exit+1,enter:item.exit,animation:item.exit_animation},end-time);
      entry={x:entry.x+leaving.x,y:entry.y+leaving.y,scale:entry.scale*leaving.scale,alpha:entry.alpha*leaving.alpha};
    }
    return entry;
  }
  if (typeof module !== 'undefined') module.exports = {pose,overlayPose};
  else root.StudioAnimation = {pose,overlayPose};
})(typeof window !== 'undefined' ? window : this);
