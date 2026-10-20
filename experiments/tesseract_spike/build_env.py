"""Erzeugt URDF/SRDF/Plugin-YAML im Scratch-Ordner und laedt die Tesseract-Environment."""
import json, os, sys
import numpy as np, trimesh
from scipy.spatial.transform import Rotation as R

REPO = "/home/user/RoboPrintIFC"
OUT = os.environ.get("SPIKE_OUT", "/tmp/claude-0/-home-user-RoboPrintIFC/4f08982b-a9ef-5842-b114-a095e2387c2d/scratchpad/spike")
os.makedirs(OUT, exist_ok=True)

H = 10.0  # Schichthoehe mm
R_FREE = 40.0
MM = 1e-3


def rpy(q_wxyz):
    w, x, y, z = q_wxyz
    return R.from_quat([x, y, z, w]).as_euler("xyz")


def make_assets(layer, size=(600, 200, 400)):
    ws = json.load(open(f"{REPO}/workstations/doosantisch.json"))
    tool = json.load(open(f"{REPO}/tools/30gut.json"))
    # Tisch: konvexe Huelle (Spike-Vereinfachung)
    t = trimesh.load(f"{REPO}/workstations/doosantisch.stl")
    t.convex_hull.export(f"{OUT}/table_hull.stl")
    # Werkzeug: Koerper = alles ausserhalb der Freizone (r_free um TCP), konvexe Huelle
    m = trimesh.load(f"{REPO}/tools/30gut.stl")
    mt = tool["mesh_transform"]
    T_mesh = np.eye(4)
    T_mesh[:3, :3] = R.from_quat([*mt["quat"][1:], mt["quat"][0]]).as_matrix()
    T_mesh[:3, 3] = mt["pos_mm"]
    tc = tool["tcp_frame"]
    T_tcp = np.eye(4)
    T_tcp[:3, :3] = R.from_quat([*tc["quat"][1:], tc["quat"][0]]).as_matrix()
    T_tcp[:3, 3] = tc["pos_mm"]
    mw = m.copy()
    mw.apply_transform(T_mesh)  # in Flanschframe, mm
    d = np.linalg.norm(mw.vertices - T_tcp[:3, 3], axis=1)
    keep = mw.vertices[d > R_FREE]
    body = trimesh.Trimesh(vertices=keep, process=False).convex_hull
    body.export(f"{OUT}/tool_body_flange.stl")  # schon im Flanschframe, mm
    return ws, tool, T_tcp


def urdf(layer, size=(600, 200, 400)):
    ws, tool, T_tcp = make_assets(layer)
    src = open(f"{REPO}/third_party/doosan_m1013/urdf/m1013.white.urdf").read()
    src = src.replace("package://dsr_description2/meshes/", f"file://{REPO}/third_party/doosan_m1013/meshes/")
    # Visuals raus (nur Kollision)
    import re
    src = re.sub(r"<visual>.*?</visual>", "", src, flags=re.S)
    tcp_q = tool["tcp_frame"]["quat"]
    tcp_p = np.array(tool["tcp_frame"]["pos_mm"]) * MM
    bp = np.array(ws["robot_base_frame"]["pos_mm"]) * MM
    sp = np.array(ws["work_surface_frame"]["pos_mm"]) * MM
    sx, sy, sz = (np.array(size) * MM)
    stand_h = layer * H * MM - H * MM  # Schichten 1..layer-1 fertig
    extra = f"""
  <link name="world"/>
  <joint name="world_base" type="fixed"><parent link="world"/><child link="base_link"/>
    <origin xyz="{bp[0]} {bp[1]} {bp[2]}" rpy="0 0 0"/></joint>
  <link name="table"><collision><geometry><mesh filename="file://{OUT}/table_hull.stl" scale="0.001 0.001 0.001"/></geometry></collision></link>
  <joint name="world_table" type="fixed"><parent link="world"/><child link="table"/><origin xyz="0 0 0" rpy="0 0 0"/></joint>
  <link name="stand"><collision><origin xyz="0 0 {stand_h/2}"/><geometry><box size="{sx} {sy} {stand_h}"/></geometry></collision></link>
  <joint name="world_stand" type="fixed"><parent link="world"/><child link="stand"/><origin xyz="{sp[0]} {sp[1]} {sp[2]}" rpy="0 0 0"/></joint>
  <link name="tool_body"><collision><geometry><mesh filename="file://{OUT}/tool_body_flange.stl" scale="0.001 0.001 0.001"/></geometry></collision></link>
  <joint name="tool_body_j" type="fixed"><parent link="link_6"/><child link="tool_body"/><origin xyz="0 0 0" rpy="0 0 0"/></joint>
  <link name="tcp"/>
  <joint name="tcp_j" type="fixed"><parent link="link_6"/><child link="tcp"/>
    <origin xyz="{tcp_p[0]} {tcp_p[1]} {tcp_p[2]}" rpy="{' '.join(map(str, rpy(tcp_q)))}"/></joint>
</robot>"""
    src = src.replace("</robot>", extra)
    src = src.replace("<robot name=\"m1013\">", "<robot name=\"m1013\" xmlns:tesseract=\"https://github.com/tesseract-robotics/tesseract\" tesseract:make_convex=\"true\">")
    open(f"{OUT}/m1013.urdf", "w").write(src)


PLUGINS = """kinematic_plugins:
  search_libraries:
    - tesseract_kinematics_opw_factories
    - tesseract_kinematics_kdl_factories
  fwd_kin_plugins:
    manipulator:
      default: KDLFwdKinChain
      plugins:
        KDLFwdKinChain:
          class: KDLFwdKinChainFactory
          config: {base_link: base_link, tip_link: %(tip)s}
  inv_kin_plugins:
    manipulator:
      default: OPWInvKin
      plugins:
        OPWInvKin:
          class: OPWInvKinFactory
          config:
            base_link: base_link
            tip_link: %(tip)s
            params: {a1: 0.0, a2: 0.0, b: 0.0345, c1: 0.1525, c2: 0.62, c3: 0.559, c4: 0.121,
                     offsets: [0, 0, 0, 0, 0, 0], sign_corrections: [1, 1, 1, 1, 1, 1]}
        KDLInvKin:
          class: KDLInvKinChainLMAFactory
          config: {base_link: base_link, tip_link: %(tip)s}
"""
CM = open("/opt/fgc-venv/lib/python3.12/site-packages/tesseract_robotics/data/tesseract/support/urdf/contact_manager_plugins.yaml").read()


def srdf(tip):
    links = ["base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6"]
    dis = []
    for i in range(6):
        dis.append((links[i], links[i + 1], "Adjacent"))
    dis += [("table", "base_link", "Adjacent"), ("table", "link_1", "Never"), ("tool_body", "link_6", "Adjacent"),
            ("tool_body", "link_5", "Adjacent"), ("table", "stand", "Never"), ("world", "base_link", "Adjacent")]
    # Werkzeugkoerper nur gegen base..link_4 pruefen (SPEC 5.1)
    dis += [("tool_body", "link_5", "Never")]
    s = f"""<?xml version="1.0"?>
<robot name="m1013">
  <group name="manipulator"><chain base_link="base_link" tip_link="{tip}"/></group>
  <group_state name="home" group="manipulator">
    <joint name="joint_1" value="0"/><joint name="joint_2" value="0"/><joint name="joint_3" value="1.5708"/>
    <joint name="joint_4" value="0"/><joint name="joint_5" value="1.5708"/><joint name="joint_6" value="0"/>
  </group_state>
  <kinematics_plugin_config filename="file://{OUT}/plugins.yaml"/>
  <contact_managers_plugin_config filename="file://{OUT}/cm.yaml"/>
""" + "".join(f'  <disable_collisions link1="{a}" link2="{b}" reason="{c}"/>\n' for a, b, c in dis) + "</robot>\n"
    return s


def make_env(layer=20, tip="tcp"):
    from tesseract_robotics.tesseract_common import FilesystemPath, GeneralResourceLocator
    from tesseract_robotics.tesseract_environment import Environment
    urdf(layer)
    open(f"{OUT}/plugins.yaml", "w").write(PLUGINS % {"tip": tip})
    open(f"{OUT}/cm.yaml", "w").write(CM)
    open(f"{OUT}/m1013.srdf", "w").write(srdf(tip))
    env = Environment()
    loc = GeneralResourceLocator()
    ok = env.init(FilesystemPath(f"{OUT}/m1013.urdf"), FilesystemPath(f"{OUT}/m1013.srdf"), loc)
    return env, ok


if __name__ == "__main__":
    env, ok = make_env(int(sys.argv[1]) if len(sys.argv) > 1 else 20, sys.argv[2] if len(sys.argv) > 2 else "tcp")
    print("init", ok)
    if ok:
        print(env.getJointNames() if hasattr(env, "getJointNames") else "")
        g = env.getKinematicGroup("manipulator", "OPWInvKin")
        print("group", g)
