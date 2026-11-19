"""Rewrite a PDF in place as PDF 1.4 without object streams.

GitHub's file viewer showed "Unable to render code block" for tectonic's PDF 1.5 output, which uses object streams.
Run: uv run python experiments/pdf14.py paper/main.pdf
"""

import sys

import pikepdf

with pikepdf.open(sys.argv[1], allow_overwriting_input=True) as pdf:
    pdf.save(sys.argv[1], object_stream_mode=pikepdf.ObjectStreamMode.disable, force_version="1.4")
