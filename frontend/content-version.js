// 與Python共用資料欄位與IEEE754序列化。只雜湊設定及媒體摘要，不重讀圖片／音訊。
(function(root){
  const schema=typeof module!=='undefined'?require('./content-schema.json'):null;
  let spec=schema;
  const numbers=new Map(),strings=new Map(),numberBytes=new ArrayBuffer(8),numberView=new DataView(numberBytes);
  const encoder=typeof TextEncoder!=='undefined'?new TextEncoder():null;
  function configure(value){if(value)spec=value;}
  function canonical(value){
    if(value==null)return 'null';
    if(typeof value==='boolean')return String(value);
    if(typeof value==='number'){
      if(!Number.isFinite(value))return 'Ninvalid';
      if(numbers.has(value))return numbers.get(value);
      numberView.setFloat64(0,value||0,false);
      const result='N'+Array.from(new Uint8Array(numberBytes),b=>b.toString(16).padStart(2,'0')).join('');
      if(numbers.size>4096)numbers.clear();numbers.set(value,result);return result;
    }
    if(typeof value==='string'){
      if(strings.has(value))return strings.get(value);
      const result=JSON.stringify(value);if(strings.size>4096)strings.clear();strings.set(value,result);return result;
    }
    if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
    return '{'+Object.keys(value).sort().map(k=>canonical(k)+':'+canonical(value[k])).join(',')+'}';
  }
  function sha256(text){
    let encoded;
    if(encoder)encoded=encoder.encode(text);
    else {encoded=[];for(const char of text){const c=char.codePointAt(0);if(c<128)encoded.push(c);else if(c<2048)encoded.push(192|(c>>6),128|(c&63));
      else if(c<65536)encoded.push(224|(c>>12),128|((c>>6)&63),128|(c&63));else encoded.push(240|(c>>18),128|((c>>12)&63),128|((c>>6)&63),128|(c&63));}}
    const length=encoded.length*8,bytes=new Uint8Array(Math.ceil((encoded.length+9)/64)*64);
    bytes.set(encoded);bytes[encoded.length]=128;
    for(let i=0;i<4;i++)bytes[bytes.length-1-i]=Math.floor(length/2**(i*8))&255;
    const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    const r=(v,n)=>(v>>>n)|(v<<(32-n)),w=new Array(64);
    for(let offset=0;offset<bytes.length;offset+=64){
      for(let i=0;i<16;i++)w[i]=(bytes[offset+4*i]<<24)|(bytes[offset+4*i+1]<<16)|(bytes[offset+4*i+2]<<8)|bytes[offset+4*i+3];
      for(let i=16;i<64;i++)w[i]=(w[i-16]+(r(w[i-15],7)^r(w[i-15],18)^(w[i-15]>>>3))+w[i-7]+(r(w[i-2],17)^r(w[i-2],19)^(w[i-2]>>>10)))|0;
      let [a,b,c,d,e,f,g,z]=h;
      for(let i=0;i<64;i++){const t=(z+(r(e,6)^r(e,11)^r(e,25))+((e&f)^(~e&g))+k[i]+w[i])|0;
        const u=((r(a,2)^r(a,13)^r(a,22))+((a&b)^(a&c)^(b&c)))|0;z=g;g=f;f=e;e=(d+t)|0;d=c;c=b;b=a;a=(t+u)|0;}
      [a,b,c,d,e,f,g,z].forEach((v,i)=>h[i]=(h[i]+v)|0);
    }
    return h.map(v=>(v>>>0).toString(16).padStart(8,'0')).join('');
  }
  const digest=v=>'cv1-'+sha256(canonical(v));
  function normalize(raw,name){raw=raw||{};const result=Object.fromEntries(Object.entries(spec[name]).map(([k,v])=>[k,raw[k]===undefined?v:raw[k]]));
    for(const key of ['color','background'])if(typeof result[key]==='string')result[key]=result[key].toLowerCase();return result;}
  function labels(rows){return (rows||[]).map(raw=>{const l=normalize(raw,'label');if(typeof l.text==='string')l.text=l.text.trim();
    if(raw.source==='gemini')Object.assign(l,normalize(raw,'gemini'));
    if(['before','after'].includes(raw.comparison_side))Object.assign(l,normalize(raw,'comparison_label'));
    if(typeof raw.origin_label_id==='string')l.origin_label_id=raw.origin_label_id;return l;});}
  function document(data,context){
    const photos=(data.photos||[]).map(row=>({...normalize(row,'photo'),labels:labels(row.labels),content_hash:context.photos?.[row.id]||'unknown'}));
    const comparisons=(data.comparisons||[]).map(row=>({...normalize(row,'clip'),name:(row.name??'裝修前後對比').trim(),
      before_crop:normalize(row.before_crop,'crop'),after_crop:normalize(row.after_crop,'crop'),labels:labels(row.labels)}));
    const raw=data.cover,cover=normalize(raw,'cover');cover.highlights=(raw?.highlights||[]).map(r=>({...r,color:r.color.toLowerCase()}));
    if(!photos.some(p=>p.id===cover.photo_id))cover.photo_id=photos.find(p=>p.role==='after')?.id||photos[0]?.id||'';
    cover.body=normalize(raw?.body,'body');if(raw==null)Object.assign(cover.body,{enabled:false,logo_enabled:false});
    cover.body.highlights=(raw?.body?.highlights||[]).map(r=>({...r,color:r.color.toLowerCase()}));
    if(raw?.shared_title)cover.shared_title=Object.fromEntries(['version','cover_id','body_id','text','cover_x','cover_y','cover_breaks','body_breaks'].map(k=>[k,raw.shared_title[k]]));
    const names=new Map((context.assets||[]).map(a=>[a.id,a.name]));
    const overlays=rows=>(rows||[]).map(o=>({...normalize(o,'overlay'),name:names.get(o.source)??o.name??''}));
    const result={schema:'interior-content-v1',photos,comparisons,cover,overlays:overlays(data.overlays),
      comparison_overlays:overlays(data.comparison_overlays),music:normalize(data.music,'music'),
      template_id:data.template_id||'items',assets:[...(context.assets||[])].sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0),
      music_asset:context.music||null,video:{width:context.width??1080,fps:30},engine:context.engine||'unknown'};
    const tour=data.tour||{};
    if(data.template_id==='tour'||tour.rooms?.length||tour.clips?.length||context.floor_plan||context.videos?.length)
      result.tour={...normalize(tour,'tour'),rooms:(tour.rooms||[]).map(r=>({...normalize(r,'room'),name:(r.name||'').trim()})),clips:(tour.clips||[]).map(c=>({...normalize(c,'tour_clip'),crop:normalize(c.crop,'crop'),labels:labels(c.labels)})),overlays:overlays(tour.overlays),plan:context.floor_plan||null,videos:context.videos||[],layout:context.tour_layout||null};
    return result;
  }
  function version(draft,context){return digest(document({photos:draft.rows,comparisons:draft.comparisons,overlays:draft.overlays,
    comparison_overlays:draft.comparisonOverlays,cover:draft.cover,music:draft.music,tour:draft.tour,template_id:draft.template},context));}
  const api={configure,canonical,sha256,digest,document,version};
  if(typeof module!=='undefined')module.exports=api;else root.StudioVersion=api;
})(typeof window!=='undefined'?window:this);
