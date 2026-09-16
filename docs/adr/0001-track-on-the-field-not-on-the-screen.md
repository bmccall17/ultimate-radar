# AD-1 — Track on the field, not on the screen

Detections are converted to field coordinates **before** association. The Kalman filter
runs in yards on the ground plane, not in pixels.

*Why.* A panning, zooming broadcast camera makes pixel-space motion meaningless: a
stationary player has large screen velocity during a pan. The standard fix is global motion
compensation (BoT-SORT's ORB/ECC module), which fits an affine model per frame and degrades
exactly when the camera zooms hard — which is when ultimate is most interesting. But we are
already computing a homography for the radar view. Using it one stage earlier makes the
motion model physical: a person accelerates at most ~6 yd/s² and sprints at most ~9.5 yd/s,
so the gate on association is a real constraint rather than a tuned pixel threshold. It also
means the tracker's state **is** the thing the radar draws — no second coordinate system to
keep in sync.

*Consequence.* Calibration quality becomes the upstream dependency for everything. A frame
whose homography residual is poor must down-weight its detections, not silently corrupt the
tracks. Carry `calibration.confidence` per frame into the tracker's measurement noise.

*Measured in M4: the sport constant the motion model needs.* Tracking on the ground plane
makes the motion model physical, which means it needs a physical number. That number is
**σ_v = 2.6 yd/s**, the stationary 1-sigma of one velocity component for an ultimate player
during a point. **It is not a tuning knob and should not be adjusted to make a tracker behave.**

It is not a sprint speed either — a sprint is ~9.5 yd/s, quoted above. It is the spread of a
velocity *component* over a whole point, most of which is spent moving moderately or standing,
and it sets how fast positional uncertainty grows while a player is unobserved.

Method (`tools/m4_speed.py`, `eval/m4/m4_speed.json`): single-frame differencing cannot measure
it, because 0.6 yd of foot-point noise over 1/15 s implies 9 yd/s — larger than the quantity
itself, and the tool prints zeroes at those baselines rather than a number. So displacement is
differenced over a range of baselines, the foot-point noise M3 *measured* is subtracted in
quadrature, and the integrated-Ornstein-Uhlenbeck displacement variance is inverted rather
than assuming velocity is constant over the baseline. The estimate rises out of the noise and
settles: **2.50, 2.64, 2.63 yd/s** at baselines of 0.8, 1.3 and 2.0 s. Fed back into the
filter and re-measured, it returns 2.635 and 2.623 — it converged.

One caveat, stated because the next person will want it: the noise subtracted (1.183 yd rms
over two frames) is about 10 % larger than M3's foot-point rms implies (1.076). Part of that
is genuine conservatism and part is population difference — M3's foot sample was restricted to
boxes ≥ 40 px tall, which are nearer players with smaller `yd_per_px`. Either way it biases
σ_v slightly low rather than high.
