# Knowledge layer (admissions)

Retrieved **2026-09-29**. Every fact carries its source URL. `trust: official` means it was read from the institution's or regulator's own site or document; `trust: secondary` means a third-party site, shown to students as "verify".

| File | Contents |
|---|---|
| `institutions.yaml` | UAJK, MUST, JAC (website **not working**, with working channels), PMC, MBBSMC, AJKMC (unreachable), SZABMU, PM&DC, UET: portals and admission contacts |
| `admissions.yaml` | **tests** (MDCAT max 180, MBBS 99, BDS 90, relaxation, fee, dates, merit formula; ECAT max 400, PEC 132, Fall 2026 averages; SEET 33%; UAJK test 50%; LAT 50%); **application_process** for uajk / must / jac (steps, documents, age limits, reserved seats, scholarships, fee and refund rules); **programs** (groups, minimum HSSC %, `test_rules` as any-one-of, fees, seats) |
| `deadlines.yaml` | MDCAT 2026 schedule, MUST Fall 2026 deadline and merit lists, UAJK Fall 2026 last date (5 Oct 2026), PM&DC 2025-26 last admission date, and admission rules |

## Sources

| Body | Official sources used |
|---|---|
| PM&DC | MDCAT-2026 public notices (registration, fee, 180 MCQs, test centres), press release (test moved to 20 Sep 2026), notification of 8 Apr 2026 (52% / 47% vacant-seat relaxation, 15 Apr 2026 last date), Admissions Regulations 2025 (eligibility, 60% HSSC, merit formula 50/40/10) - `documents/pmdc/` |
| SZABMU | MBBS admission page (eligibility, documents, AJK-quota seats at FMC Islamabad and SKBZ Lahore) - `raw/szabmu/` |
| UET | ECAT total 400 and Fall 2026 group averages (aggregates only; the source file lists candidate names and was not stored) |
| UAJK | admission procedure, eligibility, required documents, reserved seats, programs, fee structure (scanned sheets transcribed for 2025-29), scholarships, contacts; prospectus text |
| MUST | admissions, Fall 2026 eligibility, merit-list schedule, semester rules (admission and age-limit sections), prospectus 2024-25 fees, refund form, undertaking and medical forms |
| PMC / MBBSMC | admission pages (documents, process, contacts) |
| Secondary | gotest.com.pk - the last JAC cycle's application fee and dates (JAC site blocked) |

## Updating

See `docs/MANUAL.md` section 9. Quote YAML values that contain commas. `tests/test_advisor.py::test_yaml_values_not_split_by_commas` guards this.
