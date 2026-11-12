/* 处理 bpmn-js 的完整 SVG，生成离线打印页或 PNG；SVG 作为图片加载。 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.B2GPrint = factory();
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var PRINT_STYLE =
    ".djs-element.b2g-hl .djs-visual > :first-child {" +
    "stroke:#d97706!important;stroke-width:3px!important;fill:#fef3c7!important}" +
    ".djs-element.b2g-dim {opacity:.22}";

  function escapeHTML(text) {
    return String(text).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function pageLayout(width, height, paper, orientation) {
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      throw new Error("流程图的尺寸无效，无法打印。");
    }
    paper = paper === "A3" ? "A3" : "A4";
    if (orientation !== "portrait" && orientation !== "landscape") {
      orientation = width > height ? "landscape" : "portrait";
    }
    var shortSide = paper === "A3" ? 297 : 210;
    var longSide = paper === "A3" ? 420 : 297;
    var pageWidth = orientation === "landscape" ? longSide : shortSide;
    var pageHeight = orientation === "landscape" ? shortSide : longSide;
    // 四周各留 10mm；再留 1mm 防止浏览器舍入后溢出到第二页。
    var scale = Math.min((pageWidth - 21) / width, (pageHeight - 21) / height);
    return {
      paper: paper, orientation: orientation, width: pageWidth, height: pageHeight,
      imageWidth: width * scale, imageHeight: height * scale
    };
  }

  function prepareSVG(text) {
    var doc = new DOMParser().parseFromString(text, "image/svg+xml");
    var svg = doc.documentElement;
    if (doc.getElementsByTagName("parsererror").length || !svg ||
        svg.localName !== "svg" || svg.namespaceURI !== SVG_NS) {
      throw new Error("无法生成流程图的 SVG 图像。");
    }
    // 界面选中态不属于流程内容，导出时去掉，仅保留分类筛选效果。
    Array.from(svg.getElementsByTagName("g")).forEach(function (element) {
      var classes = (element.getAttribute("class") || "").split(/\s+/);
      if (classes.indexOf("b2g-lane-controls") >= 0 && element.parentNode) {
        element.parentNode.removeChild(element);
        return;
      }
      if (classes.indexOf("b2g-edge-selected") >= 0) {
        element.setAttribute("class", classes.filter(function (name) { return name !== "b2g-edge-selected"; }).join(" "));
      }
    });
    var box = (svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
    if (box.length !== 4 || !box.every(Number.isFinite) || box[2] <= 0 || box[3] <= 0) {
      throw new Error("流程图为空或没有有效的图形尺寸。");
    }
    // bpmn-js 的包围盒紧贴图形，留出描边空间，避免边缘粗线被裁剪。
    var padding = 8;
    var width = box[2] + padding * 2, height = box[3] + padding * 2;
    svg.setAttribute("viewBox", [box[0] - padding, box[1] - padding, width, height].join(" "));
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    var style = doc.createElementNS(SVG_NS, "style");
    style.textContent = PRINT_STYLE;
    svg.appendChild(style);
    return { svg: new XMLSerializer().serializeToString(svg), width: width, height: height };
  }

  function buildDocument(image, name, options) {
    options = options || {};
    var layout = pageLayout(image.width, image.height, options.paper, options.orientation);
    var title = String(name || "BPMN").replace(/\.(bpmn|xml)$/i, "") || "BPMN";
    var html = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">' +
      '<title>' + escapeHTML(title) + '</title><style>' +
      '@page {size:' + layout.paper + ' ' + layout.orientation + ';margin:10mm}' +
      '*{box-sizing:border-box}html,body{margin:0;padding:0;background:white}' +
      'body,.sheet{display:flex;justify-content:center;align-items:center}' +
      'body{print-color-adjust:exact;-webkit-print-color-adjust:exact}' +
      'img{display:block;object-fit:contain}' +
      '@media screen{body{min-height:100vh;background:#eef0f3}' +
      '.sheet{background:white;box-shadow:0 1px 6px #bbc1c9;width:min(94vw,' +
      (94 * layout.width / layout.height) + 'vh);height:min(' +
      (94 * layout.height / layout.width) + 'vw,94vh)}' +
      'img{width:' + ((layout.width - 20) / layout.width * 100) + '%;height:' +
      ((layout.height - 20) / layout.height * 100) + '%}}' +
      '@media print{body{min-height:0;width:' + (layout.width - 20) + 'mm;height:' +
      (layout.height - 21) + 'mm}.sheet{width:100%;height:100%}img{width:' + layout.imageWidth + 'mm;height:' +
      layout.imageHeight + 'mm;max-width:100%;max-height:100%;break-inside:avoid}}' +
      '</style></head><body><main class="sheet"><img id="diagram" alt="完整 BPMN 流程图" src="data:image/svg+xml;charset=utf-8,' +
      escapeHTML(encodeURIComponent(image.svg)) + '"></main></body></html>';
    return { html: html, layout: layout };
  }

  function toPNG(image) {
    // 优先 2 倍分辨率；为长图控制画布边长和内存占用，但不缩到原始尺寸以下。
    var scale = Math.min(2, 32767 / image.width, 32767 / image.height,
      Math.sqrt(32 * 1024 * 1024 / (image.width * image.height)));
    if (!Number.isFinite(scale) || scale < 1) {
      return Promise.reject(new Error("流程图过大，无法按原始分辨率导出完整 PNG。请导出 SVG，可无损放大查看。"));
    }
    var width = Math.floor(image.width * scale), height = Math.floor(image.height * scale);
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(new Blob([image.svg], { type: "image/svg+xml;charset=utf-8" }));
      var img = new Image();
      var surface = null;
      function cleanup() {
        URL.revokeObjectURL(url);
        if (surface) { surface.width = 0; surface.height = 0; }
      }
      img.onerror = function () {
        cleanup();
        reject(new Error("无法读取流程图图像，请重试或导出 SVG。"));
      };
      img.onload = function () {
        try {
          surface = document.createElement("canvas");
          surface.width = width;
          surface.height = height;
          var context = surface.getContext("2d");
          if (!context) throw new Error("无法创建 PNG 画布，请导出 SVG。");
          context.fillStyle = "#ffffff";
          context.fillRect(0, 0, width, height);
          context.drawImage(img, 0, 0, width, height);
          surface.toBlob(function (blob) {
            cleanup();
            if (blob) resolve({ blob: blob, width: width, height: height });
            else reject(new Error("PNG 生成失败，流程图可能超出浏览器支持的图片尺寸，请导出 SVG。"));
          }, "image/png");
        } catch (err) { cleanup(); reject(err); }
      };
      img.src = url;
    });
  }

  return { pageLayout: pageLayout, prepareSVG: prepareSVG, buildDocument: buildDocument, toPNG: toPNG };
});
