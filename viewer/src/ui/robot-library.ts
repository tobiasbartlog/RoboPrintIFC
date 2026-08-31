/**
 * Roboter-Bibliothek — schreibgeschützte Galerie (Issue #76, PRD #69).
 *
 * Zeigt den Roboterbestand aus `GET /robots` als Karten (Name, Reichweite,
 * Traglast) mit einem statischen, eingecheckten PNG-Thumbnail je Roboter — KEIN
 * Live-FK-Render. Bewusst **read-only**: kein Anlegen/Bearbeiten/Löschen, keine
 * Formulare. Ein funktionsfähiger neuer Roboter verlangt Solver-Konstanten
 * (`_START`/`_SIGNS`), vendored per-Glied-Meshes und die Viewer-DH — das ist
 * Vendoring-Arbeit, kein Formular (Scope-Klärung im Parent #69).
 *
 * Spiegelt den Karten-Look der bestehenden Galerien (`tool-library.ts`,
 * `workstation-library.ts`), aber ohne Aktionen. Die Fach-Formatierung + die
 * Roboter→PNG-Abbildung liegen rein in `robot-library-payload.ts` (ADR-007);
 * diese Klasse besitzt nur das DOM und lädt über einen Callback. Fehlt das PNG,
 * greift ein Platzhalter statt eines Absturzes (`img.onerror`).
 */

import type { RobotDef } from "../api/projects";
import { robotThumbnailPath, summarizeRobot } from "./robot-library-payload";

export interface RobotLibraryCallbacks {
  /** Roboterbestand laden (GET /robots). Read-only — kein Schreibpfad. */
  loadRobots(): Promise<RobotDef[]>;
}

export class RobotLibrary {
  private readonly cards = byId<HTMLElement>("rob-cards");
  private readonly empty = byId<HTMLElement>("rob-empty");
  private readonly statusEl = byId<HTMLElement>("rob-status");
  private readonly apiWarning = byId<HTMLElement>("rob-api-warning");

  private _apiAvailable = false;

  constructor(private readonly callbacks: RobotLibraryCallbacks) {}

  setApiAvailable(available: boolean): void {
    this._apiAvailable = available;
    this.apiWarning.hidden = available;
  }

  setStatus(text: string): void {
    this.statusEl.textContent = text;
  }

  /** Öffnet die Galerie und lädt den Bestand neu (read-only). */
  async openGallery(): Promise<void> {
    await this.reload();
  }

  /** Lädt den Bestand (GET /robots) und rendert die Karten. */
  async reload(): Promise<void> {
    if (!this._apiAvailable) return;
    try {
      const robots = await this.callbacks.loadRobots();
      this.render(robots);
      this.setStatus("");
    } catch (err) {
      this.setStatus(`Roboterbestand konnte nicht geladen werden: ${err}`);
    }
  }

  /** Rendert die Kartenliste aus einer Roboter-Liste (rein DOM, ohne Netz/GL). */
  render(robots: RobotDef[]): void {
    this.cards.replaceChildren();
    this.empty.hidden = robots.length > 0;
    for (const robot of robots) this.cards.append(this.buildCard(robot));
  }

  private buildCard(robot: RobotDef): HTMLElement {
    const summary = summarizeRobot(robot);
    const card = el("div", "lib-card rob-card");
    card.dataset.robot = robot.name;

    // Statisches PNG-Thumbnail; fehlt es, ersetzt onerror durch einen
    // Platzhalter statt eines Absturzes (Akzeptanzkriterium #76).
    const img = document.createElement("img");
    img.className = "lib-card-thumb";
    img.alt = `${robot.name} — Vorschau`;
    img.src = robotThumbnailPath(robot.name);
    img.addEventListener("error", () => {
      const ph = el("div", "lib-card-thumb-placeholder");
      ph.textContent = "Kein Vorschaubild";
      img.replaceWith(ph);
    });
    card.append(img);

    const body = el("div", "lib-card-body");
    const head = el("div", "rob-card-head");
    const name = el("div", "lib-card-name");
    name.textContent = robot.name;
    const badge = el("span", "rob-card-readonly");
    badge.textContent = "read-only";
    badge.title = "Kinematik hart verdrahtet — nicht bearbeitbar";
    head.append(name, badge);

    const reach = el("div", "lib-card-meta rob-card-reach");
    reach.textContent = summary.reachText;
    const payload = el("div", "lib-card-meta rob-card-payload");
    payload.textContent = summary.payloadText;
    const workspace = el("div", "lib-card-meta rob-card-workspace");
    workspace.textContent = summary.workspaceText + (summary.provisional ? " (vorläufig)" : "");

    body.append(head, reach, payload, workspace);
    card.append(body);
    return card;
  }
}

function el(tag: string, className: string): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  return node;
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element #${id} fehlt in index.html`);
  return el as T;
}
