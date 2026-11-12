/* BPMN 属性查看器：打开文件、驱动 bpmn-js、筛选高亮、详情卡与连线文本复制。 */
(function () {
  "use strict";

  var P = window.B2GProps;
  var NO_DI_MESSAGE = "该文件没有图形布局信息（BPMNDI），无法显示流程图；" +
    "可先经 yEd 布局并用本工具转回 BPMN 后再查看。";
  var SVG_NS = "http://www.w3.org/2000/svg";
  var PALETTE = [
    { stroke: "#d97706", fill: "#fef3c7" },
    { stroke: "#2563eb", fill: "#dbeafe" },
    { stroke: "#15803d", fill: "#dcfce7" },
    { stroke: "#7c3aed", fill: "#ede9fe" },
    { stroke: "#be185d", fill: "#fce7f3" },
    { stroke: "#0e7490", fill: "#cffafe" },
    { stroke: "#dc2626", fill: "#fee2e2" },
    { stroke: "#854d0e", fill: "#fef9c3" },
    { stroke: "#0f766e", fill: "#ccfbf1" },
    { stroke: "#475569", fill: "#e2e8f0" }
  ];

  var $ = function (id) { return document.getElementById(id); };
  var ui = {
    fileInput: $("file-input"), fileName: $("file-name"), attrSelect: $("attr-select"),
    chips: $("chips"), clearBtn: $("clear-btn"), fitBtn: $("fit-btn"), stage: $("stage"),
    message: $("message"), card: $("card"), dropHint: $("drop-hint"),
    printBtn: $("print-btn"), printDialog: $("print-dialog"), printClose: $("print-close"),
    printPaper: $("print-paper"), printOrientation: $("print-orientation"),
    printStatus: $("print-status"), printPreview: $("print-preview"), printConfirm: $("print-confirm"),
    exportSvgBtn: $("export-svg-btn"), exportPngBtn: $("export-png-btn"), exportStatus: $("export-status"),
    canvas: $("canvas"), scrollX: $("scroll-x"), scrollY: $("scroll-y"),
    scrollXSize: $("scroll-x-size"), scrollYSize: $("scroll-y-size"),
    laneAttr: $("lane-attr"), laneReset: $("lane-reset"), laneHeader: $("lane-header"), themeBtn: $("theme-btn")
  };

  function setTheme(theme) {
    var dark = theme === "dark";
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    ui.themeBtn.textContent = dark ? "浅色模式" : "深色模式";
    ui.themeBtn.title = dark ? "切换到浅色模式" : "切换到深色模式";
    ui.themeBtn.setAttribute("aria-label", ui.themeBtn.title);
    ui.themeBtn.setAttribute("aria-pressed", String(dark));
    try { window.localStorage.setItem("b2g-viewer-theme", dark ? "dark" : "light"); } catch (err) { /* 离线/隐私模式下仍可切换 */ }
  }
  var savedTheme = "light";
  try { savedTheme = window.localStorage.getItem("b2g-viewer-theme") || "light"; } catch (err) { /* 使用默认浅色 */ }
  setTheme(savedTheme);
  ui.themeBtn.addEventListener("click", function () {
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });

  // CSS 变量即时更新默认图形颜色；独立导出时使用浅色回退值。
  var viewer = new window.BpmnJS({ container: "#canvas", bpmnRenderer: {
    defaultFillColor: "var(--diagram-node-fill, #ffffff)",
    defaultStrokeColor: "var(--diagram-stroke, #1f2933)",
    defaultLabelColor: "var(--diagram-label, #1f2933)"
  } });
  var canvas = viewer.get("canvas");
  var registry = viewer.get("elementRegistry");
  var laneView = window.B2GLanes.create(viewer, moveLane, ui.laneHeader);
  var laneOrders = new Map();
  var activeLaneAttr = "";
  var activeLanes = [];

  var state = { nodes: [], byId: {}, attr: null, entries: [], selected: [], loaded: false };
  var loadSeq = 0;   // 每次打开文件递增；较早的、尚未完成的加载结果一律丢弃
  var importQueue = Promise.resolve();
  var printSeq = 0;
  var printImage = null;
  var printName = "";
  var exportSeq = 0;
  var exporting = false;
  var highlightedVisuals = [];
  var highlightGradients = [];
  var scrollFrame = 0;
  var scrollRange = null;
  var syncedScrollX = 0, syncedScrollY = 0;
  var selectedEdgeIds = [];
  window.b2gViewer = { viewer: viewer, state: state };   // 便于调试与端到端测试

  // 解析完成、渲染之前补上排他网关的 X 标记（见 properties.js 中 showGatewayMarkers）
  viewer.on("import.parse.complete", function (event) {
    if (event.definitions) P.showGatewayMarkers(event.definitions);
  });

  function showMessage(text, isError) {
    ui.message.textContent = text;
    ui.message.classList.toggle("error", !!isError);
    ui.message.hidden = false;
  }

  function setControlsEnabled(on) {
    ui.attrSelect.disabled = !on;
    ui.clearBtn.disabled = !on;
    ui.fitBtn.disabled = !on;
    ui.printBtn.disabled = !on;
    ui.exportSvgBtn.disabled = !on || exporting;
    ui.exportPngBtn.disabled = !on || exporting;
    ui.laneAttr.disabled = !on;
    ui.laneReset.disabled = !on || !ui.laneAttr.value;
  }

  function resetView() {
    closePrint();
    clearHighlightStyles();
    clearEdgeSelection();
    laneView.reset();
    laneOrders.clear();
    activeLaneAttr = "";
    ui.laneAttr.innerHTML = '<option value="">原始布局</option>';
    activeLanes = [];
    ui.stage.classList.remove("has-lanes");
    canvas.resized();
    scrollRange = null;
    ++exportSeq;
    exporting = false;
    ui.exportStatus.hidden = true;
    state.nodes = [];
    state.byId = {};
    state.attr = null;
    state.entries = [];
    state.selected = [];
    state.loaded = false;
    ui.attrSelect.innerHTML = "";
    ui.chips.innerHTML = "";
    hideCard();
    setControlsEnabled(false);
    scheduleScrollbars();
  }

  function openText(name, text) {
    var token = ++loadSeq;
    resetView();
    ui.fileName.textContent = name;
    ui.fileName.title = name;
    var doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.getElementsByTagName("parsererror").length || !doc.documentElement) {
      showMessage("无法解析「" + name + "」：不是有效的 XML 文件。", true);
      return clearCanvas(token);
    }
    if (!P.hasDiagram(doc)) {
      showMessage("「" + name + "」：" + NO_DI_MESSAGE, true);
      return clearCanvas(token);
    }
    // 导入排队依次进行：较早发起、尚未开始的导入直接跳过，保证画布与面板始终对应最后打开的文件
    importQueue = importQueue.then(function () {
      if (token !== loadSeq) return;
      return viewer.importXML(text).then(function () { onImported(token, doc); });
    }).catch(function (err) {
      if (token !== loadSeq) return;
      viewer.clear();
      showMessage("无法显示「" + name + "」：" + (err && err.message ? err.message : err), true);
    });
    return importQueue;
  }

  function clearCanvas(token) {
    // 排在进行中的导入之后再清空，避免旧文件稍后画到画布上
    importQueue = importQueue.then(function () { if (token === loadSeq) viewer.clear(); });
    return importQueue;
  }

  function onImported(token, doc) {
    if (token !== loadSeq) return;
    resetView();
    ui.message.hidden = true;
    canvas.zoom("fit-viewport", "auto");
    state.nodes = P.extractNodes(doc).filter(function (n) { return registry.get(n.id); });
    state.nodes.forEach(function (n) { state.byId[n.id] = n; });
    state.loaded = true;
    var attrs = P.listAttributes(state.nodes);
    attrs.forEach(function (a) {
      var opt = document.createElement("option");
      opt.value = a;
      opt.textContent = a;
      ui.attrSelect.appendChild(opt);
      var laneOpt = document.createElement("option");
      laneOpt.value = a;
      laneOpt.textContent = a;
      ui.laneAttr.appendChild(laneOpt);
    });
    setAttr(attrs.indexOf(P.SOURCE_ATTR) >= 0 ? P.SOURCE_ATTR : P.TYPE_ATTR);
    setControlsEnabled(true);
    scheduleScrollbars();
  }

  function setAttr(attr) {
    state.attr = attr;
    state.selected = [];
    state.entries = P.buildIndex(state.nodes, attr).map(function (entry, index) {
      entry.color = colorAt(index);
      return entry;
    });
    ui.attrSelect.value = attr;
    renderChips();
    applyHighlight();
  }

  function colorAt(index) {
    if (index < PALETTE.length) return PALETTE[index];
    var hue = ((index - PALETTE.length) * 137.508 + 25) % 360;
    return { stroke: "hsl(" + hue + ",65%,38%)", fill: "hsl(" + hue + ",80%,92%)" };
  }

  function moveLane(value, direction) {
    var index = activeLanes.findIndex(function (lane) { return lane.value === value; });
    var target = index + direction;
    if (!state.loaded || !activeLaneAttr || index < 0 || target < 0 || target >= activeLanes.length) return;
    var order = activeLanes.map(function (lane) { return lane.value; });
    order[index] = order[target]; order[target] = value;
    laneOrders.set(activeLaneAttr, order);
    applyLaneView();
    var lane = activeLanes.find(function (entry) { return entry.value === value; });
    if (!lane) return;
    var vb = canvas.viewbox(), padding = 8 / vb.scale;
    var right = lane.x + lane.width - 4 / vb.scale, left = right - 46 / vb.scale;
    var x = vb.x;
    if (right > vb.x + vb.width - padding) x = right - vb.width + padding;
    else if (left < vb.x + padding) x = left - padding;
    if (x !== vb.x) canvas.scroll({ dx: (vb.x - x) * vb.scale, dy: 0 });
    laneView.syncHeader();
    var group = Array.from(ui.laneHeader.querySelectorAll(".b2g-frozen-lane")).find(function (element) {
      return element.getAttribute("data-lane-value") === value;
    });
    var button = group && group.querySelector('.b2g-lane-move[data-direction="' + direction + '"]');
    if (button && button.getAttribute("aria-disabled") !== "true") button.focus({ preventScroll: true });
  }

  function applyLaneView() {
    if (!state.loaded) return;
    hideCard();
    clearEdgeSelection();
    closePrint();
    clearHighlightStyles();
    ++exportSeq;
    exporting = false;
    ui.exportStatus.hidden = true;
    var attr = ui.laneAttr.value, previous = activeLaneAttr;
    var vb = canvas.viewbox();
    try {
      if (attr) {
        var result = laneView.apply(state.nodes, attr, laneOrders.get(attr), colorAt);
        laneOrders.set(attr, result.lanes.map(function (lane) { return lane.value; }));
        activeLanes = result.lanes;
        activeLaneAttr = attr;
        ui.stage.classList.add("has-lanes");
        canvas.resized();
        if (attr !== previous) canvas.viewbox({ x: result.bounds.x,
          y: result.bounds.y + 28, width: ui.canvas.clientWidth / vb.scale, height: ui.canvas.clientHeight / vb.scale });
        laneView.syncHeader();
      } else {
        laneView.restore();
        activeLaneAttr = "";
        activeLanes = [];
        ui.stage.classList.remove("has-lanes");
        canvas.resized();
        canvas.zoom("fit-viewport", "auto");
      }
    } catch (err) {
      laneView.restore();
      activeLaneAttr = "";
      ui.laneAttr.value = "";
      activeLanes = [];
      ui.stage.classList.remove("has-lanes");
      canvas.resized();
      showExportStatus("无法生成泳道视图：" + (err && err.message ? err.message : err), true);
    }
    applyHighlight();
    scrollRange = null;
    canvas.resized();
    scheduleScrollbars();
    setControlsEnabled(state.loaded);
  }

  ui.laneAttr.addEventListener("change", applyLaneView);
  ui.laneReset.addEventListener("click", function () {
    ui.laneAttr.value = "";
    applyLaneView();
  });
  viewer.on("root.set", function () {
    if (!state.loaded || !ui.laneAttr.value) return;
    var token = loadSeq;
    window.requestAnimationFrame(function () {
      if (token !== loadSeq || !state.loaded || !ui.laneAttr.value) return;
      // 进入/退出子流程后，按新画布的节点重新生成泳道。
      activeLaneAttr = "";
      applyLaneView();
    });
  });

  function renderChips() {
    ui.chips.innerHTML = "";
    state.entries.forEach(function (entry) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip" + (entry.value === P.UNSET ? " unset" : "") +
        (state.selected.indexOf(entry.value) >= 0 ? " on" : "");
      chip.dataset.value = entry.value;
      chip.style.setProperty("--chip-stroke", entry.color.stroke);
      chip.style.setProperty("--chip-fill", entry.color.fill);
      chip.setAttribute("aria-pressed", String(state.selected.indexOf(entry.value) >= 0));
      chip.title = entry.value + "；节点颜色与标签对应，同时匹配多个已选取值的节点使用分段底色";
      chip.textContent = entry.value;
      var count = document.createElement("span");
      count.className = "count";
      count.textContent = "· " + entry.ids.length;
      chip.appendChild(count);
      chip.addEventListener("click", function () { toggleValue(entry.value); });
      ui.chips.appendChild(chip);
    });
  }

  function toggleValue(value) {
    var i = state.selected.indexOf(value);
    if (i >= 0) state.selected.splice(i, 1);
    else state.selected.push(value);
    renderChips();
    applyHighlight();
  }

  function baseOf(el) {
    return el.type === "label" && el.labelTarget ? el.labelTarget : el;
  }

  function clearHighlightStyles() {
    highlightedVisuals.forEach(function (item) {
      item.properties.forEach(function (property) {
        if (property.value) item.shape.style.setProperty(property.name, property.value, property.priority);
        else item.shape.style.removeProperty(property.name);
      });
    });
    highlightedVisuals = [];
    highlightGradients.forEach(function (gradient) { gradient.remove(); });
    highlightGradients = [];
  }

  function sharedFill(entries) {
    var svg = canvas.getActiveLayer().ownerSVGElement;
    var defs = svg.querySelector(":scope > defs");
    if (!defs) {
      defs = document.createElementNS(SVG_NS, "defs");
      svg.insertBefore(defs, svg.firstChild);
    }
    var gradient = document.createElementNS(SVG_NS, "linearGradient");
    var id = "b2g-highlight-" + loadSeq + "-" + highlightGradients.length;
    gradient.setAttribute("id", id);
    gradient.setAttribute("x1", "0%");
    gradient.setAttribute("y1", "0%");
    gradient.setAttribute("x2", "100%");
    gradient.setAttribute("y2", "0%");
    entries.forEach(function (entry, index) {
      [index / entries.length, (index + 1) / entries.length].forEach(function (offset) {
        var stop = document.createElementNS(SVG_NS, "stop");
        stop.setAttribute("offset", offset * 100 + "%");
        stop.setAttribute("stop-color", entry.color.fill);
        gradient.appendChild(stop);
      });
    });
    defs.appendChild(gradient);
    highlightGradients.push(gradient);
    return "url(#" + id + ")";
  }

  function colorShape(el, entries, fills) {
    var graphics = registry.getGraphics(el);
    var visual = graphics && graphics.querySelector(".djs-visual");
    var shape = visual && visual.firstElementChild;
    if (!shape) return;
    highlightedVisuals.push({ shape: shape, properties: ["stroke", "fill", "stroke-width"].map(function (name) {
      return { name: name, value: shape.style.getPropertyValue(name), priority: shape.style.getPropertyPriority(name) };
    }) });
    var key = entries.map(function (entry) { return state.entries.indexOf(entry); }).join(",");
    if (!fills.has(key)) fills.set(key, entries.length > 1 ? sharedFill(entries) : entries[0].color.fill);
    // 内联样式会随 saveSVG 一起导出；important 保留 bpmn-js 图形原本的描边覆盖规则。
    shape.style.setProperty("stroke", entries[0].color.stroke, "important");
    shape.style.setProperty("stroke-width", "3px", "important");
    shape.style.setProperty("fill", fills.get(key), "important");
  }

  function applyHighlight() {
    clearHighlightStyles();
    registry.getAll().forEach(function (el) {
      canvas.removeMarker(el.id, "b2g-hl");
      canvas.removeMarker(el.id, "b2g-dim");
    });
    if (!state.selected.length) return;
    // 按标签的固定顺序分配颜色，避免点击顺序改变节点颜色。
    var matched = new Map(), fills = new Map();
    state.entries.forEach(function (entry) {
      if (state.selected.indexOf(entry.value) < 0) return;
      entry.ids.forEach(function (id) {
        if (!matched.has(id)) matched.set(id, []);
        matched.get(id).push(entry);
      });
    });
    registry.getAll().forEach(function (el) {
      if (!el.parent) return;                       // 根元素（process）
      var base = baseOf(el);
      if (base.waypoints) {                          // 连线及其标签
        var keep = base.source && base.target && matched.has(base.source.id) && matched.has(base.target.id);
        if (!keep) canvas.addMarker(el.id, "b2g-dim");
        return;
      }
      if (matched.has(base.id)) {
        if (el === base) {
          canvas.addMarker(el.id, "b2g-hl");
          colorShape(el, matched.get(base.id), fills);
        }
      } else {
        canvas.addMarker(el.id, "b2g-dim");
      }
    });
  }

  function hideCard() {
    ui.card.hidden = true;
  }

  function clearEdgeSelection() {
    selectedEdgeIds.forEach(function (id) {
      if (registry.get(id)) canvas.removeMarker(id, "b2g-edge-selected");
    });
    selectedEdgeIds = [];
  }

  function selectEdge(edge) {
    clearEdgeSelection();
    selectedEdgeIds = [edge.id].concat((edge.labels || []).map(function (label) { return label.id; }));
    selectedEdgeIds.forEach(function (id) { canvas.addMarker(id, "b2g-edge-selected"); });
  }

  function fieldCopyButton(value, target, key, status) {
    var text = value == null ? "" : String(value);
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn field-copy";
    button.textContent = "复制";
    button.title = text ? "复制「" + key + "」的完整文本" : "该字段为空";
    button.setAttribute("aria-label", "复制" + key);
    button.disabled = !text;
    button.addEventListener("click", function () {
      button.disabled = true;
      status.hidden = false;
      status.textContent = "正在复制「" + key + "」…";
      copyCardText(text, target).then(function () {
        if (!ui.card.hidden && ui.card.contains(status)) status.textContent = "已复制「" + key + "」。";
      }).catch(function () {
        if (!ui.card.hidden && ui.card.contains(status)) {
          selectCardText(target);
          status.textContent = "请按 Ctrl+C（Mac：⌘C）复制选中的字段文本。";
        }
      }).then(function () { button.disabled = false; });
    });
    return button;
  }

  function addRow(dl, key, value, status) {
    var dt = document.createElement("dt");
    dt.textContent = key;
    var dd = document.createElement("dd");
    var text = document.createElement("span");
    text.className = "field-value";
    text.tabIndex = -1;
    text.textContent = value;
    dd.appendChild(text);
    dd.appendChild(fieldCopyButton(value, text, key, status));
    dl.appendChild(dt);
    dl.appendChild(dd);
  }

  function showCard(node, shape) {
    ui.card.innerHTML = "";
    ui.card.classList.remove("connection-card");
    var status = document.createElement("p");
    status.className = "copy-status";
    status.setAttribute("role", "status");
    status.hidden = true;
    var heading = document.createElement("div");
    heading.className = "card-heading";
    var title = document.createElement("h3");
    title.textContent = node.name || "（无名称）";
    title.tabIndex = -1;
    heading.appendChild(title);
    heading.appendChild(fieldCopyButton(node.name, title, "节点名称", status));
    ui.card.appendChild(heading);
    var dl = document.createElement("dl");
    addRow(dl, P.TYPE_ATTR, P.typeLabel(node.type), status);
    addRow(dl, "ID", node.id, status);
    var matches = state.entries.filter(function (entry) {
      return state.selected.indexOf(entry.value) >= 0 && entry.ids.indexOf(node.id) >= 0;
    });
    if (matches.length) addRow(dl, "当前匹配", matches.map(function (entry) { return entry.value; }).join("、"), status);
    Object.keys(node.props).forEach(function (k) { addRow(dl, k, node.props[k].join("、"), status); });
    ui.card.appendChild(dl);
    ui.card.appendChild(status);
    positionCard(shape);
  }

  function positionCard(shape) {
    ui.card.hidden = false;

    var vb = canvas.viewbox();
    var width = ui.card.offsetWidth, height = ui.card.offsetHeight;
    var stageW = ui.canvas.clientWidth, stageH = ui.canvas.clientHeight;
    var left = (shape.x + shape.width - vb.x) * vb.scale + 12;
    if (left + width > stageW - 8) left = (shape.x - vb.x) * vb.scale - width - 12;
    var stageTop = ui.canvas.offsetTop;
    var top = (shape.y - vb.y) * vb.scale + stageTop;
    ui.card.style.left = Math.max(8, Math.min(left, stageW - width - 8)) + "px";
    ui.card.style.top = Math.max(stageTop + 8, Math.min(top, stageTop + stageH - height - 8)) + "px";
  }

  function selectCardText(target) {
    target.focus({ preventScroll: true });
    if (typeof target.select === "function") {
      target.select();
    } else {
      var range = document.createRange();
      range.selectNodeContents(target);
      var selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
  }

  function copyCardText(text, target) {
    function fallback() {
      if (ui.card.hidden || !ui.card.contains(target)) throw new Error("详情已关闭。");
      selectCardText(target);
      if (!document.execCommand("copy")) throw new Error("请按 Ctrl+C（Mac：⌘C）复制选中的文本。");
    }
    // 兼容双击 HTML 打开的离线页面，以及浏览器拒绝剪贴板权限的情况。
    return Promise.resolve().then(function () {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text);
      }
      throw new Error("浏览器未提供剪贴板接口。");
    }).catch(fallback);
  }

  function showConnectionCard(connection, clicked) {
    var name = connection.businessObject && connection.businessObject.name;
    if (typeof name !== "string" || !name.trim()) { hideCard(); return; }
    ui.card.innerHTML = "";
    ui.card.classList.add("connection-card");
    var title = document.createElement("h3");
    title.textContent = "连线文字";
    ui.card.appendChild(title);
    var field = document.createElement("textarea");
    field.className = "connection-text";
    field.readOnly = true;
    field.setAttribute("aria-label", "连线完整文本");
    field.rows = Math.min(8, Math.max(3, name.split(/\r\n|\r|\n/).length));
    field.value = name;
    ui.card.appendChild(field);
    var actions = document.createElement("div");
    actions.className = "card-actions";
    var copy = document.createElement("button");
    copy.type = "button";
    copy.className = "btn primary";
    copy.textContent = "复制文本";
    var close = document.createElement("button");
    close.type = "button";
    close.className = "btn";
    close.textContent = "关闭";
    close.addEventListener("click", function () { hideCard(); clearEdgeSelection(); });
    actions.appendChild(copy);
    actions.appendChild(close);
    ui.card.appendChild(actions);
    var status = document.createElement("p");
    status.className = "copy-status";
    status.setAttribute("role", "status");
    status.textContent = "文本已选中，可按 Ctrl+C（Mac：⌘C）复制，也可选取部分文字。";
    ui.card.appendChild(status);
    copy.addEventListener("click", function () {
      copy.disabled = true;
      status.textContent = "正在复制…";
      copyCardText(field.value, field).then(function () {
        if (!ui.card.hidden && ui.card.contains(status)) status.textContent = "已复制连线文本。";
      }).catch(function () {
        if (!ui.card.hidden && ui.card.contains(status)) {
          selectCardText(field);
          status.textContent = "请按 Ctrl+C（Mac：⌘C）复制选中的文本。";
        }
      }).then(function () { copy.disabled = false; });
    });
    var anchor = clicked.type === "label" ? clicked : connection.label || (connection.labels && connection.labels[0]);
    if (!anchor) {
      var points = connection.waypoints;
      var point = points[Math.floor(points.length / 2)] || { x: 0, y: 0 };
      anchor = { x: point.x, y: point.y, width: 0, height: 0 };
    }
    positionCard(anchor);
    selectCardText(field);
  }

  viewer.on("element.click", function (event) {
    var el = baseOf(event.element);
    if (el.waypoints) { selectEdge(el); showConnectionCard(el, event.element); return; }
    clearEdgeSelection();
    var node = state.byId[el.id];
    if (node) showCard(node, el);
    else hideCard();
  });
  viewer.on("canvas.viewbox.changing", hideCard);

  function scheduleScrollbars() {
    if (scrollFrame) return;
    scrollFrame = window.requestAnimationFrame(function () {
      scrollFrame = 0;
      syncScrollbars();
    });
  }

  function syncScrollbars() {
    if (!state.loaded) {
      scrollRange = null;
      ui.scrollXSize.style.width = "1px";
      ui.scrollYSize.style.height = "1px";
      ui.scrollX.scrollLeft = syncedScrollX = 0;
      ui.scrollY.scrollTop = syncedScrollY = 0;
      return;
    }
    var vb = canvas.viewbox();
    if (!vb.outer.width || !vb.outer.height || !vb.scale) return;
    // 将整图与当前视口取并集：允许继续使用原有的自由拖动，并涵盖负坐标布局。
    var padding = 24 / vb.scale;
    var left = Math.min(vb.inner.x - padding, vb.x);
    var top = Math.min(vb.inner.y - padding, vb.y);
    var right = Math.max(vb.inner.x + vb.inner.width + padding, vb.x + vb.width);
    var bottom = Math.max(vb.inner.y + vb.inner.height + padding, vb.y + vb.height);
    // 同一缩放下保持滚动范围稳定，避免拖动滑块时范围收缩导致滑块跳动。
    if (scrollRange && scrollRange.scale === vb.scale) {
      left = Math.min(left, scrollRange.x);
      top = Math.min(top, scrollRange.y);
      right = Math.max(right, scrollRange.right);
      bottom = Math.max(bottom, scrollRange.bottom);
    }
    scrollRange = { x: left, y: top, right: right, bottom: bottom, scale: vb.scale };
    ui.scrollXSize.style.width = Math.ceil((right - left) * vb.scale) + "px";
    ui.scrollYSize.style.height = Math.ceil((bottom - top) * vb.scale) + "px";
    ui.scrollX.scrollLeft = (vb.x - left) * vb.scale;
    ui.scrollY.scrollTop = (vb.y - top) * vb.scale;
    // 原生 scroll 事件异步触发，记住实际值以免同步位置时反过来移动画布。
    syncedScrollX = ui.scrollX.scrollLeft;
    syncedScrollY = ui.scrollY.scrollTop;
  }

  ui.scrollX.addEventListener("scroll", function () {
    if (!scrollRange || Math.abs(ui.scrollX.scrollLeft - syncedScrollX) < 0.5) return;
    syncedScrollX = ui.scrollX.scrollLeft;
    var vb = canvas.viewbox();
    var x = scrollRange.x + syncedScrollX / scrollRange.scale;
    canvas.scroll({ dx: (vb.x - x) * vb.scale, dy: 0 });
    scheduleScrollbars();
  });
  ui.scrollY.addEventListener("scroll", function () {
    if (!scrollRange || Math.abs(ui.scrollY.scrollTop - syncedScrollY) < 0.5) return;
    syncedScrollY = ui.scrollY.scrollTop;
    var vb = canvas.viewbox();
    var y = scrollRange.y + syncedScrollY / scrollRange.scale;
    canvas.scroll({ dx: 0, dy: (vb.y - y) * vb.scale });
    scheduleScrollbars();
  });
  viewer.on(["canvas.viewbox.changing", "canvas.viewbox.changed", "canvas.resized"], scheduleScrollbars);
  function resizeCanvas() {
    scrollRange = null;
    canvas.resized();
    scheduleScrollbars();
  }
  if (window.ResizeObserver) new ResizeObserver(resizeCanvas).observe(ui.canvas);
  else window.addEventListener("resize", resizeCanvas);

  function readFile(file) {
    var reader = new FileReader();
    reader.onload = function () { openText(file.name, String(reader.result)); };
    reader.onerror = function () { showMessage("无法读取「" + file.name + "」。", true); };
    reader.readAsText(file, "utf-8");
  }

  ui.fileInput.addEventListener("change", function () {
    if (ui.fileInput.files.length) readFile(ui.fileInput.files[0]);
    ui.fileInput.value = "";
  });
  ui.attrSelect.addEventListener("change", function () { setAttr(ui.attrSelect.value); });
  ui.clearBtn.addEventListener("click", function () {
    state.selected = [];
    renderChips();
    applyHighlight();
  });
  ui.fitBtn.addEventListener("click", function () {
    scrollRange = null;
    canvas.zoom("fit-viewport", "auto");
  });

  function showExportStatus(text, isError) {
    ui.exportStatus.textContent = text;
    ui.exportStatus.classList.toggle("error", !!isError);
    ui.exportStatus.hidden = false;
  }

  function downloadBlob(blob, name) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    try { link.click(); }
    finally {
      link.remove();
      // 留出时间让浏览器接管下载，再释放文件内容。
      window.setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    }
  }

  function exportDiagram(format) {
    if (!state.loaded || exporting) return;
    var token = ++exportSeq;
    var name = ui.fileName.textContent.replace(/\.(bpmn|xml)$/i, "")
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/[. ]+$/g, "") || "BPMN";
    exporting = true;
    setControlsEnabled(state.loaded);
    showExportStatus("正在生成完整流程图的 " + format.toUpperCase() + "…");
    Promise.resolve().then(function () {
      if (token !== exportSeq) return;
      return viewer.saveSVG();
    }).then(function (result) {
      if (token !== exportSeq || !result) return;
      var image = window.B2GPrint.prepareSVG(result.svg);
      if (format === "png") return window.B2GPrint.toPNG(image);
      return { blob: new Blob([image.svg], { type: "image/svg+xml;charset=utf-8" }) };
    }).then(function (result) {
      if (token !== exportSeq || !result) return;
      downloadBlob(result.blob, name + "." + format);
      showExportStatus(format === "png" ?
        "已生成 PNG（" + result.width + " × " + result.height + " 像素），已开始下载。" :
        "已生成 SVG 并开始下载，可无损放大查看完整流程图。");
    }).catch(function (err) {
      if (token === exportSeq) showExportStatus("导出失败：" + (err && err.message ? err.message : err), true);
    }).then(function () {
      if (token !== exportSeq) return;
      exporting = false;
      setControlsEnabled(state.loaded);
    });
  }

  ui.exportSvgBtn.addEventListener("click", function () { exportDiagram("svg"); });
  ui.exportPngBtn.addEventListener("click", function () { exportDiagram("png"); });

  function closePrint() {
    ++printSeq;
    printImage = null;
    ui.printConfirm.disabled = true;
    ui.printPreview.removeAttribute("srcdoc");
    if (ui.printDialog.open) ui.printDialog.close();
  }

  function printError(err) {
    ui.printConfirm.disabled = true;
    ui.printStatus.textContent = "无法准备打印：" + (err && err.message ? err.message : err);
  }

  function updatePrintPreview() {
    if (!printImage || !ui.printDialog.open) return;
    ui.printConfirm.disabled = true;
    ui.printStatus.textContent = "正在准备预览…";
    try {
      var result = window.B2GPrint.buildDocument(printImage, printName, {
        paper: ui.printPaper.value, orientation: ui.printOrientation.value
      });
      ui.printPreview.onload = function () {
        if (!ui.printDialog.open || !printImage) return;
        var image = ui.printPreview.contentDocument.getElementById("diagram");
        if (!image || !image.complete || !image.naturalWidth) {
          printError(new Error("预览图像加载失败，请关闭后重试。"));
          return;
        }
        ui.printStatus.textContent = result.layout.paper + " · " +
          (result.layout.orientation === "landscape" ? "横向" : "纵向") + " · 完整流程图 / 1 页";
        ui.printConfirm.disabled = false;
      };
      ui.printPreview.srcdoc = result.html;
    } catch (err) { printError(err); }
  }

  ui.printBtn.addEventListener("click", function () {
    if (!state.loaded) return;
    var token = ++printSeq;
    printImage = null;
    printName = ui.fileName.textContent;
    ui.printStatus.textContent = "正在生成完整流程图…";
    ui.printConfirm.disabled = true;
    ui.printDialog.showModal();
    // saveSVG 导出整张图，与当前缩放、平移位置无关；不改变查看器画布。
    viewer.saveSVG().then(function (result) {
      if (token !== printSeq || !ui.printDialog.open) return;
      printImage = window.B2GPrint.prepareSVG(result.svg);
      updatePrintPreview();
    }).catch(function (err) {
      if (token === printSeq && ui.printDialog.open) printError(err);
    });
  });
  ui.printClose.addEventListener("click", closePrint);
  ui.printDialog.addEventListener("cancel", function (e) { e.preventDefault(); closePrint(); });
  ui.printPaper.addEventListener("change", updatePrintPreview);
  ui.printOrientation.addEventListener("change", updatePrintPreview);
  ui.printConfirm.addEventListener("click", function () {
    if (ui.printConfirm.disabled) return;
    try {
      ui.printPreview.contentWindow.focus();
      ui.printPreview.contentWindow.print();
    } catch (err) { printError(err); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { hideCard(); clearEdgeSelection(); }
  });

  var dragDepth = 0;
  document.addEventListener("dragenter", function (e) {
    e.preventDefault();
    dragDepth++;
    ui.dropHint.hidden = false;
  });
  document.addEventListener("dragleave", function () {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) ui.dropHint.hidden = true;
  });
  document.addEventListener("dragover", function (e) { e.preventDefault(); });
  document.addEventListener("drop", function (e) {
    e.preventDefault();
    dragDepth = 0;
    ui.dropHint.hidden = true;
    if (e.dataTransfer && e.dataTransfer.files.length) readFile(e.dataTransfer.files[0]);
  });

  // 由 `python -m bpmn2graphml view <文件>` 生成的启动页会嵌入要打开的文件
  var preload = $("b2g-preload");
  if (preload) {
    var binary = atob(preload.getAttribute("data-base64") || "");
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    openText(preload.getAttribute("data-filename") || "BPMN", new TextDecoder("utf-8").decode(bytes));
  }

  window.b2gViewer.openText = openText;
})();
