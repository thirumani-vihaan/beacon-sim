# BEACON-SIM performance log

Scenario **FOG-JITTER** · seed 0 · config f26aa8571df1 · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 132.6 | >= 20.0 | PASS |
| wall_fps | 48.8 |  |  |
| acquisition_time_s | 0.467 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.067 |  |  |
| mean_tracking_error_px | 6.47 | <= 10.0 | PASS |
| max_tracking_error_px | 88.61 |  |  |
| mean_tracking_error_urad | 705.8 |  |  |
| centroid_rmse_px | 0.146 |  |  |
| mean_centroid_error_px | 0.128 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 7.54 |  |  |
| processing_ms_p95 | 11.5 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 240.0 px/s · spare 560.0 px/s · worst-case acquisition 1.07 s
- ✓ every official spec is physically achievable for this scenario
