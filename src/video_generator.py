"""Video generation using Google Veo via Gemini API.

Generates cinematic protein structure videos from screenshots
of the Mol* 3D viewer using image-to-video generation.
"""
from __future__ import annotations

import base64
import time

from google import genai
from google.genai import types

from src.config import GEMINI_API_KEY

# Default prompts for different video styles
VIDEO_PROMPTS = {
    "rotate": (
        "Slowly rotating 3D protein molecular structure visualization, "
        "smooth 360-degree rotation, dark background, scientific visualization, "
        "high quality, cinematic lighting, depth of field"
    ),
    "zoom": (
        "Smooth camera zoom into the active site of a 3D protein structure, "
        "revealing molecular detail, scientific visualization, "
        "cinematic depth of field, dark background"
    ),
    "morph": (
        "Subtle conformational breathing motion of a protein structure, "
        "gentle pulsing of molecular bonds, scientific visualization, "
        "dark background, cinematic lighting"
    ),
    "highlight": (
        "Camera slowly orbiting a 3D protein structure with glowing highlighted "
        "regions fading in and out, scientific visualization, "
        "cinematic quality, dark background"
    ),
}


def generate_protein_video(
    image_bytes: bytes,
    prompt: str | None = None,
    style: str = "rotate",
) -> bytes:
    """Generate a video from a protein structure screenshot.

    Args:
        image_bytes: PNG/JPEG screenshot of the Mol* viewer.
        prompt: Custom prompt override. If None, uses style preset.
        style: One of "rotate", "zoom", "morph", "highlight".

    Returns:
        Video file bytes (MP4).

    Raises:
        RuntimeError: If generation fails or API key missing.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Add it to your .env file."
        )

    client = genai.Client(api_key=GEMINI_API_KEY)

    final_prompt = prompt or VIDEO_PROMPTS.get(style, VIDEO_PROMPTS["rotate"])

    # Create image part from bytes
    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type="image/png",
    )

    # Generate video using Veo
    operation = client.models.generate_videos(
        model="veo-2.0-generate-001",
        prompt=final_prompt,
        image=image_part,
    )

    # Poll until complete (max ~5 minutes)
    max_wait = 300
    start = time.time()
    while not operation.done:
        if time.time() - start > max_wait:
            raise RuntimeError(
                "Video generation timed out after 5 minutes. "
                "Try again or use a simpler prompt."
            )
        time.sleep(5)
        operation = client.operations.get(operation)

    # Extract video bytes
    if not operation.result or not operation.result.generated_videos:
        raise RuntimeError(
            "Video generation completed but returned no video. "
            "The model may have rejected the input image."
        )

    video = operation.result.generated_videos[0]
    video_data = client.files.download(file=video.video)

    # Collect all chunks
    chunks = []
    for chunk in video_data:
        chunks.append(chunk)
    return b"".join(chunks)


def generate_protein_video_text_only(
    prompt: str,
) -> bytes:
    """Generate a video from text prompt only (no input image).

    Args:
        prompt: Description of the desired protein animation.

    Returns:
        Video file bytes (MP4).
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set.")

    client = genai.Client(api_key=GEMINI_API_KEY)

    operation = client.models.generate_videos(
        model="veo-2.0-generate-001",
        prompt=prompt,
    )

    max_wait = 300
    start = time.time()
    while not operation.done:
        if time.time() - start > max_wait:
            raise RuntimeError("Video generation timed out.")
        time.sleep(5)
        operation = client.operations.get(operation)

    if not operation.result or not operation.result.generated_videos:
        raise RuntimeError("No video generated.")

    video = operation.result.generated_videos[0]
    video_data = client.files.download(file=video.video)
    chunks = []
    for chunk in video_data:
        chunks.append(chunk)
    return b"".join(chunks)
