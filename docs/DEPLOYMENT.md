# Deploying JK Assistance for free (and keeping it updated automatically)

```
 official websites (UAJK, MUST, PM&DC, SZABMU, PMC ...)
            │  daily 08:00 PKT
            ▼
 GitHub Actions: update-sources.yml ── runs scripts/update_agent.py
            │  something changed?
            ▼ yes
 Pull request "Admission sources changed" + report (dates, fees, rules, new PDFs, dead links)
            │  you review, add new dates/fees to knowledge/*.yaml, merge
            ▼
 main branch ──► GitHub Actions: tests.yml (49 tests)
            │
            ▼  auto-deploy on push
 Render (free web service)  ──►  https://ajk-admission-assistant.onrender.com  (students)
```

Everything here is free:

| Service | Used for | Free-tier terms (checked 2026-09-29) |
|---|---|---|
| **GitHub** (private repo) | code, pull requests, **Actions** (update agent + tests) | Private repos get 2,000 Actions minutes/month. One agent run takes about 3-5 minutes, so the daily schedule uses about 150 minutes/month. |
| **Render** (recommended host) | the website and API | Free web service with 750 instance-hours/month. It **sleeps after 15 minutes without traffic**, and the first request after that takes about 1 minute to wake it. There is no persistent disk, which JK Assistance doesn't need because it is read-only. |
| **Hugging Face Spaces** (alternative host) | the website and API | Free CPU Docker Space on port 7860. Disk resets on restart (fine here). It can be public or private. |
| **Anthropic API** (optional, paid) | Claude-written chat answers and Claude-drafted date entries in the agent | Not required. Without a key everything works from the rule engine. |

---

## A. Host on Render (recommended: deploys straight from the private GitHub repo)

1. Sign up at https://render.com with your GitHub account and authorise access to `faisalramzan3725/ajk-admission-assistant`.
2. Click **New → Blueprint** and pick the repo. Render reads `render.yaml`, which defines a free Docker web service named `ajk-admission-assistant`, a health check on `/api/health`, and **auto-deploy on every push to `main`**.
3. Optional: in the service's **Environment** tab, set `ANTHROPIC_API_KEY`.
4. Wait for the first build (about 3-5 minutes). Your URL will look like `https://ajk-admission-assistant.onrender.com`.
5. Check it: `https://<your-url>/api/health` should return `{"ok": true, ...}`, and `/` should show the portal.

From now on, every merge to `main`, including a merged update-agent PR, redeploys automatically.

**Cold starts:** a free service sleeps after 15 idle minutes. The first visitor then waits about a minute. If that's a problem during admission season, a paid instance removes the sleep.

## B. Host on Hugging Face Spaces (alternative)

1. Create a Space at https://huggingface.co/new-space. Choose **SDK: Docker** and **Blank**. Choose Private or Public.
2. Push the app to the Space:

   ```bash
   git clone https://huggingface.co/spaces/<your-hf-user>/ajk-admission-assistant hf-space
   ```

   Copy `Dockerfile`, `requirements-app.txt`, `jk_assistance/`, `knowledge/`, `web/`, `raw/` and `documents/` into `hf-space/`. Then copy `deploy/huggingface/README.md` to `hf-space/README.md`. Its YAML header (`sdk: docker`, `app_port: 7860`) tells Hugging Face how to run the Space. Then run `git add . && git commit -m "deploy" && git push` inside `hf-space/`.
3. Optional: add `ANTHROPIC_API_KEY` under **Settings → Variables and secrets** as a secret.

Hugging Face does not redeploy from GitHub automatically. Re-copy and push after merging updates, or use Render.

## C. Turn on the automatic update agent (GitHub Actions)

The workflow files are already in the repo (`.github/workflows/`). Do this once:

1. Repo **Settings → Actions → General**:
   - Actions permissions: **Allow all actions**.
   - Workflow permissions: **Read and write permissions**.
   - Tick **Allow GitHub Actions to create and approve pull requests**. The agent opens PRs, so this is required.
2. Optional: **Settings → Secrets and variables → Actions → New repository secret** `ANTHROPIC_API_KEY`. This lets the agent draft new date entries with Claude.
3. **Actions** tab → **update-sources** → **Run workflow**, to test it now. Otherwise it runs every day at 03:00 UTC (08:00 PKT).

What you receive:
- **No change**: nothing, apart from the report stored as a downloadable run artifact.
- **Change**: a pull request titled *"Admission sources changed - YYYY-MM-DD"*. Its description is the report: new dates, fees and rule lines, new notices/PDFs, sites that went up or down (for example "jac.portal: now UP"), broken student links, and calendar gaps, plus Claude's draft entries if a key is set.

What you do: open the PR and follow the source links. Add or edit the entries in `knowledge/deadlines.yaml` or `knowledge/admissions.yaml` on the same branch (the GitHub web editor works). Once the **tests** check passes, merge. Render redeploys.

> Why a person approves: dates, fees and minimum marks are official facts. The agent finds and highlights changes; a human confirms them. Every answer students see stays traceable to a verified source.

## D. Run the agent locally

```bash
python scripts/update_agent.py --no-llm
```

To run only some sources:

```bash
python scripts/update_agent.py --only uajk.admission_procedure pmdc.home
```

The report goes to `reports/update_report.md`, with drafts in `reports/proposals.json` and per-source state in `knowledge/source_state.json`.

## E. What was verified

| Check | Result |
|---|---|
| Update agent, full live run (23 sources) | ✅ 20 reachable. The 3 known-down sites were reported (JAC 403, AJKMC, mdcat.pmdc.pk). Calendar gaps were flagged for JAC and PM&DC (the next MBBS cycle isn't announced yet). |
| Change detection (simulated edit of the UAJK page) | ✅ It reported "05 October 2026" and "The last date for admissions has been extended!" as new lines. |
| Refetch determinism | ✅ Re-fetched pages produced byte-identical text, so there are no false alarms. |
| Container contents | ✅ With only the folders the Dockerfile copies, only `requirements-app.txt`, and `$PORT` set: `/api/health`, the portal, an eligibility check (MBBS aggregate 82.472) and a local document all respond. |
| Tests | ✅ 49 pass (admission engine, API, agent detectors and report). |
| Docker image build | ⚠️ Not built here, because Docker isn't installed on this PC. Render and Hugging Face build it on their servers. |
| GitHub Actions / Render / Hugging Face | ⚠️ These run on your accounts. Follow A and C. The first `update-sources` run and the first Render build are the live tests. |
| Claude-drafted proposals | ⚠️ Needs an `ANTHROPIC_API_KEY`, which wasn't available here. The code uses the SDK's validated JSON (`messages.parse`), and any failure is recorded in the report instead of crashing the run. |
