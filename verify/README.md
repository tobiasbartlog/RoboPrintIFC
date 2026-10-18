# verify/

Abnahme nach `spec/SPEC.md` §11. Nach Ende P0 gesperrt (`spec/LOCKED`).

| Datei | Zweck | Entsteht |
|---|---|---|
| `run.py` | Gate-Runner, aufgerufen über `scripts/verify.py` | vorhanden |
| `oracle/robot_oracle.py` | FK und Grenzen aus der URDF mit Pinocchio | P0, A0.2 |
| `oracle/collision_oracle.py` | Abstände mit Coal auf Roh-Meshes, Paare exakt nach SPEC §5.1 | P0, A0.2 |
| `oracle/test_g1_kinematics.py` | G1: vergleicht `roboprint.robot` mit `robot_oracle` | P0, A0.2 |
| `oracle/test_g2_collision.py` | G2: vergleicht `roboprint.collision` mit `collision_oracle` | P0, A0.2 |
| `check_run.py` | G3/G4: prüft einen Laufordner (SPEC §6) dicht und unabhängig. `python -m verify.check_run <dir> --scenario <json>` schreibt `<dir>/check.json` und endet mit 0 genau bei Bestehen | P0, A0.2 |
| `fake_drcf/` | G5: führt DRL in CPython mit Stubs aus. `python -m verify.fake_drcf <dir>...` endet mit 0 genau bei Bestehen | P0, A0.2 |

**Unabhängigkeit:**
- Die Orakel (`*_oracle.py`, `check_run.py`, `fake_drcf/`) lesen nur die URDF, die Assets und die
  Artefakte. Sie importieren `roboprint` nie.
- Nur die Vergleichstests `test_g1_*` und `test_g2_*` importieren beide Seiten, das System unter Test
  und das Orakel.

**Selbsttests:** Jedes Orakel hat Tests mit konstruierten Fällen unter `oracle/selftest_*.py`. Beispiele:
- Ein Würfel im Glied ergibt d < 0.
- Eine bekannte Pose ergibt bekannte Flanschkoordinaten.
- DRL mit `ch=0` wird abgelehnt.
- Ein `posx` mit um 180° verdrehter Düse wird abgelehnt.
