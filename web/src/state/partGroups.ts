/**
 * Module gleicher Geometrie zusammenfassen. Der Kern nennt für jede Kopie ihren Repräsentanten in
 * `summary.parts[].same_as` (gleiche Geometrie und Platzierung, also dieselbe Bahn und dieselbe
 * Prüfung). Eine Gruppe ist der Repräsentant mit seinen Kopien.
 */

export interface PartRef {
  part_id: string;
  /** Fehlt in älteren Läufen; dann ist jedes Teil sein eigener Repräsentant. */
  same_as?: string | null;
}

export interface PartGroup<P extends PartRef = PartRef> {
  /** Wird simuliert und geprüft; seine Ergebnisse gelten für jede Kopie. */
  rep: P;
  /** Alle Module der Gruppe, der Repräsentant zuerst, dann die Kopien in Laufreihenfolge. */
  members: P[];
}

/**
 * Gruppen in der Laufreihenfolge der Repräsentanten. Eine Kopie, deren `same_as` auf keinen
 * Repräsentanten zeigt, bildet dahinter eine eigene Gruppe, damit kein Modul verschwindet.
 */
export function groupParts<P extends PartRef>(parts: readonly P[]): PartGroup<P>[] {
  const groups = new Map<string, PartGroup<P>>();
  for (const p of parts) if (!p.same_as) groups.set(p.part_id, { rep: p, members: [p] });
  for (const p of parts) {
    if (!p.same_as) continue;
    const g = groups.get(p.same_as);
    if (g) g.members.push(p);
    else groups.set(p.part_id, { rep: p, members: [p] });
  }
  return [...groups.values()];
}

/** Gruppe, zu der das Teil gehört; null, wenn es in keiner vorkommt. */
export function groupOf<P extends PartRef>(groups: readonly PartGroup<P>[], partId: string | null): PartGroup<P> | null {
  if (partId === null) return null;
  return groups.find((g) => g.members.some((m) => m.part_id === partId)) ?? null;
}
