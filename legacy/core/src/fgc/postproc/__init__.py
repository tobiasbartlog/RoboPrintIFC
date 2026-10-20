"""fgc.postproc — Postprozessoren: DRL (Doosan) und KRL (KUKA).

Emitter lesen den roboterunabhängigen Toolpath (Targets) + das Setup-Kanal-Mapping
(ADR-011) + die Bewegungsparameter (``process_params.motion``) und schreiben
controller-native Roboterprogramme: per Target ``movel`` (Druck) / ``movej``
(Travel), vel/acc/Blending/ref aus den Bewegungsparametern. Grad-Konvertierung
ausschließlich hier (ADR-006).

Provisorisch (Spike S1): die vel/acc/Blending-Grenzen stammen aus angenommenen
Werten und tragen im DRL-Kopf einen Provisorik-Stempel (kein Gate, ADR-012/013).
"""

from fgc.postproc.emitter import emit_drl

__all__ = ["emit_drl"]
