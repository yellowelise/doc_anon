import base64
import copy
import socket
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest

from doc_anon import resources
from doc_anon.detector import merge_entities, segments_from_entities, Detector
from doc_anon.document import Document
from doc_anon.layout import inspect_document, make_review, render_variants, validate_review, preview_region, export_resolution_note
from doc_anon.ocr import DocumentError


def sample_pdf():
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((54, 80), 'Mario Rossi', fontsize=16)
        page.insert_text((54, 120), 'Email: mario.rossi@example.org', fontsize=12)
        page.insert_text((54, 160), 'Questo contenuto resta leggibile.', fontsize=12)
        pdf.set_metadata({'author': 'Mario Rossi', 'subject': 'privato'})
        pdf.embfile_add('segreto.txt', b'Mario Rossi')
        return pdf.tobytes()


def sample_review(data):
    extracted = inspect_document(data)
    text = extracted['text']
    entities = []
    for value, kind in [('Mario Rossi', 'FULLNAME'), ('mario.rossi@example.org', 'EMAIL')]:
        start = text.index(value)
        entities.append({'start': start, 'end': start+len(value), 'label': kind})
    return make_review(extracted, segments_from_entities(text, sorted(entities, key=lambda e: e['start'])))


@pytest.mark.parametrize('dpi', [150, 300, 600])
def test_exports_remove_text_pixels_metadata_attachments(dpi):
    data = sample_pdf()
    review = sample_review(data)
    variants = render_variants(data, True, review, dpi=dpi)
    for name, encoded in variants.items():
        with fitz.open(stream=base64.b64decode(encoded), filetype='pdf') as result:
            text = result[0].get_text()
            assert 'Mario' not in text and 'Rossi' not in text
            assert 'example.org' not in text
            assert 'contenuto' in text
            assert result.embfile_count() == 0
            assert not result.metadata.get('author')
            image = result.extract_image(result[0].get_images()[0][0])
            pixmap = fitz.Pixmap(image['image'])
            assert abs(pixmap.width - result[0].rect.width * dpi / 72) <= 1
            assert abs(pixmap.height - result[0].rect.height * dpi / 72) <= 1
            # The underlying embedded pixels themselves are sanitized.
            area = review['redactions'][0]['rect']
            scale = pixmap.width / result[0].rect.width
            for x in range(round((area[0]+2)*scale), round((area[2]-2)*scale), 5):
                for y in range(round((area[1]+2)*scale), round((area[3]-2)*scale), 5):
                    assert pixmap.pixel(x, y)[:3] == (255, 255, 255)
            assert ('M.R.' in text) == (name == 'lite')
    with fitz.open(stream=data, filetype='pdf') as original:
        assert 'Mario Rossi' in original[0].get_text()


@pytest.mark.parametrize('dpi', [0, 200, 1200, True, '300'])
def test_invalid_export_quality_is_rejected(dpi):
    data = sample_pdf()
    with pytest.raises(DocumentError, match='qualità'):
        render_variants(data, True, sample_review(data), dpi=dpi)


def test_preview_detail_rerenders_real_pixels_and_keeps_exact_page_coordinates():
    data = sample_pdf()
    base = preview_region(data, True, 0)
    detail = preview_region(data, True, 0, 5.5, [50.25, 60.1, 300.6, 170.2])
    assert detail['scale'] > base['scale']
    # Pixel origin must remain aligned even for fractional coordinates and scales.
    with fitz.open(stream=data, filetype='pdf') as pdf:
        direct = pdf[0].get_pixmap(matrix=fitz.Matrix(5.5, 5.5), clip=fitz.Rect(50.25, 60.1, 300.6, 170.2), alpha=False, annots=True)
    pixmap = fitz.Pixmap(detail['image'])
    assert pixmap.samples == direct.samples
    assert detail['rect'][0] * detail['scale'] == direct.x
    assert detail['rect'][1] * detail['scale'] == direct.y


def test_preview_rotated_crop_is_aligned_and_memory_is_bounded():
    with fitz.open(stream=sample_pdf(), filetype='pdf') as pdf:
        pdf[0].set_cropbox(fitz.Rect(20, 20, 570, 800))
        pdf[0].set_rotation(90)
        data = pdf.tobytes()
    clip = [80.3, 25.7, 300.2, 200.8]
    detail = preview_region(data, True, 0, 4, clip)
    with fitz.open(stream=data, filetype='pdf') as pdf:
        direct = pdf[0].get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(clip), alpha=False, annots=True)
    assert fitz.Pixmap(detail['image']).samples == direct.samples
    bounded = preview_region(data, True, 0, 100, [0, 0, 780, 550])
    pixels = fitz.Pixmap(bounded['image'])
    assert pixels.width * pixels.height < 8_010_000


def test_oversized_export_page_is_capped_and_limit_is_explained():
    # A small cap exercises the exact same branch without allocating a poster-sized image.
    with patch('doc_anon.layout.MAX_EXPORT_PIXELS', 100_000):
        data = sample_pdf()
        review = sample_review(data)
        assert 'risoluzione ridotta' in export_resolution_note(review['pages'], 600)
        variants = render_variants(data, True, review, dpi=600)
        with fitz.open(stream=base64.b64decode(variants['anonimo']), filetype='pdf') as pdf:
            info = pdf[0].get_images()[0]
            assert info[2] * info[3] < 101_000


def test_export_compresses_images_before_accumulating_more_pages(monkeypatch):
    with fitz.open(stream=sample_pdf(), filetype='pdf') as source, fitz.open() as joined:
        for _ in range(3):
            joined.insert_pdf(source)
        data = joined.tobytes()
    extracted = inspect_document(data)
    review = make_review(extracted, [{'t': extracted['text']}])
    original_new_page = fitz.Document.new_page
    checked = []
    def new_page(document, *args, **kwargs):
        if len(document):
            image = document[-1].get_images()[0]
            # Check BEFORE final tobytes(deflate=True): final compression would be too late.
            assert document.xref_get_key(image[0], 'Filter') == ('name', '/FlateDecode')
            assert len(document.xref_stream_raw(image[0])) < image[2] * image[3] * 3 / 10
            checked.append(image[0])
        return original_new_page(document, *args, **kwargs)
    monkeypatch.setattr(fitz.Document, 'new_page', new_page)
    render_variants(data, True, review, dpi=150)
    assert len(checked) == 4  # Two checks per three-page copy.


def test_export_byte_budget_counts_the_pdf_image_streams():
    data = sample_pdf()
    with patch('doc_anon.layout.MAX_EXPORT_BYTES', 1):
        with pytest.raises(DocumentError, match='qualità inferiore'):
            render_variants(data, True, sample_review(data), dpi=150)


def test_review_can_remove_and_add_areas():
    data = sample_pdf()
    review = sample_review(data)
    review['redactions'] = [a for a in review['redactions'] if a['label'] != 'FULLNAME']
    result = base64.b64decode(render_variants(data, True, review)['anonimo'])
    with fitz.open(stream=result, filetype='pdf') as pdf:
        assert 'Mario' in pdf[0].get_text()
        assert 'example.org' not in pdf[0].get_text()


@pytest.mark.parametrize('rect', [[-1, 0, 10, 10], [0, 0, float('nan'), 10], [20, 20, 1, 1], [0, 0, 99999, 99999]])
def test_invalid_geometry_rejected(rect):
    data = sample_pdf()
    review = sample_review(data)
    review['redactions'][0]['rect'] = rect
    with fitz.open(stream=data, filetype='pdf') as pdf:
        with pytest.raises(DocumentError):
            validate_review(review, pdf)


def test_export_does_not_overwrite_and_is_transactional(tmp_path):
    original = tmp_path / 'original.pdf'
    data = sample_pdf()
    original.write_bytes(data)
    document = Document(original, data, True, sample_review(data))
    one = document.export(tmp_path, document.review)
    two = document.export(tmp_path, document.review)
    assert set(one).isdisjoint(two)
    assert original.read_bytes() == data
    assert all(Path(p).is_file() for p in one + two)
    with patch('doc_anon.document.base64.b64decode', side_effect=ValueError('failure')):
        with pytest.raises(ValueError):
            document.export(tmp_path, document.review)
    assert not list(tmp_path.glob('.doc-anon-*'))


def test_merge_expands_partial_words_and_preserves_segments():
    text = 'Mario Rossi vive a Novara.'
    entities = merge_entities([{'start': 18, 'end': 20, 'label': 'CITY', 'score': .9}], text)
    assert text[entities[0]['start']:entities[0]['end']] == 'Novara'
    assert ''.join(s['t'] for s in segments_from_entities(text, entities)) == text


def test_setup_is_explicit_and_missing_models_do_not_download(tmp_path, monkeypatch):
    monkeypatch.setenv('DOC_ANON_DATA_DIR', str(tmp_path))
    with patch('socket.socket.connect', side_effect=AssertionError('Network prohibited')):
        assert not resources.is_ready()
        with pytest.raises(RuntimeError, match='incompleto'):
            resources.verify_resources()


def test_corrupt_download_is_not_activated(tmp_path):
    import requests
    class Response:
        status_code = 200
        headers = {'Content-Length': '4'}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, _): yield b'evil'
    destination = tmp_path / 'model.bin'
    with patch.object(requests, 'get', return_value=Response()):
        with pytest.raises(RuntimeError, match='Verifica'):
            resources.download('https://example.invalid/model', destination, '0'*64, size=4)
    assert not destination.exists()


def test_interrupted_download_resumes_and_checks_digest(tmp_path):
    import hashlib
    import requests
    destination = tmp_path / 'model.bin'
    destination.with_suffix('.bin.part').write_bytes(b'ab')
    payload = b'abcdef'
    class Response:
        status_code = 206
        headers = {'Content-Range': 'bytes 2-5/6', 'Content-Length': '4'}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, _): yield b'cdef'
    with patch.object(requests, 'get', return_value=Response()) as get:
        resources.download('https://example.invalid/model', destination, hashlib.sha256(payload).hexdigest(), size=6)
        assert get.call_args.kwargs['headers']['Range'] == 'bytes=2-'
    assert destination.read_bytes() == payload
    assert not destination.with_suffix('.bin.part').exists()


def test_cancelled_export_leaves_no_partial_copies(tmp_path):
    data = sample_pdf()
    doc = Document(tmp_path / 'source.pdf', data, True, sample_review(data))
    def cancel(*_):
        raise resources.Cancelled()
    with pytest.raises(resources.Cancelled):
        doc.export(tmp_path, doc.review, cancel)
    assert list(tmp_path.iterdir()) == []


def test_rotation_and_crop_keep_redactions_aligned():
    with fitz.open(stream=sample_pdf(), filetype='pdf') as pdf:
        pdf[0].set_cropbox(fitz.Rect(20, 20, 570, 800))
        pdf[0].set_rotation(90)
        data = pdf.tobytes()
    review = sample_review(data)
    output = base64.b64decode(render_variants(data, True, review)['anonimo'])
    with fitz.open(stream=output, filetype='pdf') as result, fitz.open(stream=data, filetype='pdf') as original:
        assert result[0].rect == original[0].rect
        assert 'Mario' not in result[0].get_text()
        image = result.extract_image(result[0].get_images()[0][0])
        pixels = fitz.Pixmap(image['image'])
        area = next(a for a in review['redactions'] if a['label'] == 'FULLNAME')['rect']
        scale = pixels.width / result[0].rect.width
        assert pixels.pixel(int((area[0]+area[2])/2*scale), int((area[1]+area[3])/2*scale))[:3] == (255, 255, 255)


@pytest.mark.integration
def test_real_model_and_scanned_document_without_network(tmp_path):
    if not resources.is_ready():
        pytest.skip('Run scripts/prepare_resources.py before the integration test.')
    source = tmp_path / 'sample.pdf'
    source.write_bytes(sample_pdf())
    with patch('socket.socket.connect', side_effect=AssertionError('Network prohibited')), \
         patch('socket.getaddrinfo', side_effect=AssertionError('DNS prohibited')):
        detector = Detector()
        document = Document.open(source, detector)
        assert any(a['label'] == 'FULLNAME' and 'Mario' in a['text'] for a in document.review['redactions'])
        assert any(a['label'] == 'EMAIL' for a in document.review['redactions'])
        outputs = document.export(tmp_path, document.review)
        assert len(outputs) == 2
        # Build a true scan (image only); the bundled Tesseract must recognize it.
        with fitz.open(stream=sample_pdf(), filetype='pdf') as native:
            pixels = native[0].get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png')
        with fitz.open() as scan:
            page = scan.new_page()
            page.insert_image(page.rect, stream=pixels)
            scan.save(tmp_path / 'scan.pdf')
        document = Document.open(tmp_path / 'scan.pdf', detector)
        assert document.review['ocr_pages'] == 1
        assert any('Mario' in a['text'] for a in document.review['redactions'])
