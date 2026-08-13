#!/usr/bin/env python3

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGES_ROOT = REPO_ROOT / "docs" / "images"
DESIGN_ROOT = REPO_ROOT / "docs" / "design"
OUT_ROOT = IMAGES_ROOT / "resized"
README = REPO_ROOT / "README.md"

RASTER_EXTS = {".png", ".jpg", ".jpeg"}

LOGO_WIDTH = 200
HERO_WIDTH = 700
PAIR_WIDTH = 340
TRIPLE_WIDTH = 230
DEFAULT_WIDTH = 400

CURATED: dict[str, tuple[str, int]] = {
    "docs/images/logos/rxn-bench_logo.png": ("logo.png", LOGO_WIDTH),
    "docs/design/diagrams/high-level_block_diagram/RxnBench_System-Diagram(Basic).png": (
        "system-block-diagram.jpg",
        HERO_WIDTH,
    ),
    "docs/design/diagrams/high-level_block_diagram/Workflow-Simplified.png": (
        "workflow-strip.jpg",
        HERO_WIDTH,
    ),
    "docs/images/the-making-of/Rxn Bench Setup no background.png": ("assembled-bench-1.jpg", PAIR_WIDTH),
    "docs/images/the-making-of/IMG_0401.png": ("assembled-bench-2.jpg", PAIR_WIDTH),
    "docs/images/the-making-of/Screenshot_2026-06-20_02-46-40.png": ("ph-toolhead-cad.jpg", PAIR_WIDTH),
    "docs/images/the-making-of/IMG_0160.png": ("ph-toolhead-assembled.jpg", PAIR_WIDTH),
    "docs/images/the-making-of/Screenshot_2026-06-20_02-42-15.png": ("docking-mount-cad.jpg", PAIR_WIDTH),
    "docs/images/the-making-of/IMG_0164.png": ("docking-mount-assembled.jpg", PAIR_WIDTH),
    "docs/images/rxn_bench_ui/RxnBenchGantryXZ.png": ("ui-main.jpg", HERO_WIDTH),
    "docs/images/rxn_bench_ui/RxnBenchGantry.png": ("ui-gantry.jpg", TRIPLE_WIDTH),
    "docs/images/rxn_bench_ui/RxnBenchpHProbe.png": ("ui-ph-probe.jpg", TRIPLE_WIDTH),
    "docs/images/rxn_bench_ui/RxnBenchExperimentRunner.png": ("ui-experiment-runner.jpg", TRIPLE_WIDTH),
    "docs/images/rxn_bench_ui/RxnBenchAddDevice.png": ("ui-add-device.jpg", HERO_WIDTH),
    "docs/images/the-making-of/Screenshot 2026-06-19 153343.png": ("labware-workspace-layout.jpg", PAIR_WIDTH),
    "docs/images/the-making-of/IMG_0397.png": ("labware-workspace-assembled.jpg", PAIR_WIDTH),
    "docs/images/the-making-of/24-well.png": ("labware-sample-plates-24well.jpg", PAIR_WIDTH),
    "docs/images/the-making-of/15-well_sample-holder.png": ("labware-sample-plates-15well.jpg", PAIR_WIDTH),
    "docs/images/the-making-of/workspace collection v2.png": ("labware-footprints.jpg", HERO_WIDTH),
    "docs/images/the-making-of/IMG_1125.PNG": ("labware-washing-station.jpg", HERO_WIDTH),
}


def discover_sources() -> list[Path]:
    sources = []
    for root in (IMAGES_ROOT, DESIGN_ROOT):
        for path in root.rglob("*"):
            if OUT_ROOT in path.parents:
                continue
            if path.suffix.lower() in RASTER_EXTS and path.is_file():
                sources.append(path)
    return sources


def resize_to_width(src: Path, dst: Path, width: int) -> None:
    im = Image.open(src)
    keep_alpha = dst.suffix.lower() == ".png"
    if keep_alpha:
        im = im.convert("RGBA")
    elif im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")

    w, h = im.size
    if w > width:
        im = im.resize((width, max(1, round(h * width / w))), Image.LANCZOS)

    dst.parent.mkdir(parents=True, exist_ok=True)
    if keep_alpha:
        im.save(dst, "PNG", optimize=True)
    else:
        im.save(dst, "JPEG", quality=85, optimize=True)


def main() -> None:
    shutil.rmtree(OUT_ROOT, ignore_errors=True)

    count = 0
    for src in discover_sources():
        src_rel = src.relative_to(REPO_ROOT).as_posix()
        if src_rel in CURATED:
            out_name, width = CURATED[src_rel]
            dst = OUT_ROOT / out_name
        else:
            mirrored = src.relative_to(IMAGES_ROOT) if src.is_relative_to(IMAGES_ROOT) else Path("design") / src.relative_to(DESIGN_ROOT)
            dst = (OUT_ROOT / mirrored).with_suffix(".jpg")
            width = DEFAULT_WIDTH
        resize_to_width(src, dst, width)
        count += 1

    print(f"Wrote {count} resized images to {OUT_ROOT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
