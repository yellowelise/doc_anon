from pathlib import Path
from unittest.mock import patch
import copy
import fitz

from PySide6.QtWidgets import QApplication
from doc_anon.app import MainWindow, STYLE
from doc_anon.document import Document
from test_core import sample_pdf, sample_review


def test_review_interaction_and_screenshot(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    app.processEvents()
    artifact = Path(__file__).resolve().parents[1] / '.test-data'
    artifact.mkdir(exist_ok=True)
    window.grab().save(str(artifact / 'welcome.png'))
    data = sample_pdf()
    window.document_loaded(Document(tmp_path / 'Esempio riservato.pdf', data, True, sample_review(data)))
    app.processEvents()
    count = len(window.doc.review['redactions'])
    first = window.doc.review['redactions'][0]['id']
    window.select_area(first)
    window.lite_input.setText('M.X.')
    window.update_lite()
    assert window.selected_area()['lite'] == 'M.X.'
    window.approval.setChecked(True)
    assert window.export_button.isEnabled()
    window.remove_area()
    assert not window.approval.isChecked()
    assert len(window.doc.review['redactions']) == count - 1
    window.undo()
    assert len(window.doc.review['redactions']) == count
    window.add_area([54, 180, 300, 210])
    assert window.selected_area()['label'] == 'MANUALE'
    window.coordinates[2].setValue(220)
    window.update_geometry()
    assert window.selected_area()['rect'][2] == 274
    app.processEvents()
    window.grab().save(str(artifact / 'review.png'))
    window.exported = True
    window.close()
    app.processEvents()


def test_quality_selector_controls_both_exports_and_preview_stays_aligned(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    data = sample_pdf()
    window.document_loaded(Document(tmp_path / 'qualita.pdf', data, True, sample_review(data)))
    app.processEvents()
    assert window.quality_combo.currentData() == 300
    areas = copy.deepcopy(window.doc.review['redactions'])
    window.select_area(areas[0]['id'])
    window.view.zoom(2)
    window.refresh_preview_detail()
    assert window.view.detail_item is not None
    assert window.view.detail_item.scale() < 1/window.view.base_scale
    assert window.doc.review['redactions'] == areas
    assert window.selected_area()['id'] == areas[0]['id']
    first_key = window.view.detail_key
    window.view.verticalScrollBar().setValue(window.view.verticalScrollBar().maximum())
    window.refresh_preview_detail()
    assert window.view.detail_key != first_key
    # Preview rendering must not overlap with a worker using PyMuPDF.
    window.job = object()
    with patch.object(window.doc, 'page_region', side_effect=AssertionError('Concurrent render')):
        window.refresh_preview_detail()
    window.job = None
    window.quality_combo.setCurrentIndex(2)
    assert window.quality_combo.currentData() == 600
    window.approval.setChecked(True)
    # Run the actual export work synchronously, avoiding a dialog in the test.
    window.start_job = lambda work, callback: callback(work(lambda *_: None))
    with patch('doc_anon.app.QFileDialog.getExistingDirectory', return_value=str(tmp_path)):
        window.export_files()
    assert len(window.last_exports) == 2
    for path in window.last_exports:
        with fitz.open(path) as pdf:
            image = pdf[0].get_images()[0]
            assert abs(image[2] - pdf[0].rect.width * 600/72) <= 1
    window.view.fit_width()
    window.view.verticalScrollBar().setValue(0)
    app.processEvents()
    artifact = Path(__file__).resolve().parents[1] / '.test-data'
    artifact.mkdir(exist_ok=True)
    window.grab().save(str(artifact / 'quality-review.png'))
    window.close()
    app.processEvents()
