# AD-7 — Events are tagged by hand; disc detection is a stretch goal

A small tagging pass: scrub, press `t` on a throw, `c` on a catch. Roughly 20 keystrokes per
possession. Heuristics may *suggest* events (the thrower is the near-stationary player with a
defender inside 2 yd while others cut) but the human confirms.

*Why.* Throw and catch timestamps unlock the metrics that matter and cost a minute of
attention. A disc detector good enough to replace them is a research project with a poor
success probability at this resolution.

> **Amended 2026-09-14, after building it.** The decision holds and is stronger than it was
> written. Two things measured:
>
> **(a) The heuristic does not merely *suggest* badly — it cannot be trusted at all without
> the human.** `ur/disc.py` infers the holder from the one signal the sport offers for free:
> a thrower plants a pivot and rule §15.1 keeps their mark within 3 m, so the pair is still
> while every other pair runs. Over a whole possession, solved as a sequence, it produces a
> throw list that **reverses direction 83 % of the time** and leaves the disc 35 yd short of
> the endzone it scored in. Sweeping the one free parameter across an order of magnitude does
> not fix it. The clause "heuristics may *suggest* events but the human confirms" was a
> safety margin; it turns out to be load-bearing.
>
> **(b) The tagging surface AD-7 specified was never built, and that is why the disc stage
> had nothing to stand on.** Two keys in the viewer, exactly as this decision describes.
> A tagged frame is a *hard constraint* on the holder, and the spans between tags are still
> solved, so partial tagging degrades gracefully. **Reverse steps 1 and 2 of `docs/25`'s
> build order**: tagging is not the fallback for when inference is not good enough, it is the
> source of the only ground truth this problem has. See `docs/27-disc.md`.
