"""
SAHF - Telemetry Module
========================
Real-time noise monitoring and telemetry collection for FHE operations.
Implements the feedback loop: stores predictions vs actuals for continuous learning.

Key Features:
- Real-time noise level tracking
- Prediction vs actual storage for feedback loop
- Rolling statistics computation
- Alert generation when noise exceeds thresholds
"""

import sys
import numpy as np
import pandas as pd
from collections import deque
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from .utils import logger, get_timestamp


# ─── Data Classes ──────────────────────────────────────────────
@dataclass
class TelemetrySnapshot:
    """Single telemetry measurement at a point in time."""
    timestamp: str
    step: int
    noise_actual: float
    noise_predicted: Optional[float] = None
    op_type: str = "unknown"
    depth: int = 0
    scale: float = 0.0
    action_taken: str = "CONTINUE"
    bootstrap_count: int = 0
    prediction_error: float = 0.0


@dataclass
class FeedbackRecord:
    """Record for the feedback loop — prediction vs reality."""
    step: int
    predicted_noise: float
    actual_noise: float
    absolute_error: float
    action_taken: str
    was_optimal: bool


# ─── Telemetry Engine ──────────────────────────────────────────
class TelemetryEngine:
    """
    Collects, stores, and analyzes FHE runtime telemetry.
    Powers the feedback loop for continuous model improvement.
    """
    
    def __init__(self, history_size: int = 10000, 
                 feedback_window: int = 100):
        """
        Args:
            history_size: Max telemetry records to retain
            feedback_window: Number of recent predictions for feedback analysis
        """
        self.history: deque = deque(maxlen=history_size)
        self.feedback_log: List[FeedbackRecord] = []
        self.feedback_window = feedback_window
        
        # Rolling statistics
        self.noise_history: deque = deque(maxlen=500)
        self.error_history: deque = deque(maxlen=500)
        
        # Counters
        self.total_bootstraps = 0
        self.total_steps = 0
        self.total_predictions = 0
        
        # Alerts
        self.alerts: List[Dict] = []
        
        logger.info("[TELEMETRY] Telemetry Engine initialized")
    
    def record(self, snapshot: TelemetrySnapshot):
        """
        Record a new telemetry snapshot.
        
        Args:
            snapshot: TelemetrySnapshot to store
        """
        self.history.append(snapshot)
        self.noise_history.append(snapshot.noise_actual)
        self.total_steps += 1
        
        if snapshot.action_taken in ["FULL_BOOTSTRAP", "PARTIAL_REFRESH"]:
            self.total_bootstraps += 1
        
        # Check for alerts
        if snapshot.noise_actual > 0.9:
            self._raise_alert("CRITICAL",
                f"Noise level critical: {snapshot.noise_actual:.4f} at step {snapshot.step}")
        elif snapshot.noise_actual > 0.7:
            self._raise_alert("WARNING",
                f"Noise level elevated: {snapshot.noise_actual:.4f} at step {snapshot.step}")
    
    def record_prediction(self, step: int, predicted: float, actual: float, 
                          action: str):
        """
        Record a prediction-vs-actual pair for the feedback loop.
        
        Args:
            step: Current step number
            predicted: Model's noise prediction
            actual: True noise value observed
            action: Decision engine action that was taken
        """
        error = abs(predicted - actual)
        self.error_history.append(error)
        self.total_predictions += 1
        
        # Determine if the action was optimal
        was_optimal = self._evaluate_action_optimality(predicted, actual, action)
        
        feedback = FeedbackRecord(
            step=step,
            predicted_noise=predicted,
            actual_noise=actual,
            absolute_error=error,
            action_taken=action,
            was_optimal=was_optimal
        )
        self.feedback_log.append(feedback)
    
    def _evaluate_action_optimality(self, predicted: float, actual: float, 
                                     action: str) -> bool:
        """Evaluate if the action taken was optimal given the actual noise."""
        # Determine what action SHOULD have been taken
        if actual > 0.85:
            optimal_action = "FULL_BOOTSTRAP"
        elif actual > 0.5:
            optimal_action = "PARTIAL_REFRESH"
        else:
            optimal_action = "CONTINUE"
        
        return action == optimal_action
    
    def get_feedback_summary(self) -> Dict:
        """
        Get summary statistics of the feedback loop.
        
        Returns:
            Dictionary with prediction accuracy, error rates, optimality
        """
        if not self.feedback_log:
            return {"status": "No predictions recorded yet"}
        
        recent = self.feedback_log[-self.feedback_window:]
        
        errors = [r.absolute_error for r in recent]
        optimality = [r.was_optimal for r in recent]
        
        return {
            "total_predictions": self.total_predictions,
            "recent_window_size": len(recent),
            "mean_absolute_error": float(np.mean(errors)),
            "median_absolute_error": float(np.median(errors)),
            "max_error": float(np.max(errors)),
            "min_error": float(np.min(errors)),
            "std_error": float(np.std(errors)),
            "optimality_rate": float(np.mean(optimality)),
            "optimal_actions": sum(optimality),
            "suboptimal_actions": len(optimality) - sum(optimality)
        }
    
    def get_retrain_data(self) -> Optional[pd.DataFrame]:
        """
        Extract prediction-vs-actual data for model retraining.
        Returns data when enough feedback has been collected.
        
        Returns:
            DataFrame with feedback records, or None if insufficient data
        """
        if len(self.feedback_log) < self.feedback_window:
            logger.info(f"[WAIT] Need {self.feedback_window - len(self.feedback_log)} "
                       f"more records before retraining")
            return None
        
        recent = self.feedback_log[-self.feedback_window:]
        df = pd.DataFrame([{
            "step": r.step,
            "predicted": r.predicted_noise,
            "actual": r.actual_noise,
            "error": r.absolute_error,
            "action": r.action_taken,
            "was_optimal": r.was_optimal
        } for r in recent])
        
        logger.info(f"[RETRAIN] Retrain data extracted: {len(df)} records, "
                    f"MAE={df['error'].mean():.4f}")
        return df
    
    def should_retrain(self, error_threshold: float = 0.08) -> bool:
        """
        Determine if model should be retrained based on recent error trends.
        
        Args:
            error_threshold: MAE threshold above which retraining is needed
        
        Returns:
            True if retraining is recommended
        """
        if len(self.error_history) < 50:
            return False
        
        recent_mae = np.mean(list(self.error_history)[-50:])
        return recent_mae > error_threshold
    
    def get_rolling_stats(self, window: int = 50) -> Dict:
        """
        Compute rolling statistics over recent telemetry.
        
        Args:
            window: Rolling window size
        
        Returns:
            Dictionary of rolling statistics
        """
        noise_vals = list(self.noise_history)
        if len(noise_vals) < window:
            window = max(len(noise_vals), 1)
        
        recent = noise_vals[-window:]
        
        return {
            "rolling_mean_noise": float(np.mean(recent)),
            "rolling_std_noise": float(np.std(recent)),
            "rolling_max_noise": float(np.max(recent)),
            "rolling_min_noise": float(np.min(recent)),
            "trend": float(np.polyfit(range(len(recent)), recent, 1)[0]) if len(recent) > 1 else 0.0,
            "window_size": window
        }
    
    def get_summary(self) -> Dict:
        """Get overall telemetry summary."""
        return {
            "total_steps": self.total_steps,
            "total_bootstraps": self.total_bootstraps,
            "total_predictions": self.total_predictions,
            "bootstrap_rate": self.total_bootstraps / max(self.total_steps, 1),
            "current_noise": float(self.noise_history[-1]) if self.noise_history else 0.0,
            "alerts_count": len(self.alerts),
            "feedback": self.get_feedback_summary(),
            "rolling": self.get_rolling_stats()
        }
    
    def _raise_alert(self, level: str, message: str):
        """Raise a telemetry alert."""
        alert = {
            "timestamp": get_timestamp(),
            "level": level,
            "message": message,
            "step": self.total_steps
        }
        self.alerts.append(alert)
        if level == "CRITICAL":
            logger.warning(f"[ALERT] {message}")
    
    def export_history(self) -> pd.DataFrame:
        """Export full telemetry history as DataFrame."""
        if not self.history:
            return pd.DataFrame()
        
        return pd.DataFrame([{
            "timestamp": s.timestamp,
            "step": s.step,
            "noise_actual": s.noise_actual,
            "noise_predicted": s.noise_predicted,
            "op_type": s.op_type,
            "depth": s.depth,
            "action_taken": s.action_taken,
            "prediction_error": s.prediction_error
        } for s in self.history])


# ─── Main Entry Point ─────────────────────────────────────────
if __name__ == "__main__":
    # Demo telemetry engine
    engine = TelemetryEngine()
    
    for i in range(200):
        noise = 0.01 + i * 0.004 + np.random.normal(0, 0.005)
        predicted = noise + np.random.normal(0, 0.02)
        
        snapshot = TelemetrySnapshot(
            timestamp=get_timestamp(),
            step=i,
            noise_actual=noise,
            noise_predicted=predicted,
            op_type="multiply" if i % 3 == 0 else "add",
            depth=i // 10,
            action_taken="CONTINUE" if noise < 0.5 else "PARTIAL_REFRESH"
        )
        engine.record(snapshot)
        engine.record_prediction(i, predicted, noise, snapshot.action_taken)
    
    print("\n📋 Telemetry Summary:")
    summary = engine.get_summary()
    for k, v in summary.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: {vv}")
        else:
            print(f"  {k}: {v}")
    
    print(f"\n🔄 Should retrain: {engine.should_retrain()}")
