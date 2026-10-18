import numpy as np, itertools
from urdf_fk import fk
import py_opw_kinematics as p

rng = np.random.default_rng(0)
Q = rng.uniform(-1.5, 1.5, (12, 6))
P = np.array([fk(q)[:3, 3] for q in Q])
print(fk(np.zeros(6))[:3, 3], fk(np.deg2rad([0, 0, 90, 0, 90, 0]))[:3, 3])
best = []
offs = [0, np.pi / 2, -np.pi / 2, np.pi]
for a1 in (0, 0.0345, -0.0345):
    for b in (0, 0.0345, -0.0345):
        for o1, o2, o3 in itertools.product(offs, offs, offs):
            for fl in itertools.product((False, True), repeat=3):
                m = p.KinematicModel(a1=a1, a2=0, b=b, c1=0.1525, c2=0.62, c3=0.559, c4=0.121,
                                     offsets=(o1, o2, o3, 0, 0, 0), flip_axes=fl + (False,) * 3)
                r = p.Robot(m, degrees=False)
                try:
                    e = max(np.linalg.norm(r.forward(tuple(q)).as_matrix()[:3, 3] - pp) for q, pp in zip(Q, P))
                except Exception:
                    continue
                best.append((e, a1, b, o1, o2, o3, fl))
best.sort(key=lambda x: x[0])
print(*best[:5], sep='\n')
