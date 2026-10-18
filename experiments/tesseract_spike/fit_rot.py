import numpy as np
from urdf_fk import fk
import py_opw_kinematics as p
from scipy.spatial.transform import Rotation as R
m = p.KinematicModel(a1=0, a2=0, b=0.0345, c1=0.1525, c2=0.62, c3=0.559, c4=0.121)
r = p.Robot(m, degrees=False)
rng = np.random.default_rng(1)
for _ in range(5):
    q = rng.uniform(-1.5, 1.5, 6)
    A = r.forward(tuple(q)).as_matrix()
    B = fk(q)
    Rc = A[:3, :3].T @ B[:3, :3]
    print(np.round(Rc, 3).tolist(), np.linalg.norm(A[:3, 3] - B[:3, 3]))
