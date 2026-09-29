# Knowledge layer

The curated, machine-readable policy layer JK Assistance reasons over. It was retrieved on **2026-09-29**.

| File | Contents |
|---|---|
| `institutions.yaml` | UAJK, MUST, UHS, PMC, MBBSMC, AJKMC, JAC: portals, offices, phone numbers, emails, fee-payment method |
| `services.yaml` | 27 procedures (degree, duplicate degree, verification, correction/name change, DMC/transcript, migration, transfer, clearance, provisional certificate, bonafide, English proficiency, re-checking, refund, convocation, hostel, exam services, UHS degree/transcript/migration). Each has documents, steps, forms, versioned fees, deadlines and sources. |
| `admissions.yaml` | 38 program entries for students after 12 years of education (eligibility by group and minimum %, tests, first-semester fees), entry tests (UAJK test, SEET, MDCAT, LAT), and the application process, documents, reserved seats, self-support and scholarships per institution |
| `deadlines.yaml` | Dated deadlines (UAJK Fall 2026 last date 5 Oct 2026, MUST Fall 2026 merit lists, JAC 2026 schedule, PMC closure) and relative rules (fee fine windows, re-checking, registration, refund, withdrawal, freezing, migration submission) |
| `progression_rules.yaml` | MUST semester regulations (grading, promotion, probation, relegation, degree requirements, maximum durations); UAJK and UHS marked unpublished/not ingested |

## Trust and provenance

- `trust: official` means the fact was read from the institution's own website or document. The source URL is stored next to it, and the raw page/document is in `raw/` or `documents/`.
- `trust: secondary` means it came from a third-party site because the official site could not be fetched (JAC is behind Cloudflare). The UI and answers label these "verify".
- Scanned PDFs (MUST degree form, provisional form, UAJK fee sheets, the MUST merit-list notice) were read visually and transcribed by hand. Their original files are in `documents/`.

## Fee versioning

```yaml
- item: Degree before convocation (including form fee)
  versions:
    - {amount: 7500, effective_from: 2024-09-02, source: .../Miscellaneous-Fee-Structure-2024.pdf}
    - {amount: 9080, effective_from: 2026-07-28, source: .../Degree-from-updates.pdf}
```

The engine selects the newest version whose `effective_from` is on or before the question date, and shows the superseded one. When a fee's effective date is unknown, `effective_from` is the publication or fetch date and `date_basis` says so.

## Source coverage

| Institution | Pages fetched | Documents | Notes |
|---|---|---|---|
| UAJK | admission procedure, eligibility, required documents, reserved seats, UG/PG programs, fee structure, exam department, registrar, contacts, scholarships, results, downloads, challan portal (full fee schedule) | 24 forms + 13 fee sheets + Prospectus + UG Education Policy | semester promotion rules not published |
| MUST | admissions, Fall 2026 merit schedule, examination, semester rules & regulations, grading system, downloads, student corner | 20 forms incl. 2026 degree form, misc fee structure 2024, eligibility Fall 2026, prospectus 2024-25 | page 6252 vs 6258 GPA example conflict flagged |
| UHS | fee structure, downloads, degree issuance portal | - | MBBS/BDS degrees, transcripts, verification |
| PMC Rawalakot | home, admission, downloads, contact, about | - | pmc.edu.pk is a different (Faisalabad) institution |
| MBBSMC | admissions and examinations (rendered in a browser) | - | page content looks partly templated - verify fees |
| JAC | - (Cloudflare) | - | secondary source: gotest.com.pk |
| AJKMC | - (site unreachable) | - | - |

## Updating

1. Fetch: `python scripts/fetch_pages.py uajk https://uajk.edu.pk/some-page/` saves `raw/uajk/<slug>.html` and `.txt`, and lists the document links it found.
2. Documents: save them into `documents/<site>/`, then `python scripts/extract_docs.py <site>` writes `documents/<site>/text/*.txt`. A count near 0 means a scanned PDF; transcribe it manually.
3. Edit the YAML. Add fee **versions** rather than overwriting, and quote values containing commas.
4. `python -m pytest -q`. The index rebuilds automatically on the next start.
