# Stripe Projects plan changes

If this project is managed by Stripe Projects. **Ask the user before
running any paid or destructive plan change**; upgrades bill a real
card, downgrades remove seats.

First run `stripe projects status --json` to confirm the Vercel
resource's local name. The examples below assume the default
(`vercel-plan`); substitute the actual name if it was renamed at
`stripe projects add` time.

- **Upgrade to Pro:** `stripe projects add vercel/pro`
  (or `stripe projects upgrade vercel-plan pro`)
- **Downgrade to Hobby:** `stripe projects downgrade vercel-plan hobby`

## What Pro gives you

- $20/month platform fee, includes $20/month of usage credit.
- Turbo build machines (30 vCPUs, 60 GB memory) by default for new
  projects: significantly faster builds than Hobby.
- 1 deploying seat + unlimited free Viewer seats (read-only
  collaborators, preview comments).
- Higher included allocations (1 TB Fast Data Transfer, 10M Edge
  Requests per month).
- Paid add-ons available: SAML SSO, HIPAA BAA, Flags Explorer,
  Observability Plus, Speed Insights, Web Analytics Plus.

Full details: https://vercel.com/docs/plans/pro-plan
