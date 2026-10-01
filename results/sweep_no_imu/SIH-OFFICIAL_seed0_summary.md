# BEACON-SIM performance log

Scenario **SIH-OFFICIAL** · seed 0 · config 108025f5c7fb · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 148.6 | >= 20.0 | PASS |
| wall_fps | 78.0 |  |  |
| acquisition_time_s | 0.333 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.1 |  |  |
| mean_tracking_error_px | 1.69 | <= 10.0 | PASS |
| max_tracking_error_px | 38.7 |  |  |
| mean_tracking_error_urad | 184.6 |  |  |
| centroid_rmse_px | 0.053 |  |  |
| mean_centroid_error_px | 0.046 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 6.73 |  |  |
| processing_ms_p95 | 9.39 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 120.0 px/s · spare 680.0 px/s · worst-case acquisition 0.88 s
- ✓ every official spec is physically achievable for this scenario
