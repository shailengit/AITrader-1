This technical specification provides a detailed blueprint for generating an automated trading script based on the integrated regime-switching framework derived from the sources.

# Technical Specification: Persistence-Driven Dual-Model Trading System

## 1. System Overview and Logic
The goal is to build an automated trading system that maximizes profits by identifying **persistent market regimes** (Bull vs. Bear/High-Vol) and executes trades only when a statistical regime model and a pattern-recognition model provide **convergent signals**.

### Core Principles:
*   **Regime Persistence over Reactivity:** Use **Statistical Jump Models (JM)** instead of standard Hidden Markov Models (HMM) to avoid "chattering" (erratic state switching).
*   **Tail-Risk Awareness:** Model intra-regime volatility using **GJR-GARCH** with **Student-t distributions** to account for leverage effects and fat-tailed market crashes.
*   **Financial Utility Optimization:** Train models using loss functions that penalize **Maximum Drawdown (MDD)** and **Turnover**, rather than simple Mean Squared Error (MSE).

---

## 2. Step-by-Step Implementation Pipeline

### Phase 1: Multi-Resolution Feature Engineering
**Inputs:** High-frequency (5-minute) and daily OHLCV data.
*   **Feature A (Returns):** 20-day rolling log returns.
*   **Feature B (Risk):** Exponentially weighted moving (EWM) **Downside Deviation** (hl=10, 20) and **Sortino Ratios** (hl=20, 60).
*   **Feature C (Microstructure):** Realized variance, realized quarticity, and signed jump variation.
*   **Feature D (Windows):** Use a sliding window of 20 days (14 days of daily returns, 3 days of hourly, 3 days of 15-minute) to capture multi-horizon dynamics.

### Phase 2: Regime Identification (Statistical Jump Model)
**Algorithm:** Two-State Statistical Jump Model (JM).
*   **Objective Function:** Minimize the global cost:
    $$\min \sum \text{Loss}(\text{features}_t, \theta_{s_t}) + \lambda \sum \mathbf{1}(s_t \neq s_{t-1})$$
    where $\lambda$ is the **jump penalty**.
*   **Optimization:** Use **coordinate descent** with a dynamic programming (DP) stage for state sequence optimization.
*   **Hyperparameter $\lambda$ Selection:** Perform monthly walk-forward cross-validation. Select the $\lambda$ that maximizes the **Sharpe Ratio** over an 8-year validation window.

### Phase 3: State-Dependent Volatility (MS-GARCH)
**Algorithm:** Markov-Switching GJR-GARCH.
*   **Target:** Apply to residuals of the primary mean model.
*   **Emission Distribution:** Must use **Student-t** to overcome the "Gaussian Ceiling" that underestimates the severity of tail events.
*   **Filtered Probabilities:** Extract continuous filtered probabilities ($p_t$) of being in the "Distress/High-Vol" regime.

### Phase 4: Pattern Recognition (Neural Network)
**Algorithm:** PyTorch-based **LSTM** or **XGBoost**.
*   **Inputs:** Features defined in Phase 1.
*   **Loss Function:** Use **LogMDDLoss** (Logarithmic Maximum Drawdown) or **SharpeLoss** to align training with economic utility.
*   **Regularization:** Implement **Band Turnover Regularization** to penalize rebalancing outside a 30%–100% range.

### Phase 5: Convergent Signal Generation & Portfolio Model
*   **Convergence Rule:** Execute a signal **only** if both models align:
    $$\text{Position}_t = \text{Buy if } [s_{t,JM} = \text{Bull}] \text{ AND } [NN_{forecast} > 0]$$
    $$\text{Position}_t = \text{Short/Cash if } [s_{t,JM} = \text{Bear}] \text{ OR } [p_{t,Vol} > 0.5]$$
    This consensus filter reduces false signals during regime transitions.
*   **Allocation Rule:** 
    *   *Single Asset:* Use the **0/1 Strategy** (100% in asset or 100% in risk-free asset).
    *   *Multi-Asset:* Use the **Black-Litterman model**, treating convergent signals as "investor views" to combine with market equilibrium.

---

## 3. Execution & Risk Discipline
*   **Execution Delay:** All signals must be implemented with a **one-day trading delay** to ensure robustness against latency.
*   **Transaction Frictions:** Simulations must account for a **5–10 bps** one-way transaction cost.
*   **Low-Volatility Gating:** Suppress all buy signals if the filtered high-volatility probability ($p_t$) exceeds 0.5.
*   **Walk-Forward Re-estimation:** Parameters for all models (JM centroids, $\lambda$, GARCH $\omega, \alpha, \beta$, and NN weights) must be re-estimated every three months to adapt to non-stationary market conditions.

---

## 4. Validation Metrics
*   **Primary:** Net Sharpe Ratio, Sortino Ratio, and Maximum Drawdown (MDD).
*   **Robustness:** Circular block bootstrap tests and **Hansen’s Superior Predictive Ability (SPA)** test to ensure results are not due to data snooping.
