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

Three site gates now: `no unmeasured percentage printed` and `an unmeasured page says so`,
both owned by #11 with `docs/30` § 2.7 as the finding; and `published tags show on load`,
owned by #12 with § 2.8.
