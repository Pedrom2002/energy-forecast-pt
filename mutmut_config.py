"""
mutmut configuration for energy-forecast-pt.

This file controls which source files are mutated and how the test suite
is executed during mutation testing.
"""


def pre_mutation(context):
    """Called before each mutation. Skip files we don't want to mutate."""
    # Only mutate core modules that have meaningful logic worth testing
    allowed_modules = [
        "src/utils/metrics.py",
        "src/features/feature_engineering.py",
        "src/models/model_registry.py",
        "src/models/feature_selection.py",
        "src/models/evaluation.py",
    ]

    if context.filename not in allowed_modules:
        context.skip = True


def pre_test_suite(context):
    """Called before the test suite runs for each mutant."""
    # Set a per-test-suite timeout (seconds) to kill hung mutants quickly
    context.config.test_time_multiplier = 2.0
    context.config.test_time_base = 30.0
