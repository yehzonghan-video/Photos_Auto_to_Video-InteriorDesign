const assert = require('node:assert/strict');
const test = require('node:test');
const {layout} = require('../frontend/photo-layout.js');
test('完整橫式照片包含原圖全部範圍，居中並留下上下黑邊', () => {
  assert.deepEqual(layout(300,100,90,160,{zoom:3,crop_x:1,crop_y:0}),
    {sx:0,sy:0,sw:300,sh:100,dx:0,dy:65,dw:90,dh:30});
});
test('細長直式照片保持完整並留下左右黑邊', () => {
  assert.deepEqual(layout(50,200,90,160,{fit:'contain'}),
    {sx:0,sy:0,sw:50,sh:200,dx:25,dy:0,dw:40,dh:160});
});
test('填滿畫面模式仍可選取原圖右側裁切區域', () => {
  const box=layout(300,100,90,160,{fit:'cover',zoom:1,crop_x:1,crop_y:.5});
  assert.equal(box.sx,243.75);assert.equal(box.sw,56.25);assert.equal(box.dw,90);assert.equal(box.dh,160);
});
