# Job Ad Verifier demo results

- Date:
- Contract address:
- Employer account (A):
- Jobseeker account (B):

## Part A: demos

| case_id | result_id | Expected | Actual verdict | Red flags | matches_expected | records_created | Screenshot |
|---:|---:|---|---|---|---|---|---|
| 1 | 0 | legit | | | | | |
| 2 | 1 | likely_scam | | | | | |
| 3 | 2 | suspicious | | | | | |
| 4 | 3 | likely_scam | | | | | |
| 5 | 4 | likely_scam | | | | | |

## Part B: check with right of reply

| Step | Account | Method | Result | Screenshot |
|---|---|---|---|---|
| 1 | A | register_employer | | |
| 2 | B | submit_ad | SUBMITTED | |
| 3 | any | verify | CHECKED | |
| 4-5 | A | reply with check_hash | REPLIED | |
| 6 | any | verify | FINAL | |
| 7 | any | get_employer | | |

## Notes

Record anything that failed or needed retrying, and why.
