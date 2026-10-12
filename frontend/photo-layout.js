// 瀏覽器預覽與錄製共用照片佈局，與 Python 使用相同的等比例置中規則。
(function (root) {
  function layout(imageWidth, imageHeight, width, height, photo) {
    if ((photo.fit || 'contain') === 'contain') {
      const factor = Math.min(width / imageWidth, height / imageHeight);
      const dw = Math.max(1, Math.round(imageWidth * factor));
      const dh = Math.max(1, Math.round(imageHeight * factor));
      return {sx:0,sy:0,sw:imageWidth,sh:imageHeight,
        dx:Math.floor((width-dw)/2),dy:Math.floor((height-dh)/2),dw,dh};
    }
    const factor = Math.max(width / imageWidth, height / imageHeight) * photo.zoom;
    const sw = width / factor, sh = height / factor;
    return {sx:(imageWidth-sw)*photo.crop_x,sy:(imageHeight-sh)*photo.crop_y,
      sw,sh,dx:0,dy:0,dw:width,dh:height};
  }
  if (typeof module !== 'undefined') module.exports = {layout};
  else root.StudioPhoto = {layout};
})(typeof window !== 'undefined' ? window : this);
