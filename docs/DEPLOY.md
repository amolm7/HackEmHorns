# Deploying the demo (Render + GitHub Actions)

A single container on Render, rebuilt from `main` by GitHub Actions after the tests pass.

```
push to main ─▶ Actions: tests (unit, contract, frontend, smoke, container) ─▶ Render deploy hook (this commit)
                 ─▶ wait until /api/health reports this commit ─▶ live smoke: sign up, hire, run
Internet ─HTTPS─▶ Render ─▶ one container: uvicorn server:app (API + static frontend) ─▶ SQLite file
                                              ├─▶ Meta / Gemini model APIs
                                              └─▶ GitHub MCP, shared read-only token, one repository
```

## How it behaves

- **One shared organisation.** Anyone who signs up joins it as a manager and builder of their own work, so their hires are
  approved on the spot. They see each other's agents and runs. They are never admins: only the admin can prepare GitHub.
- **GitHub is prepared at boot.** If `ADMIN_PASSWORD`, `GITHUB_DEMO_REPO` and the GitHub token are set, the server creates the admin
  account and connects GitHub for the Support and Engineering departments. The "Read GitHub repositories" tool then appears
  in the Library for everyone.
- **A GitHub agent needs a live model.** Testers pick Meta or Gemini when hiring it; the offline demo model cannot read repositories.
- **Free plan: the disk is wiped on restart or after sleeping.** Accounts and agents go with it. The bootstrap rebuilds the admin
  and GitHub connection, so the demo still works; testers just sign up again. To keep data, attach a Render disk at `/app/data`
  (paid) and nothing else changes. Run `python scripts/reset_demo.py` (or restart the service) to clear test data before a demo.
- **Cold start.** The free plan sleeps after about 15 minutes idle; the first request takes up to a minute. Open the site a few
  minutes before you present.

## One-time setup

1. **Render**: create an account, choose New > Blueprint, pick this repository. It reads `render.yaml`. Auto-deploy is off on purpose.
2. **Secrets** (Render dashboard > the service > Environment). None of these belong in the repo or in chat:

   | Name | Value |
   | --- | --- |
   | `ADMIN_PASSWORD` | 12 or more characters; the admin sign-in for the demo (`demo-admin`) |
   | `GITHUB_DEMO_REPO` | `your-username/click`, the fork the token can read |
   | `GITHUB_PERSONAL_ACCESS_TOKEN` | fine-grained, only that repository, Contents and Metadata read-only, short expiry |
   | `MODEL_API_KEY` | the Meta model key |
   | `GEMINI_API_KEY` | optional second model |
   | `SIGNUP_CODE` | optional invite code; leave unset for open sign-up |

   `APP_ORIGIN` is taken from Render's own `RENDER_EXTERNAL_URL`, so there is nothing to type for it.
3. **GitHub**, repository Settings:
   - Move the workflows: `mkdir -p .github/workflows && mv ci-pending/*.yml .github/workflows/` and commit them.
     (`tests.yml` and `deploy.yml` belong together: the deploy workflow calls the test workflow.)
   - Environments > New environment `production`. Add the secret `RENDER_DEPLOY_HOOK_URL` (Render service > Settings > Deploy Hook)
     and the variable `PRODUCTION_URL` (for example `https://orbit-hire-an-agent.onrender.com`).
   - Branches > protect `main`: require a pull request and the status checks from the test workflow.
4. Merge to `main`. The first deploy builds the image (a few minutes). Watch the Actions run; it ends with `LIVE SMOKE PASS`.
5. Check `https://<your-service>.onrender.com/api/health`: it should show `"version"` equal to the commit. The deploy check relies on that.

## Everyday

- Open a pull request: tests, smoke and a container check run. Merge when green. The merge deploys.
- Roll back: Render dashboard > Deploys > pick the previous one > Rollback, or revert the commit on `main`.
- Rotate the GitHub token: create a new one, update the secret on Render, and redeploy. After the demo, let it expire or delete it.
- Check a running site by hand: `python scripts/smoke_live.py https://<your-service>.onrender.com`. It signs up a throwaway
  `ci-smoke-…` account, so run `scripts/reset_demo.py` before a demo if you want a clean list.

## Limits and costs

- One instance only: the data is a SQLite file and agent work runs in that process. Do not scale out.
- Open sign-up spends your model quota and shows a GitHub repo to strangers. Defaults: 10 sign-ups per hour per address, 300 accounts
  in total; set `SIGNUP_CODE` to require an invite code. Put a spend limit on the model keys.
- Render's free plan costs nothing; check its current terms, since they change.
