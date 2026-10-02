# Backfill baseline: separate calibration and final holdout

| Field | Value |
| --- | --- |
| Run date | 2026-10-02 |
| Protocol | `separate_calibration_final_holdout_v1` |
| Source | historical replay (`backfill`) |
| Features | `base` (10 features; extended features were not selected) |
| Universe | the 10 default watchlist coins, 730 requested days per coin |

## Result

The run generated 7,400 labeled rows (740 per coin). All three horizons had 1,480 pooled rows in
the final holdout, covering entry dates from 2026-04-08 through 2026-09-02. Coin observations on the
same date are related, so the row count is not the number of independent market events.

| Horizon | AUC | Brier | Base-rate Brier | ECE | Net Sharpe | Final status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 day | 0.4781 | 0.2634 | 0.2526 | 0.0903 | -0.581 | rejected |
| 7 days | 0.5220 | 0.2564 | 0.2550 | 0.0580 | 0.281 | rejected |
| 30 days | 0.3358 | 0.3140 | 0.3068 | 0.2538 | -0.466 | rejected |

No horizon beat the constant-probability Brier baseline, so none passed the model health gate. The
7-day net Sharpe was positive, but its AUC remained below the 0.55 activation threshold and its
Brier score was still worse than baseline. No model was activated.

## Evaluation design

Purged walk-forward predictions from the earlier period selected between logistic regression and
boosted trees. The selected model was calibrated on a later period, then scored once on the final
chronological holdout. The holdout was not used to choose a model or feature group.

| Horizon | Model train rows | Calibration rows | Final holdout rows | Calibration method |
| --- | ---: | ---: | ---: | --- |
| 1 day | 4,800 | 1,100 | 1,480 | isotonic |
| 7 days | 4,740 | 1,040 | 1,480 | isotonic |
| 30 days | 4,510 | 810 | 1,480 | isotonic |

Label horizons were purged at the train/calibration and calibration/holdout boundaries. The final
holdout started on 2026-04-08; the eligible end date is earlier than the data-fetch date because the
longest outcome horizon needs time to mature.

## Reproduction

Run `ml-backfill-history --coin <coin> --days 730` for each of the 10 default watchlist coins, then:

```bash
uv run cdr ml-train --source backfill --features base --json
```

The database and trained model records are local application state and are not committed. These
backfill results are a historical diagnostic, not evidence of live-trading performance. Any further
feature or threshold selection needs a new untouched final period; date-block uncertainty estimates
would also help quantify the correlated holdout rows.
