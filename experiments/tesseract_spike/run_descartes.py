"""Descartes-Ladder-Graph fuer einen Rechteckring von S1 (Schicht k) mit sampleToolAxis."""
import argparse, json, math, time, sys
import numpy as np
from scipy.spatial.transform import Rotation as R
import build_env

ap = argparse.ArgumentParser()
ap.add_argument("--layer", type=int, default=20)
ap.add_argument("--step", type=float, default=20.0)
ap.add_argument("--collision", type=int, default=1)
ap.add_argument("--margin", type=float, default=0.010)
ap.add_argument("--edge", type=int, default=0)
ap.add_argument("--threads", type=int, default=2)
ap.add_argument("--res", type=float, default=15.0)
ap.add_argument("--ik", default="OPWInvKin")
ap.add_argument("--redundant", type=int, default=0)
ap.add_argument("--cy", type=float, default=605.0)  # Ringmitte y in W (mm)
ap.add_argument("--inset", type=float, default=20.0)
a = ap.parse_args()

from tesseract_robotics.tesseract_command_language import (
    DEFAULT_PROFILE_KEY, CartesianWaypoint, CartesianWaypointPoly_wrap_CartesianWaypoint, CompositeInstruction,
    InstructionPoly_as_CompositeInstruction, InstructionPoly_as_MoveInstructionPoly, MoveInstruction,
    MoveInstructionPoly_wrap_MoveInstruction, MoveInstructionType_FREESPACE, MoveInstructionType_LINEAR,
    ProfileDictionary, WaypointPoly_as_StateWaypointPoly)
from tesseract_robotics.tesseract_common import Isometry3d, ManipulatorInfo, Quaterniond, Translation3d
from tesseract_robotics.tesseract_motion_planners import PlannerRequest
from tesseract_robotics.tesseract_motion_planners_descartes import (
    DescartesDefaultMoveProfileD, DescartesLadderGraphSolverProfileD, DescartesMotionPlannerD,
    cast_DescartesMoveProfileD, cast_DescartesSolverProfileD)
from tesseract_robotics.tesseract_collision import ContactManagerConfig, CollisionCheckConfig

t0 = time.time()
env, ok = build_env.make_env(a.layer, "link_6")
assert ok
t_env = time.time() - t0

# Ring: Rechteck Zentrum (780, cy), 600x200 abzgl. inset je Seite (Mitte der Wand)
cx, cy, z0 = 780.0, a.cy, 901.0
hx, hy = 300.0 - a.inset, 100.0 - a.inset
z = z0 + a.layer * build_env.H
corners = [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy), (cx - hx, cy - hy)]
pts = []
for (x0, y0), (x1, y1) in zip(corners[:-1], corners[1:]):
    L = math.hypot(x1 - x0, y1 - y0)
    n = max(1, round(L / a.step))
    for i in range(n):
        t = i / n
        pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
pts.append(corners[0])
print("waypoints", len(pts), "z", z)

# Tool-down: tcp-z = -Z_W, tcp-x = +X_W  -> R = diag(1,-1,-1)
Rdown = np.diag([1.0, -1.0, -1.0])
qd = R.from_matrix(Rdown).as_quat()  # x y z w


def wp(x, y, zz):
    return CartesianWaypoint(Isometry3d.Identity() * Translation3d(x * 1e-3, y * 1e-3, zz * 1e-3) * Quaterniond.from_xyzw(*qd))


mi = ManipulatorInfo()
mi.tcp_frame = "tcp"
mi.working_frame = "world"
mi.manipulator = "manipulator"
mi.manipulator_ik_solver = a.ik

prog = CompositeInstruction(DEFAULT_PROFILE_KEY, mi)
for i, (x, y) in enumerate(pts):
    typ = MoveInstructionType_FREESPACE if i == 0 else MoveInstructionType_LINEAR
    prog.appendMoveInstruction(MoveInstructionPoly_wrap_MoveInstruction(
        MoveInstruction(CartesianWaypointPoly_wrap_CartesianWaypoint(wp(x, y, z)), typ, DEFAULT_PROFILE_KEY)))

mp = DescartesDefaultMoveProfileD()
mp.target_pose_fixed = False
mp.target_pose_sample_axis = np.array([0.0, 0.0, 1.0])
mp.target_pose_sample_resolution = math.radians(a.res)
mp.target_pose_sample_min = -math.pi
mp.target_pose_sample_max = math.pi - 1e-6
mp.manipulator_ik_solver = a.ik
mp.use_redundant_joint_solutions = bool(a.redundant)
mp.enable_collision = bool(a.collision)
mp.allow_collision = not a.collision
mp.enable_edge_collision = bool(a.edge)
if a.collision:
    mp.vertex_contact_manager_config = ContactManagerConfig(a.margin)
    if a.edge:
        mp.edge_contact_manager_config = ContactManagerConfig(a.margin)

sp = DescartesLadderGraphSolverProfileD()
sp.num_threads = a.threads
profiles = ProfileDictionary()
NS = "DescartesMotionPlannerTask"
profiles.addProfile(NS, DEFAULT_PROFILE_KEY, cast_DescartesMoveProfileD(mp))
profiles.addProfile(NS, DEFAULT_PROFILE_KEY, cast_DescartesSolverProfileD(sp))

req = PlannerRequest()
req.instructions = prog
req.env = env
req.profiles = profiles
planner = DescartesMotionPlannerD(NS)
t1 = time.time()
resp = planner.solve(req)
t_solve = time.time() - t1
print("success", resp.successful, "msg", resp.message, "t_env %.2f t_solve %.2f" % (t_env, t_solve))

res = {"layer": a.layer, "n_wp": len(pts), "success": bool(resp.successful), "t_env": t_env, "t_solve": t_solve,
       "args": vars(a), "msg": str(resp.message)}
if resp.successful:
    Q = []

    def it(c):
        for ins in c:
            if ins.isCompositeInstruction():
                yield from it(InstructionPoly_as_CompositeInstruction(ins))
            elif ins.isMoveInstruction():
                yield InstructionPoly_as_MoveInstructionPoly(ins)
    for m in it(resp.results):
        w = m.getWaypoint()
        if w.isStateWaypoint():
            Q.append(np.array(WaypointPoly_as_StateWaypointPoly(w).getPosition()).flatten())
    Q = np.array(Q)
    dq = np.abs(np.diff(Q, axis=0))
    res.update(n_states=len(Q), max_dq=float(dq.max()), mean_dq=float(dq.mean(axis=0).max()),
               n_jump_gt_0_3=int((dq.max(axis=1) > 0.3).sum()))
    # Zweig: Vorzeichen von q3 / q5 (Ellbogen/Handgelenk) und q2-Bereich
    res["q3_sign_changes"] = int((np.diff(np.sign(Q[:, 2])) != 0).sum())
    res["q5_sign_changes"] = int((np.diff(np.sign(Q[:, 4])) != 0).sum())
    np.save(f"{build_env.OUT}/Q_layer{a.layer}.npy", Q)
    # Nachpruefung per Tesseract-Diskretkollision mit Margin (unabhaengig vom Planer)
    from tesseract_robotics.tesseract_collision import ContactResultMap, ContactRequest, ContactTestType_ALL
    mgr = env.getDiscreteContactManager()
    jn = list(env.getGroupJointNames("manipulator"))
    mgr.setActiveCollisionObjects(list(env.getActiveLinkNames()))
    mgr.setCollisionMarginData(__import__("tesseract_robotics.tesseract_common", fromlist=["x"]).CollisionMarginData(a.margin))
    nbad = 0
    dmin = 1e9
    for q in Q:
        st = env.getStateByNamesAndValues(jn, q)
        mgr.setCollisionObjectsTransform(st.link_transforms)
        cr = ContactResultMap()
        mgr.contactTest(cr, ContactRequest(ContactTestType_ALL))
        v = list(cr.flattenCopyResults())
        if len(v):
            nbad += 1
            dmin = min(dmin, min(c.distance for c in v))
    res.update(post_check_samples_within_margin=nbad, post_check_dmin_m=None if dmin > 1e8 else dmin)
print(json.dumps(res, indent=1))
json.dump(res, open(f"{build_env.OUT}/res_{a.layer}_{a.collision}_{a.edge}_{a.res}_{a.ik}.json", "w"), indent=1)
