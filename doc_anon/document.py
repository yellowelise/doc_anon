"""An original is immutable; review and output creation never write back to it."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import shutil
import tempfile

from .layout import inspect_document, make_review, render_variants, preview, preview_region, DEFAULT_EXPORT_DPI
from .ocr import DocumentError
from .resources import configure_offline


@dataclass
class Document:
    path: Path
    data: bytes
    is_pdf: bool
    review: dict

    @classmethod
    def open(cls, path, detector, progress=lambda *_: None):
        path = Path(path)
        if path.suffix.lower() not in {'.pdf', '.txt', '.md', '.markdown'}:
            raise DocumentError('Scegli un file PDF, TXT o Markdown.')
        if path.stat().st_size > 25 * 1024 * 1024:
            raise DocumentError('Il file supera 25 MB: dividilo prima di aprirlo.')
        with path.open('rb') as stream:
            data = stream.read(25 * 1024 * 1024 + 1)
        if len(data) > 25 * 1024 * 1024:
            raise DocumentError('Il file supera 25 MB.')
        configure_offline()
        is_pdf = path.suffix.lower() == '.pdf'
        try:
            extracted = inspect_document(data, is_pdf, progress)
            segments = detector.analyze(extracted['text'], progress)
            review = make_review(extracted, segments)
        except (UnicodeError, RuntimeError) as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise DocumentError('Il file di testo deve essere codificato in UTF-8.') from exc
        return cls(path, data, is_pdf, review)

    def page_png(self, page):
        return preview(self.data, self.is_pdf, page)

    def page_region(self, page, scale=2.0, clip=None):
        return preview_region(self.data, self.is_pdf, page, scale, clip)

    def export(self, folder, review, progress=lambda *_: None, *, dpi=DEFAULT_EXPORT_DPI):
        folder = Path(folder).resolve()
        if not folder.is_dir():
            raise DocumentError('La cartella di destinazione non esiste.')
        variants = render_variants(self.data, self.is_pdf, review, progress, dpi=dpi)
        progress('Salvataggio delle due copie…', 0, 0)
        # A new private output directory for each pair prevents accidental overwrites.
        # No original or review plaintext is persisted in this directory.
        stem = re.sub(r'[^\w .-]', '_', self.path.stem)[:70].strip(' .') or 'documento'
        prefix = f'{stem}_{datetime.now():%Y%m%d_%H%M%S}_'
        staging = Path(tempfile.mkdtemp(prefix='.doc-anon-', dir=folder))
        try:
            paths = []
            for mode in ('lite', 'anonimo'):
                path = staging / f'{stem}_{mode}.pdf'
                path.write_bytes(base64.b64decode(variants[mode], validate=True))
                paths.append(path.name)
            destination = folder / (prefix + staging.name.removeprefix('.doc-anon-'))
            staging.rename(destination)
            return [str(destination / name) for name in paths]
        except BaseException:
            # Only remove our freshly created staging directory, never user files.
            shutil.rmtree(staging, ignore_errors=True)
            raise
