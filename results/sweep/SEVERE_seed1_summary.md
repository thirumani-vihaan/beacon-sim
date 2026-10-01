# BEACON-SIM performance log

Scenario **SEVERE** · seed 1 · config 095af11dc66d · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 172.7 | >= 20.0 | PASS |
| wall_fps | 48.5 |  |  |
| acquisition_time_s | 0.567 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.1 |  |  |
| mean_tracking_error_px | 5.54 | <= 10.0 | PASS |
| max_tracking_error_px | 66.06 |  |  |
| mean_tracking_error_urad | 604.3 |  |  |
| centroid_rmse_px | 0.471 |  |  |
| mean_centroid_error_px | 0.377 |  |  |
| lock_retention_pct | 95.61 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 30 |  |  |
| max_reacquisition_s | 0.167 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.075 |  |  |
| processing_ms_mean | 5.79 |  |  |
| processing_ms_p95 | 13.51 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 360.0 px/s · spare 440.0 px/s · worst-case acquisition 1.36 s
- ✓ every official spec is physically achievable for this scenario
