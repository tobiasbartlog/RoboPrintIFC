"""Datenmodell des Zerlegungsvorschlags (Issue #24).

Ein **Zerlegungsvorschlag** teilt eine Wand in nacheinander druckbare
**Abschnitte** (Zerlegungsart „Abschnitt", in place — `core/CONTEXT.md`), wenn
keine einzelne Platzierung 100 % der Wand erreicht. Ergebnis ist eine Liste von
Paaren (**Abschnitt**, **Platzierung**): jeder Abschnitt wird von seiner eigenen
Platzierung aus zu 100 % erreicht; Druckreihenfolge unten → oben.

Reine Daten (keine Kinematik, kein Mesh) — Koordinaten im Wand-System nach
ADR-006: ``x`` entlang der Wandlaenge (zentriert um 0), ``z`` entlang der Hoehe
(0 … Hoehe), Millimeter. „Segment" ist bewusst vermieden (im Slicer vergeben:
`segment_id`).
"""

from __future__ import annotations

from dataclasses import dataclass

from fgc.placement import PlacementOption, WallSurface

#: Die beiden Zerlegungsarten (core/CONTEXT.md, ADR-022): „abschnitt" = in place
#: an der Endposition gedruckt (Roboter wird umgesetzt); „modul" = stehend in
#: Einbauorientierung an der Workstation vorproduziert (feste Platzierung,
#: Issue #90) — Fuegegeometrie folgt spaeter, v1 mit ebenen Stossfugen.
DECOMPOSITION_KINDS = ("abschnitt", "modul")

#: Schnittebenen-Ausrichtungen: horizontal teilt die Hoehe (Hoehenstufen),
#: vertikal teilt die Laenge (Laengenteilung).
CUT_ORIENTATIONS = ("horizontal", "vertical")


@dataclass(frozen=True)
class Cut:
    """Eine ebene, achsparallele Schnittebene im Wand-Koordinatensystem.

    ``orientation`` = ``"horizontal"`` (Ebene bei ``z = position_mm``, teilt die
    Hoehe) oder ``"vertical"`` (Ebene bei ``x = position_mm``, teilt die Laenge).
    """

    orientation: str
    position_mm: float


@dataclass(frozen=True)
class Section:
    """Ein **Abschnitt**: Teilrechteck der Wandfront + Druckreihenfolge.

    Grenzen im Wand-System: ``x0..x1`` entlang der Laenge (zentriert um 0),
    ``z0..z1`` entlang der Hoehe (ab Wandfuss 0). ``order`` = 1-basierte
    Druckreihenfolge (unten → oben, dann links → rechts).
    """

    section_id: str
    order: int
    x0_mm: float
    x1_mm: float
    z0_mm: float
    z1_mm: float

    @property
    def length_mm(self) -> float:
        return self.x1_mm - self.x0_mm

    @property
    def height_mm(self) -> float:
        return self.z1_mm - self.z0_mm

    @property
    def center_x_mm(self) -> float:
        return 0.5 * (self.x0_mm + self.x1_mm)

    def as_surface(
        self, thickness_mm: float, z_offset_mm: float | None = None
    ) -> WallSurface:
        """Der Abschnitt als Wandflaeche (Laenge x Hoehe) an seiner echten Hoehenlage.

        Seit Issue #132 (Design-Log 2026-07-09) traegt die Flaeche per Default
        die **echte Hoehenlage** des Abschnitts (``z_offset_mm = z0_mm``): die
        Platzierungssuche/-bewertung (`fgc.placement`) sieht die IK-Ziele auf
        ``z0..z1`` absolut und die Aufstellhoehe (``stand_height_mm``) absolut
        ueber dem Boden (Boden = Wandfuss) — vorher wurde jeder Abschnitt als
        Mini-Wand ab ``z = 0`` bewertet (Phantom-Podest am Abschnittsfuss).
        ``x`` bleibt abschnittsrelativ (zentriert um die Abschnittsmitte).

        ``z_offset_mm`` uebersteuert die Hoehenlage explizit — ``0.0`` liefert
        die alte Mini-Wand-Konvention, die die Zerlegungsart „modul" weiter
        braucht (das Teil wird stehend an der Workstation gedruckt, sein Fuss
        liegt auf der Arbeitsflaeche, ADR-022 — nicht auf Einbauhoehe).
        Fuer die unterste Reihe (``z0 = 0``) sind beide Konventionen identisch.
        """
        return WallSurface(
            length_mm=self.length_mm,
            height_mm=self.height_mm,
            thickness_mm=thickness_mm,
            z_offset_mm=self.z0_mm if z_offset_mm is None else z_offset_mm,
        )


@dataclass(frozen=True)
class SectionPlan:
    """Ein Paar (**Abschnitt**, **Platzierung**) — Kern des Zerlegungsvorschlags.

    ``lateral_mm``/``standoff_mm`` der Platzierung sind abschnittsrelativ
    (seitlich um die Abschnittsmitte, Abstand vor der Wandfront);
    ``stand_height_mm`` ist seit Issue #132 **absolut ueber dem Boden**
    (Boden = Wandfuss ``z = 0`` — bei Art „modul" relativ zur Arbeitsflaeche,
    ADR-022). Ein **Plan**, kein **Setup** (ADR-006): verbindlich wird die
    Basis-Lage erst ueber das Antast-Verfahren.
    """

    section: Section
    placement: PlacementOption


@dataclass(frozen=True)
class DecompositionPlan:
    """Der komplette Zerlegungsvorschlag einer Wand (Issue #24).

    ``kind`` = Zerlegungsart (v1: ``"abschnitt"``). ``cuts`` sind die
    Schnittebenen (nur die *inneren* Teilungen — die Wandaussenkanten sind keine
    Schnitte); bei manuell editierten Plaenen (Issue #25, ``propose.from_cuts``)
    sind das die vom Nutzer gesetzten Basis-Positionen, *vor* Anwendung des
    Fugen-Versatzes. ``sections`` sind die Paare (Abschnitt, Platzierung) in
    Druckreihenfolge — deren ``x0_mm``/``x1_mm`` tragen den tatsaechlich
    versetzten Schnittverlauf je Hoehenlage. ``n_length`` / ``n_height`` =
    Anzahl der Teilungen entlang Laenge bzw. Hoehe (1 = keine Teilung in dieser
    Richtung). ``joint_offset_mm`` ist der optionale Fugen-Versatz (Issue #25):
    versetzt die vertikalen Schnitte jeder zweiten Hoehenlage gegen die
    darunterliegende (gestaffelte Stossfugen, wie im Mauerwerk); 0.0 = keine
    Staffelung (Default, rueckwaertskompatibel zu Issue #24).
    """

    kind: str
    wall: WallSurface
    cuts: tuple[Cut, ...]
    sections: tuple[SectionPlan, ...]
    n_length: int
    n_height: int
    joint_offset_mm: float = 0.0
    #: Provenienz der **kollisionsgetriebenen Verfeinerung** (Issue #165), additiv:
    #: Strategie, Aufruf-Kontingent, verbrauchte Aufrufe und je Hoehenreihe der gewaehlte
    #: automatische Hebel (IK/Platzierung) + Kollisions-Status. ``None`` (Default) bei
    #: allen anderen Pfaden (Greedy/manuelle Schnitte) — dann byte-gleich zu bisher. Der
    #: Platzierungs-Teil landet zusaetzlich **in den Teil-Platzierungen** (``sections``),
    #: der IK-Teil bleibt hier (das Plan-Modell traegt keine IK — die wendet der Aufrufer
    #: ueber ``process_params.ik_config`` an). Befund/Nachvollzug, kein Gate (ADR-013).
    refinement: dict | None = None

    # --- ADR-022-Leserichtung (Issue #191) --------------------------------
    # Die Zerlegungsart entscheidet, WIE ein Teil in der Welt liegt, und damit
    # eine Familie von Konventionen (echte Höhenlage z0, frühere Teile als
    # Druckstand, Gebäudekontext). Bis #191 war dieser Entscheid an ~10 Stellen
    # in 4 Dateien als inline ``kind``-Stringvergleich verstreut (byte-gleiche
    # Ternaries, nur per Kommentar synchrone Zwillinge — Quelle der Bugs #132/#135).
    # Jetzt **antwortet der Plan selbst**: die Stringvergleiche leben nur noch hier.

    @property
    def prints_in_place(self) -> bool:
        """Wird in place an der Endposition gedruckt (Art „Abschnitt", ADR-022)?

        Der Kern der **Leserichtung**: bei „Abschnitt" wird der Roboter an die
        Wand umgesetzt (auch in der Höhe), das Teil liegt auf seiner **echten
        Höhenlage** ``z0`` und die früher gedruckten Nachbarteile stehen als
        Druckstand im Weg. Bei „Modul" steht das Teil stattdessen auf der
        Arbeitsfläche der Workstation (Fuß bei ``z = 0``, kein früheres Teil,
        kein Gebäudekontext) — nichts davon gilt.
        """
        return self.kind == "abschnitt"

    @property
    def building_context_applicable(self) -> bool:
        """Zählt der Gebäudekontext als Hindernis (ADR-022)?

        Nur bei Art „Abschnitt" (in place am Einbauort): bei „Modul" ist die
        Workstation der Druckort, der Gebäudekontext gegenstandslos. Eigenes
        Prädikat neben :attr:`prints_in_place`, weil es eine andere Domänen-Frage
        beantwortet (auch wenn beide heute — bei zwei Arten — denselben Wert tragen).
        """
        return self.kind != "modul"

    def sim_z0_mm(self, section: Section) -> float | None:
        """Echte Höhenlage des Abschnittsfußes fürs Sim-Frame — ``None`` bei „Modul".

        Die **eine** vorgerechnete z0-Wahrheit (Issue #132/#135): bei „Abschnitt"
        die absolute Höhenlage ``z0`` (Boden liegt im Sim-Frame bei lokal ``−z0``),
        bei „Modul" ``None`` — das Teil steht auf der Arbeitsfläche, eine
        Einbau-Höhenlage gibt es nicht. Das ``None`` kodiert zugleich die
        **Präsenz** von ``meta.section_z0_mm`` im Trajektorien-Artefakt.
        """
        return section.z0_mm if self.prints_in_place else None

    def surface_for_evaluation(self, section: Section, thickness_mm: float) -> WallSurface:
        """Der Abschnitt als bewertbare Wandfläche an seiner Leserichtungs-Höhenlage.

        Kapselt den None/0.0-Entscheid der Platzierungs-Bewertung (Issue #132):
        bei „Abschnitt" trägt die Fläche die echte Höhenlage (``as_surface`` setzt
        ``z_offset = z0``), bei „Modul" bleibt sie am Boden (``z_offset = 0``, Fuß
        auf der Arbeitsfläche, ADR-022). Der gemeinsame Member der früheren
        Zwillinge in ``decompose/evaluate`` und ``advise_singularity``.
        """
        return section.as_surface(
            thickness_mm, z_offset_mm=None if self.prints_in_place else 0.0
        )
