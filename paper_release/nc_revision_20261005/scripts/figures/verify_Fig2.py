import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageChops


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    archive = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, default=archive)
    parser.add_argument("--figure-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    archive = args.archive_root.resolve()
    figure_dir = args.figure_dir.resolve() if args.figure_dir else archive / "figures"
    output_dir = args.output_dir.resolve() if args.output_dir else archive / "results" / "fig2"
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = {
        "r2_waveform_grid.csv": "872366804d289b8c824a0a3ee0baff3b7308fac9c59d9f1d84f6cd1f100c3cf2",
        "r2_wf_followsun.csv": "9d0366220bcc66c30ebe85f5ca123f96c035536b26345cb0238dd055bb440559",
    }
    inputs = {}
    for filename, digest in expected.items():
        path = archive / "inputs" / "reference" / "waveform" / filename
        assert sha256(path) == digest, f"Frozen input changed: {path}"
        data = pd.read_csv(path)
        inputs[filename] = {"sha256": digest, "rows": len(data)}
    grid = pd.read_csv(archive / "inputs" / "reference" / "waveform" / "r2_waveform_grid.csv")
    followsun = pd.read_csv(archive / "inputs" / "reference" / "waveform" / "r2_wf_followsun.csv")
    assert len(grid) == 3744 and grid.country.nunique() == 104
    assert len(followsun) == 104
    original_path = archive / "inputs" / "reference" / "fig2" / "fig2_latency_full.png"
    assert sha256(original_path) == "b9ba355031e81ff4594d11871b4c12afb3dacb3b5ae65a464f58c7189f72066e"
    original = Image.open(original_path).convert("RGB")
    revised_path = figure_dir / "Fig2.png"
    revised = Image.open(revised_path).convert("RGB")
    assert original.size == revised.size == (4672, 3336)
    bbox = ImageChops.difference(original, revised).getbbox()
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    assert 320 <= x0 < x1 <= 810 and 2980 <= y0 < y1 <= 3070, bbox
    delta = np.asarray(original, dtype=np.int16) - np.asarray(revised, dtype=np.int16)
    delta[y0:y1, x0:x1] = 0
    assert np.max(np.abs(delta)) == 0
    med = grid.groupby(["phi", "tau_ms"]).uncovered_share.median().unstack() * 100
    report = {
        "status": "passed",
        "modification": "Status quo -> Domestic only; identical original label coordinates, font, and styling",
        "original_script_sha256": "36cbac9f4c682d520c1aa4712241814c44994336375cf5b42905fd0bbf651bd0",
        "inputs": inputs,
        "country_count": 104,
        "grid_rows": 3744,
        "heatmap_medians_percent": {
            str(phi): {str(tau): float(value) for tau, value in row.items()}
            for phi, row in med.iterrows()
        },
        "original_png_sha256": sha256(original_path),
        "revised_png_sha256": sha256(revised_path),
        "revised_pdf_sha256": sha256(figure_dir / "Fig2.pdf"),
        "png_size_px": list(original.size),
        "changed_pixel_bbox": list(bbox),
        "max_pixel_difference_outside_annotation": 0,
        "scientific_data_color_layout_pixel_invariance": "passed",
    }
    (output_dir / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "changed_pixel_bbox": report["changed_pixel_bbox"]}))


if __name__ == "__main__":
    main()
