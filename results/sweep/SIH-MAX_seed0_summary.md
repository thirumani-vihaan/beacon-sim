# BEACON-SIM performance log

Scenario **SIH-MAX** · seed 0 · config 4bb979aa9c53 · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 71.9 | >= 20.0 | PASS |
| wall_fps | 22.7 |  |  |
| acquisition_time_s | 0.133 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.067 |  |  |
| mean_tracking_error_px | 4.08 | <= 10.0 | PASS |
| max_tracking_error_px | 30.82 |  |  |
| mean_tracking_error_urad | 445.4 |  |  |
| centroid_rmse_px | 0.165 |  |  |
| mean_centroid_error_px | 0.145 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 13.91 |  |  |
| processing_ms_p95 | 28.68 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 1600.0 px/s · required 720.0 px/s · spare 880.0 px/s · worst-case acquisition 0.68 s
- ✓ every official spec is physically achievable for this scenario
