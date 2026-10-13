// 安全框資料與 Python 共用 JSON；提示用 DOM SVG，永遠不畫進影片 Canvas。
(function(root){
  let config=typeof module!=='undefined'?require('./safe-area.json'):null;
  function configure(value){if(value)config=value;}
  function titlePosition(){return {x:config.inner.left/config.width,y:config.inner.top/config.height};}
  function mount(element){if(!config)return;
    const boxes=[config.outer,config.frame].map(b=>{
      const half=b.stroke/2;
      return `<rect x="${b.left+half}" y="${b.top+half}" width="${b.right-b.left-b.stroke}" height="${b.bottom-b.top-b.stroke}" stroke-width="${b.stroke}"/>`;
    }).join('');
    element.innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${config.width} ${config.height}" aria-hidden="true"><g fill="none" stroke="white" stroke-opacity=".8">${boxes}</g></svg>`;
  }
  const api={configure,titlePosition,mount};
  if(typeof module!=='undefined')module.exports=api;else root.StudioSafeArea=api;
})(typeof window!=='undefined'?window:this);
