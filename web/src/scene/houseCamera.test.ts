import { houseCamera } from './WallPreview';

describe('houseCamera', () => {
  it('blickt schräg von vorne oben auf die Mitte des Gebäudes', () => {
    const { position, target } = houseCamera([5900, 6300, 5950]);
    expect(target).toEqual([2950, 3150, 5950 / 3]);
    expect(position[0]).toBeLessThan(target[0]);
    expect(position[1]).toBeLessThan(0);
    expect(position[2]).toBeGreaterThan(5950);
  });

  it('hält bei kleinen Modellen Mindestabstand', () => {
    const { position, target } = houseCamera([100, 100, 100]);
    expect(Math.hypot(position[0] - target[0], position[1] - target[1], position[2] - target[2])).toBeGreaterThan(2500);
  });
});
