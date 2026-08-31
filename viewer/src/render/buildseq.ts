/**
 * Monotoner Bau-Zähler der Druckort-Bühne (Issue #151-Fix), rein & three.js-frei
 * (Hausmuster #128). Jeder Bühnen-**Neubau bzw. -Teardown** zählt genau EINMAL
 * hoch (`bump`, in `clearDruckortScene`). Wer während eines Baus ein Objekt
 * **asynchron** lädt (Endeffektor-Mesh am Flansch, Workstation-Mesh), erfasst zur
 * Bauzeit den aktuellen Zähler (`current`) und behält einen `guard`: löst der
 * Ladevorgang erst nach einem neuen Bau/Teardown auf, ist der Guard ungültig und
 * das stale Objekt wird verworfen.
 *
 * Kernregel: Innerhalb EINES Baus darf **nicht** weitergezählt werden — sonst
 * entwertet ein Async-Objekt den Guard eines anderen Async-Objekts desselben
 * Baus. Genau das war der #151-Defekt: das Workstation-Mesh erhöhte den Zähler
 * im selben Bau (`++`) und verwarf so den korrekt geladenen Endeffektor am
 * Flansch. `current` liest darum nur, `bump` gehört allein an die eine
 * Neubau-/Teardown-Stelle.
 */
export class BuildSeq {
  private _current = 0;

  /** Beginn eines neuen Baus/Teardowns: Zähler +1 — entwertet alle offenen Guards. */
  bump(): void {
    this._current++;
  }

  /** Aktueller Bau-Zähler; zur Bauzeit erfassen, NICHT erhöhen. */
  get current(): number {
    return this._current;
  }

  /**
   * Guard für einen zur Bauzeit erfassten Zähler: `true`, solange kein neuer
   * `bump` (Neubau/Teardown) lief — dann gehört das geladene Objekt noch zum
   * aktuellen Bau und darf angehängt werden.
   */
  guard(seq: number): () => boolean {
    return () => seq === this._current;
  }
}
