"""VisionBackend protocol: pluggable interface for vision LLM calls.

Usage:
    from shared.vision_backend import VisionBackend, create_vision_backend

    backend = create_vision_backend(mode="stepwise", work_dir="/tmp/weclaw_work")
    response = backend.query(prompt, image, max_tokens=2048)

Two implementations:
    - OpenRouterBackend: calls OpenRouter API directly (legacy, requires API key).
    - StepwiseBackend: writes image+prompt to work_dir, reads response from agent.
"""

from typing import Protocol, runtime_checkable

from PIL import Image


@runtime_checkable
class VisionBackend(Protocol):

    def query(self, prompt: str, image: Image.Image, max_tokens: int = 2048) -> str | None:
        """Send a vision prompt + image, return model response text or None."""
        ...


def create_vision_backend(mode: str = "openrouter", **kwargs) -> VisionBackend:
    """Factory: create the appropriate backend based on mode.

    mode="openrouter": uses shared.vision_ai.VisionAI (requires API key).
    mode="stepwise": uses StepwiseBackend (writes to work_dir, no LLM call).
    """
    if mode == "openrouter":
        from shared.vision_ai import VisionAI
        return VisionAI()
    if mode == "stepwise":
        from shared.stepwise_backend import StepwiseBackend
        work_dir = kwargs.get("work_dir")
        assert work_dir, "work_dir is required for stepwise mode"
        return StepwiseBackend(work_dir)
    raise ValueError(f"Unknown vision backend mode: {mode}")
