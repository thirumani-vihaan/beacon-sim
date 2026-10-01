# BEACON-SIM performance log

Scenario **SEVERE** · seed 2 · config f3fab0d939fe · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 166.3 | >= 20.0 | PASS |
| wall_fps | 45.9 |  |  |
| acquisition_time_s | 0.3 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.167 |  |  |
| mean_tracking_error_px | 5.55 | <= 10.0 | PASS |
| max_tracking_error_px | 110.32 |  |  |
| mean_tracking_error_urad | 605.7 |  |  |
| centroid_rmse_px | 0.444 |  |  |
| mean_centroid_error_px | 0.352 |  |  |
| lock_retention_pct | 96.33 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 27 |  |  |
| max_reacquisition_s | 0.1 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.073 |  |  |
| processing_ms_mean | 6.01 |  |  |
| processing_ms_p95 | 12.68 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 360.0 px/s · spare 440.0 px/s · worst-case acquisition 1.36 s
- ✓ every official spec is physically achievable for this scenario
