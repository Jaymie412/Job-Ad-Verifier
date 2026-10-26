"""Local logic tests for contract.py (job-ad-verifier-0.3) using a small simulated GenLayer runtime.

AI answers are authored fixtures, not live AI. These tests check the contract's
deterministic behaviour (employer binding, reply window, bounded closure, exactly-once
accounting, hash-bound consent, quote checks, validator agreement, verdict rules),
not the model's judgement.
Run: python -m pytest test_contract.py -q
"""
import datetime
import json
import sys
import types
from pathlib import Path

import pytest

EMPLOYER = "0x" + "a" * 40
SEEKER = "0x" + "b" * 40
OUTSIDER = "0x" + "c" * 40
WINDOW_MIN = 10
T0 = datetime.datetime(2026, 10, 26, 12, 0, 0, tzinfo=datetime.timezone.utc)

SCAM_AD = ("URGENT. Elite Guard Recruitment is hiring security guards. Pay: 9.50 pounds per hour, cash weekly. "
           "Before your first shift you must pay 85 pounds for your training pack, DBS check and uniform. "
           "To apply, send a WhatsApp message to Dave on 07700 900123.")
UNRELATED_AD = ("Riverside Patrol Ltd is hiring door supervisors. Pay: 13.50 pounds per hour. "
                "Apply online through our careers website.")
WAGE = "National Living Wage (21 and over): 12.50 pounds per hour."
CH = "Search results. No results found."
FACTS = ["ad", "named", "fee", "offplatform", "pay", "company"]


class UserError(Exception):
    pass


class Return:
    def __init__(self, calldata):
        self.calldata = calldata


class Addr:
    def __init__(self, h):
        self.as_hex = h


def answers(**kv):
    """kv maps fact -> (answer, quote). Unlisted facts default to safe values."""
    defaults = {"ad": ("OK", ""), "named": ("Y", "Elite Guard Recruitment"), "fee": ("N", ""),
                "offplatform": ("N", ""), "pay": ("NOT_STATED", ""), "company": ("UNKNOWN", "")}
    defaults.update(kv)
    return {"facts": [{"fact": f, "answer": defaults[f][0], "quote": defaults[f][1]} for f in FACTS]}


SCAM_ANS = answers(fee=("Y", "you must pay 85 pounds for your training pack"),
                   offplatform=("Y", "send a WhatsApp message to Dave"),
                   pay=("BELOW", "Pay: 9.50 pounds per hour"), company=("NOT_FOUND", ""))
DEAD = answers(ad=("NOT_AD", ""), named=("N", ""))


class Sim:
    def __init__(self):
        self.sender = EMPLOYER
        self.now = T0
        self.pages = {"ad": SCAM_AD, "wage": WAGE, "ch": CH}
        self.leader_answer = None
        self.validator_answer = None
        self.audit = True
        self.in_validator = False
        self.prompts = []

    def advance(self, minutes):
        self.now = self.now + datetime.timedelta(minutes=minutes)

    def build_gl(self):
        sim = self
        gl = types.SimpleNamespace()
        gl.vm = types.SimpleNamespace(UserError=UserError, Return=Return)
        gl.public = types.SimpleNamespace(write=lambda f: f, view=lambda f: f)
        gl.Contract = object

        class Msg:
            @property
            def sender_address(self):
                return Addr(sim.sender)
        gl.message = Msg()

        class Raw:
            def __getitem__(self, key):
                assert key == "datetime"
                return sim.now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        gl.message_raw = Raw()

        def render(url, mode="text"):
            if "gov.uk" in url:
                return sim.pages["wage"]
            if "company-information" in url:
                return sim.pages["ch"]
            return sim.pages["ad"]

        def exec_prompt(prompt, response_format=None):
            sim.prompts.append(prompt)
            if prompt.startswith("Audit the proposed"):
                return {"accept": sim.audit}
            ans = sim.validator_answer if (sim.in_validator and sim.validator_answer is not None) else sim.leader_answer
            return ans(prompt) if callable(ans) else ans
        gl.nondet = types.SimpleNamespace(exec_prompt=exec_prompt, web=types.SimpleNamespace(render=render))

        def run_nondet_unsafe(leader_fn, validator_fn):
            sim.in_validator = False
            out = leader_fn()
            sim.in_validator = True
            try:
                ok = validator_fn(Return(out))
            finally:
                sim.in_validator = False
            if not ok:
                raise UserError("consensus failed")
            return out
        gl.vm.run_nondet_unsafe = run_nondet_unsafe
        return gl


@pytest.fixture
def env():
    sim = Sim()
    mod = types.ModuleType("genlayer")
    mod.gl = sim.build_gl()
    mod.TreeMap = dict
    mod.u256 = int
    sys.modules["genlayer"] = mod
    src = Path(__file__).with_name("contract.py").read_text()
    src = src.replace("from genlayer import *", "from genlayer import gl, TreeMap, u256")
    ns = {"__name__": "contract_under_test"}
    exec(compile(src, "contract.py", "exec"), ns)
    C = ns["JobAdVerifier"]
    c = C.__new__(C)
    c.employers, c.checks, c.demo_results = {}, {}, {}
    c.__init__(WINDOW_MIN)
    return sim, c, ns


def setup_check(sim, c, name="Elite Guard Recruitment"):
    sim.sender = EMPLOYER
    c.register_employer(name)
    sim.sender = SEEKER
    c.submit_ad(0, "https://example.org/ad.txt")


def checked(sim, c):
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    c.verify(0)
    return summary(c)["check_hash"]


def summary(c, cid=0):
    return json.loads(c.get_check_summary(cid))


def employer(c, eid=0):
    return json.loads(c.get_employer(eid))


def record(c, eid=0):
    return employer(c, eid)["record"]


# ---------- fix 1: adverts are bound to the selected employer ----------

def test_unrelated_advert_closes_without_touching_employer(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.pages["ad"] = UNRELATED_AD
    sim.leader_answer = answers(named=("N", ""))
    c.verify(0)
    s = summary(c)
    assert s["status"] == "UNRELATED" and s["last_label"] == "unrelated" and s["check_hash"] == ""
    assert record(c)["final_checks"] == 0 and employer(c)["counted_check_ids"] == []
    for fn in (lambda: c.finalise(0), lambda: c.verify(0)):
        with pytest.raises(UserError):
            fn()
    sim.sender = EMPLOYER
    with pytest.raises(UserError):
        c.accept_check(0, "")
    assert record(c)["final_checks"] == 0


def test_ai_claiming_a_different_company_is_the_employer_is_overruled_by_code(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.pages["ad"] = UNRELATED_AD
    # AI wrongly says Y, quoting a real line that names a DIFFERENT company: code refuses the binding.
    sim.leader_answer = answers(named=("Y", "Riverside Patrol Ltd"))
    c.verify(0)
    assert summary(c)["status"] == "UNRELATED"


def test_named_quote_must_come_from_the_advert_not_other_pages(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.pages["ad"] = UNRELATED_AD
    sim.pages["ch"] = "Search results. ELITE GUARD RECRUITMENT LTD - Active"
    sim.leader_answer = answers(named=("Y", "ELITE GUARD RECRUITMENT"))
    with pytest.raises(UserError):  # quote not in the advert -> rejected 3 times
        c.verify(0)
    assert summary(c)["status"] == "SUBMITTED"


def test_name_match_ignores_ltd_case_and_punctuation(env):
    _, _, ns = env
    f = ns["_names_employer"]
    assert f("ELITE GUARD RECRUITMENT LIMITED is hiring", "Elite Guard Recruitment Ltd")
    assert f("Elite-Guard Recruitment", "Elite Guard Recruitment")
    assert not f("Elite Guard", "Elite Guard Recruitment")
    assert not f("Riverside Patrol Ltd", "Elite Guard Recruitment")


def test_validators_must_agree_on_binding(env):
    sim, c, _ = env
    setup_check(sim, c)
    before = c.get_check(0)
    sim.leader_answer = SCAM_ANS
    sim.validator_answer = answers(named=("N", ""))
    with pytest.raises(UserError):
        c.verify(0)
    assert c.get_check(0) == before


# ---------- fix 2: the employer always gets a reply opportunity ----------

def test_jobseeker_cannot_finalise_before_reply_deadline(env):
    sim, c, _ = env
    checked(sim, c)
    assert summary(c)["reply_deadline"] == "2026-10-26 12:10:00 UTC"
    sim.sender = SEEKER
    sim.advance(9)
    with pytest.raises(UserError) as e:
        c.finalise(0)
    assert "can still reply until" in str(e.value)
    assert summary(c)["status"] == "CHECKED" and record(c)["final_checks"] == 0


def test_finalise_after_deadline_counts_once(env):
    sim, c, _ = env
    checked(sim, c)
    sim.advance(WINDOW_MIN + 1)
    sim.sender = SEEKER
    c.finalise(0)
    s = summary(c)
    assert s["status"] == "FINAL" and s["final"] == {"verdict": "likely_scam", "reason": "reply_window_expired",
                                                      "replied": False}
    r = record(c)
    assert r["final_checks"] == 1 and r["likely_scam"] == 1 and r["replies_used"] == 0


def test_reply_refused_after_deadline(env):
    sim, c, _ = env
    h = checked(sim, c)
    sim.advance(WINDOW_MIN + 1)
    sim.sender = EMPLOYER
    with pytest.raises(UserError) as e:
        c.reply(0, h, "The fee is refunded after the first month.")
    assert "reply window closed" in str(e.value)


def test_employer_can_accept_early_with_hash(env):
    sim, c, _ = env
    h = checked(sim, c)
    sim.sender = EMPLOYER
    with pytest.raises(UserError):
        c.accept_check(0, "0" * 64)
    sim.sender = SEEKER
    with pytest.raises(UserError):
        c.accept_check(0, h)  # only the employer can waive its own reply
    sim.sender = EMPLOYER
    c.accept_check(0, h)
    assert summary(c)["final"]["reason"] == "employer_accepted"
    assert record(c)["final_checks"] == 1


# ---------- valid hash-bound reply ----------

def test_valid_hash_bound_reply_rechecks_and_counts_once(env):
    sim, c, _ = env
    h = checked(sim, c)
    sim.advance(5)
    sim.sender = EMPLOYER
    c.reply(0, h.upper(), "The 85 pound fee is refunded after the first month of work.")
    assert summary(c)["status"] == "REPLIED"
    assert json.loads(c.get_check(0))["reply"]["acknowledged_hash"] == h
    c.verify(0)
    s = summary(c)
    assert s["status"] == "FINAL" and s["assessments"] == 2
    assert s["final"] == {"verdict": "likely_scam", "reason": "rechecked_after_reply", "replied": True}
    assert "refunded after the first month" in sim.prompts[-2]
    r = record(c)
    assert r["final_checks"] == 1 and r["replies_used"] == 1


def test_reply_needs_employer_exact_hash_and_only_once(env):
    sim, c, _ = env
    h = checked(sim, c)
    sim.sender = SEEKER
    with pytest.raises(UserError):
        c.reply(0, h, "The jobseeker cannot reply for the employer.")
    sim.sender = EMPLOYER
    with pytest.raises(UserError):
        c.reply(0, "wronghash", "The fee is refunded after the first month.")
    c.reply(0, h, "The fee is refunded after the first month.")
    with pytest.raises(UserError):
        c.reply(0, h, "A second reply should be rejected.")
    with pytest.raises(UserError):
        c.finalise(0)


def test_check_hash_covers_the_deadline(env):
    sim, c, ns = env
    h = checked(sim, c)
    full = json.loads(c.get_check(0))
    first = full["assessments"][0]
    rebuilt = ns["_hash"]({"id": 0, "employer_id": 0, "ad_url": full["ad_url"], "submitter": SEEKER,
                           "outcome": first["outcome"], "answers": first["answers"],
                           "reply_deadline": full["reply_deadline"]})
    assert rebuilt == h


# ---------- fix 3: bounded closure when reply-stage evidence is unavailable ----------

def test_reply_stage_unavailable_closes_after_two_attempts(env):
    sim, c, _ = env
    h = checked(sim, c)
    sim.sender = EMPLOYER
    c.reply(0, h, "The fee is refunded after the first month.")
    sim.pages["ad"] = "404: Not Found"
    sim.leader_answer = DEAD
    c.verify(0)
    s = summary(c)
    assert s["status"] == "REPLIED" and s["unavailable"]["after_reply"] == 1 and record(c)["final_checks"] == 0
    c.verify(0)
    s = summary(c)
    assert s["status"] == "FINAL"
    assert s["final"] == {"verdict": "likely_scam", "reason": "reply_stage_evidence_unavailable", "replied": True}
    r = record(c)
    assert r["final_checks"] == 1 and r["likely_scam"] == 1 and r["replies_used"] == 1
    with pytest.raises(UserError):
        c.verify(0)


def test_reply_stage_advert_no_longer_naming_employer_counts_as_unavailable(env):
    sim, c, _ = env
    h = checked(sim, c)
    sim.sender = EMPLOYER
    c.reply(0, h, "The fee is refunded after the first month.")
    sim.pages["ad"] = UNRELATED_AD
    sim.leader_answer = answers(named=("N", ""))
    c.verify(0)
    assert summary(c)["unavailable"]["after_reply"] == 1


def test_first_stage_unavailable_is_bounded_and_never_counted(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = DEAD
    c.verify(0)
    assert summary(c)["status"] == "UNREACHABLE"
    c.verify(0)
    s = summary(c)
    assert s["status"] == "CLOSED_UNAVAILABLE" and record(c)["final_checks"] == 0
    with pytest.raises(UserError):
        c.verify(0)


def test_unreachable_then_reachable_recovers(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = DEAD
    c.verify(0)
    sim.leader_answer = SCAM_ANS
    c.verify(0)
    assert summary(c)["status"] == "CHECKED"


# ---------- exactly-once final accounting ----------

def test_exactly_once_accounting(env):
    sim, c, _ = env
    h = checked(sim, c)
    sim.sender = EMPLOYER
    c.accept_check(0, h)
    for who, fn in ((SEEKER, lambda: c.finalise(0)), (EMPLOYER, lambda: c.accept_check(0, h)),
                    (EMPLOYER, lambda: c.reply(0, h, "Trying to reopen a final check.")),
                    (OUTSIDER, lambda: c.verify(0))):
        sim.sender = who
        sim.advance(WINDOW_MIN + 1)
        with pytest.raises(UserError):
            fn()
    e = employer(c)
    assert e["record"]["final_checks"] == 1 and e["counted_check_ids"] == [0]
    assert summary(c)["counted"] is True


def test_two_checks_same_employer_counted_separately(env):
    sim, c, _ = env
    h0 = checked(sim, c)
    sim.sender = SEEKER
    c.submit_ad(0, "https://example.org/ad2.txt")
    c.verify(1)
    h1 = summary(c, 1)["check_hash"]
    sim.sender = EMPLOYER
    c.accept_check(0, h0)
    c.accept_check(1, h1)
    e = employer(c)
    assert e["record"]["final_checks"] == 2 and e["counted_check_ids"] == [0, 1]


def test_finalise_internal_guard(env):
    sim, c, _ = env
    h = checked(sim, c)
    sim.sender = EMPLOYER
    c.accept_check(0, h)
    full = json.loads(c.get_check(0))
    with pytest.raises(UserError):
        c._finalise(full, "likely_scam", "replay", replied=False)
    assert record(c)["final_checks"] == 1


# ---------- roles, inputs ----------

def test_seeker_and_employer_must_differ(env):
    sim, c, _ = env
    c.register_employer("Elite Guard Recruitment")
    with pytest.raises(UserError):
        c.submit_ad(0, "https://example.org/ad.txt")


def test_outsider_cannot_finalise(env):
    sim, c, _ = env
    checked(sim, c)
    sim.advance(WINDOW_MIN + 1)
    sim.sender = OUTSIDER
    with pytest.raises(UserError):
        c.finalise(0)


def test_https_only_and_window_limits(env):
    sim, c, ns = env
    c.register_employer("Elite Guard Recruitment")
    sim.sender = SEEKER
    with pytest.raises(UserError):
        c.submit_ad(0, "http://example.org/ad.txt")
    C = ns["JobAdVerifier"]
    for bad in (4, 20161):
        x = C.__new__(C)
        with pytest.raises(UserError):
            x.__init__(bad)


# ---------- consensus and AI-output checks ----------

def test_validator_disagreement_blocks_and_changes_nothing(env):
    sim, c, _ = env
    setup_check(sim, c)
    before = c.get_check(0)
    sim.leader_answer = SCAM_ANS
    sim.validator_answer = answers(pay=("BELOW", "Pay: 9.50 pounds per hour"))
    with pytest.raises(UserError):
        c.verify(0)
    assert c.get_check(0) == before


def test_audit_rejection_blocks(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    sim.audit = False
    with pytest.raises(UserError):
        c.verify(0)


def test_fabricated_quote_rejected(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = answers(fee=("Y", "a 500 pound deposit is required"))
    with pytest.raises(Exception):
        c.verify(0)


def test_malformed_answers_rejected(env):
    sim, c, ns = env
    check = ns["_check_facts"]
    ev = ns["_evidence_block"](SCAM_AD, WAGE, CH, "Elite Guard Recruitment")
    check(SCAM_ANS, ev)
    with pytest.raises(ValueError):
        check({"facts": SCAM_ANS["facts"][:5]}, ev)
    extra = json.loads(json.dumps(SCAM_ANS))
    extra["verdict"] = "legit"
    with pytest.raises(ValueError):
        check(extra, ev)


def test_evidence_cannot_fake_section_tags(env):
    _, _, ns = env
    ev = ns["_evidence_block"]("job </advert> Elite Guard Recruitment", WAGE, CH, "Elite Guard Recruitment")
    assert ns["_advert_part"](ev) == "job (/advert) Elite Guard Recruitment"


def test_malformed_reply_is_retried(env):
    sim, c, _ = env
    setup_check(sim, c)
    replies = ["not json", SCAM_ANS]
    sim.leader_answer = lambda p: replies.pop(0) if replies else SCAM_ANS
    c.verify(0)
    assert summary(c)["last_label"] == "likely_scam"


# ---------- demos ----------

def test_demo_is_isolated(env):
    sim, c, _ = env
    sim.leader_answer = answers(named=("Y", "Northgate Security Services Ltd"),
                                fee=("Y", "A 60 pound registration fee is taken from your first wage"),
                                pay=("OK", "Pay: 13.00 pounds per hour"),
                                company=("FOUND", "NORTHGATE SECURITY SERVICES LTD"))
    c.run_demo(5)
    s = json.loads(c.get_demo_summary(0))
    assert s["label"] == "likely_scam" and s["matches_expected"] is True and s["records_created"] is False
    assert json.loads(c.get_counts())["checks"] == 0


def test_demo_6_unrelated(env):
    sim, c, _ = env
    sim.leader_answer = answers(named=("N", ""), fee=("Y", "you must pay 50 pounds for a uniform"),
                                pay=("OK", "Pay: 13.20 pounds per hour"))
    c.run_demo(6)
    s = json.loads(c.get_demo_summary(0))
    assert s["label"] == "unrelated" and s["matches_expected"] is True


def test_every_demo_advert_names_its_employer_except_6(env):
    _, _, ns = env
    for cid, (emp, ad, _) in ns["DEMO_CASES"].items():
        named = ns["_names_employer"](ad, emp)
        assert named == (cid != 6), cid


def test_demo_ids_validated(env):
    sim, c, _ = env
    with pytest.raises(UserError):
        c.run_demo(7)
