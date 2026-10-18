"""Bahn-relative Düsen-Orientierung ``nozzle_quat`` (Scheibe 3, Issue #61).

Die eine geteilte Orientierungsquelle: 0/0 ⇒ ``NOZZLE_DOWN_QUAT`` (heutiges
Verhalten), bekannte Tangente + Winkel ⇒ erwartete Achsen (Golden-Werte). Der
Slicer *und* ``placement`` leiten ihre Rotation aus dieser Funktion ab — der
Konsistenztest sichert, dass Erreichbarkeit und Simulation nicht auseinander
driften (Regressionsschutz #51).

Vorzeichenkonvention: +lead = in Fahrtrichtung, +kipp = zur Wand-Außenseite
(aus dem CCW-Ring eindeutig).
"""

from __future__ import annotations

import math

import numpy as np

from fgc.domain.orientation import NOZZLE_DOWN_QUAT, nozzle_quat
from fgc.kinematics.opw import _quat_to_rot


def _axes(quat) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """TCP-Achsen (x, y, z) als Spalten der Rotationsmatrix im Wandsystem."""
    r = _quat_to_rot(quat)
    return r[:, 0], r[:, 1], r[:, 2]


# --- Nullpunkt: 0/0 ⇒ Düse senkrecht von oben, unabhängig von der Tangente -----


def test_zero_angles_are_nozzle_down_for_any_tangent():
    for tangent in [(1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (-3.0, 2.0), (0.0, 0.0)]:
        assert nozzle_quat(tangent, 0.0, 0.0) == NOZZLE_DOWN_QUAT


def test_degenerate_tangent_falls_back_to_nozzle_down():
    # Null-Tangente kann keine Bahnachse liefern → senkrecht von oben.
    assert nozzle_quat((0.0, 0.0), math.radians(20), math.radians(20)) == NOZZLE_DOWN_QUAT


# --- Golden: bekannte Tangente + Winkel ⇒ erwartete Achsen ---------------------


def test_kipp_tilts_nozzle_axis_toward_wall_outside():
    """+kipp kippt die Düse zur Wand-Außenseite (rechte Seite der CCW-Fahrt)."""
    # Fahrt in +x ⇒ Außenseite (n_out = t×ẑ) ist -y.
    quat = nozzle_quat((1.0, 0.0), 0.0, math.radians(30))
    tcp_x, _tcp_y, tcp_z = _axes(quat)
    # Düsenachse (TCP-z) kippt aus der Senkrechten um 30° zur Außenseite (-y).
    np.testing.assert_allclose(
        tcp_z, [0.0, -math.sin(math.radians(30)), -math.cos(math.radians(30))], atol=1e-9
    )
    # Um die Fahrtachse gedreht ⇒ TCP-x (entlang der Bahn) bleibt +x.
    np.testing.assert_allclose(tcp_x, [1.0, 0.0, 0.0], atol=1e-9)
    # Golden-Quaternion (180°−kipp um x): (sin15°, cos15°, 0, 0).
    np.testing.assert_allclose(
        quat, [math.sin(math.radians(15)), math.cos(math.radians(15)), 0.0, 0.0], atol=1e-9
    )


def test_lead_tilts_nozzle_axis_along_travel_direction():
    """+lead kippt die Düse in Fahrtrichtung (+x bei Fahrt in +x)."""
    quat = nozzle_quat((1.0, 0.0), math.radians(30), 0.0)
    _tcp_x, tcp_y, tcp_z = _axes(quat)
    np.testing.assert_allclose(
        tcp_z, [math.sin(math.radians(30)), 0.0, -math.cos(math.radians(30))], atol=1e-9
    )
    # Um die Seitenachse gedreht ⇒ TCP-y bleibt -y.
    np.testing.assert_allclose(tcp_y, [0.0, -1.0, 0.0], atol=1e-9)


def test_kipp_sign_depends_on_travel_direction():
    """Die Außenseite folgt der Fahrtrichtung: +y-Fahrt ⇒ Außenseite +x."""
    quat = nozzle_quat((0.0, 1.0), 0.0, math.radians(30))
    _tcp_x, _tcp_y, tcp_z = _axes(quat)
    # n_out = (0,1,0)×ẑ = (1,0,0) ⇒ Düsenachse kippt nach +x.
    np.testing.assert_allclose(
        tcp_z, [math.sin(math.radians(30)), 0.0, -math.cos(math.radians(30))], atol=1e-9
    )


def test_result_is_unit_quaternion():
    q = nozzle_quat((2.0, -1.0), math.radians(12), math.radians(7))
    assert math.isclose(math.sqrt(sum(c * c for c in q)), 1.0, rel_tol=1e-12)
    assert q[0] >= 0.0  # kanonisch w ≥ 0
