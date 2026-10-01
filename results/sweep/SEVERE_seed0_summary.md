# BEACON-SIM performance log

Scenario **SEVERE** · seed 0 · config 4485584a1f41 · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 159.6 | >= 20.0 | PASS |
| wall_fps | 43.8 |  |  |
| acquisition_time_s | 0.133 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.033 |  |  |
| mean_tracking_error_px | 5.02 | <= 10.0 | PASS |
| max_tracking_error_px | 53.82 |  |  |
| mean_tracking_error_urad | 547.3 |  |  |
| centroid_rmse_px | 0.476 |  |  |
| mean_centroid_error_px | 0.364 |  |  |
| lock_retention_pct | 97.04 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 21 |  |  |
| max_reacquisition_s | 0.133 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.075 |  |  |
| processing_ms_mean | 6.27 |  |  |
| processing_ms_p95 | 12.89 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 360.0 px/s · spare 440.0 px/s · worst-case acquisition 1.36 s
- ✓ every official spec is physically achievable for this scenario
