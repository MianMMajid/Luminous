"""Video generation panel — creates cinematic protein animations using Gemini Veo.

Captures the current Mol* viewer state (via user-uploaded screenshot) and
generates a short scientific animation video. Runs in background via task_manager.
"""
from __future__ import annotations

import streamlit as st

from src.video_generator import VIDEO_PROMPTS


def render_video_panel():
    """Render video generation controls and preview."""
    query = st.session_state.get("parsed_query")
    prediction = st.session_state.get("prediction_result")

    if not query or not prediction:
        st.info("Load a structure first to generate a video.")
        return

    st.markdown("### Protein Animation")
    st.caption(
        "Generate a cinematic video of your protein structure using Google Veo. "
        "Upload a screenshot of the 3D viewer or use a text prompt."
    )

    # Check if Gemini API key is configured
    from src.config import GEMINI_API_KEY

    if not GEMINI_API_KEY:
        st.warning(
            "Gemini API key not configured. Add `GEMINI_API_KEY` to your `.env` file."
        )
        return

    # Check if generation is running
    from src.task_manager import task_manager

    video_status = task_manager.status("video_generation")
    if video_status and video_status.value == "running":
        st.markdown(
            '<div class="glow-card" style="text-align:center;padding:24px">'
            '<div style="font-size:1.3rem;margin-bottom:8px">Generating video...</div>'
            '<div style="color:rgba(60,60,67,0.6);font-size:0.88rem">'
            'This takes 1–3 minutes. Feel free to explore other tabs — '
            'Lumi will notify you when it\'s ready.</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # Input mode tabs
    mode = st.radio(
        "Input mode",
        ["Screenshot → Video", "Text prompt only"],
        horizontal=True,
        key="video_input_mode",
    )

    image_bytes = None
    if mode == "Screenshot → Video":
        uploaded = st.file_uploader(
            "Upload a screenshot of the 3D viewer",
            type=["png", "jpg", "jpeg"],
            key="video_screenshot",
            help="Take a screenshot of the Mol* viewer and upload it here. "
            "The AI will animate it into a short video.",
        )
        if uploaded:
            image_bytes = uploaded.getvalue()
            st.image(image_bytes, caption="Input screenshot", use_container_width=True)

    # Style selection
    style_col, prompt_col = st.columns([1, 2])
    with style_col:
        style = st.selectbox(
            "Animation style",
            list(VIDEO_PROMPTS.keys()),
            format_func=lambda x: {
                "rotate": "Slow rotation",
                "zoom": "Zoom to active site",
                "morph": "Breathing motion",
                "highlight": "Region highlights",
            }[x],
            key="video_style",
        )

    with prompt_col:
        custom_prompt = st.text_area(
            "Custom prompt (optional)",
            placeholder=f"Default: {VIDEO_PROMPTS[style][:80]}...",
            height=80,
            key="video_custom_prompt",
        )

    # Generate button
    mut_str = f" {query.mutation}" if query.mutation else ""
    can_generate = mode == "Text prompt only" or image_bytes is not None

    if st.button(
        "Generate Video",
        type="primary",
        disabled=not can_generate,
        use_container_width=True,
        key="btn_generate_video",
    ):
        prompt = custom_prompt.strip() if custom_prompt.strip() else None
        text_only = mode == "Text prompt only"

        # If text-only and no custom prompt, build one from the query
        if text_only and not prompt:
            prompt = (
                f"Slowly rotating 3D protein structure of {query.protein_name}{mut_str}, "
                f"scientific molecular visualization, ribbon diagram, "
                f"cinematic lighting, dark background, high quality"
            )

        _submit_video_background(
            image_bytes=image_bytes,
            prompt=prompt,
            style=style,
            text_only=text_only,
        )
        st.info("Video generation submitted — Lumi will notify you when it's ready.")

    # Display generated video
    video_bytes = st.session_state.get("generated_video")
    if video_bytes:
        st.divider()
        st.markdown("### Generated Video")
        st.video(video_bytes, format="video/mp4")

        # Download button
        mut_safe = query.mutation.replace(" ", "_") if query.mutation else "wt"
        filename = f"{query.protein_name}_{mut_safe}_animation.mp4"
        st.download_button(
            "Download MP4",
            data=video_bytes,
            file_name=filename,
            mime="video/mp4",
            use_container_width=True,
            key="dl_video",
        )


def _submit_video_background(
    image_bytes: bytes | None,
    prompt: str | None,
    style: str,
    text_only: bool,
):
    """Submit video generation as a background task."""
    from src.background_tasks import generate_video_background
    from src.task_manager import task_manager

    task_manager.submit(
        task_id="video_generation",
        fn=generate_video_background,
        kwargs={
            "image_bytes": image_bytes,
            "prompt": prompt,
            "style": style,
            "text_only": text_only,
        },
        label="Protein video (Gemini Veo)",
    )
