const test=require('node:test'),assert=require('node:assert/strict'),{spawnSync}=require('node:child_process'),fs=require('node:fs');
const {geometry}=require('../frontend/overlay-model.js'),{overlayPose}=require('../frontend/animation.js');
test('PNG 尺寸、旋轉邊界及七種進出場動畫與Python一致',()=>{
  const cases=[];
  for(const animation of ['none','left','right','up','down','fade','scale'])for(const rotation of [-180,-43,0,27,90]){
    const item={start:.2,duration:1.6,enter:.4,exit:.4,animation,exit_animation:animation,width:.3,scale:4.8,x:.01,y:.99,rotation};
    cases.push({item,asset:{width:100,height:300},times:[0,.2,.3,.6,1,1.5,1.79,1.8]});
  }
  const python=fs.existsSync('.venv/Scripts/python.exe')?'.venv/Scripts/python.exe':'python';
  const script="import json,sys; from types import SimpleNamespace; from studio.overlays import geometry; from studio.animation import overlay_pose; rows=json.load(sys.stdin); print(json.dumps([dict(g=geometry(r['item'],SimpleNamespace(**r['asset'])),poses=[overlay_pose(r['item'],t) for t in r['times']]) for r in rows]))";
  const result=spawnSync(python,['-c',script],{input:JSON.stringify(cases),encoding:'utf8'});assert.equal(result.status,0,result.stderr);
  const expected=JSON.parse(result.stdout);
  for(let i=0;i<cases.length;i++){
    const c=cases[i],g=geometry(c.item,c.asset);
    for(const key of Object.keys(g))assert.ok(Math.abs(g[key]-expected[i].g[key])<1e-8,key);
    c.times.forEach((t,j)=>{const actual=overlayPose(c.item,t),e=expected[i].poses[j];
      if(!e)assert.equal(actual,null);else for(const key of Object.keys(e))assert.ok(Math.abs(e[key]-actual[key])<1e-8,`${key} ${t}`);});
  }
});
