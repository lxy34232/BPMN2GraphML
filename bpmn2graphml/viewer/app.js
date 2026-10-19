/* BPMN 属性查看器：打开文件、驱动 bpmn-js、按属性筛选高亮、节点详情卡。 */
(function () {
  "use strict";

  var P = window.B2GProps;
  var NO_DI_MESSAGE = "该文件没有图形布局信息（BPMNDI），无法显示流程图；" +
    "可先经 yEd 布局并用本工具转回 BPMN 后再查看。";

  var $ = function (id) { return document.getElementById(id); };
  var ui = {
    fileInput: $("file-input"), fileName: $("file-name"), attrSelect: $("attr-select"),
    chips: $("chips"), clearBtn: $("clear-btn"), fitBtn: $("fit-btn"), stage: $("stage"),
    message: $("message"), card: $("card"), dropHint: $("drop-hint")
  };

  var viewer = new window.BpmnJS({ container: "#canvas" });
  var canvas = viewer.get("canvas");
  var registry = viewer.get("elementRegistry");

  var state = { nodes: [], byId: {}, attr: null, selected: [], loaded: false };
  window.b2gViewer = { viewer: viewer, state: state };   // 便于调试与端到端测试

  function showMessage(text, isError) {
    ui.message.textContent = text;
    ui.message.classList.toggle("error", !!isError);
    ui.message.hidden = false;
  }

  function setControlsEnabled(on) {
    ui.attrSelect.disabled = !on;
    ui.clearBtn.disabled = !on;
    ui.fitBtn.disabled = !on;
  }

  function resetView() {
    state.nodes = [];
    state.byId = {};
    state.attr = null;
    state.selected = [];
    state.loaded = false;
    ui.attrSelect.innerHTML = "";
    ui.chips.innerHTML = "";
    hideCard();
    setControlsEnabled(false);
  }

  function openText(name, text) {
    resetView();
    ui.fileName.textContent = name;
    ui.fileName.title = name;
    var doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.getElementsByTagName("parsererror").length || !doc.documentElement) {
      viewer.clear();
      showMessage("无法解析「" + name + "」：不是有效的 XML 文件。", true);
      return Promise.resolve();
    }
    if (!P.hasDiagram(doc)) {
      viewer.clear();
      showMessage("「" + name + "」：" + NO_DI_MESSAGE, true);
      return Promise.resolve();
    }
    return viewer.importXML(text).then(function () {
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
      });
      setAttr(attrs.indexOf(P.SOURCE_ATTR) >= 0 ? P.SOURCE_ATTR : P.TYPE_ATTR);
      setControlsEnabled(true);
    }).catch(function (err) {
      viewer.clear();
      showMessage("无法显示「" + name + "」：" + (err && err.message ? err.message : err), true);
    });
  }

  function setAttr(attr) {
    state.attr = attr;
    state.selected = [];
    ui.attrSelect.value = attr;
    renderChips();
    applyHighlight();
  }

  function renderChips() {
    ui.chips.innerHTML = "";
    P.buildIndex(state.nodes, state.attr).forEach(function (entry) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip" + (entry.value === P.UNSET ? " unset" : "") +
        (state.selected.indexOf(entry.value) >= 0 ? " on" : "");
      chip.dataset.value = entry.value;
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

  function applyHighlight() {
    registry.getAll().forEach(function (el) {
      canvas.removeMarker(el.id, "b2g-hl");
      canvas.removeMarker(el.id, "b2g-dim");
    });
    if (!state.selected.length) return;
    var matched = P.matchIds(state.nodes, state.attr, state.selected);
    registry.getAll().forEach(function (el) {
      if (!el.parent) return;                       // 根元素（process）
      var base = baseOf(el);
      if (base.waypoints) {                          // 连线及其标签
        var keep = base.source && base.target && matched.has(base.source.id) && matched.has(base.target.id);
        if (!keep) canvas.addMarker(el.id, "b2g-dim");
        return;
      }
      if (matched.has(base.id)) {
        if (el === base) canvas.addMarker(el.id, "b2g-hl");
      } else {
        canvas.addMarker(el.id, "b2g-dim");
      }
    });
  }

  function hideCard() {
    ui.card.hidden = true;
  }

  function addRow(dl, key, value) {
    var dt = document.createElement("dt");
    dt.textContent = key;
    var dd = document.createElement("dd");
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }

  function showCard(node, shape) {
    ui.card.innerHTML = "";
    var title = document.createElement("h3");
    title.textContent = node.name || "（无名称）";
    ui.card.appendChild(title);
    var dl = document.createElement("dl");
    addRow(dl, P.TYPE_ATTR, P.typeLabel(node.type));
    addRow(dl, "ID", node.id);
    Object.keys(node.props).forEach(function (k) { addRow(dl, k, node.props[k].join("、")); });
    ui.card.appendChild(dl);
    ui.card.hidden = false;

    var vb = canvas.viewbox();
    var width = ui.card.offsetWidth, height = ui.card.offsetHeight;
    var stageW = ui.stage.clientWidth, stageH = ui.stage.clientHeight;
    var left = (shape.x + shape.width - vb.x) * vb.scale + 12;
    if (left + width > stageW - 8) left = (shape.x - vb.x) * vb.scale - width - 12;
    var top = (shape.y - vb.y) * vb.scale;
    ui.card.style.left = Math.max(8, Math.min(left, stageW - width - 8)) + "px";
    ui.card.style.top = Math.max(8, Math.min(top, stageH - height - 8)) + "px";
  }

  viewer.on("element.click", function (event) {
    var el = baseOf(event.element);
    var node = state.byId[el.id];
    if (node) showCard(node, el);
    else hideCard();
  });
  viewer.on("canvas.viewbox.changing", hideCard);

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
  ui.fitBtn.addEventListener("click", function () { canvas.zoom("fit-viewport", "auto"); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") hideCard(); });

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
