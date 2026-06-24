"""
methodology.py — single source of truth for AIECO's estimation assumptions.

Every constant and formula used by the emissions calculator lives here so that
the public /methodology page is generated from the *same* numbers the calculator
actually uses. If a figure changes, it changes in one place and both the
computation and its public documentation stay in sync.

All figures are research-derived estimates, not measured values. Sources are
named per constant and summarised on the methodology page.
"""
import math

# ── Tokenisation ────────────────────────────────────────────────────────────
# Average English word maps to ~1.33 sub-word tokens for modern BPE tokenisers.
# Real values vary 1.2–1.5x by tokeniser and language.
TOKENS_PER_WORD = 1.33

# ── Input vs output energy ──────────────────────────────────────────────────
# Transformer inference has two phases:
#   - prefill (processing the input prompt) — highly parallel, cheap per token
#   - decode (generating output tokens) — sequential, the dominant energy cost
# We weight each *input* token at a fraction of a *decode* token's energy.
# Estimate from autoregressive inference profiling (prefill ≈ 0.2–0.3x decode/token).
INPUT_ENERGY_WEIGHT = 0.25

# Without observing the actual response we assume the model returns roughly as
# many tokens as the prompt contained. Clearly an assumption, stated as such.
DEFAULT_OUTPUT_RATIO = 1.0

# ── Data-centre overhead (PUE) ──────────────────────────────────────────────
# Power Usage Effectiveness: total facility power / IT power. Hyperscale data
# centres report ~1.1–1.2; the global average is closer to 1.5 (Uptime 2023).
# We use a hyperscale-leaning default since most large models run in such fleets.
DEFAULT_PUE = 1.2

# ── Cost ────────────────────────────────────────────────────────────────────
# UK average electricity unit price (Ofgem price cap era), GBP per kWh.
ELECTRICITY_PRICE_GBP_PER_KWH = 0.28

# ── Uncertainty model ───────────────────────────────────────────────────────
# We treat the estimate as the product of independent uncertain factors and
# combine their relative 1-sigma uncertainties in quadrature. The energy-per-
# token term dominates because vendors do not publish per-token energy for
# proprietary models.
UNCERTAINTY_COMPONENTS = {
    "Tokenisation (words → tokens)":      0.15,
    "Energy per token (model-dependent)": 0.50,
    "Data-centre overhead (PUE)":         0.10,
    "Grid carbon intensity":              0.10,
}


def combined_relative_uncertainty():
    """Combine the independent relative uncertainties in quadrature."""
    return math.sqrt(sum(u * u for u in UNCERTAINTY_COMPONENTS.values()))


def uncertainty_bounds(central):
    """Return (low, high) for a central estimate using the combined uncertainty.

    The band is multiplicative and the lower bound is floored at zero so a
    figure can never imply negative emissions.
    """
    u = combined_relative_uncertainty()
    low = max(0.0, central * (1 - u))
    high = central * (1 + u)
    return low, high


def estimate_emissions(word_count, wh_per_token, carbon_intensity_kg_kwh,
                       output_ratio=DEFAULT_OUTPUT_RATIO, pue=DEFAULT_PUE):
    """Core estimation pipeline shared by the model and any callers.

    Returns a dict with the token split, energy, central CO2 (grams) and the
    low/high uncertainty bounds. Pure function — no database access — so it is
    trivially testable and reused by PromptEmissions.save().
    """
    input_tokens = int(round(word_count * TOKENS_PER_WORD))
    output_tokens = int(round(input_tokens * output_ratio))

    # Effective tokens weight prefill (input) below decode (output).
    effective_tokens = input_tokens * INPUT_ENERGY_WEIGHT + output_tokens

    energy_wh = effective_tokens * wh_per_token * pue
    co2_grams = (energy_wh * carbon_intensity_kg_kwh) / 1000.0
    co2_low, co2_high = uncertainty_bounds(co2_grams)

    return {
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "total_tokens":  input_tokens + output_tokens,
        "pue":           pue,
        "energy_wh":     energy_wh,
        "co2_grams":     co2_grams,
        "co2_grams_low":  co2_low,
        "co2_grams_high": co2_high,
    }
