"""Check actual browser PDF fills, vector grid widths and visible raster widths.

Run with the bundled Python (pdfplumber and Pillow). --baseline records defects
without a failing exit status. No app/database writes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import logging
from pathlib import Path
import subprocess
import tempfile

import pdfplumber
from PIL import Image

logging.getLogger("pdfminer").setLevel(logging.ERROR)
GRID = (104, 115, 109)
FILL = (240, 243, 238)


def color_matches(value, target):
    return isinstance(value, (tuple, list)) and len(value) == 3 and max(abs(a * 255 - b) for a, b in zip(value, target)) < 1


def verify(path: Path):
    pages = []
    issues = []
    required_fill = 5 if path.name.startswith("members-") else 10 if path.name.startswith("management-") else 0
    with pdfplumber.open(path) as pdf, tempfile.TemporaryDirectory(prefix="fucheng-print-grid-") as temp:
        for index, page in enumerate(pdf.pages):
            grid = [rect for rect in page.rects if color_matches(rect.get("non_stroking_color"), GRID)]
            fill = [rect for rect in page.rects if color_matches(rect.get("non_stroking_color"), FILL)]
            segments = []
            for rect in grid:
                width, height = rect["width"], rect["height"]
                if min(width, height) < 2 and max(width, height) > 2:
                    if abs(min(width, height) - .75) >= .02:
                        issues.append(f"page {index + 1}: vector grid width {min(width, height):.3f} pt")
                    if max(width, height) > 15:
                        segments.append(rect)
            if grid and len(fill) < required_fill:
                issues.append(f"page {index + 1}: foreground header fill {len(fill)} < {required_fill}")
            # Repeated thead must also divide a continued data-row fragment.
            # Checking only the lines which exist would miss a missing edge.
            for header in fill:
                edge = [rect for rect in segments if rect["height"] < 2
                        and rect["x1"] >= header["x0"]
                        and rect["x0"] <= header["x1"]
                        and abs(rect["top"] - header["bottom"]) < 2]
                covered = header["x0"]
                for rect in sorted(edge, key=lambda rect: rect["x0"]):
                    if rect["x0"] <= covered + .1:
                        covered = max(covered, rect["x1"])
                if covered < header["x1"] - .1:
                    issues.append(f"page {index + 1}: missing header lower edge at {header['bottom']:.3f} pt")
            # The 450-member fixture has a final notes-only page; all table
            # pages (and every arrangement page) must contain actual grid ink.
            if not segments and (fill or "級" in (page.extract_text() or "") or not required_fill):
                issues.append(f"page {index + 1}: no actual grid segments")
            outside = [char for char in page.chars if char["x0"] < -.1 or char["x1"] > page.width + .1 or char["top"] < -.1 or char["bottom"] > page.height + .1]
            if outside:
                issues.append(f"page {index + 1}: {len(outside)} characters outside paper")
            widths = Counter()
            if segments:
                output = Path(temp) / "page"
                subprocess.run(["pdftoppm", "-r", "576", "-f", str(index + 1), "-l", str(index + 1), "-singlefile", "-png", str(path), str(output)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                with Image.open(output.with_suffix(".png")) as source:
                    image = source.convert("RGB")
                    for rect in segments:
                        vertical = rect["width"] < rect["height"]
                        x = round((rect["x0"] + rect["width"] * (.5 if vertical else .37)) * 8)
                        y = round((rect["top"] + rect["height"] * (.37 if vertical else .5)) * 8)
                        # At 576 dpi a .75 pt line is six pixels. One edge pixel
                        # may be antialiased; a half-width line has only 2-3.
                        samples = [(x + step, y) if vertical else (x, y + step) for step in range(-12, 13)]
                        matches = [max(abs(a - b) for a, b in zip(image.getpixel(point), GRID)) <= 3 for point in samples]
                        if not matches[12]:
                            issues.append(f"page {index + 1}: invisible grid center at {x / 8:.3f}, {y / 8:.3f} pt")
                            continue
                        left = right = 12
                        while left > 0 and matches[left - 1]:
                            left -= 1
                        while right < len(matches) - 1 and matches[right + 1]:
                            right += 1
                        visible = (right - left + 1) / 8
                        if not .625 <= visible <= .875:
                            issues.append(f"page {index + 1}: visible grid width {visible:.3f} pt at {x / 8:.3f}, {y / 8:.3f} pt")
                        widths[visible] += 1
                    image.close()
            pages.append(dict(page=index + 1, grid_segments=len(segments), vector_width_pt=.75 if segments else None, solid_raster_width_pt=dict(sorted(widths.items())), foreground_header_fills=len(fill), characters_outside_page=len(outside)))
    result = dict(file=str(path), pages=pages, issues=issues, status="FAIL" if issues else "PASS")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    paths = [args.directory] if args.directory.is_file() else sorted(args.directory.rglob("*.pdf"))
    assert paths, "No browser PDFs found"
    results = [verify(path) for path in paths]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if not args.baseline and any(result["issues"] for result in results):
        raise SystemExit(1)
