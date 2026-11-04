"""Coordinate based review; exports contain only sanitized pixels and safe text.

Never copy original PDF objects, image streams, attachments or metadata into an export.
Review coordinates always use the displayed (rotated, cropped) page in PDF points.
"""
import base64
import html
import io
import math
import re
import time
import uuid
import fitz
from .ocr import DocumentError, recognize_page, MAX_TEXT, MAX_PIXELS, MAX_OCR_PAGES, OCR_BUDGET_SECONDS
EXPORT_DPI = (150, 300, 600)
DEFAULT_EXPORT_DPI = 300
MAX_EXPORT_PIXELS = 40_000_000  # Enough for a full A4 at 600 DPI (~35 MP).
MAX_EXPORT_BYTES = 256 * 1024 * 1024
MAX_PREVIEW_PIXELS = 8_000_000


def export_scale(width, height, dpi):
    if type(dpi) is not int or dpi not in EXPORT_DPI:
        raise DocumentError('Scegli una qualità di 150, 300 o 600 DPI.')
    if width <= 0 or height <= 0:
        raise DocumentError('Dimensioni pagina non valide.')
    return min(dpi / 72, math.sqrt(MAX_EXPORT_PIXELS / (width * height)))


def export_resolution_note(pages, dpi):
    limited = [72 * export_scale(p['width'], p['height'], dpi) for p in pages
               if export_scale(p['width'], p['height'], dpi) < dpi / 72 - .001]
    if limited:
        return f'{len(limited)} pagine molto grandi: risoluzione ridotta, fino a {math.floor(min(limited))} DPI, per limitare la memoria.'
    return ''


def source_pdf(data, is_pdf=True):
    if is_pdf:
        return fitz.open(stream=data, filetype='pdf')
    text = data.decode('utf-8-sig')
    if not text.strip() or len(text) > MAX_TEXT:
        raise DocumentError('Testo vuoto o troppo lungo.')
    output = io.BytesIO()
    story = fitz.Story('<html><body>' + html.escape(text).replace('\n', '<br>') + '</body></html>')
    writer = fitz.DocumentWriter(output)
    more = True
    while more:
        device = writer.begin_page(fitz.Rect(0, 0, 595, 842))
        more, _ = story.place(fitz.Rect(48, 48, 547, 794))
        story.draw(device)
        writer.end_page()
    writer.close()
    return fitz.open(stream=output.getvalue(), filetype='pdf')


def inspect_document(data, is_pdf=True, progress=None):
    pages, all_words, parts = [], [], []
    offset, ocr_pages = 0, 0
    deadline = time.monotonic() + OCR_BUDGET_SECONDS
    with source_pdf(data, is_pdf) as doc:
        if doc.needs_pass or not 1 <= len(doc) <= 250:
            raise DocumentError('PDF protetto o superiore a 250 pagine.')
        for number, page in enumerate(doc):
            if progress:
                progress(f'Lettura pagina {number + 1} di {len(doc)}', number, len(doc))
            words = []
            for w in page.get_text('words', sort=True):
                rect = fitz.Rect(w[:4]) * page.rotation_matrix
                rect &= page.rect
                if rect.is_empty:
                    continue
                words.append({'t': w[4], 'rect': list(rect), 'line': f'n:{w[5]}:{w[6]}', 'confidence': 100})
            warnings = []
            clips = []
            if not words:
                clips = [page.rect]
            else:
                # Native text remains authoritative. OCR only visible image regions,
                # excluding images already covered by a searchable OCR text layer.
                for info in page.get_image_info():
                    rect = (fitz.Rect(info['bbox']) * page.rotation_matrix) & page.rect
                    if rect.is_empty:
                        continue
                    covered = sum((fitz.Rect(w['rect']) & rect).get_area() for w in words)
                    if covered > rect.get_area() * .08:
                        warnings.append('Immagine con testo: controlla anche firme e scritte non riconosciute.')
                    elif rect.get_area() < 300:
                        warnings.append('Piccola immagine: verifica visivamente eventuali dati personali.')
                    elif not any(rect == previous for previous in clips):
                        clips.append(rect)
            if clips:
                ocr_pages += 1
                if ocr_pages > MAX_OCR_PAGES:
                    raise DocumentError('Massimo 40 pagine OCR per file: dividi il documento.')
                warnings.append('Lettura OCR: controlla nomi, scrittura a mano e firme. Le selezioni automatiche possono essere incomplete.')
                for n, clip in enumerate(clips):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise DocumentError('OCR troppo lungo: dividi il documento.')
                    recognized = recognize_page(page, remaining, clip=clip, boxes=True)
                    for word in recognized:
                        if any((fitz.Rect(word['rect']) & fitz.Rect(w['rect'])).get_area() > fitz.Rect(word['rect']).get_area() * .5 for w in words):
                            continue
                        word['line'] = f'o:{n}:' + word['line']
                        words.append(word)
                if any(w['confidence'] < 70 for w in words):
                    warnings.append('Sono presenti parole lette con bassa affidabilità: confronta questa pagina con l’originale.')
            if page.first_annot or page.first_widget:
                warnings.append('Annotazioni o campi modulo: controlla visivamente tutti i valori e le firme.')
            previous = None
            for word in words:
                separator = '' if not parts else (' ' if previous == word['line'] else '\n')
                parts.append(separator)
                offset += len(separator)
                word.update(page=number, start=offset, end=offset+len(word['t']))
                parts.append(word['t'])
                offset = word['end']
                all_words.append(word)
                previous = word['line']
            if offset > MAX_TEXT:
                raise DocumentError('Testo troppo lungo (massimo 500.000 caratteri).')
            pages.append({'width': page.rect.width, 'height': page.rect.height, 'warnings': list(dict.fromkeys(warnings))})
    return {'text': ''.join(parts), 'words': all_words, 'pages': pages, 'ocr_pages': ocr_pages}


def initials(text):
    return ''.join(w[0].upper()+'.' for w in re.findall(r'[^\W\d_]+', text)) or '[omesso]'


def make_review(extracted, segments):
    text, words = extracted['text'], extracted['words']
    if not isinstance(segments, list) or ''.join(s.get('t', '') for s in segments) != text.strip():
        raise DocumentError('Risposta del modello non valida')
    spans, offset = [], 0
    for segment in segments:
        end = offset + len(segment.get('t', ''))
        if segment.get('label'):
            spans.append((offset, end, segment['label'], 'modello'))
        offset = end
    # A generic extra rule for surname + initial, frequent in school timetables.
    # Not a list of names from the test fixtures. Includes compound surnames.
    surname = r"[A-ZÀ-Ý][A-ZÀ-Ý'’\-]{1,}(?: [A-ZÀ-Ý][A-ZÀ-Ý'’\-]*){0,2}"
    for match in re.finditer(r'(?<!\w)'+surname+r' +[A-ZÀ-Ý]\.(?!\w)', text):
        spans.append((match.start(), match.end(), 'FULLNAME', 'regola nome e iniziale'))
    # Prefer the wider surname+initial match when a model only tagged the surname.
    spans.sort(key=lambda s: (s[3] == 'modello', -(s[1]-s[0])))
    taken, redactions = set(), []
    for start, end, label, source in spans:
        selected = [(i, w) for i, w in enumerate(words) if w['start'] < end and w['end'] > start]
        if not selected or any(i in taken for i, _ in selected):
            continue
        groups = {}
        for i, w in selected:
            taken.add(i)
            groups.setdefault((w['page'], w['line']), []).append(w)
        for (page, _), group in groups.items():
            rect = fitz.Rect(group[0]['rect'])
            for word in group[1:]:
                rect |= fitz.Rect(word['rect'])
            value = ' '.join(w['t'] for w in group)
            # Small padding covers glyph edges without destroying neighboring cells.
            rect = fitz.Rect(rect.x0-.7, rect.y0-.5, rect.x1+.7, rect.y1+.5)
            bounds = fitz.Rect(0, 0, extracted['pages'][page]['width'], extracted['pages'][page]['height'])
            redactions.append({'id': str(uuid.uuid4()), 'page': page, 'rect': list(rect & bounds),
                               'text': value, 'lite': initials(value) if label == 'FULLNAME' else '[omesso]', 'label': label, 'source': source})
    return {'version': 2, 'pages': extracted['pages'], 'redactions': redactions, 'checked_pages': [], 'ocr_pages': extracted['ocr_pages']}


def validate_review(review, doc):
    if review.get('version') != 2 or len(review.get('pages', [])) != len(doc):
        raise DocumentError('Revisione non compatibile con il documento.')
    if len(review.get('redactions', [])) > 10000:
        raise DocumentError('Troppe selezioni.')
    for area in review['redactions']:
        page = area.get('page')
        if type(page) is not int or not 0 <= page < len(doc):
            raise DocumentError('Pagina non valida.')
        coords = area.get('rect', [])
        if len(coords) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in coords):
            raise DocumentError('Area non valida.')
        rect = fitz.Rect(coords)
        if rect.is_empty or not doc[page].rect.contains(rect):
            raise DocumentError('Area fuori pagina.')
        if not re.fullmatch(r'(?:[A-ZÀ-Ý]\.){1,12}|\[omesso\]', area.get('lite', '')):
            raise DocumentError('Usa solo iniziali (es. A.B.) oppure [omesso].')


def render_variants(data, is_pdf, review, progress=None, *, dpi=DEFAULT_EXPORT_DPI):
    export_scale(1, 1, dpi)  # Reject invalid options even for an empty document.
    variants = {}
    with source_pdf(data, is_pdf) as source:
        validate_review(review, source)
        for mode in ('lite', 'anonimo'):
            with fitz.open() as output:
                image_bytes = 0
                for number, page in enumerate(source):
                    if progress:
                        progress(f'Esportazione {mode} · {dpi} DPI · pagina {number + 1} di {len(source)}', number + (len(source) if mode == 'anonimo' else 0), len(source) * 2)
                    scale = export_scale(page.rect.width, page.rect.height, dpi)
                    pixels = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False, annots=True)
                    areas = [a for a in review['redactions'] if a['page'] == number]
                    for area in areas:
                        r = fitz.Rect(area['rect']) * fitz.Matrix(scale, scale)
                        r = fitz.IRect(math.floor(r.x0), math.floor(r.y0), math.ceil(r.x1), math.ceil(r.y1))
                        pixels.set_rect(r, (255, 255, 255))
                    target = output.new_page(width=page.rect.width, height=page.rect.height)
                    # The embedded image is already sanitized, not an original under an overlay.
                    image = pixels.tobytes('png')
                    image_xref = target.insert_image(target.rect, stream=image)
                    # insert_image expands PNG into raw RGB in the in-memory PDF.
                    # Compress immediately: otherwise each A4 at 600 DPI would retain
                    # ~100 MB until final save, even when its PNG is only a few KB.
                    output.update_stream(image_xref, pixels.samples, compress=True)
                    image_bytes += len(output.xref_stream_raw(image_xref))
                    if image_bytes > MAX_EXPORT_BYTES:
                        raise DocumentError('Varianti troppo grandi: scegli una qualità inferiore oppure dividi il documento.')
                    # Preserve copy/search for native text only, excluding every intersecting word.
                    for word in page.get_text('words'):
                        rect = fitz.Rect(word[:4]) * page.rotation_matrix
                        if not target.rect.contains(rect) or any(rect.intersects(fitz.Rect(a['rect'])) for a in areas):
                            continue
                        fontsize = max(2, min(rect.height*.7, rect.width/max(fitz.get_text_length(word[4], fontsize=1), .1)))
                        target.insert_text((rect.x0, rect.y1-rect.height*.2), word[4], fontsize=fontsize, render_mode=3)
                    for area in areas:
                        rect = fitz.Rect(area['rect'])
                        value = area['lite'] if mode == 'lite' else '[omesso]'
                        size = min(10, rect.height*.65, (rect.width-1)/max(fitz.get_text_length(value, fontsize=1), .1))
                        if size >= 2:
                            target.insert_text((rect.x0+.3, rect.y0+rect.height*.75), value, fontsize=size, color=(.25,.25,.25))
                variants[mode] = base64.b64encode(output.tobytes(garbage=4, deflate=True)).decode()
    return variants


def preview_region(data, is_pdf, number, scale=2.0, clip=None):
    """Return pixels and their exact page position; clipped renders stay bounded."""
    if not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
        raise DocumentError('Ingrandimento non valido.')
    with source_pdf(data, is_pdf) as doc:
        if not 0 <= number < len(doc):
            raise DocumentError('Pagina non valida.')
        page = doc[number]
        area = page.rect
        if clip is not None:
            if len(clip) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in clip):
                raise DocumentError('Area anteprima non valida.')
            area = fitz.Rect(clip) & page.rect
        if area.is_empty:
            raise DocumentError('Area anteprima fuori pagina.')
        limit = MAX_PREVIEW_PIXELS if clip is not None else 3_000_000
        scale = min(scale, 12.0, math.sqrt(limit / area.get_area()))
        pixels = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=area,
                                 colorspace=fitz.csRGB, alpha=False, annots=True)
        return {'image': pixels.tobytes('png'), 'scale': scale,
                'rect': [pixels.x/scale, pixels.y/scale,
                         (pixels.x+pixels.width)/scale, (pixels.y+pixels.height)/scale]}


def preview(data, is_pdf, number):
    return preview_region(data, is_pdf, number)['image']
