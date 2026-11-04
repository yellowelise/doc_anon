"""Run the packaged executable against synthetic fixtures with networking denied."""
import json
import os
from pathlib import Path
import socket
import sys
import time
import traceback


def run(output):
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    report = {'ok': False, 'frozen': bool(getattr(sys, 'frozen', False)), 'network_attempts': 0}

    def deny(*args, **kwargs):
        report['network_attempts'] += 1
        raise RuntimeError('Network blocked by offline self-test')

    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.getaddrinfo = deny
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    try:
        import fitz
        from .resources import configure_offline, is_ready, tesseract_path
        configure_offline()
        if not is_ready():
            raise RuntimeError('Prepare resources before running the offline self-test.')
        from .document import Document
        from .detector import Detector
        source = destination / 'esempio-sintetico.pdf'
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((54, 70), 'DOCUMENTO DI PROVA', fontsize=18)
            page.insert_text((54, 115), 'Il signor Mario Rossi abita a Roma.', fontsize=13)
            page.insert_text((54, 145), 'Email: mario.rossi@example.org', fontsize=13)
            page.insert_text((54, 180), 'Il contenuto pubblico resta leggibile.', fontsize=13)
            pdf.set_metadata({'author': 'Mario Rossi'})
            pdf.embfile_add('originale.txt', b'Mario Rossi')
            pdf.save(source)
            pixels = page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png')
        detector = Detector()
        document = Document.open(source, detector)
        assert any(a['label'] == 'FULLNAME' and 'Mario' in a['text'] for a in document.review['redactions'])
        report['native_areas'] = len(document.review['redactions'])
        report['export_dpi_verified'] = []
        for dpi in (150, 300, 600):
            outputs = document.export(destination, document.review, dpi=dpi)
            for output_path in outputs:
                with fitz.open(output_path) as pdf:
                    assert 'Mario' not in pdf[0].get_text() and 'example.org' not in pdf[0].get_text()
                    assert pdf.embfile_count() == 0 and not pdf.metadata.get('author')
                    image = pdf[0].get_images()[0]
                    assert abs(image[2] - pdf[0].rect.width * dpi / 72) <= 1
            report['export_dpi_verified'].append(dpi)
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_image(page.rect, stream=pixels)
            pdf.save(destination / 'scansione-sintetica.pdf')
        scan = Document.open(destination / 'scansione-sintetica.pdf', detector)
        assert scan.review['ocr_pages'] == 1
        assert any('Mario' in a['text'] for a in scan.review['redactions'])
        scan.export(destination, scan.review)
        report['scanned_areas'] = len(scan.review['redactions'])
        report['bundled_ocr'] = 'vendor' in str(tesseract_path())
        from PySide6.QtWidgets import QApplication
        from .app import MainWindow, STYLE
        app = QApplication.instance() or QApplication([])
        app.setStyle('Fusion')
        app.setStyleSheet(STYLE)
        window = MainWindow()
        window.show()
        app.processEvents()
        window.grab().save(str(destination / 'welcome.png'))
        window.document_loaded(document)
        window.add_area([54, 220, 310, 245])
        assert window.selected_area()['label'] == 'MANUALE'
        window.undo()
        window.approval.setChecked(True)
        assert window.export_button.isEnabled()
        app.processEvents()
        assert window.quality_combo.currentData() == 300
        window.quality_combo.setCurrentIndex(2)
        window.view.zoom(2)
        window.refresh_preview_detail()
        assert window.view.detail_item is not None
        report['dynamic_preview_verified'] = True
        window.grab().save(str(destination / 'zoom.png'))
        window.view.fit_width()
        window.view.verticalScrollBar().setValue(0)
        window.grab().save(str(destination / 'review.png'))
        window.exported = True
        window.close()
        report['ok'] = True
    except BaseException:
        report['error'] = traceback.format_exc()
    report['seconds'] = round(time.monotonic()-started, 2)
    (destination / 'self-test.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
