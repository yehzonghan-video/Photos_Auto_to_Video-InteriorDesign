// 只讀既有AI標籤與來源分類；沒有API、影像編碼或正式草稿寫入。
(function(root){
  const rooms=[['客廳','起居室'],['廚房','廚區'],['臥室','主臥','次臥'],['浴室','衛浴','廁所'],['餐廳','用餐區'],['陽台'],['玄關'],['書房']];
  const features=['落地窗','拱門','樑柱','橫梁','樓梯','中島','走道','轉角窗','斜屋頂','雙面窗','電視牆','開放式'];
  function evidence(p){
    const ai=(p.labels||[]).filter(l=>l.source==='gemini'),text=[p.name,...ai.flatMap(l=>[l.text,l.description,l.category])].join(' ');
    const found=rooms.map((words,i)=>words.some(w=>text.includes(w))?i:null).filter(i=>i!==null);
    const role=['before','after'].includes(p.role)?p.role:/施工前|裝修前|改造前|before/i.test(p.name||'')?'before':/施工後|裝修後|改造後|after/i.test(p.name||'')?'after':null;
    const stem=(p.name||'').replace(/\.[^.]+$/,'').replace(/施工[前後]|裝修[前後]|改造[前後]|before|after/gi,'').replace(/[\s_\-()（）]/g,'');
    return {role,room:found.length===1?found[0]:null,features:features.filter(f=>text.includes(f)),stem,ai:ai.length>0};
  }
  const key=(b,a)=>JSON.stringify([b,a]);
  function conflicts(b,a,clips){return clips.filter(c=>[c.before_id,c.after_id].some(id=>id===b||id===a));}
  function suggest(photos,clips){
    const result=[],data=new Map(photos.map(p=>[p.id,evidence(p)]));
    for(const b of photos)for(const a of photos){const x=data.get(b.id),y=data.get(a.id);
      if(b.id===a.id||x.role!=='before'||y.role!=='after'||clips.some(c=>c.before_id===b.id&&c.after_id===a.id))continue;
      if(x.room!==null&&y.room!==null&&x.room!==y.room)continue;
      const sameRoom=x.room!==null&&x.room===y.room,shared=x.features.filter(f=>y.features.includes(f));
      const named=x.stem.length>=3&&x.stem===y.stem&&(sameRoom||/[0-9]{2}|[a-z]{3}/i.test(x.stem));
      if(!(sameRoom&&shared.length>=1)&&!named)continue;
      const reason=[sameRoom?`兩張都提及${rooms[x.room][0]}`:'檔名有相同案例識別',shared.length?`共同特徵：${shared.join('、')}`:'',named?'去除前後字樣後檔名相同':'', '前後依來源分類／檔名字樣，仍需核對拍攝角度'].filter(Boolean).join('；');
      result.push({id:key(b.id,a.id),before_id:b.id,after_id:a.id,reason,confidence:sameRoom&&named&&shared.length?'中':'低',conflict:conflicts(b.id,a.id,clips).length>0});
    }
    // 多角度可能同時合理，不替使用者挑唯一答案，也不報假百分比。
    return result.sort((a,b)=>Number(b.confidence==='中')-Number(a.confidence==='中')||a.id.localeCompare(b.id)).slice(0,12);
  }
  const api={evidence,key,conflicts,suggest};if(typeof module!=='undefined')module.exports=api;else root.StudioPairing=api;
})(typeof window!=='undefined'?window:this);
