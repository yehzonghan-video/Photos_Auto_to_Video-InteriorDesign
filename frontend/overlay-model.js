(function(root){
  function geometry(o,asset,W=1080,H=1920){
    let w=Math.max(1,Math.floor(W*o.width*o.scale+.5)),h=Math.max(1,Math.floor(w*asset.height/asset.width+.5));
    const angle=o.rotation*Math.PI/180,c=Math.abs(Math.cos(angle)),s=Math.abs(Math.sin(angle));
    const factor=Math.min(1,(W-4)/(w*c+h*s),(H-4)/(w*s+h*c));
    w=Math.max(1,Math.floor(w*factor));h=Math.max(1,Math.floor(h*factor));
    const bw=w*c+h*s,bh=w*s+h*c;
    return {width:w,height:h,x:Math.max(bw/2,Math.min(W-bw/2,o.x*W)),y:Math.max(bh/2,Math.min(H-bh/2,o.y*H)),box_width:bw,box_height:bh};
  }
  const api={geometry};if(typeof module!=='undefined')module.exports=api;else root.StudioOverlay=api;
})(typeof window!=='undefined'?window:this);
