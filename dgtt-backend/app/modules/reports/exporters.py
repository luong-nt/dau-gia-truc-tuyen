"""Xuất CSV và PDF (FR-15, FR-23, FR-25)."""

import csv
import io
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=select_autoescape(["html"]))


def to_csv(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> bytes:
    """Trả về CSV UTF-8 có BOM để Excel đọc đúng tiếng Việt."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def render_html(template_name: str, context: dict[str, Any]) -> str:
    return _env.get_template(template_name).render(**context)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    # Import muộn: WeasyPrint cần thư viện hệ thống (Pango). Trên Windows nên chạy bằng Docker.
    from weasyprint import HTML

    return HTML(string=render_html(template_name, context)).write_pdf()
