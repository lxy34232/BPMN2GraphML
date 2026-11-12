/* 只改变查看器中的横向布局；保留原始几何信息，可随时恢复。 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else root.B2GLanes = factory(root);
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";

  function svgElement(name, attributes, parent) {
    var element = document.createElementNS(NS, name);
    Object.keys(attributes || {}).forEach(function (key) { element.setAttribute(key, attributes[key]); });
    if (parent) parent.appendChild(element);
    return element;
  }

  function copyPoints(points) {
    return JSON.parse(JSON.stringify(points));
  }

  function isFrame(element) {
    var base = element.labelTarget || element;
    return base.type === "bpmn:Participant" || base.type === "bpmn:Lane";
  }

  function simplify(points) {
    var result = [];
    points.forEach(function (point) {
      var last = result[result.length - 1];
      if (last && last.x === point.x && last.y === point.y) return;
      while (result.length > 1) {
        var a = result[result.length - 2], b = result[result.length - 1];
        var sameAxis = (a.x === b.x && b.x === point.x) || (a.y === b.y && b.y === point.y);
        var forward = (b.x - a.x) * (point.x - b.x) + (b.y - a.y) * (point.y - b.y) >= 0;
        if (!sameAxis || !forward) break;
        result.pop();
      }
      result.push({ x: point.x, y: point.y });
    });
    return result;
  }

  function direction(from, to, fallback) {
    var dx = to.x - from.x, dy = to.y - from.y;
    if (!dx && !dy) return fallback;
    return Math.abs(dx) > Math.abs(dy) ? { x: Math.sign(dx), y: 0 } : { x: 0, y: Math.sign(dy) };
  }

  function crosses(a, b, box, padding) {
    var left = box.x - padding, right = box.x + box.width + padding;
    var top = box.y - padding, bottom = box.y + box.height + padding;
    if (a.y === b.y) return a.y > top && a.y < bottom && Math.max(a.x, b.x) > left && Math.min(a.x, b.x) < right;
    return a.x > left && a.x < right && Math.max(a.y, b.y) > top && Math.min(a.y, b.y) < bottom;
  }

  // 固定原来的出入点与出入方向，在少量横/纵通道中挑选绕行较少的正交路径。
  function routeConnection(points, sourceDx, targetDx, source, target, obstacles) {
    if (!points || points.length < 2) return points ? copyPoints(points) : [];
    obstacles = obstacles || [];
    var first = points[0], last = points[points.length - 1];
    var start = { x: first.x + sourceDx, y: first.y };
    var end = { x: last.x + targetDx, y: last.y };
    var next = points.find(function (p) { return p.x !== first.x || p.y !== first.y; }) || last;
    var previous = points.slice().reverse().find(function (p) { return p.x !== last.x || p.y !== last.y; }) || first;
    var out = direction(first, next, { x: 0, y: 1 });
    var into = direction(last, previous, { x: 0, y: -1 });
    var a = { x: start.x + out.x * 24, y: start.y + out.y * 24 };
    var b = { x: end.x + into.x * 24, y: end.y + into.y * 24 };
    var boxes = [source, target].filter(Boolean);
    var xs = [(a.x + b.x) / 2, a.x, b.x], ys = [(a.y + b.y) / 2, a.y, b.y];
    boxes.forEach(function (box) {
      xs.push(box.x - 32, box.x + box.width + 32);
      ys.push(box.y - 32, box.y + box.height + 32);
    });
    // 只补充与直连走廊相近的障碍边界，避免大图产生过多候选路径。
    obstacles.filter(function (box) {
      return box.x < Math.max(a.x, b.x) + 32 && box.x + box.width > Math.min(a.x, b.x) - 32 &&
        box.y < Math.max(a.y, b.y) + 32 && box.y + box.height > Math.min(a.y, b.y) - 32;
    }).slice(0, 6).forEach(function (box) {
      xs.push(box.x - 16, box.x + box.width + 16);
      ys.push(box.y - 16, box.y + box.height + 16);
    });
    var candidates = [
      [a, { x: b.x, y: a.y }, b],
      [a, { x: a.x, y: b.y }, b]
    ];
    Array.from(new Set(xs)).forEach(function (x) { candidates.push([a, { x: x, y: a.y }, { x: x, y: b.y }, b]); });
    Array.from(new Set(ys)).forEach(function (y) { candidates.push([a, { x: a.x, y: y }, { x: b.x, y: y }, b]); });
    var best = null, bestScore = Infinity;
    candidates.forEach(function (middle) {
      var path = simplify([start].concat(middle, [end]));
      var score = path.length * 12;
      for (var i = 1; i < path.length; i++) {
        var p = path[i - 1], q = path[i];
        score += Math.abs(q.x - p.x) + Math.abs(q.y - p.y);
        obstacles.forEach(function (box) { if (crosses(p, q, box, 6)) score += 100000; });
        // 出入点所在图形只检查中间段，允许端点位于菱形/圆形的包围盒内部。
        if (i > 1 && i < path.length - 1) boxes.forEach(function (box) {
          if (crosses(p, q, box, 0)) score += 100000;
        });
        if (i > 1) {
          var before = path[i - 2];
          if ((p.x - before.x) * (q.x - p.x) + (p.y - before.y) * (q.y - p.y) < 0) score += 1000000;
        }
      }
      if (score < bestScore) { best = path; bestScore = score; }
    });
    return best;
  }

  function labelPosition(points, width, height, ratio, occupied) {
    var total = 0, before = 0, candidates = [];
    for (var i = 1; i < points.length; i++) total += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
    for (var j = 1; j < points.length; j++) {
      var a = points[j - 1], b = points[j], length = Math.hypot(b.x - a.x, b.y - a.y);
      if (!length) continue;
      var horizontal = a.y === b.y;
      var extent = horizontal ? width : height;
      [Math.max(0, Math.min(1, (ratio * total - before) / length)), 0.25, 0.5, 0.75].forEach(function (t) {
        if (length > extent + 16) t = Math.max((extent / 2 + 8) / length, Math.min(1 - (extent / 2 + 8) / length, t));
        var x = a.x + (b.x - a.x) * t, y = a.y + (b.y - a.y) * t;
        [-1, 1].forEach(function (side) {
          var box = { x: horizontal ? x - width / 2 : x + (side < 0 ? -width - 8 : 8),
            y: horizontal ? y + (side < 0 ? -height - 8 : 8) : y - height / 2, width: width, height: height };
          var score = Math.abs(before + length * t - ratio * total) + (length < extent + 16 ? 500 : 0);
          occupied.forEach(function (other) {
            if (box.x < other.x + other.width + 4 && box.x + width > other.x - 4 &&
                box.y < other.y + other.height + 4 && box.y + height > other.y - 4) score += 100000;
          });
          candidates.push({ box: box, score: score });
        });
      });
      before += length;
    }
    candidates.sort(function (a, b) { return a.score - b.score; });
    return candidates.length ? candidates[0].box : { x: points[0].x + 8, y: points[0].y, width: width, height: height };
  }

  function create(viewer, onMove, header) {
    var P = root.B2GProps;
    var canvas = viewer.get("canvas"), registry = viewer.get("elementRegistry");
    var events = viewer.get("eventBus");
    var originals = new Map(), background = null;
    var frozenLanes = [], headerKey = "", headerFrame = 0;

    function clearBackground() {
      if (background) background.remove();
      background = null;
      frozenLanes = [];
      headerKey = "";
      if (header) { header.replaceChildren(); header.setAttribute("hidden", ""); }
    }

    function remember() {
      registry.getAll().forEach(function (element) {
        if (!element.parent || originals.has(element.id)) return;
        originals.set(element.id, {
          x: element.x, y: element.y, width: element.width, height: element.height,
          hidden: element.hidden,
          waypoints: element.waypoints ? copyPoints(element.waypoints) : null
        });
      });
    }

    function restoreGeometry() {
      clearBackground();
      originals.forEach(function (saved, id) {
        var element = registry.get(id);
        if (!element) return;
        element.hidden = saved.hidden;
        if (saved.waypoints) element.waypoints = copyPoints(saved.waypoints);
        else {
          element.x = saved.x; element.y = saved.y;
          element.width = saved.width; element.height = saved.height;
        }
      });
    }

    function redraw() {
      events.fire("elements.changed", { elements: registry.getAll().filter(function (element) {
        return element.parent && originals.has(element.id);
      }) });
      canvas.resized();
    }

    function restore() {
      if (!originals.size) return;
      restoreGeometry();
      redraw();
    }

    function reset() {
      clearBackground();
      originals.clear();
    }

    // 展开的子流程及其内部节点、边界事件作为一个整体，保持原有包含关系。
    function ownerOf(element, nodeIds) {
      if (element.host) return ownerOf(element.host, nodeIds);
      if (element.parent && element.parent !== canvas.getRootElement() && nodeIds.has(element.parent.id)) {
        return ownerOf(element.parent, nodeIds);
      }
      return element;
    }

    function groupBounds(group) {
      var left = Infinity, right = -Infinity, top = Infinity, bottom = -Infinity;
      group.members.forEach(function (element) {
        left = Math.min(left, element.x); right = Math.max(right, element.x + element.width);
        top = Math.min(top, element.y); bottom = Math.max(bottom, element.y + element.height);
      });
      group.left = left; group.top = top; group.bottom = bottom; group.width = right - left;
    }

    function labelRatio(label, points) {
      var cx = label.x + label.width / 2, cy = label.y + label.height / 2;
      var lengths = [], total = 0;
      for (var i = 1; i < points.length; i++) {
        var length = Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
        lengths.push(length); total += length;
      }
      var nearest = Infinity, ratio = 0.5, before = 0;
      lengths.forEach(function (length, index) {
        var a = points[index], b = points[index + 1];
        var dx = b.x - a.x, dy = b.y - a.y;
        var t = length ? Math.max(0, Math.min(1, ((cx - a.x) * dx + (cy - a.y) * dy) / (length * length))) : 0;
        var distance = Math.hypot(cx - a.x - t * dx, cy - a.y - t * dy);
        if (distance < nearest) { nearest = distance; ratio = total ? (before + t * length) / total : 0.5; }
        before += length;
      });
      return ratio;
    }

    function moveConnections(elements, offsets) {
      var shapes = elements.filter(function (element) {
        return !element.hidden && !element.waypoints && !element.labelTarget && !isFrame(element) &&
          !(element.children || []).some(function (child) { return !child.labelTarget && !child.waypoints; });
      });
      var labels = [];
      elements.filter(function (element) { return element.waypoints; }).forEach(function (edge) {
        var saved = originals.get(edge.id), points = saved.waypoints;
        var sourceDx = edge.source ? offsets.get(edge.source.id) || 0 : 0;
        var targetDx = edge.target ? offsets.get(edge.target.id) || 0 : 0;
        edge.waypoints = routeConnection(points, sourceDx, targetDx, edge.source, edge.target,
          shapes.filter(function (shape) { return shape !== edge.source && shape !== edge.target; }));
        (edge.labels || []).forEach(function (label) {
          var origin = originals.get(label.id);
          if (origin && edge.waypoints.length > 1) {
            labels.push({ label: label, origin: origin, points: edge.waypoints, ratio: labelRatio(origin, points) });
          }
        });
      });
      var occupied = shapes.slice();
      labels.sort(function (a, b) { return b.origin.width * b.origin.height - a.origin.width * a.origin.height; });
      labels.forEach(function (item) {
        var position = labelPosition(item.points, item.origin.width, item.origin.height, item.ratio, occupied);
        item.label.x = position.x; item.label.y = position.y;
        occupied.push(position);
      });
    }

    function titleText(value, width, fontSize) {
      var characters = Array.from(value), used = 0, text = "";
      if (width < fontSize) return "";
      for (var i = 0; i < characters.length; i++) {
        var size = characters[i].codePointAt(0) > 255 ? fontSize : fontSize * 0.6;
        if (used + size + (i < characters.length - 1 ? fontSize : 0) > width) return text + "…";
        text += characters[i]; used += size;
      }
      return text;
    }

    function drawControls(parent, lane, index, count, width) {
      if (!onMove) return;
      var visible = width >= 84;
      var controls = svgElement("g", { "class": "b2g-lane-controls", "pointer-events": "all",
        visibility: visible ? "visible" : "hidden" }, parent);
      [-1, 1].forEach(function (direction, buttonIndex) {
        var disabled = index + direction < 0 || index + direction >= count;
        var button = svgElement("g", {
          "class": "b2g-lane-move", "data-direction": direction, role: "button",
          tabindex: disabled || !visible ? -1 : 0, "aria-disabled": String(disabled),
          "aria-label": (direction < 0 ? "向左移动泳道：" : "向右移动泳道：") + lane.value,
          transform: "translate(" + (width - 46 + buttonIndex * 22) + " 5)"
        }, controls);
        svgElement("title", {}, button).textContent = button.getAttribute("aria-label");
        svgElement("rect", { width: 20, height: 18, rx: 3,
          fill: "var(--panel, #ffffff)", stroke: "var(--border, #cbd5e1)", "stroke-width": 1 }, button);
        svgElement("text", { x: 10, y: 12, "text-anchor": "middle", "pointer-events": "none",
          fill: "var(--text, #1f2933)", "font-size": 10,
          "font-family": "Microsoft YaHei, sans-serif" }, button).textContent = direction < 0 ? "◀" : "▶";
        // 不把标题按钮的点击交给 bpmn-js，避免触发画布拖动或空白处点击。
        ["pointerdown", "mousedown", "dblclick"].forEach(function (type) {
          button.addEventListener(type, function (event) { event.stopPropagation(); });
        });
        button.addEventListener("click", function (event) {
          event.stopPropagation();
          if (!disabled) onMove(lane.value, direction);
        });
        button.addEventListener("keydown", function (event) {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault(); event.stopPropagation();
          if (!disabled) onMove(lane.value, direction);
        });
      });
    }

    function syncHeader() {
      if (!header || !frozenLanes.length) return;
      var vb = canvas.viewbox();
      // 纵向滚动不重建标题栏，保持按钮焦点，横向缩放/平移才更新位置。
      var key = JSON.stringify([vb.x, vb.scale, vb.outer.width,
        frozenLanes.map(function (lane) { return [lane.value, lane.x, lane.width]; })]);
      header.removeAttribute("hidden");
      if (key === headerKey) return;
      headerKey = key;
      header.replaceChildren();
      var defs = svgElement("defs", {}, header);
      frozenLanes.forEach(function (lane, index) {
        var x = (lane.x - vb.x) * vb.scale, width = lane.width * vb.scale;
        var clipId = "b2g-frozen-lane-clip-" + index;
        var clip = svgElement("clipPath", { id: clipId }, defs);
        svgElement("rect", { width: width, height: 28 }, clip);
        var group = svgElement("g", { "class": "b2g-frozen-lane", "data-lane-value": lane.value,
          transform: "translate(" + x + " 0)", "clip-path": "url(#" + clipId + ")" }, header);
        svgElement("title", {}, group).textContent = lane.value;
        svgElement("rect", { width: width, height: 28, fill: "var(--diagram-node-fill, #ffffff)" }, group);
        svgElement("rect", { width: width, height: 28, fill: lane.color.fill,
          "fill-opacity": "var(--lane-header-opacity, 1)", stroke: "var(--border, #cbd5e1)" }, group);
        svgElement("text", { x: 8, y: 18, fill: "var(--lane-title-color, " + lane.color.stroke + ")",
          "font-family": "Microsoft YaHei, PingFang SC, sans-serif", "font-size": 13,
          "font-weight": 600 }, group).textContent = titleText(lane.value, width - (width >= 84 && onMove ? 60 : 16), 13);
        drawControls(group, lane, index, frozenLanes.length, width);
      });
    }

    function scheduleHeader() {
      if (!header || headerFrame) return;
      headerFrame = root.requestAnimationFrame(function () { headerFrame = 0; syncHeader(); });
    }

    events.on(["canvas.viewbox.changing", "canvas.viewbox.changed", "canvas.resized"], scheduleHeader);
    if (header) header.addEventListener("wheel", function (event) {
      event.preventDefault();
      canvas.getContainer().dispatchEvent(new WheelEvent("wheel", {
        bubbles: true, cancelable: true, deltaX: event.deltaX, deltaY: event.deltaY, deltaMode: event.deltaMode,
        clientX: event.clientX, clientY: event.clientY, ctrlKey: event.ctrlKey, metaKey: event.metaKey, shiftKey: event.shiftKey
      }));
    }, { passive: false });

    function drawLanes(lanes, elements) {
      var top = Infinity, bottom = -Infinity;
      elements.forEach(function (element) {
        if (element.hidden || isFrame(element)) return;
        if (element.waypoints) element.waypoints.forEach(function (point) {
          top = Math.min(top, point.y); bottom = Math.max(bottom, point.y);
        });
        else if (Number.isFinite(element.y)) {
          top = Math.min(top, element.y); bottom = Math.max(bottom, element.y + element.height);
        }
      });
      top -= 48; bottom += 32;
      background = svgElement("g", { "class": "b2g-swimlanes", "pointer-events": "none" });
      var layer = canvas.getActiveLayer();
      layer.insertBefore(background, layer.firstChild);
      lanes.forEach(function (lane, index) {
        var group = svgElement("g", { "class": "b2g-lane", "data-lane-value": lane.value }, background);
        var title = svgElement("title", {}, group);
        title.textContent = lane.value;
        svgElement("rect", { x: lane.x, y: top, width: lane.width, height: bottom - top,
          fill: "var(--diagram-paper, #ffffff)", stroke: "var(--border, #cbd5e1)", "stroke-width": 1 }, group);
        svgElement("rect", { "class": "b2g-lane-tint", x: lane.x, y: top, width: lane.width, height: bottom - top,
          fill: lane.color.fill, "fill-opacity": "var(--lane-tint-opacity, 0.38)" }, group);
        // 场景中保留静态标题用于导出；界面使用视口顶部的固定标题层。
        var heading = svgElement("g", { "class": "b2g-lane-header" }, group);
        svgElement("rect", { x: lane.x, y: top, width: lane.width, height: 28,
          fill: "var(--diagram-node-fill, #ffffff)" }, heading);
        svgElement("rect", { x: lane.x, y: top, width: lane.width, height: 28,
          fill: lane.color.fill, "fill-opacity": "var(--lane-header-opacity, 1)",
          stroke: "var(--border, #cbd5e1)", "stroke-width": 1 }, heading);
        svgElement("text", { x: lane.x + 10, y: top + 19, fill: "var(--lane-title-color, " + lane.color.stroke + ")",
          "font-family": "Microsoft YaHei, PingFang SC, sans-serif", "font-size": 14,
          "font-weight": 600 }, heading).textContent = titleText(lane.value, lane.width - 20, 14);
      });
      frozenLanes = lanes;
      syncHeader();
      return { x: lanes[0].x, y: top, width: lanes.reduce(function (sum, lane) { return sum + lane.width; }, 0), height: bottom - top };
    }

    function apply(nodes, attr, order, colorAt) {
      remember();
      restoreGeometry();
      var rootElement = canvas.getRootElement();
      var elements = registry.getAll().filter(function (element) {
        return element.parent && canvas.findRoot(element) === rootElement;
      });
      var nodeById = new Map(nodes.map(function (node) { return [node.id, node]; }));
      var nodeIds = new Set(nodes.map(function (node) { return node.id; }));
      var groups = new Map(), membership = new Map();
      elements.forEach(function (element) {
        if (element.hidden || element.waypoints || element.labelTarget || isFrame(element)) return;
        var owner = ownerOf(element, nodeIds);
        if (!groups.has(owner.id)) groups.set(owner.id, { owner: owner, members: [], count: 0 });
        var group = groups.get(owner.id);
        group.members.push(element);
        if (nodeById.has(element.id)) group.count++;
        membership.set(element.id, group);
      });
      elements.forEach(function (element) {
        if (element.hidden || !element.labelTarget || element.labelTarget.waypoints) return;
        var group = membership.get(element.labelTarget.id);
        if (group) group.members.push(element);
      });
      if (!groups.size) { redraw(); throw new Error("当前图中没有可排列的流程节点。"); }
      var activeNodes = nodes.filter(function (node) { return membership.has(node.id); });
      var lanes = P.buildIndex(activeNodes, attr).map(function (entry, index) {
        return { value: entry.value, color: colorAt(index), groups: [], count: 0 };
      });
      var byValue = new Map(lanes.map(function (lane) { return [lane.value, lane]; }));
      groups.forEach(function (group) {
        var node = nodeById.get(group.owner.id);
        var values = node ? P.valuesOf(node, attr) : [];
        var value = values.length ? values[0] : P.UNSET;
        if (!byValue.has(value)) {
          var lane = { value: value, color: colorAt(lanes.length), groups: [], count: 0 };
          lanes.push(lane); byValue.set(value, lane);
        }
        groupBounds(group);
        byValue.get(value).groups.push(group);
        byValue.get(value).count += group.count;
      });
      var ranks = new Map((order || []).map(function (value, index) { return [value, index]; }));
      lanes.sort(function (a, b) {
        return (ranks.has(a.value) ? ranks.get(a.value) : Infinity) - (ranks.has(b.value) ? ranks.get(b.value) : Infinity);
      });
      var x = 0, offsets = new Map();
      lanes.forEach(function (lane) {
        var columns = [];
        lane.groups.sort(function (a, b) { return a.top - b.top || a.left - b.left; });
        lane.groups.forEach(function (group) {
          var column = columns.find(function (item) { return item.bottom + 16 <= group.top; });
          if (!column) { column = { width: 0, bottom: -Infinity }; columns.push(column); }
          column.width = Math.max(column.width, group.width);
          column.bottom = group.bottom;
          group.column = column;
        });
        var offset = 24;
        columns.forEach(function (column) { column.x = offset; offset += column.width + 24; });
        lane.width = Math.max(240, offset);
        lane.x = x;
        lane.groups.forEach(function (group) {
          var dx = x + group.column.x + (group.column.width - group.width) / 2 - group.left;
          group.members.forEach(function (element) {
            element.x = originals.get(element.id).x + dx;
            offsets.set(element.id, dx);
          });
        });
        x += lane.width;
      });
      moveConnections(elements, offsets);
      elements.filter(isFrame).forEach(function (element) { element.hidden = true; });
      redraw();
      var bounds = drawLanes(lanes, elements);
      canvas.resized();
      return { lanes: lanes, bounds: bounds };
    }

    return { apply: apply, restore: restore, reset: reset, syncHeader: syncHeader };
  }

  return { create: create, routeConnection: routeConnection };
});
