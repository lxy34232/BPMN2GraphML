/*
 * 节点属性的纯逻辑：从 BPMN XML 文档提取节点及其属性、建立筛选索引、计算匹配。
 * 只使用 DOM Level 2 API，浏览器和 Node（@xmldom/xmldom）中都能运行。
 * 浏览器中挂到 window.B2GProps；Node 中通过 module.exports 导出。
 */
(function (root) {
  "use strict";

  var BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL";
  var BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI";
  var TYPE_ATTR = "元素类型";
  var UNSET = "（未设置）";
  var SOURCE_ATTR = "来源流程";

  var TYPE_LABELS = {
    task: "任务", manualTask: "人工任务", userTask: "用户任务", serviceTask: "服务任务",
    scriptTask: "脚本任务", sendTask: "发送任务", receiveTask: "接收任务",
    businessRuleTask: "业务规则任务", subProcess: "子流程", callActivity: "调用活动",
    startEvent: "开始事件", endEvent: "结束事件", intermediateThrowEvent: "中间抛出事件",
    intermediateCatchEvent: "中间捕获事件", boundaryEvent: "边界事件",
    exclusiveGateway: "排他网关", parallelGateway: "并行网关", inclusiveGateway: "包容网关",
    eventBasedGateway: "事件网关", complexGateway: "复杂网关"
  };

  function typeLabel(type) {
    return Object.prototype.hasOwnProperty.call(TYPE_LABELS, type) ? TYPE_LABELS[type] : type;
  }

  function elementChildren(el) {
    var out = [];
    for (var i = 0; i < el.childNodes.length; i++) {
      if (el.childNodes[i].nodeType === 1) out.push(el.childNodes[i]);
    }
    return out;
  }

  function walk(el, visit) {
    visit(el);
    elementChildren(el).forEach(function (c) { walk(c, visit); });
  }

  function trimmed(el, attr) {
    return (el.getAttribute(attr) || "").trim();
  }

  function readProps(el) {
    var props = {};
    elementChildren(el).forEach(function (ext) {
      if (ext.namespaceURI !== BPMN_NS || ext.localName !== "extensionElements") return;
      elementChildren(ext).forEach(function (group) {
        if (group.localName !== "properties") return;
        elementChildren(group).forEach(function (p) {
          if (p.localName !== "property") return;
          var name = trimmed(p, "name"), value = trimmed(p, "value");
          if (!name || !value) return;
          var values = props[name] || (props[name] = []);
          if (values.indexOf(value) < 0) values.push(value);
        });
      });
    });
    return props;
  }

  function extractNodes(doc) {
    var nodes = [];
    walk(doc.documentElement, function (el) {
      if (el.namespaceURI !== BPMN_NS || !TYPE_LABELS.hasOwnProperty(el.localName)) return;
      var id = el.getAttribute("id");
      if (!id) return;
      nodes.push({ id: id, type: el.localName, name: el.getAttribute("name") || "", props: readProps(el) });
    });
    return nodes;
  }

  function hasDiagram(doc) {
    var found = false;
    walk(doc.documentElement, function (el) {
      if (el.namespaceURI === BPMNDI_NS && el.localName === "BPMNShape") found = true;
    });
    return found;
  }

  function listAttributes(nodes) {
    var attrs = [TYPE_ATTR];
    nodes.forEach(function (n) {
      Object.keys(n.props).forEach(function (k) {
        if (attrs.indexOf(k) < 0) attrs.push(k);
      });
    });
    return attrs;
  }

  function valuesOf(node, attr) {
    if (attr === TYPE_ATTR) return [typeLabel(node.type)];
    return node.props[attr] || [];
  }

  function buildIndex(nodes, attr) {
    var index = [], byValue = {}, unset = [];
    nodes.forEach(function (n) {
      var values = valuesOf(n, attr);
      if (!values.length) unset.push(n.id);
      values.forEach(function (v) {
        if (!byValue[v]) {
          byValue[v] = { value: v, ids: [] };
          index.push(byValue[v]);
        }
        byValue[v].ids.push(n.id);
      });
    });
    if (unset.length) index.push({ value: UNSET, ids: unset });
    return index;
  }

  function matchIds(nodes, attr, selected) {
    var ids = new Set();
    if (!selected.length) return ids;
    var wantUnset = selected.indexOf(UNSET) >= 0;
    nodes.forEach(function (n) {
      var values = valuesOf(n, attr);
      var hit = values.some(function (v) { return selected.indexOf(v) >= 0; }) ||
        (wantUnset && values.length === 0);
      if (hit) ids.add(n.id);
    });
    return ids;
  }

  var api = {
    TYPE_ATTR: TYPE_ATTR, UNSET: UNSET, SOURCE_ATTR: SOURCE_ATTR,
    typeLabel: typeLabel, extractNodes: extractNodes, hasDiagram: hasDiagram,
    listAttributes: listAttributes, valuesOf: valuesOf, buildIndex: buildIndex, matchIds: matchIds
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.B2GProps = api;
})(this);
