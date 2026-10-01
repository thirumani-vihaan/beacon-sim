# BEACON-SIM performance log

Scenario **RAIN-LOWLIGHT** · seed 1 · config 41186f6db8ec · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 61.4 | >= 20.0 | PASS |
| wall_fps | 24.1 |  |  |
| acquisition_time_s | 0.433 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.067 |  |  |
| mean_tracking_error_px | 2.58 | <= 10.0 | PASS |
| max_tracking_error_px | 51.31 |  |  |
| mean_tracking_error_urad | 281.9 |  |  |
| centroid_rmse_px | 0.1 |  |  |
| mean_centroid_error_px | 0.085 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 16.29 |  |  |
| processing_ms_p95 | 40.78 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 120.0 px/s · spare 680.0 px/s · worst-case acquisition 0.88 s
- ✓ every official spec is physically achievable for this scenario
