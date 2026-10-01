# BEACON-SIM performance log

Scenario **NOISY** · seed 2 · config a1b680b5cd08 · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 133.7 | >= 20.0 | PASS |
| wall_fps | 40.4 |  |  |
| acquisition_time_s | 0.467 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.1 |  |  |
| mean_tracking_error_px | 1.38 | <= 10.0 | PASS |
| max_tracking_error_px | 41.98 |  |  |
| mean_tracking_error_urad | 150.0 |  |  |
| centroid_rmse_px | 0.156 |  |  |
| mean_centroid_error_px | 0.135 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 7.48 |  |  |
| processing_ms_p95 | 19.67 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 120.0 px/s · spare 680.0 px/s · worst-case acquisition 0.88 s
- ✓ every official spec is physically achievable for this scenario
