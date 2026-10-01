# BEACON-SIM performance log

Scenario **FOG-JITTER** · seed 1 · config 5f4a32ec6a99 · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 158.6 | >= 20.0 | PASS |
| wall_fps | 57.4 |  |  |
| acquisition_time_s | 0.533 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.067 |  |  |
| mean_tracking_error_px | 1.69 | <= 10.0 | PASS |
| max_tracking_error_px | 36.96 |  |  |
| mean_tracking_error_urad | 183.9 |  |  |
| centroid_rmse_px | 0.141 |  |  |
| mean_centroid_error_px | 0.125 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 6.31 |  |  |
| processing_ms_p95 | 13.09 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 240.0 px/s · spare 560.0 px/s · worst-case acquisition 1.07 s
- ✓ every official spec is physically achievable for this scenario
