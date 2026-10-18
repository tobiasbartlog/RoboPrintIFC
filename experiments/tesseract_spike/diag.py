import sys, numpy as np, collections
import build_env
from tesseract_robotics.tesseract_collision import ContactRequest, ContactTestType_ALL, ContactResultMap
from tesseract_robotics.tesseract_common import CollisionMarginData
layer = int(sys.argv[1]); Q = np.load(f"{build_env.OUT}/Q_layer{layer}.npy")
env, ok = build_env.make_env(layer, "link_6")
mgr = env.getDiscreteContactManager()
jn = list(env.getGroupJointNames("manipulator"))
mgr.setActiveCollisionObjects(list(env.getActiveLinkNames()))
mgr.setCollisionMarginData(CollisionMarginData(0.01))
cnt = collections.Counter()
for q in Q[::6]:
    mgr.setCollisionObjectsTransform(env.getStateByNamesAndValues(jn, q).link_transforms)
    cr = ContactResultMap(); mgr.contactTest(cr, ContactRequest(ContactTestType_ALL))
    for c in cr.flattenCopyResults():
        cnt[(tuple(sorted(c.link_names)), round(c.distance, 3))] += 1
for k, v in sorted(cnt.items()):
    print(k, v)
print(Q[0])
