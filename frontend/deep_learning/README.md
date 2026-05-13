# Jeonse Risk Deep Learning Guide

This module preprocesses jeonse transaction data and produces two model outputs.

- TabNet: classifies whether a transaction looks like a price/risk anomaly.
- LSTM: forecasts monthly jeonse price-per-pyeong by region, housing type, and area bucket.

## Run

From the project root:

```powershell
python .\frontend\deep_learning\run_analysis.py --source db
```

Preprocess only:

```powershell
python .\frontend\deep_learning\preprocess.py --source db
```

## Outputs

| File | Meaning |
|---|---|
| `processed/load_summary.json` | Source and processed row counts |
| `processed/jeonse_monthly.csv` | Monthly jeonse price-per-pyeong statistics |
| `processed/sale_monthly.csv` | Monthly sale price-per-pyeong statistics |
| `processed/jeonse_building_monthly.csv` | Building-level monthly jeonse statistics |
| `processed/jeonse_labeled.csv` | Labeled dataset for TabNet |
| `models/tabnet_metadata.json` | TabNet metrics and feature importances |
| `models/lstm_metadata.json` | LSTM metrics and naive-baseline comparison |
| `analysis_summary.json` | Combined analysis summary |

## Preprocessing Notes

`jeonse_labeled.csv` now reduces label leakage and adds reliability fields.

- Price anomaly uses leave-one-out region statistics, so the current transaction is excluded from its own z-score reference.
- Groups with fewer than 3 trades are marked `region_reliability=low_sample` and are not used for price-anomaly labeling.
- If same-month sale price is missing, the latest prior sale price for the same sido/sigungu/housing_type/area_bucket is used and marked `sale_price_source=prior_month`.

`is_anomaly` is a pricing/risk signal, not proof of fraud.

## TabNet Metrics

The TabNet feature list excludes direct label-rule fields: `z_score`, `jeonse_ratio`, `q25`, and `q75`.

Check these fields in `tabnet_metadata.json`:

| Field | Meaning |
|---|---|
| `split_strategy` | Prefer latest-month holdout; falls back to stratified random split if needed |
| `features` | Actual model inputs |
| `excluded_leaked_features` | Fields removed to avoid direct label leakage |
| `auc` | Ranking/separation performance |
| `classification_report` | precision, recall, f1-score |
| `confusion_matrix` | True/predicted class counts |
| `feature_importances` | TabNet feature importance values |

## LSTM Metrics

The LSTM scaler is fit only on the training window. Early stopping now uses validation loss, not training loss. Each group is also compared with a naive baseline that predicts the previous month value.

Check these fields in `lstm_metadata.json`:

| Field | Meaning |
|---|---|
| `mae`, `rmse` | LSTM forecast error |
| `naive_mae`, `naive_rmse` | Previous-month baseline error |
| `beats_naive` | Whether LSTM RMSE is better than the baseline |
| `best_valid_loss` | Best validation loss used for model selection |
| `last_train_loss` | Last observed training loss |
| `months` | Number of monthly observations in the group |

When `beats_naive=false`, treat the LSTM forecast as weak evidence.
