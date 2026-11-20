#!/usr/bin/env python3
"""Freeze local text-to-image and editing prompts with synthetic edit sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "suites/vision/generation/local-full-v1"
SEEDS = [17, 101, 1009, 104729]

TEXT_PROMPTS = {
    "objects_attributes": [
        ("A red enamel kettle on a white kitchen counter, with a blue mug to its right.", ["red kettle", "blue mug", "mug right of kettle"]),
        ("Three ceramic bowls on a wooden table: green, yellow, and blue from left to right.", ["three bowls", "green left", "yellow middle", "blue right"]),
        ("A silver bicycle leaning against a brick wall beside one orange traffic cone.", ["silver bicycle", "brick wall", "one orange cone"]),
        ("A black cat wearing a purple collar, sitting on a pale green sofa.", ["black cat", "purple collar", "green sofa"]),
        ("A transparent glass vase holding exactly two white lilies against a dark navy background.", ["transparent vase", "two white lilies", "navy background"]),
        ("A yellow raincoat hanging from a wooden hook above a pair of red boots.", ["yellow raincoat", "wooden hook", "red boots below"]),
        ("A blue backpack with a round orange patch beside a folded gray blanket.", ["blue backpack", "round orange patch", "gray blanket"]),
        ("A small green toy truck carrying four brown boxes on a clean white floor.", ["green toy truck", "four brown boxes", "white floor"]),
    ],
    "spatial_counting": [
        ("Four red apples in a straight row above two green pears, viewed from directly overhead.", ["four red apples", "two green pears", "apples above pears"]),
        ("A blue cube balanced on a yellow cylinder, with a small red sphere to the left.", ["blue cube on cylinder", "yellow cylinder", "red sphere left"]),
        ("Exactly five paper boats on a pond: three near the top and two near the bottom.", ["five boats", "three top", "two bottom"]),
        ("A white chair between two identical wooden tables in a bright empty room.", ["one white chair", "chair between tables", "two tables"]),
        ("A green circle inside a black square, and a red triangle outside the square on its right.", ["circle inside square", "triangle outside", "triangle right"]),
        ("Six yellow stars arranged as two rows of three on a plain navy poster.", ["six stars", "two rows", "three per row"]),
    ],
    "typography": [
        ("A clean enamel storefront sign reading exactly NORTH STAR REPAIRS, photographed straight-on in daylight.", ["exact text NORTH STAR REPAIRS", "one storefront sign", "daylight"]),
        ("A white coffee cup with the exact words GOOD MORNING in bold black capitals, product photo.", ["exact text GOOD MORNING", "white cup", "black capitals"]),
        ("A minimal blue event poster with headline SCIENCE FAIR 2027 and subheading SATURDAY 10 AM.", ["exact headline SCIENCE FAIR 2027", "exact subheading SATURDAY 10 AM", "blue poster"]),
        ("A red road sign reading exactly STOP AT BRIDGE, centered and fully legible.", ["exact text STOP AT BRIDGE", "red road sign"]),
        ("A yellow shipping box printed with the exact code ZX-4812-B in large black letters.", ["exact code ZX-4812-B", "yellow box", "black text"]),
        ("A notebook cover bearing only the title FIELD NOTES in crisp white lettering on dark green.", ["exact text FIELD NOTES", "white lettering", "dark green cover"]),
    ],
    "people_interactions": [
        ("Two researchers in lab coats jointly pointing at one chart on a wall; both people fully visible.", ["two researchers", "both pointing at chart", "both fully visible"]),
        ("A cyclist wearing a blue helmet hands a red water bottle to a standing friend at a park.", ["blue helmet", "red bottle", "bottle handoff", "park"]),
        ("A chef carefully places a single strawberry on a cake while an assistant watches nearby.", ["chef placing strawberry", "assistant watching", "one cake"]),
        ("An adult and a child build a small wooden birdhouse together at an outdoor workbench.", ["adult and child", "wooden birdhouse", "outdoor workbench"]),
    ],
    "photorealism_materials": [
        ("A macro product photograph of brushed copper beside frosted glass, soft side lighting, visible material textures.", ["brushed copper", "frosted glass", "soft side lighting"]),
        ("A realistic rain-wet cobblestone street at dusk reflecting amber shop lights, empty of traffic.", ["wet cobblestones", "dusk", "amber reflections", "no traffic"]),
        ("A studio photograph of a ripe pear on dark linen with natural skin texture and soft shadows.", ["ripe pear", "dark linen", "natural texture", "soft shadows"]),
        ("A close-up photo of a ceramic bowl with a hairline crack next to a polished steel spoon.", ["ceramic bowl", "hairline crack", "steel spoon"]),
    ],
    "illustration_style": [
        ("A cozy mountain cabin under snowfall, rendered as a flat vector illustration with a limited teal and cream palette.", ["mountain cabin", "snowfall", "flat vector", "teal and cream"]),
        ("A red fox reading in a library, illustrated in watercolor with loose paper texture.", ["red fox", "reading", "library", "watercolor"]),
        ("A futuristic tram at a station, rendered as an isometric pixel-art game scene.", ["tram", "station", "isometric pixel art"]),
        ("A botanical illustration of three different mushrooms on an off-white specimen sheet, ink and watercolor.", ["three mushrooms", "specimen sheet", "ink and watercolor"]),
    ],
    "exclusion": [
        ("A single blue ceramic teapot on a plain white background. No cups, no people, no text.", ["one blue teapot", "white background", "no cups", "no people", "no text"]),
        ("A green electric bus parked at an empty stop in daylight. No other vehicles and no passengers.", ["green bus", "empty stop", "daylight", "no other vehicles", "no passengers"]),
        ("A red umbrella lying on wet pavement. No rain drops, no person, no lettering.", ["red umbrella", "wet pavement", "no raindrops", "no person", "no lettering"]),
        ("One orange balloon floating above a plain field under a clear blue sky. No clouds or buildings.", ["one orange balloon", "field", "clear sky", "no clouds", "no buildings"]),
    ],
}

EDIT_TASKS = [
    ("object_attribute", "Change the blue square to red. Keep every other object and the layout unchanged.", ["square red", "other objects unchanged"]),
    ("object_attribute", "Change the green circle to yellow. Keep the sign and background unchanged.", ["circle yellow", "sign unchanged"]),
    ("object_attribute", "Make the orange vase purple. Preserve the flower and the table.", ["vase purple", "flower and table preserved"]),
    ("object_attribute", "Change the black book cover to navy blue without changing its title.", ["book navy", "title unchanged"]),
    ("text_replace", "Replace the sign text START with FINISH, preserving the sign's shape and color.", ["exact text FINISH", "sign preserved"]),
    ("text_replace", "Replace the label text ALPHA with BRAVO, leaving the box unchanged.", ["exact text BRAVO", "box preserved"]),
    ("background_lighting", "Change the pale gray background to a warm sunset sky. Preserve the foreground objects.", ["sunset background", "foreground preserved"]),
    ("background_lighting", "Make this scene look like night with moonlight. Keep the objects in their positions.", ["night lighting", "objects in place"]),
    ("preservation", "Add a small yellow star in the top-right corner. Preserve everything else.", ["small yellow star top right", "else preserved"]),
    ("preservation", "Remove the red ball from the scene. Preserve the blue square and background.", ["red ball absent", "blue square preserved"]),
    ("identity", "Make the same little robot wave one arm. Preserve its blue square head and orange antenna.", ["robot waving", "blue square head", "orange antenna"]),
    ("identity", "Place this same little robot in a garden. Preserve its blue square head and orange antenna.", ["robot in garden", "blue square head", "orange antenna"]),
]


def source_image(index: int, path: Path) -> None:
    image = Image.new("RGB", (1024, 1024), "#e7e9ed")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 86)
    draw.rectangle((110, 730, 910, 820), fill="#977757")
    draw.rectangle((210, 400, 450, 640), fill="#3177be")
    draw.ellipse((620, 455, 795, 630), fill="#46a363")
    draw.ellipse((700, 650, 830, 780), fill="#cd423e")
    if index == 2:
        draw.polygon([(555, 450), (760, 450), (720, 730), (590, 730)], fill="#df8740")
        draw.line((655, 450, 655, 275), fill="#36854b", width=16)
        for x, y in ((625, 270), (675, 270), (650, 240), (650, 300)):
            draw.ellipse((x-27, y-27, x+27, y+27), fill="#efcf87")
    if index == 3:
        draw.rectangle((540, 400, 810, 700), fill="#1b1d22", outline="#444", width=6)
        draw.text((568, 455), "NOTES", font=ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 51), fill="white")
    if index in (4, 5):
        draw.rectangle((205, 190, 815, 345), fill="#234e88")
        draw.text((260, 215), "START" if index == 4 else "ALPHA", font=font, fill="white")
    if index in (10, 11):
        draw.rectangle((425, 335, 675, 590), fill="#3377bf", outline="#1b3854", width=8)
        draw.ellipse((510, 235, 560, 340), fill="#e88435")
        draw.ellipse((470, 420, 505, 455), fill="white")
        draw.ellipse((590, 420, 625, 455), fill="white")
        draw.line((425, 495, 335, 555), fill="#3377bf", width=30)
        draw.line((675, 495, 765, 555), fill="#3377bf", width=30)
    image.save(path, format="PNG", optimize=False)


def main() -> None:
    if SUITE.exists():
        raise SystemExit(f"refusing to overwrite frozen suite: {SUITE}")
    images = SUITE / "source_images"
    images.mkdir(parents=True)
    cases = []
    for category, rows in TEXT_PROMPTS.items():
        for prompt, requirements in rows:
            cases.append({"id": f"t2i-{len(cases)+1:03d}", "track": "text_to_image",
                          "category": category, "prompt": prompt, "requirements": requirements,
                          "seeds": SEEDS, "width": 1024, "height": 1024})
    assert len(cases) == 36
    for index, (category, prompt, requirements) in enumerate(EDIT_TASKS):
        path = images / f"edit-{index+1:02d}.png"
        source_image(index, path)
        cases.append({"id": f"edit-{index+1:03d}", "track": "image_editing",
                      "category": category, "prompt": prompt, "requirements": requirements,
                      "source_image": str(path.relative_to(SUITE)),
                      "seeds": SEEDS, "width": 1024, "height": 1024})
    assert len(cases) == 48 and len({item["id"] for item in cases}) == 48
    manifest = SUITE / "cases.jsonl"
    manifest.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in cases), encoding="utf-8")
    paths = sorted([manifest, *images.glob("*.png")])
    (SUITE / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(SUITE)}\n"
        for path in paths), encoding="utf-8")
    print(f"Frozen {len(cases)} generation/editing prompts and {len(list(images.glob('*.png')))} sources at {SUITE}")


if __name__ == "__main__":
    main()
