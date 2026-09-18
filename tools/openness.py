"""Run the viewer's openness card under node, and read who it could not see.

    from tools import openness as OP
    html = pathlib.Path("docs/index.html").read_text(encoding="utf-8")
    OP.claim(html, doc, f=238, who="O4")     # {'value': '5.1 yd', 'unseen': [...], ...}
    OP.scan(html, doc).bad                   # every measured claim over an unseen slot

`tools/audit_site.py` reads published JSON on purpose and says why. This is the
fourth exception, after the accuracy sentence, the tag list and the self-pass
guard, and it is the same shape of exception: the defect is not in the data.
Every field behind p0001's 15.867 s separation is correct and honest. D5 is
`predicted` there and the file says so plainly. What was wrong was the claim
built out of those fields - a nearest-defender number, badged `measured`, with a
defender left out of both the search and the sentence.

**An openness claim is a minimum over a set.** "The receiver had 5.1 yd" is not a
statement about the nearest defender; it is a statement about all seven, and one
of the seven was not seen. A minimum over a set with an unseen member is not a
measurement of that minimum, however well the other six were seen, so the badge
has to rest on the whole set and the missing ones have to be named.

So, as with the other three, this does **not** re-implement the claim in Python.
`opennessCard` is lifted out of the page along with everything it reads - the
claim itself, `at`, `dist`, `coverage`, `evidence`, `seenDefenders`, the jersey
lookup, the three prose helpers, and the two state constants - and run under
node. A Python copy would carry its own idea of which states count as seen, and
would go on agreeing with itself the day the page changed its mind.

**It lifts the card, not the claim.** `opennessClaim` decides what is true;
`opennessCard` is the whole of what a reader is told about it - the figure, the
badge, the tail on the context line and the sentence that accounts for it. #14
asks that the check fail when a measured badge *renders* over an unseen defender,
and a check on the claim alone stays green over a card that quietly stops naming
anybody. The one hop this still does not cover is `renderCards` pasting those
strings into `card()`; `docs/30` § 2.19 says so rather than claiming otherwise.

`scan` sweeps every frame and every attacker on a possession and returns two
lists: claims that badge `measured` while a defender is outside
`observed`/`confirmed`, and cards that never mention a defender they could not
see. `sighted` and `blinded` are the other half, per AD-12: hand the page a
defence it can see whole and a measured badge has to appear, take one slot back
out of sight and every measured claim has to go. The positive scenario is
constructed because p0005 makes no measured claim of its own on any of its 450
frames, and an ablation that takes away nothing from nothing is a row that passes
having covered nothing (AD-11).
"""

from __future__ import annotations

import json
from typing import NamedTuple

from tools.page_js import NoNode, extract, extract_const, node, run_source  # noqa: F401

FUNC = "opennessCard"

# What the card reads out of the page, in the order node needs it declared.
# `evidence` calls `coverage`, and both read the two state sets, so the sets come
# first. Lifting them rather than restating them is the point: `MEASURABLE` is
# the definition of "seen" this whole check turns on, and a second copy of it
# here would pass forever while the page moved underneath.
CONSTS = ("ANCHORED", "MEASURABLE")
FUNCS = ("at", "dist", "coverage", "evidence", "seenDefenders", "opennessClaim",
         "readingsFor", "jerseyOf", "unseenName", "unseenTail", "unseenSentence",
         FUNC)

# `window.POSSESSION` and the names the page binds off it at load. These are
# viewer/index.html's own lines - the roster at 393-394, and the jersey store
# seeded from `identity_readings` - and the harness holds them for the same
# reason `gate_sentence`'s does: the card closes over `PL`, `BY`, `DEF` and
# `JERSEY`, and a harness that invented them would be testing its own roster.
_PREAMBLE = """\
globalThis.window = globalThis;
const IN = require(process.argv[2]);
const D = IN.doc;
const OFF = D.possession.offense, DEF = D.possession.defense;
const PL = D.players, BY = Object.fromEntries(PL.map(p => [p.id, p]));
const JERSEY = (D.identity_readings || []).slice();
__SRC__
"""

_HARNESS = _PREAMBLE + """\
const NF = D.possession.frames;
const out = [], unnamed = [];
let measured = 0, claims = 0;
for(let f = 0; f < NF; f++){
  for(const p of PL){
    if(p.team !== OFF) continue;
    const c = opennessCard(f, p.id);
    if(c.yd === null) continue;
    claims++;
    if(c.ev === "measured"){
      measured++;
      if(c.unseen.length) out.push({f, who: p.id,
                                    unseen: c.unseen.map(u => u.slot)});
    }
    // ...and the other half: wherever a slot is missing, the card has to say so.
    // A badge that downgrades over a defender the reader is never told about is
    // the same omission wearing a quieter costume, and it is the half that
    // survives somebody deleting the naming and leaving the badge alone.
    const said = c.tail + c.why;
    const silent = c.unseen.filter(u => said.indexOf(u.slot) < 0).map(u => u.slot);
    if(silent.length) unnamed.push({f, who: p.id, unseen: silent});
  }
}
process.stdout.write(JSON.stringify({bad: out, unnamed, measured, claims}));
"""

# One card, for a caller that wants to look at a single frame.
_ONE = _PREAMBLE + """\
process.stdout.write(JSON.stringify(opennessCard(IN.f, IN.who)));
"""


def source(page_html: str) -> str:
    """The card and everything it reads, lifted out of the page as JS."""
    parts = [extract_const(page_html, c) for c in CONSTS]
    parts += [extract(page_html, f) for f in FUNCS]
    return "\n".join(parts)


def claim(page_html: str, doc: dict, f: int, who: str) -> dict:
    """The card the page builds about `who`'s room on frame `f`, strings and all."""
    return json.loads(run_source(_ONE.replace("__SRC__", source(page_html)),
                                 {"doc": doc, "f": int(f), "who": who}, FUNC))


class Scan(NamedTuple):
    """Every openness card a possession's page can build, swept in one node run."""

    claims: int          # attacker-frames that produce a number at all
    measured: int        # ...of those, the ones badged `measured`
    bad: list            # ...of those, the ones with a defender unseen
    unnamed: list        # cards with an unseen defender they never mention

    @property
    def ok(self) -> bool:
        return not self.bad and not self.unnamed

    def say(self) -> str:
        """The one clause the gate's `got` needs."""
        if self.bad:
            b = self.bad[0]
            return (f"{len(self.bad)} measured claim(s) over an unseen defender, "
                    f"first at frame {b['f']} on {b['who']} "
                    f"({', '.join(b['unseen'])} unseen)")
        if self.unnamed:
            u = self.unnamed[0]
            return (f"{len(self.unnamed)} card(s) never name a defender they "
                    f"could not see, first at frame {u['f']} on {u['who']} "
                    f"({', '.join(u['unseen'])})")
        return (f"{self.measured} measured of {self.claims} claims, none over an "
                "unseen defender, and every unseen slot named")


def scan(page_html: str, doc: dict) -> Scan:
    """Run the page's card over every frame and every attacker."""
    r = json.loads(run_source(_HARNESS.replace("__SRC__", source(page_html)),
                              {"doc": doc}, FUNC))
    return Scan(claims=r["claims"], measured=r["measured"], bad=r["bad"],
                unnamed=r["unnamed"])


# The state a defender takes when the camera loses it: drawn, dead-reckoned, and
# outside `MEASURABLE`. Used to construct the negative scenario, because no
# published possession is free of unseen defenders to start with and a check that
# only ever sees one arrangement has not been tested against the other.
BLIND = "predicted"


def blinded(doc: dict, slot: str) -> dict:
    """`doc` with one defender out of sight on every frame, and nothing else touched.

    The ablation AD-12 asks for. `scan` passing on the published document proves
    the claims that badge `measured` have no unseen defender behind them; it does
    not prove the badge would notice one. Put a defender the camera did see out of
    sight everywhere, and every measured claim on the page has to disappear.
    """
    players = []
    for p in doc["players"]:
        if p["id"] == slot:
            p = {**p, "state": [BLIND] * len(p["state"])}
        players.append(p)
    return {**doc, "players": players}


def sighted(doc: dict) -> dict:
    """`doc` with every slot `observed` on every frame, and no position touched.

    The positive half of the probe, and the reason it is constructed rather than
    taken from the possession. p0005 has one frame in 450 where all seven
    defenders were seen and it does not clear the coverage bar, so p0005 makes no
    measured claim at all - and `blinded` taking away nothing from nothing is a
    row that passes having covered nothing (AD-11). Hand the page a defence it
    can see whole and a measured badge has to appear; take one slot back out and
    it has to go. Both halves then bite on every page.
    """
    return {**doc, "players": [{**p, "state": ["observed"] * len(p["state"])}
                               for p in doc["players"]]}


def a_seen_defender(doc: dict) -> str | None:
    """A defence slot the camera saw on at least one frame, or None.

    Named rather than assumed: `blinded` has to take away a sighting that was
    there, and blinding a slot that was already unseen throughout would prove
    nothing while passing.
    """
    seen = {"observed", "confirmed"}
    for p in doc["players"]:
        if p["team"] == doc["possession"]["defense"] and any(s in seen for s in p["state"]):
            return p["id"]
    return None
