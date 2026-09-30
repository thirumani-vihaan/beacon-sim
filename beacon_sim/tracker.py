"""Kalman tracker (constant-velocity, screen coordinates) + lock state machine SEARCH->ACQUIRE->LOCK->COAST->REACQUIRE."""
from __future__ import annotations

import numpy as np
from filterpy.kalman import IMMEstimator, KalmanFilter

SEARCH, ACQUIRE, LOCK, COAST, REACQUIRE = "SEARCH", "ACQUIRE", "LOCK", "COAST", "REACQUIRE"
STATES = [SEARCH, ACQUIRE, LOCK, COAST, REACQUIRE]


class Tracker:
    CONFIRM = 3        # consistent hits to declare LOCK
    MISS_TO_COAST = 2  # consecutive misses before COAST
    COAST_MAX_S = 0.5  # coast on prediction this long, then widen search (REACQUIRE)

    def __init__(self, dt: float, meas_sigma: float = 1.5, accel_sigma: float = 350.0, imm: bool = True,
                 manoeuvre_sigma: float = 2000.0):
        """Constant-velocity Kalman filter; with imm=True an Interacting Multiple Model blends a calm CV model
        (accel_sigma) and a manoeuvring CV model (manoeuvre_sigma) by their measurement likelihoods."""
        self.dt = dt
        self.imm = imm
        if imm:
            self.filters = [self._cv(dt, accel_sigma * 0.5, meas_sigma), self._cv(dt, manoeuvre_sigma, meas_sigma)]
            self.kf = self.filters[0]  # exposes x / P / R of the blended estimate after each step (see _sync)
            self._imm = IMMEstimator(self.filters, np.array([0.8, 0.2]), np.array([[0.95, 0.05], [0.10, 0.90]]))
        else:
            self.kf = self._cv(dt, accel_sigma, meas_sigma)
            self.filters = [self.kf]
        self.state, self.hits, self.misses, self.coast_t = SEARCH, 0, 0, 0.0
        self.initialised = False
        self.pending: np.ndarray | None = None  # far re-acquisition candidate awaiting a second consistent hit

    @staticmethod
    def _cv(dt: float, accel_sigma: float, meas_sigma: float) -> KalmanFilter:
        kf = KalmanFilter(dim_x=4, dim_z=2)
        kf.F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], float)
        kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], float)
        g = np.array([[dt ** 2 / 2], [dt]])
        blk = g @ g.T * accel_sigma ** 2
        kf.Q = np.zeros((4, 4))
        kf.Q[np.ix_([0, 2], [0, 2])] = blk
        kf.Q[np.ix_([1, 3], [1, 3])] = blk
        kf.R = np.eye(2) * meas_sigma ** 2
        return kf

    def set_meas_sigma(self, sigma: float) -> None:
        for f in self.filters:
            f.R = np.eye(2) * sigma ** 2

    @property
    def mode_prob(self) -> float:
        """Probability of the manoeuvring model (0 when IMM is off)."""
        return float(self._imm.mu[1]) if self.imm else 0.0

    # ------------------------------------------------------------------
    @property
    def pos(self) -> np.ndarray:
        x = self._imm.x if self.imm else self.kf.x
        return x[:2, 0].copy()

    @property
    def vel(self) -> np.ndarray:
        x = self._imm.x if self.imm else self.kf.x
        return x[2:, 0].copy()

    @property
    def P(self) -> np.ndarray:
        return self._imm.P if self.imm else self.kf.P

    def _set_state(self, x: np.ndarray, P: np.ndarray | None = None) -> None:
        for f in self.filters:
            f.x = x.copy()
            if P is not None:
                f.P = P.copy()
        if self.imm:
            self._imm.x = x.copy()
            if P is not None:
                self._imm.P = P.copy()

    def near_gate(self) -> float:
        return 3.5 * float(np.sqrt(np.trace(self.P[:2, :2]) / 2 + self.filters[0].R[0, 0])) + 12

    def gate(self) -> float:
        """Innovation gate in pixels; grows while coasting so a fast beacon can be re-captured."""
        base = self.near_gate()
        if self.state in (COAST, REACQUIRE):
            base += 400 * self.coast_t
        return min(base, 450.0)

    def predict(self) -> np.ndarray | None:
        if not self.initialised:
            return None
        if self.imm:
            self._imm.predict()
        else:
            self.kf.predict()
        return self.pos

    def update(self, meas: np.ndarray | None) -> str:
        """meas: detected beacon position in screen coords (or None). Returns the new state."""
        held = False
        if meas is not None and self.state in (COAST, REACQUIRE) and self.initialised:
            # a hit far outside the normal gate may be a noise blob: confirm it with a second consistent hit
            if np.hypot(*(meas - self.pos)) > self.near_gate():
                ok = self.pending is not None and np.hypot(*(meas - self.pending)) < 30 + self.near_gate() * 0.25
                if not ok:
                    self.pending, meas, held = meas.copy(), None, True
                else:
                    x = np.vstack([meas.reshape(2, 1), self.vel.reshape(2, 1) * 0.5])  # jump to the confirmed position
                    self._set_state(x)
                    self.pending = None
        if meas is not None:
            if not self.initialised:
                self._set_state(np.array([[meas[0]], [meas[1]], [0.0], [0.0]]), np.diag([4.0, 4.0, 300.0 ** 2, 300.0 ** 2]))
                if self.imm:
                    self._imm.mu = np.array([0.8, 0.2])
                self.initialised = True
            elif self.imm:
                self._imm.update(meas.reshape(2, 1))
            else:
                self.kf.update(meas.reshape(2, 1))
            self.misses, self.coast_t = 0, 0.0
            self.hits += 1
            if self.state in (SEARCH, ACQUIRE):
                self.state = LOCK if self.hits >= self.CONFIRM else ACQUIRE
            elif self.state in (COAST, REACQUIRE):
                self.state = LOCK
        else:
            if not held:
                self.pending = None
            self.misses += 1
            if self.state == ACQUIRE:
                self.hits = 0
                self.state = SEARCH
                self.initialised = False
            elif self.state == LOCK and self.misses >= self.MISS_TO_COAST:
                self.state = COAST
            if self.state in (COAST, REACQUIRE):
                self.coast_t += self.dt
                if self.coast_t > self.COAST_MAX_S:
                    self.state = REACQUIRE
                    x = np.vstack([self.pos.reshape(2, 1), self.vel.reshape(2, 1) * 0.9])  # velocity confidence decays
                    self._set_state(x)
        return self.state

    def reset(self) -> None:
        self.state, self.hits, self.misses, self.coast_t, self.initialised = SEARCH, 0, 0, 0.0, False
