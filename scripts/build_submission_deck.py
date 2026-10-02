"""Build the six-slide TRIDENT OPS deck from the official hackathon template."""

from __future__ import annotations

import argparse
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

TEAM_URL = (
    "https://hack2skill.com/event/cococlihack-gccedition/dashboard/"
    "team-management?utm_source=hack2skill&utm_medium=homepage"
)
LEADER_URL = "https://www.linkedin.com/in/jangam-ashok-53a95812b/"
APP_URL = "https://app.snowflake.com/streamlit/FMXJOWH/BRC04642/#/apps/bd2ocwt4eblddojvzl7v"
REPO_URL = "https://github.com/ashokjangam/snowcore-pdm/tree/feat/tridents-ops"

WHITE = "F4FAFD"
MUTED = "A5B7C3"
CYAN = "36A9E1"
TEAL = "31D7C5"
AMBER = "F2B84B"
RED = "EF6A72"
BLUE = "0A5CA8"
DARK = "0C1822"
PANEL = "122431"
GRID = "29404E"


def rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def remove_non_picture_shapes(slide) -> None:
    for shape in list(slide.shapes):
        if shape.shape_type != 13:  # PICTURE
            shape._element.getparent().remove(shape._element)


def add_text(
    slide,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    size: int = 15,
    color: str = WHITE,
    bold: bool = False,
    font: str = "Calibri",
    align=PP_ALIGN.LEFT,
    valign=MSO_ANCHOR.TOP,
    margin: float = 0.03,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    box.text_frame.clear()
    box.text_frame.margin_left = Inches(margin)
    box.text_frame.margin_right = Inches(margin)
    box.text_frame.margin_top = Inches(margin)
    box.text_frame.margin_bottom = Inches(margin)
    box.text_frame.vertical_anchor = valign
    box.text_frame.word_wrap = True
    paragraph = box.text_frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = rgb(color)
    return box


def add_rich_text(slide, runs, x, y, w, h, *, size=15, color=WHITE, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.margin_left = frame.margin_right = Inches(0.03)
    frame.margin_top = frame.margin_bottom = Inches(0.02)
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    for spec in runs:
        run = paragraph.add_run()
        run.text = spec["text"]
        run.font.name = spec.get("font", "Calibri")
        run.font.size = Pt(spec.get("size", size))
        run.font.bold = spec.get("bold", False)
        run.font.color.rgb = rgb(spec.get("color", color))
        if spec.get("url"):
            run.hyperlink.address = spec["url"]
    return box


def add_title(slide, title: str, kicker: str) -> None:
    add_text(slide, kicker.upper(), 0.48, 0.50, 5.4, 0.22, size=9, color=TEAL, bold=True)
    add_text(slide, title, 0.46, 0.76, 8.9, 0.55, size=27, color=DARK, bold=True, font="Cambria")


def add_footer(slide, text: str) -> None:
    add_text(slide, text, 0.48, 5.31, 9.0, 0.17, size=7, color="667D8C")


def shape_box(slide, x, y, w, h, fill, *, radius=True, line=GRID):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    shape.line.color.rgb = rgb(line)
    shape.line.width = Pt(1)
    return shape


def circle(slide, x, y, diameter, fill, line=GRID):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(diameter), Inches(diameter))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    shape.line.color.rgb = rgb(line)
    shape.line.width = Pt(1.4)
    return shape


def arrow(slide, x, y, w=0.36, h=0.24, color=CYAN):
    shape = slide.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    shape.line.fill.background()
    return shape


def stat(slide, value, label, note, x, y, w, tone=TEAL):
    shape_box(slide, x, y, w, 1.45, PANEL)
    add_text(slide, value, x + 0.16, y + 0.12, w - 0.32, 0.42, size=26, color=tone, bold=True)
    add_text(slide, label, x + 0.16, y + 0.59, w - 0.32, 0.24, size=11, color=WHITE, bold=True)
    add_text(slide, note, x + 0.16, y + 0.88, w - 0.32, 0.42, size=9, color=MUTED)


def fill_title_slide(slide) -> None:
    remove_non_picture_shapes(slide)
    add_text(slide, "TRIDENT OPS", 6.72, 3.28, 2.78, 0.48, size=29, color=BLUE, bold=True, font="Cambria")
    add_text(slide, "EVIDENCE-FIRST PREDICTIVE MAINTENANCE + OEE", 6.73, 3.78, 2.74, 0.48, size=10, color=DARK, bold=True)
    add_rich_text(
        slide,
        [
            {"text": "Team Name: ", "bold": True, "color": DARK},
            {"text": "TRidents", "bold": True, "color": BLUE, "url": TEAM_URL},
        ],
        0.48, 3.44, 5.6, 0.28, size=13, color=DARK,
    )
    add_rich_text(
        slide,
        [
            {"text": "Team Leader: ", "bold": True, "color": DARK},
            {"text": "Ashok Jangam", "bold": True, "color": BLUE, "url": LEADER_URL},
        ],
        0.48, 3.82, 5.6, 0.28, size=13, color=DARK,
    )
    add_text(slide, "Team Size: 4", 0.48, 4.20, 5.6, 0.28, size=13, color=DARK, bold=True)
    add_text(
        slide,
        "Problem Statement: Predictive Maintenance and OEE Command Center",
        0.48, 4.58, 8.95, 0.30, size=13, color=DARK, bold=True,
    )
    add_text(slide, "Two evidence lanes. One auditable decision path. Zero fabricated joins.",
             0.48, 5.05, 8.95, 0.26, size=11, color=BLUE, bold=True, align=PP_ALIGN.CENTER)


def fill_problem_slide(slide) -> None:
    remove_non_picture_shapes(slide)
    add_title(slide, "The gap isn't a model. It's a missing thread.", "01 · Problem brief")
    circle(slide, 0.65, 1.55, 2.25, "102C3A", TEAL)
    add_text(slide, "PIADE", 1.17, 1.88, 1.2, 0.34, size=22, color=TEAL, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "Real line states\nalarms + package counts\nweighted OEE", 0.94, 2.30, 1.68, 0.84,
             size=11, color=WHITE, align=PP_ALIGN.CENTER)
    circle(slide, 7.08, 1.55, 2.25, "2E2513", AMBER)
    add_text(slide, "MetroPT", 7.48, 1.88, 1.45, 0.34, size=22, color=AMBER, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "Real compressor sensors\n+ failure windows\nno production counts", 7.34, 2.30, 1.75, 0.84,
             size=11, color=WHITE, align=PP_ALIGN.CENTER)
    shape_box(slide, 3.48, 1.76, 3.05, 1.78, "1A1D22", radius=False, line=RED)
    add_text(slide, "NO-JOIN\nFIREWALL", 4.05, 2.03, 1.9, 0.68, size=21, color=RED, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "different plants · no shared key", 3.83, 2.86, 2.35, 0.24, size=9, color=MUTED, align=PP_ALIGN.CENTER)
    add_text(slide, "The honest product", 0.75, 4.08, 1.8, 0.25, size=11, color=TEAL, bold=True)
    add_text(
        slide,
        "PIADE drives OEE, ownership and next-hour ranking. MetroPT remains a separate sensor-evidence lane labelled detection—not forecast.",
        2.30, 3.96, 7.05, 0.66, size=16, color=DARK, bold=True,
    )
    add_footer(slide, "Sources: PIADE DOI 10.5281/zenodo.7071747 · MetroPT-3 DOI 10.24432/C5VW3R · both public")


def fill_architecture_slide(slide) -> None:
    remove_non_picture_shapes(slide)
    add_title(slide, "One console. Two databases. Three working tines.", "02 · Architecture")
    shape_box(slide, 0.52, 1.50, 1.65, 1.12, "102C3A")
    add_text(slide, "PIADE CSV", 0.75, 1.72, 1.2, 0.25, size=14, color=TEAL, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "states · alarms · counts", 0.69, 2.09, 1.32, 0.22, size=8, color=MUTED, align=PP_ALIGN.CENTER)
    arrow(slide, 2.30, 1.94)
    shape_box(slide, 2.82, 1.36, 2.15, 1.42, "122431")
    add_text(slide, "SNOWCORE_REAL", 3.05, 1.62, 1.68, 0.26, size=14, color=CYAN, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "BRONZE → SILVER → GOLD → ML", 3.03, 2.03, 1.75, 0.35, size=8, color=MUTED, align=PP_ALIGN.CENTER)
    shape_box(slide, 0.52, 3.42, 1.65, 1.12, "2E2513")
    add_text(slide, "MetroPT", 0.75, 3.66, 1.2, 0.25, size=14, color=AMBER, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "pressure · current · load", 0.69, 4.03, 1.32, 0.22, size=8, color=MUTED, align=PP_ALIGN.CENTER)
    arrow(slide, 2.30, 3.86, color=AMBER)
    shape_box(slide, 2.82, 3.28, 2.15, 1.42, "282316")
    add_text(slide, "PNEUMORA", 3.05, 3.54, 1.68, 0.26, size=14, color=AMBER, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "CORE → ML → evidence", 3.03, 3.95, 1.75, 0.35, size=8, color=MUTED, align=PP_ALIGN.CENTER)
    arrow(slide, 5.16, 2.38, 0.42, 0.26)
    arrow(slide, 5.16, 3.28, 0.42, 0.26, AMBER)
    shape_box(slide, 5.76, 1.46, 3.68, 3.02, "0E2029", line=TEAL)
    add_text(slide, "TRIDENT OPS", 6.00, 1.70, 3.20, 0.33, size=22, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    for x, label, note, tone in [
        (6.02, "COMPUTE", "OEE + baseline", CYAN),
        (7.10, "EXPLAIN", "bounded Cortex", TEAL),
        (8.18, "ACT", "idempotent row", AMBER),
    ]:
        circle(slide, x, 2.42, 0.88, PANEL, tone)
        add_text(slide, label, x + 0.03, 2.68, 0.82, 0.16, size=8, color=tone, bold=True, align=PP_ALIGN.CENTER)
        add_text(slide, note, x - 0.06, 3.42, 1.00, 0.30, size=8, color=MUTED, align=PP_ALIGN.CENTER)
    add_text(slide, "TRIDENT_OPS.OPS.TRIAGE_ACTION", 6.10, 4.05, 3.00, 0.20,
             size=8, color=TEAL, bold=True, align=PP_ALIGN.CENTER)
    add_footer(slide, "Snowflake: warehouse Streamlit · Snowpark SQL procedures · AI_COMPLETE · governed views")


def fill_evidence_slide(slide) -> None:
    remove_non_picture_shapes(slide)
    add_title(slide, "Evidence before ego", "03 · Measured impact")
    stat(slide, "46.78%", "PIADE weighted OEE", "A 64.32% × P 72.93% × Q 99.72%", 0.55, 1.48, 2.75, TEAL)
    stat(slide, "76.4%", "Blind top-decile precision", "Persistence baseline 62.4%; archived Dec-2021 holdout", 3.62, 1.48, 2.75, CYAN)
    stat(slide, "+72 / +86", "MetroPT external timing", "minutes after leak onset · NO PROMOTION", 6.69, 1.48, 2.75, AMBER)
    add_text(slide, "What changed because of the model?", 0.62, 3.27, 3.10, 0.28, size=13, color=DARK, bold=True)
    add_text(slide, "Not yet measured. OEE lift and realised savings require intervention data.", 0.62, 3.66, 2.80, 0.82, size=11, color=RED, bold=True)
    add_text(slide, "What did automation prove?", 3.62, 3.27, 2.76, 0.28, size=13, color=DARK, bold=True)
    add_text(slide, "45 replay orders · 35.6% hit rate · 1.26× random timing · 23% coverage", 3.62, 3.66, 2.76, 0.82, size=11, color="B07400", bold=True)
    add_text(slide, "What did search teach us?", 6.70, 3.27, 2.68, 0.28, size=13, color=DARK, bold=True)
    add_text(slide, "25 trials improved validation AUC by 0.0001. Missing signal—not another model—is the ceiling.", 6.70, 3.66, 2.68, 0.82, size=11, color="087F72", bold=True)
    add_footer(slide, "Every number is Observed, Derived, Model, Scenario or Operator-entered · no unlabelled financial claim")


def fill_demo_slide(slide) -> None:
    remove_non_picture_shapes(slide)
    add_title(slide, "The 4-minute proof: compute → explain → act", "04 · End-to-end CoCo CLI workflow")
    steps = [
        ("1", "COMPUTE", "CoCo queries weighted OEE and ownership.\nStreamlit shows the same deterministic row.", CYAN),
        ("2", "EXPLAIN", "Five alarm-pattern rows go to Cortex.\nThe answer cites codes and states what is unknown.", TEAL),
        ("3", "ACT", "The operator opens an inspection.\nA Snowflake MERGE writes one reload-safe action.", AMBER),
    ]
    for index, (number, title, body, tone) in enumerate(steps):
        x = 0.62 + index * 3.10
        circle(slide, x, 1.66, 0.68, tone, tone)
        add_text(slide, number, x, 1.82, 0.68, 0.24, size=17, color=DARK, bold=True, align=PP_ALIGN.CENTER)
        add_text(slide, title, x + 0.86, 1.72, 1.70, 0.28, size=17, color=tone, bold=True)
        add_text(slide, body, x, 2.60, 2.57, 1.00, size=12, color=DARK)
        if index < 2:
            arrow(slide, x + 2.61, 2.02, 0.32, 0.22, tone)
    shape_box(slide, 1.05, 4.16, 7.90, 0.62, "151F26", line=GRID)
    add_text(slide, "BLACK-BOX RESULT", 1.28, 4.34, 1.42, 0.18, size=9, color=TEAL, bold=True)
    add_text(slide, "same input → same action id → second run deduplicated=true", 2.78, 4.28, 5.75, 0.28,
             size=14, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    add_footer(slide, "Saved prompts: docs/demo/01_oee.txt · 02_rca.txt · 03_action.txt")


def fill_thank_you(slide) -> None:
    remove_non_picture_shapes(slide)
    shape_box(slide, 0.56, 4.66, 8.88, 0.54, "07131E", line=GRID)
    add_rich_text(
        slide,
        [
            {"text": "LIVE  ", "bold": True, "color": TEAL},
            {"text": "TRIDENT OPS", "bold": True, "color": WHITE, "url": APP_URL},
            {"text": "     CODE  ", "bold": True, "color": CYAN},
            {"text": "github.com/ashokjangam/snowcore-pdm", "color": WHITE, "url": REPO_URL},
        ],
        0.76, 4.82, 8.46, 0.23, size=10, color=WHITE, align=PP_ALIGN.CENTER,
    )
    add_text(slide, "Compute. Explain. Act. Admit what the evidence cannot prove.",
             1.55, 5.22, 6.90, 0.22, size=10, color=WHITE, bold=True, align=PP_ALIGN.CENTER)


def build(template: Path, output: Path) -> None:
    presentation = Presentation(str(template))
    if len(presentation.slides) != 6:
        raise ValueError(f"Expected the official six-slide template, found {len(presentation.slides)} slides")
    fill_title_slide(presentation.slides[0])
    fill_problem_slide(presentation.slides[1])
    fill_architecture_slide(presentation.slides[2])
    fill_evidence_slide(presentation.slides[3])
    fill_demo_slide(presentation.slides[4])
    fill_thank_you(presentation.slides[5])
    output.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(str(output))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.template, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
