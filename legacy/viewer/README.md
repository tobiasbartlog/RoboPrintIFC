# fgc-viewer

Statische Web-App (Vite + TypeScript + three.js). Zustandsloser Abspieler
(ADR-007): lädt einen Laufordner aus `runs/`, rendert Wand-Mesh
(`wallspec.json`), Pfade (`toolpath.json`) mit Layer-Slider und den
Gebäudekontext (`context.json`, restliches IFC-Modell als Geister-Mesh).
Er rechnet nichts — alles Sichtbare hat der Core vorher als Artefakt erzeugt.

## Bedienung

Bequemster Weg: `.\fgc start` im Repo-Root — der Wizard sliced eine Wand,
startet diesen Dev-Server bei Bedarf und öffnet den Lauf im Browser.
Manuell:

```bash
cd viewer
npm install   # einmalig
npm run dev   # http://localhost:5173
```

Dann **„Laufordner öffnen…"** und einen `runs/<lauf>/`-Ordner wählen —
oder per URL-Parameter direkt laden (Dev-Server):

```
http://localhost:5173/?run=/@fs/C:/…/RoboPrintIFC/runs/<lauf>
```

- **Schicht-Slider**: zeigt Schichten 0…n kumulativ; „nur aktive Schicht" isoliert eine.
- **Travel-Wege / Wand-Mesh / Gebäudekontext**: ein-/ausblendbar
  (Kontext-Schalter erscheint nur, wenn der Lauf ein `context.json` hat).
- Print-Pfade terrakotta, Travel grau-blau, Wand transparent mit Kanten,
  Kontext als dunkles Geister-Mesh; die Kamera fokussiert die Wand.

## Struktur (modular)

- `src/artifacts/` — TS-Typen der Schemas + Laufordner-Lader (Picker & URL)
- `src/scene/` — three.js-Grundgerüst (Renderer, Kamera, Licht, z-hoch→y-hoch)
- `src/render/` — je ein Renderer pro Artefakt (`wall.ts`, `toolpath.ts`)
- `src/ui/` — Seitenpanel (Slider, Toggles, Laufmetadaten)
- `src/main.ts` — verdrahtet nur
