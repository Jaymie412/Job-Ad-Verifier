# Job Ad Verifier

A GenLayer Intelligent Contract that answers: **does this UK job advert show the warning signs of a scam?**

An employer registers a profile. A jobseeker submits a link to one of that employer's adverts. GenLayer validators each fetch the advert, the official minimum wage page on gov.uk and the Companies House register, answer a fixed set of fact questions with word-for-word quotes, and must independently reach the same verdict. Code then records the result on the employer's public record. The employer gets one right of reply, bound to the exact check by its hash.

Example: an advert that asks for £85 for a "training pack" before the first shift is **likely_scam**, whatever the employer replies, because the policy counts any upfront fee as a red flag.

## Why I built it

When I was looking for security work in the UK, I came across adverts asking for money upfront for training or DBS checks, adverts paying below minimum wage, and "companies" that didn't seem to exist. People new to the UK job market are easy targets. A shared record of each employer's adverts, checked against official sources, helps everyone who comes after.

## What is implemented

- **Two distinct parties.** The jobseeker and the employer must be different addresses.
- **Right of reply bound to the exact check.** After the first check the contract fingerprints it (`check_hash`). The employer can reply once, and only by quoting that exact hash, so the reply answers the result it actually saw.
- **Evidence fetched by validators.** Each validator fetches the advert, `gov.uk/national-minimum-wage-rates` and a Companies House search itself. No wage figure is hard-coded.
- **Verified quotes.** An upfront fee, off-platform-only contact, the advert's pay and a Companies House match must each be backed by a quote copied word for word from the fetched evidence. The contract checks every quote. Made-up quotes are rejected.
- **Independent agreement.** Using `gl.vm.run_nondet_unsafe`, each validator answers every fact itself and must reach the same verdict as the leader. It then audits the leader's individual answers and quotes. (Matching every secondary flag exactly proved too strict in Studio: live gov.uk and Companies House pages can differ slightly between fetches.)
- **Code decides the outcome.** The AI only answers fact questions. Red flags, verdict, status and the employer record are calculated by fixed rules.
- **No state changes until the check passes every check.** A malformed AI reply is asked again (up to 3 attempts).
- **Employer record** counts only final results: legit, suspicious, likely_scam, insufficient_evidence, and replies used.
- **Five isolated fictional demos**, including a prompt-injection case. Demos never create employers, checks or records.

## Lifecycle

| Step | Who | Method | Status after |
|---|---|---|---|
| Register | Employer | `register_employer(employer_name)` | |
| Submit an advert | Jobseeker | `submit_ad(employer_id, ad_url)` | SUBMITTED |
| Check | Anyone | `verify(check_id)` | CHECKED (or UNREACHABLE, then verify again) |
| Accept | Jobseeker or employer | `finalise(check_id)` | FINAL |
| Or reply once | Employer | `reply(check_id, expected_check_hash, reply_text)` → `verify` | REPLIED → FINAL |

Read methods: `get_employer`, `get_check`, `get_check_summary` (shows `check_hash`), `get_counts`, `get_policy`, `get_demo`, `get_demo_result`, `get_demo_summary`. Demo write: `run_demo(case_id)`.

## Rules

Red flags: **upfront fee**, **off-platform only** (WhatsApp, text or personal email), **pay below the National Living Wage**, **not on Companies House**.

| Verdict | Rule |
|---|---|
| likely_scam | an upfront fee, or two or more red flags |
| suspicious | exactly one red flag |
| insufficient_evidence | no red flags, but gov.uk or Companies House couldn't be read |
| legit | no red flags, and both official checks ran |

The full definitions are returned by `get_policy`.

## Quick start in Studio

1. Import `contract.py` into GenLayer Studio and deploy with no arguments.
2. Call `run_demo` with `case_id = 1` and wait for it to be accepted.
3. Call `get_demo_summary` with `result_id = 0`. Expected: verdict `legit`, `matches_expected: true`, `records_created: false`.

See [DEMO_GUIDE.md](DEMO_GUIDE.md) for all five demos and the full two-account walkthrough.

## Demonstrated in Studio

See [DEMO_RESULTS.md](DEMO_RESULTS.md) for the recorded run, deployment address and screenshots.

## Testing

`test_contract.py` contains 20 local tests using a simulated GenLayer runtime and authored AI answers. They check roles, the lifecycle, the hash-bound reply, quote checking, validator disagreement, audit rejection, malformed AI output and retries, verdict rules and demo isolation. They test the contract's behaviour, not the AI's judgement. See [VERIFICATION.md](VERIFICATION.md).

## Boundaries

- This flags warning signs in an advert's wording. It is not legal advice or proof of fraud.
- It checks what the advert says, not whether the employer behaves that way.
- Companies House search results can list similar names; a borderline match may fail to reach consensus and need retrying.
- The demos use fictional wage and Companies House snapshots, clearly labelled. Real checks use the live pages.
- All data is public on-chain. Don't submit adverts containing personal details.
- Instructions hidden in an advert or reply are treated as data. This reduces prompt injection but doesn't guarantee against it.
- Different addresses do not prove different people, and a registered employer name is not verified ownership of that company.

## Built with

- [GenLayer](https://docs.genlayer.com) Intelligent Contracts (Python, GenVM v0.2.16 runner)
- Developed with help from Claude
