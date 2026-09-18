# AD-12 — A gate may read the rendered page, when the data cannot show the defect

`tools/audit_site.py` reads the published JSON, not the rendered HTML, and that stays the
default. **One class of defect is exempt: a claim the formatter invents.** Where the data
is right and the page is wrong, the check runs the viewer's own function under node and
reads the string a reader gets.

Two constraints make it a rule rather than a licence to grep:

1. **Run the page's code, never a copy of it.** `tools/page_js.py` lifts the named
   function out of the published HTML as source and executes it. A Python
   re-implementation of the formatting would agree with itself and catch nothing.
2. **Take the input away rather than predict the output.** The test for a number nobody
   measured is to render the page a second time with every measurement removed and fail
   on any figure that survives. Nothing compares a printed value to an expected one.

*Why.* Five of six published pages printed a rounded `0 %` for tracker recall and again
for sigma containment. Both fields are `null` on those possessions and `measured_on` says
`p0001`: the data said "unmeasured" and meant it. `Math.round(null * 100)` is `0`.

Every data-side check was green, and correctly so. `no borrowed gate numbers` exists to
stop precisely this class of misstatement and could not see it, because the misstatement
was not in the numbers — it was in the rounding. AD-5 gets a state to every sample and
AGENTS rule 3 gets it as far as the page; one arithmetic op at the end threw it away.
**A formatter is a place a claim can be invented,** and no amount of reading the fields
will show you one.

*Why not simply always read the HTML.* Because the rule it bends is a finding too. The
first version of the site audit grepped rendered HTML for "the huck is on" and flagged it,
when the phrase survived only inside a code comment. What a page *asserts* lives in its
data; what a page *prints* is a different fact, and it is only worth the cost of asking
when the two can disagree.

*Why ablation rather than an expected value.* An expected-value check has to reproduce the
formatting to know what to expect — JS rounds half up, Python half to even, so the two
disagree about `12.5` — and it only ever catches the page it is looking at. Removing the
measurement asks the question the finding is actually about: is there anything behind this
number? That is what makes it fail on `p0001`, which prints a true `97 %` today over code
that was one null away from printing `0 %`. Comparing values called that page clean.

*What it costs.* **`node` on PATH**, for the first time in this project: MIT, exec'd as a
separate process like ffmpeg, a development dependency only, and a row in
`docs/07-licenses.md` before it was used (AGENTS rule 1). If it is missing, the rows go
red saying so rather than skipping — a gate that cannot run has not passed (AD-11), and so
do a renamed function and a node that throws, because a traceback out of a gate reports
nothing about any of the other 118 rows.

*The second instance, and what it confirmed.* p0001, p0003 and p0009 publish 6, 14 and 12
human tags, and all three pages opened saying **"Nothing tagged yet"** — the tag list
rendered from the array of tags made in the current browser tab, which starts empty, while
`D.events` reached the metric cards and the download button and never the list. Same shape
exactly: correct data, a page asserting the opposite, every field-side check green. It is
worth recording because the exemption above was written about a number the formatter
invented, and this is a formatter inventing an **absence** — which is the same act and
reads worse, because a reader takes "nothing tagged yet" as a fact about the possession
rather than as a gap. Both constraints held without amendment: `tools/tag_list.py` runs
the page's own `tagListHtml`, and it renders a second time with the published tags taken
away rather than comparing rows against expected text.

*The third instance, and the one that widens this decision.* `addTag()` refuses a catch
naming the player of the throw before it, and read only the tags made in the current
browser tab, so a throw already in `events.json` was invisible to it (§ 2.9). That is not a
claim the formatter invents. It is a **refusal the page fails to make**, and the exemption
above was written about printed claims.

It is the same exemption rather than a wider one, and the reason is the test at the top of
this file: *is this something the reader gets from the page that the data cannot show?* A
refusal qualifies on both halves. The reader gets it — it is the sentence that appears, or
does not, when they press `c`. And the data cannot show it: every `events.json` in `work/`
is correct, so no published possession contains a self-pass, and no amount of reading them
reveals a guard that would let one through. So the wording stands with one word widened:
the exemption covers **what a page states**, whether that is a number it prints or a
refusal it owes.

*The constraint that widening costs.* A check on a printed claim has its subject in front
of it. A check on a refusal has to **construct the failure**, and a constructed scenario is
one the author chose, so it can be chosen to pass. Two scenarios are therefore required
alongside it, and `a self-pass is always refused` carries both: **one legitimate case that
must not be refused**, without which a guard that refused every tag would go green, and
**the same case with the input taken away**, without which a guard that never read its
input at all would. The second is constraint 2 above, unchanged. The first is new, and it
is the price of checking a refusal rather than a claim.

*The fourth instance, and it needed the widening.* The separation card printed `5.1 yd` and
badged it `measured` while a defender sat `predicted` — named nowhere, searched anyway
(§ 2.19). It is a printed claim, so the original exemption covers it: the data is right, the
word above the number is not, and reading the fields cannot show you which players a
sentence quantifies over. What it takes from the widening is the **constructed positive**.
Sweeping the published page proves only that it makes no such claim today; a card that
badged nothing `measured` would pass forever. So `tools/openness.py` hands the page a
defence it can see whole, which must reach a measured badge, and then blinds one slot, which
must take every measured badge away. p0005 makes no measured claim on any of its 450 frames,
so without the first half the ablation would take nothing from nothing — AD-11 again, in the
place the widening predicted it.

Five site gates now: `no unmeasured percentage printed` and `an unmeasured page says so`,
both owned by #11 with `docs/30` § 2.7 as the finding; `published tags show on load`, owned
by #12 with § 2.8; `a self-pass is always refused`, owned by #25 with § 2.9; and `no
measured claim over an unseen defender`, owned by #14 with § 2.19 and AD-15.
