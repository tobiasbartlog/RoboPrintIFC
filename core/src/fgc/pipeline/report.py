"""Textausgaben der Pipeline — Tabellen und Zusammenfassungen als Strings.

Reine Formatierung, kein I/O: CLI und Wizard drucken die Ergebnisse selbst.
"""

from __future__ import annotations

from fgc.domain.models import WallCandidate
from fgc.domain.process_params import SliceParams
from fgc.ifc_io.walls import WallData
from fgc.pipeline.actions import SliceRun


def candidate_verdict(candidate: WallCandidate) -> str:
    """Eignungsurteil einer Wand als Kurztext (ja/nein + Gründe/Vorbehalte)."""
    verdict = "ja" if candidate.eligible else "nein"
    flags = [
        f"{'~' if ch.provisional else ''}{ch.check}"
        for ch in candidate.checks
        if not ch.passed
    ]
    if flags:
        verdict += f"  ({', '.join(flags)})"
    provisional_passes = [ch.check for ch in candidate.checks if ch.passed and ch.provisional]
    if candidate.eligible and provisional_passes:
        verdict += f"  [provisional: {', '.join(provisional_passes)}]"
    return verdict


def candidate_reasons(candidate: WallCandidate) -> str:
    """Ablehnungsgründe einer Wand als '; '-getrennte Liste 'check: reason'.

    Präsentationslogik der E1-Warnung: CLI und Wizard bauen ihren
    Warnhinweis über diese eine Stelle, statt den Reason-Join zu duplizieren.
    """
    return "; ".join(
        f"{c.check}: {c.reason or 'nicht bestanden'}" for c in candidate.failed_checks
    )


def candidates_table(candidates: list[WallCandidate], *, numbered: bool = False) -> str:
    """Kandidatentabelle; mit numbered=True bekommt jede Zeile eine Auswahlnummer."""
    prefix = f"{'Nr':>4}  " if numbered else ""
    lines = [
        f"{prefix}{'GlobalId':<24} {'Name':<32} {'LxHxD [mm]':<20} eignet sich",
        "-" * (96 + (6 if numbered else 0)),
    ]
    for i, c in enumerate(candidates):
        d = c.dimensions_mm
        dims = f"{d['length']:.0f}x{d['height']:.0f}x{d['thickness']:.0f}"
        row_prefix = f"{i + 1:>4}  " if numbered else ""
        lines.append(
            f"{row_prefix}{c.global_id:<24} {(c.name or '—')[:31]:<32} "
            f"{dims:<20} {candidate_verdict(c)}"
        )
    return "\n".join(lines)


def slice_summary(wall: WallData, params: SliceParams, run: SliceRun) -> str:
    s = run.toolpath.summary()
    lines = [
        f"Wand {wall.global_id} ({wall.name or '—'}) gesliced:",
        f"  {s['n_layers']} Schichten à {params.layer_height_mm} mm, "
        f"{params.n_shells} Schalen à {params.strand_width_mm} mm Strangbreite",
        f"  {s['n_targets']} Targets ({s['n_print']} print / "
        f"{s['n_targets'] - s['n_print']} travel)",
    ]
    if run.n_context:
        lines.append(f"  Gebäudekontext: {run.n_context} Elemente (context.json)")
    lines.append(f"  Laufordner: {run.run_dir}")
    return "\n".join(lines)
