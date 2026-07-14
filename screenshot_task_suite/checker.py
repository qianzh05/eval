#!/usr/bin/env python3
"""Deterministic checker for the screenshot task suite pilot.

Implements _meta.check_semantics from tasks/pilot_tasks.json (v4, 2026-07-11):
  normalize -> boundary-aware gold+distractor candidates -> negation/attribution
  exemptions -> PASS iff a gold candidate survives and the LAST surviving
  candidate is gold. Set-match tasks use their stated extraction rules against
  one of the listed gold sets. Generation-2 chained tasks add decimal/dual gold
  literals and a success-gating URL check (the logged Wolfram Alpha query must
  contain the correct year + topic; see check_semantics.url_gate).

Gate: `python3 test_checker.py` must pass every _meta.test_vectors entry
before any pilot run is scored.

API:
    from checker import check
    check("pilot-T1-3c", "WA reports 1.91%",
          urls=["...wolframalpha.com/input?i=us+inflation+rate+2018"]) ->
        {"verdict": "PASS"|"FAIL", "final_assertion": <label|None>,
         "url_gate": "pass"|"fail"|"not_evaluated"|absent, ...}
    For gated tasks, scoring runs MUST pass urls (steps.jsonl url_before/
    url_after up to and including the answer step); urls=None only reports
    url_gate="not_evaluated" and does not gate.

Stdlib only. No LLM anywhere.
"""

import re
from collections import namedtuple
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------- normalize

def _fold_thousands(s):
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", s)
    return s


def normalize(s):
    s = _fold_thousands(s)
    s = re.sub(r"(?i)US\$|USD|\$", "", s)
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = re.sub(r"(?i)\b(?:negative|minus)\s+(?=\d)", "-", s)
    return s


# ------------------------------------------------------------- candidates

Cand = namedtuple("Cand", "start end kind label")  # kind: 'gold' | 'distractor'


def _blocked_before(s, st):
    """A digit, or a decimal point attached to a digit, immediately before."""
    if st == 0:
        return False
    c = s[st - 1]
    return c.isdigit() or (c == "." and st > 1 and s[st - 2].isdigit())


def _blocked_after(s, en):
    """A digit, or a decimal point followed by a digit (true decimal
    continuation), immediately after. A sentence-ending period does NOT block."""
    if en >= len(s):
        return False
    c = s[en]
    return c.isdigit() or (c == "." and en + 1 < len(s) and s[en + 1].isdigit())

_NEG = re.compile(
    r"(?i)(?:\bnot\b|n't\b|\bnever\b|\bwrong\b|\bincorrect\b"
    r"|\brather than\b|\binstead of\b|\bexcluding\b)"
)
# clause break between marker and candidate protects the candidate;
# a spaced dash is a break, an unspaced dash (range/sign) is not.
_BREAK = re.compile(r"[,;.]|\s-\s|(?i:\bbut\b)")


def _standalone_numbers(s, signed=False):
    """Yield (start, end, int_value) for standalone integers.

    Boundary rule: the char before and after the matched span may not be a
    digit or '.'. For signed=True a leading '-' is included only when it is a
    true sign (char before the '-' is a non-digit); a range dash like
    5000-22140 yields the positive 22140 instead.
    """
    pat = re.compile(r"-?\d+" if signed else r"\d+")
    pos = 0
    while True:
        m = pat.search(s, pos)
        if not m:
            return
        st, en, txt = m.start(), m.end(), m.group(0)
        if signed and txt.startswith("-"):
            before_ok = st == 0 or not (s[st - 1].isdigit() or s[st - 1] == ".")
            if not before_ok:  # range dash: emit unsigned part
                st += 1
                txt = txt[1:]
        if not _blocked_before(s, st) and not _blocked_after(s, en):
            yield st, en, int(txt)
        pos = en


def _decimal_matches(s, literal):
    """Boundary-aware occurrences of a decimal literal like '3.2' or '5.68'."""
    out = []
    for m in re.finditer(re.escape(literal), s):
        if not _blocked_before(s, m.start()) and not _blocked_after(s, m.end()):
            out.append((m.start(), m.end()))
    return out


# ------------------------------------------------------------- exemptions

def _apply_negation(s, cands):
    """A marker drops only the NEXT candidate, <=25 chars away, with no clause
    break and no other candidate in between."""
    dropped = set()
    for m in _NEG.finditer(s):
        nxt = None
        for i, c in enumerate(cands):
            if c.start >= m.end() and (nxt is None or c.start < cands[nxt].start):
                nxt = i
        if nxt is None:
            continue
        c = cands[nxt]
        gap = s[m.end():c.start]
        if c.start - m.end() <= 25 and not _BREAK.search(gap):
            dropped.add(nxt)
    return dropped


def _apply_attribution(s, cands, attr_map):
    """attr_map: label -> list of token regex strings (word-boundary applied by
    caller). Bidirectional window of 12 chars between token edge and candidate
    edge; drops that distractor candidate only."""
    dropped = set()
    for i, c in enumerate(cands):
        if c.kind != "distractor" or c.label not in attr_map:
            continue
        for tok in attr_map[c.label]:
            for tm in re.finditer(tok, s, re.I):
                if (0 <= c.start - tm.end() <= 12) or (0 <= tm.start() - c.end <= 12):
                    dropped.add(i)
    return dropped


def _verdict(s, cands, attr_map=None):
    cands = sorted(cands, key=lambda c: c.start)
    dropped = _apply_negation(s, cands)
    if attr_map:
        dropped |= _apply_attribution(s, cands, attr_map)
    survivors = [c for i, c in enumerate(cands) if i not in dropped]
    if survivors and survivors[-1].kind == "gold":
        return {"verdict": "PASS", "final_assertion": "gold"}
    final = survivors[-1].label if survivors else None
    return {"verdict": "FAIL", "final_assertion": final}


# --------------------------------------------------------------- per task

def _band_task(s, gold_value, lo, hi, signed=False, attr_map=None,
               attr_value=None, local_sub=None):
    if local_sub:
        s = re.sub(*local_sub, string=s)
    cands = []
    for st, en, val in _standalone_numbers(s, signed=signed):
        if val == gold_value:
            cands.append(Cand(st, en, "gold", "gold"))
        elif lo <= abs(val) <= hi and (not signed or val != gold_value):
            label = str(val)
            if attr_value is not None and val == attr_value:
                label = f"attr:{val}"
            cands.append(Cand(st, en, "distractor", label))
    amap = {}
    if attr_map and attr_value is not None:
        amap = {f"attr:{attr_value}": attr_map}
    return _verdict(s, cands, amap)


def check_t1_1(s):
    return _band_task(s, 17623, 17550, 17700)


def check_t1_2(s):
    # local: accept trailing .0 on the gold; then signed band on abs value
    s = re.sub(r"(-?22140)\.0(?!\d)", r"\1", s)
    cands = []
    for st, en, val in _standalone_numbers(s, signed=True):
        if val == -22140:
            cands.append(Cand(st, en, "gold", "gold"))
        elif 21500 <= abs(val) <= 22800:
            label = "attr:+22140" if val == 22140 else str(val)
            cands.append(Cand(st, en, "distractor", label))
    return _verdict(s, cands, {"attr:+22140": [r"\bmagnitude\b", r"\babsolute\b"]})


def check_t1_3r(s):
    return _band_task(
        s, 32037, 31500, 32500,
        attr_map=[r"\binclusive\w*\b", r"\bboth endpoints\b", r"\bend date\b"],
        attr_value=32038,
    )


def _literal_task(s, golds, spec):
    """Generation-2 decimal-literal task (check_semantics.decimal_golds).

    golds: list of gold literals; matching ANY of them is gold (dual golds).
    spec:  [(distractor_literal, [attribution token regexes])] - enumerated
    literals only, no bands, so verbatim source phrasing can't become a
    candidate."""
    cands = []
    for g in golds:
        for st, en in _decimal_matches(s, g):
            cands.append(Cand(st, en, "gold", "gold"))
    attr_map = {}
    for lit, toks in spec:
        for st, en in _decimal_matches(s, lit):
            cands.append(Cand(st, en, "distractor", lit))
        attr_map[lit] = toks
    return _verdict(s, cands, attr_map)


def check_t1_1c(s):
    # token lists widened 2026-07-11 after the gen-2 red-team: trailing-context
    # narration ('a year earlier', 'ending the year', 'the spring') must exempt
    # its value or correct verbose answers false-fail.
    mon = [r"\bmonth\w*"]
    peak = [r"\bApril\b", r"\bpeak\w*", r"\bhigh\b", r"\bspring\b",
            r"\breach\w*", r"\bpandemic\b", r"\brose\b", r"\bris\w*"] + mon
    yr_prev = [r"\b2019\b", r"\bprevious\b", r"\bprior\b", r"\bearlier\b",
               r"\byear before\b"]
    yr_next = [r"\b2021\b", r"\bfollowing\b", r"\bnext\b"]
    return _literal_task(s, ["8.1", "8.10"], [
        ("14.8", peak), ("14.7", peak + [r"\bpublished\b"]),
        ("6.7", [r"\bDec(?:ember)?\b", r"\bNov(?:ember)?\b",
                 r"\bend\w*(?:\s+of)?(?:\s+the)?(?:\s+year)?",
                 r"\byear[- ]?end\w*"] + mon),
        ("13.2", [r"\bMay\b"] + mon), ("11.0", [r"\bJune\b"] + mon),
        ("10.2", [r"\bJuly\b"] + mon), ("8.4", [r"\bAug(?:ust)?\b"] + mon),
        ("7.8", [r"\bSept?(?:ember)?\b"] + mon),
        ("6.9", [r"\bOct(?:ober)?\b"] + mon),
        ("4.4", [r"\bMarch\b"] + mon),
        ("3.6", [r"\bJan(?:uary)?\b"] + mon + yr_prev),
        ("3.5", [r"\bFeb(?:ruary)?\b"] + mon),
        ("3.7", yr_prev), ("5.3", yr_next), ("5.4", yr_next),
    ])


def check_t1_2c(s):
    return _literal_task(s, ["17.3", "17.1"], [
        ("16.9", [r"\b1922\b", r"\bDec(?:ember)?\b", r"\bApril\b", r"\bMay\b",
                  r"\bmonth\w*", r"\bfall\w*", r"\bfell\b", r"\bspring\b"]),
        ("16.8", [r"\b1922\b"]),
        ("17.5", [r"\b1925\b"]), ("17.9", [r"\b1925\b"]),
        ("17.7", [r"\b1926\b"]), ("17.4", [r"\b1927\b"]),
        ("17.2", [r"\b1928\b", r"\b1929\b"]),
    ])


def check_t1_3c(s):
    conv = [r"\bannual\w*", r"\baverage\b", r"\bfull\b", r"\bwhole\b",
            r"\bcalendar\b"]
    return _literal_task(s, ["1.91", "1.9", "1.90"], [
        ("2.44", conv), ("2.4", conv), ("2.49", conv),
        ("2.1", [r"\b2017\b"]), ("2.3", [r"\b2019\b"]),
        ("1.8", [r"\b2019\b"]), ("2.2", [r"\b2019\b"]),
    ])


def check_t2_2(s):
    low = s.lower()
    gold_sub = "llama-3.2-1b-instruct-iq3_m.gguf"
    cands, gold_spans = [], []
    for m in re.finditer(re.escape(gold_sub), low):
        cands.append(Cand(m.start(), m.end(), "gold", "gold"))
        gold_spans.append((m.start(), m.end()))
    for m in re.finditer(r"\bi?q\d[a-z0-9_]*\b", low):
        if any(a <= m.start() and m.end() <= b for a, b in gold_spans):
            continue  # inside the gold filename
        if m.group(0) == "iq3_m":
            continue  # the gold's own quant token is never a distractor
        cands.append(Cand(m.start(), m.end(), "distractor", m.group(0)))
    return _verdict(s, cands)


def check_t2_3(s):
    low = s.lower()
    cands = []
    for m in re.finditer(r"\bfrank\b", low):
        m2 = re.search(r"\bschulenburg\b", low[m.end():m.end() + 60])
        if m2:
            cands.append(Cand(m.start(), m.end() + m2.end(), "gold", "gold"))
    return _verdict(s, cands)


_SET_A = {"1710.09829", "1811.06969", "1906.06818"}
_SET_B = _SET_A | {"1907.02957"}


def check_t3_1(s):
    ids = set()
    for m in re.finditer(r"\d{4}\.\d{4,5}", s):
        if _blocked_before(s, m.start()) or _blocked_after(s, m.end()):
            continue
        ids.add(m.group(0))
    ok = ids == _SET_A or ids == _SET_B
    return {"verdict": "PASS" if ok else "FAIL",
            "extracted": sorted(ids),
            "final_assertion": None if ok else "set-mismatch"}


_GOLD_ISSUES = {8135, 8324, 8454, 8569}
_MONTHS = (r"january|february|march|april|may|june|july|august|september"
           r"|october|november|december")


def check_t3_2(s):
    s2 = re.sub(r"\d{4}-\d{2}-\d{2}", " ", s)
    s2 = re.sub(rf"(?i)\b(?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s*,?\s*\d{{4}})?\b", " ", s2)
    s2 = re.sub(rf"(?i)\b(?:{_MONTHS})\s+\d{{4}}\b", " ", s2)
    vals = set()
    for m in re.finditer(r"(#?)(\d+)", s2):
        if _blocked_before(s2, m.start()) or _blocked_after(s2, m.end()):
            continue
        v = int(m.group(2))
        if m.group(1) == "#":
            vals.add(v)
        elif v >= 1000 and not (1900 <= v <= 2099):
            vals.add(v)
    ok = vals == _GOLD_ISSUES
    return {"verdict": "PASS" if ok else "FAIL",
            "extracted": sorted(vals),
            "final_assertion": None if ok else "set-mismatch"}


def check_t4_1(s):
    cands = []
    for m in re.finditer(r"(?i)\b(\d+|sixteen)\s+(?:\w+\s+)?modules?\b", s):
        tok = m.group(1).lower()
        kind = "gold" if tok in ("16", "sixteen") else "distractor"
        cands.append(Cand(m.start(1), m.end(1), kind, "gold" if kind == "gold" else tok))
    for m in re.finditer(r"(?i)\bmodules?\s*[:\-]?\s*(\d+|sixteen)\b", s):
        tok = m.group(1).lower()
        kind = "gold" if tok in ("16", "sixteen") else "distractor"
        cands.append(Cand(m.start(1), m.end(1), kind, "gold" if kind == "gold" else tok))
    # dedupe overlapping captures
    seen, uniq = set(), []
    for c in sorted(cands, key=lambda c: c.start):
        if (c.start, c.end) not in seen:
            seen.add((c.start, c.end))
            uniq.append(c)
    if not uniq:
        # v3.1 fallback: a correct minimal answer ("16") has no 'module' token
        # to bind to. If the answer contains exactly ONE standalone number (or
        # 'sixteen') that is NOT bound to another unit noun, it is the
        # candidate; "16 weeks" stays excluded and still fails.
        unit = re.compile(r"(?i)\b(?:\d+|sixteen)\s+(?:\w+\s+)?"
                          r"(?:hours?|weeks?|minutes?|days?|stars?|ratings?|reviews?)\b")
        unit_spans = [(m.start(), m.end()) for m in unit.finditer(s)]
        loose = []
        for st, en, val in _standalone_numbers(s):
            if not any(a <= st and en <= b for a, b in unit_spans):
                loose.append((st, en, str(val)))
        for m in re.finditer(r"(?i)\bsixteen\b", s):
            if not any(a <= m.start() and m.end() <= b for a, b in unit_spans):
                loose.append((m.start(), m.end(), "sixteen"))
        if len(loose) == 1:
            st, en, tok = loose[0]
            kind = "gold" if tok in ("16", "sixteen") else "distractor"
            uniq = [Cand(st, en, kind, "gold" if kind == "gold" else tok)]
    return _verdict(s, uniq)


def check_t4_2(s):
    cands = []
    for val, kind in ((1399, "gold"), (1299, "distractor"), (1499, "distractor")):
        for m in re.finditer(rf"{val}(?:\.00)?", s):
            if _blocked_before(s, m.start()) or _blocked_after(s, m.end()):
                continue
            cands.append(Cand(m.start(), m.end(), kind,
                              "gold" if kind == "gold" else str(val)))
    return _verdict(s, cands, {"1299": [r"\b8-core\b"], "1499": [r"\b15-inch\b"]})


_MILLION = re.compile(r"^\s*(?:\w+\s+)?(?:million|mn|m)\b", re.I)


def check_p0_2(s):
    cands = []
    for m in re.finditer(r"3\.90?", s):
        if _blocked_before(s, m.start()) or _blocked_after(s, m.end()):
            continue
        if _MILLION.match(s[m.end():]):
            continue  # population-count mention: neither gold nor distractor
        cands.append(Cand(m.start(), m.end(), "gold", "gold"))
    table_tokens = [r"\btable\b", r"\bcomput\w*", r"\bcalculat\w*", r"\bcohort\b",
                    r"\bboth sexes\b"]
    spec = [("3.3", [r"\bmales?\b"]), ("3.1", table_tokens), ("3.2", table_tokens),
            ("5.68", table_tokens), ("7.22", table_tokens),
            ("4.0", [r"\b50-54\b", r"\blargest\b"])]
    attr_map = {}
    for lit, toks in spec:
        for st, en in _decimal_matches(s, lit):
            cands.append(Cand(st, en, "distractor", lit))
        attr_map[lit] = toks
    for m in re.finditer(r"4\s*%", s):  # '4%' distractor
        if not _blocked_before(s, m.start()):
            cands.append(Cand(m.start(), m.end(), "distractor", "4.0"))
    return _verdict(s, cands, attr_map)


TASKS = {
    # generation-2 chained T1 (2026-07-11)
    "pilot-T1-1c": check_t1_1c,
    "pilot-T1-2c": check_t1_2c,
    "pilot-T1-3c": check_t1_3c,
    "pilot-T2-2": check_t2_2,
    "pilot-T2-3": check_t2_3,
    "pilot-T3-1": check_t3_1,
    "pilot-T3-2": check_t3_2,
    "pilot-T4-1": check_t4_1,
    "pilot-T4-2": check_t4_2,
    "pilot-P0-2": check_p0_2,
    # retired generation-1 tasks, kept runnable as alternates
    # (specs: tasks/pilot_tasks_gen1_2026-07-10.json)
    "pilot-T1-1": check_t1_1,
    "pilot-T1-2": check_t1_2,
    "pilot-T1-3r": check_t1_3r,
}

# success-gating URL requirements (check_semantics.url_gate):
# (query_must_all, query_must_any), word-boundary-matched against the decoded
# i= parameter of wolframalpha.com/input URLs from steps.jsonl. Host and path
# are checked structurally (red-team 2026-07-11: substring matching passed
# timestamp params and search-engine URLs that merely mention WA).
_URL_GATES = {
    "pilot-T1-1c": (["2020"], ["unemployment", "unemployed", "jobless"]),
    "pilot-T1-2c": (["1923"], ["cpi", "consumer price", "price index",
                               "cost of living"]),
    "pilot-T1-3c": (["2018"], ["inflation", "cpi", "consumer price"]),
}


def _tok(query, token):
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", query)


def check_url_gate(task_id, urls):
    gate = _URL_GATES.get(task_id)
    if gate is None:
        return "not_applicable"
    must_all, must_any = gate
    for u in urls or []:
        try:
            p = urlparse(str(u))
        except ValueError:
            continue
        host = (p.hostname or "").lower()
        if host != "wolframalpha.com" and not host.endswith(".wolframalpha.com"):
            continue
        if not p.path.startswith("/input"):
            continue
        for q in parse_qs(p.query).get("i", []):
            ql = q.lower()
            if all(_tok(ql, t) for t in must_all) and any(_tok(ql, t) for t in must_any):
                return "pass"
    return "fail"


def check(task_id, final_answer, urls=None):
    if task_id not in TASKS:
        raise KeyError(f"unknown task id: {task_id}")
    if not final_answer or not final_answer.strip():
        res = {"verdict": "FAIL", "final_assertion": "empty-answer"}
    else:
        res = TASKS[task_id](normalize(final_answer))
    if task_id in _URL_GATES:
        if urls is None:
            res["url_gate"] = "not_evaluated"
            res["requires_urls"] = True
        else:
            gate = check_url_gate(task_id, urls)
            res["url_gate"] = gate
            if gate == "fail":
                # keep the string verdict for the failure rubric
                # (wrong-WA-query vs pod-read-failure need it)
                res = {"verdict": "FAIL", "final_assertion": "url-gate",
                       "url_gate": "fail", "string_result": res}
    return res


if __name__ == "__main__":
    import sys
    print(check(sys.argv[1], sys.argv[2],
                sys.argv[3].split(",") if len(sys.argv) > 3 else None))
