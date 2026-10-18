"""Druckbarkeit als Lauf-Eigenschaft der Zerlegung (Issue #164).

**Scheibe 3 des kollisionsgetriebenen Zerlegungs-Constraints** (Karte #139,
Entscheidung #141). Reines, tiefes Domänen-Modul: es **verheiratet** die beiden
Kriterien der Serie zu **einem** sichtbaren Druckbarkeits-Urteil je Teil und legt
es additiv in den Zerlegungslauf — das lügende „16/16 ✓" bei real kollidierenden
Teilen fällt.

Zwei Kriterien, zwei Stufen (Fehlerrichtung stets „kollidiert", nie
falsch-„frei" — #141/S6):

1. **Freigang** (Stufe 1, wand-weit, gratis — :mod:`fgc.decompose.freigang`):
   ist die Wand strikt dicker als die druckbare Tiefe von einer Seite, ist sie
   sicher **nicht** einseitig druckbar — jedes Teil trägt dann das Urteil
   ``too_thick`` und die teure Prüf-Tür **entfällt** (der klare Fall, für den das
   Freigang-Kriterium gebaut wurde, Design-Log #163).

2. **Prüf-Tür** (Stufe 2, teuer — :func:`fgc.collision.finding.check_part_clearance`):
   ist die Wand nicht schon zu dick, urteilt die verdünnte ``find_collisions``-
   Instanz. Sie kostet ~10 s je Teil; alle Teile voll zu prüfen wäre zu teuer, also
   prüft der Aufrufer **repräsentativ** die **ungünstigste Zelle je Höhenreihe**
   (:func:`representative_by_row`) und die übrigen Zellen der Reihe **erben** das
   Urteil, ehrlich als ``presumed`` gekennzeichnet („vermutlich").

**Ehrlichkeit ist der Kern (Issue #164).** ``printable`` (grün) sagt **nur**, was
die Prüf-Tür wirklich frei gesehen hat — das Freigang-Kriterium bescheinigt nie
Druckbarkeit (ein stummer Freigang-Befund wird **kein** grünes Häkchen). Ein
geerbtes Reihen-Urteil ist ``presumed`` und darf nicht wie ein geprüftes aussehen.

**Befund, kein Gate** (ADR-013): das Urteil blockiert nie. Fehlt beides (kein
Freigang-Befund, keine Prüf-Tür-Geometrie), bleibt das Urteil ``unknown`` — der
Aufrufer schreibt es dann gar nicht (additiv, Altläufe byte-gleich). Deterministisch,
ohne I/O; der Aufrufer reicht Freigang-Befund und Prüf-Tür-Urteile herein.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fgc.decompose.evaluate import SectionStatus
    from fgc.decompose.freigang import FreigangCheck
    from fgc.decompose.plan import DecompositionPlan

#: Die möglichen Urteile je Teil (das grüne ``printable`` **nur** aus der Prüf-Tür).
VERDICT_PRINTABLE = "printable"
VERDICT_COLLIDES = "collides"
VERDICT_TOO_THICK = "too_thick"
#: Zweite Stufe-1-Schranke (Issue #209): das Teil ist strikt höher als die druckbare
#: Höhe ``H_max`` (Gl. 9, Stamatopoulos — :func:`fgc.decompose.freigang.check_teilhoehe`);
#: die teure Prüfung entfiel. Wie ``too_thick`` **rot, aber ``presumed``** (platzierungs-
#: blinde Vermutung, kein Gate/keine geprüfte Gewissheit).
VERDICT_TOO_TALL = "too_tall"
VERDICT_UNKNOWN = "unknown"

#: Grund eines ``unknown``-Urteils („ungeprüft", Issue #170) — beide führen zum
#: Teil-Zustand „ungeprüft", **nie** zu „frei"; sie unterscheiden nur die Herkunft:
#: :data:`REASON_NO_GEOMETRY` = die Prüf-Tür war **unzuständig** (Altprojekt/Roboter
#: ohne Kollisions-Geometrie), :data:`REASON_ERROR` = die Prüfung ist **fehlgeschlagen**
#: (Ausnahme in der Prüf-Tür — Regression/fehlende Bibliothek; wird geloggt). Ein
#: totes Prüfsystem ist so nicht mehr von einem unzuständigen zu unterscheiden — der
#: Kern von B5/B12/B34/B35.
REASON_NO_GEOMETRY = "no_geometry"
REASON_ERROR = "error"

#: Grund eines ``unknown``-Urteils, wenn die Reihe **keinen** gültigen Repräsentanten
#: hat (Issue #174, Befund B13): keine erreichbare Nicht-Override-Zelle der Reihe —
#: ein Repräsentant ohne erreichbare Pose (fehlende Kinematik-Marge) würde über eine
#: **eingefrorene**, physikalisch bedeutungslose Trajektorie urteilen (typisch „frei").
#: Die Reihe erbt dann **kein** „frei", sondern diesen ehrlichen Nicht-Urteils-Zustand.
REASON_UNREACHABLE = "unreachable"

#: Grund eines ``unknown``-Urteils, wenn die teure Stufe-2-Prüf-Tür für dieses Teil
#: **(noch) nicht angestoßen** wurde (Issue #175). Die Prüf-Tür verlässt den
#: interaktiven Schnittplan-Loop (Befund B14: ~71 s Editor-Freeze je Schnitt-Edit) und
#: läuft nur noch auf **expliziten Anstoß oder asynchron** — bis dahin ist ein
#: nicht-``too_thick``-Teil ehrlich ``unchecked`` (der Ruhezustand nach einem Edit),
#: **nie** stilles Grün (ADR-013). Unterscheidet sich von :data:`REASON_NO_GEOMETRY`
#: (Prüf-Tür unzuständig) und :data:`REASON_ERROR` (Prüfung abgestürzt): hier ist die
#: Prüfung schlicht **noch ausstehend**, ein bewusster Zustand, kein Fehlbestand.
REASON_UNCHECKED = "unchecked"


@dataclass(frozen=True)
class PartPrintability:
    """Druckbarkeits-Urteil **eines** Teils — reine Daten, **Befund, kein Gate**.

    ``verdict`` ist genau eines von :data:`VERDICT_PRINTABLE` (grün, die Prüf-Tür
    hat es frei gesehen), :data:`VERDICT_COLLIDES` (die Prüf-Tür hat eine Kollision
    gesehen), :data:`VERDICT_TOO_THICK` (die Wand ist schon nach dem Freigang-
    Kriterium zu dick — die teure Prüfung entfiel) oder :data:`VERDICT_UNKNOWN`
    (kein Urteil, z. B. keine Kollisions-Geometrie).

    ``presumed`` (``True`` = „vermutlich") kennzeichnet ein Urteil, das **nicht selbst
    an diesem Teil geprüft** wurde und darum keine Gewissheit ist — zwei Quellen:

    - ein **geerbtes** Reihen-Urteil: nicht dieses Teil, sondern die ungünstigste Zelle
      seiner Reihe (``representative_id``) wurde von der Prüf-Tür geprüft (#164);
    - ein ``too_thick``-Urteil des Freigang-Kriteriums (Issue #177): dieses ist
      **höhenblind** — es kennt weder Wandhöhe noch Aufstellung und kann für eine
      niedrige, dicke Wand (Sockel, Handgelenk frei über der Krone) irren. Solange die
      **Wandhöhen-Wache #167** nicht existiert, ist „zu dick" darum eine **Vermutung,
      nie eine geprüfte Gewissheit** (``presumed=True``, ``representative_id`` bleibt
      ``None`` — kein Prüf-Tür-Repräsentant); die falsifizierende Prüf-Tür entfällt
      bewusst (der Freigang-Kurzschluss von #163), das Überspringen ist damit ehrlich
      als „vermutlich, ungeprüft" ausgewiesen (Befund statt Gate, ADR-013).

    ``causer_link`` / ``causer_against`` / ``penetration_mm`` / ``min_distance_mm``
    tragen die **Ursache** der Kollision aus der Prüf-Tür (Eindringrichtung/-tiefe);
    ``excess_mm`` den Dicken-Überschuss aus dem Freigang-Befund (nur ``too_thick``).

    ``reason`` (Issue #170) ist **nur** bei :data:`VERDICT_UNKNOWN` gesetzt und nennt,
    **warum** ungeprüft: :data:`REASON_NO_GEOMETRY` (Prüf-Tür unzuständig) oder
    :data:`REASON_ERROR` (Prüfung fehlgeschlagen). Beide bleiben „ungeprüft", nie „frei".

    ``reachable`` / ``reachable_fraction`` (Issue #180) tragen den **zweiten Kanal** —
    die Erreichbarkeit des Teils (aus dem Reichweiten-Befund, :class:`SectionStatus`).
    Das Urteil **kombiniert** beide Kanäle statt sie zu überstimmen (Befund B33): grün
    (:attr:`printable`) wird ein Teil **nur**, wenn die Prüf-Tür es frei sah **und** es
    voll erreichbar ist. Ein kollisionsfreies, aber nur teilweise erreichbares Teil
    behält ``verdict == printable`` (der Prüf-Tür-Kanal bleibt ehrlich ablesbar), ist
    aber **nicht** grün — Unerreichbarkeit erzeugt nie „printable". Beide Kanäle bleiben
    getrennt lesbar (die UI kombiniert sie sichtbar). ``reachable`` defaultet auf ``True``
    (kein Erreichbarkeits-Kanal übergeben ⇒ Konjunktion ist ein No-op, Altverhalten).

    ``tcp_provisional`` (Issue #177, Befund B9) trägt die **Vorläufigkeit** eines
    ``too_thick``-Urteils, dessen druckbare Tiefe ``D`` aus einem **geschätzten** (noch
    nicht am Gerät vermessenen) Werkzeug-TCP gerechnet wurde: ein zu klein geschätzter
    TCP könnte eine real druckbare Wand fälschlich als „zu dick" melden. Der Befund
    bleibt eine Vermutung (``presumed`` ohnehin ``True``), die UI weist die Vorläufigkeit
    zusätzlich sichtbar aus. Defaultet auf ``False`` (bestätigter TCP), nur ``True`` wird
    serialisiert (additiv, Altläufe byte-gleich).

    ``travel_thinned`` / ``n_checked`` / ``n_samples`` / ``tool_provisional`` (Issue #182,
    Befunde B15/B37/B38) tragen die **Prüf-Vorbehalte der Prüf-Tür selbst** durch, statt
    sie beim Verheiraten stillschweigend fallen zu lassen: ``travel_thinned`` = die Bahn
    wurde NICHT lückenlos geprüft (nur jedes ``travel_stride``-te Travel-Sample, der
    S5-Hebel von :func:`fgc.collision.finding.check_part_clearance`) — dieselbe
    Rechtfertigung, mit der intern die Travel-Ausdünnung begründet wird, ging bislang auf
    dem Ampel-Pfad verloren; ``n_checked``/``n_samples`` beziffern das ehrlich (geprüfte
    von allen Samples der Bahn); ``tool_provisional`` = der Endeffektor lief als
    **provisorische Hülle** (offener PRD-Punkt 3) durch die Prüfung. Ein Tür-„frei" sieht
    so nicht mehr stärker aus, als es ist — konsistent mit dem Kollisionsbefund im Player
    (``travel_not_continuously_checked``/``tool_provisional`` in ``meta.collision``).
    Nur bei einem echten Prüf-Tür-Urteil (``printable``/``collides``) gesetzt — ein
    ``too_thick``-Urteil hat keine Prüf-Tür gesehen, ``n_checked``/``n_samples`` bleiben
    dann ``None``. Additiv: ``travel_thinned``/``tool_provisional`` nur bei ``True``
    serialisiert, ``n_checked``/``n_samples`` nur, wenn gesetzt (Altläufe byte-gleich).

    ``worst_original_index`` / ``worst_layer`` / ``causer_position_mm`` / ``red_intervals``
    (Issue #181, Befund B24, Vorarbeit für #165) tragen den **Kollisions-ORT** der
    Prüf-Tür durch, additiv zum bisherigen einen schlimmsten Sample: ``worst_original_index``
    ist der schlimmste Sample-Index **vor** der Travel-Ausdünnung
    (:func:`fgc.collision.finding.original_sample_index` rechnet den intern
    ausgedünnten Index zurück), ``worst_layer`` seine Schicht, ``causer_position_mm`` die
    Position des Verursacher-Glieds **im Teil-System** an diesem Sample, ``red_intervals``
    die Liste **aller** roten Intervalle (Glied/Gegner/schlimmster Index je Intervall)
    statt nur des einen schlimmsten Samples — der Hebel, entlang dem #165 ohne Heuristik
    entlang der Verursacher-Achse teilen kann. Wie ``n_checked``/``n_samples`` nur bei
    einem echten Prüf-Tür-Urteil gesetzt, additiv nur geschrieben, wenn vorhanden
    (Altläufe/``too_thick``/``unknown`` bleiben byte-gleich).
    """

    section_id: str
    verdict: str
    presumed: bool
    representative_id: str | None = None
    causer_link: int | None = None
    causer_against: str | None = None
    penetration_mm: float | None = None
    min_distance_mm: float | None = None
    excess_mm: float | None = None
    #: Winkel-Überschuss (Grad) der zweiten Stufe-1-Schranke (Issue #209): um wie viel
    #: die vom Teil geforderte Neigung die druckbare ``φ_max^sample`` (Gl. 9) übersteigt.
    #: **Nur** bei ``VERDICT_TOO_TALL`` gesetzt (der Zwilling zu ``excess_mm``, das dort
    #: den Höhen-Überschuss trägt); additiv, nur bei gesetztem Wert serialisiert.
    excess_deg: float | None = None
    reason: str | None = None
    reachable: bool = True
    reachable_fraction: float = 1.0
    tcp_provisional: bool = False
    travel_thinned: bool = False
    n_checked: int | None = None
    n_samples: int | None = None
    tool_provisional: bool = False
    worst_original_index: int | None = None
    worst_layer: int | None = None
    causer_position_mm: tuple[float, float, float] | None = None
    red_intervals: tuple[dict[str, Any], ...] = ()

    @property
    def printable(self) -> bool:
        """Grün: die Prüf-Tür sah es frei **und** es ist voll erreichbar (Issue #180).

        Die **Konjunktion beider Kanäle** — ``VERDICT_PRINTABLE`` (Prüf-Tür frei)
        **und** :attr:`reachable` (Reichweiten-Befund grün). Ein unerreichbares Teil
        wird so **nie** grün, auch wenn die Prüf-Tür es kollisionsfrei sah (B33).
        """
        return self.verdict == VERDICT_PRINTABLE and self.reachable

    @property
    def collides(self) -> bool:
        """Rot: gesehene Kollision **oder** zu dicke Wand **oder** zu hohes Teil."""
        return self.verdict in (VERDICT_COLLIDES, VERDICT_TOO_THICK, VERDICT_TOO_TALL)

    @property
    def known(self) -> bool:
        """``True``, sobald ein echtes Urteil vorliegt (nicht ``unknown``)."""
        return self.verdict != VERDICT_UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "verdict": self.verdict,
            "presumed": self.presumed,
            "representative_id": self.representative_id,
            "causer_link": self.causer_link,
            "causer_against": self.causer_against,
            "penetration_mm": self.penetration_mm,
            "min_distance_mm": self.min_distance_mm,
            "excess_mm": self.excess_mm,
        }
        # Winkel-Überschuss (Issue #209) nur bei ``too_tall`` — additiv, die übrigen
        # Urteile (auch ``too_thick``) bleiben byte-gleich (Feld erscheint gar nicht).
        if self.excess_deg is not None:
            d["excess_deg"] = self.excess_deg
        # ``reason`` nur bei „ungeprüft" (Issue #170) — echte Urteile bleiben byte-gleich
        # (das Feld erscheint gar nicht, additiv wie die übrigen Optionalfelder).
        if self.reason is not None:
            d["reason"] = self.reason
        # Erreichbarkeits-Kanal (Issue #180) nur, wenn er das Urteil **abweicht** — ein
        # voll erreichbares Teil bleibt byte-gleich (Feld erscheint gar nicht, wie bei
        # ``reason``). Ein teilweise unerreichbares Teil trägt ``reachable=False`` +
        # Anteil, damit die UI „kollisionsfrei, aber teilweise unerreichbar" zeigen kann.
        if not self.reachable:
            d["reachable"] = self.reachable
            d["reachable_fraction"] = self.reachable_fraction
        # Vorläufigkeit (Issue #177) nur bei provisorischem TCP schreiben — bestätigter
        # TCP/Altläufe bleiben byte-gleich (additiv, wie ``reason``/``reachable``).
        if self.tcp_provisional:
            d["tcp_provisional"] = self.tcp_provisional
        # Prüf-Vorbehalte der Prüf-Tür (Issue #182, B15/B37/B38) — additiv, dieselbe
        # Byte-Gleichheits-Regel: nur schreiben, was zutrifft/gesetzt ist.
        if self.travel_thinned:
            d["travel_thinned"] = self.travel_thinned
        if self.n_checked is not None:
            d["n_checked"] = self.n_checked
        if self.n_samples is not None:
            d["n_samples"] = self.n_samples
        if self.tool_provisional:
            d["tool_provisional"] = self.tool_provisional
        # Kollisions-ORT der Prüf-Tür (Issue #181) — additiv, dieselbe Byte-Gleichheits-
        # Regel: nur schreiben, was tatsächlich bekannt ist.
        if self.worst_original_index is not None:
            d["worst_original_index"] = self.worst_original_index
        if self.worst_layer is not None:
            d["worst_layer"] = self.worst_layer
        if self.causer_position_mm is not None:
            d["causer_position_mm"] = list(self.causer_position_mm)
        if self.red_intervals:
            d["red_intervals"] = list(self.red_intervals)
        return d


def _obstacle_load(
    plan: DecompositionPlan, order_index: dict[str, int], section_id: str
) -> int:
    """Hindernislast einer Zelle in Druckreihenfolge (Issue #174, Befund B10).

    Der **eigentliche Kollisionstreiber** bei Art „Abschnitt": der Arm fährt beim
    Druck einer Zelle durch das bereits gedruckte, frische Material der Nachbar-
    bänder (**früher gedruckte Teile als Hindernis**). Zählt genau die Teile, die
    :func:`fgc.pipeline.sectionsim.section_sim_context` als ``earlier_parts`` als
    Hindernis stellt — nicht ein Proxy, die tatsächliche Wahrheit:

    - **„abschnitt":** die **Position in Druckreihenfolge** (``plan.sections`` liegt
      in Druckreihenfolge, jedes Teil davor steht real als Hindernis); je später
      gedruckt, desto größer die Hindernislast — innerhalb einer Reihe monoton mit
      der Reihenfolge.
    - **„modul":** **0 für alle** — am Workstation-Druckort steht kein früheres Teil
      (ADR-022); der Gleichstand ist dort konstruktiv, der Stich (zuletzt gedruckt)
      entscheidet.
    """
    return order_index[section_id] if plan.prints_in_place else 0


def _has_reachable_pose(
    status_by_id: dict[str, SectionStatus], section_id: str
) -> bool:
    """``True``, wenn die Zelle **mindestens eine** erreichbare Pose hat (Issue #174).

    ``kinematic_margin is None`` heißt (``fgc.placement.evaluate``): **kein** Bahn-
    punkt ist erreichbar — die Simulation friert die Bahn dann auf der letzten
    gültigen Gelenkstellung ein, und die Prüf-Tür urteilt über eine physikalisch
    bedeutungslose Trajektorie (Arm in Nullstellung statt Druckbahn), typischerweise
    „frei" (Befund B13). Eine solche Zelle darf **nie** Repräsentant werden.
    """
    st = status_by_id.get(section_id)
    return st is not None and st.kinematic_margin is not None


def representative_by_row(
    plan: DecompositionPlan,
    status_by_id: dict[str, SectionStatus],
    override_ids: frozenset[str] | set[str] = frozenset(),
) -> dict[str, str | None]:
    """Ordnet jedem Teil den Repräsentanten **seiner Höhenreihe** zu (Issue #164/#174).

    Eine **Reihe** ist ein Höhenband ``(z0, z1)``: die Prüf-Tür kostet ~10 s je Teil,
    deshalb wird je Reihe nur **eine** Zelle geprüft und die übrigen erben ihr Urteil
    (als „vermutlich"). Die Höhe ist der dominante Kollisionstreiber (höhere Reihe =
    mehr Druckstand darunter).

    **Kollisionsehrliche Wahl (Issue #174, Befunde B10/B13/B26/B36).** Der Repräsentant
    ist die Zelle mit **maximaler Hindernislast** in Druckreihenfolge (:func:`_obstacle_load`,
    der eigentliche Kollisionstreiber bei „Abschnitt"), bei Gleichstand die **zuletzt
    gedruckte** Zelle (``max(order)``, nicht die hindernisärmste erste). Ausgeschlossen
    von der Wahl:

    - Zellen **ohne erreichbare Pose** (fehlende Kinematik-Marge, :func:`_has_reachable_pose`):
      ihr Prüf-Tür-Urteil käme von einer eingefrorenen Trajektorie (B13).
    - Zellen mit **eigenem Platzierungs-Override** (``override_ids``): ihr Urteil wurde
      an einer **anderen** Platzierung gemessen und darf nicht vererbt werden (B36).

    Rückgabe ``section_id → section_id | None`` (reine Funktion):

    - **erbende Zelle** ⇒ die ``section_id`` ihres Reihen-Repräsentanten;
    - **Repräsentant** ⇒ sich selbst;
    - **Override-Zelle** ⇒ sich selbst, falls erreichbar (**selbst geprüft**, erbt nie),
      sonst ``None``;
    - ``None`` ⇒ **ehrlicher Nicht-Urteils-Zustand**: keine erreichbare Nicht-Override-
      Zelle in der Reihe — die Reihe erbt **kein** „frei" (der Aufrufer setzt ``unknown``
      mit :data:`REASON_UNREACHABLE`).
    """
    rows: dict[tuple[float, float], list[Any]] = {}
    order_index: dict[str, int] = {}
    for pos, sp in enumerate(plan.sections):
        s = sp.section
        order_index[s.section_id] = pos
        key = (round(float(s.z0_mm), 3), round(float(s.z1_mm), 3))
        rows.setdefault(key, []).append(s)

    rep_by_section: dict[str, str | None] = {}
    for cells in rows.values():
        # Kandidaten: erreichbar UND ohne eigenen Platzierungs-Override.
        candidates = [
            s
            for s in cells
            if s.section_id not in override_ids
            and _has_reachable_pose(status_by_id, s.section_id)
        ]
        # Maximale Hindernislast; Stich = zuletzt gedruckt (max order).
        rep = (
            max(
                candidates,
                key=lambda s: (_obstacle_load(plan, order_index, s.section_id), s.order),
            )
            if candidates
            else None
        )
        rep_id = rep.section_id if rep is not None else None
        for s in cells:
            sid = s.section_id
            if sid in override_ids:
                # Override-Zelle erbt nicht: selbst geprüft (falls erreichbar), sonst
                # ehrlicher Nicht-Urteils-Zustand.
                rep_by_section[sid] = (
                    sid if _has_reachable_pose(status_by_id, sid) else None
                )
            else:
                rep_by_section[sid] = rep_id
    return rep_by_section


def _reachability(
    status_by_id: dict[str, SectionStatus] | None, section_id: str
) -> tuple[bool, float]:
    """Erreichbarkeits-Kanal eines Teils (Issue #180) aus dem Reichweiten-Befund.

    Fehlt der Befund (kein ``status_by_id`` übergeben — Altaufrufer/reiner Prüf-Tür-
    Test), gilt das Teil als **voll erreichbar** (``True``, 1.0): die Konjunktion ist
    dann ein No-op und das Altverhalten (#164) bleibt bit-genau erhalten.
    """
    st = status_by_id.get(section_id) if status_by_id else None
    if st is None:
        return True, 1.0
    return bool(st.reachable), float(st.reachable_fraction)


def combine_printability(
    plan: DecompositionPlan,
    freigang: FreigangCheck | None,
    verdict_by_rep: dict[str, Any],
    rep_by_section: dict[str, str],
    status_by_id: dict[str, SectionStatus] | None = None,
    *,
    default_reason: str = REASON_NO_GEOMETRY,
) -> dict[str, PartPrintability]:
    """Verheiratet Freigang (Stufe 1) + Prüf-Tür (Stufe 2) + Erreichbarkeit zum Urteil
    je Teil (Issue #164, Konjunktion #180).

    - **Freigang zu dick** ⇒ jedes Teil ``too_thick`` (wand-weit) — **als Vermutung**
      (``presumed=True``, Issue #177): das Freigang-Kriterium ist höhenblind, solange
      die Wandhöhen-Wache #167 fehlt, darum ist „zu dick" nie eine geprüfte Gewissheit.
      Die Prüf-Tür (die es falsifizieren würde) entfällt bewusst — das Überspringen ist
      als „vermutlich, ungeprüft" ausgewiesen, nicht ersatzlos. War der TCP provisorisch
      (``freigang.tcp_provisional``), trägt das Urteil zusätzlich ``tcp_provisional``.
    Die **zweite** Stufe-1-Schranke „Teil zu hoch für die freie Länge" (Issue #209,
    ``VERDICT_TOO_TALL``) ist **per Teil** (nicht wand-weit) und lebt eine Ebene höher,
    in der Prüf-Politik :func:`fgc.decompose.pruefung.assess_plan` (Stufe-1-Pfad) — sie
    überschreibt dort die hier gebauten Urteile additiv. So bleibt diese Verheiratung
    rein über Freigang (wand-weit) + Prüf-Tür.
    - sonst erbt jedes Teil das Prüf-Tür-Urteil seines **Reihen-Repräsentanten**
      (``rep_by_section``): kollidiert er, ``collides`` (mit Ursache); sah die
      Prüf-Tür ihn frei, ``printable``.
    - fehlt für die Reihe ein echtes Prüf-Tür-Urteil, bleibt das Teil ``unknown``
      („ungeprüft", Issue #170) — **nie** grün. Der **Grund** wird durchgereicht:
      ``None`` bzw. :data:`REASON_NO_GEOMETRY` = Prüf-Tür unzuständig (keine
      Geometrie/Altprojekt), :data:`REASON_ERROR` = Prüfung fehlgeschlagen. Ein
      **String**-Wert wird **nie** als freies Urteil missdeutet (Ehrlichkeit B12).
    - hat die Reihe **keinen** gültigen Repräsentanten (``rep_by_section[sid] is None``,
      Issue #174/B13 — keine erreichbare Nicht-Override-Zelle bzw. unerreichbare
      Override-Zelle), bleibt das Teil ebenfalls ``unknown``, mit :data:`REASON_UNREACHABLE`
      — die Reihe erbt **kein** „frei" von einer eingefrorenen Trajektorie.

    **Zweiter Kanal — Erreichbarkeit (Issue #180, Befund B33):** jedes Teil trägt
    zusätzlich ``reachable`` / ``reachable_fraction`` aus ``status_by_id`` (dem
    Reichweiten-Befund). Das Urteil **kombiniert** die Kanäle statt sie zu überstimmen:
    grün (:attr:`PartPrintability.printable`) wird ein Teil **nur** bei Prüf-Tür-``printable``
    **und** voller Erreichbarkeit — ein kollisionsfreies, aber nur teilweise erreichbares
    Teil behält ``verdict == printable`` (Prüf-Tür-Kanal ehrlich), ist aber nicht grün.
    Ohne ``status_by_id`` ist die Konjunktion ein No-op (Altverhalten #164, alle Teile
    gelten als erreichbar).

    ``verdict_by_rep`` bildet Repräsentant-``section_id`` → Prüf-Tür-Urteil
    (Objekt mit ``collides``/``causer_link``/``causer_against``/``penetration_mm``/
    ``min_distance_mm``, i. d. R. ein :class:`fgc.collision.finding.ClearanceVerdict`),
    ``None`` (keine Geometrie) oder einen der Grund-Strings (:data:`REASON_NO_GEOMETRY`/
    :data:`REASON_ERROR`, Issue #170). Reine, deterministische Funktion.

    ``default_reason`` (Issue #175) bestimmt den ``reason`` eines Teils, für dessen
    Reihe **kein** Prüf-Tür-Objekt vorliegt (``verdict is None``): normal
    :data:`REASON_NO_GEOMETRY` (Prüf-Tür unzuständig), aber der Stufe-1-Kurzschluss
    (die Prüf-Tür wurde bewusst noch nicht angestoßen) reicht :data:`REASON_UNCHECKED`
    herein — dann heißt „kein Urteil" ehrlich „noch nicht geprüft" statt „keine
    Geometrie". Ein **String**-Wert in ``verdict_by_rep`` (echter Grund) gewinnt immer
    über den Default (ein Absturz bleibt ``error``, nie „nur ausstehend").
    """
    too_thick = freigang is not None and bool(getattr(freigang, "too_thick", False))
    excess = float(getattr(freigang, "excess_mm", 0.0)) if freigang is not None else None
    # Vorläufigkeit des einfließenden TCP (Issue #177/B9): ein „zu dick" aus einem
    # geschätzten TCP ist nie eine geprüfte Gewissheit.
    tcp_prov = freigang is not None and bool(getattr(freigang, "tcp_provisional", False))

    out: dict[str, PartPrintability] = {}
    for sp in plan.sections:
        sid = sp.section.section_id
        reachable, reach_frac = _reachability(status_by_id, sid)
        if too_thick:
            # „vermutlich zu dick" (Issue #177): höhenblind, solange die Wandhöhen-Wache
            # #167 fehlt — presumed=True, die falsifizierende Prüf-Tür entfiel bewusst.
            out[sid] = PartPrintability(
                sid, VERDICT_TOO_THICK, presumed=True, excess_mm=excess,
                reachable=reachable, reachable_fraction=reach_frac,
                tcp_provisional=tcp_prov,
            )
            continue
        rep_id = rep_by_section.get(sid, sid)
        # Kein Repräsentant (``None``, Issue #174/B13): keine erreichbare (Nicht-
        # Override-)Zelle in der Reihe bzw. eine unerreichbare Override-Zelle ⇒
        # ehrlicher Nicht-Urteils-Zustand, NIE „frei" erben.
        if rep_id is None:
            out[sid] = PartPrintability(
                sid, VERDICT_UNKNOWN, presumed=False, reason=REASON_UNREACHABLE,
                reachable=reachable, reachable_fraction=reach_frac,
            )
            continue
        verdict = verdict_by_rep.get(rep_id)
        # „ungeprüft" (Issue #170): kein Objekt-Urteil ⇒ unknown, nie grün. Ein
        # String ist der **Grund** (no_geometry/error) und wird NIE als freies Urteil
        # gelesen (sonst würde ein Absturz zu „frei" — genau der Fehler B12).
        if verdict is None or isinstance(verdict, str):
            reason = verdict if isinstance(verdict, str) else default_reason
            out[sid] = PartPrintability(
                sid, VERDICT_UNKNOWN, presumed=False, reason=reason,
                reachable=reachable, reachable_fraction=reach_frac,
            )
            continue
        collides = bool(getattr(verdict, "collides", False))
        out[sid] = PartPrintability(
            sid,
            VERDICT_COLLIDES if collides else VERDICT_PRINTABLE,
            presumed=(rep_id != sid),
            representative_id=rep_id,
            causer_link=getattr(verdict, "causer_link", None),
            causer_against=getattr(verdict, "causer_against", None),
            penetration_mm=getattr(verdict, "penetration_mm", None),
            min_distance_mm=getattr(verdict, "min_distance_mm", None),
            reachable=reachable,
            reachable_fraction=reach_frac,
            # Prüf-Vorbehalte der Prüf-Tür durchreichen (Issue #182, B15/B37/B38) —
            # additiv, verlustfrei vom ClearanceVerdict-Repräsentanten geerbt (auch von
            # erbenden Zellen: dieselbe Prüfung galt für die ganze Reihe).
            travel_thinned=bool(getattr(verdict, "travel_thinned", False)),
            n_checked=getattr(verdict, "n_checked", None),
            n_samples=getattr(verdict, "n_samples", None),
            tool_provisional=bool(getattr(verdict, "tool_provisional", False)),
            # Kollisions-ORT (Issue #181) — additiv, verlustfrei vom ClearanceVerdict-
            # Repräsentanten geerbt (auch von erbenden Zellen: dieselbe Prüfung galt für
            # die ganze Reihe). ``red_intervals`` kommt als Tupel von RedInterval-
            # Objekten (echtes ClearanceVerdict) oder bereits als Dicts (Test-Doubles) —
            # beide werden zu Dicts vereinheitlicht.
            worst_original_index=getattr(verdict, "worst_original_index", None),
            worst_layer=getattr(verdict, "worst_layer", None),
            causer_position_mm=getattr(verdict, "causer_position_mm", None),
            red_intervals=tuple(
                iv.to_dict() if hasattr(iv, "to_dict") else iv
                for iv in getattr(verdict, "red_intervals", ())
            ),
        )
    return out
