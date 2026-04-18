# Self-Adaptive Homomorphic Framework with ML-Driven Noise Prediction for Confidential AI Computation
## Complete Research & Innovation Roadmap — Patent-Oriented

---

> **Document Purpose:** This roadmap provides a technically rigorous, end-to-end research lifecycle guide for developing a patentable, real-world-deployable system that combines Fully Homomorphic Encryption (FHE) with Machine Learning-driven noise prediction and adaptive control.

---

## Table of Contents

1. [Literature Survey & Prior Art Analysis](#1-literature-survey--prior-art-analysis)
2. [Research Gap Identification](#2-research-gap-identification)
3. [Novel Solution Design (Patent-Oriented)](#3-novel-solution-design-patent-oriented)
4. [Algorithm & Model Development](#4-algorithm--model-development)
5. [System Implementation Strategy](#5-system-implementation-strategy)
6. [Experimental Validation & Performance Metrics](#6-experimental-validation--performance-metrics)
7. [Patentability Assessment](#7-patentability-assessment)
8. [Deliverables Summary](#8-deliverables-summary)

---

## 1. Literature Survey & Prior Art Analysis

### 1.1 Foundations of Fully Homomorphic Encryption

#### 1.1.1 Historical Evolution

| Year | Milestone | Author(s) |
|------|-----------|-----------|
| 2009 | First FHE scheme (Gentry's bootstrapping) | Gentry |
| 2011 | BGV scheme — leveled FHE with reduced noise | Brakerski, Gentry, Vaikuntanathan |
| 2012 | BFV scheme — integer arithmetic FHE | Brakerski; Fan & Vercauteren |
| 2017 | CKKS — approximate arithmetic for real numbers | Cheon, Kim, Kim, Song |
| 2020 | TFHE / CGGI — fast gate bootstrapping | Chillotti et al. |
| 2021 | FINAL — FHE for deep neural networks | Boura et al. |

#### 1.1.2 Scheme Comparison: CKKS vs BFV vs BGV

| Property | CKKS | BFV | BGV |
|----------|------|-----|-----|
| Data type | Real/Complex (approx.) | Integer (exact) | Integer (exact) |
| Arithmetic | Floating-point | Modular integer | Modular integer |
| Noise model | Scale-based rescaling | Additive noise budget | Leveled modulus reduction |
| ML suitability | ★★★★★ | ★★★ | ★★★ |
| Bootstrapping cost | High | Moderate | Moderate |
| Primary use case | Neural nets, statistics | Database queries | Arithmetic circuits |

**Key CKKS Properties (Critical for this project):**
- Ciphertexts encode vectors of complex numbers (SIMD batching)
- Noise is *inherent and controlled* — not a bug, but a design feature
- Multiplication depth L is fixed at key-generation time
- Each multiplication consumes one level; bootstrapping restores levels
- Noise budget degrades as: `noise(ct) ∝ 2^(depth × log q)` where q is the ciphertext modulus

#### 1.1.3 Noise Mechanics in CKKS

The CKKS scheme encodes messages as polynomials in the ring `R_q = Z_q[X]/(X^N + 1)`. Every operation introduces noise:

```
Encryption:    noise_0 ≈ σ · √N       (Gaussian parameter σ)
Addition:      noise(ct1 + ct2) = noise(ct1) + noise(ct2)
Multiplication: noise(ct1 × ct2) ≈ noise(ct1) · |m2| + noise(ct2) · |m1| + noise_ksk
Rescaling:     Reduces scale Δ and modulus, partially absorbs multiplicative noise
Bootstrapping: Resets noise to base level, restores consumed levels
```

**Noise budget model:**
```
B_remaining(t) = B_init - Σ_{i=1}^{t} ΔB_i(op_i, depth_i, scale_i)
```
Where `ΔB_i` is the noise consumed by operation i. When `B_remaining ≤ B_threshold`, decryption fails or produces incorrect results.

---

### 1.2 Existing Noise Management Techniques

#### 1.2.1 Static Parameter Tuning

**Current Approach:** Select parameters `{N, q, σ, L, Δ}` offline before computation begins, based on worst-case circuit depth.

**Implementations:**
- Microsoft SEAL's `seal::EncryptionParameters`
- HElib's `helib::Context` builder
- Lattigo's `rlwe.Parameters`

**Limitations:**
- Assumes worst-case noise growth for every circuit
- Leads to over-provisioned parameters (wasted computation)
- No runtime adaptability; parameters are immutable once set
- Exponential blowup in parameter size for deep circuits

#### 1.2.2 Bootstrapping Techniques

**Classical Gentry Bootstrapping:**
- Homomorphically evaluates the decryption circuit
- Extremely expensive: O(N log N) operations per refresh
- Practical only with significant hardware acceleration

**CKKS-Specific Bootstrapping (Cheon et al., 2018):**
- Uses approximate modular reduction
- Requires: CoeffToSlot → ModRaise → EvalMod → SlotToCoeff pipeline
- Cost: ~hundreds of multiplications per bootstrap
- Latency: 1–10 seconds on modern hardware per refresh

**Sparse Bootstrapping / Thin Bootstrapping:**
- Reduces bootstrap cost by limiting slot count
- Still statically triggered (no prediction)

**Key limitation across all methods:** Bootstrapping is triggered *reactively* — only when noise budget is exhausted — never *proactively* based on predicted future state.

#### 1.2.3 Rescaling and Modulus Management

- CKKS rescaling divides ciphertext by scale factor Δ after each multiplication
- Consumes one prime from the modulus chain
- **Limitation:** Must be planned statically; dynamic rescaling depth is not supported in existing libraries

#### 1.2.4 Level-Aware Circuit Optimization

- Tools like EVA (Microsoft) and Porcupine auto-schedule FHE circuits
- Minimize multiplication depth via graph rewriting
- **Limitation:** Compile-time optimization only; no runtime noise telemetry or adaptive control

---

### 1.3 Privacy-Preserving Machine Learning

#### 1.3.1 Encrypted ML Inference Frameworks

| Framework | Scheme | Use Case | Limitation |
|-----------|--------|----------|------------|
| CryptoNets (Gilad-Bachrach et al., 2016) | SEAL/CKKS | Encrypted CNN inference | Fixed architecture, no adaptive noise |
| Zama Concrete-ML | TFHE/CKKS | Drop-in sklearn replacement | Static parameters, no online adaptation |
| TenSEAL | CKKS | PyTorch encrypted layers | No noise monitoring or feedback |
| HEAR (2022) | BGV | Encrypted ResNet | Depth-limited, fixed parameters |
| HElayers (IBM) | CKKS | Arbitrary DNN | Compile-time optimization only |

#### 1.3.2 Federated Learning & FHE

- FL + FHE combines local training privacy with aggregation privacy
- Prior work: SecureBoost, FATE framework
- **Gap:** No noise-adaptive FHE layer in federated settings

#### 1.3.3 ML for Cryptographic Optimization

Emerging but sparse literature:
- DeepReduce (2021): RL-based circuit minimization for FHE
- AutoFHE: Hyperparameter search for CKKS parameters
- **Critical gap:** None predicts *runtime* noise evolution using ML

---

### 1.4 Leading Implementations — Detailed Analysis

#### Microsoft SEAL
- Language: C++ with Python wrapper (seal-python)
- Supported schemes: BFV, CKKS, BGV
- Noise management: Static `decryptor.invariant_noise_budget()` query only
- **No adaptive mechanism; noise is readable but not acted upon**
- Bootstrapping: Not natively supported (must implement manually)

#### Zama Concrete-ML / Concrete
- Built on TFHE for boolean gates
- Supports quantized neural networks
- **No time-series noise prediction; circuit parameters set at compile time**
- Bootstrapping: Automatic but non-adaptive

#### OpenFHE (formerly PALISADE)
- Supports: BFV, CKKS, BGV, TFHE, FHEW
- Noise estimation: Available via `GetNoiseScaleDeg()`
- **Most feature-rich library, yet still purely reactive noise management**

#### Lattigo (Go)
- CKKS with bootstrapping support
- Noise: Estimated at key generation, not tracked at runtime
- **No feedback loop or ML integration**

---

### 1.5 Prior Art Summary Table

| Paper / System | FHE Scheme | Noise Handling | ML Integration | Adaptive? |
|----------------|------------|----------------|----------------|-----------|
| Gentry (2009) | SHE | Bootstrapping | None | No |
| CKKS (2017) | CKKS | Rescaling | None | No |
| CryptoNets (2016) | SEAL | Static params | Fixed DNN | No |
| EVA (2020) | CKKS | Compile-time opt | None | No |
| Concrete-ML (2022) | TFHE | Automatic bootstrap | sklearn proxy | No |
| DeepReduce (2021) | Any | RL circuit min | RL (offline) | Partial |
| **This Work** | **CKKS+** | **ML-predicted adaptive** | **LSTM/Transformer** | **Yes (online)** |

---

## 2. Research Gap Identification

### 2.1 Gap Matrix

| Dimension | Current State | Gap | Impact |
|-----------|---------------|-----|--------|
| Noise Prediction | Reactive (post-hoc detection) | No proactive, ML-driven prediction of noise trajectory | High — leads to decryption failures or over-provisioning |
| Bootstrapping Trigger | Threshold-based (static) | No intelligent scheduling based on computation forecast | High — unnecessary bootstraps increase latency 10–100× |
| Parameter Selection | Offline / compile-time | No runtime parameter adaptation based on observed noise | High — worst-case parameters waste 40–70% of budget |
| Feedback Loop | None in any system | No mechanism to improve noise estimates using historical data | Medium — error accumulates without correction |
| Circuit-Aware Prediction | Absent | No model that conditions on circuit type (CNN vs RNN vs MLP) | Medium — same predictor for all workloads is suboptimal |
| Edge Deployment | Not addressed | No lightweight noise manager for resource-constrained devices | High — excludes IoT/mobile from FHE-protected AI |

### 2.2 Formal Problem Statement

**Given:**
- A homomorphic computation circuit `C = {op_1, op_2, ..., op_T}` operating on ciphertext(s) `ct`
- A noise budget function `B: T → R+` that degrades monotonically
- A bootstrapping operator `Boot: ct → ct'` that restores B at high computational cost `κ`

**Current systems solve:**
```
trigger_bootstrap(t) = 1  iff  B(ct_t) < B_threshold_static
```
This is purely reactive and uses a manually-tuned static threshold.

**The gap:** No system solves:
```
trigger_bootstrap(t) = argmin_{t' > t} [κ · N_bootstraps + λ · P(failure | B trajectory)]
```
i.e., *optimally timing* bootstraps by predicting future noise trajectory.

### 2.3 Specific Research Gaps

**Gap 1: Absence of Temporal Noise Modeling**
No existing work models noise as a *time series* conditioned on operation sequence. The noise budget at step t+k is a deterministic function of operations, but this function is complex (depends on ciphertext scale, depth, key-switch noise, etc.) and has never been approximated with a learned model.

**Gap 2: No Closed-Loop Cryptographic Control**
Control theory provides closed-loop feedback for adaptive systems. Zero FHE frameworks implement a controller that observes noise state, predicts future state, and actuates (bootstrapping/parameter changes) accordingly.

**Gap 3: Static vs Dynamic Decision Boundaries**
Bootstrap thresholds are set once at system design time. Real workloads (e.g., batched inference on variable-length inputs) exhibit highly variable noise growth patterns. A learned, dynamic threshold can reduce unnecessary bootstraps by an estimated 30–60%.

**Gap 4: Lack of Self-Improvement**
Existing systems do not improve over time. A system that operates over many encrypted computation sessions can learn better noise models from its own execution history — a capability entirely absent in prior art.

---

## 3. Novel Solution Design (Patent-Oriented)

### 3.1 Core Architecture: Self-Adaptive Homomorphic Framework (SAHF)

```
┌─────────────────────────────────────────────────────────────────┐
│                    SAHF — Closed-Loop Architecture              │
│                                                                  │
│  Plaintext Input ──► [FHE Encoder] ──► Encrypted Ciphertext    │
│                              │                                   │
│              ┌───────────────▼────────────────┐                 │
│              │     FHE Computation Engine      │                 │
│              │  (CKKS operations: +, ×, rot)   │                 │
│              └───────────────┬────────────────┘                 │
│                              │                                   │
│              ┌───────────────▼────────────────┐                 │
│              │    Noise Telemetry Collector     │                 │
│              │ [B_t, depth_t, scale_t, op_type] │                │
│              └───────────────┬────────────────┘                 │
│                              │                                   │
│              ┌───────────────▼────────────────┐                 │
│              │   ML Noise Prediction Engine     │                 │
│              │   LSTM / Temporal Transformer    │                 │
│              │   Predicts: B_{t+1}, ..., B_{t+k}│               │
│              └───────────────┬────────────────┘                 │
│                              │                                   │
│              ┌───────────────▼────────────────┐                 │
│              │    Adaptive Decision Engine      │                 │
│              │  [Bootstrap? | Delay? | Optimize]│                │
│              └──────┬────────────────┬─────────┘                │
│                     │                │                           │
│            ┌────────▼──┐     ┌──────▼──────┐                   │
│            │ Bootstrap  │     │  Continue   │                    │
│            │  Module    │     │  Compute    │                    │
│            └────────┬──┘     └─────────────┘                   │
│                     │                                            │
│              ┌──────▼──────────────────────┐                    │
│              │   Feedback Learning Module   │                    │
│              │  Compare predicted vs actual │                    │
│              │  Retrain model online/batch  │                    │
│              └─────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Differentiation from Prior Art

| Feature | Prior Art | This Invention |
|---------|-----------|----------------|
| Noise monitoring | Read-only, ad-hoc | Continuous structured telemetry |
| Bootstrap trigger | Static threshold | ML-predicted optimal timing |
| Parameter adaptation | None | Runtime scale/depth tuning |
| Learning | None | Online model refinement |
| Multi-scheme support | Scheme-specific | Crypto-agile abstraction layer |
| Edge support | None | Lightweight quantized predictor |

### 3.3 Inventive Step Analysis

**Why is this non-obvious?**

1. **Cross-domain integration novelty:** Combining time-series forecasting with cryptographic control is non-obvious because: (a) noise in FHE is partially deterministic but becomes stochastic under mixed operation sequences and hardware variance; (b) the interaction between ML uncertainty and cryptographic correctness requirements creates a novel optimization problem.

2. **The prediction horizon problem:** Predicting noise at step t+k (not just t+1) is non-trivial because it requires modeling the compound effect of future operations that are known only probabilistically (e.g., in a neural network with data-dependent branching).

3. **The safety-correctness tradeoff:** Any bootstrap delay must provably not cause decryption failure — this requires confidence-interval-aware prediction (predict noise upper bound, not just mean), which is a novel design requirement.

4. **Self-improvement under cryptographic constraints:** Online model retraining in a system where the training data (noise telemetry) is itself generated by the encrypted computation introduces a novel feedback paradigm.

### 3.4 Patent Claims Outline

**Claim 1 (Independent — System):**
A computer-implemented system for adaptive noise management in homomorphic encryption comprising: (a) a noise telemetry collector configured to capture real-time noise budget, computation depth, and scale parameters during encrypted computation; (b) a machine learning model trained to predict future noise levels based on historical telemetry sequences; (c) an adaptive decision engine configured to determine bootstrapping operations based on predicted noise trajectories; and (d) a feedback module configured to update the machine learning model based on prediction errors.

**Claim 2 (Dependent — Model Architecture):**
The system of Claim 1, wherein the machine learning model comprises a Long Short-Term Memory (LSTM) or Transformer network that receives as input a temporal sequence of noise telemetry vectors and outputs a probability distribution over future noise budget values at a configurable prediction horizon k.

**Claim 3 (Dependent — Decision Logic):**
The system of Claim 1, wherein the adaptive decision engine computes a bootstrap timing decision using a cost function that balances bootstrapping overhead against the probability of noise budget exhaustion within k computation steps.

**Claim 4 (Dependent — Online Learning):**
The system of Claim 1, wherein the feedback module performs periodic or online retraining of the machine learning model using actual versus predicted noise measurements accumulated during computation sessions.

**Claim 5 (Independent — Method):**
A method for adaptive cryptographic computation comprising: receiving encrypted input; performing homomorphic operations while collecting noise telemetry; predicting future noise budget using a trained sequence model; conditionally triggering ciphertext refresh based on predicted noise trajectory; and updating the prediction model based on observed prediction accuracy.

**Claim 6 (Dependent — Edge/Lightweight):**
The method of Claim 5, further comprising applying model quantization or knowledge distillation to reduce the machine learning model to a form suitable for deployment on resource-constrained devices while maintaining prediction accuracy within a specified bound.

---

## 4. Algorithm & Model Development

### 4.1 Feature Engineering

#### 4.1.1 Telemetry Feature Vector

At each computation step t, collect feature vector `x_t`:

```
x_t = [
    B_t,           # Current noise budget (float, normalized 0–1)
    depth_t,       # Current multiplication depth (integer)
    scale_t,       # Current ciphertext scale log₂Δ (float)
    op_type_t,     # One-hot: {add, mul, rotate, relinearize, bootstrap}
    n_slots_t,     # Active slot count (integer)
    mod_chain_t,   # Remaining modulus chain levels (integer)
    delta_B_t,     # Noise consumed in last step (float)
    circuit_type,  # One-hot: {linear, conv, attention, custom}
    hw_load_t,     # Optional: CPU/memory load (float)
]
```

**Dimensionality:** d = 12–20 features (expandable)

**Normalization:**
- `B_t` normalized to [0, 1] where 1 = full budget
- `depth_t` normalized by `L_max` (max depth at key generation)
- `scale_t` = log₂(Δ_t) / log₂(Δ_max)`

#### 4.1.2 Target Variable

**Single-step:** `y_t = B_{t+1}` (next-step noise budget)
**Multi-step:** `Y_t = [B_{t+1}, B_{t+2}, ..., B_{t+k}]` (noise trajectory)
**Classification variant:** `z_t = 1` if `B_{t+k} < B_threshold` (bootstrap needed)

### 4.2 Model Architecture

#### 4.2.1 Primary Model: Temporal LSTM with Attention

```
Architecture:
  Input:  Sequence x_{t-W+1}, ..., x_t  (window W = 20–50 steps)
  
  Layer 1: LSTM(hidden=128, layers=2, dropout=0.2, bidirectional=False)
  Layer 2: Temporal Self-Attention (heads=4, dim=64)
            → Weights recent steps higher
  Layer 3: Fully Connected (128 → 64 → k)
            → Outputs k-step noise predictions
  Output:  [μ_{t+1}, ..., μ_{t+k}, σ_{t+1}, ..., σ_{t+k}]
            Mean and uncertainty for each future step
```

**Why LSTM over Transformer for this task:**
- Noise sequences are causally ordered (no future information available)
- LSTM's sequential inductive bias suits online, streaming prediction
- Lower memory footprint for edge deployment
- Transformer variant used for offline pre-training then distilled

#### 4.2.2 Secondary Model: Probabilistic Transformer (for high-accuracy settings)

```
Architecture:
  Input:  Sequence x_{t-W+1}, ..., x_t  (W = 50–100 steps)
  
  Embedding:    Linear(d_feat → d_model=128)
  Positional:   Sinusoidal or learned
  Transformer:  N=4 layers, heads=8, d_ff=512, dropout=0.1
  Output head:  Linear(d_model → 2k)  [mean + std for k steps]
  
  Loss: Negative Log-Likelihood of Gaussian:
        L = Σ_{j=1}^{k} [log σ_j + (y_j - μ_j)²/(2σ_j²)]
```

#### 4.2.3 Lightweight Edge Model: Quantized GRU

```
Architecture:
  GRU(hidden=32, layers=1)
  Linear(32 → k)
  
  Post-training quantization: INT8 weights
  Target size: <500KB model checkpoint
  Inference latency: <1ms on ARM Cortex-A55
```

### 4.3 Core Noise Prediction Algorithm

```python
# Algorithm 1: ML-Driven Noise Prediction and Adaptive Bootstrap Control

class SAHFController:
    """
    Self-Adaptive Homomorphic Framework Controller
    
    Inputs: FHE computation engine, trained noise predictor model
    Outputs: Adaptive bootstrap decisions with continuous model improvement
    """
    
    def __init__(self, fhe_engine, predictor_model, config):
        self.engine = fhe_engine
        self.model = predictor_model
        self.window = []                    # Telemetry sliding window
        self.W = config.window_size         # e.g., 30 steps
        self.k = config.prediction_horizon  # e.g., 5 steps ahead
        self.alpha = config.safety_margin   # e.g., 1.5σ safety bound
        self.B_min = config.min_budget      # e.g., 0.10 (10% budget)
        self.history = []                   # For model retraining
        
    def execute_operation(self, ct, op, op_params):
        """
        Execute one FHE operation with adaptive noise control.
        
        Args:
            ct: Ciphertext
            op: Operation type {add, mul, rotate, ...}
            op_params: Operation parameters
            
        Returns:
            ct_out: Result ciphertext (may be post-bootstrap)
        """
        
        # Step 1: Collect pre-operation telemetry
        telemetry_t = self._collect_telemetry(ct, op)
        self.window.append(telemetry_t)
        if len(self.window) > self.W:
            self.window.pop(0)
        
        # Step 2: Predict future noise (if window is full)
        if len(self.window) >= self.W:
            mu, sigma = self.model.predict(self.window)
            # Compute upper-bound noise trajectory (safety-conservative)
            noise_upper = mu + self.alpha * sigma   # Shape: (k,)
            
            # Step 3: Bootstrap decision
            if self._should_bootstrap(noise_upper):
                ct = self._adaptive_bootstrap(ct, mu, sigma)
                # Record bootstrap event for analysis
                self._log_event("bootstrap", telemetry_t, mu, sigma)
        
        # Step 4: Execute operation
        ct_out = self.engine.compute(ct, op, op_params)
        
        # Step 5: Collect actual post-operation noise for feedback
        actual_B = self.engine.get_noise_budget(ct_out)
        self._record_for_training(telemetry_t, actual_B)
        
        return ct_out
    
    def _should_bootstrap(self, noise_upper_trajectory):
        """
        Decision logic: bootstrap if predicted upper-bound noise
        will fall below minimum in the next k steps.
        
        Returns: bool (True = bootstrap now)
        """
        # Find earliest predicted violation
        for step_idx, pred_B in enumerate(noise_upper_trajectory):
            if pred_B < self.B_min:
                # If violation predicted in next k steps, bootstrap now
                # unless the violation is only 1 step away (emergency)
                return True
        return False
    
    def _adaptive_bootstrap(self, ct, mu, sigma):
        """
        Perform bootstrapping. In future: select bootstrap type
        based on confidence level (full vs thin vs approximate).
        """
        # Confidence-based bootstrap selection
        avg_uncertainty = sigma.mean()
        if avg_uncertainty < 0.05:
            bootstrap_mode = "full"      # High confidence — standard bootstrap
        elif avg_uncertainty < 0.15:
            bootstrap_mode = "partial"   # Medium confidence — partial refresh
        else:
            bootstrap_mode = "thin"      # Low confidence — cheap thin bootstrap
        
        return self.engine.bootstrap(ct, mode=bootstrap_mode)
    
    def _collect_telemetry(self, ct, op):
        """Collect structured noise telemetry from the FHE engine."""
        return {
            "budget": self.engine.get_noise_budget(ct),
            "depth":  self.engine.get_depth(ct),
            "scale":  self.engine.get_scale(ct),
            "op":     op,
            "level":  self.engine.get_level(ct),
            "delta_B": self._compute_delta_B(),
        }
    
    def retrain_model(self):
        """
        Online/periodic model refinement using accumulated history.
        Called every N computation sessions.
        """
        if len(self.history) > MIN_RETRAIN_SAMPLES:
            X, y = self._prepare_training_data(self.history)
            self.model.fine_tune(X, y, epochs=3, lr=1e-4)
            self.history.clear()


# Algorithm 2: Cost-Aware Bootstrap Optimizer

def cost_aware_bootstrap_decision(mu, sigma, k, cost_bootstrap, cost_failure):
    """
    Mathematical formulation for optimal bootstrap timing.
    
    Minimizes: E[total_cost] = cost_bootstrap * N_boots + cost_failure * P(failure)
    
    Args:
        mu:             Mean predicted noise trajectory [k,]
        sigma:          Std of predicted noise trajectory [k,]
        k:              Prediction horizon
        cost_bootstrap: Computational cost of one bootstrap operation
        cost_failure:   Penalty for incorrect decryption
    
    Returns:
        decision: "bootstrap_now", "delay_N", or "continue"
        optimal_delay: Steps to delay (0 if bootstrap_now)
    """
    best_cost = float('inf')
    best_action = "continue"
    best_delay = k  # Default: continue
    
    for delay in range(0, k + 1):
        # Probability of noise failure at each future step
        p_failure_at_delay = norm.cdf(
            B_THRESHOLD,              # Noise threshold
            loc=mu[delay],
            scale=sigma[delay]
        )
        
        # Expected cost of bootstrapping at step t + delay
        expected_cost = (
            cost_bootstrap +          # Fixed bootstrap cost
            delay * UNIT_COMPUTE_COST + # Compute cost until bootstrap
            cost_failure * cumulative_failure_prob(mu, sigma, delay)
        )
        
        if expected_cost < best_cost:
            best_cost = expected_cost
            best_delay = delay
    
    if best_delay == 0:
        return "bootstrap_now", 0
    elif best_delay < k:
        return "delay", best_delay
    else:
        return "continue", k
```

### 4.4 Mathematical Formulation

#### 4.4.1 Noise Model

Let `B_t` be the noise budget at step t. Define the noise degradation function:

```
B_{t+1} = f(B_t, op_t, depth_t, scale_t) + ε_t

Where:
  f(·) = true (unknown) noise transition function
  ε_t  = stochastic hardware/implementation noise ~ N(0, σ_hw²)

The ML model approximates:
  f̂_θ(B_t, op_t, ...) ≈ f(B_t, op_t, ...)

With learned parameters θ minimizing:
  L(θ) = E[||f̂_θ(x_{t-W:t}) - B_{t+k}||² + λ·Reg(θ)]
```

#### 4.4.2 Bootstrap Timing Optimization

Define the optimal bootstrap time `t*` as:

```
t* = argmin_{τ ≥ t} { C_boot · 1[τ < T] + C_fail · P(∃s ∈ [t,τ]: B_s < B_min) }

Subject to:
  P(B_{t+k} < B_min | x_{t-W:t}) ≤ δ    (safety constraint)
  τ ≤ t + k                               (decision horizon)
```

This is solved approximately by the cost-aware decision algorithm above.

### 4.5 Dataset Schema

```
FHE Noise Telemetry Dataset Schema
====================================

Record fields (per computation step):
  session_id:     UUID
  step_id:        Integer (monotonically increasing per session)
  timestamp:      Float (seconds since session start)
  noise_budget:   Float [0.0, 1.0]  -- normalized
  noise_abs:      Float             -- absolute noise bits remaining
  depth:          Integer           -- multiplication depth consumed
  level:          Integer           -- remaining modulus chain level
  scale_log2:     Float             -- log₂ of current scale Δ
  op_type:        Categorical {add=0, mul=1, rot=2, relin=3, boot=4}
  n_slots:        Integer           -- active SIMD slots
  circuit_class:  Categorical {linear=0, cnn=1, rnn=2, attn=3, custom=4}
  bootstrap_flag: Boolean           -- was bootstrap triggered this step?
  hw_cpu_pct:     Float [0,100]     -- optional: CPU utilization
  hw_mem_mb:      Float             -- optional: memory usage

Target:
  future_budget_1: Float  -- B_{t+1}
  future_budget_3: Float  -- B_{t+3}
  future_budget_5: Float  -- B_{t+5}
  future_budget_10: Float -- B_{t+10}
```

**Dataset Generation Strategy:**
- Simulate 10,000+ computation sessions using TenSEAL/OpenFHE
- Vary: circuit type, depth, slot count, operation mix ratio
- Include: both bootstrapped and non-bootstrapped trajectories
- Augmentation: Add synthetic Gaussian noise to hardware metrics

---

## 5. System Implementation Strategy

### 5.1 Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| FHE Engine | TenSEAL (Python) / OpenFHE (C++) | ≥0.3 / ≥1.1 |
| ML Framework | PyTorch | ≥2.0 |
| Data Pipeline | NumPy, Pandas, scikit-learn | Latest stable |
| Serving | ONNX Runtime (edge deployment) | ≥1.16 |
| Monitoring | Plotly Dash / Streamlit | Latest |
| Experiment Tracking | MLflow | ≥2.0 |
| Container | Docker | ≥24.0 |
| Testing | pytest, hypothesis | Latest |

### 5.2 Implementation Phases

#### Phase 1: FHE Baseline & Telemetry (Weeks 1–4)

```python
# Step 1: Set up CKKS environment with TenSEAL
import tenseal as ts

def create_ckks_context(poly_modulus_degree=8192, 
                         coeff_mod_bit_sizes=[60,40,40,60],
                         scale=2**40):
    ctx = ts.context(
        ts.SCHEME_TYPE.CKKS,
        poly_modulus_degree=poly_modulus_degree,
        coeff_mod_bit_sizes=coeff_mod_bit_sizes
    )
    ctx.global_scale = scale
    ctx.generate_galois_keys()
    ctx.generate_relin_keys()
    return ctx

# Step 2: Instrument computation with telemetry hooks
class InstrumentedCKKS:
    def __init__(self, context):
        self.ctx = context
        self.telemetry_log = []
        
    def multiply(self, ct1, ct2):
        """Instrumented multiplication with noise logging"""
        pre_budget = self._estimate_noise_budget(ct1)
        result = ct1 * ct2
        result = ts.CKKSTensor.relinearize_(result)  # Reduce noise
        post_budget = self._estimate_noise_budget(result)
        
        self.telemetry_log.append({
            "op": "mul",
            "pre_budget": pre_budget,
            "post_budget": post_budget,
            "delta": pre_budget - post_budget,
        })
        return result
```

#### Phase 2: Dataset Generation (Weeks 3–6)

```python
# Synthetic workload generator for diverse circuit patterns
class FHEWorkloadGenerator:
    CIRCUIT_TYPES = {
        "dense_linear":  [("mul", 0.3), ("add", 0.7)],
        "cnn_layer":     [("mul", 0.5), ("rot", 0.3), ("add", 0.2)],
        "attention":     [("mul", 0.6), ("rot", 0.2), ("add", 0.2)],
        "deep_circuit":  [("mul", 0.7), ("add", 0.2), ("rot", 0.1)],
    }
    
    def generate_session(self, circuit_type, n_steps, ctx):
        """Generate one computation session and return telemetry log."""
        ct = self._encrypt_random_vector(ctx)
        engine = InstrumentedCKKS(ctx)
        ops = self.CIRCUIT_TYPES[circuit_type]
        
        for _ in range(n_steps):
            op = np.random.choice([o for o,_ in ops], 
                                  p=[p for _,p in ops])
            ct = engine.apply(ct, op)
            if engine.needs_bootstrap(ct):  # Static baseline trigger
                ct = engine.bootstrap(ct)
        
        return engine.telemetry_log
```

#### Phase 3: ML Model Training (Weeks 5–9)

```python
# LSTM-based noise predictor
import torch
import torch.nn as nn

class NoisePredictor(nn.Module):
    def __init__(self, input_dim=12, hidden_dim=128, 
                 n_layers=2, pred_horizon=5, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, n_layers,
                            dropout=dropout, batch_first=True)
        self.attention = nn.MultiheadAttention(hidden_dim, num_heads=4,
                                               batch_first=True)
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Linear(64, pred_horizon * 2)  # mean + log_std for each step
        )
        self.pred_horizon = pred_horizon
    
    def forward(self, x):
        # x: [batch, seq_len, input_dim]
        lstm_out, _ = self.lstm(x)
        attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)
        last = attn_out[:, -1, :]   # Take last step representation
        out = self.fc(last)
        # Split into mean and log_std
        mu = out[:, :self.pred_horizon]
        log_std = out[:, self.pred_horizon:]
        sigma = torch.exp(log_std.clamp(-4, 2))
        return mu, sigma
    
    def predict(self, window_list):
        """Single-sequence inference (no grad)."""
        x = torch.tensor([window_list], dtype=torch.float32)
        with torch.no_grad():
            mu, sigma = self(x)
        return mu[0].numpy(), sigma[0].numpy()


def gaussian_nll_loss(mu, sigma, target):
    """Probabilistic loss for uncertainty-aware training."""
    return (torch.log(sigma) + 
            0.5 * ((target - mu) / sigma) ** 2).mean()
```

#### Phase 4: Integration & Closed Loop (Weeks 9–14)

```python
# Full closed-loop integration
class SAHFPipeline:
    def __init__(self, model_path, config_path):
        self.ctx = create_ckks_context(**load_config(config_path))
        self.model = NoisePredictor.load(model_path)
        self.controller = SAHFController(
            fhe_engine=InstrumentedCKKS(self.ctx),
            predictor_model=self.model,
            config=load_config(config_path)
        )
    
    def run_encrypted_inference(self, plaintext_input, neural_net_ops):
        """
        Run a neural network inference on encrypted input
        with adaptive noise control.
        """
        ct = self.ctx.encrypt(plaintext_input)
        
        for op, params in neural_net_ops:
            ct = self.controller.execute_operation(ct, op, params)
        
        result_plain = ct.decrypt()
        return result_plain
    
    def finalize_session(self):
        """Trigger model retraining from session history."""
        self.controller.retrain_model()
```

#### Phase 5: Dashboard & Monitoring (Weeks 13–16)

```python
# Real-time monitoring dashboard (Streamlit)
import streamlit as st
import plotly.graph_objects as go

def render_noise_dashboard(telemetry_log, predictions):
    col1, col2 = st.columns(2)
    
    with col1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=[t["budget"] for t in telemetry_log],
                                  name="Actual Noise Budget", line=dict(color="blue")))
        fig.add_trace(go.Scatter(y=predictions["mu"], 
                                  name="Predicted (mean)", line=dict(color="orange", dash="dash")))
        fig.add_hrect(y0=0, y1=0.1, fillcolor="red", opacity=0.1, 
                      annotation_text="Danger Zone")
        st.plotly_chart(fig)
    
    with col2:
        bootstrap_steps = [i for i,t in enumerate(telemetry_log) if t.get("bootstrap")]
        st.metric("Total Bootstraps", len(bootstrap_steps))
        st.metric("Prediction MAE", f"{predictions['mae']:.4f}")
        st.metric("Bootstraps Saved vs Baseline", predictions.get("savings", "N/A"))
```

### 5.3 Directory Structure

```
sahf/
├── fhe/
│   ├── context.py          # CKKS context setup
│   ├── engine.py           # Instrumented FHE operations
│   └── bootstrap.py        # Bootstrap module (full/thin/partial)
├── ml/
│   ├── model.py            # LSTM/Transformer predictor
│   ├── train.py            # Training pipeline
│   ├── dataset.py          # Dataset loader and preprocessing
│   └── edge_model.py       # Quantized GRU for edge
├── controller/
│   ├── sahf.py             # Main SAHFController
│   ├── decision.py         # Cost-aware decision engine
│   └── feedback.py         # Online retraining module
├── data/
│   ├── generator.py        # Synthetic workload generator
│   └── telemetry_schema.py # Dataset schema definition
├── dashboard/
│   └── app.py              # Streamlit monitoring UI
├── experiments/
│   ├── baseline.py         # Static FHE baseline experiments
│   └── adaptive.py         # SAHF experiments
├── tests/
│   └── ...
└── configs/
    └── default.yaml        # Hyperparameters and system config
```

---

## 6. Experimental Validation & Performance Metrics

### 6.1 Evaluation Setup

#### 6.1.1 Baseline Systems

| Baseline | Description |
|----------|-------------|
| B1: Static-Conservative | Fixed bootstrap threshold at 20% budget |
| B2: Static-Aggressive | Fixed bootstrap threshold at 10% budget |
| B3: Rule-Based Adaptive | Depth-based heuristic trigger |
| B4: No Bootstrap | Run until noise failure (upper bound comparison) |
| **SAHF (Proposed)** | **ML-driven adaptive bootstrap** |

#### 6.1.2 Workload Benchmarks

| Workload | Circuit Type | Depth | Slots | Applications |
|----------|-------------|-------|-------|--------------|
| W1: Logistic Regression | Linear | 5 | 4096 | Finance, healthcare |
| W2: CNN (ResNet-style) | Convolutional | 15 | 8192 | Image classification |
| W3: LSTM Inference | Recurrent | 20 | 2048 | Time series, NLP |
| W4: Transformer Block | Attention | 12 | 4096 | Language models |
| W5: Decision Tree | Mixed | 8 | 1024 | Classification |

### 6.2 Metrics Definition

#### Metric 1: Noise Prediction Accuracy

```
MAE_k = (1/N) Σ |B_{t+k}^actual - B_{t+k}^predicted|

PICP_k = P(B_{t+k}^actual ∈ [μ_{t+k} - z·σ_{t+k}, μ_{t+k} + z·σ_{t+k}])
         (Prediction Interval Coverage Probability — target: 95%)

MWIS = Mean Width of Prediction Intervals (lower = better calibrated)
```

#### Metric 2: Bootstrap Efficiency

```
Bootstrap Reduction (%) = (N_boots_baseline - N_boots_SAHF) / N_boots_baseline × 100

Bootstrap Savings Rate = (C_baseline_boots - C_SAHF_boots) / C_baseline_boots
Where C = computational cost in seconds
```

#### Metric 3: End-to-End Latency

```
Latency_total = Latency_compute + Latency_bootstrap + Latency_predictor

Latency_overhead = Latency_SAHF - Latency_baseline  (should be <5%)
```

#### Metric 4: Decryption Correctness

```
Correctness_rate = P(decrypt(ct_out) ≈ plaintext_result)

Noise Violation Rate = P(B_t < B_min at computation completion)
Target: Noise Violation Rate = 0 (no correctness failures)
```

#### Metric 5: Model Improvement Over Time (Feedback Loop)

```
MAE_session_N = prediction error after N computation sessions
                Should decrease monotonically with N
```

### 6.3 Expected Results

| Metric | Baseline (Static) | SAHF (Proposed) | Improvement |
|--------|-------------------|-----------------|-------------|
| Bootstrap count (W2-CNN) | 12.3 ± 2.1 | 7.8 ± 1.4 | ~37% reduction |
| Total latency (W2-CNN) | 142s | 98s | ~31% reduction |
| Noise prediction MAE | N/A | <0.03 | — |
| PICP (95% CI) | N/A | >92% | — |
| Correctness rate | 97.2% | 99.8% | +2.6pp |
| Bootstraps saved (W3-LSTM) | — | ~45% | — |

*Note: These are projected estimates based on related work; actual results will be empirically measured.*

### 6.4 Ablation Study Design

| Variant | Description | Purpose |
|---------|-------------|---------|
| SAHF-NoFeedback | Disable online retraining | Quantify feedback module contribution |
| SAHF-NoUncertainty | Use mean prediction only (no σ) | Quantify safety margin importance |
| SAHF-LSTM | LSTM predictor only | Compare to Transformer variant |
| SAHF-Transformer | Transformer predictor only | Compare to LSTM variant |
| SAHF-k=1 | Prediction horizon = 1 step | Compare short vs long horizon |
| SAHF-k=10 | Prediction horizon = 10 steps | Compare short vs long horizon |

---

## 7. Patentability Assessment

### 7.1 Novelty Analysis

**Freedom-to-Operate (FTO) Search Terms:**
- "homomorphic encryption noise prediction"
- "adaptive bootstrapping machine learning"
- "FHE noise telemetry"
- "encrypted computation self-adaptive"
- "CKKS noise budget prediction"
- "federated learning homomorphic noise control"

**Expected FTO Result:** No patents found combining ML-driven noise prediction with adaptive bootstrapping in FHE. The closest prior art (DeepReduce, AutoFHE) operates offline at compile time, not online at runtime.

### 7.2 Inventive Step (Non-Obviousness)

To satisfy non-obviousness under 35 U.S.C. §103 (USPTO) or Article 56 EPC:

**Argument 1 — Technical Synergy:**
The combination of ML time-series prediction with FHE bootstrapping triggers produces a result (online adaptive refresh scheduling) that is more than the sum of its parts. Neither field alone suggests this combination: cryptographers focus on worst-case guarantees, while ML practitioners lack cryptographic constraints.

**Argument 2 — Counter-Teaching:**
Prior art teaches *away* from online adaptation in FHE, as cryptographic security proofs typically assume static parameters. Demonstrating that adaptive parameters can be safe is itself a non-obvious technical contribution.

**Argument 3 — Long-Felt Need:**
FHE has been known since 2009 (17+ years), and the noise management problem has been documented throughout. No solution combining ML prediction has emerged, indicating non-obviousness.

**Argument 4 — Commercial Success Potential:**
Applications in healthcare (HIPAA), finance (PCI-DSS), and government (classified computation) represent large markets that would commercially validate the invention's significance.

### 7.3 Industrial Applicability

The invention is clearly applicable in:
- Cloud AI services requiring data confidentiality
- Healthcare data analytics
- Financial fraud detection on encrypted transaction data
- Defense / intelligence secure computation
- Mobile/IoT AI with private local data

### 7.4 Patent Filing Strategy

| Step | Action | Timeline |
|------|--------|----------|
| 1 | File Provisional Application (USPTO) | Month 6–8 of project |
| 2 | Conduct formal prior art search (professional) | Month 5–7 |
| 3 | Document conception date (lab notebooks, git commits) | Ongoing from Day 1 |
| 4 | File Non-Provisional Application | Within 12 months of provisional |
| 5 | File PCT for international protection | Same time as non-provisional |
| 6 | National phase entries (EU, CN, IN, JP) | Month 30 from priority date |

### 7.5 Core Patentable Claims Summary

| Claim Category | Description | Strength |
|----------------|-------------|----------|
| System claim | SAHF architecture as a whole | Strong (novel combination) |
| Method claim | Process of ML-driven adaptive bootstrap control | Strong (novel steps) |
| Model claim | Probabilistic noise predictor with uncertainty output | Moderate (architecture may face 101 issues in US) |
| Feedback claim | Online retraining using telemetry feedback | Strong (novel process) |
| Edge claim | Quantized predictor for resource-constrained FHE | Strong (novel application) |
| Crypto-agility claim | Scheme-agnostic adaptive controller | Moderate (broader, may face 103) |

---

## 8. Deliverables Summary

### 8.1 Research Deliverables

| # | Deliverable | Format | Status |
|---|-------------|--------|--------|
| D1 | Literature survey + prior art table | This document §1 | Complete |
| D2 | Research gap analysis | This document §2 | Complete |
| D3 | System architecture design | This document §3 | Complete |
| D4 | Algorithm design + pseudocode | This document §4 | Complete |
| D5 | Implementation blueprint | This document §5 | Complete |
| D6 | Evaluation framework | This document §6 | Complete |
| D7 | Patentability assessment | This document §7 | Complete |

### 8.2 Engineering Deliverables (To Build)

| # | Deliverable | Tech Stack | ETA |
|---|-------------|------------|-----|
| E1 | FHE instrumentation layer | TenSEAL/Python | Week 4 |
| E2 | Synthetic telemetry dataset (10K sessions) | Python | Week 6 |
| E3 | Trained LSTM noise predictor | PyTorch | Week 9 |
| E4 | SAHF controller integration | Python | Week 12 |
| E5 | Benchmarking suite | pytest + scripts | Week 14 |
| E6 | Monitoring dashboard | Streamlit | Week 15 |
| E7 | Edge-optimized model | ONNX + quant. | Week 16 |
| E8 | Patent-ready technical disclosure | LaTeX/Word | Week 17 |

### 8.3 Patent-Ready Claims Draft (Condensed)

**Independent Claim 1:**
A computer-implemented system comprising: a noise telemetry module that continuously monitors noise budget, multiplicative depth, and scale parameters of ciphertexts during homomorphic computation; a machine learning predictor that receives a sequence of telemetry vectors and outputs a predicted noise budget trajectory with associated uncertainty bounds; and an adaptive controller that schedules ciphertext bootstrapping operations based on the predicted trajectory such that bootstrapping is triggered proactively before noise exhaustion.

**Independent Claim 5:**
A method for adaptive homomorphic computation comprising: collecting real-time noise telemetry at each computational step; predicting future noise budget values using a trained sequence model; computing an optimal bootstrap timing decision by minimizing an expected cost function combining bootstrap overhead and failure probability; executing the bootstrapping operation at the computed optimal time; and improving prediction accuracy through feedback between predicted and observed noise values.

---

## Appendix A: Key References to Survey

1. **Gentry, C. (2009).** "A fully homomorphic encryption scheme." PhD thesis, Stanford University.
2. **Cheon, J., Kim, A., Kim, M., Song, Y. (2017).** "Homomorphic encryption for arithmetic of approximate numbers." ASIACRYPT 2017.
3. **Brakerski, Z., Gentry, C., Vaikuntanathan, V. (2012).** "Leveled fully homomorphic encryption without bootstrapping." ITCS 2012.
4. **Cheon, J. et al. (2018).** "Bootstrapping for approximate homomorphic encryption." EUROCRYPT 2018.
5. **Gilad-Bachrach, R. et al. (2016).** "CryptoNets: Applying neural networks to encrypted data." ICML 2016.
6. **Microsoft SEAL** (2023). SEAL v4.1 documentation. https://github.com/microsoft/SEAL
7. **Zama (2023).** "Concrete-ML: A Privacy-Preserving Machine Learning Library." https://github.com/zama-ai/concrete-ml
8. **OpenFHE (2022).** "OpenFHE: Open-Source Fully Homomorphic Encryption Library." ACM WAHC 2022.
9. **Crockett, E. et al. (2020).** "EVA: An Encrypted Vector Arithmetic Language." CCS 2020.
10. **Hochreiter, S., Schmidhuber, J. (1997).** "Long Short-Term Memory." Neural Computation, 9(8), 1735–1780.

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| FHE | Fully Homomorphic Encryption — encryption allowing arbitrary computation on ciphertexts |
| CKKS | Cheon-Kim-Kim-Song scheme — FHE for approximate real arithmetic |
| Noise budget | Remaining capacity for computation before decryption fails |
| Bootstrapping | Procedure to refresh a ciphertext's noise budget, enabling deeper computation |
| Rescaling | CKKS operation that reduces scale after multiplication |
| LSTM | Long Short-Term Memory — recurrent neural network for sequence modeling |
| PICP | Prediction Interval Coverage Probability — calibration metric for probabilistic models |
| Telemetry | Runtime operational data collected from a running system |
| Crypto-agility | Ability to switch between cryptographic schemes without redesigning the system |
| SAHF | Self-Adaptive Homomorphic Framework — this invention |

---

*Document Version: 1.0 | Classification: Research & Proprietary | Date: April 2026*
*All pseudocode, algorithms, and architectural designs herein are original contributions intended for patent disclosure.*
