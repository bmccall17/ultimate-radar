"""
Generates fixtures/possession_demo.json -- a SYNTHETIC 7v7 UFA possession used to
develop and review the viewer before any real tracking output exists.

Everything here is invented. It exists so the viewer's hardest cases are present
from day one: players leaving the camera, dead-reckoned ghosts drifting away from
truth, and an identity swap a human has to fix.

Units: yards. Field frame: X 0..120 along the field (endzones 0..20 and 100..120),
Y 0..53.333 across. Z up. Time: 15 Hz.
"""
import json, math
import numpy as np
from scipy.ndimage import gaussian_filter1d

FPS = 15
DUR = 21.0
N = int(DUR * FPS) + 1
T = np.linspace(0, DUR, N)

FIELD_L, FIELD_W, EZ = 120.0, 160.0 / 3.0, 20.0
IMG_W, IMG_H = 1280, 720

def track(waypoints, smooth=6):
    """waypoints: [(t, x, y), ...] -> smoothed (N,2) array."""
    tw = np.array([w[0] for w in waypoints], float)
    xs = np.interp(T, tw, [w[1] for w in waypoints])
    ys = np.interp(T, tw, [w[2] for w in waypoints])
    return np.stack([gaussian_filter1d(xs, smooth, mode="nearest"),
                     gaussian_filter1d(ys, smooth, mode="nearest")], axis=1)

# ---------------------------------------------------------------- offense (Sol)
# Vertical stack, disc on the left-centre, attacking toward X=120.
# Beat sheet: 0-4 reset / 4-9 two unders / 9-13 iso continuation /
#             13-17 break-side swing / 17-21 huck to the endzone.
O = {}
O["O1"] = track([(0,45,26),(3.5,46,25),(4.2,46,25),(9,46,24),(13,47,22),(21,48,22)])           # initiating handler
O["O2"] = track([(0,41,19),(5,44,18),(9,50,17),(13,54,14),(15.5,58,12),(17.5,60,12),(21,62,13)]) # reset -> swing receiver
O["O3"] = track([(0,42,34),(6,45,35),(12,48,36),(17,52,36),(21,55,35)])                        # weak-side reset
O["O4"] = track([(0,58,26),(3,63,22),(4.2,57,24),(8,54,26),(12,52,27),(16,55,28),(21,60,28)])   # front of stack, in-cut
O["O5"] = track([(0,63,27),(5,68,30),(8.6,62,29),(11,58,30),(14,62,31),(18,74,33),(21,86,34)])  # second cut, then clear
O["O6"] = track([(0,69,25),(7,72,22),(11,78,20),(13.5,84,20),(16,92,23),(18.5,101,27),(21,110,31)]) # deep threat -> scores
O["O7"] = track([(0,74,27),(6,79,31),(10,86,34),(14,90,38),(18,88,41),(21,84,42)])              # deep clear-out

# --------------------------------------------------------- defence (Wind Chill)
# Person defence with a forehand force. D6 breaks off at t~9.5 to bracket the
# deep lane (the poach), leaving O4 free underneath -- the thing the tool exists
# to make visible.
D = {}
D["D1"] = track([(0,46.5,26.6),(3.5,47.5,25.6),(9,47.5,24.6),(13,48.5,22.6),(21,49.5,22.6)])    # the mark
D["D2"] = track([(0,42.6,18.0),(5,45.6,17.0),(9,51.6,16.2),(13,55.6,13.2),(17.5,61.4,11.2),(21,63.4,12.2)])
D["D3"] = track([(0,43.4,35.4),(6,46.4,36.4),(12,49.4,37.4),(17,53.4,37.4),(21,56.4,36.4)])
D["D4"] = track([(0,60,26.5),(3,65,22.4),(4.2,59,24.4),(8,56,26.4),(12,54,27.4),(16,57,28.4),(21,62,28.4)])
D["D5"] = track([(0,65,27.6),(5,70,30.6),(8.6,64,29.6),(11,60,30.6),(14,64,31.6),(18,76,33.6),(21,88,34.6)])
# D6 poaches off O6 at ~9.5s into the deep lane, then recovers late
D["D6"] = track([(0,71,24.6),(7,74,21.6),(9.5,79,20.0),(11.5,80,26.0),(13.5,83,29.0),(15.5,88,28.0),(18,98,27.5),(21,109,30.0)])
D["D7"] = track([(0,76,27.4),(6,81,31.4),(10,88,34.4),(14,92,38.4),(18,90,41.4),(21,86,42.4)])

PLAYERS = [
    # id, team, slot label, jersey (synthetic), role
    ("O1","sol","O1",7,"handler"),  ("O2","sol","O2",21,"handler"), ("O3","sol","O3",4,"handler"),
    ("O4","sol","O4",33,"cutter"),  ("O5","sol","O5",12,"cutter"),  ("O6","sol","O6",88,"cutter"),
    ("O7","sol","O7",15,"cutter"),
    ("D1","chill","D1",2,"mark"),   ("D2","chill","D2",19,"defender"), ("D3","chill","D3",44,"defender"),
    ("D4","chill","D4",9,"defender"),("D5","chill","D5",27,"defender"),("D6","chill","D6",5,"defender"),
    ("D7","chill","D7",31,"defender"),
]
TRUTH = {**O, **D}

# ------------------------------------------------------------------ disc events
EVENTS = [
    {"t": 0.0,  "type": "possession_start", "player": "O1", "note": "Catch after the pull"},
    {"t": 4.2,  "type": "throw",  "player": "O1", "target": "O4"},
    {"t": 5.0,  "type": "catch",  "player": "O4"},
    {"t": 8.6,  "type": "throw",  "player": "O4", "target": "O5"},
    {"t": 9.3,  "type": "catch",  "player": "O5"},
    {"t": 13.2, "type": "throw",  "player": "O5", "target": "O2"},
    {"t": 14.1, "type": "catch",  "player": "O2"},
    {"t": 17.4, "type": "throw",  "player": "O2", "target": "O6", "note": "Huck to the break side"},
    {"t": 20.3, "type": "catch",  "player": "O6"},
    {"t": 20.3, "type": "goal",   "player": "O6"},
]

def disc_position(t):
    """Disc rides with the holder; flies on a parabola-ish path between."""
    holder, hold_t = "O1", 0.0
    for e in EVENTS:
        if e["type"] in ("possession_start", "catch") and e["t"] <= t:
            holder, hold_t = e["player"], e["t"]
    for e in EVENTS:
        if e["type"] == "throw" and e["t"] <= t:
            land = next((c for c in EVENTS if c["type"] == "catch" and c["t"] > e["t"]), None)
            if land and land["t"] > t >= e["t"]:
                a = np.interp(t, T, np.arange(N))
                i0 = int(round(e["t"] * FPS)); i1 = int(round(land["t"] * FPS))
                u = (t - e["t"]) / (land["t"] - e["t"])
                p0 = TRUTH[e["player"]][i0]; p1 = TRUTH[land["player"]][i1]
                xy = p0 * (1 - u) + p1 * u
                h = 1.5 + 4.0 * math.sin(math.pi * u)
                return float(xy[0]), float(xy[1]), h
    i = int(round(t * FPS))
    p = TRUTH[holder][min(i, N - 1)]
    return float(p[0]), float(p[1]), 1.1

DISC = np.array([disc_position(t) for t in T])

# ------------------------------------------------------------------ the camera
# One elevated sideline camera, the way a UFA broadcast actually shoots it:
# it chases the disc, it lags on fast swings, and it never holds the whole field.
CAM_POS = np.array([58.0, -21.0, 13.0])

aim = np.stack([
    gaussian_filter1d(DISC[:, 0] + 3.5, 11, mode="nearest"),   # leads slightly downfield
    gaussian_filter1d(DISC[:, 1] * 0.55 + 24.0 * 0.45, 14, mode="nearest"),
], axis=1)
# operator lag: the pan trails the action, worst on the 13-17s swing
lag = np.zeros(N)
lag[int(13.0*FPS):int(17.0*FPS)] = 1.0
lag = gaussian_filter1d(lag, 8, mode="nearest")
aim[:, 0] = aim[:, 0] - lag * gaussian_filter1d(np.gradient(DISC[:, 0]) * FPS * 0.45, 6, mode="nearest")

# focal length: tight on the handler set, wider as the play stretches
spread = np.array([max(np.ptp([TRUTH[p][i][0] for p in TRUTH]), 24.0) for i in range(N)])
spread = gaussian_filter1d(spread, 12, mode="nearest")
dist = np.linalg.norm(np.stack([aim[:,0], aim[:,1], np.zeros(N)], 1) - CAM_POS, axis=1)
fov_yd = spread * 0.92            # tight broadcast framing: the whole field is never in shot
focal = IMG_W * dist / np.maximum(fov_yd, 17.0)

def projection(i):
    tgt = np.array([aim[i,0], aim[i,1], 1.2])
    fwd = tgt - CAM_POS; fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0,0,1.0])); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    R = np.stack([right, -up, fwd])          # world -> camera (y down in image)
    f = focal[i]
    K = np.array([[f,0,IMG_W/2],[0,f,IMG_H/2],[0,0,1.0]])
    Rt = np.hstack([R, (-R @ CAM_POS).reshape(3,1)])
    return K @ Rt

def project(P, xyz):
    v = P @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
    if v[2] <= 0.3: return None
    return v[0]/v[2], v[1]/v[2]

# ------------------------------------------------- visibility + what we "know"
MARGIN = 26        # px inside the frame edge before we trust a detection
LOST_INTERP = 0.5  # s -- gap we're willing to bridge as interpolation
LOST_PRED   = 2.2  # s -- how long we dead-reckon before giving up

visible = {pid: np.zeros(N, bool) for pid in TRUTH}
for i in range(N):
    P = projection(i)
    for pid, tr in TRUTH.items():
        pt = project(P, (tr[i,0], tr[i,1], 0.0))
        head = project(P, (tr[i,0], tr[i,1], 2.0))
        visible[pid][i] = bool(pt and head and MARGIN < pt[0] < IMG_W-MARGIN and MARGIN < pt[1] < IMG_H-MARGIN)

# scripted occlusion: D5 is screened behind O5 for ~0.8s around the second catch
for i in range(int(9.0*FPS), int(9.8*FPS)): visible["D5"][i] = False
# scripted detector dropout on a distant small player
for i in range(int(6.2*FPS), int(6.9*FPS)): visible["O7"][i] = False

def build_estimate(pid):
    """What the pipeline believes, frame by frame, with provenance."""
    tr = TRUTH[pid]; vis = visible[pid]
    est = np.zeros((N,2)); state = []; sigma = np.zeros(N)
    last_obs_i, last_obs_p, last_obs_v = None, None, np.zeros(2)
    for i in range(N):
        if vis[i]:
            est[i] = tr[i]
            if last_obs_i is not None and 0 < i - last_obs_i <= LOST_INTERP*FPS:
                # retro-fill the short gap as straight-line interpolation
                for j in range(last_obs_i+1, i):
                    u = (j - last_obs_i) / (i - last_obs_i)
                    est[j] = last_obs_p*(1-u) + tr[i]*u
                    state[j] = "interpolated"; sigma[j] = 0.4 + 0.6*math.sin(math.pi*u)
            v = (tr[i] - tr[max(i-2,0)]) / (2/FPS) if i >= 2 else np.zeros(2)
            last_obs_i, last_obs_p, last_obs_v = i, tr[i].copy(), v
            state.append("observed"); sigma[i] = 0.28
        else:
            if last_obs_i is None:
                est[i] = tr[i]; state.append("unknown"); sigma[i] = 6.0; continue
            dt = (i - last_obs_i) / FPS
            # dead reckoning: constant velocity, decaying -- this is WHY ghosts drift
            damp = math.exp(-dt/2.6)
            est[i] = last_obs_p + last_obs_v * dt * damp
            est[i,0] = float(np.clip(est[i,0], -4, FIELD_L+4))
            est[i,1] = float(np.clip(est[i,1], -4, FIELD_W+4))
            if dt <= LOST_INTERP:   state.append("interpolated"); sigma[i] = 0.4 + 0.9*dt
            elif dt <= LOST_PRED:   state.append("predicted");    sigma[i] = 0.6 + 1.7*dt + 0.55*dt*dt
            else:                   state.append("unknown");      sigma[i] = min(3.0 + 2.1*dt, 16.0)
    return est, state, sigma

players_out = []
for pid, team, slot, jersey, role in PLAYERS:
    est, state, sigma = build_estimate(pid)
    players_out.append({
        "id": pid, "team": team, "slot": slot, "jersey": jersey, "role": role,
        "truth": [[round(float(x),2), round(float(y),2)] for x,y in TRUTH[pid]],
        "est":   [[round(float(x),2), round(float(y),2)] for x,y in est],
        "state": state,
        "sigma": [round(float(s),2) for s in sigma],
    })

# ------------------------------------------------------- a real mistake to fix
# D5 and D7 cross at ~10s; the tracker swaps their identities and never recovers.
# The viewer ships with this swap live so the correction flow is exercised.
SWAP = {"frame": int(10.4*FPS), "a": "D5", "b": "D7",
        "reason": "Both defenders passed within 1.1 yd travelling the same direction; "
                  "team colour and motion were identical, jersey numbers were unreadable at this range."}
pa = next(p for p in players_out if p["id"] == SWAP["a"])
pb = next(p for p in players_out if p["id"] == SWAP["b"])
f = SWAP["frame"]
for key in ("est","state","sigma"):
    pa[key][f:], pb[key][f:] = pb[key][f:], pa[key][f:]

doc = {
    "schema": "ultimate-radar/possession@0.2",
    "synthetic": True,
    "notice": "SYNTHETIC DEMO DATA. Invented positions and jersey numbers; not derived from any real game.",
    "possession": {
        "id": "demo-0001",
        "label": "Demo possession - offence breaks a poach",
        "source_video": {"platform": "youtube", "id": "IDnoyd4cKfM",
                         "title": "Pro Frisbee Semifinals: Austin Sol vs Minnesota Wind Chill (UFA, 27 Aug 2026)",
                         "note": "Referenced as the target footage. No frames from it are included."},
        "fps": FPS, "frames": N, "duration_s": DUR,
        "offense": "sol", "defense": "chill",
        "attacking_direction": "+x",
    },
    "field": {"length_yd": FIELD_L, "width_yd": round(FIELD_W,3), "endzone_yd": EZ,
              "brick_yd": 20.0, "spec": "UFA 2026: 80 yd playing proper, 20 yd endzones, 53 1/3 yd wide"},
    "teams": {
        "sol":   {"name": "Austin Sol", "short": "SOL", "kit": "light"},
        "chill": {"name": "Minnesota Wind Chill", "short": "MIN", "kit": "dark"},
    },
    "camera": {
        "model": "pinhole, fixed position, pan/tilt/zoom",
        "image_w": IMG_W, "image_h": IMG_H,
        "position_yd": [round(float(v),2) for v in CAM_POS],
        "per_frame": [{"aim": [round(float(aim[i,0]),2), round(float(aim[i,1]),2)],
                       "focal_px": round(float(focal[i]),1)} for i in range(N)],
    },
    "disc": [[round(float(a),2), round(float(b),2), round(float(c),2)] for a,b,c in DISC],
    "events": EVENTS,
    "players": players_out,
    "known_error": SWAP,
}
with open("/home/claude/ultimate-radar/fixtures/possession_demo.json","w") as fh:
    json.dump(doc, fh, separators=(",",":"))

vis_pct = {p["id"]: round(100*sum(1 for s in p["state"] if s=="observed")/N) for p in players_out}
print("frames", N, "bytes", len(json.dumps(doc, separators=(',',':'))))
print("observed % per player:", vis_pct)
print("mean simultaneously observed:", round(np.mean([sum(1 for p in players_out if p["state"][i]=="observed") for i in range(N)]),2), "/ 14")
