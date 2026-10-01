# BEACON-SIM performance log

Scenario **SIH-MAX** · seed 0 · config bf9c99008c06 · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 77.3 | >= 20.0 | PASS |
| wall_fps | 23.8 |  |  |
| acquisition_time_s | 0.133 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.067 |  |  |
| mean_tracking_error_px | 27.64 | <= 10.0 | FAIL |
| max_tracking_error_px | 372.21 |  |  |
| mean_tracking_error_urad | 3015.5 |  |  |
| centroid_rmse_px | 0.168 |  |  |
| mean_centroid_error_px | 0.147 |  |  |
| lock_retention_pct | 99.54 |  |  |
| target_loss_pct | 0.11 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.167 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.167 |  |  |
| processing_ms_mean | 12.93 |  |  |
| processing_ms_p95 | 30.7 |  |  |

**Overall: SOME SPECS NOT MET**

## Physical feasibility

Slew budget 1600.0 px/s · required 720.0 px/s · spare 880.0 px/s · worst-case acquisition 0.68 s
- ✓ every official spec is physically achievable for this scenario
