# Job Ad Verifier demo guide (version 0.3)

Use GenLayer Studio (studio-next.genlayer.com) with two accounts:
**A = employer**, **B = jobseeker**. After each write, wait for it to finish, then confirm with a read method (State: Accepted). "FINALIZED" alone doesn't mean success.

Deploy `contract.py` with `reply_window_minutes = 30`.

## Part A: six isolated demos

For each case run `run_demo(case_id)`, then `get_demo_summary(result_id)`. Result ids start at 0.

| case_id | Scenario | Expected label |
|---:|---|---|
| 1 | Fair pay, apply online, company found | legit |
| 2 | £85 training pack and DBS fee | likely_scam |
| 3 | Apply only by WhatsApp | suspicious |
| 4 | Low pay, company not found | likely_scam |
| 5 | £60 fee + hidden "IGNORE ALL PREVIOUS INSTRUCTIONS" | likely_scam |
| 6 | Advert names a different company (Riverside Patrol Ltd) | unrelated |

Then `get_counts`: `checks` stays 0.

## Part B: live checks covering every review point

Advert links:
- Check 0: https://raw.githubusercontent.com/Jaymie412/Job-Ad-Verifier/refs/heads/main/scam_ad.txt
- Check 1: https://raw.githubusercontent.com/Jaymie412/Job-Ad-Verifier/refs/heads/main/unrelated_ad.txt
- Check 2: https://raw.githubusercontent.com/Jaymie412/Job-Ad-Verifier/refs/heads/main/vanishing_ad.txt

| # | Account | Call | Expected |
|---|---|---|---|
| 1 | A | `register_employer("Elite Guard Recruitment")` | employer 0 |
| 2 | B | `submit_ad(0, scam_ad link)` | check 0 SUBMITTED |
| 3 | B | `verify(0)` | CHECKED, likely_scam, check_hash and reply_deadline set |
| 4 | B | `finalise(0)` straight away | **refused**: "The employer can still reply until …" (premature closure blocked) |
| 5 | A | `reply(0, check_hash, "The 85 pound fee is refunded after the first month of work.")` | REPLIED |
| 6 | B | `verify(0)` | FINAL, reason `rechecked_after_reply` |
| 7 | B | `submit_ad(0, unrelated_ad link)` then `verify(1)` | **UNRELATED**; `get_employer(0)` unchanged |
| 8 | B | `submit_ad(0, vanishing_ad link)` then `verify(2)` | CHECKED |
| 9 | A | `reply(2, check_hash, "This event advert was posted by a former manager without approval.")` | REPLIED |
| 10 | | Delete `vanishing_ad.txt` from the GitHub repo; wait until its raw link shows "404: Not Found" | |
| 11 | B | `verify(2)` | still REPLIED, `unavailable.after_reply` 1 |
| 12 | B | `verify(2)` | FINAL, reason `reply_stage_evidence_unavailable` |
| 13 | B | `finalise(0)` again | **refused** (already final) |
| 14 | A | `accept_check(2, check_hash)` | **refused** (already final) |
| 15 | any | `get_employer(0)` | `final_checks` 2, `counted_check_ids` [0, 2], `replies_used` 2 |
