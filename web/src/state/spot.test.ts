import { describeSpot, distanceBeforeRobot, moveSpot, snapSpot, spotGrid } from './spot';

describe('Rastfeld des Druckplatzes', () => {
  it('reicht von der Tischmitte 250 mm nach vorn und 200 mm zu jeder Seite, nie zum Roboter hin', () => {
    const grid = spotGrid();
    expect(grid).toHaveLength(9 * 6);
    expect(Math.max(...grid.map((s) => s.y))).toBe(0);
    expect(Math.min(...grid.map((s) => s.y))).toBe(-250);
    expect(new Set(grid.map((s) => s.x))).toEqual(new Set([-200, -150, -100, -50, 0, 50, 100, 150, 200]));
    expect(grid).toContainEqual({ x: 0, y: -50 });
  });

  it('rastet auf den nächsten Punkt ein und bleibt am Rand', () => {
    expect(snapSpot(12, -74)).toEqual({ x: 0, y: -50 });
    expect(snapSpot(-26, -76)).toEqual({ x: -50, y: -100 });
    expect(snapSpot(900, 400)).toEqual({ x: 200, y: 0 });
    expect(snapSpot(-900, -900)).toEqual({ x: -200, y: -250 });
    expect(Object.is(snapSpot(-10, -10).x, 0)).toBe(true); // keine −0 im Parameter
  });

  it('verschiebt in Rastungen, Pfeil hoch heißt zum Roboter', () => {
    expect(moveSpot({ x: 0, y: -50 }, 1, 0)).toEqual({ x: 50, y: -50 });
    expect(moveSpot({ x: 0, y: -50 }, 0, 1)).toEqual({ x: 0, y: 0 });
    expect(moveSpot({ x: 0, y: 0 }, 0, 1)).toEqual({ x: 0, y: 0 });
  });

  it('beschreibt die Lage vom Bediener vor dem Tisch aus', () => {
    expect(describeSpot({ x: 0, y: -50 })).toBe('50 mm vor der Tischmitte, mittig');
    expect(describeSpot({ x: 200, y: 0 })).toBe('Tischmitte, 200 mm rechts');
    expect(describeSpot({ x: -150, y: -250 })).toBe('250 mm vor der Tischmitte, 150 mm links');
    expect(distanceBeforeRobot({ x: 0, y: -50 })).toBe(535);
  });
});
