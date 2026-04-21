"""
SAHF - Decision Engine
========================
Adaptive control logic for FHE bootstrapping decisions.
Core novelty: ML-driven vs fixed-interval bootstrap scheduling.

Decision Rules:
    if predicted_noise > 0.85 → FULL_BOOTSTRAP
    elif predicted_noise > 0.50 → PARTIAL_REFRESH
    else → CONTINUE

Implements both:
    System A (Baseline):  Fixed-interval bootstrapping every N steps
    System B (Proposed):  ML-adaptive bootstrapping based on predictions
"""

import numpy as np
import sys
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        # In Jupyter and some environments, reconfigure() is not available
        pass

from .utils import logger, timer, noise_growth_model, get_timestamp
from .fhe_simulation import CKKSContextManager
from .telemetry import TelemetryEngine, TelemetrySnapshot


# ─── Action Constants ──────────────────────────────────────────
ACTION_CONTINUE = "CONTINUE"
ACTION_PARTIAL = "PARTIAL_REFRESH"
ACTION_FULL = "FULL_BOOTSTRAP"


# ─── Decision Engine ──────────────────────────────────────────
class AdaptiveDecisionEngine:
    """
    ML-driven decision engine for adaptive FHE bootstrapping.
    
    Uses LSTM noise predictions to determine when bootstrapping is needed,
    replacing expensive fixed-interval approaches.
    """
    
    def __init__(self, 
                 high_threshold: float = 0.90,
                 medium_threshold: float = 0.75,
                 confidence_weight: float = 0.9):
        """
        Args:
            high_threshold: Noise level for full bootstrap trigger
            medium_threshold: Noise level for partial refresh trigger
            confidence_weight: Weight for prediction confidence in decisions
        """
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.confidence_weight = confidence_weight
        
        # Decision tracking
        self.decision_history: List[Dict] = []
        self.total_decisions = 0
        self.bootstrap_actions = 0
        self.refresh_actions = 0
        self.continue_actions = 0
        
        logger.info(f"[ENGINE] Decision Engine initialized | "
                    f"thresholds=[{medium_threshold}, {high_threshold}]")
    
    def decide(self, predicted_noise: float, 
               current_noise: float = None,
               depth: int = 0,
               step: int = 0) -> str:
        """
        Make a bootstrapping decision based on predicted noise.
        
        Implements the formal decision model:
            O' = O × (1 + w1·Depth + w2·Op_weight + w3·Scale_factor)
        
        Args:
            predicted_noise: LSTM model's noise prediction for next step
            current_noise: Current actual noise level (for validation)
            depth: Current circuit depth
            step: Current step number
        
        Returns:
            Action string: FULL_BOOTSTRAP, PARTIAL_REFRESH, or CONTINUE
        """
        self.total_decisions += 1
        
        # Blend predicted and actual noise for robustness
        if current_noise is not None:
            effective_noise = (self.confidence_weight * predicted_noise + 
                             (1 - self.confidence_weight) * current_noise)
        else:
            effective_noise = predicted_noise
        
        # Decision logic
        if effective_noise > self.high_threshold:
            action = ACTION_FULL
            self.bootstrap_actions += 1
            reason = (f"Noise {effective_noise:.4f} > {self.high_threshold} "
                     f"→ Full bootstrap required")
        elif effective_noise > self.medium_threshold:
            action = ACTION_PARTIAL
            self.refresh_actions += 1
            reason = (f"Noise {effective_noise:.4f} > {self.medium_threshold} "
                     f"→ Partial refresh")
        else:
            action = ACTION_CONTINUE
            self.continue_actions += 1
            reason = f"Noise {effective_noise:.4f} — safe to continue"
        
        # Log decision
        self.decision_history.append({
            "step": step,
            "predicted_noise": float(predicted_noise),
            "current_noise": float(current_noise) if current_noise else None,
            "effective_noise": float(effective_noise),
            "action": action,
            "reason": reason,
            "depth": depth,
            "timestamp": get_timestamp()
        })
        
        return action
    
    def get_stats(self) -> Dict:
        """Get decision engine statistics."""
        total = max(self.total_decisions, 1)
        return {
            "total_decisions": self.total_decisions,
            "full_bootstraps": self.bootstrap_actions,
            "partial_refreshes": self.refresh_actions,
            "continues": self.continue_actions,
            "bootstrap_rate": self.bootstrap_actions / total,
            "refresh_rate": self.refresh_actions / total,
            "continue_rate": self.continue_actions / total,
            "total_bootstrap_events": self.bootstrap_actions + self.refresh_actions
        }


# ─── Baseline System (Fixed Interval) ─────────────────────────
class BaselineSystem:
    """
    System A: Fixed-interval bootstrapping.
    Bootstraps every N operations regardless of noise level.
    """
    
    def __init__(self, bootstrap_interval: int = 8):
        """
        Args:
            bootstrap_interval: Number of steps between forced bootstraps
        """
        self.interval = bootstrap_interval
        self.steps_since_bootstrap = 0
        self.total_bootstraps = 0
        self.total_steps = 0
        self.total_latency = 0.0
        self.noise_history = []
        self.bootstrap_events = []
        
        logger.info(f"[BASELINE] Baseline System initialized | interval={bootstrap_interval}")
    
    def step(self, ctx: CKKSContextManager, op_type: str = None) -> Dict:
        """
        Execute one step of the baseline system.
        
        Args:
            ctx: FHE context manager
            op_type: Operation type ('add' or 'multiply')
        
        Returns:
            Dictionary with step results
        """
        self.total_steps += 1
        self.steps_since_bootstrap += 1
        
        # Record noise before any action
        noise_before = ctx.noise_estimate
        action = ACTION_CONTINUE
        bootstrap_cost = 0.0
        
        # Fixed-interval bootstrap check
        if self.steps_since_bootstrap >= self.interval:
            action = ACTION_FULL
            bootstrap_cost = ctx.bootstrap(mode="full")
            self.total_bootstraps += 1
            self.total_latency += bootstrap_cost
            self.steps_since_bootstrap = 0
            self.bootstrap_events.append(self.total_steps)
        
        self.noise_history.append(ctx.noise_estimate)
        
        return {
            "step": self.total_steps,
            "noise": ctx.noise_estimate,
            "action": action,
            "bootstrap_cost": bootstrap_cost,
            "noise_before": noise_before
        }
    
    def get_results(self) -> Dict:
        """Get baseline system results."""
        return {
            "system": "Baseline (Fixed Interval)",
            "interval": self.interval,
            "total_steps": self.total_steps,
            "total_bootstraps": self.total_bootstraps,
            "total_latency": self.total_latency,
            "avg_noise": float(np.mean(self.noise_history)) if self.noise_history else 0,
            "max_noise": float(np.max(self.noise_history)) if self.noise_history else 0,
            "noise_history": self.noise_history,
            "bootstrap_events": self.bootstrap_events
        }


# ─── Adaptive System (ML-Driven) ──────────────────────────────
class AdaptiveSystem:
    """
    System B: ML-driven adaptive bootstrapping.
    Uses LSTM predictions to decide when to bootstrap.
    """
    
    def __init__(self, predictor=None, 
                 decision_engine: AdaptiveDecisionEngine = None):
        """
        Args:
            predictor: NoisePredictor instance (from model.py)
            decision_engine: AdaptiveDecisionEngine instance
        """
        self.predictor = predictor
        self.engine = decision_engine or AdaptiveDecisionEngine()
        self.telemetry = TelemetryEngine()
        
        self.total_steps = 0
        self.total_bootstraps = 0
        self.total_latency = 0.0
        self.noise_history = []
        self.prediction_history = []
        self.action_history = []
        self.bootstrap_events = []
        
        logger.info("[ADAPTIVE] Adaptive System initialized")
    
    def step(self, ctx: CKKSContextManager, 
             features: np.ndarray = None,
             op_type: str = None) -> Dict:
        """
        Execute one step of the adaptive system.
        
        Args:
            ctx: FHE context manager
            features: Feature vector for noise prediction
            op_type: Operation type
        
        Returns:
            Dictionary with step results
        """
        self.total_steps += 1
        noise_before = ctx.noise_estimate
        
        # Get prediction from LSTM model
        predicted_noise = -1.0
        if self.predictor is not None and features is not None:
            predicted_noise = self.predictor.predict(features)
        
        # If predictor not ready (warmup period), use current noise as-is
        # This avoids the mathematical model over-predicting growth
        if predicted_noise < 0:
            predicted_noise = ctx.noise_estimate
        
        # Make decision based on prediction
        action = self.engine.decide(
            predicted_noise=predicted_noise,
            current_noise=ctx.noise_estimate,
            depth=ctx.depth,
            step=self.total_steps
        )
        
        # Execute action
        bootstrap_cost = 0.0
        if action == ACTION_FULL:
            bootstrap_cost = ctx.bootstrap(mode="full")
            self.total_bootstraps += 1
            self.total_latency += bootstrap_cost
            self.bootstrap_events.append(self.total_steps)
        elif action == ACTION_PARTIAL:
            bootstrap_cost = ctx.bootstrap(mode="partial")
            self.total_bootstraps += 1
            self.total_latency += bootstrap_cost
            self.bootstrap_events.append(self.total_steps)
        
        # Record telemetry
        self.noise_history.append(ctx.noise_estimate)
        self.prediction_history.append(predicted_noise)
        self.action_history.append(action)
        
        snapshot = TelemetrySnapshot(
            timestamp=get_timestamp(),
            step=self.total_steps,
            noise_actual=ctx.noise_estimate,
            noise_predicted=predicted_noise,
            op_type=op_type or "unknown",
            depth=ctx.depth,
            action_taken=action,
            bootstrap_count=self.total_bootstraps,
            prediction_error=abs(predicted_noise - ctx.noise_estimate)
        )
        self.telemetry.record(snapshot)
        self.telemetry.record_prediction(
            self.total_steps, predicted_noise, ctx.noise_estimate, action
        )
        
        return {
            "step": self.total_steps,
            "noise": ctx.noise_estimate,
            "predicted_noise": predicted_noise,
            "action": action,
            "bootstrap_cost": bootstrap_cost,
            "noise_before": noise_before
        }
    
    def get_results(self) -> Dict:
        """Get adaptive system results."""
        feedback = self.telemetry.get_feedback_summary()
        
        return {
            "system": "Adaptive (ML-Driven)",
            "total_steps": self.total_steps,
            "total_bootstraps": self.total_bootstraps,
            "total_latency": self.total_latency,
            "avg_noise": float(np.mean(self.noise_history)) if self.noise_history else 0,
            "max_noise": float(np.max(self.noise_history)) if self.noise_history else 0,
            "noise_history": self.noise_history,
            "prediction_history": self.prediction_history,
            "action_history": self.action_history,
            "bootstrap_events": self.bootstrap_events,
            "decision_stats": self.engine.get_stats(),
            "feedback": feedback,
            "telemetry_summary": self.telemetry.get_summary()
        }


# ─── Comparison Runner ─────────────────────────────────────────
@timer
def run_comparison(num_steps: int = 500, 
                   baseline_interval: int = 20,
                   predictor=None,
                   seed: int = 42) -> Dict:
    """
    Run a head-to-head comparison of Baseline vs Adaptive systems.
    
    Baseline: Bootstraps every `baseline_interval` steps (wasteful).
    Adaptive: Only bootstraps when noise actually exceeds thresholds.
    
    The adaptive system is smarter because it allows noise to grow
    when it's safe, only acting when needed — resulting in fewer
    total bootstrap operations.
    
    Args:
        num_steps: Number of FHE operations to simulate
        baseline_interval: Fixed bootstrap interval for baseline
        predictor: Trained NoisePredictor for adaptive system
        seed: Random seed
    
    Returns:
        Dictionary with comparison metrics
    """
    np.random.seed(seed)
    
    logger.info(f"[COMPARE] Starting comparison: {num_steps} steps")
    logger.info(f"   Baseline interval: {baseline_interval}")
    
    # Initialize both systems with identical contexts
    ctx_baseline = CKKSContextManager()
    ctx_adaptive = CKKSContextManager()
    
    # Baseline uses conservative fixed interval  
    baseline = BaselineSystem(bootstrap_interval=baseline_interval)
    
    # Adaptive system uses smart thresholds - only bootstrap at high noise
    adaptive_engine = AdaptiveDecisionEngine(
        high_threshold=0.90,
        medium_threshold=0.75,
        confidence_weight=0.9
    )
    adaptive = AdaptiveSystem(predictor=predictor, decision_engine=adaptive_engine)
    
    # Operation sequence (same for both)
    ops = np.random.choice(["add", "multiply"], size=num_steps, 
                           p=[0.55, 0.45])
    
    # Encrypted vectors
    vec_a_b = ctx_baseline.encrypt_vector([1.0, 2.0, 3.0, 4.0])
    vec_b_b = ctx_baseline.encrypt_vector([0.5, 1.5, 2.5, 3.5])
    vec_a_a = ctx_adaptive.encrypt_vector([1.0, 2.0, 3.0, 4.0])
    vec_b_a = ctx_adaptive.encrypt_vector([0.5, 1.5, 2.5, 3.5])
    
    for i in range(num_steps):
        op = ops[i]
        
        # ── Baseline System ──
        if op == "add":
            try:
                vec_a_b = ctx_baseline.homomorphic_add(vec_a_b, vec_b_b)
            except Exception:
                ctx_baseline.bootstrap(mode="full")
                vec_a_b = ctx_baseline.encrypt_vector([1.0, 2.0, 3.0, 4.0])
                vec_b_b = ctx_baseline.encrypt_vector([0.5, 1.5, 2.5, 3.5])
        else:
            try:
                vec_a_b = ctx_baseline.homomorphic_multiply(vec_a_b, vec_b_b)
            except Exception:
                ctx_baseline.bootstrap(mode="full")
                vec_a_b = ctx_baseline.encrypt_vector([1.0, 2.0, 3.0, 4.0])
                vec_b_b = ctx_baseline.encrypt_vector([0.5, 1.5, 2.5, 3.5])
        
        b_result = baseline.step(ctx_baseline, op)
        if b_result["action"] != ACTION_CONTINUE:
            vec_a_b = ctx_baseline.encrypt_vector([1.0, 2.0, 3.0, 4.0])
            vec_b_b = ctx_baseline.encrypt_vector([0.5, 1.5, 2.5, 3.5])
        
        # ── Adaptive System ──
        if op == "add":
            try:
                vec_a_a = ctx_adaptive.homomorphic_add(vec_a_a, vec_b_a)
            except Exception:
                ctx_adaptive.bootstrap(mode="full")
                vec_a_a = ctx_adaptive.encrypt_vector([1.0, 2.0, 3.0, 4.0])
                vec_b_a = ctx_adaptive.encrypt_vector([0.5, 1.5, 2.5, 3.5])
        else:
            try:
                vec_a_a = ctx_adaptive.homomorphic_multiply(vec_a_a, vec_b_a)
            except Exception:
                ctx_adaptive.bootstrap(mode="full")
                vec_a_a = ctx_adaptive.encrypt_vector([1.0, 2.0, 3.0, 4.0])
                vec_b_a = ctx_adaptive.encrypt_vector([0.5, 1.5, 2.5, 3.5])
        
        # Build feature vector for adaptive system
        tel = ctx_adaptive.get_telemetry()
        features = np.array([
            1 if op == "multiply" else 0,
            tel["depth"],
            tel["scale"] / 1e12,
            0.0,  # delta_noise placeholder
            1.0,  # noise_ratio placeholder
            tel["since_last_reset"],
            tel["noise_estimate"]
        ])
        
        a_result = adaptive.step(ctx_adaptive, features, op)
        if a_result["action"] != ACTION_CONTINUE:
            vec_a_a = ctx_adaptive.encrypt_vector([1.0, 2.0, 3.0, 4.0])
            vec_b_a = ctx_adaptive.encrypt_vector([0.5, 1.5, 2.5, 3.5])
        
        # Safety guard: auto-bootstrap if noise exceeds hard ceiling
        if ctx_baseline.noise_estimate > 0.95:
            ctx_baseline.bootstrap(mode="full")
            baseline.total_bootstraps += 1
            baseline.total_latency += 7.5  # avg bootstrap cost
            baseline.bootstrap_events.append(i)
            vec_a_b = ctx_baseline.encrypt_vector([1.0, 2.0, 3.0, 4.0])
            vec_b_b = ctx_baseline.encrypt_vector([0.5, 1.5, 2.5, 3.5])
        
        if ctx_adaptive.noise_estimate > 0.95:
            ctx_adaptive.bootstrap(mode="full")
            adaptive.total_bootstraps += 1
            adaptive.total_latency += 7.5
            adaptive.bootstrap_events.append(i)
            vec_a_a = ctx_adaptive.encrypt_vector([1.0, 2.0, 3.0, 4.0])
            vec_b_a = ctx_adaptive.encrypt_vector([0.5, 1.5, 2.5, 3.5])
        
        if (i + 1) % 100 == 0:
            logger.info(f"  Step {i+1}/{num_steps} | "
                       f"B_noise={ctx_baseline.noise_estimate:.4f} "
                       f"A_noise={ctx_adaptive.noise_estimate:.4f}")
    
    # Compile results
    b_results = baseline.get_results()
    a_results = adaptive.get_results()
    
    # Calculate improvement metrics
    bootstrap_reduction = 0.0
    if b_results["total_bootstraps"] > 0:
        bootstrap_reduction = (1 - a_results["total_bootstraps"] / 
                              b_results["total_bootstraps"]) * 100
    
    latency_improvement = 0.0
    if b_results["total_latency"] > 0:
        latency_improvement = (1 - a_results["total_latency"] / 
                               b_results["total_latency"]) * 100
    
    comparison = {
        "baseline": b_results,
        "adaptive": a_results,
        "improvement": {
            "bootstrap_reduction_pct": float(bootstrap_reduction),
            "latency_improvement_pct": float(latency_improvement),
            "baseline_bootstraps": b_results["total_bootstraps"],
            "adaptive_bootstraps": a_results["total_bootstraps"],
            "baseline_latency": b_results["total_latency"],
            "adaptive_latency": a_results["total_latency"],
            "baseline_avg_noise": b_results["avg_noise"],
            "adaptive_avg_noise": a_results["avg_noise"]
        }
    }
    
    logger.info("\n" + "="*60)
    logger.info("COMPARISON RESULTS")
    logger.info("="*60)
    logger.info(f"  Baseline bootstraps:  {b_results['total_bootstraps']}")
    logger.info(f"  Adaptive bootstraps:  {a_results['total_bootstraps']}")
    logger.info(f"  Bootstrap reduction:  {bootstrap_reduction:.1f}%")
    logger.info(f"  Baseline latency:     {b_results['total_latency']:.2f}s")
    logger.info(f"  Adaptive latency:     {a_results['total_latency']:.2f}s")
    logger.info(f"  Latency improvement:  {latency_improvement:.1f}%")
    logger.info("="*60)
    
    return comparison


# ─── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    from utils import print_banner
    print_banner()
    
    # Run comparison without ML predictor (uses mathematical model)
    results = run_comparison(num_steps=300)
    
    print("\n📋 Improvement Summary:")
    for k, v in results["improvement"].items():
        print(f"  {k}: {v}")
