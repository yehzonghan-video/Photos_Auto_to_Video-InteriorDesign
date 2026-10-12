// 未套用時用本機字型即時繪製；套用後選用伺服器 PNG，與最終 MP4 一致。
(function (root) {
  const fields=['text','font_size','color','background','opacity','radius'];
  function key(label) {return JSON.stringify(fields.map(field=>label[field]));}
  function raster(label, createCanvas) {
    const canvas=createCanvas(), ctx=canvas.getContext('2d'), size=Math.trunc(label.font_size);
    const font=`${size}px "Microsoft JhengHei", "Noto Sans CJK TC", sans-serif`;
    ctx.font=font;
    const lines=[];let line='';
    for(const char of label.text) {
      if(char==='\n'||(line&&ctx.measureText(line+char).width>800)){lines.push(line);line=char==='\n'?'':char;}
      else line+=char;
    }
    lines.push(line);
    const step=Math.trunc(size*1.35),padding=24;
    canvas.width=Math.min(848,Math.trunc(Math.max(...lines.map(text=>ctx.measureText(text).width)))+48);
    canvas.height=lines.length*step+48;
    ctx.font=font;ctx.textBaseline='top';ctx.fillStyle=label.background;
    ctx.globalAlpha=label.opacity;ctx.beginPath();ctx.roundRect(0,0,canvas.width,canvas.height,label.radius);ctx.fill();
    ctx.globalAlpha=1;ctx.fillStyle=label.color;
    lines.forEach((text,i)=>ctx.fillText(text,padding,padding+i*step));
    return canvas;
  }
  const api={key,raster};if(typeof module!=='undefined')module.exports=api;else root.StudioLabel=api;
})(typeof window!=='undefined'?window:this);
