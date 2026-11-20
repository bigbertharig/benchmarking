#!/usr/bin/env python3
"""Build the deterministic, offline image-understanding benchmark assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "benchmarks" / "understanding" / "local-v1"
IMAGES = SUITE / "images"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def canvas(title: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (960, 640), "white")
    draw = ImageDraw.Draw(image)
    if title:
        draw.rectangle((0, 0, 960, 74), fill="#183153")
        draw.text((28, 18), title, font=font(34, True), fill="white")
    return image, draw


cases: list[dict] = []


def save(case_id: str, category: str, prompt: str, answers: list[str], image: Image.Image) -> None:
    path = IMAGES / f"{case_id}.png"
    image.save(path, format="PNG", optimize=False)
    cases.append(
        {
            "id": case_id,
            "split": "local-v1",
            "category": category,
            "image": f"images/{case_id}.png",
            "prompt": prompt,
            "expected": {"answers": answers},
            "scoring": {"type": "exact_normalized"},
        }
    )


def build_ocr() -> None:
    image, draw = canvas("WAREHOUSE LABEL")
    draw.rounded_rectangle((120, 150, 840, 500), 24, outline="black", width=5)
    draw.text((175, 205), "BIN 7-C", font=font(54, True), fill="black")
    draw.text((175, 300), "PART: ZK-4827-LM", font=font(48), fill="black")
    draw.text((175, 405), "QTY 18", font=font(44, True), fill="#a21c1c")
    save("ocr-01", "ocr", "What is the complete part code?", ["ZK-4827-LM"], image)

    image, draw = canvas("NORTHSIDE MARKET")
    lines = ["Bread                 $4.75", "Coffee               $12.60", "Apples                $6.00", "Tax                    $1.87"]
    y = 130
    for line in lines:
        draw.text((180, y), line, font=font(35), fill="black")
        y += 70
    draw.line((170, 445, 790, 445), fill="black", width=3)
    draw.text((180, 475), "TOTAL                 $25.22", font=font(42, True), fill="black")
    save("ocr-02", "ocr", "What total is printed on the receipt?", ["$25.22", "25.22"], image)

    image, draw = canvas("EQUIPMENT PLATE")
    draw.rectangle((160, 155, 800, 490), fill="#d9dde1", outline="#333", width=6)
    draw.text((215, 220), "MODEL  AX-14", font=font(45, True), fill="#222")
    draw.text((215, 315), "SERIAL  8QF-193-RT", font=font(42), fill="#222")
    draw.text((215, 405), "INPUT  24 VDC", font=font(38), fill="#222")
    save("ocr-03", "ocr", "Read the serial number exactly.", ["8QF-193-RT"], image)

    image, draw = canvas("DEPARTURE BOARD")
    rows = [("A17", "RIVER CITY", "09:40"), ("B04", "LAKE POINT", "10:15"), ("C22", "PINE RIDGE", "11:05")]
    y = 150
    for gate, place, time in rows:
        draw.text((100, y), gate, font=font(38, True), fill="black")
        draw.text((270, y), place, font=font(38), fill="black")
        draw.text((730, y), time, font=font(38, True), fill="#164e8c")
        y += 115
    save("ocr-04", "ocr", "What time is shown for Lake Point?", ["10:15"], image)


def build_documents() -> None:
    image, draw = canvas("INVOICE #1048")
    draw.text((65, 115), "Customer: Alder Workshop", font=font(31), fill="black")
    draw.text((65, 170), "Due date: 2026-12-14", font=font(31, True), fill="black")
    draw.rectangle((60, 245, 900, 500), outline="#555", width=3)
    draw.text((85, 275), "Item", font=font(28, True), fill="black")
    draw.text((580, 275), "Quantity", font=font(28, True), fill="black")
    draw.text((780, 275), "Price", font=font(28, True), fill="black")
    draw.text((85, 355), "Safety gloves", font=font(28), fill="black")
    draw.text((650, 355), "12", font=font(28), fill="black")
    draw.text((790, 355), "$96.00", font=font(28), fill="black")
    save("document-01", "document", "What is the invoice due date?", ["2026-12-14", "December 14 2026"], image)

    image, draw = canvas("SHIFT HANDOFF")
    text = ["Line 2 inspection completed.", "Coolant pressure stable at 42 psi.", "Replace filter after 18:00.", "Supervisor: Mina Chen"]
    y = 135
    for line in text:
        draw.text((70, y), line, font=font(34), fill="black")
        y += 90
    save("document-02", "document", "At what pressure is the coolant stable?", ["42 psi", "42"], image)

    image, draw = canvas("DELIVERY FORM")
    draw.text((75, 130), "Destination: Cedar Annex", font=font(34), fill="black")
    draw.text((75, 205), "Packages received: 7", font=font(34), fill="black")
    draw.text((75, 280), "Condition:", font=font(34, True), fill="black")
    draw.rectangle((280, 285, 315, 320), outline="black", width=3)
    draw.text((330, 280), "Good", font=font(32), fill="black")
    draw.rectangle((500, 285, 535, 320), outline="black", width=3)
    draw.line((503, 302, 515, 316), fill="#b00020", width=5)
    draw.line((515, 316, 533, 289), fill="#b00020", width=5)
    draw.text((550, 280), "Damaged", font=font(32), fill="black")
    save("document-03", "document", "Which condition box is checked?", ["Damaged"], image)

    image, draw = canvas("PROJECT MILESTONES")
    rows = [("Prototype", "Nov 24", "Complete"), ("Field test", "Dec 03", "In progress"), ("Review", "Dec 11", "Pending")]
    y = 145
    for task, date, status in rows:
        draw.text((80, y), task, font=font(31, True), fill="black")
        draw.text((430, y), date, font=font(31), fill="black")
        draw.text((650, y), status, font=font(31), fill="#174a7e")
        y += 110
    save("document-04", "document", "What is the status of the field test?", ["In progress"], image)


def build_charts() -> None:
    image, draw = canvas("QUARTERLY UNITS")
    vals = [("Q1", 35), ("Q2", 60), ("Q3", 48), ("Q4", 75)]
    x = 140
    for label, value in vals:
        top = 540 - value * 5
        draw.rectangle((x, top, x + 110, 540), fill="#3976b8")
        draw.text((x + 28, top - 42), str(value), font=font(28, True), fill="black")
        draw.text((x + 28, 555), label, font=font(28), fill="black")
        x += 190
    save("chart-01", "chart", "Which quarter has the highest number of units?", ["Q4", "Quarter 4"], image)

    image, draw = canvas("SENSOR TEMPERATURE")
    pts = [(140, 450), (300, 390), (460, 420), (620, 300), (780, 250)]
    draw.line(pts, fill="#c62f2f", width=8)
    for x, y in pts:
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill="#c62f2f")
    for i, label in enumerate(["08:00", "09:00", "10:00", "11:00", "12:00"]):
        draw.text((105 + i * 160, 540), label, font=font(23), fill="black")
    draw.text((735, 205), "28°C", font=font(30, True), fill="black")
    save("chart-02", "chart", "What temperature is shown at 12:00?", ["28°C", "28 C", "28"], image)

    image, draw = canvas("SUPPORT TICKETS")
    vals = [("Billing", 18, "#6a51a3"), ("Login", 31, "#e68626"), ("Shipping", 24, "#3a923a")]
    y = 170
    for label, value, color in vals:
        draw.text((70, y), label, font=font(30), fill="black")
        draw.rectangle((260, y, 260 + value * 16, y + 55), fill=color)
        draw.text((275 + value * 16, y + 8), str(value), font=font(28, True), fill="black")
        y += 120
    save("chart-03", "chart", "How many more login tickets than billing tickets are shown?", ["13"], image)

    image, draw = canvas("WAREHOUSE CAPACITY")
    draw.ellipse((230, 145, 690, 605), fill="#4c8ed9")
    draw.pieslice((230, 145, 690, 605), 0, 90, fill="#efb33e")
    draw.text((705, 220), "Reserved 25%", font=font(30, True), fill="#8a5b00")
    draw.text((70, 440), "Available 75%", font=font(30, True), fill="#164f90")
    save("chart-04", "chart", "What percentage of capacity is available?", ["75%", "75"], image)


def build_gui() -> None:
    image, draw = canvas("SETTINGS")
    tabs = [("General", False), ("Network", True), ("Updates", False)]
    x = 70
    for label, selected in tabs:
        draw.rounded_rectangle((x, 105, x + 220, 175), 12, fill="#2463a6" if selected else "#e6e8eb")
        draw.text((x + 35, 120), label, font=font(27, True), fill="white" if selected else "black")
        x += 250
    draw.text((85, 250), "Proxy server", font=font(31), fill="black")
    draw.rounded_rectangle((700, 245, 815, 295), 25, fill="#2c9b53")
    draw.ellipse((765, 248, 812, 292), fill="white")
    save("gui-01", "gui", "Which settings tab is selected?", ["Network"], image)

    image, draw = canvas("UPLOAD MANAGER")
    draw.text((75, 135), "report-final.pdf", font=font(34), fill="black")
    draw.rectangle((75, 210, 870, 270), outline="#777", width=3)
    draw.rectangle((78, 213, 635, 267), fill="#3987c9")
    draw.text((420, 220), "70%", font=font(30, True), fill="white")
    draw.rounded_rectangle((650, 480, 875, 560), 14, fill="#b4232d")
    draw.text((707, 500), "CANCEL", font=font(30, True), fill="white")
    save("gui-02", "gui", "What percentage of the upload is complete?", ["70%", "70"], image)

    image, draw = canvas("CONNECTION ERROR")
    draw.rounded_rectangle((165, 145, 795, 505), 22, fill="#fff3f3", outline="#b4232d", width=5)
    draw.text((235, 205), "Unable to reach server", font=font(38, True), fill="#8a1620")
    draw.text((275, 300), "Error code: E-731", font=font(35), fill="black")
    draw.rounded_rectangle((355, 400, 605, 470), 12, fill="#2463a6")
    draw.text((422, 416), "RETRY", font=font(30, True), fill="white")
    save("gui-03", "gui", "What error code is displayed?", ["E-731"], image)

    image, draw = canvas("TASK BOARD")
    columns = [("TO DO", "#e5e7eb"), ("ACTIVE", "#dbeafe"), ("DONE", "#dcfce7")]
    x = 30
    for label, color in columns:
        draw.rectangle((x, 100, x + 280, 590), fill=color, outline="#777")
        draw.text((x + 75, 120), label, font=font(28, True), fill="black")
        x += 315
    draw.rounded_rectangle((365, 220, 625, 310), 10, fill="white", outline="#444")
    draw.text((395, 242), "Verify backups", font=font(25), fill="black")
    save("gui-04", "gui", "Which column contains the Verify backups task?", ["Active"], image)


def build_negative() -> None:
    image, draw = canvas("DESK INVENTORY")
    draw.rectangle((100, 430, 860, 530), fill="#9b6b43")
    draw.rectangle((170, 225, 410, 430), fill="#333")
    draw.rectangle((195, 250, 385, 385), fill="#d7eef7")
    draw.ellipse((600, 350, 700, 450), fill="#c74242")
    save("negative-01", "negative", "What color is the bicycle? Answer unavailable if no bicycle is visible.", ["unavailable", "answer unavailable"], image)

    image, draw = canvas("SEALED PACKAGE")
    draw.rectangle((250, 150, 710, 520), fill="#c99b62", outline="#6f4b25", width=6)
    draw.rectangle((405, 150, 550, 520), fill="#e6cf9e")
    draw.text((330, 300), "HANDLE WITH CARE", font=font(33, True), fill="#6d1b1b")
    save("negative-02", "negative", "What serial number is printed? Answer unavailable if none is visible.", ["unavailable", "answer unavailable"], image)

    image, draw = canvas("PARKING MAP")
    for row in range(3):
        for col in range(5):
            x, y = 90 + col * 165, 135 + row * 145
            draw.rectangle((x, y, x + 120, y + 90), outline="#888", width=3)
    draw.text((120, 550), "Visitor spaces are marked in blue", font=font(29), fill="#164f90")
    save("negative-03", "negative", "Which parking space contains a red car? Answer unavailable if none is visible.", ["unavailable", "answer unavailable"], image)

    image, draw = canvas("MEETING ROOM")
    draw.rectangle((200, 270, 760, 480), fill="#d1b38a", outline="#6b5134", width=4)
    for x in (230, 650):
        draw.ellipse((x, 180, x + 100, 270), fill="#4b6a8b")
        draw.ellipse((x, 480, x + 100, 570), fill="#4b6a8b")
    save("negative-04", "negative", "What time is shown on the wall clock? Answer unavailable if no clock is visible.", ["unavailable", "answer unavailable"], image)


def build_spatial() -> None:
    image, draw = canvas("SHAPE COUNT")
    shapes = [(160, 180, "#d43b3b"), (330, 180, "#326dc2"), (500, 180, "#d43b3b"), (670, 180, "#d43b3b"), (245, 380, "#326dc2"), (585, 380, "#d43b3b")]
    for x, y, color in shapes:
        draw.ellipse((x, y, x + 100, y + 100), fill=color)
    save("spatial-01", "spatial", "How many red circles are visible?", ["4", "four"], image)

    image, draw = canvas("OBJECT POSITIONS")
    draw.rectangle((130, 245, 350, 435), fill="#f1c84b")
    draw.text((178, 315), "BOX", font=font(40, True), fill="black")
    draw.ellipse((630, 270, 800, 440), fill="#4a8bd4")
    draw.text((660, 325), "BALL", font=font(32, True), fill="white")
    save("spatial-02", "spatial", "Is the ball to the left or right of the box?", ["right"], image)

    image, draw = canvas("GRID LOCATION")
    for x in (210, 390, 570, 750):
        draw.line((x, 120, x, 560), fill="#555", width=3)
    for y in (230, 340, 450):
        draw.line((60, y, 900, y), fill="#555", width=3)
    for i, label in enumerate(["A", "B", "C", "D", "E"]):
        draw.text((125 + i * 180, 80), label, font=font(28, True), fill="black")
    for i, label in enumerate(["1", "2", "3", "4"]):
        draw.text((25, 160 + i * 110), label, font=font(28, True), fill="black")
    draw.polygon([(480, 360), (493, 398), (533, 398), (501, 421), (513, 460), (480, 436), (447, 460), (459, 421), (427, 398), (467, 398)], fill="#d79b16")
    save("spatial-03", "spatial", "Which grid cell contains the gold star?", ["C3"], image)

    image, draw = canvas("STACK ORDER")
    draw.rectangle((260, 420, 700, 520), fill="#4c8ed9")
    draw.rectangle((315, 320, 645, 420), fill="#e6a33b")
    draw.rectangle((380, 220, 580, 320), fill="#54a868")
    save("spatial-04", "spatial", "What color is the top block?", ["green"], image)


def main() -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    for old in IMAGES.glob("*.png"):
        old.unlink()
    cases.clear()
    build_ocr()
    build_documents()
    build_charts()
    build_gui()
    build_negative()
    build_spatial()

    manifest = SUITE / "cases.jsonl"
    manifest.write_text("".join(json.dumps(case, sort_keys=True) + "\n" for case in cases), encoding="utf-8")
    smoke = SUITE / "smoke.jsonl"
    smoke_cases = [case for case in cases if case["id"].endswith("-01")]
    smoke.write_text("".join(json.dumps(case, sort_keys=True) + "\n" for case in smoke_cases), encoding="utf-8")
    checksums = []
    for path in sorted([manifest, smoke, *IMAGES.glob("*.png")]):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {path.relative_to(SUITE)}\n")
    (SUITE / "SHA256SUMS").write_text("".join(checksums), encoding="utf-8")
    print(f"built {len(cases)} cases in {SUITE}")


if __name__ == "__main__":
    main()
