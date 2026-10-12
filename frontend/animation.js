(function (root) {
  function pose(label, time) {
    if (time < label.start || time >= label.end) return null;
    const p = label.enter ? Math.min(1, (time - label.start) / label.enter) : 1;
    const ease = 1 - Math.pow(1 - p, 3), remaining = 1 - ease;
    let x = 0, y = 0, scale = 1, alpha = 1;
    if (label.animation === 'left') x = -.22 * remaining;
    if (label.animation === 'right') x = .22 * remaining;
    if (label.animation === 'up') y = -.16 * remaining;
    if (label.animation === 'down') y = .16 * remaining;
    if (label.animation === 'fade') alpha = ease;
    if (label.animation === 'scale') { scale = .65 + .35 * ease; alpha = ease; }
    if (!['none', 'fade', 'scale'].includes(label.animation)) alpha = ease;
    return {x, y, scale, alpha};
  }
  if (typeof module !== 'undefined') module.exports = {pose};
  else root.StudioAnimation = {pose};
})(typeof window !== 'undefined' ? window : this);
