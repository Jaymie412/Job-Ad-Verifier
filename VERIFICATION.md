# Job Ad Verifier verification

Contract file: `contract.py`, version `job-ad-verifier-0.3`.

## Local checks completed

- Python syntax compilation succeeded.
- `test_contract.py`: **32 tests passed** against a simulated GenLayer runtime.
- The transaction time is read from `gl.message_raw["datetime"]`, which is defined in the `py-genlayer` v0.2.16 SDK (`genlayer/_internal/msg.py`). Every other SDK call is the same as in version 0.2, which ran end to end on GenLayer Studio.

The official `genlayer-test` package couldn't be installed in the environment used, so the tests use a small simulated runtime instead. All AI answers in the tests are authored fixtures. They check the contract's deterministic behaviour, not the AI's judgement.

## Regression tests for the review points

**Unrelated adverts**
1. An advert naming a different company closes as UNRELATED: no check hash, no record change, and it can't be finalised, accepted or verified again.
2. If the AI wrongly says the advert names the employer but quotes a different company, code overrules it: UNRELATED.
3. The employer-name quote must come from the advert itself. A name that only appears on the Companies House page is rejected.
4. Name matching ignores case, punctuation and Ltd/Limited, but a partial name doesn't count.
5. Validators disagreeing on whether the advert names the employer blocks the check and changes nothing.

**Premature closure**
6. The jobseeker's `finalise` is refused before the reply deadline ("The employer can still reply until …"), and nothing is counted.
7. After the deadline, `finalise` closes the check and counts it once (reason `reply_window_expired`).
8. A reply after the deadline is refused.
9. Only the employer can close early, with `accept_check` and the exact hash (reason `employer_accepted`).

**Valid hash-bound reply**
10. The employer replies with the exact hash (case ignored) before the deadline; the reply is passed to the validators as data; re-check → FINAL (reason `rechecked_after_reply`), counted once with `replies_used` 1.
11. The jobseeker can't reply, a wrong hash is refused, and a second reply is refused.
12. The check hash covers the reply deadline.

**Unavailable reply-stage evidence**
13. After a reply, the first unreadable re-check keeps the check REPLIED (`unavailable.after_reply` 1) with nothing counted. The second closes it FINAL on the first agreed verdict (reason `reply_stage_evidence_unavailable`), counted once. No further verify is possible.
14. An advert that no longer names the employer at the reply stage counts as unavailable.
15. At the first stage, two unreadable checks close it as CLOSED_UNAVAILABLE, never counted. A successful read after one failure recovers.

**Exactly-once final accounting**
16. After FINAL, `finalise`, `accept_check`, `reply` and `verify` are all refused; the record shows `final_checks` 1 and `counted_check_ids` [0].
17. Two different checks on the same employer are each counted once: [0, 1].
18. Calling the internal finalising method again on a final check is refused.

**Other checks kept from 0.2**
19. Jobseeker and employer must differ; https links only; outsiders can't finalise; reply window must be 5 to 20160 minutes.
20. A validator reaching a different verdict, or a failed audit, blocks the check and leaves it unchanged.
21. Fabricated quotes, missing or extra facts and extra fields are rejected; a malformed AI reply is asked again.
22. Fetched pages can't fake the evidence section markers.
23. Demos are isolated; demo 6 (unrelated advert) is labelled `unrelated`; every other demo advert names its employer.

## Live Studio evidence

See [DEMO_RESULTS.md](DEMO_RESULTS.md) for the deployment of version 0.3 and screenshots of each regression case.
