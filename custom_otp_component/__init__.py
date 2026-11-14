
from pathlib import Path
import streamlit.components.v1 as components

_component = components.declare_component(
    "makkal_kural_six_digit_otp",
    path=str(Path(__file__).parent / "frontend"),
)


def otp_input(disabled=False, key=None):
    """Display the six-digit OTP component."""
    return _component(
        disabled=disabled,
        default=None,
        key=key,
    )
