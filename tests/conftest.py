import os
import sys

# Make the component's modules importable as top-level (auth, api) without HA.
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "miele_wine")
)
