const assert = require('node:assert/strict');
const test = require('node:test');
const {pose} = require('../frontend/animation.js');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
test('前端與 Python 七種動畫在邊界及中途相同', () => {
  const python = path.resolve('.venv/Scripts/python.exe');
  const cases = ['left','right','up','down','fade','scale','none'].flatMap(animation=>[-.1,0,.3,.6,1,3.999,4].map(time=>({label:{animation,start:0,enter:.6,end:4},time})));
  const code = 'import json,sys; from studio.animation import pose; print(json.dumps([pose(c["label"],c["time"]) for c in json.load(sys.stdin)]))';
  const expected = JSON.parse(execFileSync(python,['-c',code],{input:JSON.stringify(cases),encoding:'utf8'}));
  cases.forEach((c,i)=>{const actual=pose(c.label,c.time); if(!expected[i])assert.equal(actual,null);else for(const key of Object.keys(actual))assert.ok(Math.abs(actual[key]-expected[i][key])<1e-12,`${c.label.animation} ${c.time} ${key}`);});
});
