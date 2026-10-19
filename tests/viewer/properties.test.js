// 测试 bpmn2graphml/viewer/properties.js（纯逻辑）。运行：npm test
const test = require("node:test");
const assert = require("node:assert/strict");
const { DOMParser } = require("@xmldom/xmldom");
const P = require("../../bpmn2graphml/viewer/properties.js");

const BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL";
const B2G = "https://github.com/lxy34232/BPMN2GraphML/properties";
const CAMUNDA = "http://camunda.org/schema/1.0/bpmn";
const DI = "http://www.omg.org/spec/BPMN/20100524/DI";

function parse(body, extraNs = "") {
  const xml = `<bpmn2:definitions xmlns:bpmn2="${BPMN}" xmlns:b2g="${B2G}" xmlns:camunda="${CAMUNDA}" ${extraNs}>` +
    `<bpmn2:process id="P">${body}</bpmn2:process></bpmn2:definitions>`;
  return new DOMParser().parseFromString(xml, "text/xml");
}

const b2g = (pairs) =>
  `<bpmn2:extensionElements><b2g:properties>${pairs
    .map(([n, v]) => `<b2g:property name="${n}" value="${v}"/>`)
    .join("")}</b2g:properties></bpmn2:extensionElements>`;

const byId = (nodes) => Object.fromEntries(nodes.map((n) => [n.id, n]));

test("extracts b2g and camunda properties", () => {
  const nodes = byId(P.extractNodes(parse(
    `<bpmn2:manualTask id="a" name="审核">${b2g([["负责人", "张三"], ["负责人", "李四"], ["负责人", "张三"]])}</bpmn2:manualTask>` +
    `<bpmn2:userTask id="b" name="填写"><bpmn2:extensionElements><camunda:properties>` +
    `<camunda:property name="系统" value="OA"/></camunda:properties></bpmn2:extensionElements></bpmn2:userTask>`)));
  assert.deepEqual(nodes.a, { id: "a", type: "manualTask", name: "审核", props: { 负责人: ["张三", "李四"] } });
  assert.deepEqual(nodes.b.props, { 系统: ["OA"] });
});

test("extracts with default namespace", () => {
  const doc = new DOMParser().parseFromString(
    `<definitions xmlns="${BPMN}"><process id="P"><task id="t" name="T"/></process></definitions>`, "text/xml");
  assert.deepEqual(P.extractNodes(doc), [{ id: "t", type: "task", name: "T", props: {} }]);
});

test("extracts nested nodes", () => {
  const ids = P.extractNodes(parse(
    `<bpmn2:subProcess id="s" name="子"><bpmn2:task id="inner" name="内"/></bpmn2:subProcess>`)).map((n) => n.id);
  assert.deepEqual(ids.sort(), ["inner", "s"]);
});

test("ignores empty values", () => {
  const [n] = P.extractNodes(parse(
    `<bpmn2:task id="a">${b2g([["系统", ""], ["系统", "  "], ["系统", " OA "], [" ", "x"]])}</bpmn2:task>`));
  assert.deepEqual(n.props, { 系统: ["OA"] });
  assert.equal(n.name, "");
});

test("ignores sequence flows", () => {
  const ids = P.extractNodes(parse(
    `<bpmn2:task id="a"/><bpmn2:task id="b"/><bpmn2:sequenceFlow id="f" sourceRef="a" targetRef="b"/>`)).map((n) => n.id);
  assert.deepEqual(ids, ["a", "b"]);
});

test("hasDiagram", () => {
  assert.equal(P.hasDiagram(parse(`<bpmn2:task id="a"/>`)), false);
  const withDi = new DOMParser().parseFromString(
    `<bpmn2:definitions xmlns:bpmn2="${BPMN}" xmlns:bpmndi="${DI}"><bpmn2:process id="P"><bpmn2:task id="a"/></bpmn2:process>` +
    `<bpmndi:BPMNDiagram><bpmndi:BPMNPlane bpmnElement="P"><bpmndi:BPMNShape bpmnElement="a"/></bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn2:definitions>`,
    "text/xml");
  assert.equal(P.hasDiagram(withDi), true);
});

const sample = () => P.extractNodes(parse(
  `<bpmn2:task id="a">${b2g([["来源流程", "策划"], ["负责人", "张三"]])}</bpmn2:task>` +
  `<bpmn2:task id="b">${b2g([["来源流程", "申报"], ["负责人", "张三"]])}</bpmn2:task>` +
  `<bpmn2:exclusiveGateway id="c">${b2g([["来源流程", "策划"], ["来源流程", "申报"]])}</bpmn2:exclusiveGateway>`));

test("listAttributes order", () => {
  assert.deepEqual(P.listAttributes(sample()), ["元素类型", "来源流程", "负责人"]);
});

test("buildIndex counts and unset", () => {
  assert.deepEqual(P.buildIndex(sample(), "负责人"), [
    { value: "张三", ids: ["a", "b"] },
    { value: "（未设置）", ids: ["c"] },
  ]);
  assert.deepEqual(P.buildIndex(sample(), "来源流程"), [
    { value: "策划", ids: ["a", "c"] },
    { value: "申报", ids: ["b", "c"] },
  ]);
});

test("buildIndex type attr has no unset", () => {
  assert.deepEqual(P.buildIndex(sample(), "元素类型"), [
    { value: "任务", ids: ["a", "b"] },
    { value: "排他网关", ids: ["c"] },
  ]);
});

test("matchIds any-of and unset", () => {
  const nodes = sample();
  assert.deepEqual([...P.matchIds(nodes, "来源流程", ["申报"])].sort(), ["b", "c"]);
  assert.deepEqual([...P.matchIds(nodes, "负责人", ["（未设置）"])], ["c"]);
  assert.deepEqual([...P.matchIds(nodes, "负责人", ["张三", "（未设置）"])].sort(), ["a", "b", "c"]);
  assert.equal(P.matchIds(nodes, "负责人", []).size, 0);
});

test("typeLabel", () => {
  assert.equal(P.typeLabel("manualTask"), "人工任务");
  assert.equal(P.typeLabel("intermediateThrowEvent"), "中间抛出事件");
  assert.equal(P.typeLabel("fooBar"), "fooBar");
});
