// 共用標題僅連結專案已定義的兩個元素，不搜尋／取代一般文字標籤。
(function(root){
  const clone=v=>JSON.parse(JSON.stringify(v)),chars=s=>Array.from(s),plain=s=>s.replace(/[\r\n]/g,''),Y=659/1920;
  const ids={cover:'project-cover-title',body:'project-body-title'};
  function breaks(text){let n=0;const result=[];for(const c of chars(text))if(c==='\n'){if(n&&!result.includes(n))result.push(n);}else if(c!=='\r')n++;return result.filter(i=>i<n);}
  function display(text,points){const set=new Set(points);return chars(text).map((c,i)=>(set.has(i)?'\n':'')+c).join('');}
  const title=c=>c?.shared_title?.text??plain(c?.title||'');
  function remap(oldText,newText,ranges){
    const old=chars(oldText),next=chars(newText),a=old.filter(c=>c!=='\n'&&c!=='\r'),b=next.filter(c=>c!=='\n'&&c!=='\r');let dropped=0;
    const map=[];next.forEach((c,i)=>{if(c!=='\n'&&c!=='\r')map.push(i);});
    const kept=[];
    for(const r of ranges||[]){const word=old.slice(r.start,r.end).filter(c=>c!=='\n'&&c!=='\r');let start;
      if(a.join('')===b.join(''))start=old.slice(0,r.start).filter(c=>c!=='\n'&&c!=='\r').length;
      else{const found=[];for(let i=0;i<=b.length-word.length;i++)if(word.length&&b.slice(i,i+word.length).join('')===word.join(''))found.push(i);if(found.length===1)start=found[0];}
      if(start===undefined||!word.length||map[start+word.length-1]===undefined){dropped++;continue;}
      kept.push({start:map[start],end:map[start+word.length-1]+1,color:r.color});
    }
    return {ranges:kept,dropped};
  }
  function assign(style,text){const mapped=remap(style.title,text,style.highlights);style.title=text;style.highlights=mapped.ranges;return mapped.dropped;}
  function ensure(c,source='cover',confirmed=false){
    if(c.shared_title)return 0;
    if(!c.body?.follow_cover&&!confirmed)throw new Error('封面與正文未明確連動，請先確認標題元素與採用文字。');
    if(c.body.follow_cover){c.body.title=c.title;c.body.color=c.color;c.body.highlights=clone(c.highlights);}
    const text=plain(source==='body'?c.body.title:c.title),coverBreaks=plain(c.title)===text?breaks(c.title):[],bodyBreaks=plain(c.body.title)===text?breaks(c.body.title):[];
    c.shared_title={version:1,cover_id:ids.cover,body_id:ids.body,text,cover_x:.5,cover_y:Y,cover_breaks:coverBreaks,body_breaks:bodyBreaks};
    c.body.follow_cover=false;return assign(c,display(text,coverBreaks))+assign(c.body,display(text,bodyBreaks));
  }
  function setText(c,text){text=plain(text);if(title(c)===text)return {changed:false,dropped:0};
    let dropped=ensure(c);c.shared_title.text=text;c.shared_title.cover_breaks=[];c.shared_title.body_breaks=[];
    dropped+=assign(c,text)+assign(c.body,text);return {changed:true,dropped};
  }
  function setBreaks(c,side,text){if(plain(text)!==title(c))throw new Error('此處只調換行；文字內容請在上方「影片標題」修改。');
    const points=breaks(text);if(points.length>5)throw new Error('標題最多6行。');ensure(c);
    const target=side==='cover'?c:c.body,rendered=display(title(c),points);c.shared_title[side+'_breaks']=points;return assign(target,rendered);}
  function setDisplay(c,side,text){if(breaks(text).length>5)throw new Error('標題最多6行。');const result=setText(c,plain(text));return {changed:true,dropped:result.dropped+setBreaks(c,side,text)};}
  function coverBox(c){const t=c.shared_title;return {x:Math.round((t?.cover_x??.5)*1080-294),y:Math.round((t?.cover_y??Y)*1920-146),width:588,height:292};}
  function validate(c){const t=c?.shared_title;if(!t)return null;
    if(t.version!==1||t.cover_id!==ids.cover||t.body_id!==ids.body||typeof t.text!=='string'||chars(t.text).length>80||/[\r\n]/.test(t.text)||c.body.follow_cover)return '共用標題關聯不正確。';
    for(const side of ['cover','body']){const b=t[side+'_breaks'];if(!Array.isArray(b)||b.length>5||b.some((i,n)=>!Number.isInteger(i)||i<=0||i>=chars(t.text).length||(n&&i<=b[n-1]))||display(t.text,b)!==(side==='cover'?c:c.body).title)return '封面與正文的文字／換行不一致，請重新確認。';}
    if(['cover_x','cover_y'].some(k=>!Number.isFinite(t[k])||t[k]<0||t[k]>1))return '封面位置需為0～100%。';return null;}
  function normalized(t){return Object.fromEntries(['version','cover_id','body_id','text','cover_x','cover_y','cover_breaks','body_breaks'].map(k=>[k,t[k]]));}
  function filename(text,ext){let clean=String(text).replace(/[<>:"/\\|?*\x00-\x1f\x7f？]/g,'').replace(/\s+/g,' ').replace(/^[ .]+|[ .]+$/g,'');clean=chars(clean).slice(0,60).join('').replace(/[ .]+$/g,'')||'室內設計案例';if(/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(clean))clean='案例_'+clean;return clean+'.'+ext;}
  const api={ids,title,plain,breaks,display,remap,ensure,setText,setBreaks,setDisplay,coverBox,validate,normalized,filename};
  if(typeof module!=='undefined')module.exports=api;else root.StudioTitle=api;
})(typeof window!=='undefined'?window:this);
