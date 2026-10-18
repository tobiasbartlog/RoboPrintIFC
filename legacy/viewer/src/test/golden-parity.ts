/**
 * expectGoldenParity — die eine vitest-Leseschleife der geteilten Py↔TS-Goldens
 * (ADR-009, Issue #195). Gegenstück zum Core-Manifest `fgc.parity`
 * (`core/src/fgc/parity.py`, pytest `core/tests/test_parity.py`): der Core
 * erzeugt die Goldens (`python viewer/scripts/gen_goldens.py`), hier rechnet
 * die TS-Zwillingsfunktion jeden Fall nach. Rezept: docs/paritaet.md.
 */
import { expect } from "vitest";

/** Vergleichs-Mechanik eines Paares: Ableitung gegen den gespeicherten Fall. */
export type GoldenCompare<C> = (got: unknown, c: C, label: string) => void;

/**
 * Prüft jeden Golden-Fall: `fn(fall)` gegen `compare` — Default ist
 * deep-equal zur gespeicherten `expected`-Ableitung. Leere Fall-Listen
 * schlagen fehl (fehlendes Golden bleibt sichtbar).
 */
export function expectGoldenParity<C extends object>(
  cases: readonly C[],
  fn: (c: C) => unknown,
  compare?: GoldenCompare<C>,
): void {
  expect(cases.length, "Golden ohne Fälle — gen_goldens.py laufen lassen").toBeGreaterThan(0);
  cases.forEach((c, i) => {
    const label = (c as { name?: string }).name ?? `Fall ${i}`;
    const got = fn(c);
    if (compare) compare(got, c, label);
    else expect(got, label).toEqual((c as C & { expected?: unknown }).expected);
  });
}
