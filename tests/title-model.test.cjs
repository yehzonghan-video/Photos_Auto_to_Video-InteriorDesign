const test=require('node:test'),assert=require('node:assert/strict');
const T=require('../frontend/title-model.js'),B=require('../frontend/body-editor.js');
const make=()=>({enabled:true,title:'18坪小宅超強收納',color:'#ffffff',font_size:120,highlights:[{start:5,end:9,color:'#ffd34e'}],body:B.newBody()});
test('明確欄位連結一次文字、不同排版，普通標籤不參與搜尋取代',()=>{
  const c=make(),prior=JSON.stringify(c.body);T.setText(c,'18坪小宅打造超強收納');
  assert.equal(c.title,c.body.title);assert.equal(c.shared_title.text,c.title);assert.equal(c.shared_title.cover_id,'project-cover-title');
  assert.equal(c.body.follow_cover,false);assert.equal(c.body.font_size,100);assert.equal(c.font_size,120);assert.equal(c.body.y,.245);
  assert.equal(T.validate(c),null);c.color='#ff0000';assert.equal(c.body.color,'#ffffff');
});
test('沒有明確關聯先拒絕，確認後只連結兩個固定元素且可採用正文文字',()=>{
  const c=make();c.body.follow_cover=false;c.body.title='正文獨立標題';c.body.color='#00aaff';const before=JSON.stringify(c);
  assert.throws(()=>T.setText(c,'新標題'),/確認/);assert.equal(JSON.stringify(c),before);
  T.ensure(c,'body',true);assert.equal(c.title,'正文獨立標題');assert.equal(c.body.color,'#00aaff');assert.equal(c.color,'#ffffff');
});
test('Unicode重點字唯一對應才保留，重複／消失不錯套，改換行仍保留原字',()=>{
  let r=T.remap('老屋超強收納','18坪😀超強收納',[{start:2,end:6,color:'#ffff00'}]);
  assert.deepEqual(r.ranges,[{start:4,end:8,color:'#ffff00'}]);assert.equal(r.dropped,0);
  r=T.remap('超強收納','超強收納與超強收納',[{start:0,end:4,color:'#ffff00'}]);assert.equal(r.dropped,1);assert.deepEqual(r.ranges,[]);
  assert.equal(T.remap('超強收納','全新標題',[{start:0,end:4,color:'#ffff00'}]).dropped,1);
  assert.deepEqual(T.remap('超強收納','超強\n收納',[{start:0,end:4,color:'#ffff00'}]).ranges,[{start:0,end:5,color:'#ffff00'}]);
});
test('封面及正文換行獨立，錯誤輸入不建立關聯、不修改動畫與時間',()=>{
  const c=make(),before=JSON.stringify(c);assert.throws(()=>T.setBreaks(c,'cover','改錯內容'),/換行/);assert.equal(JSON.stringify(c),before);
  T.ensure(c);const timing=[c.body.start,c.body.end,c.body.auto_timing];T.setBreaks(c,'cover','18坪小宅\n超強收納');
  assert.equal(c.body.title,'18坪小宅超強收納');assert.equal(c.title,'18坪小宅\n超強收納');assert.deepEqual([c.body.start,c.body.end,c.body.auto_timing],timing);
  T.setBreaks(c,'body','18坪\n小宅超強收納');assert.equal(T.validate(c),null);
  T.setText(c,'全新標題');assert.equal(c.title,c.body.title);assert.deepEqual(c.shared_title.cover_breaks,[]);
  const valid=JSON.stringify(c);assert.throws(()=>T.setDisplay(c,'cover','新\n標\n題\n測\n試\n過\n多'),/6行/);assert.equal(JSON.stringify(c),valid);
});
test('檔名不修改顯示標題，特殊字元、空白與保留名稱都有安全結果',()=>{
  for(const [input,expected] of [['18坪小宅？','18坪小宅'],['<|?*>','室內設計案例'],[' \n. ','室內設計案例'],['CON','案例_CON'],['案例/衛浴\n設計','案例衛浴設計']]){
    assert.equal(T.filename(input,'mp4'),expected+'.mp4');assert.equal(T.filename(input,'zip'),expected+'.zip');
  }
  assert.ok(Array.from(T.filename('😀'.repeat(100),'zip')).length<=64);
});
