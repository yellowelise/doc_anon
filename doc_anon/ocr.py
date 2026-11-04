"""Bounded, CPU-only OCR. Page images and recognized text stay in memory."""
import csv
from dataclasses import dataclass
from functools import lru_cache
import io
import math
import os
import re
import subprocess
import time

import fitz


def command():
    return os.environ.get('DOC_ANON_TESSERACT', 'tesseract')


def run_ocr(args, **kwargs):
    # A packaged Windows app must not open a console for every OCR page.
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return subprocess.run([command(), *args], **kwargs)

MAX_TEXT = 500_000
MAX_OCR_PAGES = 40
OCR_BUDGET_SECONDS = 240
PAGE_TIMEOUT_SECONDS = 30
MAX_PIXELS = 12_000_000


class DocumentError(ValueError):
    pass


class OCRUnavailable(RuntimeError):
    pass


@dataclass
class Extraction:
    text: str
    ocr_pages: int = 0


@lru_cache(maxsize=1)
def check_engine():
    try:
        version = run_ocr(['--version'], capture_output=True, timeout=5, check=True).stdout.decode()
        languages = run_ocr(['--list-langs'], capture_output=True, timeout=5, check=True).stdout.decode()
    except (OSError, subprocess.SubprocessError) as exc:
        raise OCRUnavailable('OCR locale non disponibile') from exc
    if not re.search(r'tesseract v?5\.', version) or 'ita' not in languages.splitlines():
        raise OCRUnavailable('Richiesti Tesseract 5 e modello italiano')
    return version.splitlines()[0]


def parse_tsv(data):
    lines = []
    previous = None
    words = []
    weighted_confidence = 0.0
    characters = 0
    for row in csv.DictReader(io.StringIO(data), delimiter='\t', quoting=csv.QUOTE_NONE):
        word = row.get('text', '').strip()
        if row.get('level') != '5' or not word:
            continue
        key = tuple(row[k] for k in ('page_num', 'block_num', 'par_num', 'line_num'))
        if previous is not None and key != previous:
            lines.append(' '.join(words))
            words = []
        previous = key
        words.append(word)
        weighted_confidence += max(0, float(row['conf'])) * len(word)
        characters += len(word)
    if words:
        lines.append(' '.join(words))
    text = '\n'.join(lines)
    if not characters or weighted_confidence / characters < 70:
        raise DocumentError('Scansione poco leggibile: carica una copia più nitida e orientata correttamente.')
    return text


def recognize_page(page, remaining_seconds, clip=None, boxes=False):
    check_engine()
    area = (clip or page.rect).get_area()
    if area <= 0:
        raise DocumentError('Dimensioni della pagina non valide.')
    scale = min(300 / 72, math.sqrt(MAX_PIXELS / area))
    if scale * 72 < 100:
        raise DocumentError('Pagina troppo grande per il riconoscimento OCR.')
    pixels = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, colorspace=fitz.csGRAY, alpha=False, annots=True)
    # No filename, no temporary PDF and no persisted plaintext OCR output.
    try:
        result = run_ocr(
            ['stdin', 'stdout', '-l', 'ita', '--oem', '1', '--psm', '3',
             '--dpi', str(round(scale * 72)), '-c', 'tessedit_create_tsv=1'],
            input=pixels.tobytes('png'), capture_output=True,
            timeout=min(PAGE_TIMEOUT_SECONDS, remaining_seconds),
            env={**os.environ, 'OMP_THREAD_LIMIT': '2'},
        )
    except subprocess.TimeoutExpired as exc:
        raise DocumentError('OCR troppo lungo: dividi il documento in file più piccoli.') from exc
    except OSError as exc:
        raise OCRUnavailable('OCR locale non disponibile') from exc
    if result.returncode:
        raise DocumentError('Impossibile riconoscere questa scansione.')
    data = result.stdout.decode('utf-8')
    if not boxes:
        return parse_tsv(data)
    words = []
    for row in csv.DictReader(io.StringIO(data), delimiter='\t', quoting=csv.QUOTE_NONE):
        if row.get('level') != '5' or not row.get('text', '').strip():
            continue
        x, y, w, h = (float(row[k]) for k in ('left', 'top', 'width', 'height'))
        words.append({'t': row['text'].strip(), 'rect': [(pixels.x+x)/scale, (pixels.y+y)/scale, (pixels.x+x+w)/scale, (pixels.y+y+h)/scale],
                      'line': ':'.join(row[k] for k in ('block_num', 'par_num', 'line_num')), 'confidence': float(row['conf'])})
    return words


def extract_document(data, is_pdf=True):
    if not is_pdf:
        text = data.decode('utf-8-sig')
        if not text.strip() or len(text) > MAX_TEXT:
            raise DocumentError('Testo vuoto o troppo lungo.')
        return Extraction(text)
    deadline = time.monotonic() + OCR_BUDGET_SECONDS
    parts = []
    length = 0
    ocr_pages = 0
    with fitz.open(stream=data, filetype='pdf') as doc:
        if doc.needs_pass or not 1 <= len(doc) <= 250:
            raise DocumentError('PDF protetto o superiore a 250 pagine.')
        for index, page in enumerate(doc):
            native = page.get_text(sort=True)
            # OCR the full visible page, including images, vector text and annotations.
            needs_ocr = not native.strip()
            if needs_ocr:
                ocr_pages += 1
                if ocr_pages > MAX_OCR_PAGES:
                    raise DocumentError('Massimo 40 pagine OCR per file: dividi il documento.')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DocumentError('OCR troppo lungo: dividi il documento in file più piccoli.')
                try:
                    text = recognize_page(page, remaining)
                except DocumentError as exc:
                    raise DocumentError(f'Pagina {index + 1}: {exc}') from exc
            else:
                text = native
            length += len(text) + 2
            if length > MAX_TEXT:
                raise DocumentError('Testo troppo lungo (massimo 500.000 caratteri).')
            parts.append(text)
    return Extraction('\n\n'.join(parts), ocr_pages)
