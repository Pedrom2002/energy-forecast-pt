# Project decisions

Notes on the decisions I made along the way — including the ones that forced me to backtrack. Written by me, after hours, more to clear my head than to impress anyone reading.

---

## The synthetic-data foot-gun

Commits: [`013c6c6`](../../../commit/013c6c6), [`86e2163`](../../../commit/86e2163)

v5 ran on synthetic series. Good enough to bootstrap, but it wouldn't survive a real code review, so I moved to real sources: e-Redes national, e-Redes regional by postal code (CP4), and Open-Meteo for weather.

v6 is where I screwed up. Because the national series had more history than the regional one, I used CP4 to compute static shares (hour-of-week × region) and applied them to the national series to reconstruct the regional one. I hit MAPE 1.6% and was happy for a few minutes. Then I sat down and looked at what I had actually built: `regional[t] = national[t] × constant`. Each region was literally a scaled copy of the national one. Any model with lags reconstructs one region from another trivially. Structural leakage in disguise.

In v7 I threw it out and started training directly on CP4 — 40,075 rows, 5 NUTS-II regions, 11 months. I lost 2+ years of history (and the April 2025 blackout, which annoyed me) but I gained numbers that survive cross-examination.

### But v8 sits at 1.44% and v6 was at 1.6%. How do I know this isn't the same problem?

That was the first question I asked myself and the only one worth answering thoroughly.

Short answer: *no_lags* collapses to ~5% in both regimes, so that test discriminates nothing — it's just a truism about autoregressive forecasting. What discriminates is the **structure** of the problem, not the MAPE value.

Four reasons, in order of strength:

**1. Inter-regional variance.** Per-region MAPE in v8 ranges from 1.02% (Alentejo) to 2.31% (Norte). In v6 this was *mathematically impossible* — if the series are `national × k_region`, then `MAPE = |y - ŷ|/|y|` is invariant to `k`, so all regions would have to share the same MAPE. Having 1.02% on one side and 2.31% on the other only happens if regions have their own dynamics. Norte is industrial and volatile, Alentejo is residential and predictable — the model is learning that difference.

This is the one I consider proof. The other three are corroboration.

**2. Importance distribution.** Top feature is `consumption_mw_diff_1` at 8.4%; `lag_1` is 6.5%; top-10 cumulative is 44.8%. When there's a structural shortcut, a single feature usually soaks up >30% of the mass because it's the cheapest path to minimum loss. The distribution I see is incompatible with that.

**3. Target generation.** In v6 the target was deterministic from the national series. In v7/v8 it comes from independent CP4 measurements (real consumption per 4-digit postal code, aggregated to NUTS-II). Five distinct series, not 5 rescalings.

**4. Temporal separation.** Train → val → test with no overlap; lags computed per-region (verified in [src/features/feature_engineering.py](../src/features/feature_engineering.py)). In v6 this separation was cosmetic because the series were algebraically identical.

### Empirical test

The arguments above are solid but they're arguments. To turn them into something reproducible, I wrote [`scripts/verify_no_cross_region_leakage.py`](../scripts/verify_no_cross_region_leakage.py).

The script reproduces the pipeline, confirms the pickle reproduces the metadata MAPE (1.4360% vs 1.4360%, per-region down to the 3rd decimal — validates artefact integrity), then runs the cross-region swap: for each (target, donor) pair, it replaces the 34 lag/rolling/ewma/diff features of the target with the donor's values at the same timestamp, **with scale correction** — each donor lag is multiplied by `mean_target/mean_donor` (means computed on the training set) before injection. Without this correction, part of the degradation would just be scale mismatch (injecting Centro lags ~1300 MW into an Alentejo row ~350 MW) and the test wouldn't distinguish v6 from v8. With the correction, what's left is pure regional-dynamics signal.

Why the correction discriminates:

- In v6 (`regional[t] = national[t] × k_region`), the correction exactly cancels the donor's `k_region` and reintroduces the target's. The corrected donor lag becomes mathematically equal to the target's own lag. Swap would have **zero** effect.
- In v8 (genuine per-region dynamics), even after rescaling, the underlying time-series shapes differ. Degradation persists.

MAPE % matrix after swap (diagonal = baseline):

|          | Alentejo | Algarve | Centro | Lisboa | Norte |
|----------|---------:|--------:|-------:|-------:|------:|
| Alentejo |    1.02  |   11.19 |  14.17 |  11.34 |  17.63|
| Algarve  |   12.99  |    1.31 |  19.21 |  14.82 |  21.29|
| Centro   |   17.59  |   26.17 |   1.09 |   8.30 |   4.89|
| Lisboa   |   11.77  |   18.52 |   6.98 |   1.46 |   8.28|
| Norte    |   22.89  |   29.16 |   5.45 |  10.48 |   2.31|

Overall: 1.44% → 14.7%. **~10× degradation, with scale already neutralised.** In v6 this number would be ~1×. Here there's significant degradation even between regions of comparable scale (Centro↔Lisboa: 7-8% vs ~1% baseline), which can only come from genuinely different dynamics — exactly what you'd expect when the model has learned region-specific patterns.

The lesson: the test that alerted me in v6 (no_lags collapses) was measuring the wrong thing — it's a universal truism about autoregressive series, says nothing about leakage. The test that actually discriminates is the cross-region swap with scale correction. It's in the script and re-runnable any time.

---

## Serving the worse model in the demo

Commit: [`75324f6`](../../../commit/75324f6)

I have two models: `with_lags` (1.44%) and `no_lags` (4.77%). The obvious pick for the demo is the good one. It isn't that simple.

`with_lags` needs the last 48h of real consumption to work. In the demo, the user doesn't have that. Two options remained: either fabricate the lags (and the perceived MAPE jumps to something far worse than 1.44%), or ask the user to enter 48 hourly values (UX garbage). Neither serves.

So the public `/forecast` uses `no_lags`, and I removed the `with_lags` metrics from the main dashboard — I don't want anyone opening the demo expecting 1.44%. The number people see is ~5%, much less marketable than what's in the README, but it's the honest one.

---

## I cut pretty things that weren't defensible

Commits: [`4875cbf`](../../../commit/4875cbf), [`38b5fc4`](../../../commit/38b5fc4)

At one point the dashboard had a live consumption section via ENTSO-E and an interactive drift simulator. Eye-catching. But:

The ENTSO-E API has unpredictable rate limits on the free tier and variable latency. Roughly 1 in 5 visits showed an error or empty data. Bad first contact, and outside my control.

The drift simulator generated synthetic drift from a slider. Pretty in a demo, but if anyone asked "how do you generate this signal?", the honest answer was "scaled random noise". Indefensible in an interview.

I removed both. The monitoring page now only shows what's true: Prometheus latencies, empirical coverage from the `CoverageTracker`, and anomalies from the actual `AnomalyDetector`. The principle that stuck with me: in a public portfolio, don't display what you can't defend.

---

## Everything in one container

Commits: [`7cd9d9b`](../../../commit/7cd9d9b), [`8773c6a`](../../../commit/8773c6a), [`c18ac71`](../../../commit/c18ac71), [`a0bbf5a`](../../../commit/a0bbf5a)

Target: HuggingFace Spaces free tier — 512 MB RAM, 1 container. The "right" architecture would be SPA on a CDN + stateless API across multiple workers. Not an option.

What I ended up doing: SPA served by FastAPI via `StaticFiles(html=True)` mounted after the routers (React Router handles client-side routing); 1 uvicorn worker (any more blows the RAM because each worker loads the models); models baked into the Docker image (no persistent volume on the free tier); relaxed CSP for the Vite assets.

I accept the frontend↔backend coupling and the lack of horizontal scaling because the alternative was no demo at all. The `render.yaml` and Kubernetes/Helm manifests in the repo ([`e579f29`](../../../commit/e579f29)) are for the budgeted scenario — I included them to show I know the right path, not as live config.

---

## CI: I left the scars showing

The first time I turned CI on, everything failed. Seven commits to get it green: [`bb420f0`](../../../commit/bb420f0), [`5f72cb5`](../../../commit/5f72cb5), [`169ae50`](../../../commit/169ae50), [`615d353`](../../../commit/615d353), [`14a93d2`](../../../commit/14a93d2), [`db28421`](../../../commit/db28421).

I could have rebased and presented it all as one clean commit. I didn't. Those 7 commits show I can debug real pipelines, not just copy YAML from Stack Overflow.

---

## Things I deliberately didn't do

- **MLflow / W&B** — overhead for a single-author project. The JSON tracker ([src/models/experiment_tracker.py](../src/models/experiment_tracker.py)) is git-versionable and enough. Migrating to MLflow if the team grew would take half an afternoon.
- **LSTM / Transformers** — 40k tabular points with strong seasonality is GBDT territory. M4 and M5 confirm. Deep learning earns its keep at >1M points or with non-tabular features (satellite imagery, text).
- **Feature store** (Feast etc.) — a well-structured parquet plus deterministic feature engineering is enough. A feature store only makes sense with multiple models sharing features or online serving under tight SLA.
- **A/B testing** — no real traffic. It would be theatre.
