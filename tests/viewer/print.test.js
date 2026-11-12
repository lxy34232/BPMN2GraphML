const test = require("node:test");
const assert = require("node:assert/strict");
const { DOMParser, XMLSerializer } = require("@xmldom/xmldom");
global.DOMParser = DOMParser;
global.XMLSerializer = XMLSerializer;
const P = require("../../bpmn2graphml/viewer/print.js");

test("automatically chooses orientation and fits the entire diagram within one page", () => {
  for (const paper of ["A4", "A3"]) {
    for (const [width, height] of [[8000, 300], [300, 8000], [100, 100]]) {
      const layout = P.pageLayout(width, height, paper, "auto");
      assert.equal(layout.orientation, width > height ? "landscape" : "portrait");
      assert.ok(layout.imageWidth <= layout.width - 20);
      assert.ok(layout.imageHeight <= layout.height - 20);
      assert.ok(Math.abs(layout.imageWidth / layout.imageHeight - width / height) < 1e-10);
    }
  }
});

test("honors explicit page choices and rejects empty or invalid dimensions", () => {
  assert.deepEqual(P.pageLayout(800, 100, "A3", "portrait"), {
    paper: "A3", orientation: "portrait", width: 297, height: 420,
    imageWidth: 276, imageHeight: 34.5
  });
  assert.equal(P.pageLayout(10, 100, "A4", "landscape").width, 297);
  for (const size of [0, -1, NaN, Infinity]) {
    assert.throws(() => P.pageLayout(size, 100), /尺寸无效/);
    assert.throws(() => P.pageLayout(100, size), /尺寸无效/);
  }
});

test("preserves SVG text, edges and markers, adds padding and standalone highlight styles", () => {
  const image = P.prepareSVG('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 30 800 400">' +
    '<defs><marker id="arrow"/></defs><g class="djs-element b2g-hl"><text>审批 &amp; 发布</text></g>' +
    '<path marker-end="url(#arrow)" d="M0,0 L100,100"/></svg>');
  assert.equal(image.width, 816);
  assert.equal(image.height, 416);
  const doc = new DOMParser().parseFromString(image.svg, "image/svg+xml");
  assert.equal(doc.documentElement.getAttribute("viewBox"), "-28 22 816 416");
  assert.equal(doc.getElementsByTagName("text")[0].textContent, "审批 & 发布");
  assert.equal(doc.getElementsByTagName("path")[0].getAttribute("marker-end"), "url(#arrow)");
  assert.match(doc.getElementsByTagName("style")[0].textContent, /b2g-hl.*#d97706/);
  assert.match(image.svg, /b2g-dim/);
});

test("rejects non-SVG and empty diagrams before generating a print page", () => {
  for (const svg of ['<html/>', '<svg xmlns="http://www.w3.org/2000/svg"/>',
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 20"/>',
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 NaN 20"/>']) {
    assert.throws(() => P.prepareSVG(svg), /无法生成|为空/);
  }
});

test("excludes the temporary connection selection while retaining filter markers", () => {
  const image = P.prepareSVG('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">' +
    '<g class="djs-element djs-connection b2g-dim b2g-edge-selected"><path d="M0 0 H200"/></g>' +
    '<g class="djs-element b2g-hl b2g-edge-selected"><text>连线文字</text></g></svg>');
  assert.ok(!image.svg.includes("b2g-edge-selected"));
  const doc = new DOMParser().parseFromString(image.svg, "image/svg+xml");
  assert.match(doc.getElementsByTagName("g")[0].getAttribute("class"), /b2g-dim/);
  assert.match(doc.getElementsByTagName("g")[1].getAttribute("class"), /b2g-hl/);
  assert.equal(doc.getElementsByTagName("text")[0].textContent, "连线文字");
});

test("excludes interactive lane controls while preserving lane titles and backgrounds", () => {
  const image = P.prepareSVG('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 500">' +
    '<g class="b2g-lane"><rect width="240" height="500"/><text>来源流程</text>' +
    '<g class="b2g-lane-controls"><g role="button"><rect width="24" height="26"/><text>▶</text></g></g></g></svg>');
  const doc = new DOMParser().parseFromString(image.svg, "image/svg+xml");
  assert.equal(doc.getElementsByTagName("rect").length, 1);
  assert.equal(doc.getElementsByTagName("text")[0].textContent, "来源流程");
  assert.ok(!image.svg.includes("b2g-lane-controls"));
  assert.ok(!image.svg.includes('role="button"'));
});

test("print document safely embeds names and SVG as an inert image without remote assets", () => {
  const image = { svg: '<svg><text>中文</text><script>alert(1)</script></svg>', width: 800, height: 400 };
  const { html, layout } = P.buildDocument(image, '审批</title><script>bad()</script>.bpmn', {
    paper: "A3", orientation: "landscape"
  });
  assert.equal(layout.paper, "A3");
  assert.match(html, /@page \{size:A3 landscape;margin:10mm\}/);
  assert.match(html, /<title>审批&lt;\/title&gt;&lt;script&gt;bad\(\)&lt;\/script&gt;<\/title>/);
  assert.ok(!html.includes("<script>"));
  assert.ok(!html.includes("http://") && !html.includes("https://"));
  const src = html.match(/src="([^"]+)"/)[1];
  assert.equal(decodeURIComponent(src.split(",")[1]), image.svg);
  assert.equal(P.buildDocument(image, "流程.XML").html.match(/<title>(.*?)<\/title>/)[1], "流程");
});
