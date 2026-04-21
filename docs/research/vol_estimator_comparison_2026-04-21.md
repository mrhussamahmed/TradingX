# Volatility Estimator Comparison

Aggregate trend-sleeve winner: `ewma`

This comparison is trend-sleeve-only per DESIGN-0013 W4. vol-target and mean-reversion candidate defaults are not retuned from this evidence.

## Per-symbol RMSE (annualized vol units)

| Symbol | realized | ewma | garch | har_rv |
| --- | --- | --- | --- | --- |
| EEM | 0.072171 | 0.067760 | 0.065923 | 0.074171 |
| IWM | 0.074995 | 0.069576 | 0.134189 | 0.076388 |
| QQQ | 0.084725 | 0.080819 | 0.080161 | 0.087341 |
| SPY | 0.073262 | 0.069299 | 0.066600 | 0.075702 |
| TLT | 0.040443 | 0.036657 | 0.164816 | 0.040432 |
| XLE | 0.302661 | 0.290294 | 0.217982 | 0.312710 |
| XLF | 0.080697 | 0.073928 | 0.074087 | 0.082025 |
| XLK | 0.299975 | 0.285747 | 0.289947 | 0.309839 |

## Pooled RMSE (annualized vol units)

| Method | pooled_rmse_vol | prediction_count |
| --- | --- | --- |
| realized | 0.163216 | 9696 |
| ewma | 0.155522 | 9848 |
| garch | 0.157104 | 9696 |
| har_rv | 0.167678 | 9136 |
