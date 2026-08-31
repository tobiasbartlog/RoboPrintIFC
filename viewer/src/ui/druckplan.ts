/**
 * Reiter Druckplan (Issue #22/#23/#24, Schnittplan-Editing #25, Aufstell-Toggle #81).
 *
 * Aufstellung = ein **Toggle** (Issue #81, PRD B/#70): „Roboter steht auf dem
 * Boden“ (`floor`) vs. „darf auch erhöht stehen“ (`elevated`) — er ersetzt die
 * frühere manuelle Aufstell-Liste. Umschalten persistiert über die Core-Route
 * (`PUT /projects/{slug}/stand-mode`) und stößt die Neubewertung an: der Core
 * leitet aus dem Toggle den erlaubten Podesthöhen-Satz und damit die Höhenteilung
 * der Zerlegung ab (`floor` → mehr Höhenbänder). Die Platzierung rechnet der
 * Core **je Abschnitt** automatisch (zentral, beste Podesthöhe, optimierter
 * Abstand — #80/#132); der frühere Gesamtwand-Platzierungsvorschlag (#22/#23,
 * „vorschlag-1/2/3" + Wahl) ist mit Issue #134 entfallen — er hatte nach der
 * Zerlegung keinen Konsumenten mehr. Alles hier ist ein **Plan**, kein
 * Setup (ADR-006): verbindlich wird die Basis-Lage erst durchs Antasten.
 *
 * Schnittplan-Editing (Issue #25): der Zerlegungsvorschlag (Issue #24) wird
 * anpassbar — Schnitte hinzufügen/verschieben/entfernen, Fugen-Versatz, je
 * Abschnitt die Platzierung übersteuern. Die Zustandslogik dafür (Schnitte,
 * Dirty-Flag) liegt in `ui/cutplan-state.ts` (reine Funktionen, ohne three.js);
 * dieses Panel ruft sie nur auf und rendert das Ergebnis. Jede Änderung markiert
 * den Plan als „ungeprüft" (dirty); erst eine erfolgreiche Neubewertung durch
 * den Core (Button „Prüfen", debounced nach jeder Änderung) zeigt wieder eine
 * scharfe Ampel — die UI rechnet nie selbst (ADR-007). Drag (three.js,
 * `main.ts`/`render/cutplanes.ts`) und das Zahlenfeld hier rufen beide
 * `setCutPosition` auf denselben Zustand — daher bleiben sie synchron.
 *
 * Der Panel hält nur Formularzustand; Fachzustand liegt im project.json und im
 * Zerlegungslauf (decompose.json) auf der Platte (ADR-007/016).
 */

import { type StandMode, normalizeStandMode } from "./aufstell-state";
import { normalizeContextCheck } from "./kontext-state";
import {
  type CollapsibleState,
  collapsibleState,
  collapsibleView,
  toggleCollapsible,
} from "./collapsible-state";
import {
  addCut,
  applyEvaluation,
  type CutPlanState,
  initCutPlanState,
  markUnchecked,
  moveCut,
  overrideFor,
  removeCut,
  replaceSectionOverrides,
  setJointOffset,
  setSectionOverride,
} from "./cutplan-state";
import type { FocusStore } from "./focus-store";
import type { CollisionMeta } from "../artifacts/types";
import { PartsPalette } from "./parts-palette";
import { paletteEntries } from "./parts-palette-state";
import {
  normalizeZerlegungsart,
  switchArt,
  visibilityFor,
  workstationHint,
  type Zerlegungsart,
} from "./zerlegungsart-state";
import { headStatus, paletteCounter } from "./zerlegung-status";
import { freigangBannerView } from "./freigang-state";
import { printabilityCounter } from "./printability-state";
import {
  checkProgressView,
  lastCheckView,
  scopeAnnouncement,
} from "./pruef-check-state";
import {
  beamProgressView,
  beamSummary,
  relaxAusweis,
  verworfenRows,
} from "./refinement-state";
import {
  placementFeasibilityHint,
  placementSuggestionRows,
} from "./placement-suggestion-state";
import type { Revisions } from "./staleness";
import type {
  BeamProposeStatus,
  Cut,
  DecompositionCheckStatus,
  DecompositionRefinement,
  DecompositionSection,
  FreigangFinding,
  LastPruef,
  PlacementOption,
  PlacementSuggestionResult,
  PruefScope,
  SectionOverride,
} from "../api/projects";

/** Debounce-Verzögerung (ms) zwischen einer Schnittplan-Änderung und der
 *  automatischen Neubewertung ("Prüfen") — Bedienmuster aus PRD #15. */
const CHECK_DEBOUNCE_MS = 700;

export interface DruckplanPanelCallbacks {
  /**
   * Aufstell-Toggle umgeschaltet (Issue #81): den neuen Zustand über die Core-
   * Route persistieren (`PUT /projects/{slug}/stand-mode`) und die Neubewertung
   * anstoßen — der Core leitet aus dem Toggle den Podesthöhen-Satz und damit die
   * Höhenteilung ab (ADR-007). Gibt die frische Zerlegung zurück (wie
   * `onDecompose`), damit das Panel Schnitte + Ampeln neu zeichnet; `null`, wenn
   * (noch) keine Neubewertung möglich war.
   */
  onStandModeChange(
    mode: StandMode,
  ): Promise<{
    cuts: Cut[];
    sections: DecompositionSection[];
    freigang?: FreigangFinding | null;
  } | null>;
  /**
   * Gebäudekontext-Schalter umgeschaltet (Issue #131): den neuen Zustand über die
   * Core-Route `PUT /projects/{slug}/context-check` persistieren. Kein Rückgabewert —
   * der Schalter ändert keinen Zerlegungsplan, er wirkt erst bei der nächsten
   * Simulation (bei „ein" prüft der Befund zusätzlich gegen den Gebäudekontext).
   */
  onContextCheckChange?(enabled: boolean): Promise<void>;
  /** „Zerlegungsvorschlag" geklickt (Issue #24): Core schlägt eine frische
   *  Zerlegung in Abschnitte vor (verwirft einen laufenden Schnittplan-Entwurf) —
   *  Startpunkt fürs Editieren (Issue #25). */
  onDecompose(kind: "abschnitt" | "modul"): Promise<{
    cuts: Cut[];
    sections: DecompositionSection[];
    freigang?: FreigangFinding | null;
  }>;
  /**
   * Schnittplan neu bewerten („Prüfen", Issue #25) — der Core baut aus den
   * Plan-Eingaben (Schnitte, Fugen-Versatz, Overrides) die Abschnittsgeometrie
   * und die Ampel (`fgc.decompose.from_cuts` + `evaluate`). Wird nach jeder
   * Änderung debounced automatisch aufgerufen, zusätzlich per Button.
   */
  onCheckCutPlan(
    kind: "abschnitt" | "modul",
    cuts: Cut[],
    jointOffsetMm: number,
    sectionOverrides: SectionOverride[],
  ): Promise<{
    cuts: Cut[];
    jointOffsetMm: number;
    sections: DecompositionSection[];
    freigang?: FreigangFinding | null;
  }>;
  /** Feuert synchron bei jeder Schnitt-Änderung (add/remove/move) — für die
   *  sofortige 3D-Darstellung (Darstellungsmathematik, kein Core-Aufruf). */
  onCutsChanged(cuts: Cut[]): void;
  /**
   * Feuert NUR, wenn eine Prüf-Antwort tatsächlich übernommen wurde (nicht bei
   * verworfenen stale Antworten, Issue #45): main.ts wendet erst hier die
   * Nebenwirkungen an (Abschnitte an Simulation/Export, Revisionsstände).
   */
  onCheckApplied?(): void;
  /**
   * Zerlegungsart umgeschaltet (Issue #95, ADR-022). Reine **Meldung** an
   * main.ts — die eigentliche Persistenz (Zerlegungsart + geräumte
   * Platzierungs-Overrides) läuft über die anschließende Neubewertung
   * (`onCheckCutPlan`) durch die eine Schreibstelle `fgc.project` (ADR-016).
   * Optional; main.ts kann darauf 3D-Beschriftungen o. Ä. nachziehen.
   */
  onArtChanged?(art: Zerlegungsart): void;
  /**
   * Optionale Modul-Obergrenzen geändert (Issue #90/#95): über die #90-Route
   * `PUT …/module-limits` persistieren (einzige Schreibstelle, ADR-016).
   * `null` je Grenze = keine Obergrenze. Kein Rückgabewert nötig — die
   * Neubewertung (Gewicht/Grenzen-Befund je Teil) stößt das Panel debounced an.
   */
  onModuleLimitsChange?(maxLengthMm: number | null, maxHeightMm: number | null): Promise<void>;
  /**
   * Stufe-2-Prüf-Tür anstoßen (Issue #175): die teure Druckbarkeitsprüfung läuft als
   * Hintergrundlauf (nicht im interaktiven Loop, Befund B14). `scope` = `"focus"` (nur
   * die Höhenreihe des Fokus-Teils, Default-Wahl) oder `"global"` (ganze Wand, teure
   * Wahl); `focusSectionId` = das Fokus-Teil bei `"focus"`. main.ts startet den Lauf,
   * poll't ihn und meldet den Fortschritt über `setCheckStatus` zurück; bei `done`
   * übernimmt es die frischen Abschnitte (wie `onCheckApplied`).
   */
  onStartPruef?(scope: "focus" | "global", focusSectionId: string | null): void;
  /** Laufenden Hintergrund-Prüflauf abbrechen (Issue #175, AC-Zusatz). */
  onCancelPruef?(): void;
  /**
   * Beam-Zerlegungslauf anstoßen (Issue #221, Folge #217): die kollisionsgetriebene
   * Beam-Suche (PRD #183 Stufe 3) läuft als Hintergrundlauf (sie kostet Prüf-Tür-
   * Aufrufe). main.ts startet den Lauf, poll't ihn und meldet den Fortschritt über
   * `setBeamStatus` zurück; bei `done` übernimmt es den Sieger-Schnittplan (wie
   * `onCheckApplied`) und speist den Such-Ausweis über `setRefinement`.
   */
  onStartBeam?(): void;
  /** Laufenden Beam-Zerlegungslauf abbrechen (Issue #221). */
  onCancelBeam?(): void;
  /**
   * „Kollisions-Ampel prüfen" geklickt (Issue #231, ADR-026 Punkt 2): fragt den
   * bestehenden Optimalvorschlag (POST …/placement-suggestion, Issue #23/#80)
   * rein lesend ab. Der Core liefert je Kandidat die fertig gerechnete
   * Kollisions-Einstufung (`score.collision`, Issue #228) und den Gesamt-Befund
   * `feasibility` — das Panel wendet nichts an (keine Auswahl/Persistenz).
   */
  onCheckPlacementSuggestion?(): Promise<PlacementSuggestionResult>;
}

export class DruckplanPanel {
  private readonly floorRadio = byId<HTMLInputElement>("aufstell-floor");
  private readonly elevatedRadio = byId<HTMLInputElement>("aufstell-elevated");
  private readonly aufstellStatus = byId<HTMLParagraphElement>("aufstell-status");
  // Gebäudekontext-Schalter der Kollisionskontrolle (Issue #131): eigene Gruppe im
  // Accordion „Art & Aufstellung", wie die Aufstell-Gruppe nur bei Abschnitt sichtbar
  // (bei Modul gegenstandslos, ADR-022).
  private readonly kontextGroup = byId<HTMLElement>("kontext-group");
  private readonly kontextCheckBox = byId<HTMLInputElement>("kontext-check");
  private readonly kontextStatus = byId<HTMLParagraphElement>("kontext-status");
  // Primärbutton (Issue #106/#134): „✦ Automatisch vorschlagen" löst den
  // Zerlegungsvorschlag (#24) aus — die Abschnitts-Platzierungen sucht der Core
  // dabei je Teil automatisch (#80/#132); der frühere Gesamtwand-
  // Optimalvorschlag (#23) ist entfallen (Issue #134).
  private readonly autoBtn = byId<HTMLButtonElement>("zerlegung-auto-btn");
  private readonly apiWarning = byId<HTMLElement>("placement-api-warning");
  private readonly precondition = byId<HTMLElement>("placement-precondition");
  // Kopf-/Palette-Status (Issue #106): „ungeprüft" (amber) ↔ „geprüft ✓" (grün) /
  // „N/M ✓" — reine Anzeige aus `zerlegung-status.ts` (kein neuer Fachzustand).
  private readonly headStatusEl = byId<HTMLElement>("zerlegung-head-status");
  private readonly paletteCountEl = byId<HTMLElement>("parts-palette-count");
  // Zerlegungsart-Weiche (Issue #95): prominente Radiogruppe statt der früheren
  // deaktivierten Dropdown-Option. Abschnitte ↔ Module.
  private readonly abschnittRadio = byId<HTMLInputElement>("zerlegungsart-abschnitt");
  private readonly modulRadio = byId<HTMLInputElement>("zerlegungsart-modul");
  private readonly artHint = byId<HTMLParagraphElement>("zerlegungsart-hint");
  // Sichtbarkeitsmatrix (`.hidden` only): Abschnitt → Aufstell-Gruppe, Modul →
  // Modulgrößen-Gruppe (max. Länge/Höhe).
  private readonly aufstellGroup = byId<HTMLElement>("aufstell-group");
  private readonly moduleLimitsGroup = byId<HTMLElement>("module-limits-group");
  private readonly maxLengthInput = byId<HTMLInputElement>("module-max-length");
  private readonly maxHeightInput = byId<HTMLInputElement>("module-max-height");
  private readonly moduleLimitsStatus = byId<HTMLParagraphElement>("module-limits-status");
  private readonly decomposeStatus = byId<HTMLParagraphElement>("decompose-status");
  private readonly freigangEl = byId<HTMLParagraphElement>("decompose-freigang");
  private readonly cutsList = byId<HTMLUListElement>("decompose-cuts");
  private readonly addHorizontalBtn = byId<HTMLButtonElement>("decompose-add-horizontal-btn");
  private readonly addVerticalBtn = byId<HTMLButtonElement>("decompose-add-vertical-btn");
  private readonly jointOffsetInput = byId<HTMLInputElement>("decompose-joint-offset");
  private readonly checkBtn = byId<HTMLButtonElement>("decompose-check-btn");
  // Stufe-2-Prüf-Tür entkoppelt (Issue #175): eigener Block mit letztem Prüfstand,
  // Fokus-/Global-Anstoß, Fortschritt + Abbrechen. Reine Anzeige aus
  // `pruef-check-state.ts` (der Core rechnet, ADR-007).
  private readonly pruefLastEl = byId<HTMLParagraphElement>("pruef-last");
  private readonly pruefFocusBtn = byId<HTMLButtonElement>("pruef-focus-btn");
  private readonly pruefGlobalBtn = byId<HTMLButtonElement>("pruef-global-btn");
  private readonly pruefProgressEl = byId<HTMLElement>("pruef-progress");
  private readonly pruefProgressBar = byId<HTMLProgressElement>("pruef-progress-bar");
  private readonly pruefProgressLabel = byId<HTMLElement>("pruef-progress-label");
  private readonly pruefCancelBtn = byId<HTMLButtonElement>("pruef-cancel-btn");
  // Beam-Zerlegungslauf auslösbar (Issue #221, Folge #217): Anstoß-Knopf,
  // Fortschritt (Prüf-Tür-Aufrufe) + Abbrechen sowie der Such-Ausweis
  // (Verworfen-Gründe/Relaxation) — reine Anzeige aus `refinement-state.ts`.
  private readonly beamStartBtn = byId<HTMLButtonElement>("beam-start-btn");
  private readonly beamProgressEl = byId<HTMLElement>("beam-progress");
  private readonly beamProgressBar = byId<HTMLProgressElement>("beam-progress-bar");
  private readonly beamProgressLabel = byId<HTMLElement>("beam-progress-label");
  private readonly beamCancelBtn = byId<HTMLButtonElement>("beam-cancel-btn");
  private readonly beamSummaryEl = byId<HTMLParagraphElement>("beam-summary");
  private readonly beamRelaxEl = byId<HTMLParagraphElement>("beam-relax");
  private readonly beamVerworfenEl = byId<HTMLUListElement>("beam-verworfen");
  // Kollisions-Ampel je Platzierungsvorschlag (Issue #231, ADR-026 Punkt 2):
  // rein lesende Vorschau des Optimalvorschlags + Absprung auf den Beam-Trigger
  // oben. Reine Anzeige aus `placement-suggestion-state.ts` (der Core rechnet).
  private readonly placementSuggestionCheckBtn = byId<HTMLButtonElement>(
    "placement-suggestion-check-btn",
  );
  private readonly placementSuggestionStatus = byId<HTMLParagraphElement>(
    "placement-suggestion-status",
  );
  private readonly placementSuggestionList = byId<HTMLUListElement>(
    "placement-suggestion-list",
  );
  private readonly placementSuggestionHint = byId<HTMLParagraphElement>(
    "placement-suggestion-hint",
  );
  private readonly placementSuggestionHintText = byId<HTMLElement>(
    "placement-suggestion-hint-text",
  );
  private readonly placementSuggestionJumpBtn = byId<HTMLButtonElement>(
    "placement-suggestion-jump-btn",
  );
  // Accordions des Inspectors (Issue #106): Aufklapp-Muster wie
  // `collapsible-state.ts` (▸/▾), Zustand je Gruppe in localStorage persistiert.
  private readonly accordions = [
    { key: "art", toggleId: "zerlegung-acc-art-toggle", bodyId: "zerlegung-acc-art-body", label: "Art & Aufstellung" },
    { key: "cuts", toggleId: "zerlegung-acc-cuts-toggle", bodyId: "zerlegung-acc-cuts-body", label: "Schnittplan" },
    { key: "placement", toggleId: "zerlegung-acc-placement-toggle", bodyId: "zerlegung-acc-placement-body", label: "Platzierung" },
  ] as const;

  // Erfasste Aufstellmöglichkeiten des Druckjobs (Altprojekte, Issue #22):
  // speisen nur noch die Override-Referenz-Dropdowns der Teile-Palette (#94a).
  private _options: PlacementOption[] = [];
  private _standMode: StandMode = "floor";
  private _contextCheck = false;
  // Zerlegungsart (Issue #95): ersetzt den früheren `kindSelect.value`-Lesezugriff.
  private _kind: Zerlegungsart = "abschnitt";
  // Trägt der Druckjob eine Workstation? Art „modul" braucht sie (Druckort,
  // ADR-022) — sonst freundlicher Hinweis statt Vorschlag (kein Gate).
  private _workstationPresent = false;
  // Freigang-Befund der Wand (Issue #163): „Wand zu dick" — wand-weit, aus dem
  // Zerlegungslauf verbatim. `null` = kein Befund (nicht zu dick oder Geometrie
  // unbekannt) ⇒ Banner versteckt. Befund, kein Gate.
  private _freigang: FreigangFinding | null = null;
  private _cutPlan: CutPlanState = initCutPlanState();
  // Teile-Palette am 3D-Feld (Issue #91): dünne DOM-Klasse, gefüttert aus dem
  // reinen `paletteEntries`. Die frühere Aside-Abschnittsliste (#decompose-sections)
  // geht vollständig hierin auf.
  private readonly _palette = new PartsPalette({
    onSelect: (sectionId) => this.focusSection(sectionId),
    onOverrideChange: (sectionId, optionId) => {
      this._cutPlan = setSectionOverride(this._cutPlan, sectionId, optionId);
      this._renderPalette();
      this._scheduleCheck();
    },
  });
  // section_ids mit Slicing-Override (Marker-Quelle #82), von main.ts gespeist.
  private _overrideSectionIds: string[] = [];
  // Persistierte Platzierungs-Overrides des aktiven Jobs (Issue #161), von
  // main.ts gespeist (updatePartsOverrideMarkers — dieselbe Quelle wie die
  // ▪-Marker): die Karten-Zeile „Platzierung: …" zeigt für übersteuerte Teile
  // die Override-Werte statt der ggf. veralteten Zerlegungs-Platzierung.
  private _placementOverrides: SectionOverride[] = [];
  // Kollisions-Befunde je Teil (Kollisionskontrolle S3, US 12, #128): aus den
  // simulierten Läufen (meta.collision), von main.ts gespeist — speist das
  // Kollisions-Badge der Palette (getrennt von der Platzierungs-Ampel).
  private _collisionBySectionId: Record<string, CollisionMeta | undefined> = {};
  // Revisionsstände des Druckjobs (Issue #182): speisen die Veraltet-Markierung
  // des Kollisions-Badges — dieselbe Ableitung wie die übrigen Stufen-Badges
  // (Druckplan/Simulation/Export), von main.ts über `refreshRevisions` gespeist.
  private _revisions: Revisions | undefined;
  // Stufe-2-Prüf-Tür-Zustand (Issue #175): Umfangsansage (aus der Zerlegungs-Antwort),
  // letzter Prüfstand (aus dem Druckjob) und der laufende Hintergrundlauf-Status.
  private _pruefScope: PruefScope | null = null;
  private _lastPruef: LastPruef | null = null;
  private _checkStatus: DecompositionCheckStatus | null = null;
  // Beam-Zerlegungslauf (Issue #221): laufender Hintergrundlauf-Status + der
  // Such-Ausweis (refinement) des zuletzt übernommenen Sieger-Laufs.
  private _beamStatus: BeamProposeStatus | null = null;
  private _refinement: DecompositionRefinement | null = null;
  // Kollisions-Ampel je Platzierungsvorschlag (Issue #231): letztes Antwort-
  // Ergebnis der lesenden Vorschau, `null` = noch nicht/nicht erfolgreich geprüft.
  private _suggestionResult: PlacementSuggestionResult | null = null;
  private _suggestionBusy = false;
  // Gilt-für-Umschalter auf „Teil" (Issue #92): strukturelle Einstellungen
  // (Aufstellung, Zerlegung, Schnittplan) sind ausgegraut — nie ausgeblendet.
  private _structuralLocked = false;
  private _busy = false;
  private _busyCheck = false;
  private _apiAvailable = false;
  private _projectOpen = false;
  private _checkTimer: ReturnType<typeof setTimeout> | null = null;
  // Lost-Update-Schutz (Issue #36): zählt jede Plan-Änderung. Eine laufende
  // Prüfung, deren Start-Generation nicht mehr stimmt, ist veraltet — ihr
  // Ergebnis wird verworfen und der aktuelle Stand erneut geprüft.
  private _planGeneration = 0;
  // Prüfwunsch, der in ein laufendes Busy-Fenster fiel — wird nachgeholt.
  private _recheckWanted = false;
  // Aufklapp-Zustand je Accordion (Issue #106): reiner `collapsible-state.ts`-
  // Zustand, je Gruppe in localStorage persistiert (Default: aufgeklappt).
  private readonly _accStates: Record<string, CollapsibleState> = Object.fromEntries(
    this.accordions.map((a) => [a.key, collapsibleState(loadAccordionExpanded(a.key))]),
  );

  constructor(
    // Fokus-Teil (Issue #84/#196): der EINE Halter (`focus-store.ts`) — das
    // Panel delegiert Toggle/Reconcile und liest den Stand; die Wirkungen
    // (Highlight, Kamera, Panel-Umschaltungen) sind in main.ts registrierte
    // Subscriber (FOCUS_EFFECT_ORDER), keine Panel-Callbacks mehr.
    private readonly focus: FocusStore,
    private readonly callbacks: DruckplanPanelCallbacks,
  ) {
    // Palette + Prüf-Tür-Knöpfe folgen jedem Fokus-Wechsel (auch aus dem
    // 3D-Klick/`reconcile`): eigene Subscription statt Doppel-Render-Aufrufe.
    this.focus.subscribe(() => {
      this._renderPalette();
      this._renderPruef(); // Fokus-Knopf-Verfügbarkeit nachziehen (Issue #175)
    });

    // Aufstell-Toggle (Issue #81): Umschalten persistiert den Zustand und stößt
    // die Core-Neubewertung an — die frische Zerlegung wird wie ein
    // Zerlegungsvorschlag übernommen (Schnitte + Ampeln neu).
    this.floorRadio.addEventListener("change", () => void this._onToggle("floor"));
    this.elevatedRadio.addEventListener("change", () => void this._onToggle("elevated"));

    // Gebäudekontext-Schalter (Issue #131): Umschalten persistiert den Zustand über
    // die Core-Route; er wirkt erst bei der nächsten Simulation (kein Re-Decompose).
    this.kontextCheckBox.addEventListener("change", () => void this._onContextToggle());

    // Aktion „✦ Automatisch vorschlagen" (Issue #106/#134): Zerlegungsvorschlag
    // (#24) über die einzige Schreibstelle (proposeDecomposition, ADR-016) —
    // die Abschnitts-Platzierungen sucht der Core dabei je Teil automatisch.
    this.autoBtn.addEventListener("click", () => void this._runAuto());

    // Zerlegungsart-Weiche (Issue #95): Umschalten behält die Schnitte, verwirft
    // die Platzierungs-Overrides, setzt dirty und stößt den Re-Check mit der neuen
    // Art an (ADR-022 Punkt 5).
    this.abschnittRadio.addEventListener("change", () => void this._onArtChange("abschnitt"));
    this.modulRadio.addEventListener("change", () => void this._onArtChange("modul"));

    // Modul-Obergrenzen (Issue #90/#95): über die #90-Route persistieren + Re-Check
    // (der Gewichts-/Grenzen-Befund je Teil folgt).
    this.maxLengthInput.addEventListener("change", () => void this._onModuleLimitsChange());
    this.maxHeightInput.addEventListener("change", () => void this._onModuleLimitsChange());

    // Accordions (Issue #106): Klick kippt den Aufklapp-Zustand (persistiert je
    // Gruppe) — reines Sicht-Toggling wie das `collapsible-state.ts`-Muster.
    for (const acc of this.accordions) {
      byId<HTMLButtonElement>(acc.toggleId).addEventListener("click", () => {
        this._accStates[acc.key] = toggleCollapsible(this._accStates[acc.key]);
        saveAccordionExpanded(acc.key, this._accStates[acc.key].expanded);
        this._renderAccordion(acc.key);
      });
      this._renderAccordion(acc.key);
    }

    this.addHorizontalBtn.addEventListener("click", () => this._addCut("horizontal"));
    this.addVerticalBtn.addEventListener("click", () => this._addCut("vertical"));

    this.jointOffsetInput.addEventListener("change", () => {
      const mm = Number(this.jointOffsetInput.value);
      this._cutPlan = setJointOffset(this._cutPlan, Number.isFinite(mm) ? mm : 0);
      this._renderPalette(); // Ampel sofort auf "ungeprüft" umschalten
      this._scheduleCheck();
    });

    this.checkBtn.addEventListener("click", () => {
      this._cancelPendingCheck();
      void this._runCheck();
    });

    // Stufe-2-Prüf-Tür anstoßen (Issue #175): Fokus = nur die Höhenreihe des
    // Fokus-Teils (schnell, Default); Global = ganze Wand (teure, bewusste Wahl).
    this.pruefFocusBtn.addEventListener("click", () => {
      const focus = this.focus.get();
      if (!focus) return; // ohne Fokus-Teil kein Fokus-Anstoß (Knopf ist dann disabled)
      this.callbacks.onStartPruef?.("focus", focus);
    });
    this.pruefGlobalBtn.addEventListener("click", () => {
      this.callbacks.onStartPruef?.("global", null);
    });
    this.pruefCancelBtn.addEventListener("click", () => {
      this.callbacks.onCancelPruef?.();
    });
    this._renderPruef();

    // Beam-Zerlegung anstoßen/abbrechen (Issue #221): Hintergrundlauf, main.ts
    // poll't und meldet Fortschritt/Sieger über setBeamStatus/setRefinement zurück.
    this.beamStartBtn.addEventListener("click", () => {
      this.callbacks.onStartBeam?.();
    });
    this.beamCancelBtn.addEventListener("click", () => {
      this.callbacks.onCancelBeam?.();
    });
    this._renderBeam();

    // Kollisions-Ampel je Platzierungsvorschlag (Issue #231): rein lesende
    // Vorschau (POST …/placement-suggestion); der Absprung springt nur zum
    // vorhandenen Beam-Trigger, löst ihn nicht selbst aus (lose Kopplung).
    this.placementSuggestionCheckBtn.addEventListener("click", () => {
      void this._checkPlacementSuggestion();
    });
    this.placementSuggestionJumpBtn.addEventListener("click", () => {
      this.beamStartBtn.scrollIntoView({ behavior: "smooth", block: "center" });
      this.beamStartBtn.focus();
    });
    this._renderPlacementSuggestion();
  }

  /**
   * „Kollisions-Ampel prüfen" (Issue #231): fragt den Optimalvorschlag rein
   * lesend ab und zeigt die Core-Einstufung — ändert keinen Plan-/Fachzustand.
   */
  private async _checkPlacementSuggestion(): Promise<void> {
    if (this._suggestionBusy || !this.callbacks.onCheckPlacementSuggestion) return;
    this._suggestionBusy = true;
    this._syncButtons();
    this.placementSuggestionStatus.textContent = "Prüft Optimalvorschlag …";
    try {
      this._suggestionResult = await this.callbacks.onCheckPlacementSuggestion();
      this.placementSuggestionStatus.textContent = "";
    } catch (err) {
      this._suggestionResult = null;
      this.placementSuggestionStatus.textContent = `Fehler: ${err}`;
    } finally {
      this._suggestionBusy = false;
      this._syncButtons();
      this._renderPlacementSuggestion();
    }
  }

  /** Rendert Vorschlagsliste (Ampel je Kandidat) + Machbarkeits-Hinweis (rein). */
  private _renderPlacementSuggestion(): void {
    const rows = placementSuggestionRows(this._suggestionResult?.scored);
    this.placementSuggestionList.replaceChildren();
    this.placementSuggestionList.hidden = rows.length === 0;
    for (const row of rows) {
      const li = document.createElement("li");
      li.className = "placement-suggestion-row";
      const dot = document.createElement("span");
      const dotClass = row.ampel.tone === "ok" ? "ok" : row.ampel.tone === "bad" ? "err" : "muted";
      dot.className = `dot ${dotClass}`;
      li.appendChild(dot);
      const text = document.createElement("span");
      text.textContent = `${row.optionId}: ${row.ampel.label} — ${row.detail}`;
      li.appendChild(text);
      this.placementSuggestionList.appendChild(li);
    }
    const hint = placementFeasibilityHint(this._suggestionResult?.feasibility);
    this.placementSuggestionHint.hidden = !hint.show;
    this.placementSuggestionHintText.textContent = hint.text;
  }

  /**
   * Aktion „✦ Automatisch vorschlagen" (Issue #106/#134): Zerlegungsvorschlag
   * (#24) über die bestehende Schreibstelle — die Abschnitts-Platzierungen
   * sucht der Core je Teil automatisch (#80/#132). Ein Busy-Fenster deckt die
   * ganze Aktion; die debouncte Prüfung ruht solange (`_runCheck`-Guard).
   */
  private async _runAuto(): Promise<void> {
    if (this._busy) return;
    this._busy = true;
    this._syncButtons();
    this.autoBtn.textContent = "Rechnet …";
    try {
      await this._decompose();
    } finally {
      this._busy = false;
      this.autoBtn.textContent = "✦ Automatisch vorschlagen";
      this._syncButtons();
    }
  }

  /** Zerlegungsvorschlag (#24): frische Zerlegung in erreichbare Teile. */
  private async _decompose(): Promise<void> {
    const kind = this._kind;
    // Art „modul" ohne Workstation: freundlicher Hinweis statt Vorschlag —
    // kein Absturz, kein Gate (ADR-022, die Workstation ist der Druckort).
    if (kind === "modul" && !this._workstationPresent) {
      this._renderArtHint();
      return;
    }
    this.decomposeStatus.textContent =
      "Zerlegungsvorschlag wird berechnet — Core sucht erreichbare Teile …";
    try {
      this._cancelPendingCheck();
      // Laufende Prüfung entwerten (Issue #36): ihr Snapshot ist mit dem
      // frischen Vorschlag hinfällig — ihre Antwort darf ihn nicht überschreiben.
      this._planGeneration += 1;
      this._recheckWanted = false;
      const result = await this.callbacks.onDecompose(kind);
      // Frischer Vorschlag ersetzt einen laufenden Schnittplan-Entwurf komplett
      // (Overrides/Fugen-Versatz verwerfen — neuer Startpunkt fürs Editieren).
      this._cutPlan = applyEvaluation(initCutPlanState({ cuts: result.cuts }), result.sections);
      this._freigang = result.freigang ?? null;
      // Fokus mit dem frischen Abschnittssatz abgleichen (Issue #84).
      this._reconcileFocus();
      this.callbacks.onCutsChanged(this._cutPlan.cuts);
      this._renderCuts();
      this._renderPalette();
      this._reportDecomposeStatus();
      this._renderFreigang();
    } catch (err) {
      this.decomposeStatus.textContent = `Fehler beim Zerlegungsvorschlag: ${err}`;
    }
  }

  /** Spiegelt den Aufklapp-Zustand eines Accordions ins DOM (`.hidden` + ▸/▾). */
  private _renderAccordion(key: string): void {
    const acc = this.accordions.find((a) => a.key === key);
    if (!acc) return;
    const view = collapsibleView(this._accStates[key], acc.label);
    byId<HTMLElement>(acc.bodyId).hidden = view.bodyHidden;
    const toggle = byId<HTMLButtonElement>(acc.toggleId);
    toggle.setAttribute("aria-expanded", view.ariaExpanded);
    const marker = toggle.querySelector<HTMLElement>(".acc-marker");
    if (marker) marker.textContent = this._accStates[key].expanded ? "▾" : "▸";
  }

  /**
   * Setzt den Titel des „Platzierung — <Teil>"-Accordions (Issue #106/#94): der
   * Name des gewählten Teils, sonst schlicht „Platzierung". Reine Anzeige.
   */
  setPlacementTitle(partName: string | null): void {
    const el = document.getElementById("zerlegung-placement-title");
    if (el) el.textContent = partName ? `Platzierung — ${partName}` : "Platzierung";
  }

  /**
   * Stellt den Panel-Zustand aus dem Druckjob wieder her (nach Projekt-Öffnen):
   * erfasste Aufstellmöglichkeiten (Altprojekte, für die Override-Referenzen
   * #94a) + Schnittplan-Eingaben (Issue #25). Abschnitte kommen separat via
   * setSections (aus dem referenzierten Lauf, ADR-016).
   */
  restoreFromJob(
    placements: PlacementOption[],
    decompositionKind: "abschnitt" | "modul" = "abschnitt",
    cuts: Cut[] = [],
    jointOffsetMm: number = 0,
    sectionOverrides: SectionOverride[] = [],
    standMode: string | null | undefined = "floor",
    moduleLimits: { max_length_mm?: number; max_height_mm?: number } | null | undefined = null,
    workstationPresent: boolean = false,
    contextCheck: boolean | null | undefined = false,
  ): void {
    this._options = placements.map((p) => ({ ...p }));
    this._standMode = normalizeStandMode(standMode);
    this._contextCheck = normalizeContextCheck(contextCheck);
    this._kind = normalizeZerlegungsart(decompositionKind);
    this._workstationPresent = workstationPresent;
    this._cutPlan = initCutPlanState({ cuts, jointOffsetMm, sectionOverrides });
    // Override-Marker des alten Projekts zurücksetzen (main.ts speist die frischen
    // gleich über setSlicingOverrideSections nach, Issue #91).
    this._overrideSectionIds = [];
    this.jointOffsetInput.value = String(jointOffsetMm);
    this.maxLengthInput.value =
      moduleLimits?.max_length_mm != null ? String(moduleLimits.max_length_mm) : "";
    this.maxHeightInput.value =
      moduleLimits?.max_height_mm != null ? String(moduleLimits.max_height_mm) : "";
    this._cancelPendingCheck();
    this._planGeneration += 1; // laufende Prüfungen des alten Projekts entwerten
    this._recheckWanted = false;
    this._renderToggle();
    this._renderContextToggle();
    this._renderArt();
    this._renderCuts();
    this._renderPalette();
    // Freigang-Banner des alten Projekts löschen; es kommt aus dem neuen
    // Zerlegungslauf (setFreigang) oder der nächsten Prüfung wieder.
    this._freigang = null;
    this._renderFreigang();
    this.decomposeStatus.textContent = "";
    this.aufstellStatus.textContent = "";
    this.kontextStatus.textContent = "";
    this.moduleLimitsStatus.textContent = "";
    this._syncButtons();
  }

  /**
   * Setzt den Freigang-Befund der Wand (Issue #163) aus dem wiederhergestellten
   * Zerlegungslauf (decompose.json, ADR-007) — so überlebt das „Wand zu dick"-
   * Banner das Neuladen des Projekts. `null`/fehlt = still. Befund, kein Gate.
   */
  setFreigang(freigang: FreigangFinding | null | undefined): void {
    this._freigang = freigang ?? null;
    this._renderFreigang();
  }

  /** Zeigt die Abschnitte eines Zerlegungslaufs (aus decompose.json, ADR-016). */
  setSections(sections: DecompositionSection[], kind: "abschnitt" | "modul"): void {
    this._cutPlan = applyEvaluation(this._cutPlan, sections);
    this._kind = normalizeZerlegungsart(kind);
    this._renderArt();
    // Fokus mit dem frischen Abschnittssatz abgleichen (Issue #84): verschwindet
    // der Fokus-Abschnitt durch eine neue Zerlegung, fällt er sauber weg.
    this._reconcileFocus();
    this._renderPalette();
  }

  /**
   * Setzt, ob der Druckjob eine Workstation trägt (Issue #95): Art „modul"
   * braucht sie als Druckort (ADR-022). Aktualisiert den freundlichen Hinweis;
   * kein Gate.
   */
  setWorkstationPresent(present: boolean): void {
    this._workstationPresent = present;
    this._renderArtHint();
  }

  /** Die aktuell gewählte Zerlegungsart (für main.ts-Beschriftungen, Issue #95). */
  getKind(): Zerlegungsart {
    return this._kind;
  }

  /** Die aktuellen Abschnitte — für die 3D-Pick-Ziele (Issue #84). */
  getSections(): DecompositionSection[] {
    return this._cutPlan.sections;
  }

  /**
   * Nimmt einen Abschnitt in den Fokus bzw. hebt ihn auf (Toggle, Issue #84) —
   * aufgerufen vom 3D-Klick in `main.ts` und der Teile-Palette (#91). Reine
   * Delegation an den EINEN Halter (`focus-store.ts`, #196): Palette/Prüf-Tür
   * ziehen über die eigene Subscription nach, die übrigen Wirkungen über die in
   * main.ts registrierte Vertragsliste (FOCUS_EFFECT_ORDER).
   */
  focusSection(sectionId: string): void {
    this.focus.toggle(sectionId);
  }

  /**
   * Setzt die `section_id`s mit einem Slicing-Override (Issue #91): sie steuern
   * den ▪-Marker je Teil in der Palette. Von main.ts gespeist, sobald sich
   * `process_params.sections` ändert (Speichern, Neuladen, Zerlegung) — reine
   * Anzeigequelle (`slicingOverrideSectionIds`, #82). Seit Issue #94 zählen
   * auch Platzierungs-Overrides mit (`placementOverrideSectionIds`, Union).
   */
  setSlicingOverrideSections(sectionIds: readonly string[]): void {
    this._overrideSectionIds = [...sectionIds];
    this._renderPalette();
  }

  /**
   * Übernimmt die persistierten Platzierungs-Overrides des aktiven Druckjobs
   * (`section_overrides`, Issue #161): die Karten-Zeile „Platzierung: …" zeigt
   * für übersteuerte Teile die Override-Werte (sparse — nur überschriebene
   * Felder ersetzen die Zerlegungs-Werte), damit die Karte nach „Anwenden"
   * eines Placement-Hebels (#130/#65) nicht die alte Platzierung behauptet.
   * Von main.ts gespeist (derselbe Weg wie die ▪-Marker).
   */
  setPlacementOverrideValues(overrides: readonly SectionOverride[]): void {
    this._placementOverrides = overrides.map((o) => ({ ...o }));
    this._renderPalette();
  }

  /**
   * Übernimmt die Kollisions-Befunde je Teil (Kollisionskontrolle S3, US 12,
   * #128): aus den simulierten Läufen (`meta.collision`), von main.ts gespeist.
   * Speist das Kollisions-Badge der Palette — **verbatim** (ADR-007), getrennt
   * von der Platzierungs-Ampel. Ein leeres Objekt (Altprojekt, nichts simuliert)
   * zeigt kein Badge (Status quo).
   */
  setCollisionFindings(map: Readonly<Record<string, CollisionMeta | undefined>>): void {
    this._collisionBySectionId = { ...map };
    this._renderPalette();
  }

  /**
   * Übernimmt die Revisionsstände des Druckjobs (Issue #182): speist die
   * Veraltet-Markierung des Kollisions-Badges — dieselbe `sectionStageStatus`-
   * Ableitung wie die übrigen Stufen-Badges (Druckplan/Simulation/Export,
   * `staleness.ts`). Von main.ts über `refreshRevisions` nach jeder Änderung
   * gespeist, die frische `print_jobs` liefert.
   */
  setRevisions(revisions: Revisions | undefined): void {
    this._revisions = revisions;
    this._renderPalette();
    this._renderPruef();
  }

  /**
   * Umfangsansage der Stufe-2-Prüf-Tür (Issue #175) aus der Zerlegungs-Antwort
   * (`pruef_scope`): speist die Beschriftung „Ganze Wand prüfen (N, ~X s)".
   */
  setPruefScope(scope: PruefScope | null | undefined): void {
    this._pruefScope = scope ?? null;
    this._renderPruef();
  }

  /**
   * Letzter Prüf-Tür-Stand des Druckjobs (Issue #175, `print_job.last_pruef`):
   * speist die Zeile „Zuletzt geprüft: … (veraltet?)".
   */
  setLastPruef(lastPruef: LastPruef | null | undefined): void {
    this._lastPruef = lastPruef ?? null;
    this._renderPruef();
  }

  /**
   * Fortschritt/Ergebnis des laufenden Hintergrund-Prüflaufs (Issue #175): main.ts
   * poll't den Lauf und meldet den Status hier zurück (`null` = kein Lauf). Rendert den
   * Fortschrittsbalken + „Abbrechen" bzw. den ehrlichen Abschluss-Text.
   */
  setCheckStatus(status: DecompositionCheckStatus | null): void {
    this._checkStatus = status;
    this._renderPruef();
  }

  /** Rendert den Prüf-Tür-Block: letzter Prüfstand, Anstoß-Knöpfe, Fortschritt. */
  private _renderPruef(): void {
    // Letzter Prüfstand („was zuletzt geprüft, veraltet?").
    const last = lastCheckView(this._revisions, this._lastPruef);
    this.pruefLastEl.textContent = last.label;
    this.pruefLastEl.dataset.tone = last.tone;

    // Umfangsansage + Fokus-Verfügbarkeit an den Knöpfen.
    const ann = scopeAnnouncement(this._pruefScope);
    this.pruefGlobalBtn.textContent = ann.globalLabel;
    const running = this._checkStatus?.state === "running";
    this.pruefGlobalBtn.disabled = ann.globalEmpty || running;
    const hasFocus = this.focus.get() !== null;
    this.pruefFocusBtn.textContent = hasFocus
      ? ann.focusLabel
      : "Fokus prüfen (Teil wählen)";
    this.pruefFocusBtn.disabled = !hasFocus || running;

    // Fortschritt/Abschluss.
    const prog = checkProgressView(this._checkStatus);
    this.pruefProgressEl.classList.toggle("hidden", !prog.active);
    this.pruefProgressLabel.textContent = prog.label;
    this.pruefProgressLabel.dataset.tone = prog.tone;
    this.pruefCancelBtn.classList.toggle("hidden", !prog.cancellable);
    if (prog.running) {
      this.pruefProgressBar.classList.remove("hidden");
      this.pruefProgressBar.value = prog.fraction;
    } else {
      this.pruefProgressBar.classList.add("hidden");
    }
  }

  /**
   * Fortschritt/Ergebnis des laufenden Beam-Zerlegungslaufs (Issue #221): main.ts
   * poll't den Lauf und meldet den Status hier zurück (`null` = kein Lauf). Rendert
   * den Fortschrittsbalken (Prüf-Tür-Aufrufe) + „Abbrechen" bzw. den ehrlichen
   * Abschluss-Text.
   */
  setBeamStatus(status: BeamProposeStatus | null): void {
    this._beamStatus = status;
    this._renderBeam();
    this._syncButtons(); // Anstoß-Knopf während des Laufs sperren
  }

  /**
   * Setzt den Such-Ausweis des zuletzt übernommenen Beam-Laufs (Issue #221, `refinement`-
   * Block verbatim aus decompose.json): speist Verworfen-Gründe (US 10),
   * Relaxationsausweis (US 22) und die Beam-Kopfzeile. `null` = nichts zu zeigen
   * (Greedy/Altlauf). Reine Übersetzung des Core-Urteils in Anzeigetext (ADR-007).
   */
  setRefinement(refinement: DecompositionRefinement | null | undefined): void {
    this._refinement = refinement ?? null;
    this._renderBeam();
  }

  /** Rendert den Beam-Block: Fortschritt/Abschluss + Such-Ausweis (rein). */
  private _renderBeam(): void {
    // Fortschritt/Abschluss des Hintergrundlaufs.
    const prog = beamProgressView(this._beamStatus);
    this.beamProgressEl.classList.toggle("hidden", !prog.active);
    this.beamProgressLabel.textContent = prog.label;
    this.beamProgressLabel.dataset.tone = prog.tone;
    this.beamCancelBtn.classList.toggle("hidden", !prog.cancellable);
    if (prog.running) {
      this.beamProgressBar.classList.remove("hidden");
      this.beamProgressBar.value = prog.fraction;
    } else {
      this.beamProgressBar.classList.add("hidden");
    }

    // Such-Ausweis (nur nach einem übernommenen Lauf): Kopfzeile + Relaxation +
    // Verworfen-Gründe. Ohne Beam-Provenienz bleibt alles still (nichts zu zeigen).
    const summary = beamSummary(this._refinement);
    this.beamSummaryEl.hidden = !summary.show;
    this.beamSummaryEl.textContent = summary.label;

    const relax = relaxAusweis(this._refinement);
    this.beamRelaxEl.hidden = !relax.show;
    this.beamRelaxEl.textContent = relax.label;

    const rows = verworfenRows(this._refinement);
    this.beamVerworfenEl.hidden = rows.length === 0;
    this.beamVerworfenEl.replaceChildren(
      ...rows.map((row) => {
        const li = document.createElement("li");
        li.className = "beam-verworfen-row";
        li.textContent = `${row.kandidat} (${row.raster}): ${row.label}`;
        return li;
      }),
    );
  }

  /**
   * Übernimmt den frisch persistierten Platzierungs-Override-Stand des Druckjobs
   * (Issue #94, nach `PUT …/placement-override`) und stößt die Neubewertung an
   * („Prüfen", debounced — ADR-007): Ampel/erreichbar %/Marge aktualisieren sich,
   * Basis-Marker/Roboter-Mesh folgen dem Override nach der Antwort. Der Zustand
   * hält exakt das, was der Core gespeichert hat — die Prüfrunde sendet die
   * Overrides unverändert zurück (kein Lost Update).
   */
  applySectionOverrides(overrides: SectionOverride[]): void {
    this._cutPlan = replaceSectionOverrides(this._cutPlan, overrides);
    this._renderPalette(); // Ampel sofort auf „ungeprüft" umschalten
    this._scheduleCheck();
  }

  /** Zeigt/verbirgt die Teile-Palette am 3D-Feld (Reiter-Gate, nur `.hidden`). */
  setPaletteVisible(visible: boolean): void {
    this._palette.setVisible(visible);
  }

  /**
   * Ausgrau-Matrix des Gilt-für-Umschalters (Issue #92, `scope-state.ts`):
   * im Teil-Modus sind die strukturellen Gruppen (Aufstellung, Zerlegungsart/
   * Vorschlag, Schnittplan) **deaktiviert** — sie *erzeugen* die Teile erst und
   * können nicht je Teil gelten. Ausschließlich `disabled`, nie `.hidden`:
   * das Formular springt nicht.
   */
  setStructuralLocked(locked: boolean): void {
    if (locked === this._structuralLocked) return;
    this._structuralLocked = locked;
    this._syncButtons();
  }

  /** Gleicht den Fokus mit den vorhandenen Abschnitten ab (Store meldet Wegfall selbst). */
  private _reconcileFocus(): void {
    this.focus.reconcile(this._cutPlan.sections.map((s) => s.section_id));
  }

  /** Setzt API-Verfügbarkeit: ohne API ist der Reiter gesperrt. */
  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.apiWarning.hidden = available;
    this._syncButtons();
    this._renderPalette(); // Override-Selects nach Verfügbarkeit (de)aktivieren
  }

  /** Setzt, ob ein Projekt geöffnet ist. */
  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    if (!open) {
      // Projekt gewechselt/geschlossen (Issue #231): die alte Vorschau gehört
      // zum vorigen Projekt — verwerfen statt eine fremde Ampel zu zeigen.
      this._suggestionResult = null;
      this._renderPlacementSuggestion();
    }
    this._syncButtons();
    this._renderPalette();
  }

  /**
   * Zeigt einen Voraussetzungs-Hinweis (z. B. „zuerst Wand übernehmen") oder
   * blendet ihn aus (null). Kein Gate — nur Orientierung.
   */
  setPrecondition(text: string | null): void {
    this.precondition.hidden = text === null;
    this.precondition.textContent = text ?? "";
  }

  /**
   * Committet eine Schnitt-Position (Issue #25) — von der 3D-Drag-Interaktion
   * in main.ts nach Drag-Ende aufgerufen. Ruft dieselbe `moveCut`-Funktion wie
   * das Zahlenfeld auf: Drag und Zahlenfeld bleiben dadurch synchron (Issue
   * #25, Architektur-Leitplanke) — kein Ad-hoc-Sync, sondern derselbe Zustand.
   */
  setCutPosition(index: number, positionMm: number): void {
    this._cutPlan = moveCut(this._cutPlan, index, positionMm);
    this._renderCuts();
    this._renderPalette();
    this._scheduleCheck();
  }

  /** Die aktuellen Schnittebenen — für die sofortige 3D-Darstellung nach Drag-Start. */
  getCuts(): Cut[] {
    return this._cutPlan.cuts;
  }

  private _addCut(orientation: Cut["orientation"]): void {
    this._cutPlan = addCut(this._cutPlan, orientation, 0);
    this.callbacks.onCutsChanged(this._cutPlan.cuts);
    this._renderCuts();
    this._renderPalette();
    this._scheduleCheck();
  }

  private _removeCut(index: number): void {
    this._cutPlan = removeCut(this._cutPlan, index);
    this.callbacks.onCutsChanged(this._cutPlan.cuts);
    this._renderCuts();
    this._renderPalette();
    this._scheduleCheck();
  }

  private _moveCutFromField(index: number, positionMm: number): void {
    this._cutPlan = moveCut(this._cutPlan, index, positionMm);
    this.callbacks.onCutsChanged(this._cutPlan.cuts);
    this._renderPalette();
    this._scheduleCheck();
  }

  private _scheduleCheck(): void {
    this._planGeneration += 1; // jede geplante Prüfung folgt auf eine Plan-Änderung
    this._cancelPendingCheck();
    this._checkTimer = setTimeout(() => {
      this._checkTimer = null;
      void this._runCheck();
    }, CHECK_DEBOUNCE_MS);
  }

  private _cancelPendingCheck(): void {
    if (this._checkTimer !== null) {
      clearTimeout(this._checkTimer);
      this._checkTimer = null;
    }
  }

  private async _runCheck(): Promise<void> {
    // Leerer Plan OHNE bekannten Befund = nichts zu prüfen. MIT Befund (Abschnitte
    // vorhanden) muss auch cuts=[] zum Core — sonst geht das Löschen des letzten
    // Schnitts beim Neuladen verloren (Issue #49).
    if (this._cutPlan.cuts.length === 0 && this._cutPlan.sections.length === 0) return;
    // Während eines laufenden Zerlegungsvorschlags (_busy) nicht prüfen — der
    // frische Vorschlag ersetzt den Entwurf ohnehin (Issue #45).
    if (this._busy) return;
    if (this._busyCheck) {
      // Prüfwunsch fällt in eine laufende Prüfung: nicht verwerfen, sondern
      // nach deren Ende nachholen (Issue #36 — sonst gewinnt die veraltete
      // Antwort und der Nutzerstand wäre nie bewertet).
      this._recheckWanted = true;
      return;
    }
    // Art „modul" ohne Workstation: nicht prüfen — freundlicher Hinweis (der
    // Core würde 422 werfen; hier kein Gate, kein Absturz — ADR-022).
    if (this._kind === "modul" && !this._workstationPresent) {
      this._renderArtHint();
      return;
    }
    this._busyCheck = true;
    const generation = this._planGeneration;
    this._syncButtons();
    this.checkBtn.textContent = "Prüft …";
    this.decomposeStatus.textContent = "Schnittplan wird neu bewertet …";
    try {
      const kind = this._kind;
      const result = await this.callbacks.onCheckCutPlan(
        kind,
        this._cutPlan.cuts,
        this._cutPlan.jointOffsetMm,
        this._cutPlan.sectionOverrides,
      );
      if (generation === this._planGeneration) {
        this._cutPlan = applyEvaluation(
          { ...this._cutPlan, cuts: result.cuts, jointOffsetMm: result.jointOffsetMm },
          result.sections,
        );
        // Fokus mit dem neu bewerteten Abschnittssatz abgleichen (Issue #84).
        this._reconcileFocus();
        this.callbacks.onCutsChanged(this._cutPlan.cuts);
        // Nebenwirkungen (Abschnitte an Simulation/Export, Revisionen) erst
        // jetzt — nie für verworfene stale Antworten (Issue #45).
        this.callbacks.onCheckApplied?.();
        this._freigang = result.freigang ?? null;
        this._renderCuts();
        this._renderPalette();
        this._reportDecomposeStatus();
        this._renderFreigang();
      }
      // else: Plan wurde während der Prüfung geändert — Antwort ist ein
      // veralteter Snapshot und wird verworfen. KEIN _recheckWanted hier:
      // die auslösende Änderung hat ihren eigenen Debounce-Timer (bzw. lief
      // in den Busy-Guard oben); nach restoreFromJob/Projektwechsel wäre eine
      // Nachhol-Prüfung sogar falsch (Issue #45).
    } catch (err) {
      this.decomposeStatus.textContent = `Fehler bei der Neubewertung: ${err}`;
    } finally {
      this._busyCheck = false;
      this.checkBtn.textContent = "Prüfen";
      this._syncButtons();
      if (this._recheckWanted) {
        this._recheckWanted = false;
        this._cancelPendingCheck();
        this._checkTimer = setTimeout(() => {
          this._checkTimer = null;
          void this._runCheck();
        }, CHECK_DEBOUNCE_MS);
      }
    }
  }

  /** Freigang-Banner (Issue #163): „Wand zu dick" oder still (reine Regel). */
  private _renderFreigang(): void {
    const view = freigangBannerView(this._freigang);
    this.freigangEl.hidden = view.hidden;
    this.freigangEl.textContent = view.text;
  }

  private _reportDecomposeStatus(): void {
    const sections = this._cutPlan.sections;
    const red = sections.filter((s) => !s.status.reachable).length;
    const noun = this._kind === "modul" ? "Module" : "Abschnitte";
    this.decomposeStatus.textContent =
      red === 0
        ? `Zerlegung in ${sections.length} ${noun} — alle erreichbar (grün).`
        : `Zerlegung in ${sections.length} ${noun} — ${red} noch nicht erreichbar (rot). ` +
          "Befund, kein Gate.";
  }

  /** Schnittplan editierbar? Auch während eines Zerlegungsvorschlags (_busy)
   *  gesperrt — sonst laufen Edit und Vorschlag gegeneinander (Issue #45) —
   *  und im Teil-Modus des Gilt-für-Umschalters (strukturell, Issue #92). */
  private _cutEditingEnabled(): boolean {
    return (
      this._apiAvailable &&
      this._projectOpen &&
      !this._busyCheck &&
      !this._busy &&
      !this._structuralLocked
    );
  }

  private _syncButtons(): void {
    const enabled =
      this._apiAvailable && this._projectOpen && !this._busy && !this._structuralLocked;
    this.floorRadio.disabled = !enabled;
    this.elevatedRadio.disabled = !enabled;
    // Vereinter Vorschlag-Button (Issue #106): folgt der Bedienbarkeit.
    this.autoBtn.disabled = !enabled;
    // Zerlegungsart-Weiche ist strukturell (Issue #92/#95): im Teil-Modus des
    // Gilt-für-Umschalters ausgegraut (nur `disabled`, nie `.hidden`).
    this.abschnittRadio.disabled = this._structuralLocked;
    this.modulRadio.disabled = this._structuralLocked;
    // Modul-Obergrenzen folgen der Bedienbarkeit + Art (nur bei „modul" relevant).
    this.maxLengthInput.disabled = !enabled;
    this.maxHeightInput.disabled = !enabled;
    const enabledCheck = this._cutEditingEnabled();
    this.addHorizontalBtn.disabled = !enabledCheck;
    this.addVerticalBtn.disabled = !enabledCheck;
    this.jointOffsetInput.disabled = !enabledCheck;
    this.checkBtn.disabled =
      !enabledCheck ||
      (this._cutPlan.cuts.length === 0 && this._cutPlan.sections.length === 0);
    // Beam-Zerlegung (Issue #221): anstoßbar wie ein Zerlegungsvorschlag (Auto-
    // Vorschlag-Bedienbarkeit), aber nicht, solange ein Beam-Lauf schon läuft.
    const beamRunning = this._beamStatus?.state === "running";
    this.beamStartBtn.disabled = !enabled || beamRunning;
    // Kollisions-Ampel je Platzierungsvorschlag (Issue #231): dieselbe
    // Bedienbarkeit wie „Automatisch vorschlagen", gesperrt während der Abfrage.
    this.placementSuggestionCheckBtn.disabled = !enabled || this._suggestionBusy;
    // Auch die Zahlenfelder/Lösch-Buttons der Schnittliste sperren (Issue #45).
    for (const el of this.cutsList.querySelectorAll<HTMLInputElement | HTMLButtonElement>(
      "input, button",
    )) {
      el.disabled = !enabledCheck;
    }
  }

  /**
   * Aufstell-Toggle umgeschaltet (Issue #81): den Zustand merken, persistieren
   * und die Core-Neubewertung anstoßen. Die frische Zerlegung (falls geliefert)
   * wird wie ein Zerlegungsvorschlag übernommen — Schnitte + Ampeln neu, ein
   * laufender Schnittplan-Entwurf wird dabei ersetzt (ADR-007).
   */
  private async _onToggle(mode: StandMode): Promise<void> {
    if (this._busy || mode === this._standMode) {
      this._renderToggle();
      return;
    }
    this._standMode = mode;
    this._renderToggle();
    this._busy = true;
    this._syncButtons();
    this.aufstellStatus.textContent =
      mode === "floor"
        ? "Aufstellung: Boden — Neubewertung läuft (mehr Höhenbänder) …"
        : "Aufstellung: erhöht — Neubewertung läuft (Podesthöhen erlaubt) …";
    try {
      // Laufende Prüfung entwerten (Issue #36): ihr Snapshot ist mit dem
      // frischen Toggle-Stand hinfällig.
      this._cancelPendingCheck();
      this._planGeneration += 1;
      this._recheckWanted = false;
      const result = await this.callbacks.onStandModeChange(mode);
      if (result) {
        this._cutPlan = applyEvaluation(
          initCutPlanState({ cuts: result.cuts }),
          result.sections,
        );
        this._freigang = result.freigang ?? null;
        // Fokus mit dem frischen Abschnittssatz abgleichen (Issue #84).
        this._reconcileFocus();
        this.callbacks.onCutsChanged(this._cutPlan.cuts);
        this._renderCuts();
        this._renderPalette();
        this._reportDecomposeStatus();
        this._renderFreigang();
      }
      this.aufstellStatus.textContent =
        mode === "floor"
          ? "Aufstellung: Roboter steht auf dem Boden (Podesthöhe 0)."
          : "Aufstellung: Roboter darf erhöht stehen (reale Podesthöhen).";
    } catch (err) {
      this.aufstellStatus.textContent = `Fehler beim Umschalten: ${err}`;
    } finally {
      this._busy = false;
      this._syncButtons();
    }
  }

  /** Spiegelt den Toggle-Zustand in die Radio-Buttons (checked). */
  private _renderToggle(): void {
    this.floorRadio.checked = this._standMode === "floor";
    this.elevatedRadio.checked = this._standMode === "elevated";
  }

  /**
   * Gebäudekontext-Schalter umgeschaltet (Issue #131): den Zustand merken und über
   * die Core-Route persistieren. Kein Re-Decompose (der Schalter wirkt erst bei der
   * nächsten Simulation). Bei Fehler den Zustand zurückrollen (Viewer bleibt
   * zustandslos — die Wahrheit steht im project.json, ADR-007/016).
   */
  private async _onContextToggle(): Promise<void> {
    const enabled = this.kontextCheckBox.checked;
    if (enabled === this._contextCheck) return;
    this._contextCheck = enabled;
    this._renderContextToggle();
    try {
      await this.callbacks.onContextCheckChange?.(enabled);
      this.kontextStatus.textContent = enabled
        ? "Gebäudekontext wird bei der nächsten Simulation geprüft."
        : "Gebäudekontext wird nicht geprüft.";
    } catch (err) {
      this._contextCheck = !enabled;
      this._renderContextToggle();
      this.kontextStatus.textContent = `Fehler beim Umschalten: ${err}`;
    }
  }

  /** Spiegelt den Kontext-Schalter in die Checkbox (checked). */
  private _renderContextToggle(): void {
    this.kontextCheckBox.checked = this._contextCheck;
  }

  /**
   * Zerlegungsart umgeschaltet (Issue #95, ADR-022 Punkt 5). Reiner Weiche-State
   * (`switchArt`): ALLE Schnitte bleiben, die Platzierungs-Overrides verfallen,
   * der Plan wird ungeprüft (dirty). Slicing-Overrides
   * (`process_params.sections`) leben in main.ts weiter und überstehen den
   * Wechsel unangetastet. Die Neubewertung (Re-Check mit der neuen Art) läuft
   * über den bestehenden debounced Mechanismus und ist zugleich die **eine**
   * Schreibstelle (`proposeDecomposition` → `fgc.project`, ADR-016), die die
   * geräumten Overrides + die neue Art persistiert.
   */
  private async _onArtChange(art: Zerlegungsart): Promise<void> {
    if (this._busy || art === this._kind) {
      this._renderArt();
      return;
    }
    this._kind = art;
    // Artwechsel-Regeln (ADR-022 Punkt 5) auf den Plan-Zustand anwenden: Schnitte
    // + Fugen-Versatz behalten, Platzierungs-Overrides verwerfen, dirty setzen.
    const switched = switchArt({
      cuts: this._cutPlan.cuts,
      jointOffsetMm: this._cutPlan.jointOffsetMm,
      sectionOverrides: this._cutPlan.sectionOverrides,
    });
    this._cutPlan = {
      ...this._cutPlan,
      cuts: switched.cuts,
      jointOffsetMm: switched.jointOffsetMm,
      sectionOverrides: switched.sectionOverrides,
      dirty: switched.dirty,
    };
    this._renderArt();
    this._renderCuts();
    this._renderPalette(); // Ampeln sofort auf „ungeprüft", Namen umschalten
    this.callbacks.onArtChanged?.(art);
    // Re-Check mit der neuen Art (persistiert Art + geräumte Overrides). Bei Art
    // „modul" ohne Workstation geht der Guard in `_runCheck` sauber ins Leere
    // (freundlicher Hinweis statt Absturz, ADR-022).
    this._scheduleCheck();
  }

  /**
   * Modul-Obergrenzen geändert (Issue #90/#95): über die #90-Route persistieren
   * (`onModuleLimitsChange`) und den Re-Check anstoßen — der Gewichts-/Grenzen-
   * Befund je Teil folgt. Leeres Feld = keine Obergrenze (`null`).
   */
  private async _onModuleLimitsChange(): Promise<void> {
    if (!this.callbacks.onModuleLimitsChange) return;
    const maxLength = parseOptionalMm(this.maxLengthInput.value);
    const maxHeight = parseOptionalMm(this.maxHeightInput.value);
    this.moduleLimitsStatus.textContent = "Obergrenzen werden gespeichert …";
    try {
      await this.callbacks.onModuleLimitsChange(maxLength, maxHeight);
      this.moduleLimitsStatus.textContent =
        maxLength === null && maxHeight === null
          ? "Keine Obergrenzen — nur der Arbeitsraum begrenzt (ADR-022)."
          : "Obergrenzen gespeichert — Befund je Teil in der Palette (kein Gate).";
      // Plan als ungeprüft markieren + Re-Check: die Grenzen ändern den Gewichts-/
      // Grenzen-Befund je Teil (nur bei Art „modul" spürbar).
      this._cutPlan = markUnchecked(this._cutPlan);
      this._renderPalette();
      this._scheduleCheck();
    } catch (err) {
      this.moduleLimitsStatus.textContent = `Fehler beim Speichern der Obergrenzen: ${err}`;
    }
  }

  /**
   * Spiegelt die Zerlegungsart in die Radiogruppe + die Sichtbarkeitsmatrix
   * (Issue #95). Ausschließlich `.hidden` (Lehre aus #56): Abschnitt → Aufstell-
   * Gruppe sichtbar, Modul → Modulgrößen-Gruppe sichtbar. Schaltet zugleich die
   * Palette-Beschriftung und den Workstation-Hinweis.
   */
  private _renderArt(): void {
    this.abschnittRadio.checked = this._kind === "abschnitt";
    this.modulRadio.checked = this._kind === "modul";
    const vis = visibilityFor(this._kind);
    this.aufstellGroup.hidden = vis.aufstellHidden;
    // Gebäudekontext-Schalter teilt die Abschnitt-Sichtbarkeit (bei Modul
    // gegenstandslos, ADR-022) — ausgeblendet, nicht gelöscht (Issue #131).
    this.kontextGroup.hidden = vis.aufstellHidden;
    this.moduleLimitsGroup.hidden = vis.moduleLimitsHidden;
    this._palette.setKind(this._kind);
    this._renderArtHint();
  }

  /** Zeigt/verbirgt den freundlichen „modul ohne Workstation"-Hinweis (kein Gate). */
  private _renderArtHint(): void {
    const hint = workstationHint(this._kind, this._workstationPresent);
    this.artHint.hidden = hint === null;
    this.artHint.textContent = hint ?? "";
  }

  /** Rendert die Schnittebenen-Liste (Issue #25): Position editierbar, entfernbar. */
  private _renderCuts(): void {
    this.cutsList.replaceChildren();
    this._cutPlan.cuts.forEach((cut, idx) => {
      const li = document.createElement("li");
      li.className = "decompose-cut-row";

      const label = document.createElement("span");
      label.className = "decompose-cut-label";
      label.textContent = cut.orientation === "horizontal" ? "Höhenschnitt" : "Längsschnitt";

      const input = document.createElement("input");
      input.type = "number";
      input.step = "any";
      input.className = "decompose-cut-position";
      input.value = String(cut.position_mm);
      input.title = "Position (mm) — synchron mit dem Ziehen der Ebene in der 3D-Ansicht";
      input.addEventListener("change", () => {
        const mm = Number(input.value);
        this._moveCutFromField(idx, Number.isFinite(mm) ? mm : cut.position_mm);
      });

      const del = document.createElement("button");
      del.type = "button";
      del.className = "decompose-cut-del";
      del.textContent = "×";
      del.title = "Schnitt entfernen";
      del.addEventListener("click", () => this._removeCut(idx));

      li.append(label, input, del);
      this.cutsList.append(li);
    });
    this._syncButtons(); // frisch gerenderte Zeilen sofort nach Busy-Zustand sperren (Issue #45)
  }

  /**
   * Zeichnet die Teile-Palette am 3D-Feld neu (Issue #91). Die Einträge (Ampel,
   * erreichbar %, ▪-Marker, Auswahl) leitet das reine `paletteEntries` aus dem
   * aktuellen Schnittplan-Zustand ab; die dünne DOM-Klasse rendert sie und die
   * Platzierungs-Override-Selects. Ersetzt das frühere `_renderSections` (Aside).
   */
  private _renderPalette(): void {
    const entries = paletteEntries({
      sections: this._cutPlan.sections,
      dirty: this._cutPlan.dirty,
      focusedSectionId: this.focus.get(),
      overrideSectionIds: this._overrideSectionIds,
      kind: this._kind,
      collisionBySectionId: this._collisionBySectionId,
      // Ehrliche Platzierungs-Zeile (Issue #161): Override-Werte sparse.
      placementOverrides: this._placementOverrides,
      // Veraltet-Markierung des Kollisions-Badges (Issue #182).
      revisions: this._revisions,
    });
    this._palette.render({
      entries,
      options: this._options,
      overrideFor: (sectionId) => overrideFor(this._cutPlan, sectionId),
      enabled: this._apiAvailable && this._projectOpen,
    });
    // Status-Badges (Issue #106): Kopf des Inspectors („ungeprüft"/„geprüft ✓")
    // und Zähler der Teile-Palette („N/M ✓"/„ungeprüft") aus derselben
    // Dirty-/Ampel-Ableitung (zerlegung-status.ts).
    applyBadge(this.headStatusEl, headStatus(this._cutPlan.dirty, this._cutPlan.sections.length));
    // Zähler (Issue #164/#170): der EHRLICHE Druckbarkeits-Zähler — Nenner = ALLE
    // Teile, Ungeprüfte werden ausgewiesen („4 druckbar · 12 ungeprüft"), nur
    // geprüft-frei zählt als ✓ (das lügende „16/16 ✓" fällt). Ein Lauf mit
    // fehlgeschlagener/fehlender Prüfung sieht so nie wie „alles geprüft" aus (B34/B35).
    // Nur die leere Palette (kein Teil) fällt auf den generischen Zähler zurück.
    const printCount = printabilityCounter(entries.map((e) => e.printability));
    applyBadge(this.paletteCountEl, printCount ?? paletteCounter(entries.map((e) => e.ampel)));
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}

/** Setzt ein Status-Badge (Text + `.badge-*`-Klasse + Sichtbarkeit, Issue #106). */
function applyBadge(
  el: HTMLElement,
  badge: { label: string; cssClass: "badge-warn" | "badge-ok"; show: boolean },
): void {
  el.textContent = badge.label;
  el.className = badge.cssClass;
  el.hidden = !badge.show;
}

/** localStorage-Schlüssel des Aufklapp-Zustands je Accordion-Gruppe (Issue #106). */
function accordionKey(key: string): string {
  return `fgc.zerlegung.acc.${key}`;
}

/** Aufklapp-Zustand einer Accordion-Gruppe lesen (Default: aufgeklappt). */
function loadAccordionExpanded(key: string): boolean {
  try {
    return localStorage.getItem(accordionKey(key)) !== "0";
  } catch {
    return true;
  }
}

/** Aufklapp-Zustand einer Accordion-Gruppe persistieren. */
function saveAccordionExpanded(key: string, expanded: boolean): void {
  try {
    localStorage.setItem(accordionKey(key), expanded ? "1" : "0");
  } catch {
    /* localStorage nicht verfügbar (private mode) — nicht persistieren, kein Fehler. */
  }
}

/** Optionale mm-Eingabe: leeres/nicht-endliches Feld → `null` (keine Obergrenze). */
function parseOptionalMm(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}
