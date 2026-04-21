"""Assemble the full Shark Tank pitch deck as a .pptx file.

Builds 6 slides in 16:9 widescreen. All visual assets are pre-generated PNGs.
Slide 1 (title) and Slide 6 (thank-you) use PowerPoint text boxes so you can
edit team names / contact info directly in PowerPoint after generation.

Run: python build_pitch_deck.py
Output: pitch_deck_jefferson_ems.pptx
"""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

ROOT = Path(__file__).parent

# ---- Colors ----
NAVY    = RGBColor(0x11, 0x11, 0x11)
RED     = RGBColor(0xB2, 0x22, 0x22)
BLUE    = RGBColor(0x2C, 0x7F, 0xB8)
GRAY    = RGBColor(0x55, 0x55, 0x55)
LIGHT   = RGBColor(0x77, 0x77, 0x77)
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)

# ---- Canvas: 16:9 widescreen, 13.333" x 7.5" ----
prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
SLIDE_W = prs.slide_width
SLIDE_H = prs.slide_height

BLANK_LAYOUT = prs.slide_layouts[6]  # blank


def add_textbox(slide, left, top, width, height, text, *,
                size=18, bold=False, italic=False,
                color=NAVY, align=PP_ALIGN.LEFT, font="Calibri"):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    # First paragraph is already there
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = font
    return tb


def add_footer(slide, text):
    add_textbox(slide, Inches(0.4), Inches(7.15), Inches(12.5), Inches(0.3),
                text, size=9, italic=True, color=LIGHT, align=PP_ALIGN.CENTER)


def add_full_image(slide, image_path, *, pad_top=0.3, pad_side=0.3,
                   pad_bottom=0.5):
    """Place an image centered in the slide, fitting to slide dims."""
    slide.shapes.add_picture(
        str(image_path),
        Inches(pad_side), Inches(pad_top),
        width=SLIDE_W - Inches(2 * pad_side),
        height=SLIDE_H - Inches(pad_top + pad_bottom),
    )


# =====================================================================
# SLIDE 1 — The Hook (Title + team)
# =====================================================================
s1 = prs.slides.add_slide(BLANK_LAYOUT)

# Anchor map fills most of the slide
s1.shapes.add_picture(
    str(ROOT / "pitch_slide1_anchor_map.png"),
    Inches(0.25), Inches(1.0),
    width=Inches(12.8), height=Inches(6.0),
)

# Team line over the top
add_textbox(s1, Inches(0.5), Inches(0.2), Inches(12.3), Inches(0.6),
            "ISyE 450 Capstone  |  Team: [Your names here]",
            size=20, bold=True, color=NAVY, align=PP_ALIGN.LEFT)

# Footer — data provenance
add_footer(s1,
           "Data: CY2024 NFIRS (n=8,396 EMS calls, Jefferson geography) · "
           "P-Median + ORS road-network isochrones")


# =====================================================================
# SLIDE 2 — The Bottleneck
# =====================================================================
s2 = prs.slides.add_slide(BLANK_LAYOUT)

add_textbox(s2, Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.7),
            "The Bottleneck: 12 Half-Empty Systems",
            size=32, bold=True, color=NAVY, align=PP_ALIGN.LEFT)

add_textbox(s2, Inches(0.5), Inches(0.95), Inches(12.3), Inches(0.5),
            "Each of Jefferson County's 12 departments funds its own backup ambulance — "
            "used 10-15% of the time, yet still leaving 41 coverage gaps per year.",
            size=15, italic=True, color=GRAY, align=PP_ALIGN.LEFT)

# Use the existing concurrent-demand chart
s2.shapes.add_picture(
    str(ROOT / "secondary_demand_by_dept_jeffco.png"),
    Inches(0.5), Inches(1.6),
    width=Inches(8.5), height=Inches(5.3),
)

# Right-side callout box
add_textbox(s2, Inches(9.3), Inches(1.9), Inches(3.7), Inches(0.5),
            "THE KEY NUMBERS",
            size=14, bold=True, color=RED, align=PP_ALIGN.LEFT)

add_textbox(s2, Inches(9.3), Inches(2.4), Inches(3.7), Inches(4.0),
            "21  all-busy events/yr\n     in Ixonia alone\n"
            "     (≈ once every 2.5 weeks)\n\n"
            "12  all-busy events/yr\n     in Waterloo\n\n"
            "41  total countywide\n     where NO ambulance\n     was available\n\n"
            "— Every one of these calls\nwaits for mutual aid from\nanother county.",
            size=14, bold=False, color=GRAY, align=PP_ALIGN.LEFT)

add_footer(s2, "Source: CY2024 NFIRS concurrent-call analysis · "
               "Jefferson County geography only")


# =====================================================================
# SLIDE 3 — The IE Intervention
# =====================================================================
s3 = prs.slides.add_slide(BLANK_LAYOUT)
add_full_image(s3, ROOT / "pitch_slide3_concept.png",
               pad_top=0.25, pad_side=0.3, pad_bottom=0.35)
add_footer(s3, "Methodology: P-Median (facility location) + Erlang-C (queuing) + "
               "OpenRouteService (road-network drive times)")


# =====================================================================
# SLIDE 4 — The Data Evidence (Before/After)
# =====================================================================
s4 = prs.slides.add_slide(BLANK_LAYOUT)
add_full_image(s4, ROOT / "pitch_slide4_before_after.png",
               pad_top=0.25, pad_side=0.3, pad_bottom=0.35)
add_footer(s4, "Before: K=2 MCLP T=10 proxy for current patchwork mutual-aid · "
               "After: K=4 P-Median optimization on total demand")


# =====================================================================
# SLIDE 5 — The Bottom Line
# =====================================================================
s5 = prs.slides.add_slide(BLANK_LAYOUT)
add_full_image(s5, ROOT / "pitch_slide5_bottomline.png",
               pad_top=0.25, pad_side=0.3, pad_bottom=0.35)
add_footer(s5, "All figures framed as patient-outcome deltas. "
               "Financial model available on request (cost-neutral at hybrid staffing).")


# =====================================================================
# SLIDE 6 — Thank You + Call to Action
# =====================================================================
s6 = prs.slides.add_slide(BLANK_LAYOUT)

# Big "Thank You"
add_textbox(s6, Inches(0.5), Inches(1.3), Inches(12.3), Inches(1.5),
            "Thank You.",
            size=72, bold=True, color=NAVY, align=PP_ALIGN.CENTER)

# Call to action
add_textbox(s6, Inches(1.5), Inches(2.9), Inches(10.3), Inches(1.0),
            "We're asking for feedback and partnership as the Jefferson County "
            "EMS Working Group moves into implementation.",
            size=20, italic=True, color=BLUE, align=PP_ALIGN.CENTER)

# Team block (placeholder — edit in PPT)
add_textbox(s6, Inches(1.5), Inches(4.4), Inches(10.3), Inches(0.5),
            "ISyE 450 Capstone Team",
            size=16, bold=True, color=NAVY, align=PP_ALIGN.CENTER)

add_textbox(s6, Inches(1.5), Inches(4.9), Inches(10.3), Inches(0.6),
            "[Team member 1]    [Team member 2]    [Team member 3]    [Team member 4]",
            size=14, color=GRAY, align=PP_ALIGN.CENTER)

add_textbox(s6, Inches(1.5), Inches(5.6), Inches(10.3), Inches(0.5),
            "Questions? We have backup slides on sensitivity, staffing scenarios, "
            "and dispatch protocols.",
            size=13, italic=True, color=LIGHT, align=PP_ALIGN.CENTER)

add_footer(s6, "University of Wisconsin–Madison · ISyE 450 · April 2026")


# ---- Save ----
out = ROOT / "pitch_deck_jefferson_ems.pptx"
prs.save(str(out))
print(f"Saved: {out}")
print(f"Slides: {len(prs.slides)}")
