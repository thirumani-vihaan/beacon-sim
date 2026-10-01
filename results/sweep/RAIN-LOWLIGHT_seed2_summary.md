# BEACON-SIM performance log

Scenario **RAIN-LOWLIGHT** · seed 2 · config 7cac51efcd5c · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 87.3 | >= 20.0 | PASS |
| wall_fps | 35.2 |  |  |
| acquisition_time_s | 0.233 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.067 |  |  |
| mean_tracking_error_px | 2.36 | <= 10.0 | PASS |
| max_tracking_error_px | 28.97 |  |  |
| mean_tracking_error_urad | 257.5 |  |  |
| centroid_rmse_px | 0.103 |  |  |
| mean_centroid_error_px | 0.09 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 11.45 |  |  |
| processing_ms_p95 | 20.82 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 120.0 px/s · spare 680.0 px/s · worst-case acquisition 0.88 s
- ✓ every official spec is physically achievable for this scenario
