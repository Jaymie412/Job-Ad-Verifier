# Job Ad Verifier

A GenLayer Intelligent Contract that answers: **does this UK job advert show the warning signs of a scam?**

An employer registers a profile. A jobseeker submits a link to one of that employer's adverts. GenLayer validators each fetch the advert, the official minimum wage page on gov.uk and the Companies House register. They answer a fixed set of fact questions with word-for-word quotes, and must independently reach the same result. Code then decides whether the advert really belongs to that employer, works out the verdict and updates the employer's public record exactly once. The employer always gets a fair window to reply, bound to the exact check by its hash.

Example: an advert that asks for £85 for a "training pack" before the first shift is **likely_scam**, whatever the employer replies, because the policy counts any upfront fee as a red flag.

## Why I built it

When I was looking for security work in the UK, I came across adverts asking for money upfront for training or DBS checks, adverts paying below minimum wage, and "companies" that didn't seem to exist. People new to the UK job market are easy targets. A shared record of each employer's adverts, checked against official sources, helps everyone who comes after.

## What changed in 0.3 (steward review)

| Issue raised | Fix |
|---|---|
| Any submitter could attach an unrelated advert to an employer and finalise it into that employer's record | The advert itself must name the selected employer. The AI must quote the advert's own words, the quote must appear in the advert (not the other pages), and **code** checks that the quote contains the employer's name. If not, the check closes as **UNRELATED** and the employer's record is never touched. |
| The submitter could finalise immediately and block the employer's reply | Every checked advert gets a **reply deadline** (set at deployment, e.g. 48 hours). The jobseeker can only finalise after it has passed. Before then, only the employer can close it, by replying or by accepting the result with the check hash. |
| After a reply, an unavailable advert could leave the check pending forever | **Bounded closure.** If the advert can't be read (or no longer names the employer) at the reply stage twice, the check closes FINAL on the first agreed verdict, with reason `reply_stage_evidence_unavailable`. At the first stage, two failed reads close it as CLOSED_UNAVAILABLE with no record change. |
| Final accounting | A single internal method is the only place a record changes. It refuses a check already counted, using both a flag on the check and the employer's `counted_check_ids` list. |

## What is implemented

- **Two distinct parties.** The jobseeker and the employer must be different addresses.
- **Advert bound to the employer.** Checked by code from a verified quote, as above.
- **Right of reply bound to the exact check.** After the first check the contract fingerprints it (`check_hash`, which includes the reply deadline). The employer can reply once, or accept the result, only by quoting that exact hash.
- **Reply window enforced with the transaction time**, which is the same for every validator.
- **Evidence fetched by validators.** Each validator fetches the advert, `gov.uk/national-minimum-wage-rates` and a Companies House search itself. No wage figure is hard-coded. Fetched pages cannot fake the evidence section markers.
- **Verified quotes.** The employer name, an upfront fee, off-platform-only contact and the advert's pay must be quoted word for word from the advert; a Companies House match from the search page. Made-up quotes are rejected.
- **Independent agreement.** Using `gl.vm.run_nondet_unsafe`, each validator answers every fact itself and must reach the same label as the leader (unreachable, unrelated, or the verdict). It then audits the leader's answers and quotes.
- **Code decides the outcome.** The AI only answers fact questions. Binding, red flags, verdict, status and the employer record are calculated by fixed rules.
- **No state changes until the agreed answers pass every check.** A malformed AI reply is asked again (up to 3 attempts).
- **Six isolated fictional demos**, including a prompt-injection case and an unrelated advert. Demos never create employers, checks or records.

## Lifecycle

| Step | Who | Method | Status after |
|---|---|---|---|
| Deploy | | `reply_window_minutes` (5 to 20160) | |
| Register | Employer | `register_employer(employer_name)` | |
| Submit an advert | Jobseeker | `submit_ad(employer_id, ad_url)` | SUBMITTED |
| Check | Anyone | `verify(check_id)` | CHECKED with a reply deadline, UNRELATED, or UNREACHABLE (verify again; second failure → CLOSED_UNAVAILABLE) |
| Reply once, before the deadline | Employer | `reply(check_id, expected_check_hash, reply_text)` → `verify` | REPLIED → FINAL (two unreadable re-checks → FINAL on the first verdict) |
| Or accept now | Employer | `accept_check(check_id, expected_check_hash)` | FINAL |
| Or after the deadline | Jobseeker or employer | `finalise(check_id)` | FINAL |

Read methods: `get_employer` (record and `counted_check_ids`), `get_check`, `get_check_summary` (shows `check_hash`, `reply_deadline`, `final`), `get_counts`, `get_policy`, `get_demo`, `get_demo_result`, `get_demo_summary`. Demo write: `run_demo(case_id)`.

## Rules

Red flags: **upfront fee**, **off-platform only** (WhatsApp, text or personal email), **pay below the National Living Wage**, **not on Companies House**.

| Verdict | Rule |
|---|---|
| likely_scam | an upfront fee, or two or more red flags |
| suspicious | exactly one red flag |
| insufficient_evidence | no red flags, but gov.uk or Companies House couldn't be read |
| legit | no red flags, and both official checks ran |

An advert that doesn't name the selected employer gets no verdict: it is **unrelated** and never counted. The full definitions are returned by `get_policy`.

## Quick start in Studio

1. Import `contract.py` into GenLayer Studio and deploy with `reply_window_minutes = 30`.
2. Call `run_demo` with `case_id = 1` and wait for it to be accepted.
3. Call `get_demo_summary` with `result_id = 0`. Expected: label `legit`, `matches_expected: true`, `records_created: false`.

See [DEMO_GUIDE.md](DEMO_GUIDE.md) for all six demos and the full two-account walkthrough, including every regression case.

## Demonstrated in Studio

See [DEMO_RESULTS.md](DEMO_RESULTS.md) for the recorded run, deployment address and screenshots.

## Testing

`test_contract.py` contains 32 local tests using a simulated GenLayer runtime and authored AI answers, including regression tests for every review point. See [VERIFICATION.md](VERIFICATION.md).

## Boundaries

- This flags warning signs in an advert's wording. It is not legal advice or proof of fraud.
- It checks what the advert says, not whether the employer behaves that way.
- Binding proves the advert names the employer, not that the employer published it. Someone could host a fake advert using a real company's name; the employer's reply window exists so they can say so on the record.
- The reply window uses the transaction time agreed by the network, accurate to the transaction, not to the second.
- Companies House search results can list similar names; a borderline match may fail to reach consensus and need retrying.
- The demos use fictional wage and Companies House snapshots, clearly labelled. Real checks use the live pages.
- All data is public on-chain. Don't submit adverts containing personal details.
- Instructions hidden in an advert or reply are treated as data. This reduces prompt injection but doesn't guarantee against it.
- Different addresses do not prove different people, and a registered employer name is not verified ownership of that company.

## Built with

- [GenLayer](https://docs.genlayer.com) Intelligent Contracts (Python, GenVM v0.2.16 runner)
- Developed with help from Claude
