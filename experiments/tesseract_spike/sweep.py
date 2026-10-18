import subprocess, sys, time, os
t0 = float(open("/tmp/claude-0/t0").read())
print("elapsed min", (time.time() - t0) / 60)
env = dict(os.environ, OMP_NUM_THREADS="2")
for args in ["--collision 1", "--collision 1 --edge 1", "--collision 1 --layer 1", "--collision 1 --layer 39",
             "--collision 1 --res 5", "--collision 1 --redundant 1", "--collision 1 --cy 705"]:
    t = time.time()
    p = subprocess.run([sys.executable, "-W", "ignore", "run_descartes.py", *args.split()], capture_output=True, text=True, env=env)
    keep = [l for l in p.stdout.splitlines() if any(k in l for k in ("success", "post_check", "max_dq", "n_jump", "sign_ch"))]
    print("==", args, "wall %.1fs" % (time.time() - t))
    print("\n".join(keep))
