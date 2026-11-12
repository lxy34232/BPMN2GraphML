const test = require("node:test");
const assert = require("node:assert/strict");
const { routeConnection } = require("../../bpmn2graphml/viewer/swimlanes.js");

function assertOrthogonal(points) {
  assert.ok(points.length >= 2);
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    assert.ok(Number.isFinite(a.x) && Number.isFinite(a.y));
    assert.notDeepEqual(a, b, "route contains a zero-length segment");
    assert.ok(a.x === b.x || a.y === b.y, `diagonal segment: ${JSON.stringify([a, b])}`);
  }
}

const source = { x: 0, y: 0, width: 100, height: 60 };

test("routes displaced vertical connections orthogonally, keeping both docking points", () => {
  const original = [{ x: 50, y: 60 }, { x: 50, y: 200 }];
  for (const [sourceDx, targetDx] of [[0, 200], [300, -120], [-300, 400], [0, 0]]) {
    const result = routeConnection(original, sourceDx, targetDx,
      { ...source, x: sourceDx }, { x: targetDx, y: 200, width: 100, height: 60 });
    assertOrthogonal(result);
    assert.deepEqual(result[0], { x: 50 + sourceDx, y: 60 });
    assert.deepEqual(result.at(-1), { x: 50 + targetDx, y: 200 });
    assert.equal(result[1].x, result[0].x);
    assert.equal(result.at(-2).x, result.at(-1).x);
  }
  assert.deepEqual(original, [{ x: 50, y: 60 }, { x: 50, y: 200 }]);
});

test("routes same-height, return and mixed-direction connections", () => {
  const cases = [
    [{ x: 100, y: 30 }, { x: 200, y: 30 }],
    [{ x: 50, y: 60 }, { x: 50, y: 100 }, { x: 250, y: 100 }, { x: 250, y: -100 }],
    [{ x: 100, y: 30 }, { x: 250, y: 30 }, { x: 250, y: 200 }],
    [{ x: 50, y: 60 }, { x: 50, y: 230 }, { x: 200, y: 230 }]
  ];
  for (const points of cases) assertOrthogonal(routeConnection(points, 200, -100, source));
});

test("routes a self-loop outside its node", () => {
  const points = [{ x: 100, y: 30 }, { x: 130, y: 30 }, { x: 130, y: -20 }, { x: 50, y: -20 }, { x: 50, y: 0 }];
  const result = routeConnection(points, 0, 0, source, source);
  assertOrthogonal(result);
  assert.ok(result[1].x > 100);
  assert.ok(result.at(-2).y < 0);
});

test("chooses an available channel around an intervening node", () => {
  const obstacle = { x: 120, y: 80, width: 80, height: 80 };
  const result = routeConnection([{ x: 50, y: 60 }, { x: 50, y: 200 }], 0, 200,
    source, { x: 200, y: 200, width: 100, height: 60 }, [obstacle]);
  assertOrthogonal(result);
  for (let i = 1; i < result.length; i++) {
    const a = result[i - 1], b = result[i];
    const crosses = a.y === b.y ? a.y > 80 && a.y < 160 && Math.max(a.x, b.x) > 120 && Math.min(a.x, b.x) < 200 :
      a.x > 120 && a.x < 200 && Math.max(a.y, b.y) > 80 && Math.min(a.y, b.y) < 160;
    assert.equal(crosses, false);
  }
});

test("handles repeated points, originally diagonal paths, and missing geometry", () => {
  assertOrthogonal(routeConnection([{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 100, y: 100 }], -10, 20));
  assert.deepEqual(routeConnection([], 0, 0), []);
  assert.deepEqual(routeConnection(null, 0, 0), []);
});
