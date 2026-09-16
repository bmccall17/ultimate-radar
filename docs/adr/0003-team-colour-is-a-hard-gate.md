# AD-3 — Team colour is a hard gate

> **Amended 2026-09-14, after the round-2 ghost audit.** The decision's *reason* is
> unchanged and is still the important part: **a cross-team identity swap corrupts every
> matchup, every separation number and the scheme classifier at once, so it is forbidden
> outright.** That prohibition is intact and is measured at zero on p0001 before and after.
> What changed is what the prohibition applies to.
>
> **(a) The gate is on a confident kit call, not on a hard three-way label.** `ur/team.py`
> emits `team_p`, the probability that a detection's torso is the team it is labelled. A
> detection the classifier puts at P ≥ 0.9 for one kit can never be associated to a slot of
> the other — that is AD-3, unchanged. Below that the detection is admissible to either team
> and pays `−2 ln P(kit = slot's team)` in the assignment cost, in the same units as the
> squared Mahalanobis distance because both are twice a negative log likelihood. Association
> is blocked outright once the kit evidence leans 3:1 to the other team (`KIT_BLOCK_P`).
>
> **(b) A weak kit call is no longer a deletion.** This is the substantive change. The old
> code did not merely refuse to cross teams on a `weak_team` detection, it **excluded that
> detection from association entirely**, on the grounds recorded in `docs/17` that such
> detections were "over half referees and camera crew". Measured against
> `eval/m3/team_labels.json`, which labels every in-bounds box on 20 held-out frames, the
> `weak_team` set is **14 real players, 5 non-players and 3 boxes spanning two players** —
> 64 % players, not the majority non-players the exclusion assumed. It was the single largest
> cause of slots going blind: 218 slot-frames on p0001 where a usable detection sat within
> 1.5 yd of a slot that was dead-reckoning instead.
>
> **(c) The assignment is solved once, not once per team.** A kit-ambiguous detection is a
> candidate for slots on both teams, and two separate per-team solves would each be free to
> take it — which is how one person becomes two players. One Hungarian over all fourteen
> slots is what makes the one-to-one constraint mean anything now that the teams' candidate
> sets overlap. `tools/m4_structure.py` checks for shared detections and measures zero.
>
> **What still protects against a cross-team swap, now that the gate is not on the label.**
> Four things, in order of how much work they do:
>
> 1. **The confident-kit prohibition itself.** The kits are ΔE 36.6 apart in CIELAB and only
>    1 of 234 hand-labelled players is misclassified by luminance alone. The overwhelming
>    majority of detections are confident, and for those nothing changed at all.
> 2. **The 3:1 block.** Measured across block thresholds of 0.10 to 0.50, the observed
>    fraction is flat (0.714 ± 0.001) while assignments taking a detection whose nearer label
>    is the other team fall from 21 to 0. Coverage does not pay for the strictness, so the
>    setting is taken from the strict end of the plateau.
> 3. **The cost, not just the gate.** An ambiguous detection carries a penalty of up to 2.8
>    against a chi-square gate of 9.21, so it loses every contest that is close on geometry.
>    A confident same-team candidate beats it every time.
> 4. **Cold starts still require a confident kit.** A slot that has never been observed has
>    no motion model and no competing claim to catch a bad seed, so it may only be seeded
>    from a detection at P ≥ 0.9.
>
> **What this gives up, stated plainly.** 13 of 3568 assignments on p0001 take a detection
> whose nearer label is the other team, all at P 0.25–0.49 — never confident. Under the old
> rule those 13 would have been dropped rather than crossed, and some of them are probably
> wrong. The trade is 13 uncertain crossings against 218 slot-frames of blindness, and the
> crossings are visible in `tracks.json` as `assoc.kit_p` rather than silent.
>
> The original decision, which still governs where the amendment is silent:

Torso-crop colour, clustered into two groups per point, assigns team. Association across
teams is forbidden outright.

*Why.* The Sol wear light kit and the Wind Chill dark; the separation is close to trivial and
far more reliable than any learned re-ID embedding. Cross-team identity swaps are the single
most damaging error for a defensive-analysis tool — they corrupt every matchup, every
separation number, and the scheme classifier at once. Forbidding them removes that whole
class of error and halves the assignment problem.

*Consequence.* Handle the third cluster: referees, sideline players, and coaches inside the
frame. Reject detections whose position falls outside the field bounds by more than ~2 yd,
and whose colour matches neither cluster tightly.

*Measured in M0: the colour half of this is safe, the reject half is harder than assumed.*
Torso separation is ΔE = 36.6 in CIELAB (L\* 31.8 dark vs 66.6 light), with the clusters
barely touching at the 5th/95th percentiles — colour will not be the failure mode. But two
reject cases are worse than this doc implies: **referees wear black-and-grey vertical stripes
and stand on the field**, landing squarely in the Wind Chill cluster in most live frames; and
**Wind Chill have a light-blue alternate kit** worn on the sideline, which lands in the *Sol*
cluster. So the out-of-bounds filter is doing more work than the colour gate. Build and
measure it first. See `docs/00-footage-report.md` Q5.
