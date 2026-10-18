# Job Ad Verifier verification

Contract file: `contract.py`, version `job-ad-verifier-0.2`.

## Local checks completed

- Python syntax compilation succeeded.
- Every GenLayer SDK call the contract uses (`gl.vm.run_nondet_unsafe`, `gl.vm.Return`, `gl.nondet.exec_prompt`, `gl.nondet.web.render`, `gl.vm.UserError`, `gl.message.sender_address`) is used by my Deposit Dispute Court and Security Incident Log contracts, which ran end to end on GenLayer Studio with the same `py-genlayer` runner.
- `test_contract.py`: **20 tests passed** against a simulated GenLayer runtime.

The official `genlayer-test` package couldn't be installed in the environment used, so the tests use a small simulated runtime instead. All AI answers in the tests are authored fixtures. They check the contract's deterministic behaviour, not the AI's judgement.

## What the tests cover

1. Check → finalise: verdict, red flags, check hash, and the employer record updated only at FINAL.
2. Employer reply: hash-bound, passed to the validators as data, re-check, FINAL, reply counted.
3. Verdict rules: legit, suspicious, likely_scam, insufficient_evidence, unreachable.
4. An unreachable advert can be verified again.
5. Jobseeker and employer must be different addresses; https links only.
6. Only the employer can reply, only with the exact `check_hash`, and only once.
7. Outsiders can't finalise; a checked advert can't be verified twice.
8. A validator reaching a different verdict blocks the check and leaves it unchanged.
9. Validators disagreeing only on a secondary flag that doesn't change the verdict still agree.
10. Validators quoting different words but reaching the same outcome still agree.
11. A failed audit blocks the check.
12. Fabricated quotes, missing quotes, missing or extra facts, extra fields and unknown answers are rejected.
13. A malformed AI reply is asked again instead of failing the transaction.
14. Quote matching tolerates spacing and capital letters only.
15. Demos are isolated: no employers, checks or records are created.

## Live Studio evidence

Recorded in GenLayer Studio on 18 October 2026 at `0x7c8d9c45f5C4C64fE78E71BE32C5bc98675975b3`. Full details and screenshots are in [DEMO_RESULTS.md](DEMO_RESULTS.md).

- All 5 isolated demos matched their expected verdict, including the prompt-injection case, and created no records.
- A real two-account check ran end to end using live evidence: submitted → verified (likely_scam, 4 red flags) → employer replied with the exact check hash → re-verified → FINAL, still likely_scam.
- Employer record updated by code: final_checks 1, likely_scam 1, replies_used 1.
- An earlier deployment's live check was UNDETERMINED because validators had to match every secondary flag; the agreement rule was changed to the verdict and the fixed contract redeployed.
