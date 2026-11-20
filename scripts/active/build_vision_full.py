#!/usr/bin/env python3
"""Build a frozen 120-case synthetic local image-understanding suite."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from PIL import ImageDraw


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/active/build_vision_understanding_suite.py"
SPEC = importlib.util.spec_from_file_location("vision_screen_builder", SOURCE)
assert SPEC and SPEC.loader
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
suite = ROOT / "suites/vision/understanding/local-full-v1"
base.SUITE = suite
base.IMAGES = suite / "images"


def add(category: str, number: int, prompt: str, answers: list[str], image) -> None:
    base.save(f"{category}-{number:02d}", category, prompt, answers, image)


def build_ocr() -> None:
    for i in range(4):
        image, d = base.canvas("PARTS INVENTORY")
        code = ["MX-72B-401", "KT-18Q-963", "RV-44C-208", "PL-63F-715"][i]
        d.rectangle((115, 145, 850, 510), outline="#222", width=5)
        d.text((160, 195), f"BIN {i+11}-D", font=base.font(43, True), fill="#333")
        d.text((160, 290), f"PART {code}", font=base.font(43, True), fill="#111")
        d.text((160, 390), f"QTY {i*7+14}", font=base.font(38), fill="#8a2424")
        add("ocr", 5+i, "Read the complete PART code.", [code], image)

        image, d = base.canvas("CAFE RECEIPT")
        total = ["18.40", "27.65", "34.80", "42.15"][i]
        d.text((155, 140), "Tea                    $5.20", font=base.font(35), fill="black")
        d.text((155, 235), "Lunch                $11.00", font=base.font(35), fill="black")
        d.text((155, 325), f"Order                  #{i+41}", font=base.font(35), fill="black")
        d.line((145, 430, 790, 430), fill="black", width=3)
        d.text((155, 465), f"TOTAL                 ${total}", font=base.font(39, True), fill="black")
        add("ocr", 9+i, "What total is printed on this receipt?", [total, f"${total}"], image)

        image, d = base.canvas("DEVICE PLATE")
        serial = ["8AC-491-ZT", "3PG-825-RN", "6WD-173-KX", "9JH-647-FM"][i]
        d.rectangle((135, 150, 825, 510), fill="#e6e8e9", outline="#333", width=5)
        d.text((180, 205), f"MODEL  T-{i+30}", font=base.font(42, True), fill="#222")
        d.text((180, 315), f"SERIAL  {serial}", font=base.font(41), fill="#222")
        d.text((180, 415), "INPUT  12 VDC", font=base.font(37), fill="#222")
        add("ocr", 13+i, "What is the exact serial number?", [serial], image)

        image, d = base.canvas("TRANSIT BOARD")
        target_time = ["08:25", "13:40", "17:05", "21:30"][i]
        rows = [("A14", "HARBOR", "07:10"), ("C28", "CEDAR BAY", target_time), ("D03", "WEST HILL", "22:15")]
        for j, (gate, place, hour) in enumerate(rows):
            y = 160 + j*115
            d.text((95, y), gate, font=base.font(36, True), fill="black")
            d.text((260, y), place, font=base.font(35), fill="black")
            d.text((735, y), hour, font=base.font(35, True), fill="#205b91")
        add("ocr", 17+i, "What time is shown for Cedar Bay?", [target_time], image)


def build_document() -> None:
    for i in range(4):
        date = ["2027-01-12", "2027-02-19", "2027-03-23", "2027-04-30"][i]
        image, d = base.canvas(f"INVOICE #{2041+i}")
        d.text((70, 140), "Customer: Elm Equipment", font=base.font(34), fill="black")
        d.text((70, 230), f"Due date: {date}", font=base.font(38, True), fill="black")
        d.text((70, 320), f"Units: {i+6}", font=base.font(34), fill="black")
        d.text((70, 400), "Status: awaiting payment", font=base.font(34), fill="black")
        add("document", 5+i, "What is the invoice due date in YYYY-MM-DD format?", [date], image)

        pressure = ["36", "48", "53", "61"][i]
        image, d = base.canvas("SHIFT HANDOFF")
        for j, line in enumerate(["Line 3 inspection complete.", f"Coolant pressure: {pressure} psi.", "Replace filter at 18:00.", "Supervisor: Tara Moss"]):
            d.text((70, 140+j*92), line, font=base.font(34), fill="black")
        add("document", 9+i, "What coolant pressure is recorded?", [pressure, f"{pressure} psi"], image)

        condition = ["Good", "Damaged", "Good", "Damaged"][i]
        image, d = base.canvas("DELIVERY CHECK")
        d.text((70, 145), f"Packages received: {i+3}", font=base.font(34), fill="black")
        for j, label in enumerate(("Good", "Damaged")):
            x = 200+j*340
            d.rectangle((x, 275, x+44, 319), outline="black", width=4)
            if label == condition:
                d.line((x+4, 295, x+18, 314, x+42, 279), fill="#bc1e31", width=6)
            d.text((x+65, 272), label, font=base.font(34), fill="black")
        add("document", 13+i, "Which condition is checked?", [condition], image)

        status = ["Pending", "In progress", "Complete", "Blocked"][i]
        image, d = base.canvas("PROJECT TASKS")
        for j, (task, state) in enumerate((("Prototype", "Complete"), ("Field test", status), ("Review", "Pending"))):
            y = 150+j*115
            d.text((85, y), task, font=base.font(35, True), fill="black")
            d.text((585, y), state, font=base.font(34), fill="#174a7e")
        add("document", 17+i, "What is the status of Field test?", [status], image)


def build_chart() -> None:
    for i in range(4):
        values = [[31, 58, 45, 72], [68, 44, 79, 53], [55, 82, 48, 63], [90, 76, 61, 43]][i]
        image, d = base.canvas("QUARTERLY OUTPUT")
        for j, v in enumerate(values):
            x = 130+j*200
            top = 535-v*4
            d.rectangle((x, top, x+100, 535), fill="#427cb4")
            d.text((x+25, top-40), str(v), font=base.font(29, True), fill="black")
            d.text((x+27, 555), f"Q{j+1}", font=base.font(28), fill="black")
        winner = f"Q{values.index(max(values))+1}"
        add("chart", 5+i, "Which quarter has the highest output?", [winner, "Quarter "+winner[1:]], image)

        a, b = [(27, 15), (36, 21), (42, 19), (51, 28)][i]
        image, d = base.canvas("SUPPORT REQUESTS")
        for j, (label, value, color) in enumerate((("Login", a, "#d47b28"), ("Billing", b, "#6c53a4"))):
            y = 195+j*160
            d.text((75, y), label, font=base.font(34), fill="black")
            d.rectangle((290, y, 290+value*10, y+60), fill=color)
            d.text((305+value*10, y+10), str(value), font=base.font(30, True), fill="black")
        add("chart", 9+i, "How many more login than billing requests are shown?", [str(a-b)], image)

        value = ["19", "24", "31", "37"][i]
        image, d = base.canvas("NOON TEMPERATURE")
        pts = [(140, 470), (300, 390), (460, 430), (620, 320), (780, 250)]
        d.line(pts, fill="#c63a37", width=8)
        for x,y in pts:
            d.ellipse((x-10,y-10,x+10,y+10), fill="#c63a37")
        for j,label in enumerate(("08:00", "09:00", "10:00", "11:00", "12:00")):
            d.text((105+j*160, 545), label, font=base.font(22), fill="black")
        d.text((730, 205), f"{value}°C", font=base.font(32, True), fill="black")
        add("chart", 13+i, "What temperature is shown at 12:00?", [value, value+"°C", value+" C"], image)

        pct = [20, 30, 40, 60][i]
        image, d = base.canvas("STORAGE CAPACITY")
        d.ellipse((225, 145, 695, 615), fill="#427eb7")
        d.pieslice((225,145,695,615), 0, 360*pct/100, fill="#e4ae37")
        d.text((700, 230), f"Reserved {pct}%", font=base.font(29, True), fill="#795400")
        d.text((50, 450), f"Available {100-pct}%", font=base.font(29, True), fill="#164e85")
        add("chart", 17+i, "What percentage is available?", [str(100-pct), f"{100-pct}%"], image)


def build_gui() -> None:
    for i in range(4):
        selected = ["General", "Network", "Updates", "Privacy"][i]
        image, d = base.canvas("PREFERENCES")
        for j,label in enumerate(("General", "Network", "Updates", "Privacy")):
            x = 40+j*230
            d.rounded_rectangle((x, 120, x+210, 200), 12, fill="#2463a6" if label == selected else "#e5e8eb")
            d.text((x+18, 140), label, font=base.font(25, True), fill="white" if label == selected else "black")
        d.text((80, 305), "Automatic updates", font=base.font(34), fill="black")
        add("gui", 5+i, "Which preferences tab is selected?", [selected], image)

        pct = [25, 45, 80, 95][i]
        image, d = base.canvas("FILE TRANSFER")
        d.text((75, 150), "dataset-export.csv", font=base.font(35), fill="black")
        d.rectangle((75, 245, 875, 320), outline="#777", width=4)
        d.rectangle((80, 250, 80+int(790*pct/100), 315), fill="#3b86c3")
        d.text((385, 260), f"{pct}%", font=base.font(34, True), fill="black")
        add("gui", 9+i, "What percentage of the file transfer is complete?", [str(pct), f"{pct}%"], image)

        code = ["E-204", "E-518", "E-762", "E-930"][i]
        image, d = base.canvas("NETWORK ERROR")
        d.rounded_rectangle((155, 150, 805, 510), 20, fill="#fff3f3", outline="#a62c31", width=5)
        d.text((225, 220), "Connection interrupted", font=base.font(37, True), fill="#832126")
        d.text((275, 320), f"Error code: {code}", font=base.font(36), fill="black")
        add("gui", 13+i, "What error code is displayed?", [code], image)

        column = ["To do", "Active", "Review", "Done"][i]
        image, d = base.canvas("WORK BOARD")
        for j,label in enumerate(("TO DO", "ACTIVE", "REVIEW", "DONE")):
            x = 15+j*235
            d.rectangle((x, 110, x+220, 575), fill="#e6edf5", outline="#666")
            d.text((x+30, 135), label, font=base.font(24, True), fill="black")
        x = 15+i*235
        d.rounded_rectangle((x+10, 245, x+210, 330), 10, fill="white", outline="#444")
        d.text((x+20, 265), "Check backup", font=base.font(24), fill="black")
        add("gui", 17+i, "Which column contains Check backup?", [column], image)


def build_negative() -> None:
    for i in range(4):
        image, d = base.canvas("DESK ITEMS")
        d.rectangle((95, 440, 855, 545), fill="#a37449")
        d.rectangle((155, 245, 405, 440), fill="#3c4145")
        d.ellipse((570, 355, 695, 445), fill="#cf4c3f")
        absent = ("bicycle", "cat", "tree", "clock")[i]
        add("negative", 5+i, f"What color is the {absent}? Answer unavailable if it is not visible.", ["unavailable", "answer unavailable"], image)

        image, d = base.canvas("SHIPPING LABEL")
        d.rectangle((145, 155, 820, 505), fill="#f8f4ea", outline="#333", width=4)
        d.text((205, 225), "FRAGILE", font=base.font(50, True), fill="#a22323")
        d.text((205, 330), f"LOT {i+20}-C", font=base.font(42), fill="black")
        absent = ("serial number", "expiration date", "weight", "invoice number")[i]
        add("negative", 9+i, f"What {absent} is printed? Answer unavailable if none is visible.", ["unavailable", "answer unavailable"], image)

        image, d = base.canvas("PARKING PLAN")
        for row in range(3):
            for col in range(5):
                x,y = 80+col*165, 145+row*125
                d.rectangle((x,y,x+120,y+85), outline="#999", width=3)
        absent = ("red car", "blue truck", "yellow taxi", "white bus")[i]
        add("negative", 13+i, f"Which space contains the {absent}? Answer unavailable if none is visible.", ["unavailable", "answer unavailable"], image)

        image, d = base.canvas("MEETING AREA")
        d.rectangle((185, 270, 760, 470), fill="#d4b995", outline="#6b5134", width=4)
        for x in (220, 650):
            d.ellipse((x, 170, x+95, 270), fill="#4b6a8b")
        absent = ("wall clock", "digital clock", "desk clock", "ceiling clock")[i]
        add("negative", 17+i, f"What time is shown on the {absent}? Answer unavailable if none is visible.", ["unavailable", "answer unavailable"], image)


def build_spatial() -> None:
    for i in range(4):
        count = i+2
        image, d = base.canvas("COLOR COUNT")
        for j in range(6):
            x,y = 160+(j%3)*250, 180+(j//3)*210
            d.ellipse((x,y,x+90,y+90), fill="#d43b3b" if j<count else "#326dc2")
        add("spatial", 5+i, "How many red circles are visible?", [str(count), ["two", "three", "four", "five"][i]], image)

        side = ["left", "right", "left", "right"][i]
        image, d = base.canvas("OBJECT PLACEMENT")
        box_x, ball_x = (650, 140) if side == "left" else (140, 650)
        d.rectangle((box_x,260,box_x+170,440), fill="#e7bd43")
        d.text((box_x+30,325), "BOX", font=base.font(34, True), fill="black")
        d.ellipse((ball_x,275,ball_x+150,425), fill="#4b8bd4")
        d.text((ball_x+25,325), "BALL", font=base.font(29, True), fill="white")
        add("spatial", 9+i, "Is the ball left or right of the box?", [side], image)

        cell = [("A", 1), ("B", 2), ("D", 3), ("E", 4)][i]
        image, d = base.canvas("GRID POSITION")
        for x in (210,390,570,750):
            d.line((x,120,x,560), fill="#555", width=3)
        for y in (230,340,450):
            d.line((60,y,900,y), fill="#555", width=3)
        for j,label in enumerate("ABCDE"):
            d.text((125+j*180,80),label,font=base.font(28,True),fill="black")
        for j in range(4):
            d.text((25,160+j*110),str(j+1),font=base.font(28,True),fill="black")
        col = ord(cell[0])-ord("A")
        cx,cy=150+col*180,175+(cell[1]-1)*110
        d.ellipse((cx-25,cy-25,cx+25,cy+25), fill="#d79b16")
        add("spatial", 13+i, "Which grid cell contains the gold dot?", [f"{cell[0]}{cell[1]}"], image)

        top = ["red", "blue", "green", "yellow"][i]
        palette = {"red":"#d44842", "blue":"#4c8ed9", "green":"#54a868", "yellow":"#e8ba43"}
        image, d = base.canvas("STACK ORDER")
        d.rectangle((255,430,705,530), fill=palette["blue"])
        d.rectangle((315,330,645,430), fill=palette["yellow"])
        d.rectangle((380,230,580,330), fill=palette[top])
        add("spatial", 17+i, "What color is the top block?", [top], image)


def main() -> None:
    if suite.exists():
        raise SystemExit(f"refusing to overwrite frozen suite: {suite}")
    base.IMAGES.mkdir(parents=True)
    base.cases.clear()
    for maker in (base.build_ocr, base.build_documents, base.build_charts,
                  base.build_gui, base.build_negative, base.build_spatial,
                  build_ocr, build_document, build_chart, build_gui,
                  build_negative, build_spatial):
        maker()
    assert len(base.cases) == 120
    assert len({case["id"] for case in base.cases}) == 120
    assert all(sum(case["category"] == cat for case in base.cases) == 20
               for cat in ("ocr", "document", "chart", "gui", "negative", "spatial"))
    manifest = suite / "cases.jsonl"
    for case in base.cases:
        case["split"] = "local-full-v1"
    manifest.write_text("".join(json.dumps(case, sort_keys=True) + "\n" for case in base.cases), encoding="utf-8")
    paths = [manifest, *base.IMAGES.glob("*.png")]
    (suite / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(suite)}\n"
        for path in sorted(paths)), encoding="utf-8")
    print(f"Frozen {len(base.cases)} cases at {suite}")


if __name__ == "__main__":
    main()
