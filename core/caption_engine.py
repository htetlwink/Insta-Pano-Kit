"""
Smart Caption & Hashtag Generation Engine for Instagram Panoramas and Carousels.
==============================================================================
Generates engaging, algorithm-optimized Instagram captions in multiple styles:
- Aesthetic / Storytelling with swipe cues
- Technical Photography breakdown (EXIF details)
- Engagement hook question
- High-reach curated hashtags
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
from PIL import Image

from core.image_engine import extract_exif_metadata


# Preset caption storytelling copy organized by visual theme
THEME_AESTHETIC_TEMPLATES: Dict[str, str] = {
    "General": (
        "Some moments are simply too expansive for a single frame. 🌌✨ "
        "Every angle holds a piece of the story waiting to unfold.\n\n"
        "Swipe across ➔ (all {num_slices} slides) to experience the full panoramic view."
    ),
    "Landscape": (
        "Where the sky whispers to the earth and horizons stretch beyond the edge of imagination. 🏔️🌿 "
        "A wide-open breath in an ever-rushing world.\n\n"
        "Swipe across ➔ (all {num_slices} slides) to take in the entire vista."
    ),
    "Urban / Architecture": (
        "Lines, light, and soaring silhouettes. The geometry of human ambition framed from edge to edge. 🏙️📐 "
        "Finding rhythm in the urban pulse.\n\n"
        "Swipe through ➔ (all {num_slices} slides) to walk through the skyline."
    ),
    "Minimalist": (
        "Space to breathe. The quiet harmony between stillness and light. 🕊️☁️ "
        "Less noise, more horizon.\n\n"
        "Swipe across ➔ (all {num_slices} slides) for the continuous calm."
    ),
    "Cinematic": (
        "A widescreen scene suspended between memory and motion picture. 🎬🎞️ "
        "Every frame cut with intention, every transition seamless.\n\n"
        "Swipe right ➔ (all {num_slices} slides) to view the panoramic sequence."
    ),
    "Travel / Adventure": (
        "Wanderlust led me here, but the stillness made me stay. 🧭🎒 "
        "Documenting the places that make us feel gloriously small.\n\n"
        "Swipe across ➔ (all {num_slices} slides) to join the journey."
    ),
    "Sunset / Golden Hour": (
        "Chasing amber light before twilight claims the sky. 🌅✨ "
        "The golden hour paints differently when you can see the whole horizon.\n\n"
        "Swipe through ➔ (all {num_slices} slides) for the sunset spectrum."
    ),
}

# Engagement questions organized by theme
THEME_ENGAGEMENT_TEMPLATES: Dict[str, str] = {
    "General": "Which slide draws you in most: Slide 1 or Slide {num_slices}? Drop your number below! 👇",
    "Landscape": "Would you rather wake up to sunrise here or watch twilight fall? 1, 2, or {num_slices}? Let me know below! 👇",
    "Urban / Architecture": "Which perspective feels more powerful to you: the lead slide or the final reveal? Drop your pick below! 👇",
    "Minimalist": "Does your gaze linger on the empty space or the focal point? Tell me in the comments! 👇",
    "Cinematic": "If this was an opening shot of a film, what genre would it be? 🎬 Let me know your guess below!",
    "Travel / Adventure": "Tag someone you'd explore this panoramic landscape with! ✈️ Where is your next adventure?",
    "Sunset / Golden Hour": "Golden hour or blue hour? Which slide captures the light best for you? 👇",
}

# Hashtags curated for maximum reach
THEME_HASHTAGS: Dict[str, str] = {
    "General": (
        "#panoramaphotography #seamlesscarousel #instapanorama #wideanglelens "
        "#panoramic #carouselpost #visualsofearth #artofvisuals #exploretocreate "
        "#photooftheday #wanderlust #creatorgrams"
    ),
    "Landscape": (
        "#landscapephotography #earthpix #visualsofearth #landscapelovers "
        "#roamtheplanet #wildernessculture #natureperfection #panoramaphotography "
        "#instapanorama #seamlesscarousel #optoutside #ourplanetdaily"
    ),
    "Urban / Architecture": (
        "#urbanphotography #architecturelovers #cityscape #streetphotography "
        "#architecturephotography #urbanandstreet #citykillerz #panoramaphotography "
        "#skylinephotography #seamlesscarousel #agameoftones"
    ),
    "Minimalist": (
        "#minimalism #minimalmood #simplicity #cleanlines #quietmoments "
        "#negative_space #minimalzine #panoramaphotography #seamlesscarousel "
        "#visualpoetry #subtletones"
    ),
    "Cinematic": (
        "#cinematicphotography #filmgrain #cinematictones #moodygrams "
        "#storyteller #widescreen #filmmaking #panoramaphotography "
        "#seamlesscarousel #cinemaaesthetic #framing"
    ),
    "Travel / Adventure": (
        "#travelphotography #stayandwander #roamtheplanet #travelgram "
        "#adventureawaits #theglobewanderer #exploringtheglobe #panoramaphotography "
        "#seamlesscarousel #passionpassport #travelinspo"
    ),
    "Sunset / Golden Hour": (
        "#goldenhour #sunsetphotography #sunsetlovers #sky_perfection "
        "#twilightscapes #goldenhourlight #panoramaphotography #seamlesscarousel "
        "#warmtones #sunsetchaser #magiclight"
    ),
}


def generate_smart_captions(
    image_path: Optional[Union[str, Path]] = None,
    pil_image: Optional[Image.Image] = None,
    exif_data: Optional[Dict[str, str]] = None,
    num_slices: int = 3,
    theme: str = "General",
) -> Dict[str, str]:
    """
    Generate Instagram captions and hashtags for seamless panoramic carousels.

    Args:
        image_path: Optional path to image file.
        pil_image: Optional PIL Image instance.
        exif_data: Optional pre-extracted EXIF metadata dictionary.
        num_slices: Number of slides in the carousel (for swipe cue & engagement).
        theme: Theme name (e.g. 'General', 'Landscape', 'Urban / Architecture', 'Minimalist', 'Cinematic').

    Returns:
        Dictionary with keys:
            - 'aesthetic': Poetic & wanderlust storytelling caption with emojis and swipe cue.
            - 'technical': Full photography breakdown (Shot on ... | ...mm | f/... | 1/...s | ISO ...).
            - 'engagement': Algorithm-optimized engagement hook question.
            - 'hashtags': Curated list of high-reach hashtags.
    """
    # 1. Resolve or extract EXIF metadata
    meta = exif_data or {}
    if not meta and (image_path is not None or pil_image is not None):
        try:
            source = image_path if image_path is not None else pil_image
            meta = extract_exif_metadata(source)
        except Exception:
            meta = {}

    camera = meta.get("camera") or "Wide Lens Camera"
    focal_length = meta.get("focal_length") or "24mm"
    aperture = meta.get("aperture") or "f/8.0"
    shutter_speed = meta.get("shutter_speed") or "1/250s"
    iso = meta.get("iso") or "100"

    # Normalize theme
    norm_theme = "General"
    for t_key in THEME_AESTHETIC_TEMPLATES.keys():
        if t_key.lower() == theme.strip().lower() or t_key.lower().split()[0] in theme.lower():
            norm_theme = t_key
            break

    # 2. Build Aesthetic Caption
    aesthetic_template = THEME_AESTHETIC_TEMPLATES.get(norm_theme, THEME_AESTHETIC_TEMPLATES["General"])
    aesthetic = aesthetic_template.format(num_slices=num_slices)

    # 3. Build Technical Breakdown
    technical = (
        f"📸 Shot on {camera} | {focal_length} | {aperture} | {shutter_speed} | ISO {iso}\n"
        f"📐 Panorama Split: {num_slices}-slide seamless carousel\n"
        f"✨ Processed with Insta-Pano-Kit"
    )

    # 4. Build Engagement Hook
    engagement_template = THEME_ENGAGEMENT_TEMPLATES.get(norm_theme, THEME_ENGAGEMENT_TEMPLATES["General"])
    engagement = engagement_template.format(num_slices=num_slices)

    # 5. Build Curated Hashtags
    hashtags = THEME_HASHTAGS.get(norm_theme, THEME_HASHTAGS["General"])

    return {
        "aesthetic": aesthetic,
        "technical": technical,
        "engagement": engagement,
        "hashtags": hashtags,
    }


def format_full_caption(captions: Dict[str, str]) -> str:
    """Format dictionary of captions into a ready-to-paste Instagram post string."""
    aesthetic = captions.get("aesthetic", "")
    engagement = captions.get("engagement", "")
    technical = captions.get("technical", "")
    hashtags = captions.get("hashtags", "")

    parts = []
    if aesthetic:
        parts.append(aesthetic)
    if engagement:
        parts.append(engagement)
    if technical:
        parts.append(f"---\n{technical}")
    if hashtags:
        parts.append(f".\n.\n.\n{hashtags}")

    return "\n\n".join(parts)
