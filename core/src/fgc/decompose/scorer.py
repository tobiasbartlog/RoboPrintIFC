"""Billiger Zerlegungs-Scorer (Issue #216, PRD #183 Stufe 3): Kriterienwerte je Kandidat.

Liefert je Band-Raster-Kandidat (``fgc.decompose.kandidaten``) die
**injizierten** :class:`~fgc.decompose.objective.KriterienWerte` der
Zielfunktion (#212) — ohne Pruef-Tuer, ohne IK je Kandidat:

- **Erreichbarkeit (K.-o.)** und **Anzahl Standplaetze (Umsetzvorgaenge)** aus
  der Reichweitenkarte (#210) ueber die #214-Abfrage ``standplatz_fuer_reihe``
  (punktweises **Minimum ueber die Bahnposen** je Hoehenreihe, Vahrenkamp
  Gl. 3): eine Reihe ist gedeckt, wenn mindestens ein Standplatz-Kandidat ihre
  Unter- UND Oberkante erreicht; aufeinanderfolgende Reihen, die einen
  gemeinsamen Standplatz teilen (UND der Reihen-Masken nicht leer), werden
  bottom-up zu **einem** Umsetzvorgang gruppiert (Min-Aggregation).
- **Kinematische Marge** als Karten-Proxy „Standplatz-Robustheit": wie weit
  (mm, Chessboard) darf die Basis verschoben werden, ohne die Reihendeckung zu
  verlieren (Distanztransformation der Standplatz-Maske × Gitterschritt).
  PROVISORISCH bis zur Eichung an echten Kandidaten nach AP 2 (wie die
  Quantisierungs-Schrittweiten in #212).
- **Fugenflaeche, Volumen-c_v und Raycast-Inselkarte** per Masken-/Matrix-
  bewertung nach Han (Gl.-6–9-Muster: alle Teil-Kennzahlen aus **einem**
  bool-Raster der Wandfront per vektorisierter numpy-Auswertung; Inselzaehlung
  im Z-Chunking-Raycast-Muster, dort 1 mm auf Desktop-Teilen — im Bau-Massstab
  haelt :data:`INSEL_RASTER_MM` = 10 mm die Matrix klein). Oeffnungen liefern
  Aufrufer als injizierte Maske (``False`` = kein Material); der Default ist
  die volle Rechteckfront (``WallSurface`` kennt keine Oeffnungen).

Alles **Schaetzung/Vorfilter** (Ehrlichkeitsregel ADR-007/#164): „geprueft
frei" entsteht ausschliesslich in der Pruef-Tuer — die Beam-Suche (#217)
schickt nur Ueberlebende dorthin. Deterministisch: gleicher Input ⇒ bit-gleiche
Werte (US 19/25); keine Zufallsquellen, stabile Tie-Breaks (kleinster Index).

Einheiten strikt nach ADR-006: Millimeter, Radiant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy import ndimage

from fgc.decompose.kandidaten import BandRasterKandidat
from fgc.decompose.objective import KriterienWerte
from fgc.domain.tool import ToolDef
from fgc.placement.evaluate import SAMPLE_SPACING_MM, PlacementOption, WallSurface
from fgc.placement.reachmap import standplatz_fuer_reihe

if TYPE_CHECKING:
    from fgc.kinematics.reachability import ReachabilityMap

__all__ = [
    "INSEL_RASTER_MM",
    "BilligerScorer",
    "KandidatBewertung",
    "Standplatz",
    "fugenflaeche_mm2",
    "raycast_inselkarte",
    "standplatz_gitter",
    "volumen_cv",
    "wand_maske",
]

#: Default-Rasterkante (mm) der Masken-/Inselbewertung. Z-Chunking nutzt 1 mm
#: auf Desktop-Teilen; im Bau-Massstab (Waende in Metern) haelt 10 mm die Matrix
#: klein bei stabiler Inseltopologie. PROVISORISCH (Eichung nach AP 2, wie die
#: #212-Schrittweiten).
INSEL_RASTER_MM = 10.0


# ---------------------------------------------------------------------------
# Masken-/Matrixbewertung (Han Gl. 6–9-Muster): ein Raster, alle Teil-Kennzahlen
# ---------------------------------------------------------------------------


def wand_maske(wall: WallSurface, raster_mm: float = INSEL_RASTER_MM) -> np.ndarray:
    """Bool-Raster der Wandfront: Zeilen = Hoehe (unten → oben), Spalten = Laenge.

    Default volle Rechteckfront (``WallSurface`` kennt keine Oeffnungen);
    Aufrufer mit Oeffnungswissen bauen eine Maske gleicher Bauart und setzen
    Oeffnungszellen ``False``. Zellzahl aus Rundung — die effektive Zellkante
    ist ``laenge/n`` (≈ ``raster_mm``), damit die Maske die Front exakt deckt.
    """
    if raster_mm <= 0 or not math.isfinite(raster_mm):
        raise ValueError(f"raster_mm muss positiv/endlich sein, ist {raster_mm!r}.")
    nx = max(1, int(round(wall.length_mm / raster_mm)))
    nz = max(1, int(round(wall.height_mm / raster_mm)))
    return np.ones((nz, nx), dtype=bool)


def _teil_indizes(
    maske_form: tuple[int, ...], kandidat: BandRasterKandidat
) -> tuple[np.ndarray, np.ndarray]:
    """Teil-Index je Rasterzeile/-spalte (Zellmitten in die Band-Grenzen digitalisiert)."""
    nz, nx = maske_form
    wall = kandidat.wall
    if wall.length_mm > 0:
        xs = (np.arange(nx) + 0.5) / nx  # Zellmitten, normiert 0..1 ab linker Kante
        col = np.minimum((xs * kandidat.n_length).astype(int), kandidat.n_length - 1)
    else:
        col = np.zeros(nx, dtype=int)
    if wall.height_mm > 0:
        zs = (np.arange(nz) + 0.5) / nz
        row = np.minimum((zs * kandidat.n_height).astype(int), kandidat.n_height - 1)
    else:
        row = np.zeros(nz, dtype=int)
    return row, col


def fugenflaeche_mm2(maske: Any, kandidat: BandRasterKandidat) -> float:
    """Fugenflaeche (mm²) ueber die inneren Schnitte, Masken-basiert.

    Je Schnitt zaehlen die Materialzellen-**Paare** beidseits der Schnittlinie
    (Han-Matrixmuster): Paaranzahl × Zellkante × Wanddicke — eine Fuge durch
    eine Oeffnung traegt nichts. Ohne Dicke (``thickness_mm ≤ 0``) ehrlich 0.
    """
    m = np.asarray(maske, dtype=bool)
    nz, nx = m.shape
    wall = kandidat.wall
    dicke = max(0.0, wall.thickness_mm)
    zell_x = wall.length_mm / nx
    zell_z = wall.height_mm / nz
    flaeche = 0.0
    for cut in kandidat.cuts:
        if cut.orientation == "vertical" and wall.length_mm > 0:
            b = int(round((cut.position_mm + wall.length_mm / 2.0) / wall.length_mm * nx))
            if 0 < b < nx:
                paare = int(np.count_nonzero(m[:, b - 1] & m[:, b]))
                flaeche += paare * zell_z * dicke
        elif cut.orientation == "horizontal" and wall.height_mm > 0:
            b = int(round(cut.position_mm / wall.height_mm * nz))
            if 0 < b < nz:
                paare = int(np.count_nonzero(m[b - 1, :] & m[b, :]))
                flaeche += paare * zell_x * dicke
    return float(flaeche)


def volumen_cv(maske: Any, kandidat: BandRasterKandidat) -> float:
    """Volumen-Gleichmaessigkeit ``c_v = σ/μ`` der Teil-Volumina (Stamatopoulos Gl. 1).

    Masken-basiert: Volumen ∝ Materialzellen je Teil (Zellflaeche × Dicke kuerzt
    sich im Quotienten). Leere Maske (μ = 0) ⇒ 0.0 (neutral, kein NaN).
    """
    m = np.asarray(maske, dtype=bool)
    row, col = _teil_indizes(m.shape, kandidat)
    teil_id = row[:, None] * kandidat.n_length + col[None, :]
    counts = np.bincount(teil_id[m].ravel(), minlength=kandidat.n_parts).astype(float)
    mean = counts.mean()
    if mean <= 0:
        return 0.0
    return float(counts.std() / mean)


def raycast_inselkarte(
    maske: Any, kandidat: BandRasterKandidat
) -> tuple[np.ndarray, tuple[int, ...]]:
    """Inselkarte nach Z-Chunking-Muster: zusammenhaengende Materialinseln je Teil.

    Rueckgabe ``(labels, inseln_je_teil)``: ``labels`` ist ein int-Raster in
    Masken-Bauart (0 = kein Material; Inseln fortlaufend nummeriert in
    Teil-Reihenfolge unten → oben, links → rechts — deterministisch);
    ``inseln_je_teil`` die Inselzahl je Teil in derselben Reihenfolge
    (Teil = Reihe × Spalte, wie die ``propose``-Druckreihenfolge). Mehr als
    eine Insel je Teil = Fragment-Indiz (Wu-Fragmentschutz-Analogon) — ein
    **Befund fuer die Suche** (#217: Verworfen-Grund „Fragment", US 10),
    kein Gate. 4er-Nachbarschaft (``scipy.ndimage.label``-Default).
    """
    m = np.asarray(maske, dtype=bool)
    row, col = _teil_indizes(m.shape, kandidat)
    labels = np.zeros(m.shape, dtype=int)
    inseln: list[int] = []
    vergeben = 0
    for r in range(kandidat.n_height):
        in_reihe = (row == r)[:, None]
        for c in range(kandidat.n_length):
            teil = m & in_reihe & (col == c)[None, :]
            teil_labels, n = ndimage.label(teil)
            if n:
                labels[teil] = teil_labels[teil] + vergeben
                vergeben += int(n)
            inseln.append(int(n))
    return labels, tuple(inseln)


# ---------------------------------------------------------------------------
# Standplaetze aus der Karte (#210/#214): Min-Aggregation je Reihe + Gruppierung
# ---------------------------------------------------------------------------


def standplatz_gitter(
    wall: WallSurface, reach_map: ReachabilityMap, *, schritt_mm: float
) -> tuple[np.ndarray, tuple[int, int]]:
    """Deterministisches Standplatz-Kandidatengitter ``(N, 2)`` im Wandsystem.

    ``x`` symmetrisch ueber Wandlaenge + Kartenreichweite, ``y`` vor der
    Wandfront (ab einem Gitterschritt vor der Flaeche, ADR-025-Konvention
    ``y = Dicke/2 + Abstand``) bis zur Kartenreichweite — weiter draussen ist
    laut Karte nichts erreichbar (#210, extent deckt die volle Armlaenge).
    Rueckgabe: Punkte + Gitterform ``(n_y, n_x)`` (fuer die Margen-Erosion).
    """
    if schritt_mm <= 0 or not math.isfinite(schritt_mm):
        raise ValueError(f"schritt_mm muss positiv/endlich sein, ist {schritt_mm!r}.")
    half = wall.length_mm / 2.0
    reichweite = float(reach_map.extent_mm)
    nx_halb = int(math.floor((half + reichweite) / schritt_mm))
    xs = np.arange(-nx_halb, nx_halb + 1) * schritt_mm
    ny = max(1, int(math.floor(reichweite / schritt_mm)))
    y0 = max(0.0, wall.thickness_mm) / 2.0
    ys = y0 + np.arange(1, ny + 1) * schritt_mm
    gx, gy = np.meshgrid(xs, ys)  # Zeilen = y, Spalten = x
    punkte = np.stack([gx.ravel(), gy.ravel()], axis=1)
    return punkte, (len(ys), len(xs))


@dataclass(frozen=True)
class Standplatz:
    """Ein Umsetzvorgang: gemeinsamer Standplatz fuer aufeinanderfolgende Reihen.

    ``reihen`` = 0-basierte Hoehenreihen-Indizes (unten → oben), die dieser
    Standplatz komplett deckt; ``lateral_mm``/``y_mm`` = Basis im Wandsystem
    (``y`` ab Mittelebene — Ruecken zur Platzierungs-Konvention ueber
    ``fgc.placement.evaluate.standoff_from_base_y``); ``stand_height_mm``
    absolut ueber dem Boden (Issue #132). ``marge_mm`` = Karten-Proxy
    Standplatz-Robustheit (Verschiebe-Spielraum, Chessboard). Schaetzung, kein
    Urteil (ADR-007) — #217 macht daraus Platzierungs-Vorschlaege.
    """

    reihen: tuple[int, ...]
    lateral_mm: float
    y_mm: float
    stand_height_mm: float
    marge_mm: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "reihen": list(self.reihen),
            "lateral_mm": self.lateral_mm,
            "y_mm": self.y_mm,
            "stand_height_mm": self.stand_height_mm,
            "marge_mm": self.marge_mm,
        }


@dataclass(frozen=True)
class KandidatBewertung:
    """Die billige Bewertung eines Kandidaten: #212-Kriterienwerte + Diagnose.

    ``werte`` speist :func:`~fgc.decompose.objective.candidate_key`/
    ``compare_candidates`` direkt; ``reihen_gedeckt``/``standplaetze``/
    ``inseln_je_teil`` sind die Diagnose fuer Verworfen-Gruende (US 10) und den
    Metriken-Katalog (US 20) der Beam-Suche (#217). Reine Daten, bit-vergleichbar.
    """

    kandidat: BandRasterKandidat
    werte: KriterienWerte
    reihen_gedeckt: tuple[bool, ...]
    standplaetze: tuple[Standplatz, ...]
    inseln_je_teil: tuple[int, ...]

    @property
    def reichweite_anteil(self) -> float:
        """Anteil karten-gedeckter Hoehenreihen (Schaetzung, US 7/20)."""
        if not self.reihen_gedeckt:
            return 0.0
        return sum(self.reihen_gedeckt) / len(self.reihen_gedeckt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kandidat": self.kandidat.key,
            "n_length": self.kandidat.n_length,
            "n_height": self.kandidat.n_height,
            "werte": {
                "erreichbar": self.werte.erreichbar,
                "umsetzvorgaenge": self.werte.umsetzvorgaenge,
                "fugenflaeche_mm2": self.werte.fugenflaeche_mm2,
                "kinematische_marge_mm": self.werte.kinematische_marge_mm,
                "volumen_cv": self.werte.volumen_cv,
            },
            "reichweite_anteil": self.reichweite_anteil,
            "reihen_gedeckt": list(self.reihen_gedeckt),
            "standplaetze": [s.to_dict() for s in self.standplaetze],
            "inseln_je_teil": list(self.inseln_je_teil),
        }


class BilligerScorer:
    """Bindet Karte + Wand + Endeffektor + Verfahrens-Parameter einmal (#216).

    ``bewerte(kandidat)`` liefert die :class:`KandidatBewertung` — genau die
    ``bewerte``-Rolle der :class:`~fgc.decompose.strategie.RasterAufgabe`.
    Reihen-Masken werden ueber Kandidaten hinweg gecacht (gleiche Hoehenlinie ⇒
    eine Karten-Abfrage): der Cache ist reine Memoisation derselben
    deterministischen Abfrage, das Ergebnis bleibt bit-gleich.

    ``stand_heights_mm`` = zulaessige Aufstellhoehen (absolut, Issue #132;
    Default nur Boden — #217 reicht den Workstation-Podesthoehen-Satz durch,
    Aufstell-Toggle-Muster #81); ``gitter_schritt_mm`` Default = Kartenzelle
    (feiner lohnt nicht: die Karte rundet auf ihre Knoten, #210).

    ``fixe_platzierung`` (Issue #237) schaltet den **Modul-Modus** (ADR-022):
    statt einer Standplatz-Suche vor der Wand gilt die **eine feste**
    Workstation-Platzierung, und jede Hoehenreihe wird **modul-lokal** bewertet
    (jedes Modul wird am Druckort ab ``z = 0`` gedruckt — die absolute Wandhoehe
    der Reihe ist dort ohne Belang; genau daran scheiterte der Vorfilter im
    Denkmal-Befund #237: 256/256 Kandidaten „reichweite" bei exakt bewertetem
    ``reachable_fraction = 1.0``). ``stand_heights_mm`` wird dann von der
    Aufstellhoehe der festen Platzierung ersetzt.
    """

    def __init__(
        self,
        reach_map: ReachabilityMap,
        wall: WallSurface,
        tool: ToolDef,
        *,
        maske: Any | None = None,
        raster_mm: float = INSEL_RASTER_MM,
        spacing_mm: float = SAMPLE_SPACING_MM,
        stand_heights_mm: tuple[float, ...] = (0.0,),
        gitter_schritt_mm: float | None = None,
        fixe_platzierung: PlacementOption | None = None,
    ) -> None:
        if not stand_heights_mm:
            raise ValueError("stand_heights_mm darf nicht leer sein (mindestens Boden 0.0).")
        self._map = reach_map
        self._wall = wall
        self._tool = tool
        self._maske = (
            wand_maske(wall, raster_mm) if maske is None else np.asarray(maske, dtype=bool)
        )
        self._spacing_mm = float(spacing_mm)
        self._schritt_mm = float(gitter_schritt_mm or reach_map.cell_mm)
        self._fix = fixe_platzierung
        if fixe_platzierung is not None:
            # Modul-Modus (#237): genau EIN Standplatz-Kandidat — die feste Basis am
            # Druckort (ADR-025-Konvention ``y = Dicke/2 + Abstand``, wie
            # :func:`standplatz_gitter`); Aufstellhoehe aus der festen Platzierung.
            self._heights = (float(fixe_platzierung.stand_height_mm),)
            y = max(0.0, wall.thickness_mm) / 2.0 + float(fixe_platzierung.standoff_mm)
            self._gitter = np.array([[float(fixe_platzierung.lateral_mm), y]])
            self._gitter_form = (1, 1)
        else:
            self._heights = tuple(float(h) for h in stand_heights_mm)
            self._gitter, self._gitter_form = standplatz_gitter(
                wall, reach_map, schritt_mm=self._schritt_mm
            )
        # Memoisation je Hoehenlinie: (gerundetes z) -> bool (n_heights, N).
        self._linien_cache: dict[float, np.ndarray] = {}
        # Modul-Modus: Memoisation je Zellgroesse ((laenge, hoehe) -> gedeckt) —
        # alle Reihen eines Kandidaten sind modul-lokal identisch.
        self._modul_cache: dict[tuple[float, float], bool] = {}

    # -- Karten-Seite: Reihen-Deckung + Standplaetze ---------------------------

    def _linien_maske(self, z_mm: float) -> np.ndarray:
        """Standplatz-Maske einer Hoehenlinie: ``(n_heights, N)`` ueber das Gitter."""
        key = round(float(z_mm), 3)
        cached = self._linien_cache.get(key)
        if cached is None:
            cached = np.stack(
                [
                    standplatz_fuer_reihe(
                        self._map, self._wall, self._tool, self._gitter, h,
                        row_z_mm=key, spacing_mm=self._spacing_mm,
                    )
                    for h in self._heights
                ],
                axis=0,
            )
            self._linien_cache[key] = cached
        return cached

    def _standplatz(self, reihen: tuple[int, ...], maske: np.ndarray) -> Standplatz:
        """Bester Standplatz einer Gruppe: max. Verschiebe-Spielraum (stabile Tie-Breaks).

        Je Aufstellhoehe wird die 2D-Gitterscheibe per Chessboard-Distanz-
        transformation (Rand = ungedeckt) bewertet; es gewinnt die Zelle mit der
        groessten Distanz — Gleichstand: kleinste Hoehe, dann kleinster
        Zellindex (Zeilen = y aufsteigend, Spalten = x aufsteigend).
        """
        ny, nx = self._gitter_form
        beste: tuple[int, int, int] | None = None  # (Distanz, Hoehen-Index, Zellindex)
        for hi in range(maske.shape[0]):
            scheibe = maske[hi].reshape(ny, nx)
            if not scheibe.any():
                continue
            dist = ndimage.distance_transform_cdt(
                np.pad(scheibe, 1), metric="chessboard"
            )[1:-1, 1:-1]
            flach = dist.ravel()
            idx = int(np.argmax(flach))  # Gleichstand: kleinster Index (deterministisch)
            d = int(flach[idx])
            if beste is None or d > beste[0]:
                beste = (d, hi, idx)
        assert beste is not None  # Aufrufer reicht nur deckbare Gruppen herein
        d, hi, idx = beste
        return Standplatz(
            reihen=reihen,
            lateral_mm=float(self._gitter[idx, 0]),
            y_mm=float(self._gitter[idx, 1]),
            stand_height_mm=self._heights[hi],
            marge_mm=float((d - 1) * self._schritt_mm),
        )

    # -- Modul-Modus (#237): Reihen modul-lokal an der festen Platzierung ------

    def _modul_reihe_gedeckt(self, cell_length_mm: float, cell_height_mm: float) -> bool:
        """Deckt die feste Basis eine Modul-Zelle ``(Laenge × Hoehe)`` laut Karte?

        Modul-lokal: die Zelle steht am Druckort ab ``z = 0`` (ADR-022), gedeckt
        heisst Unter- UND Oberkante erreichbar (Min-Aggregation wie #214). Memoisiert
        je Zellgroesse — alle Reihen eines Band-Kandidaten sind gleich gross.
        """
        key = (round(float(cell_length_mm), 3), round(float(cell_height_mm), 3))
        cached = self._modul_cache.get(key)
        if cached is None:
            cell = WallSurface(key[0], key[1], self._wall.thickness_mm)
            unten = standplatz_fuer_reihe(
                self._map, cell, self._tool, self._gitter, self._heights[0],
                row_z_mm=0.0, spacing_mm=self._spacing_mm,
            )
            oben = standplatz_fuer_reihe(
                self._map, cell, self._tool, self._gitter, self._heights[0],
                row_z_mm=key[1], spacing_mm=self._spacing_mm,
            )
            cached = bool((unten & oben).any())
            self._modul_cache[key] = cached
        return cached

    def _bewerte_modul(self, kandidat: BandRasterKandidat) -> KandidatBewertung:
        """Die billige Bewertung im Modul-Modus (#237): feste Basis, modul-lokale Reihen.

        Jede Reihe wird als Modul-Zelle ab ``z = 0`` bewertet (alle Reihen eines
        Kandidaten identisch); gedeckt ⇒ **ein** Umsetzvorgang (die Basis steht fest,
        der Kran setzt Module — kein Roboter-Umsetzen), ungedeckt ⇒ ehrlich eine
        Gruppe je Reihe. Die kinematische Marge ist 0 (die feste Basis hat keinen
        Verschiebe-Spielraum — der Karten-Proxy traegt hier nicht); der Komparator
        (#212) unterscheidet Kandidaten dann ueber die Fugenflaeche (weniger Teile
        zuerst). Front-Kennzahlen (Fugenflaeche/c_v/Inseln) wie im Abschnitts-Modus.
        """
        assert self._fix is not None
        cell_len = self._wall.length_mm / kandidat.n_length
        cell_h = self._wall.height_mm / kandidat.n_height
        gedeckt_ein = self._modul_reihe_gedeckt(cell_len, cell_h)
        n_h = kandidat.n_height
        gedeckt = (gedeckt_ein,) * n_h
        if gedeckt_ein:
            standplaetze: tuple[Standplatz, ...] = (
                Standplatz(
                    reihen=tuple(range(n_h)),
                    lateral_mm=float(self._gitter[0, 0]),
                    y_mm=float(self._gitter[0, 1]),
                    stand_height_mm=self._heights[0],
                    marge_mm=0.0,
                ),
            )
            umsetz = 1.0
        else:
            standplaetze = ()
            umsetz = float(n_h)
        werte = KriterienWerte(
            erreichbar=gedeckt_ein,
            umsetzvorgaenge=umsetz,
            fugenflaeche_mm2=fugenflaeche_mm2(self._maske, kandidat),
            kinematische_marge_mm=0.0,
            volumen_cv=volumen_cv(self._maske, kandidat),
        )
        _labels, inseln = raycast_inselkarte(self._maske, kandidat)
        return KandidatBewertung(
            kandidat=kandidat,
            werte=werte,
            reihen_gedeckt=gedeckt,
            standplaetze=standplaetze,
            inseln_je_teil=inseln,
        )

    # -- Die eine Tuer: Kandidat -> Kriterienwerte -----------------------------

    def bewerte(self, kandidat: BandRasterKandidat) -> KandidatBewertung:
        """Bewertet einen Kandidaten billig — Karte + Masken-Matrix, keine Pruef-Tuer.

        Reihen-Deckung = Min-Aggregation (#214) ueber Unter- UND Oberkante jeder
        Hoehenreihe; Umsetzvorgaenge = bottom-up gruppierte Standplaetze
        (aufeinanderfolgende Reihen mit gemeinsamem Standplatz teilen einen);
        Marge = kleinste Standplatz-Robustheit ueber die Gruppen (die
        schlechteste Stelle entscheidet, #98-Muster). Unerreichbare Kandidaten
        (mindestens eine ungedeckte Reihe) tragen ``erreichbar=False`` — das
        harte K.-o. des Komparators (#212) — und Marge 0.

        Im **Modul-Modus** (``fixe_platzierung``, Issue #237) laeuft stattdessen
        :meth:`_bewerte_modul` — modul-lokale Reihen an der festen Platzierung.
        """
        if self._fix is not None:
            return self._bewerte_modul(kandidat)
        reihen = kandidat.row_bounds_mm()
        reihen_masken = [
            self._linien_maske(z0) & self._linien_maske(z1) for z0, z1 in reihen
        ]
        gedeckt = tuple(bool(m.any()) for m in reihen_masken)

        # Min-Aggregation → Umsetzvorgaenge: bottom-up mergen, solange die
        # UND-Maske der Gruppe nicht leer wird (ein Standplatz deckt alle Reihen
        # der Gruppe — Vahrenkamp-Minimum ueber Reihen statt nur Posen).
        gruppen: list[tuple[int, ...]] = []
        gruppen_masken: list[np.ndarray | None] = []
        for i, m in enumerate(reihen_masken):
            deckbar = bool(m.any())
            if deckbar and gruppen and gruppen_masken[-1] is not None:
                kombiniert = gruppen_masken[-1] & m
                if kombiniert.any():
                    gruppen[-1] = (*gruppen[-1], i)
                    gruppen_masken[-1] = kombiniert
                    continue
            gruppen.append((i,))
            gruppen_masken.append(m if deckbar else None)

        standplaetze = tuple(
            self._standplatz(reihen_idx, m)
            for reihen_idx, m in zip(gruppen, gruppen_masken, strict=True)
            if m is not None
        )
        erreichbar = all(gedeckt)
        marge = (
            min(s.marge_mm for s in standplaetze) if erreichbar and standplaetze else 0.0
        )

        werte = KriterienWerte(
            erreichbar=erreichbar,
            umsetzvorgaenge=float(len(gruppen)),
            fugenflaeche_mm2=fugenflaeche_mm2(self._maske, kandidat),
            kinematische_marge_mm=marge,
            volumen_cv=volumen_cv(self._maske, kandidat),
        )
        _labels, inseln = raycast_inselkarte(self._maske, kandidat)
        return KandidatBewertung(
            kandidat=kandidat,
            werte=werte,
            reihen_gedeckt=gedeckt,
            standplaetze=standplaetze,
            inseln_je_teil=inseln,
        )
