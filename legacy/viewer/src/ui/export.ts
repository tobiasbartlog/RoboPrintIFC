/**
 * Reiter Export (Issue #29): DRL je Abschnitt + Übergabe-Checkliste — der
 * Abschluss des Prozesses.
 *
 * Je Abschnitt (Druckreihenfolge) lässt sich ein DRL-Programm erzeugen: der Core
 * nutzt die bestehende Emit-Aktion (Issue #13) und legt die `program.drl` in den
 * Abschnitts-Lauf (ADR-004). Liegt dort ein **gemessenes Setup** (Kanal-Mapping,
 * ADR-011) → vollständiges DRL; sonst ein sichtbar gekennzeichneter
 * **Antasten-Hinweis** statt eines unmarkiert unvollständigen Programms — kein
 * Gate (ADR-006). Der Abschnitt muss zuvor simuliert sein (`section_runs`, #26).
 *
 * Die **veraltet-Markierung** (Querschnitts-Konsistenz): Badges zeigen je Stufe
 * (Druckplan/Simulation/Export), ob der Stand *veraltet* ist — abgeleitet aus den
 * Revisionsständen des Druckjobs (reine Funktion `staleness.ts`, ADR-007). Der
 * Viewer zeigt nur; gerechnet/geschrieben wird im Core.
 */

import type { DecompositionSection, ExportDrlResult, SectionRun } from "../api/projects";
import {
  type OutputName,
  type Revisions,
  allStageStatuses,
  outputLabel,
  stageStatusLabel,
} from "./staleness";

export interface ExportPanelCallbacks {
  /** „DRL exportieren" für einen Abschnitt anstoßen (POST …/export). */
  onExport(sectionId: string): Promise<ExportDrlResult>;
}

/** Merkbares Ergebnis eines Abschnitts-Exports (für die Zeilenanzeige). */
interface ExportResult {
  complete: boolean;
  note: string;
  drlPath: string;
}

export class ExportPanel {
  private readonly stages = byId<HTMLElement>("export-stages");
  private readonly sectionsList = byId<HTMLUListElement>("export-sections");
  private readonly status = byId<HTMLParagraphElement>("export-status");
  private readonly apiWarning = byId<HTMLElement>("export-api-warning");
  private readonly precondition = byId<HTMLElement>("export-precondition");
  private readonly empty = byId<HTMLElement>("export-empty");

  private _sections: DecompositionSection[] = [];
  private _runs = new Map<string, string>(); // section_id → Lauf-Pfad
  private _results = new Map<string, ExportResult>();
  private _revisions: Revisions | undefined;
  private _busy: string | null = null;
  private _apiAvailable = false;
  private _projectOpen = false;

  constructor(private readonly callbacks: ExportPanelCallbacks) {}

  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.apiWarning.hidden = available;
    this._render();
  }

  setProjectOpen(open: boolean): void {
    this._projectOpen = open;
    this._render();
  }

  /** Voraussetzungs-Hinweis (kein Gate — nur Orientierung); null blendet aus. */
  setPrecondition(text: string | null): void {
    this.precondition.hidden = text === null;
    this.precondition.textContent = text ?? "";
  }

  setStatus(text: string): void {
    this.status.textContent = text;
  }

  /** Die Abschnitte des Schnittplans (Druckreihenfolge) — aus decompose.json. */
  setSections(sections: DecompositionSection[]): void {
    this._sections = [...sections].sort((a, b) => a.order - b.order);
    this._render();
  }

  /** Vorhandene Abschnitts-Läufe (Simulation nötig, bevor exportiert werden kann). */
  setSectionRuns(runs: SectionRun[]): void {
    this._runs = new Map(runs.map((r) => [r.section_id, r.run]));
    this._render();
  }

  /** Revisionsstände des Druckjobs für die veraltet-Badges (Issue #29). */
  setRevisions(revisions: Revisions | undefined): void {
    this._revisions = revisions;
    this._render();
  }

  /** Zurücksetzen (neues Projekt / neue Wand). */
  reset(): void {
    this._sections = [];
    this._runs.clear();
    this._results.clear();
    this._revisions = undefined;
    this._busy = null;
    this._render();
  }

  private async _export(sectionId: string): Promise<void> {
    if (this._busy) return;
    this._busy = sectionId;
    this.status.textContent = `DRL für Abschnitt ${sectionId} wird erzeugt …`;
    this._render();
    try {
      const result = await this.callbacks.onExport(sectionId);
      this._results.set(sectionId, {
        complete: result.complete,
        note: result.note,
        drlPath: result.drl_path,
      });
      // Revisionsstände aus der Antwort aktualisieren (Export nicht mehr veraltet).
      const job = result.print_jobs.find((j) => j.job_id === result.job_id);
      if (job) this._revisions = job.revisions;
      this.status.textContent = result.complete
        ? `DRL für Abschnitt ${sectionId} vollständig erzeugt (gemessenes Setup).`
        : `DRL für Abschnitt ${sectionId} erzeugt — unvollständig: ${result.note}`;
    } catch (err) {
      this.status.textContent = `Fehler beim Export von Abschnitt ${sectionId}: ${err}`;
    } finally {
      this._busy = null;
      this._render();
    }
  }

  /** Zeichnet die veraltet-Badges je Stufe aus den Revisionsständen (ADR-007). */
  private _renderStages(): void {
    this.stages.replaceChildren();
    const statuses = allStageStatuses(this._revisions);
    for (const name of ["druckplan", "simulation", "export"] as OutputName[]) {
      const status = statuses[name];
      const badge = document.createElement("span");
      badge.className = `stage-badge stage-${status}`;
      badge.textContent = `${outputLabel(name)}: ${stageStatusLabel(status)}`;
      if (status === "stale") {
        badge.title =
          "Eine vorgelagerte Eingabe (Wand, Roboter, Endeffektor oder Schnittplan) " +
          "hat sich geändert — dieser Stand ist veraltet. Neu erzeugen hebt die " +
          "Markierung auf; gelöscht wird nichts.";
      }
      this.stages.append(badge);
    }
  }

  private _render(): void {
    this._renderStages();
    const enabled = this._apiAvailable && this._projectOpen && this._busy === null;
    this.empty.hidden = this._sections.length > 0;
    this.sectionsList.replaceChildren();

    for (const s of this._sections) {
      const li = document.createElement("li");
      li.className = "export-section";

      const name = document.createElement("strong");
      name.textContent = `#${s.order} ${s.section_id}`;

      const hasRun = this._runs.has(s.section_id);
      const result = this._results.get(s.section_id);
      const info = document.createElement("span");
      info.className = "export-info";
      if (result) {
        info.textContent = result.complete
          ? "DRL vollständig — gemessenes Setup vorhanden."
          : `DRL unvollständig — ${result.note}`;
        info.classList.add(result.complete ? "export-complete" : "export-incomplete");
      } else if (hasRun) {
        info.textContent = "Bereit zum Export (Abschnitts-Lauf vorhanden).";
      } else {
        info.textContent = "Noch nicht simuliert — zuerst im Reiter Simulation slicen + simulieren.";
      }

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "export-btn";
      const busyHere = this._busy === s.section_id;
      btn.textContent = busyHere ? "Erzeugt …" : result ? "DRL neu erzeugen" : "DRL exportieren";
      btn.disabled = !enabled || !hasRun;
      btn.addEventListener("click", () => void this._export(s.section_id));

      li.append(name, info, btn);
      this.sectionsList.append(li);
    }
  }
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}
