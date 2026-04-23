"""
Strip images from a PDF to reduce multimodal token cost.

Design principle (per project notes): one goal — reduce image tokens while
preserving the text layer. Analyze → Transform in two phases; fail early if
the PDF has no usable text layer.

Usage:
    python pdf_strip_images.py input.pdf                       # writes input_stripped.pdf
    python pdf_strip_images.py input.pdf -o out.pdf            # custom output
    python pdf_strip_images.py input.pdf --analyze-only        # diagnostic only
"""
from __future__ import annotations

import argparse
import gc
import sys
from pathlib import Path

import pymupdf


def analyze_pdf(pdf_path: Path) -> dict:
    """Read-only diagnostic. Returns per-page stats and overall assessment."""
    doc = pymupdf.open(pdf_path)
    pages = []
    total_images = 0
    total_text_chars = 0
    pages_without_text = 0
    for i, page in enumerate(doc):
        info = page.get_image_info()
        images_on_page = len(info)
        page_area = page.rect.width * page.rect.height
        union = pymupdf.Rect()
        for img in info:
            try:
                union |= pymupdf.Rect(img["bbox"])
            except Exception:
                continue
        covered = abs((union & page.rect)) / page_area if page_area else 0.0
        text = page.get_text()
        text_chars = len(text.strip())
        if text_chars < 50:
            pages_without_text += 1
        pages.append({
            "page_1based": i + 1,
            "images": images_on_page,
            "coverage_pct": round(covered * 100, 1),
            "text_chars": text_chars,
        })
        total_images += images_on_page
        total_text_chars += text_chars
    doc.close()

    has_text_layer = total_text_chars > 1000 and pages_without_text < len(pages) / 2
    return {
        "path": str(pdf_path),
        "total_pages": len(pages),
        "total_images": total_images,
        "total_text_chars": total_text_chars,
        "pages_without_text": pages_without_text,
        "has_text_layer": has_text_layer,
        "per_page": pages,
    }


def strip_images(input_path: Path, output_path: Path) -> dict:
    """Destructive. Removes all images and rewrites the PDF."""
    doc = pymupdf.open(input_path)
    removed = 0
    for i, page in enumerate(doc):
        for xref in [img[0] for img in page.get_images()]:
            try:
                page.delete_image(xref)
                removed += 1
            except Exception:
                pass
        try:
            page.clean_contents()
        except Exception:
            pass
        if i % 10 == 0:
            gc.collect()

    input_size = input_path.stat().st_size
    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()
    output_size = output_path.stat().st_size
    return {
        "input_size_bytes": input_size,
        "output_size_bytes": output_size,
        "size_reduction_pct": round((1 - output_size / input_size) * 100, 1) if input_size else 0.0,
        "images_removed": removed,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", help="Input PDF path")
    p.add_argument("-o", "--output", help="Output path (default: <input>_stripped.pdf)")
    p.add_argument("--analyze-only", action="store_true", help="Diagnostic only; no output")
    args = p.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print(f"ERROR: not found: {inp}", file=sys.stderr)
        sys.exit(1)

    analysis = analyze_pdf(inp)
    print(f"[analyze] {inp.name}: pages={analysis['total_pages']} images={analysis['total_images']} text_chars={analysis['total_text_chars']}")
    if not analysis["has_text_layer"]:
        print("WARNING: PDF has no usable text layer. Stripping would yield blank pages.", file=sys.stderr)
        print("  This PDF needs OCR before image stripping. Aborting.", file=sys.stderr)
        sys.exit(2)

    if args.analyze_only:
        import json
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
        return

    out = Path(args.output) if args.output else inp.parent / f"{inp.stem}_stripped{inp.suffix}"
    if out.resolve() == inp.resolve():
        print("ERROR: output path equals input path; refusing to overwrite.", file=sys.stderr)
        sys.exit(3)

    result = strip_images(inp, out)
    print(f"[strip] {out.name}: removed={result['images_removed']} {result['input_size_bytes']:,} -> {result['output_size_bytes']:,} bytes ({result['size_reduction_pct']}% smaller)")


if __name__ == "__main__":
    main()
