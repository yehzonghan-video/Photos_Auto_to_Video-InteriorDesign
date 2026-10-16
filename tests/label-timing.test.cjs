const test=require('node:test'),assert=require('node:assert/strict');
const {delay}=require('../frontend/label-timing.js');
const {pose}=require('../frontend/animation.js');
test('標籤各自延後1秒一次，保留終點與後續人工時間',()=>{
  const l={start:.3,end:4,enter:.6};assert.equal(delay(l,4),true);assert.equal(l.start,1.3);assert.equal(l.end,4);
  assert.equal(pose(l,1),null);assert.ok(pose(l,2));l.start=.5;
  assert.equal(delay(l,4),false);assert.equal(l.start,.5);
  const title={start:0,end:2,enter:.3,comparison_side:'before'};assert.equal(delay(title,5),false);assert.equal(title.start,0);
});
test('短片段／接近結尾保留至少一影格，單影格直接顯示，無效草稿不被改寫',()=>{
  for(const [duration,start,end] of [[1,0,1],[4,3.8,4],[4,0,.01]]){
    const l={start,end,enter:.6};assert.equal(delay(l,duration),true);
    assert.ok(l.start>=0&&l.start<l.end&&l.end<=duration);assert.equal(l.enter,0);
    assert.equal(pose({...l,animation:'fade'},l.start).alpha,1);
  }
  const invalid={start:NaN,end:4};assert.equal(delay(invalid,4),false);assert.ok(Number.isNaN(invalid.start));
});
