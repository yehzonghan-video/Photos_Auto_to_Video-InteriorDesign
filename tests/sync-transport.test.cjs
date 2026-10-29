const assert=require('node:assert/strict');
const test=require('node:test');
const Transport=require('../frontend/sync-transport.js');

function clock(){
  const tasks=[];
  return {
    tasks,
    setTimer(fn,delay){const task={fn,delay,cleared:false};tasks.push(task);return task;},
    clearTimer(task){task.cleared=true;},
    fire(delay){for(const task of tasks.filter(item=>item.delay===delay&&!item.cleared))task.fn();}
  };
}

test('Cloud同步在15與45秒只重送相同交易，120秒才逾時',()=>{
  const timer=clock(),attempts=[],slow=[];let timedOut=0;
  Transport.watch({retry:value=>attempts.push(value),onSlow:value=>slow.push(value),onTimeout:()=>timedOut++,
    setTimer:timer.setTimer,clearTimer:timer.clearTimer});
  assert.deepEqual(timer.tasks.map(task=>task.delay),[15000,45000,120000]);
  timer.fire(15000);assert.deepEqual(attempts,[1]);assert.deepEqual(slow,[1]);assert.equal(timedOut,0);
  timer.fire(45000);assert.deepEqual(attempts,[1,2]);assert.deepEqual(slow,[1,2]);assert.equal(timedOut,0);
  timer.fire(120000);assert.equal(timedOut,1);
});

test('收到ACK後取消所有重送與逾時計時器',()=>{
  const timer=clock(),attempts=[];let timedOut=0;
  const watcher=Transport.watch({retry:value=>attempts.push(value),onTimeout:()=>timedOut++,
    setTimer:timer.setTimer,clearTimer:timer.clearTimer});
  watcher.cancel();timer.fire(15000);timer.fire(45000);timer.fire(120000);
  assert.deepEqual(attempts,[]);assert.equal(timedOut,0);assert.ok(timer.tasks.every(task=>task.cleared));
});
