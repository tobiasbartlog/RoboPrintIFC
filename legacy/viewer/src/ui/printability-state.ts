/**
 * Druckbarkeits-Urteil → Anzeige (Issue #164, Karte #139 / Entscheidung #141).
 *
 * Reine Ableitung (DOM-frei, ADR-007): der Viewer rechnet nichts, er formatiert
 * nur das vom Core gelieferte {@link PartPrintability} je Teil zur Anzeige an der
 * Teile-Palette. Der Core hat Freigang (#163) + repräsentative Prüf-Tür (#162)
 * bereits zu **einem** Urteil verheiratet — hier wird es nur ehrlich sichtbar.
 *
 * **Ehrlichkeit ist der Kern (Issue #164):**
 * - **Grün** (`severity: "ok"`) **nur** aus `verdict === "printable"` — das ist,
 *   was die Prüf-Tür wirklich frei gesehen hat. Ein stummer Freigang-Befund wird
 *   nie grün (S6-Lehre); `too_thick` ist rot, nicht grün.
 * - **`presumed`** (,vermutlich') markiert ein **geerbtes** Reihen-Urteil: die
 *   ungünstigste Zelle der Höhenreihe wurde geprüft, dieses Teil erbt — es darf
 *   nicht wie ein geprüftes Urteil aussehen (eigener Text + hohles Symbol im DOM).
 *
 * **Ungeprüft ist sichtbar (Issue #170):** ein `unknown`-Urteil liefert **nicht**
 * mehr `null`, sondern eine eigene Ansicht (`severity: "unknown"`, Label
 * „ungeprüft") — unterscheidbar von grün/rot/„vermutlich" — und nennt im Titel den
 * Grund (`no_geometry` = Prüf-Tür unzuständig / `error` = Prüfung fehlgeschlagen).
 * Nur ein **fehlendes** Urteil (`null`/`undefined` — Altlauf vor #164) liefert `null`;
 * der Aufrufer zeigt es ebenfalls als „ungeprüft" (nie die alte Erreichbarkeits-Ampel).
 *
 * **Ampel-Konjunktion (Issue #180, Befund B33):** die Druckbarkeit ERSETZT das
 * Erreichbarkeits-Urteil nicht mehr, sie **kombiniert** beide Kanäle. Ein Teil wird
 * **nur** grün, wenn die Prüf-Tür es frei sah (`verdict === "printable"`) **und** es
 * voll erreichbar ist (`reachable !== false`). Ein kollisionsfreies, aber nur teilweise
 * erreichbares Teil (`verdict === "printable"`, `reachable === false`) ist **nicht** grün,
 * sondern rot („kollisionsfrei, aber teilweise unerreichbar") — Unerreichbarkeit erzeugt
 * nie „printable". Beide Kanäle bleiben ablesbar (der Prüf-Tür-Kanal im Text, die
 * Erreichbarkeit zusätzlich in der „erreichbar N %"-Zeile der Palette). Fehlt der
 * `reachable`-Kanal (voll erreichbar / Altlauf vor #180), ist die Konjunktion ein
 * No-op — das Teil gilt als erreichbar (Altverhalten #164).
 *
 * **Prüf-Vorbehalte durchreichen (Issue #182, Befunde B15/B37/B38):** ein Tür-„frei"
 * sieht nicht mehr stärker aus, als es ist — die Ehrlichkeits-Metadaten der Prüf-Tür
 * (Travel ausgedünnt geprüft, n geprüft von m Samples, Endeffektor-Hülle provisorisch)
 * hängen additiv am Tooltip von `printable`/`collides` (`printabilityCaveats`),
 * konsistent zum Kollisionsbefund im Player (`collisionCaveats`, Issue #156).
 *
 * **Befund, kein Gate** (ADR-013): das Urteil blockiert nichts.
 */
import type { PartPrintability } from "../api/projects";

/** Schweregrad des Urteils für die Ampel: grün / rot / ungeprüft (kein/kaputtes Urteil). */
export type PrintSeverity = "ok" | "bad" | "unknown";

/** Aufbereitetes Druckbarkeits-Urteil für die Anzeige (reine Daten, kein DOM). */
export interface PrintabilityView {
  /** ok = druckbar (grün), bad = kollidiert/zu dick (rot), unknown = kein Urteil. */
  severity: PrintSeverity;
  /** true = geerbtes Reihen-Urteil (,vermutlich') — visuell zu unterscheiden. */
  presumed: boolean;
  /** Kurztext für die Karte („frei", „kollidiert · Glied 4 · 206 mm tief", „zu dick · 176 mm"). */
  label: string;
  /** Ausführlicher Tooltip (Herkunft des Urteils, Vererbung, Befund kein Gate). */
  title: string;
}

/** Ganze Millimeter, deutsches Format. */
function mm(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value)} mm`;
}

/** Ganze Prozent des erreichbaren Anteils (Issue #180) — „N %" oder leer. */
function reachPct(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : ` (${Math.round(value * 100)} %)`;
}

/** Benennt das verursachende Glied menschenlesbar (Index; TOOL_INDEX = Endeffektor). */
function causerLabel(p: PartPrintability): string {
  if (p.causer_link === null || p.causer_link === undefined) return "";
  return ` · Glied ${p.causer_link}`;
}

/**
 * Prüf-Vorbehalte eines echten Prüf-Tür-Urteils (Issue #182, Befunde B15/B37/B38):
 * dieselben Ehrlichkeits-Metadaten, mit denen die Travel-Ausdünnung der Prüf-Tür
 * intern gerechtfertigt wird (Travel „nicht lückenlos geprüft"), gehen additiv in
 * die Anzeige ein — ein Tür-„frei" sieht nicht mehr stärker aus, als es ist.
 * Konsistent zum Kollisionsbefund im Player (`collisionCaveats`, Issue #156):
 * dieselbe Wortwahl für denselben Sachverhalt. Leere Liste, wenn keiner der
 * Vorbehalte gilt (`too_thick`/Altlauf — kein Prüf-Tür-Urteil, keine Vorbehalte).
 */
export function printabilityCaveats(p: PartPrintability): string[] {
  const out: string[] = [];
  if (p.travel_thinned) out.push("Travel nicht lückenlos geprüft");
  if (p.n_checked != null && p.n_samples != null && p.n_checked < p.n_samples) {
    out.push(`${p.n_checked} von ${p.n_samples} Samples geprüft`);
  }
  if (p.tool_provisional) out.push("Endeffektor-Hülle provisorisch");
  return out;
}

/** Vorbehalte als Titel-Anhang („ — Vorbehalt, Vorbehalt") oder leer. */
function caveatSuffix(p: PartPrintability): string {
  const caveats = printabilityCaveats(p);
  return caveats.length ? ` (${caveats.join(", ")})` : "";
}

/** Titel-Zusatz je Grund eines ,ungeprüft'-Urteils (Issue #170). */
function ungeprueftTitle(reason: PartPrintability["reason"]): string {
  if (reason === "error") {
    return (
      "Ungeprüft: die Kollisions-Prüf-Tür ist fehlgeschlagen (Fehler, protokolliert) — " +
      "dieses Teil wurde NICHT geprüft. Kein ‚frei‘, kein ‚kollidiert‘. Befund, kein Gate."
    );
  }
  if (reason === "no_geometry") {
    return (
      "Ungeprüft: keine Kollisions-Geometrie vorhanden (Altprojekt/Roboter ohne " +
      "Prüf-Geometrie) — die Prüf-Tür war unzuständig. Kein ‚frei‘. Befund, kein Gate."
    );
  }
  if (reason === "unreachable") {
    return (
      "Ungeprüft: keine erreichbare Zelle in dieser Höhenreihe — es gibt keinen " +
      "Repräsentanten, dessen Prüfung physikalisch sinnvoll wäre (eine unerreichbare " +
      "Pose läge eingefroren). Die Reihe erbt kein ‚frei‘. Befund, kein Gate."
    );
  }
  if (reason === "unchecked") {
    return (
      "Ungeprüft: die (teure) Kollisions-Prüf-Tür wurde für dieses Teil noch nicht " +
      "angestoßen — sie läuft nur auf ausdrücklichen Anstoß (‚Fokus prüfen‘ / " +
      "‚Ganze Wand prüfen‘), damit ein Schnitt-Edit den Editor nicht blockiert. " +
      "Kein ‚frei‘, kein ‚kollidiert‘. Befund, kein Gate."
    );
  }
  return (
    "Ungeprüft: für dieses Teil liegt (noch) kein Druckbarkeits-Urteil vor. " +
    "Kein ‚frei‘, kein ‚kollidiert‘ — stoße die Prüf-Tür an, um es zu prüfen. Befund, kein Gate."
  );
}

/**
 * Bereitet das Druckbarkeits-Urteil eines Teils auf. Ein `unknown`-Urteil liefert
 * eine eigene „ungeprüft"-Ansicht (`severity: "unknown"`, Issue #170) mit dem Grund
 * im Titel; nur ein **fehlendes** Urteil (`null`/`undefined` — Altlauf) liefert `null`
 * (der Aufrufer zeigt es dann ebenfalls als „ungeprüft"). Reine Funktion, deterministisch.
 */
export function printabilityView(
  p: PartPrintability | null | undefined,
): PrintabilityView | null {
  if (!p) return null;
  if (p.verdict === "unknown") {
    return {
      severity: "unknown",
      presumed: false,
      label: "ungeprüft",
      title: ungeprueftTitle(p.reason),
    };
  }
  const prefix = p.presumed ? "vermutlich " : "";
  switch (p.verdict) {
    case "printable":
      // Ampel-Konjunktion (Issue #180, B33): grün NUR bei Prüf-Tür-frei UND voller
      // Erreichbarkeit. Ein kollisionsfrei geprüftes, aber nur teilweise erreichbares
      // Teil (`reachable === false`) wird NICHT grün, sondern rot — Unerreichbarkeit
      // darf ein hartes rotes Reichweiten-Urteil nicht zu „druckbar" überstimmen.
      // Beide Kanäle bleiben ablesbar (kollisionsfrei + teilweise unerreichbar).
      if (p.reachable === false) {
        return {
          severity: "bad",
          presumed: p.presumed,
          label: `${prefix}kollisionsfrei, aber teilweise unerreichbar${reachPct(p.reachable_fraction)}`,
          title:
            "Nicht druckbar (Erreichbarkeit): die Prüf-Tür hat dieses Teil zwar " +
            "kollisionsfrei gesehen, aber es ist nur teilweise erreichbar" +
            `${reachPct(p.reachable_fraction)} — grün wird ein Teil nur bei ` +
            "Kollisionsfreiheit UND voller Erreichbarkeit (Issue #180). Beide Befunde " +
            `bleiben sichtbar. Befund, kein Gate.${caveatSuffix(p)}`,
        };
      }
      return {
        severity: "ok",
        presumed: p.presumed,
        label: `${prefix}frei`,
        title:
          (p.presumed
            ? "Vermutlich druckbar: die ungünstigste Zelle dieser Reihe wurde von der " +
              "Prüf-Tür frei gesehen, dieses Teil erbt das Urteil (nicht selbst geprüft)."
            : "Druckbar: die Prüf-Tür hat dieses Teil kollisionsfrei gesehen. Befund, kein Gate.") +
          caveatSuffix(p),
      };
    case "collides":
      return {
        severity: "bad",
        presumed: p.presumed,
        // „tief" benennt die Größe (Issue #238): die Zahl ist die EINDRINGTIEFE des
        // Verursacher-Glieds, keine Kollisions- oder Schnitthöhe — ohne das Wort
        // wurde sie im Denkmal-Projekt als Höhe gelesen („bei 486 mm schneiden").
        label: `${prefix}kollidiert${causerLabel(p)} · ${mm(p.penetration_mm)} tief`,
        title:
          (p.presumed
            ? "Vermutlich Kollision: die ungünstigste Zelle dieser Reihe kollidiert " +
              `(Glied ${p.causer_link}, Eindringtiefe ${mm(p.penetration_mm)}), dieses Teil ` +
              "erbt das Urteil (nicht selbst geprüft). Befund, kein Gate."
            : "Kollision: die Prüf-Tür hat dieses Teil kollidieren gesehen " +
              `(Glied ${p.causer_link}, Eindringtiefe ${mm(p.penetration_mm)}). Befund, kein Gate.`) +
          caveatSuffix(p),
      };
    case "too_thick": {
      // „vermutlich zu dick" (Issue #177, Befunde B7/B9): das Freigang-Kriterium ist
      // höhenblind (kennt weder Wandhöhe noch Aufstellung) und kann für eine niedrige,
      // dicke Wand irren — solange die Wandhöhen-Wache #167 fehlt, ist „zu dick" nie eine
      // geprüfte Gewissheit. `presumed` ist deshalb `true` (Core), die falsifizierende
      // Prüf-Tür entfiel bewusst (Überspringen als „vermutlich, ungeprüft" ausgewiesen).
      const tcpNote = p.tcp_provisional ? " · TCP vorläufig" : "";
      return {
        severity: "bad",
        presumed: p.presumed,
        label: `${prefix}zu dick · ${mm(p.excess_mm)}${tcpNote}`,
        title:
          "Vermutlich zu dick für einseitigen Druck (Freigang-Kriterium): der Überschuss " +
          `beträgt ${mm(p.excess_mm)}. Das Urteil ist HÖHENBLIND — es kennt weder Wandhöhe ` +
          "noch Aufstellung und kann für eine niedrige, dicke Wand irren; die Wandhöhen-Wache " +
          "(#167) prüft das erst. Keine geprüfte Gewissheit; die teure Kollisions-Prüfung " +
          "entfiel bewusst (vermutlich, ungeprüft)." +
          (p.tcp_provisional
            ? " Zusätzlich vorläufig: die druckbare Tiefe wurde aus einem geschätzten, noch " +
              "nicht vermessenen Werkzeug-TCP gerechnet (#136)."
            : "") +
          " Befund, kein Gate.",
      };
    }
    case "too_tall": {
      // „vermutlich zu hoch" (Issue #209, zweite Stufe-1-Schranke, Gl. 9 Stamatopoulos):
      // die Teilhöhe übersteigt die druckbare Höhe H_max für die freie Länge. Wie
      // `too_thick` rot, aber `presumed` (Core setzt presumed=true) — die Schranke ist
      // PLATZIERUNGSBLIND (kennt weder Standplatz noch das schichtweise Umsetzen); die
      // teure Prüf-Tür entfiel bewusst. Überschuss doppelt: Höhe (mm) UND Winkel (Grad).
      const degNote =
        p.excess_deg === null || p.excess_deg === undefined
          ? ""
          : ` · ${Math.round(p.excess_deg)}°`;
      const tcpNoteTall = p.tcp_provisional ? " · TCP vorläufig" : "";
      return {
        severity: "bad",
        presumed: p.presumed,
        label: `${prefix}zu hoch · ${mm(p.excess_mm)}${degNote}${tcpNoteTall}`,
        title:
          "Vermutlich zu hoch für die freie Länge unter dem Handgelenk (zweite Stufe-1-" +
          `Schranke, Gl. 9): der Überschuss beträgt ${mm(p.excess_mm)}` +
          (p.excess_deg === null || p.excess_deg === undefined
            ? ""
            : ` (${Math.round(p.excess_deg)}° über der druckbaren Neigung)`) +
          ". Das Urteil ist PLATZIERUNGSBLIND — es kennt weder Standplatz noch das " +
          "schichtweise Umsetzen des Roboters und kann irren. Keine geprüfte Gewissheit; " +
          "die teure Kollisions-Prüfung entfiel bewusst (vermutlich, ungeprüft)." +
          (p.tcp_provisional
            ? " Zusätzlich vorläufig: die freie Länge wurde aus einem geschätzten, noch " +
              "nicht vermessenen Werkzeug-TCP gerechnet (#136)."
            : "") +
          " Befund, kein Gate.",
      };
    }
    default:
      return null;
  }
}

/**
 * Aggregierter, ehrlicher Palette-Zähler aus den Urteilen (Issue #164/#170).
 *
 * **Der Nenner sind ALLE Teile** (Issue #170, B34): ungeprüfte Teile (`null` =
 * Altlauf/dirty, oder `severity: "unknown"` = kein Urteil/Prüffehler) verschwinden
 * **nicht** aus dem Zähler, sondern werden **ausgewiesen** („4 druckbar · 12
 * ungeprüft"). So sieht ein Lauf mit fehlgeschlagener Prüfung **nie** wie „alles
 * geprüft" aus. Nur wenn wirklich **jedes** Teil geprüft-frei ist, steht das
 * beruhigende „N/N druckbar ✓" (grün). ,Vermutlich'-frei zählt **nicht** als
 * geprüftes ✓ (Ehrlichkeit — das lügende „16/16 ✓" fällt). Liefert `null` nur bei
 * **leerer** Palette (kein Teil).
 */
export interface PrintabilityCounter {
  label: string;
  cssClass: "badge-ok" | "badge-warn";
  show: boolean;
}

export function printabilityCounter(
  views: readonly (PrintabilityView | null)[],
): PrintabilityCounter | null {
  const total = views.length;
  if (total === 0) return null; // leere Palette ⇒ kein Zähler

  const isUnchecked = (v: PrintabilityView | null): boolean =>
    v === null || v.severity === "unknown";
  const unchecked = views.filter(isUnchecked).length;
  const checkedFree = views.filter(
    (v) => v !== null && v.severity === "ok" && !v.presumed,
  ).length;
  const bad = views.filter((v) => v !== null && v.severity === "bad").length;

  // Alles geprüft (kein ungeprüftes Teil): das gewohnte #164-Bild.
  if (unchecked === 0) {
    const label =
      bad > 0 ? `${bad}/${total} nicht druckbar` : `${checkedFree}/${total} druckbar ✓`;
    return {
      label,
      cssClass: bad === 0 && checkedFree === total ? "badge-ok" : "badge-warn",
      show: true,
    };
  }

  // Ungeprüfte im Nenner ausweisen (B34/B35) — nie „alles geprüft".
  const segments: string[] = [];
  if (checkedFree > 0) segments.push(`${checkedFree} druckbar`);
  if (bad > 0) segments.push(`${bad} nicht druckbar`);
  segments.push(`${unchecked} ungeprüft`);
  return { label: segments.join(" · "), cssClass: "badge-warn", show: true };
}
