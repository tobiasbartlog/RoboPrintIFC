/**
 * Simulations-Dock am Fuß des Viewports (Issue #108; vormals der Simulieren-
 * Bereich des Reiters Druckplan, #26/#86). Feste Leiste über dem 3D-Feld mit den
 * bestehenden Simulier-Aktionen und dem Trajektorien-Abspieler:
 *
 *   [▶ <Fokus-Teil> simulieren (Primär)] [Ganze Wand (Sekundär)]
 *   [▶/⏸] [Timeline] [Zeit] [Phasen-Pill]
 *
 * Zwei Simulier-Knöpfe — Standard **Fokus-Teil** (voller Arm-Lauf, sofort im
 * Player) und **ganze Wand / alle Module** (Gesamtablauf-Sequenz #27/#97). Die
 * Timeline/Zeit/Phasen-Pill spiegeln den bestehenden Player-Zustand; die Aktionen
 * docken an `main.ts` an (Slicing, IK, Timing kommen vom Core — der Viewer rechnet
 * nichts, ADR-007).
 *
 * Der frühere Modus-Umschalter „Vorbereiten↔Simulieren" (#86) ist mit dem Dock
 * ersatzlos entfallen (#108): Schnittplan-Bearbeitung und Simulation koexistieren
 * ohne Modus; den „nicht mit veralteten Werten simulieren"-Schutz leistet allein
 * die Veraltet-Markierung (nur veraltete Teile amber, ADR-017). Ein frisch über
 * „Fokus simulieren" erzeugter Lauf entsteht aus den *aktuellen* Werten (nie
 * veraltet). Deutliche Kennzeichnung: kinematisches Replay — **keine
 * Kollisionsprüfung** (PRD Out of Scope).
 */

import type { DecompositionSection, SectionRun, SimulateSectionResult } from "../api/projects";
import type { CollisionMeta } from "../artifacts/types";
import {
  collisionBadge,
  collisionCaveats,
  collisionMetaPairs,
  collisionStatusLine,
  timelineMarkers,
  type CollisionMarker,
} from "./collision-state";
import type { FocusReader } from "./focus-store";
import { formatTime } from "../trajectory/interpolate";
import {
  focusSimHint,
  focusSimLabel,
  focusSimTitle,
  focusTarget,
  sequenceSimHint,
  sequenceSimLabel,
  sequenceSimTitle,
} from "./sim-actions";
import { sequenceReady } from "./simulation-state";
import { simDockHidden } from "./sim-dock-state";
import { SPEED_STEPS, speedOptionLabel } from "./speed-control";
import type { Zerlegungsart } from "./zerlegungsart-state";

/** Ein Teil der abspielbaren Sequenz: Geometrie/Platzierung + sein Lauf. */
export interface SequenceItem {
  section: DecompositionSection;
  runPath: string;
}

export interface SimulationPanelCallbacks {
  /** „Slicen + Simulieren" für ein Teil anstoßen (POST …/simulate). */
  onSimulate(sectionId: string): Promise<SimulateSectionResult>;
  /** Den frisch simulierten Lauf im Replay-Player (im geteilten 3D-Feld) öffnen. */
  onOpenRun(sectionId: string, runPath: string): void;
  /**
   * Den Gesamtablauf abspielen (Issue #27): alle Teile in Druckreihenfolge
   * mit Umbau-Schritt dazwischen. Items sind bereits nach `order` sortiert.
   */
  onPlaySequence(items: SequenceItem[]): void;
  /**
   * Abspielgeschwindigkeit gewechselt (Issue #155): `rate` ist ein Vielfaches der
   * Echtzeit. Der Faktor klebt an der Sitzung (main.ts hält ihn); der laufende
   * Player übernimmt ihn sofort (Umbaupausen bleiben 3 s, skalieren nicht mit).
   */
  onSpeedChange(rate: number): void;
  /** Replay abspielen (Issue #48): der Player wird im Dock bedient. */
  onPlay(): void;
  /** Replay pausieren (Issue #48). */
  onPause(): void;
  /** Replay an Zeit t (Sekunden) springen (Issue #48). */
  onSeek(t: number): void;
  /**
   * „Zurück zur Übersicht" (Issue #48, Befund 1): die Modellübersicht
   * (Schnittebenen + Basis-Marker) im geteilten 3D-Feld wiederherstellen.
   */
  onBackToOverview(): void;
}

export class SimulationPanel {
  // Zwei Simulieren-Knöpfe (Issue #86/#108): Standard Fokus-Teil (voller Arm-Lauf,
  // Primär) + „ganze Wand"/„alle Module" (Gesamtablauf-Sequenz #27/#97, Sekundär).
  private readonly focusBtn = byId<HTMLButtonElement>("sim-focus-btn");
  private readonly sequenceBtn = byId<HTMLButtonElement>("sim-sequence-btn");
  private readonly apiWarning = byId<HTMLElement>("sim-api-warning");
  private readonly precondition = byId<HTMLElement>("sim-precondition");
  private readonly status = byId<HTMLElement>("sim-status");
  // Trajektorien-Abspieler im Dock (Issue #48/#108): erscheint erst, wenn ein Lauf
  // (oder der Gesamtablauf) spielt — Timeline/Zeit/Phasen-Pill spiegeln den Player.
  private readonly player = byId<HTMLElement>("sim-player");
  private readonly phase = byId<HTMLElement>("sim-phase");
  private readonly playBtn = byId<HTMLButtonElement>("sim-play-btn");
  private readonly slider = byId<HTMLInputElement>("sim-slider");
  private readonly time = byId<HTMLOutputElement>("sim-time");
  private readonly backBtn = byId<HTMLButtonElement>("sim-back-btn");
  // Abspielgeschwindigkeit (Issue #155): schmales <select> im Replay-Modus. Optionen
  // (Faktor + resultierende Replay-Dauer) baut _buildSpeedOptions je Lauf.
  private readonly speedSelect = byId<HTMLSelectElement>("sim-speed");
  // Kollisionskontrolle S3 (#128): anklickbare Timeline-Marker, Live-Abstandszahl
  // und Befund-Badge — alle verbatim aus `meta.collision` (collision-state.ts).
  private readonly collisionMarkers = byId<HTMLElement>("sim-collision-markers");
  private readonly collisionDist = byId<HTMLOutputElement>("sim-collision-dist");
  private readonly collisionBadgeEl = byId<HTMLElement>("sim-collision-badge");
  // Aufklappbarer Befundblock der Leiste (Issue #156): der Badge ist sein Anker,
  // ein Klick klappt ihn auf/zu — OHNE Reiter-/Bühnenwechsel (#147/#157). Zahlen
  // → <dl>, Vorbehalte → <ul>, dieselbe reine Zerlegung wie im Reiter Projekt.
  private readonly collisionPanel = byId<HTMLElement>("sim-collision-panel");
  private readonly collisionPanelMeta = byId<HTMLDListElement>("sim-collision-panel-meta");
  private readonly collisionPanelWarnings = byId<HTMLUListElement>("sim-collision-panel-warnings");

  private _sections: DecompositionSection[] = [];
  private _runs = new Map<string, string>(); // section_id → Lauf-Pfad
  private _busy: string | null = null; // gerade simuliertes section_id
  private _apiAvailable = false;
  private _projectOpen = false;
  // Dock-Modus (Issue #154): läuft ein Replay (Startknöpfe verschwinden) und liegt
  // ein Voraussetzungs-Hinweis an? Speist die reine Modus-Wahl (`simDockHidden`).
  private _replaying = false;
  private _hasPrecondition = false;
  // Zerlegungsart (Issue #97): steuert Knopf-Beschriftung + Venue der Simulation
  // (Abschnitt: in place; Modul: am Druckort, S8).
  private _kind: Zerlegungsart = "abschnitt";
  // Replay-Player-Zustand (Issue #48).
  private _playerDuration = 0;
  private _playing = false;
  private _dragging = false;
  // Abspielgeschwindigkeit (Issue #155): aktueller Sitzungs-Faktor + die Bausteine der
  // Restdauer-Anzeige je Option (Summe Druckphasen, Summe Umbaupausen ungeteilt).
  private _rate = 1;
  private _printTotal = 0;
  private _umbauTotal = 0;

  constructor(
    // Fokus-Teil (Issue #84/#86): Ziel des „Fokus simulieren"-Knopfs — seit
    // #196 direkt aus dem einen Halter (`focus-store.ts`) gelesen, statt einer
    // per Setter gefütterten Kopie.
    private readonly focus: FocusReader,
    private readonly callbacks: SimulationPanelCallbacks,
  ) {
    // „Fokus … simulieren" (Issue #86): das Fokus-Teil slicen + simulieren
    // (frischer Lauf mit den *aktuellen* Werten → nie veraltet) und sofort als
    // vollen Arm-Lauf im Player öffnen.
    this.focusBtn.addEventListener("click", () => void this._simulateFocusAndPlay());
    this.sequenceBtn.addEventListener("click", () => this._playSequence());

    // Replay-Player (Issue #48): Play/Pause, Seek, „Zurück zur Übersicht".
    this.playBtn.addEventListener("click", () => {
      if (this._playing) this.callbacks.onPause();
      else this.callbacks.onPlay();
    });
    // pointerdown/-up statt mousedown+change (analog Panel, Issue #49): ein Klick
    // ohne Wertänderung feuert kein change und ließe _dragging sonst true.
    this.slider.addEventListener("pointerdown", () => { this._dragging = true; });
    this.slider.addEventListener("pointerup", () => { this._dragging = false; });
    this.slider.addEventListener("pointercancel", () => { this._dragging = false; });
    this.slider.addEventListener("input", () => {
      const t = (Number(this.slider.value) / 10000) * this._playerDuration;
      this.time.value = formatTime(t);
      this.callbacks.onSeek(t);
    });
    this.slider.addEventListener("change", () => { this._dragging = false; });
    this.backBtn.addEventListener("click", () => this.callbacks.onBackToOverview());
    // Befund-Badge als Anker (Issue #156): Klick/Enter/Space klappt den Befundblock
    // der Leiste auf/zu — kein Reiterwechsel, kein Bühnenwechsel (#147/#157).
    this.collisionBadgeEl.addEventListener("click", () => this._toggleCollisionPanel());
    this.collisionBadgeEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this._toggleCollisionPanel();
      }
    });
    // Geschwindigkeitswechsel (Issue #155): meldet den neuen Faktor an main.ts (er
    // klebt an der Sitzung); der laufende Player übernimmt ihn sofort.
    this.speedSelect.addEventListener("change", () => {
      this._rate = Number(this.speedSelect.value);
      this.callbacks.onSpeedChange(this._rate);
    });
    this._buildSpeedOptions(); // Ausgangs-Optionen (1×, noch ohne Lauf-Dauer)
    this._render();
    this._applyDockMode(); // Ausgangszustand: Start-Modus (Player versteckt, Knöpfe da)
  }

  /**
   * Wendet die reine Modus-Wahl (`simDockHidden`, Issue #154) auf die Dock-Leiste
   * an — ausschließlich über `.hidden` (Lehre aus #56). Start-Modus zeigt die
   * Startknöpfe + anliegende Hinweise, Replay-Modus den Player; nie beides (Ende
   * der Überlagerung). Gilt für BEIDE Bühnen (Wand-Replay und Modul-Replay am
   * Druckort — beide bedienen dieselbe Leiste).
   */
  private _applyDockMode(): void {
    const hidden = simDockHidden({
      replaying: this._replaying,
      apiAvailable: this._apiAvailable,
      hasPrecondition: this._hasPrecondition,
    });
    this.focusBtn.hidden = hidden.focusBtn;
    this.sequenceBtn.hidden = hidden.sequenceBtn;
    this.apiWarning.hidden = hidden.apiWarning;
    this.precondition.hidden = hidden.precondition;
    this.player.hidden = hidden.player;
    this.speedSelect.hidden = hidden.speed; // Geschwindigkeit nur im Replay-Modus (#155)
  }

  /**
   * Speist die Geschwindigkeits-Anzeige (Issue #155): der aktuelle Sitzungs-Faktor
   * (`rate`, klebt an der Sitzung) und die Bausteine der Restdauer je Option —
   * `printTotal_s` (Summe der Druckphasen, skaliert mit dem Faktor) und `umbauTotal_s`
   * (Summe der Umbaupausen, UNGETEILT). main.ts ruft dies je Lauf/Modul/Bühne nach
   * `showPlayer`, damit die Optionen die Dauer dieses Laufs nennen.
   */
  setSpeedModel(rate: number, printTotal_s: number, umbauTotal_s: number): void {
    this._rate = rate;
    this._printTotal = printTotal_s;
    this._umbauTotal = umbauTotal_s;
    this._buildSpeedOptions();
  }

  /** Baut die <select>-Optionen: je Faktor „50× · ~1:44", der aktuelle Faktor gewählt. */
  private _buildSpeedOptions(): void {
    const opts = SPEED_STEPS.map((r) => {
      const o = document.createElement("option");
      o.value = String(r);
      o.textContent = speedOptionLabel(r, this._printTotal, this._umbauTotal);
      o.selected = r === this._rate;
      return o;
    });
    this.speedSelect.replaceChildren(...opts);
    this.speedSelect.value = String(this._rate);
  }

  /**
   * Blendet den Player im Dock ein (Issue #48): ein Teil-Lauf oder der
   * Gesamtablauf wird im geteilten 3D-Feld abgespielt, bedient im Dock. `label`
   * benennt, was läuft (Phasen-Pill); `durationS` speist den Zeit-Slider.
   */
  showPlayer(durationS: number, label: string): void {
    this._playerDuration = durationS;
    this._playing = false;
    this._replaying = true; // Replay-Modus: Startknöpfe verschwinden, Player erscheint (#154)
    this._applyDockMode();
    this.slider.value = "0";
    this.time.value = formatTime(0);
    this.playBtn.textContent = "▶";
    this.playBtn.setAttribute("aria-label", "Abspielen");
    // Die Phasen-Pill zeigt anfangs, WAS läuft (bei Sequenzen überschreibt sie
    // setPhase mit „Abschnitt 1 druckt / Umbau …").
    this.setPhase(label);
  }

  /** Aktualisiert Play/Pause-Zustand + Slider/Zeit des Players (Issue #48). */
  setPlayerState(t: number, playing: boolean): void {
    this._playing = playing;
    this.playBtn.textContent = playing ? "⏸" : "▶";
    this.playBtn.setAttribute("aria-label", playing ? "Pause" : "Abspielen");
    if (!this._dragging) {
      this.slider.value = String(
        this._playerDuration > 0 ? Math.round((t / this._playerDuration) * 10000) : 0,
      );
      this.time.value = formatTime(t);
    }
  }

  /** Phasen-Pill des Players (Issue #48): welcher Abschnitt / Umbau. */
  setPhase(text: string | null): void {
    this.phase.hidden = text === null;
    this.phase.textContent = text ?? "";
  }

  /** Blendet den Player aus (Issue #48): zurück zur Modellübersicht. */
  hidePlayer(): void {
    this._replaying = false; // Ende des Replays → zurück in den Start-Modus (#154)
    this._applyDockMode();
    this._playing = false;
    this.clearCollision();
  }

  /**
   * Kollisions-Befund des laufenden Replays (Kollisionskontrolle S3, #128): setzt
   * das Befund-Badge (US 12/25) und die anklickbaren Timeline-Marker (US 9), alle
   * **verbatim** aus `meta.collision` (ADR-007). `collision === null` (Altlauf,
   * Lauf ohne Kollisionsgeometrie) räumt Marker/Badge/Abstandszahl ab — die
   * ehrliche „keine Kollisionsprüfung"-Zeile (Phasen-Pill) bleibt (US 25).
   */
  setCollisionFinding(
    collision: CollisionMeta | null | undefined,
    sampleTimes: readonly number[],
    durationS: number,
  ): void {
    if (!collision || !collisionBadge(collision)) {
      this.clearCollision();
      return;
    }
    this._renderCollisionBadge(collision);
    this._renderCollisionMarkers(timelineMarkers(collision, sampleTimes, durationS));
  }

  /**
   * Kollisions-Anzeige des **aktiven Moduls** am Druckort (Issue #153, Entscheidung
   * #147 Variante b): Befund-Badge (verbatim) + die bereits **auf die Sequenzachse
   * projizierten** Marker (`projectModuleMarkers`) — nur des laufenden Moduls, keine
   * über die Umbaupausen. Ein Klick springt über `onSeek` auf die Sequenz-Zeit
   * innerhalb des Moduls (kein Bühnenwechsel). `collision === null` (Altlauf des
   * Moduls) räumt Badge + Marker ab; die ehrliche Statuszeile bleibt (US 25).
   */
  setModuleCollision(
    collision: CollisionMeta | null | undefined,
    markers: readonly CollisionMarker[],
  ): void {
    if (!collision || !collisionBadge(collision)) {
      this.collisionMarkers.replaceChildren();
      this.collisionBadgeEl.hidden = true;
      this._hideCollisionPanel();
      return;
    }
    this._renderCollisionBadge(collision);
    this._renderCollisionMarkers(markers);
  }

  /**
   * Setzt das Befund-Badge (verbatim aus `meta.collision`) UND füllt den
   * aufklappbaren Befundblock der Leiste (Issue #156): die kurze Badge-Zeile
   * bleibt Anker, die Zahlen/Vorbehalte ordnen sich im Block darunter ein.
   */
  private _renderCollisionBadge(collision: CollisionMeta): void {
    const badge = collisionBadge(collision)!;
    this.collisionBadgeEl.hidden = false;
    this.collisionBadgeEl.textContent = badge.label;
    this.collisionBadgeEl.className = `sim-collision-badge ${badge.status}`;
    this.collisionBadgeEl.title = collisionStatusLine(collision);
    this._renderCollisionPanel(collision);
  }

  /**
   * Füllt den Leisten-Befundblock (Issue #156): Zahlen → `<dl>`, Vorbehalte →
   * `<ul>` — dieselbe reine Zerlegung (`collisionMetaPairs`/`collisionCaveats`)
   * wie im Reiter Projekt, verbatim aus `meta.collision` (ADR-007). Ein frischer
   * Befund startet zugeklappt (der Badge öffnet ihn), damit die Leiste einzeilig
   * bleibt (#154).
   */
  private _renderCollisionPanel(collision: CollisionMeta): void {
    this.collisionPanelMeta.replaceChildren();
    for (const p of collisionMetaPairs(collision)) {
      const dt = document.createElement("dt");
      dt.textContent = p.label;
      const dd = document.createElement("dd");
      dd.textContent = p.value;
      this.collisionPanelMeta.append(dt, dd);
    }
    const caveats = collisionCaveats(collision);
    this.collisionPanelWarnings.hidden = caveats.length === 0;
    this.collisionPanelWarnings.replaceChildren();
    for (const text of caveats) {
      const li = document.createElement("li");
      li.textContent = text;
      this.collisionPanelWarnings.append(li);
    }
    this._hideCollisionPanel(); // frischer Befund: zugeklappt starten (#156)
  }

  /** Klappt den Leisten-Befundblock auf/zu (nur bei sichtbarem Badge = Befund). */
  private _toggleCollisionPanel(): void {
    if (this.collisionBadgeEl.hidden) return;
    const open = this.collisionPanel.hidden;
    this.collisionPanel.hidden = !open;
    this.collisionBadgeEl.setAttribute("aria-expanded", String(open));
  }

  /** Klappt den Leisten-Befundblock zu (kein Befund / Player aus / Modulwechsel). */
  private _hideCollisionPanel(): void {
    this.collisionPanel.hidden = true;
    this.collisionBadgeEl.setAttribute("aria-expanded", "false");
  }

  /** Rendert die anklickbaren Timeline-Marker (Position = `midFraction` der Player-Leiste). */
  private _renderCollisionMarkers(markers: readonly CollisionMarker[]): void {
    this.collisionMarkers.replaceChildren();
    for (const m of markers) {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = `sim-collision-marker ${m.status}`;
      dot.style.left = `${(m.midFraction * 100).toFixed(2)}%`;
      dot.title = m.title;
      dot.addEventListener("click", () => this.callbacks.onSeek(m.seekTime_s));
      this.collisionMarkers.appendChild(dot);
    }
  }

  /**
   * Live-Abstandszahl im Player (US 11, #128): `text === null` blendet sie aus
   * (Altlauf oder ⚙-Schalter „Abstandszahl" aus). `status` färbt sie rot/gelb.
   */
  setCollisionDistance(text: string | null, status: "red" | "yellow" | "green" = "green"): void {
    this.collisionDist.hidden = text === null;
    this.collisionDist.textContent = text ?? "";
    this.collisionDist.className = `sim-collision-dist ${status}`;
  }

  /** Räumt alle Kollisions-Anzeigen ab (kein Befund / Player aus). */
  clearCollision(): void {
    this.collisionMarkers.replaceChildren();
    this.collisionBadgeEl.hidden = true;
    this.collisionDist.hidden = true;
    this._hideCollisionPanel();
  }

  /** Sammelt die Teile in Druckreihenfolge, die einen Lauf haben. */
  private _sequenceItems(): SequenceItem[] {
    return this._sections
      .filter((s) => this._runs.has(s.section_id))
      .map((s) => ({ section: s, runPath: this._runs.get(s.section_id)! }));
  }

  /** Das eindeutige Ziel des „Fokus … simulieren"-Knopfs (Issue #86). */
  private _focusTarget(): string | null {
    return focusTarget(
      this.focus.get(),
      this._sections.map((s) => s.section_id),
    );
  }

  /**
   * „Fokus … simulieren" (Issue #86): das fokussierte Teil (bzw. bei nur einem
   * Teil dieses — US 24) slicen + simulieren und **sofort** als vollen Arm-Lauf
   * im Player öffnen. Der frische Lauf entsteht aus den aktuellen Werten (nie
   * veraltet). Reine Orchestrierung über die bestehenden Aktionen (ADR-007).
   */
  private async _simulateFocusAndPlay(): Promise<void> {
    const id = this._focusTarget();
    if (!id || this._busy) return;
    await this._simulate(id);
    const run = this._runs.get(id);
    if (run) this.callbacks.onOpenRun(id, run);
  }

  private _playSequence(): void {
    const items = this._sequenceItems();
    if (items.length === 0) return;
    this.status.hidden = false;
    this.status.textContent =
      "Gesamtablauf wird geladen — alle Teile in Druckreihenfolge, " +
      "mit Umbau-Schritt dazwischen (kinematisches Replay, keine Kollisionsprüfung).";
    this.callbacks.onPlaySequence(items);
  }

  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this._applyDockMode(); // API-Warnung nur im Start-Modus UND bei fehlender API (#154)
    this._render();
  }

  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    this._render();
  }

  /** Voraussetzungs-Hinweis (kein Gate — nur Orientierung); null blendet aus. */
  setPrecondition(text: string | null): void {
    this._hasPrecondition = text !== null;
    this.precondition.textContent = text ?? "";
    this._applyDockMode(); // Vorbedingung nur im Start-Modus UND bei anliegendem Hinweis (#154)
  }

  setStatus(text: string): void {
    this.status.hidden = text === "";
    this.status.textContent = text;
  }

  /** Die Teile des Schnittplans (Druckreihenfolge) — aus decompose.json. */
  setSections(sections: DecompositionSection[]): void {
    this._sections = [...sections].sort((a, b) => a.order - b.order);
    this._render();
  }

  /**
   * Fokus-Kaskaden-Mitglied `syncSimulationDock` (Issue #196): das fokussierte
   * Teil (Ziel des Standard-„Fokus simulieren"-Knopfs, #84/#86) hat gewechselt —
   * Knöpfe/Hinweis neu ableiten (der Wert kommt aus dem Store).
   */
  onFocusChanged(): void {
    this._render();
  }

  /**
   * Zerlegungsart des Druckjobs (Issue #97): schaltet die zwei Simulieren-Knöpfe
   * artabhängig um — „Fokus-Abschnitt simulieren" + „Ganze Wand" bei Abschnitten,
   * „Fokus-Modul simulieren" + „Alle Module" bei Modulen. Reine Beschriftung
   * (aus `sim-actions`); die Venue-Umschaltung (in place ↔ Druckort) macht
   * `main.ts` über die Callbacks.
   */
  setKind(kind: Zerlegungsart): void {
    if (kind === this._kind) return;
    this._kind = kind;
    this._render();
  }

  /**
   * Bereits vorhandene Teil-Läufe wiederherstellen (nach Projekt-Öffnen): merkt
   * je Teil den Lauf, damit „Ganze Wand"/„Alle Module" abspielbar wird, sobald
   * jedes Teil einen Lauf hat (sequenceReady). Reine Zustandsübernahme (ADR-007).
   */
  setSectionRuns(runs: SectionRun[]): void {
    this._runs = new Map(runs.map((r) => [r.section_id, r.run]));
    this._render();
  }

  /** Zurücksetzen (neues Projekt / neue Wand): Teile + Läufe leeren.
   *  Der Fokus liegt im Store (#196) und wird dort per `reconcile` bereinigt. */
  reset(): void {
    this._sections = [];
    this._runs.clear();
    this._busy = null;
    this._kind = "abschnitt";
    this.hidePlayer();
    this.setStatus("");
    this._render();
  }

  private async _simulate(sectionId: string): Promise<void> {
    if (this._busy) return;
    this._busy = sectionId;
    this.setStatus(`${sectionLabel(this._kind)} ${sectionId} wird gesliced und simuliert …`);
    this._render();
    try {
      const result = await this.callbacks.onSimulate(sectionId);
      this._runs.set(sectionId, result.run_dir);
      // Nur der neutrale Abschluss — die Kollisions-Aussage der Zeile kommt
      // beim Öffnen des Laufs verbatim aus `meta.collision` (replayStatusLine,
      // Issue #135): der frühere Festtext „(keine Kollisionsprüfung)" stand im
      // Widerspruch zu Badge + Live-Abstand desselben Replays.
      this.setStatus(`${sectionLabel(this._kind)} ${sectionId} simuliert — Replay startet …`);
    } catch (err) {
      this.setStatus(`Fehler bei ${sectionLabel(this._kind)} ${sectionId}: ${err}`);
    } finally {
      this._busy = null;
      this._render();
    }
  }

  private _render(): void {
    const enabled = this._apiAvailable && this._projectOpen && this._busy === null;

    // Gesamtablauf (Issue #27): abspielbar, sobald jedes Teil einen Lauf hat
    // (Replay braucht keine Core-API — es lädt nur vorhandene Läufe).
    const ready = sequenceReady(
      this._sections.map((s) => s.section_id),
      this._runs.keys(),
    );
    const seqEnabled = ready && this._projectOpen && this._busy === null;
    this.sequenceBtn.disabled = !seqEnabled;

    // Knopf-Beschriftung folgt der Zerlegungsart (Issue #97) — reine Beschriftung
    // aus `sim-actions`. Der Primär-Knopf trägt das ▶-Glyph des Docks.
    const focusId = this._focusTarget();
    this.focusBtn.textContent =
      this._busy !== null ? "Rechnet …" : `▶ ${focusSimLabel(this._kind)}`;
    this.focusBtn.disabled = !enabled || focusId === null;
    // Der zustandsabhängige Hinweis wandert in die Tooltips der Knöpfe (Scheibe 3:
    // Erklärtexte → ⓘ/title statt Fläche).
    this.focusBtn.title = `${focusSimTitle(this._kind)} — ${focusSimHint(
      this._kind,
      focusId,
      this._sections.length,
    )}`;

    this.sequenceBtn.textContent = sequenceSimLabel(this._kind);
    const missing = this._sections.length - this._runs.size;
    this.sequenceBtn.title = `${sequenceSimTitle(this._kind)} — ${sequenceSimHint(
      this._kind,
      ready,
      this._sections.length,
      missing,
    )}`;
  }
}

/** „Abschnitt"/„Modul" je Zerlegungsart — für Status-/Fehlertexte. */
function sectionLabel(kind: Zerlegungsart): string {
  return kind === "modul" ? "Modul" : "Abschnitt";
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}
