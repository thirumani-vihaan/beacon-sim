# BEACON-SIM performance log

Scenario **NOISY** · seed 1 · config 4eb274fdc2f7 · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 158.8 | >= 20.0 | PASS |
| wall_fps | 44.2 |  |  |
| acquisition_time_s | 0.067 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.067 |  |  |
| mean_tracking_error_px | 0.6 | <= 10.0 | PASS |
| max_tracking_error_px | 23.97 |  |  |
| mean_tracking_error_urad | 65.8 |  |  |
| centroid_rmse_px | 0.166 |  |  |
| mean_centroid_error_px | 0.146 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 6.3 |  |  |
| processing_ms_p95 | 11.93 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 120.0 px/s · spare 680.0 px/s · worst-case acquisition 0.88 s
- ✓ every official spec is physically achievable for this scenario
