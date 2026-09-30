# BEACON-SIM performance log

Scenario **SEVERE** · seed 0 · config 4d93075b2e96 · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 197.7 | >= 20.0 | PASS |
| wall_fps | 40.4 |  |  |
| acquisition_time_s | 0.167 | <= 2.0 | PASS |
| mean_tracking_error_px | 38.54 | <= 10.0 | FAIL |
| max_tracking_error_px | 145.11 |  |  |
| mean_tracking_error_urad | 4203.6 |  |  |
| centroid_rmse_px | 0.761 |  |  |
| mean_centroid_error_px | 0.521 |  |  |
| lock_retention_pct | 96.24 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 26 |  |  |
| max_reacquisition_s | 0.1 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.074 |  |  |
| processing_ms_mean | 5.06 |  |  |
| processing_ms_p95 | 9.6 |  |  |

**Overall: SOME SPECS NOT MET**
