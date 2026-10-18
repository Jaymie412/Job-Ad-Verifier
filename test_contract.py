"""Local logic tests for contract.py using a small simulated GenLayer runtime.

AI answers are authored fixtures, not live AI. These tests check the contract's
deterministic behaviour (roles, lifecycle, hash-bound reply, quote checks,
validator agreement, verdict rules, employer records), not the model's judgement.
Run: python -m pytest test_contract.py -q
"""
import json
import sys
import types
from pathlib import Path

import pytest

EMPLOYER = "0x" + "a" * 40
SEEKER = "0x" + "b" * 40
OUTSIDER = "0x" + "c" * 40

SCAM_AD = ("Security Guards needed. Pay: 9.50 pounds per hour, cash weekly. Before your first shift you must "
           "pay 85 pounds for your training pack, DBS check and uniform. To apply, send a WhatsApp message to "
           "Dave on 07700 900123.")
WAGE = "National Living Wage (21 and over): 12.50 pounds per hour."
CH = "Search results. No results found."
FACTS = ["ad", "fee", "offplatform", "pay", "company"]


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
    defaults = {"ad": ("OK", ""), "fee": ("N", ""), "offplatform": ("N", ""),
                "pay": ("NOT_STATED", ""), "company": ("UNKNOWN", "")}
    defaults.update(kv)
    return {"facts": [{"fact": f, "answer": defaults[f][0], "quote": defaults[f][1]} for f in FACTS]}


SCAM_ANS = answers(fee=("Y", "you must pay 85 pounds for your training pack"),
                   offplatform=("Y", "send a WhatsApp message to Dave"),
                   pay=("BELOW", "Pay: 9.50 pounds per hour"), company=("NOT_FOUND", ""))


class Sim:
    def __init__(self):
        self.sender = EMPLOYER
        self.pages = {"ad": SCAM_AD, "wage": WAGE, "ch": CH}
        self.leader_answer = None
        self.validator_answer = None
        self.audit = True
        self.in_validator = False
        self.prompts = []

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
    c.__init__()
    return sim, c, ns


def setup_check(sim, c):
    sim.sender = EMPLOYER
    c.register_employer("Elite Guard Recruitment")
    sim.sender = SEEKER
    c.submit_ad(0, "https://example.org/ad.txt")


def summary(c, cid=0):
    return json.loads(c.get_check_summary(cid))


def record(c, eid=0):
    return json.loads(c.get_employer(eid))["record"]


# ---------- happy paths ----------

def test_check_then_finalise_updates_employer(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    sim.sender = OUTSIDER
    c.verify(0)
    s = summary(c)
    assert s["status"] == "CHECKED" and s["verdict"] == "likely_scam"
    assert s["red_flags"] == ["upfront_fee", "off_platform_only", "pay_below_minimum_wage", "not_on_companies_house"]
    assert len(s["check_hash"]) == 64
    assert record(c)["final_checks"] == 0  # nothing counted until FINAL
    sim.sender = SEEKER
    c.finalise(0)
    assert summary(c)["status"] == "FINAL"
    r = record(c)
    assert r["final_checks"] == 1 and r["likely_scam"] == 1 and r["replies_used"] == 0


def test_employer_reply_rechecks_once(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    c.verify(0)
    h = summary(c)["check_hash"]
    sim.sender = EMPLOYER
    c.reply(0, h, "The 85 pound fee is refunded after the first month of work.")
    assert summary(c)["status"] == "REPLIED"
    c.verify(0)
    s = summary(c)
    assert s["status"] == "FINAL" and s["verdict"] == "likely_scam" and s["assessments"] == 2
    assert "refunded after the first month" in sim.prompts[-2]
    r = record(c)
    assert r["final_checks"] == 1 and r["replies_used"] == 1


def test_legit_and_insufficient_evidence(env):
    sim, c, ns = env
    out = ns["_outcome"]
    ok = answers(pay=("OK", "x"), company=("FOUND", "y"))
    assert out(ok)["verdict"] == "legit"
    assert out(answers(pay=("OK", "x")))["verdict"] == "insufficient_evidence"
    assert out(answers(offplatform=("Y", "x"), pay=("OK", "x"), company=("FOUND", "y")))["verdict"] == "suspicious"
    assert out(answers(fee=("Y", "x"), pay=("OK", "x"), company=("FOUND", "y")))["verdict"] == "likely_scam"
    assert out(answers(ad=("NOT_AD", "")))["reachable"] is False


def test_unreachable_ad_can_be_verified_again(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = answers(ad=("NOT_AD", ""))
    c.verify(0)
    assert summary(c)["status"] == "UNREACHABLE"
    sim.leader_answer = SCAM_ANS
    c.verify(0)
    assert summary(c)["status"] == "CHECKED"


# ---------- roles and consent ----------

def test_seeker_and_employer_must_differ(env):
    sim, c, _ = env
    c.register_employer("Elite Guard Recruitment")
    with pytest.raises(UserError):
        c.submit_ad(0, "https://example.org/ad.txt")


def test_reply_needs_employer_and_exact_hash(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    c.verify(0)
    h = summary(c)["check_hash"]
    sim.sender = SEEKER
    with pytest.raises(UserError):
        c.reply(0, h, "The jobseeker cannot reply for the employer.")
    sim.sender = EMPLOYER
    with pytest.raises(UserError):
        c.reply(0, "wronghash", "The fee is refunded after the first month.")


def test_only_one_reply_and_no_finalise_after_reply(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    c.verify(0)
    h = summary(c)["check_hash"]
    sim.sender = EMPLOYER
    c.reply(0, h, "The fee is refunded after the first month.")
    with pytest.raises(UserError):
        c.reply(0, h, "A second reply should be rejected.")
    with pytest.raises(UserError):
        c.finalise(0)


def test_outsider_cannot_finalise(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    c.verify(0)
    sim.sender = OUTSIDER
    with pytest.raises(UserError):
        c.finalise(0)


def test_cannot_verify_checked_or_final(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    c.verify(0)
    with pytest.raises(UserError):
        c.verify(0)


def test_https_only(env):
    sim, c, _ = env
    c.register_employer("Elite Guard Recruitment")
    sim.sender = SEEKER
    with pytest.raises(UserError):
        c.submit_ad(0, "http://example.org/ad.txt")


# ---------- consensus and AI-output checks ----------

def test_validator_disagreement_blocks_and_changes_nothing(env):
    sim, c, _ = env
    setup_check(sim, c)
    before = c.get_check(0)
    sim.leader_answer = SCAM_ANS
    sim.validator_answer = answers(pay=("BELOW", "Pay: 9.50 pounds per hour"))  # suspicious, not likely_scam
    with pytest.raises(UserError):
        c.verify(0)
    assert c.get_check(0) == before


def test_same_verdict_different_secondary_flag_agrees(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    sim.validator_answer = answers(fee=("Y", "you must pay 85 pounds"), offplatform=("Y", "WhatsApp"),
                                   pay=("UNKNOWN", ""), company=("UNKNOWN", ""))
    c.verify(0)
    assert summary(c)["verdict"] == "likely_scam"


def test_same_outcome_different_quotes_agrees(env):
    sim, c, _ = env
    setup_check(sim, c)
    sim.leader_answer = SCAM_ANS
    alt = json.loads(json.dumps(SCAM_ANS))
    alt["facts"][1]["quote"] = "pay 85 pounds"
    sim.validator_answer = alt
    c.verify(0)
    assert summary(c)["verdict"] == "likely_scam"


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
    with pytest.raises(ValueError):
        check({"facts": SCAM_ANS["facts"][:4]}, SCAM_AD)
    extra = json.loads(json.dumps(SCAM_ANS))
    extra["verdict"] = "legit"
    with pytest.raises(ValueError):
        check(extra, SCAM_AD)
    bad = json.loads(json.dumps(SCAM_ANS))
    bad["facts"][3]["answer"] = "MAYBE"
    with pytest.raises(ValueError):
        check(bad, SCAM_AD)
    noquote = json.loads(json.dumps(SCAM_ANS))
    noquote["facts"][1]["quote"] = ""
    with pytest.raises(ValueError):
        check(noquote, SCAM_AD)


def test_malformed_reply_is_retried(env):
    sim, c, _ = env
    setup_check(sim, c)
    replies = ["not json", SCAM_ANS]
    sim.leader_answer = lambda p: replies.pop(0) if replies else SCAM_ANS
    c.verify(0)
    assert summary(c)["verdict"] == "likely_scam"


def test_quote_match_ignores_spacing_and_case(env):
    sim, c, ns = env
    out = ns["_check_facts"](answers(fee=("Y", "YOU MUST   pay 85 pounds")), SCAM_AD)
    assert out["facts"][1]["answer"] == "Y"


# ---------- demos ----------

def test_demo_is_isolated(env):
    sim, c, _ = env
    sim.leader_answer = answers(fee=("Y", "A 60 pound registration fee is taken from your first wage"),
                                pay=("OK", "Pay: 13.00 pounds per hour"),
                                company=("FOUND", "NORTHGATE SECURITY SERVICES LTD"))
    c.run_demo(5)
    s = json.loads(c.get_demo_summary(0))
    assert s["verdict"] == "likely_scam" and s["matches_expected"] is True and s["records_created"] is False
    assert json.loads(c.get_counts()) == {"employers": 0, "checks": 0, "demo_results": 1}


def test_demo_ids_validated(env):
    sim, c, _ = env
    with pytest.raises(UserError):
        c.run_demo(0)
