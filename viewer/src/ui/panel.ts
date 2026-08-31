/** Seitenpanel: Laufordner-Auswahl, Layer-Slider, Sichtbarkeits-Schalter,
 *  Parameter-Panel für Re-Slicing über die Core-API (Issue #9, ADR-014),
 *  Wand-Eignungsbericht mit Direkt-Slicing (Issue #10),
 *  Trajektorien-Animation mit Zeit-Slider und io-Verlauf (Issue #14).
 */

import type { Candidate, RunData, Trajectory, ToolpathParams } from "../artifacts/types";
import { formatTime } from "../trajectory/interpolate";
import { collisionCaveats, collisionMetaPairs } from "./collision-state";
import { summarizeWarnings } from "./warnings";

/** Deckelung der Warnungsliste (Issue #32) — Läufe mit weitgehend
 *  unerreichbaren Zielen tragen hunderte reach-Warnungen. */
const MAX_WARNINGS_SHOWN = 20;

export interface PanelCallbacks {
  onRunSelected(files: FileList): void;
  onLayerChanged(layer: number, onlyCurrent: boolean): void;
  onTravelToggled(visible: boolean): void;
  onWallToggled(visible: boolean): void;
  onContextToggled(visible: boolean): void;
  onModelToggled(visible: boolean): void;
  /** Re-Slice-Anfrage: null = Karten-Default übernehmen (leeres Feld). */
  onReslice(
    layerHeightMm: number | null,
    strandWidthMm: number | null,
    shells: number | null,
  ): void;
  /** Direkt-Slicing aus der Wand-Auswahl (Issue #10). */
  onSliceWall(globalId: string): void;
  /**
   * Wand in den aktiven Druckjob des geöffneten Projekts übernehmen (Issue #19).
   * Eignung ist Befund, kein Gate — wird auch für ungeeignete Wände aufgerufen.
   * ``wallName`` ist der Anzeigename aus candidates.json (optional).
   */
  onAdoptToJob(globalId: string, wallName: string | null, eligible: boolean): void;
  /** Trajektorie abspielen (Issue #14). */
  onTrajectoryPlay(): void;
  /** Trajektorie pausieren (Issue #14). */
  onTrajectoryPause(): void;
  /** Trajektorie an Zeit t (Sekunden) springen (Issue #14). */
  onTrajectorySeek(t: number): void;
}

export class Panel {
  private readonly runInput = byId<HTMLInputElement>("run-input");
  private readonly slider = byId<HTMLInputElement>("layer-slider");
  private readonly layerValue = byId<HTMLOutputElement>("layer-value");
  private readonly layerMax = byId<HTMLSpanElement>("layer-max");
  private readonly onlyCurrent = byId<HTMLInputElement>("only-current");
  private readonly showTravel = byId<HTMLInputElement>("show-travel");
  private readonly showWall = byId<HTMLInputElement>("show-wall");
  private readonly showContext = byId<HTMLInputElement>("show-context");
  private readonly showContextLabel = byId<HTMLLabelElement>("show-context-label");
  private readonly showModel = byId<HTMLInputElement>("show-model");
  private readonly showModelLabel = byId<HTMLLabelElement>("show-model-label");
  private readonly toolpathControls = byId<HTMLElement>("toolpath-controls");
  private readonly runInfo = byId<HTMLElement>("run-info");
  private readonly runName = byId<HTMLHeadingElement>("run-name");
  private readonly runMeta = byId<HTMLDListElement>("run-meta");
  private readonly controls = byId<HTMLElement>("controls");
  private readonly status = byId<HTMLParagraphElement>("status");

  // Parameter-Panel (Issue #9)
  private readonly reslicePanel = byId<HTMLElement>("reslice-panel");
  private readonly resliceApiHint = byId<HTMLElement>("reslice-api-hint");
  private readonly resliceFieldset = byId<HTMLFieldSetElement>("reslice-fieldset");
  private readonly paramLayerHeight = byId<HTMLInputElement>("param-layer-height");
  private readonly paramStrandWidth = byId<HTMLInputElement>("param-strand-width");
  private readonly paramShells = byId<HTMLInputElement>("param-shells");
  private readonly resliceBtn = byId<HTMLButtonElement>("reslice-btn");

  // Wand-Eignungsbericht (Issue #10)
  private readonly wallReport = byId<HTMLElement>("wall-report");
  private readonly wallReportId = byId<HTMLElement>("wall-report-id");
  private readonly wallReportRobot = byId<HTMLElement>("wall-report-robot");
  private readonly wallChecks = byId<HTMLUListElement>("wall-checks");
  private readonly sliceWallBtn = byId<HTMLButtonElement>("slice-wall-btn");
  // Druckjob-Übernahme (Issue #19)
  private readonly adoptJobBtn = byId<HTMLButtonElement>("adopt-job-btn");

  // Trajektorien-Panel (Issue #14)
  private readonly trajectoryPanel = byId<HTMLElement>("trajectory-panel");
  private readonly trajPlayBtn = byId<HTMLButtonElement>("traj-play-btn");
  private readonly trajSlider = byId<HTMLInputElement>("traj-slider");
  private readonly trajTime = byId<HTMLOutputElement>("traj-time");
  // Arm- und Strang-Schalter sind ins ⚙-Menü (ViewerSettings) gewandert (Issue
  // #159) — der Replay-Bühnen-Schalter lebt dort, wo die Bühne läuft.
  private readonly seqPhase = byId<HTMLParagraphElement>("seq-phase");
  private readonly trajMeta = byId<HTMLDListElement>("traj-meta");
  private readonly trajWarnings = byId<HTMLUListElement>("traj-warnings");
  private readonly trajIo = byId<HTMLDivElement>("traj-io");

  private _apiAvailable = false;
  private _projectOpen = false;
  private _resliceRequested = false;
  private _currentRobot: string | null = null;
  private _selectedGlobalId: string | null = null;
  private _selectedWallName: string | null = null;
  private _selectedEligible = true;
  private _sliceWallLabel = "Diese Wand slicen";
  private _adoptJobLabel = "In Druckjob übernehmen";
  private _trajDuration = 0;
  private _trajPlaying = false;
  private _trajDragging = false;

  constructor(callbacks: PanelCallbacks) {
    this.runInput.addEventListener("change", () => {
      if (this.runInput.files?.length) callbacks.onRunSelected(this.runInput.files);
    });
    const emitLayer = () => {
      const layer = Number(this.slider.value);
      this.layerValue.value = String(layer);
      callbacks.onLayerChanged(layer, this.onlyCurrent.checked);
    };
    this.slider.addEventListener("input", emitLayer);
    this.onlyCurrent.addEventListener("change", emitLayer);
    this.showTravel.addEventListener("change", () =>
      callbacks.onTravelToggled(this.showTravel.checked),
    );
    this.showWall.addEventListener("change", () => callbacks.onWallToggled(this.showWall.checked));
    this.showContext.addEventListener("change", () =>
      callbacks.onContextToggled(this.showContext.checked),
    );
    this.showModel.addEventListener("change", () =>
      callbacks.onModelToggled(this.showModel.checked),
    );

    // Re-Slice-Button
    this.resliceBtn.addEventListener("click", () => {
      const layerH = this.paramLayerHeight.value.trim()
        ? parseFloat(this.paramLayerHeight.value)
        : null;
      const strandW = this.paramStrandWidth.value.trim()
        ? parseFloat(this.paramStrandWidth.value)
        : null;
      const shells = this.paramShells.value.trim()
        ? parseInt(this.paramShells.value, 10)
        : null;
      callbacks.onReslice(layerH, strandW, shells);
    });

    // Direkt-Slicing aus Wand-Auswahl (Issue #10)
    this.sliceWallBtn.addEventListener("click", () => {
      if (this._selectedGlobalId) callbacks.onSliceWall(this._selectedGlobalId);
    });

    // Druckjob-Übernahme (Issue #19)
    this.adoptJobBtn.addEventListener("click", () => {
      if (this._selectedGlobalId) {
        callbacks.onAdoptToJob(
          this._selectedGlobalId,
          this._selectedWallName,
          this._selectedEligible,
        );
      }
    });

    // Trajektorie: Play/Pause und Slider (Issue #14)
    this.trajPlayBtn.addEventListener("click", () => {
      if (this._trajPlaying) callbacks.onTrajectoryPause();
      else callbacks.onTrajectoryPlay();
    });
    // pointerdown/-up statt mousedown+change: ein Klick ohne Wertänderung feuert
    // kein change und ließe _trajDragging sonst dauerhaft true (Issue #49).
    this.trajSlider.addEventListener("pointerdown", () => { this._trajDragging = true; });
    this.trajSlider.addEventListener("pointerup", () => { this._trajDragging = false; });
    this.trajSlider.addEventListener("pointercancel", () => { this._trajDragging = false; });
    this.trajSlider.addEventListener("input", () => {
      const t = (Number(this.trajSlider.value) / 10000) * this._trajDuration;
      this.trajTime.value = formatTime(t);
      callbacks.onTrajectorySeek(t);
    });
    this.trajSlider.addEventListener("change", () => { this._trajDragging = false; });
  }

  /**
   * Zeigt/versteckt die Sequenz-Phase-Zeile (Issue #27): welcher Abschnitt
   * gerade druckt bzw. läuft ein Umbau-Schritt. null blendet sie aus.
   */
  setSequencePhase(text: string | null): void {
    this.seqPhase.hidden = text === null;
    this.seqPhase.textContent = text ?? "";
  }

  /**
   * Sequenz-Modus (Issue #27): im Gesamtablauf deckt die Zeit den Strang auf —
   * der Layer-Slider ist dann bedeutungslos und wird ausgeblendet. Beim Verlassen
   * (Einzel-Lauf) wieder eingeblendet. Der Strang-Schalter selbst wohnt seit #159
   * im ⚙-Menü; main.ts blendet ihn dort im Sequenz-Modus aus (ViewerSettings).
   */
  setSequenceMode(on: boolean): void {
    this.toolpathControls.hidden = on;
    if (!on) this.setSequencePhase(null);
  }

  /** Aktueller Zustand des Kontext-Schalters (für neu geladene Läufe). */
  get contextVisible(): boolean {
    return this.showContext.checked;
  }

  // Weitere Schalter-Zustände: showRun wendet sie auf frisch gebaute Objekte an
  // (Issue #49 — vorher starteten Travel/Wand/Modell immer sichtbar, obwohl die
  // Checkboxen abgewählt blieben).
  get travelVisible(): boolean {
    return this.showTravel.checked;
  }
  get wallVisible(): boolean {
    return this.showWall.checked;
  }
  get modelVisible(): boolean {
    return this.showModel.checked;
  }

  setStatus(text: string): void {
    this.status.textContent = text;
  }

  /**
   * Setzt den API-Verfügbarkeitszustand des Parameter-Panels.
   * Wird einmalig beim Laden der Seite und nach jedem Re-Slice geprüft.
   */
  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.resliceApiHint.hidden = available;
    this.resliceFieldset.disabled = !available;
    // Slice-Wand-Button und Adopt-Button nachziehen, falls bereits sichtbar.
    if (!this.sliceWallBtn.hidden) {
      this.sliceWallBtn.disabled = !available;
    }
    if (!this.adoptJobBtn.hidden) {
      this.adoptJobBtn.disabled = !available || !this._projectOpen;
    }
  }

  /**
   * Setzt, ob ein Projekt geöffnet ist — steuert den „In Druckjob übernehmen"-Button.
   * Ohne offenes Projekt bleibt der Button deaktiviert (kein Ziel für den Druckjob).
   */
  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    if (!this.adoptJobBtn.hidden) {
      this.adoptJobBtn.disabled = !this._apiAvailable || !open;
    }
    // Standalone-Reslice-Sichtbarkeit nachziehen (Issue #60): im Projektfluss
    // entfällt der Reiter-Projekt-Reslice zugunsten des Vorwärtsflusses.
    this._syncReslice();
  }

  /**
   * Setzt den Roboter, für den die Eignungsprüfung zuletzt lief (Issue #20).
   * Wird im Eignungsbericht als „geprüft für {robot}" angezeigt.
   */
  setCurrentRobot(name: string | null): void {
    this._currentRobot = name;
    // Sichtbares Update: falls Bericht bereits offen, sofort nachziehen.
    if (!this.wallReport.hidden && !this.wallReportRobot.hidden) {
      if (name) {
        this.wallReportRobot.textContent = `geprüft für: ${name}`;
      } else {
        this.wallReportRobot.hidden = true;
      }
    }
  }

  /**
   * Zeigt das Standalone-Parameter-Panel (Reiter Projekt) für den geladenen Lauf
   * oder versteckt es. Pre-füllt die Felder aus `params` (schema_version 0.3);
   * fehlt der Block (ältere 0.2-Läufe), bleiben die Felder leer (= Karten-Default).
   *
   * Issue #60: Das Standalone-Reslice ist an den **Abspieler-Modus** (`?run=`,
   * kein Projekt) gebunden. Im Projektfluss fließt der Prozess vorwärts — die
   * Slice-Basisparameter setzt man im Reiter Druckplan (`process_params.slice`),
   * gesliced wird je Abschnitt im Reiter Simulation; der Reiter Projekt dient dann
   * nur der Modellübersicht + Wandübernahme, ohne konkurrierendes Reslice.
   */
  setResliceParams(params: ToolpathParams | null, visible: boolean): void {
    this._resliceRequested = visible;
    this._syncReslice();
    if (params) {
      this.paramLayerHeight.value = String(params.layer_height_mm);
      this.paramStrandWidth.value = String(params.strand_width_mm);
      this.paramShells.value = String(params.n_shells);
    } else {
      this.paramLayerHeight.value = "";
      this.paramStrandWidth.value = "";
      this.paramShells.value = "";
    }
  }

  /**
   * Blendet das Standalone-Reslice-Panel ein, sofern gewünscht **und** kein
   * Projekt geöffnet ist (Issue #60 — Vorwärtsfluss statt Reiter-Projekt-Reslice).
   */
  private _syncReslice(): void {
    this.reslicePanel.hidden = !this._resliceRequested || this._projectOpen;
  }

  /**
   * Setzt den Schaltflächen-Zustand während eines laufenden Re-Slice-Vorgangs.
   */
  setResliceBusy(busy: boolean): void {
    this.resliceBtn.disabled = busy || !this._apiAvailable;
    this.resliceBtn.textContent = busy ? "Slicing …" : "Neu slicen";
  }

  // --- Wand-Eignungsbericht (Issue #10) ---

  /**
   * Zeigt den Eignungsbericht für die angeklickte Wand im Panel an.
   * `candidate` = null → keine Eignungsdaten (unbekannte Wand).
   * Slicen ist auch für ungeeignete Wände erlaubt (Parität zum Wizard):
   * die Eignung ist ein Befund, kein Gate — ungeeignete Wände werden später
   * über Roboter-Platzierung oder Zerlegung passend gemacht.
   */
  showWallReport(globalId: string, candidate: Candidate | null): void {
    this._selectedGlobalId = globalId;
    this._selectedWallName = candidate?.name ?? null;
    this._selectedEligible = candidate?.eligible ?? true;
    this.wallReport.hidden = false;
    this.wallReportId.textContent = globalId;
    // Roboter-Hinweis (Issue #20): „geprüft für {robot}"
    if (this._currentRobot) {
      this.wallReportRobot.hidden = false;
      this.wallReportRobot.textContent = `geprüft für: ${this._currentRobot}`;
    } else {
      this.wallReportRobot.hidden = true;
    }
    this.wallChecks.replaceChildren();

    if (!candidate) {
      const li = document.createElement("li");
      li.textContent = "Kein Eignungseintrag für diese Wand.";
      li.className = "check-unknown";
      this.wallChecks.append(li);
      this.sliceWallBtn.hidden = true;
      this.adoptJobBtn.hidden = true;
      return;
    }

    for (const c of candidate.checks) {
      const li = document.createElement("li");
      li.className = c.passed
        ? c.provisional
          ? "check-provisional"
          : "check-pass"
        : "check-fail";

      const symbol = document.createElement("span");
      symbol.className = "check-symbol";
      symbol.textContent = c.passed ? "✓" : "✗";

      const label = document.createElement("strong");
      label.textContent = c.check;

      li.append(symbol, " ", label);

      if (c.provisional && c.passed) {
        const badge = document.createElement("span");
        badge.className = "provisional-badge";
        badge.textContent = "vorläufig";
        li.append(" ", badge);
      }

      if (c.reason) {
        const reason = document.createElement("span");
        reason.className = "check-reason";
        reason.textContent = c.reason;
        li.append(reason);
      }

      this.wallChecks.append(li);
    }

    // Genau eine Primäraktion je Modus: Im Projektfluss übernimmt „In Druckjob
    // übernehmen" — gesliced wird dort je Abschnitt im Reiter Simulation
    // (ADR-016). Das Direkt-Slicing (Issue #10) bleibt dem Abspieler-Modus
    // ohne Projekt (?run=) vorbehalten; zwei Slice-artige Buttons nebeneinander
    // wären missverständlich.
    // Ungeeignete Wände sind mit Warnung slicebar — wie im Wizard.
    this.sliceWallBtn.hidden = this._projectOpen;
    this.sliceWallBtn.disabled = !this._apiAvailable;
    this.sliceWallBtn.title = !this._apiAvailable
      ? "Core-API nicht erreichbar — mit fgc start hochfahren"
      : candidate.eligible
        ? ""
        : "Achtung: Wand ist laut Eignungsprüfung nicht druckgeeignet";
    this._sliceWallLabel = candidate.eligible
      ? "Diese Wand slicen"
      : "Trotzdem slicen (nicht geeignet)";
    this.sliceWallBtn.textContent = this._sliceWallLabel;

    // Adopt-Button: Wand in den Druckjob übernehmen (Issue #19).
    // Auch ungeeignete Wände sind übernehmbar (Befund, kein Gate — ADR-013/CONTEXT).
    // Nur im Projektfluss sichtbar (ohne Projekt gibt es kein Ziel für den Job).
    this.adoptJobBtn.hidden = !this._projectOpen;
    this.adoptJobBtn.disabled = !this._apiAvailable || !this._projectOpen;
    if (!this._apiAvailable) {
      this.adoptJobBtn.title = "Core-API nicht erreichbar — mit fgc start hochfahren";
    } else if (!candidate.eligible) {
      this.adoptJobBtn.title =
        "Achtung: Wand ist laut Eignungsprüfung nicht druckgeeignet — wird trotzdem übernommen";
    } else {
      this.adoptJobBtn.title = "";
    }
    this._adoptJobLabel = candidate.eligible
      ? "In Druckjob übernehmen"
      : "Trotzdem übernehmen (nicht geeignet)";
    this.adoptJobBtn.textContent = this._adoptJobLabel;
  }

  /** Versteckt den Wand-Eignungsbericht (nach Lauf-Wechsel oder Klick ins Leere). */
  hideWallReport(): void {
    this._selectedGlobalId = null;
    this._selectedWallName = null;
    this.wallReport.hidden = true;
    this.adoptJobBtn.hidden = true;
  }

  /** Setzt den Button-Zustand während des Direkt-Slicings. */
  setSliceWallBusy(busy: boolean): void {
    this.sliceWallBtn.disabled = busy || !this._apiAvailable;
    this.sliceWallBtn.textContent = busy ? "Slicing …" : this._sliceWallLabel;
  }

  /** Setzt den Button-Zustand während der Druckjob-Übernahme (Issue #19). */
  setAdoptBusy(busy: boolean): void {
    this.adoptJobBtn.disabled = busy || !this._apiAvailable || !this._projectOpen;
    this.adoptJobBtn.textContent = busy ? "Übernehmen …" : this._adoptJobLabel;
  }

  // --- Trajektorien-Panel (Issue #14) ---

  /** Blendet das Trajektorien-Panel ein und füllt Metadaten + Warnungen. */
  showTrajectory(trajectory: Trajectory): void {
    this._trajDuration = trajectory.meta.duration_s;
    this._trajPlaying = false;
    this.trajectoryPanel.hidden = false;

    // Meta: Gesamtdauer + Druckzeitschätzung (aus letztem Sample) + io_compensated
    this.trajMeta.replaceChildren();
    const addRow = (label: string, value: string) => {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      this.trajMeta.append(dt, dd);
    };
    addRow("Dauer", formatTime(trajectory.meta.duration_s));
    // Druckzeit: Zeit des letzten Samples (entspricht Gesamtdauer der Bewegung)
    if (trajectory.samples.length > 0) {
      const lastT = trajectory.samples[trajectory.samples.length - 1].t_s;
      if (Math.abs(lastT - trajectory.meta.duration_s) > 0.01) {
        addRow("Letztes Sample", formatTime(lastT));
      }
    }
    addRow("io kompensiert", trajectory.meta.io_compensated ? "ja (−t_tot)" : "nein");
    // Lagequelle (Issue #26): geplante Platzierung vs. gemessenes Setup. Den
    // Kollisionsbefund behauptet diese Zeile NICHT mehr ein zweites Mal (#156,
    // Entdoppelung): trägt der Lauf einen Befund, steht der als eigener Block in
    // dieser Liste (collisionMetaPairs) — die Lagequelle nennt dann nur die Quelle.
    // Der ehrliche „keine Kollisionsprüfung"-Zusatz bleibt nur ohne Befund (US 25).
    if (trajectory.meta.pose_source) {
      addRow(
        "Lagequelle",
        trajectory.meta.pose_source === "planned"
          ? trajectory.meta.collision
            ? "geplant (Platzierung)"
            : "geplant (Platzierung) — Replay, keine Kollisionsprüfung"
          : "gemessen (Setup)",
      );
    }
    if (trajectory.meta.axis_utilization) {
      const maxUtil = Math.max(...trajectory.meta.axis_utilization);
      addRow("Max. Achsauslastung", `${(maxUtil * 100).toFixed(0)} %`);
    }

    // Kollisionsbefund als Lauf-Eigenschaft (Issue #156): die Zahlen ordnen sich
    // in diese bewohnte Meta-Liste ein (sie verdrängen nichts), die Vorbehalte in
    // die Warnungsliste weiter unten. Dieselbe reine Zerlegung (collision-state.ts)
    // wie im Slicing-Dock — verbatim aus meta.collision (ADR-007). Altlauf ohne
    // Befund ⇒ keine Zeilen, kein Crash (US 25).
    if (trajectory.meta.collision) {
      for (const p of collisionMetaPairs(trajectory.meta.collision)) addRow(p.label, p.value);
    }

    // Warnungen — gedeckelt + je Art zusammengefasst (Issue #32): hunderte
    // reach-Warnungen dürfen das Panel nicht fluten; der Gesamtbefund
    // („N× reach") ist wichtiger als jede Einzelzeile.
    const summary = summarizeWarnings(trajectory.meta.warnings ?? [], MAX_WARNINGS_SHOWN);
    // Kollisions-Vorbehalte als eigene Warnungspunkte (Issue #156): sie stehen
    // vor den Trajektorien-Warnungen; die Liste wird sichtbar, sobald Vorbehalte
    // ODER Warnungen anliegen. Verbatim aus meta.collision (ADR-007).
    const caveats = trajectory.meta.collision ? collisionCaveats(trajectory.meta.collision) : [];
    this.trajWarnings.hidden = summary.total === 0 && caveats.length === 0;
    this.trajWarnings.replaceChildren();
    for (const text of caveats) {
      const li = document.createElement("li");
      li.className = "traj-caveat";
      li.textContent = text;
      this.trajWarnings.append(li);
    }
    if (summary.hidden > 0) {
      const kinds = Object.entries(summary.countsByKind)
        .map(([kind, n]) => `${n}× ${kind}`)
        .join(", ");
      const head = document.createElement("li");
      head.textContent =
        `${summary.total} Warnungen gesamt (${kinds}) — die ersten ${summary.shown.length}:`;
      this.trajWarnings.append(head);
    }
    for (const w of summary.shown) {
      const li = document.createElement("li");
      li.textContent = `${formatTime(w.t_s)} [${w.kind}] ${w.message}`;
      this.trajWarnings.append(li);
    }
    if (summary.hidden > 0) {
      const tail = document.createElement("li");
      tail.textContent = `… und ${summary.hidden} weitere.`;
      this.trajWarnings.append(tail);
    }

    // Slider und Zeitanzeige zurücksetzen
    this.trajSlider.value = "0";
    this.trajTime.value = "0.0 s";
    this.trajPlayBtn.textContent = "▶";
    this.trajPlayBtn.setAttribute("aria-label", "Abspielen");

    // io-Kanäle aus erstem Sample initialisieren
    this._rebuildIoChannels(trajectory.samples[0]?.io ?? {});
  }

  /** Versteckt das Trajektorien-Panel (Lauf ohne trajectory.json). */
  hideTrajectory(): void {
    this.trajectoryPanel.hidden = true;
    this._trajDuration = 0;
    this._trajPlaying = false;
  }

  /**
   * Aktualisiert Slider, Zeitanzeige, Play/Pause-Button und io-Kanäle
   * gemäß dem aktuellen Abspiel-Zustand. Slider-Update nur wenn nicht gezogen.
   */
  updateTrajectoryState(
    t: number,
    playing: boolean,
    io: Record<string, number>,
  ): void {
    this._trajPlaying = playing;
    this.trajPlayBtn.textContent = playing ? "⏸" : "▶";
    this.trajPlayBtn.setAttribute("aria-label", playing ? "Pause" : "Abspielen");

    if (!this._trajDragging) {
      const sliderVal =
        this._trajDuration > 0 ? (t / this._trajDuration) * 10000 : 0;
      this.trajSlider.value = String(Math.round(sliderVal));
      this.trajTime.value = formatTime(t);
    }

    this._updateIoChannels(io);
  }

  private _ioChannelEls = new Map<string, HTMLElement>();

  private _rebuildIoChannels(io: Record<string, number>): void {
    this._ioChannelEls.clear();
    this.trajIo.replaceChildren();
    for (const [name, value] of Object.entries(io)) {
      const wrapper = document.createElement("div");
      wrapper.className = "traj-channel";

      const header = document.createElement("div");
      header.className = "traj-channel-header";

      const nameEl = document.createElement("span");
      nameEl.className = "traj-channel-name";
      nameEl.textContent = name;

      const valueEl = document.createElement("span");
      valueEl.className = "traj-channel-value";
      valueEl.textContent = value.toFixed(3);

      header.append(nameEl, valueEl);

      const bar = document.createElement("div");
      bar.className = "traj-channel-bar";
      const fill = document.createElement("div");
      fill.className = "traj-channel-fill";
      fill.style.width = `${Math.max(0, Math.min(1, value)) * 100}%`;
      bar.append(fill);

      wrapper.append(header, bar);
      this.trajIo.append(wrapper);
      this._ioChannelEls.set(name, wrapper);
    }
  }

  private _updateIoChannels(io: Record<string, number>): void {
    // Rebuild wenn neue Kanäle auftauchen
    const currentKeys = [...this._ioChannelEls.keys()].sort().join(",");
    const newKeys = Object.keys(io).sort().join(",");
    if (currentKeys !== newKeys) {
      this._rebuildIoChannels(io);
      return;
    }
    for (const [name, value] of Object.entries(io)) {
      const wrapper = this._ioChannelEls.get(name);
      if (!wrapper) continue;
      const valueEl = wrapper.querySelector<HTMLElement>(".traj-channel-value");
      const fill = wrapper.querySelector<HTMLElement>(".traj-channel-fill");
      if (valueEl) valueEl.textContent = value.toFixed(3);
      if (fill) fill.style.width = `${Math.max(0, Math.min(1, value)) * 100}%`;
    }
  }

  showRun(run: RunData, maxLayer: number, targetCount: number): void {
    this.runInfo.hidden = false;
    this.runName.textContent = run.folderName;
    this.runMeta.replaceChildren();
    const provenance =
      run.toolpath?.provenance ?? run.wallspec?.provenance ?? run.candidates?.provenance;

    // Druckbar-Zusammenfassung aus candidates.json (ADR-007: Viewer rechnet nichts).
    const eligibilityRow: [string, string] | null = run.candidates
      ? (() => {
          const total = run.candidates.walls.length;
          const eligible = run.candidates.walls.filter((w) => w.eligible).length;
          return ["Druckbar", `${eligible} / ${total} Wände`];
        })()
      : null;

    const rows: Array<[string, string]> = [
      ...(eligibilityRow ? [eligibilityRow] : []),
      ["Wand", run.wallspec?.name ?? run.toolpath?.wall_global_id ?? "—"],
      ["GlobalId", run.toolpath?.wall_global_id ?? run.wallspec?.global_id ?? "—"],
      ["Targets", run.toolpath ? String(targetCount) : "—"],
      ["Schichten", run.toolpath ? String(maxLayer + 1) : "—"],
      ["Kontext", run.context ? `${run.context.elements.length} Elemente` : "—"],
      ["Erzeugt", provenance?.created ?? "—"],
      ["Commit", provenance?.git_commit ?? "—"],
      ["Quelle", provenance?.source ?? "—"],
    ];
    for (const [dt, dd] of rows) {
      const term = document.createElement("dt");
      term.textContent = dt;
      const detail = document.createElement("dd");
      detail.textContent = dd;
      this.runMeta.append(term, detail);
    }

    // Controls-Sektion: sichtbar sobald Toolpath ODER Modellübersicht vorliegt.
    this.controls.hidden = !run.toolpath && !run.modelMap;
    this.toolpathControls.hidden = !run.toolpath;
    this.showContextLabel.hidden = !run.context;
    this.showModelLabel.hidden = !run.modelMap;
    this.slider.max = String(maxLayer);
    this.slider.value = String(maxLayer);
    this.layerMax.textContent = String(maxLayer);
    this.layerValue.value = String(maxLayer);
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}
