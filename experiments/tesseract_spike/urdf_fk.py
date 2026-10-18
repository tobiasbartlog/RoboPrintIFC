import numpy as np, xml.etree.ElementTree as ET
from scipy.spatial.transform import Rotation as R
URDF = "/home/user/RoboPrintIFC/third_party/doosan_m1013/urdf/m1013.white.urdf"


def load():
    J = []
    for j in ET.parse(URDF).getroot().findall('joint'):
        o = j.find('origin')
        xyz = [float(x) for x in o.get('xyz').split()]
        rpy = [float(x) for x in (o.get('rpy') or '0 0 0').split()]
        T = np.eye(4)
        T[:3, :3] = R.from_euler('xyz', rpy).as_matrix()
        T[:3, 3] = xyz
        J.append(T)
    return J


JT = load()


def fk(q):
    T = np.eye(4)
    for Tj, qi in zip(JT, q):
        Rz = np.eye(4)
        Rz[:3, :3] = R.from_euler('z', qi).as_matrix()
        T = T @ Tj @ Rz
    return T
