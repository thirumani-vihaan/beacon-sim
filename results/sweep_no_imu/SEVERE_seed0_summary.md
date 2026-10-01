# BEACON-SIM performance log

Scenario **SEVERE** · seed 0 · config 6f89e088a52f · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 108.1 | >= 20.0 | PASS |
| wall_fps | 32.6 |  |  |
| acquisition_time_s | 0.467 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.367 |  |  |
| mean_tracking_error_px | 14.76 | <= 10.0 | FAIL |
| max_tracking_error_px | 45.17 |  |  |
| mean_tracking_error_urad | 1610.2 |  |  |
| centroid_rmse_px | 0.458 |  |  |
| mean_centroid_error_px | 0.356 |  |  |
| lock_retention_pct | 96.43 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 28 |  |  |
| max_reacquisition_s | 0.1 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.07 |  |  |
| processing_ms_mean | 9.25 |  |  |
| processing_ms_p95 | 16.06 |  |  |

**Overall: SOME SPECS NOT MET**

## Physical feasibility

Slew budget 800.0 px/s · required 360.0 px/s · spare 440.0 px/s · worst-case acquisition 1.36 s
- ✓ every official spec is physically achievable for this scenario
