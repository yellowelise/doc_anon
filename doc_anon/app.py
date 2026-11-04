from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import sys
import threading
import uuid

from PySide6.QtCore import Qt, Signal, QThread, QRectF, QPointF, QTimer, QUrl
from PySide6.QtGui import QColor, QPen, QBrush, QPixmap, QPainter, QFont, QFontDatabase, QKeySequence, QShortcut, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QFileDialog, QMessageBox, QProgressBar, QSplitter, QListWidget,
    QListWidgetItem, QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsItem,
    QLineEdit, QDoubleSpinBox, QFormLayout, QCheckBox, QButtonGroup, QScrollArea, QComboBox,
)

from . import __version__
from .resources import is_ready, prepare, Cancelled, data_root, configure_offline, APP_ROOT
from .detector import Detector
from .document import Document
from .layout import export_resolution_note

STYLE = """
QWidget { font-family: 'Manrope'; font-size: 13px; color: #213b35; }
QMainWindow, #root { background: #f4f3ed; }
QLabel { background: transparent; }
QLabel#brand { font-family: 'Newsreader'; font-size: 30px; color: #183e32; }
QLabel#eyebrow { font-size: 11px; font-weight: 700; color: #737f70; letter-spacing: 2px; }
QLabel#hero { font-family: 'Newsreader'; font-size: 48px; color: #183e32; }
QLabel#subhead { font-size: 15px; color: #67736b; }
QLabel#title { font-size: 17px; font-weight: 600; }
QLabel#muted { color: #758078; font-size: 12px; }
QLabel#badge { background: #e2eadf; border-radius: 13px; padding: 7px 15px; color: #325b41; font-size: 11px; font-weight: 600; }
QFrame#header { border-bottom: 1px solid #d9ded4; background: #f4f3ed; }
QFrame#authorBanner { background: #e2eadf; border-bottom: 1px solid #cbd8c5; }
QLabel#authorName { color: #244e3c; font-size: 13px; font-weight: 600; }
QLabel#authorContact { color: #325b41; font-size: 12px; }
QFrame#panel { background: #fafaf6; border: 1px solid #dce0d6; border-radius: 10px; }
QFrame#notice { background: #eeecdf; border-radius: 7px; }
QPushButton { background: #fafaf7; border: 1px solid #d6dccf; border-radius: 6px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #e8eddf; border-color: #99ac96; }
QPushButton:pressed { background: #d9e2ce; }
QPushButton:checked { background: #d9e5d1; border-color: #698b64; color: #244d35; }
QPushButton:disabled { color: #a6afa3; background: #efefe8; border-color: #e2e5db; }
QPushButton#primary { background: #244e3c; border-color: #244e3c; color: white; padding: 11px 19px; }
QPushButton#primary:hover { background: #34694e; }
QPushButton#primary:disabled { background: #c4cdbf; border-color: #c4cdbf; color: #f8faf4; }
QPushButton#danger { color: #a84a36; background: #fff8f1; border-color: #e8cfc2; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 11px 10px; margin: 3px 0px; border-radius: 6px; border: 1px solid transparent; }
QListWidget::item:hover { background: #eff1e7; }
QListWidget::item:selected { background: #e3ecd9; border: 1px solid #a6ba97; color: #21482f; }
QLineEdit, QDoubleSpinBox, QComboBox { background: white; border: 1px solid #cdd7c4; border-radius: 5px; padding: 7px; selection-background-color: #adc697; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #fafaf6; selection-background-color: #e3ecd9; selection-color: #21482f; padding: 5px; }
QLineEdit:focus, QDoubleSpinBox:focus { border: 1px solid #4d7b50; }
QProgressBar { background: #e6e9de; border: none; border-radius: 3px; height: 6px; }
QProgressBar::chunk { background: #7b9b5d; border-radius: 3px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #a9b69e; border-radius: 3px; background: #fcfcf8; }
QCheckBox::indicator:checked { background: #426c43; border: 3px solid #b6cba8; }
QSplitter::handle { background: #e0e4d8; width: 1px; }
QScrollBar:vertical { background: #e9ecdf; width: 9px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #b2beaa; min-height: 28px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #244e3c; color: white; border: none; padding: 6px; }
"""


def label(text, name=None, wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName('primary')
    item.clicked.connect(callback)
    return item


def load_fonts():
    for path in (APP_ROOT / 'assets/fonts').glob('*.ttf'):
        QFontDatabase.addApplicationFont(str(path))
    QApplication.setFont(QFont('Manrope', 10))


class QualityCombo(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#426c43'), 1.5))
        x, y = self.width()-15, self.height()//2
        painter.drawLine(x-4, y-2, x, y+2)
        painter.drawLine(x, y+2, x+4, y-2)


class Job(QThread):
    progress = Signal(str, int, int)
    result = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, work, parent=None):
        super().__init__(parent)
        self.work = work
        self.cancel_event = threading.Event()

    def report(self, message, done=0, total=0):
        if self.cancel_event.is_set():
            raise Cancelled()
        # Qt signals use signed 32-bit ints; percentage is enough even for large downloads.
        self.progress.emit(message, int(done * 1000 / total) if total else 0, 1000 if total else 0)

    def run(self):
        try:
            self.result.emit(self.work(self.report))
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            # Don't persist tracebacks, document text or source paths to disk.
            message = str(exc)
            if len(message) > 450:
                message = 'Operazione non riuscita. Controlla il documento o ripeti la preparazione delle risorse.'
            self.failed.emit(message or 'Operazione non riuscita.')


class RedactionItem(QGraphicsRectItem):
    def __init__(self, area, bounds, callback):
        x0, y0, x1, y1 = area['rect']
        super().__init__(0, 0, x1-x0, y1-y0)
        self.area_id = area['id']
        self.bounds = bounds
        self.callback = callback
        self.setPos(x0, y0)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        pen = QPen(QColor('#c07934'), 1.4)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(223, 161, 65, 58)))
        self.setZValue(1)
        self.setToolTip(f"{area.get('label', 'MANUALE')} · {area.get('text', '')}")
        self.before = self.pos()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return QPointF(max(0, min(value.x(), self.bounds.width()-self.rect().width())),
                           max(0, min(value.y(), self.bounds.height()-self.rect().height())))
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        if self.isSelected():
            painter.setPen(QPen(QColor('#275a42'), 1.8 / max(painter.transform().m11(), .1)))
            painter.setBrush(QColor(91, 151, 96, 65))
            painter.drawRect(self.rect())
        else:
            super().paint(painter, option, widget)

    def mousePressEvent(self, event):
        self.before = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.pos() != self.before:
            # Use actual coordinates, excluding the highlight's pen width.
            self.callback(self.area_id, [self.pos().x(), self.pos().y(),
                self.pos().x()+self.rect().width(), self.pos().y()+self.rect().height()])


class PageView(QGraphicsView):
    selected = Signal(str)
    created = Signal(list)
    moved = Signal(str, list)
    detailRequested = Signal()
    zoomChanged = Signal(float)

    def __init__(self):
        super().__init__()
        self.canvas = QGraphicsScene(self)
        self.setScene(self.canvas)
        self.setBackgroundBrush(QColor('#e5e8dd'))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.bounds = QRectF()
        self.drawing = False
        self.start = None
        self.rubber = None
        self.items_by_id = {}
        self.detail_item = None
        self.detail_key = None
        self.base_scale = 2.0
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(120)
        self.preview_timer.timeout.connect(self.detailRequested.emit)
        self.horizontalScrollBar().valueChanged.connect(self.schedule_detail)
        self.verticalScrollBar().valueChanged.connect(self.schedule_detail)
        self.canvas.selectionChanged.connect(self.selection_changed)

    def display(self, rendered, width, height, areas):
        self.canvas.blockSignals(True)
        self.detail_item = None
        self.detail_key = None
        self.canvas.clear()
        self.rubber = None
        self.start = None
        self.items_by_id = {}
        self.bounds = QRectF(0, 0, width, height)
        pixmap = QPixmap()
        pixmap.loadFromData(rendered['image'])
        page = self.canvas.addPixmap(pixmap)
        self.base_scale = rendered['scale']
        page.setScale(1 / self.base_scale)
        page.setPos(*rendered['rect'][:2])
        page.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.canvas.setSceneRect(self.bounds.adjusted(-18, -18, 18, 18))
        self.canvas.blockSignals(False)
        self.set_areas(areas)
        self.fit_width()
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())
        self.schedule_detail()

    def schedule_detail(self, *_):
        if not self.bounds.isEmpty():
            self.preview_timer.start()

    def detail_request(self):
        scale = math.ceil(self.transform().m11() * self.viewport().devicePixelRatioF() * 2) / 2
        if scale <= self.base_scale:
            return None
        clip = self.mapToScene(self.viewport().rect()).boundingRect()
        clip = clip.adjusted(-24, -24, 24, 24).intersected(self.bounds)
        if clip.isEmpty():
            return None
        return scale, [clip.left(), clip.top(), clip.right(), clip.bottom()]

    def set_detail(self, rendered, key):
        if self.detail_item is not None:
            self.canvas.removeItem(self.detail_item)
        pixmap = QPixmap()
        pixmap.loadFromData(rendered['image'])
        self.detail_item = self.canvas.addPixmap(pixmap)
        self.detail_item.setPos(*rendered['rect'][:2])
        self.detail_item.setScale(1 / rendered['scale'])
        self.detail_item.setZValue(.5)
        self.detail_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.detail_key = key

    def set_areas(self, areas, selected=None):
        self.canvas.blockSignals(True)
        for item in self.items_by_id.values():
            self.canvas.removeItem(item)
        self.items_by_id = {}
        for area in areas:
            item = RedactionItem(area, self.bounds, self.moved.emit)
            self.items_by_id[area['id']] = item
            self.canvas.addItem(item)
            item.setSelected(area['id'] == selected)
        self.canvas.blockSignals(False)

    def selection_changed(self):
        selected = self.canvas.selectedItems()
        self.selected.emit(selected[0].area_id if selected else '')

    def select(self, area_id):
        self.canvas.blockSignals(True)
        for key, item in self.items_by_id.items():
            item.setSelected(key == area_id)
        self.canvas.blockSignals(False)
        if area_id in self.items_by_id:
            self.ensureVisible(self.items_by_id[area_id], 30, 30)

    def fit_width(self):
        if self.bounds.width():
            self.resetTransform()
            scale = max(.2, (self.viewport().width()-48) / self.bounds.width())
            self.scale(scale, scale)
            self.zoomChanged.emit(scale)
            self.schedule_detail()

    def zoom(self, multiplier):
        scale = self.transform().m11() * multiplier
        if .2 <= scale <= 5:
            self.scale(multiplier, multiplier)
            self.zoomChanged.emit(scale)
            self.schedule_detail()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'preview_timer'):
            self.schedule_detail()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.25 if event.angleDelta().y() > 0 else .8)
            event.accept()
        else:
            super().wheelEvent(event)

    def draw_mode(self, enabled):
        self.drawing = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        for item in self.items_by_id.values():
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton if enabled else Qt.MouseButton.LeftButton)

    def mousePressEvent(self, event):
        if self.drawing and event.button() == Qt.MouseButton.LeftButton:
            point = self.mapToScene(event.position().toPoint())
            if self.bounds.contains(point):
                self.start = point
                self.rubber = self.canvas.addRect(QRectF(point, point), QPen(QColor('#275a42'), 1), QBrush(QColor(91, 151, 96, 70)))
                self.rubber.setZValue(2)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start is not None and self.rubber:
            point = self.mapToScene(event.position().toPoint())
            self.rubber.setRect(QRectF(self.start, point).normalized().intersected(self.bounds))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.start is not None and self.rubber:
            rect = self.rubber.rect()
            self.canvas.removeItem(self.rubber)
            self.rubber = None
            self.start = None
            if rect.width() >= 2 and rect.height() >= 2:
                self.created.emit([rect.left(), rect.top(), rect.right(), rect.bottom()])
            return
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        load_fonts()
        self.setWindowTitle('Doc Anon · Documenti, sotto il tuo controllo')
        self.setWindowIcon(QIcon(str(APP_ROOT / 'assets/doc-anon.ico')))
        self.resize(1440, 920)
        self.setMinimumSize(1080, 720)
        self.detector = Detector()
        self.doc = None
        self.page = 0
        self.selected_id = ''
        self.undo_stack = []
        self.job = None
        self.result_callback = None
        self.last_exports = []
        self.refreshing = False
        self.exported = False
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName('header')
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(27, 18, 27, 18)
        header_layout.addWidget(label('doc anon.', 'brand'))
        header_layout.addSpacing(18)
        header_layout.addWidget(label('IL TUO ARCHIVIO. LA TUA PRIVACY.', 'eyebrow'))
        header_layout.addStretch()
        self.badge = label('ELABORAZIONE LOCALE', 'badge')
        header_layout.addWidget(self.badge)
        self.resources_button = button('Risorse', self.show_resources)
        header_layout.addWidget(self.resources_button)
        layout.addWidget(header)
        self.author_banner = QFrame()
        self.author_banner.setObjectName('authorBanner')
        author_layout = QVBoxLayout(self.author_banner)
        author_layout.setContentsMargins(27, 10, 27, 10)
        author_layout.setSpacing(4)
        for text, name in [
            ('Software freeware fatto da: Andrea Battellocchi - Docente Informatica - Consulente Informatico', 'authorName'),
            ('(andrea.battellocchi@gmail.com per richiedere consulenze e sviluppo software personalizzato)', 'authorContact'),
        ]:
            author_label = label(text, name, wrap=True)
            author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            author_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            author_layout.addWidget(author_label)
        layout.addWidget(self.author_banner)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.home = self.make_home()
        self.editor = self.make_editor()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.editor)
        self.activity = QFrame()
        activity_layout = QVBoxLayout(self.activity)
        activity_layout.setContentsMargins(28, 8, 28, 16)
        row = QHBoxLayout()
        self.activity_text = label('Tutti i documenti vengono elaborati su questo computer.', 'muted')
        row.addWidget(self.activity_text, 1)
        self.cancel_button = button('Annulla operazione', self.cancel_job)
        self.cancel_button.hide()
        row.addWidget(self.cancel_button)
        row.addWidget(label('v' + __version__, 'muted'))
        activity_layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        activity_layout.addWidget(self.progress)
        layout.addWidget(self.activity)
        self.update_home()
        for keys, action in [('Ctrl+O', self.choose_file), ('Ctrl+Z', self.undo), ('Ctrl+S', self.export_files)]:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(action)

    def make_home(self):
        home = QWidget()
        outer = QHBoxLayout(home)
        outer.setContentsMargins(64, 24, 64, 24)
        text = QVBoxLayout()
        text.addStretch()
        text.addWidget(label('01 / PREPARA IL TUO SPAZIO', 'eyebrow'))
        text.addSpacing(18)
        text.addWidget(label('I tuoi documenti.\nSolo sul tuo PC.', 'hero'))
        text.addSpacing(20)
        intro = label('Oscura i dati personali, controlla ogni dettaglio\ne salva due copie pronte da condividere.', 'subhead', True)
        text.addWidget(intro)
        text.addSpacing(28)
        for number, title, detail in [('01', 'Apri il documento', 'PDF, scansioni, TXT e Markdown.'),
                                      ('02', 'Decidi cosa oscurare', 'Rivedi, correggi e aggiungi le selezioni.'),
                                      ('03', 'Salva le due versioni', 'Lite con iniziali e anonima con omissioni.')]:
            row = QHBoxLayout()
            row.addWidget(label(number, 'eyebrow'))
            row.addSpacing(14)
            col = QVBoxLayout()
            col.addWidget(label(title, 'title'))
            col.addWidget(label(detail, 'muted'))
            row.addLayout(col, 1)
            text.addLayout(row)
            text.addSpacing(14)
        text.addStretch()
        outer.addLayout(text, 5)
        outer.addSpacing(60)
        card = QFrame()
        card.setObjectName('panel')
        card.setMaximumWidth(460)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.addWidget(label('MOTORE LOCALE', 'eyebrow'))
        card_layout.addSpacing(18)
        self.home_title = label('Un solo download.\nPoi lavori offline.', 'brand', True)
        card_layout.addWidget(self.home_title)
        card_layout.addSpacing(20)
        self.home_description = label('', 'subhead', True)
        card_layout.addWidget(self.home_description)
        card_layout.addSpacing(22)
        self.home_action = button('Scarica e prepara', self.home_clicked, True)
        self.home_action.setMinimumHeight(48)
        card_layout.addWidget(self.home_action)
        self.verify_button = button('Verifica / ripara risorse', self.prepare_resources)
        card_layout.addWidget(self.verify_button)
        self.return_button = button('Torna al documento', lambda: self.stack.setCurrentWidget(self.editor))
        card_layout.addWidget(self.return_button)
        card_layout.addSpacing(16)
        card_layout.addWidget(label('Nessun account · Nessuna chiave API\nNessun caricamento dei documenti', 'muted', True))
        card_layout.addSpacing(22)
        self.path_label = label('', 'muted', True)
        card_layout.addWidget(self.path_label)
        card_layout.addStretch()
        right = QVBoxLayout()
        right.addStretch()
        right.addWidget(card)
        right.addStretch()
        outer.addLayout(right, 4)
        return home

    def make_editor(self):
        editor = QWidget()
        layout = QVBoxLayout(editor)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(14)
        top = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label('02 / REVISIONE DEL DOCUMENTO', 'eyebrow'))
        self.filename = label('', 'title')
        titles.addWidget(self.filename)
        top.addLayout(titles, 1)
        self.open_button = button('Apri un altro file', self.choose_file)
        top.addWidget(self.open_button)
        self.export_button = button('Esporta le due copie', self.export_files, True)
        top.addWidget(self.export_button)
        layout.addLayout(top)
        quality_row = QHBoxLayout()
        quality_row.addWidget(label('QUALITÀ PDF', 'eyebrow'))
        self.quality_combo = QualityCombo()
        self.quality_combo.setAccessibleName('Qualità del PDF esportato')
        self.quality_combo.addItem('Compatta · 150 DPI', 150)
        self.quality_combo.addItem('Standard · 300 DPI', 300)
        self.quality_combo.addItem('Alta · 600 DPI', 600)
        self.quality_combo.setCurrentIndex(1)
        self.quality_combo.setMinimumWidth(220)
        quality_row.addWidget(self.quality_combo)
        self.quality_hint = label('Per lettura e stampa: equilibrio tra nitidezza e dimensione.', 'muted', True)
        quality_row.addWidget(self.quality_hint, 1)
        self.quality_combo.currentIndexChanged.connect(self.update_quality_hint)
        layout.addLayout(quality_row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QFrame()
        left.setObjectName('panel')
        left.setMinimumWidth(145)
        left.setMaximumWidth(230)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 18, 14, 14)
        left_layout.addWidget(label('PAGINE', 'eyebrow'))
        self.page_list = QListWidget()
        self.page_list.currentRowChanged.connect(self.change_page)
        left_layout.addWidget(self.page_list)
        self.page_check = QCheckBox('Pagina controllata')
        self.page_check.toggled.connect(self.check_page)
        left_layout.addWidget(self.page_check)
        splitter.addWidget(left)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(12, 0, 12, 0)
        center_layout.setSpacing(8)
        toolbar = QHBoxLayout()
        self.draw_button = button('+ Area manuale', lambda: None)
        self.draw_button.setCheckable(True)
        self.draw_button.toggled.connect(self.toggle_draw)
        toolbar.addWidget(self.draw_button)
        self.undo_button = button('Annulla modifica', self.undo)
        toolbar.addWidget(self.undo_button)
        toolbar.addStretch()
        toolbar.addWidget(button('−', lambda: self.view.zoom(.8)))
        self.zoom_label = label('100%', 'muted')
        self.zoom_label.setMinimumWidth(40)
        toolbar.addWidget(self.zoom_label)
        toolbar.addWidget(button('+', lambda: self.view.zoom(1.25)))
        toolbar.addWidget(button('Adatta', lambda: self.view.fit_width()))
        center_layout.addLayout(toolbar)
        self.view = PageView()
        self.view.created.connect(self.add_area)
        self.view.selected.connect(self.select_area)
        self.view.moved.connect(self.move_area)
        self.view.detailRequested.connect(self.refresh_preview_detail)
        self.view.zoomChanged.connect(lambda scale: self.zoom_label.setText(f'{round(scale*100)}%'))
        center_layout.addWidget(self.view, 1)
        self.page_warning = label('', 'muted', True)
        center_layout.addWidget(self.page_warning)
        splitter.addWidget(center)
        right = QFrame()
        right.setObjectName('panel')
        right.setMinimumWidth(275)
        right.setMaximumWidth(360)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(18, 18, 18, 18)
        self.selection_count = label('SELEZIONI', 'eyebrow')
        right_layout.addWidget(self.selection_count)
        self.area_list = QListWidget()
        self.area_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area_list.currentItemChanged.connect(self.list_selected)
        right_layout.addWidget(self.area_list, 1)
        self.inspector = QWidget()
        fields = QVBoxLayout(self.inspector)
        fields.setContentsMargins(0, 8, 0, 0)
        fields.addWidget(label('SOSTITUZIONE NELLA COPIA LITE', 'eyebrow'))
        self.lite_input = QLineEdit()
        self.lite_input.setPlaceholderText('A.B. oppure [omesso]')
        self.lite_input.editingFinished.connect(self.update_lite)
        fields.addWidget(self.lite_input)
        fields.addWidget(label('Nella copia anonima: [omesso]', 'muted'))
        geometry = QFormLayout()
        self.coordinates = []
        for title in ['Posizione X', 'Posizione Y', 'Larghezza', 'Altezza']:
            field = QDoubleSpinBox()
            field.setDecimals(1)
            field.setRange(0, 20000)
            field.setSuffix(' pt')
            field.setKeyboardTracking(False)
            field.editingFinished.connect(self.update_geometry)
            geometry.addRow(title, field)
            self.coordinates.append(field)
        fields.addLayout(geometry)
        fields.addWidget(label('Trascina l’area sulla pagina per spostarla.', 'muted', True))
        remove = button('Rimuovi oscuramento', self.remove_area)
        remove.setObjectName('danger')
        fields.addWidget(remove)
        right_layout.addWidget(self.inspector)
        self.inspector.hide()
        splitter.addWidget(right)
        splitter.setSizes([170, 830, 300])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        footer = QFrame()
        footer.setObjectName('notice')
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(15, 12, 15, 12)
        self.approval = QCheckBox('Ho controllato tutte le pagine e gli oscuramenti.')
        self.approval.toggled.connect(self.update_export_button)
        footer_layout.addWidget(self.approval, 1)
        self.open_output = button('Apri cartella esportata', self.open_export_folder)
        self.open_output.hide()
        footer_layout.addWidget(self.open_output)
        footer_layout.addWidget(label('L’originale rimane invariato.', 'muted'))
        layout.addWidget(footer)
        return editor

    def update_home(self):
        ready = is_ready()
        self.home_title.setText('Pronto.\nAnche senza Internet.' if ready else 'Un solo download.\nPoi lavori offline.')
        self.home_description.setText(
            'Modello italiano e OCR sono disponibili su questo computer. Apri un documento per iniziare la revisione.' if ready else
            'Scarica il modello italiano Rizzo e i dati OCR: circa 1,3 GB. Il download è riprendibile. Poi puoi scollegare Internet.')
        self.home_action.setText('Apri un documento' if ready else 'Scarica e prepara')
        self.verify_button.setVisible(ready)
        self.return_button.setVisible(self.doc is not None)
        self.path_label.setText('Risorse salvate in:\n' + str(data_root()))

    def home_clicked(self):
        if is_ready():
            self.choose_file()
        else:
            self.prepare_resources()

    def show_resources(self):
        if self.job:
            return
        self.update_home()
        self.stack.setCurrentWidget(self.home)

    def prepare_resources(self):
        if not self.job:
            self.start_job(prepare, lambda _: self.resources_done())

    def resources_done(self):
        self.detector = Detector()
        self.update_home()
        self.activity_text.setText('Preparazione completata. Puoi scollegare Internet e aprire un documento.')

    def choose_file(self):
        if self.job:
            return
        if not is_ready():
            self.show_resources()
            return
        if self.doc and not self.exported:
            answer = QMessageBox.question(self, 'Aprire un altro documento?',
                'La revisione corrente non è stata esportata. Aprendo un altro file verrà sostituita.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        path, _ = QFileDialog.getOpenFileName(self, 'Scegli il documento', '', 'Documenti (*.pdf *.txt *.md *.markdown)')
        if path:
            self.start_job(lambda progress: Document.open(path, self.detector, progress), self.document_loaded)

    def document_loaded(self, doc):
        self.doc = doc
        self.page = 0
        self.selected_id = ''
        self.undo_stack = []
        self.exported = False
        self.last_exports = []
        self.open_output.hide()
        self.filename.setText(doc.path.name)
        self.update_quality_hint()
        self.approval.setChecked(False)
        self.stack.setCurrentWidget(self.editor)
        self.populate_pages()
        self.page_list.setCurrentRow(0)
        self.display_page()
        self.activity_text.setText(f"{len(doc.review['redactions'])} aree proposte · {len(doc.review['pages'])} pagine · {doc.review['ocr_pages']} pagine con OCR. Controlla anche firme e scrittura a mano.")

    def populate_pages(self):
        if not self.doc:
            return
        self.page_list.blockSignals(True)
        self.page_list.clear()
        for i in range(len(self.doc.review['pages'])):
            count = sum(a['page'] == i for a in self.doc.review['redactions'])
            checked = '✓  ' if i in self.doc.review['checked_pages'] else ''
            self.page_list.addItem(f'{checked}Pagina {i+1:02d}\n{count} aree')
        self.page_list.setCurrentRow(self.page)
        self.page_list.blockSignals(False)

    def change_page(self, number):
        if not self.doc or number < 0:
            return
        self.page = number
        self.selected_id = ''
        self.display_page()

    def display_page(self):
        if not self.doc:
            return
        info = self.doc.review['pages'][self.page]
        try:
            self.view.display(self.doc.page_region(self.page), info['width'], info['height'], self.page_areas())
        except Exception:
            self.error('Anteprima non disponibile per questa pagina.')
            return
        self.draw_button.setChecked(False)
        self.page_warning.setText(' '.join(info['warnings']) or 'Controlla le aree evidenziate. Aggiungi manualmente eventuali dati non riconosciuti.')
        self.page_check.blockSignals(True)
        self.page_check.setChecked(self.page in self.doc.review['checked_pages'])
        self.page_check.blockSignals(False)
        self.refresh_areas()

    def refresh_preview_detail(self):
        # PyMuPDF is used serially: never render here while an analysis/export job runs.
        if not self.doc or self.job is not None or self.stack.currentWidget() != self.editor:
            return
        request = self.view.detail_request()
        if request is None:
            return
        scale, clip = request
        key = (id(self.doc), self.page, scale, tuple(clip))
        if key == self.view.detail_key:
            return
        try:
            rendered = self.doc.page_region(self.page, scale, clip)
            self.view.set_detail(rendered, key)
        except Exception:
            self.activity_text.setText('Dettaglio anteprima non disponibile. Prova a ridurre lo zoom.')

    def update_quality_hint(self, *_):
        dpi = self.quality_combo.currentData()
        descriptions = {150: 'File più leggeri, per consultazione e invio.',
                        300: 'Per lettura e stampa: equilibrio tra nitidezza e dimensione.',
                        600: 'Massimo dettaglio. File più grandi, più tempo e memoria.'}
        text = descriptions[dpi]
        if self.doc:
            note = export_resolution_note(self.doc.review['pages'], dpi)
            if note:
                text += ' ' + note
        self.quality_hint.setText(text)
        self.export_button.setToolTip(f'Esporta entrambe le copie a {dpi} DPI')

    def page_areas(self):
        return [area for area in self.doc.review['redactions'] if area['page'] == self.page]

    def refresh_areas(self):
        self.area_list.blockSignals(True)
        self.area_list.clear()
        areas = self.page_areas()
        for area in areas:
            text = area.get('text', 'Area manuale').replace('\n', ' ')
            item = QListWidgetItem(f"{area['label']}\n{text[:65]}")
            item.setData(Qt.ItemDataRole.UserRole, area['id'])
            item.setToolTip(text)
            self.area_list.addItem(item)
            if area['id'] == self.selected_id:
                self.area_list.setCurrentItem(item)
        self.area_list.blockSignals(False)
        self.selection_count.setText(f'SELEZIONI IN QUESTA PAGINA · {len(areas)}')
        self.view.set_areas(areas, self.selected_id)
        self.view.draw_mode(self.draw_button.isChecked())
        self.update_inspector()
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.update_export_button()

    def selected_area(self):
        return next((a for a in self.page_areas() if a['id'] == self.selected_id), None) if self.doc else None

    def list_selected(self, item, _previous):
        self.select_area(item.data(Qt.ItemDataRole.UserRole) if item else '')

    def select_area(self, area_id):
        self.selected_id = area_id
        self.view.select(area_id)
        self.area_list.blockSignals(True)
        for n in range(self.area_list.count()):
            item = self.area_list.item(n)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) == area_id)
        self.area_list.blockSignals(False)
        self.update_inspector()

    def update_inspector(self):
        area = self.selected_area()
        self.inspector.setVisible(area is not None)
        if not area:
            return
        self.refreshing = True
        self.lite_input.setText(area['lite'])
        x0, y0, x1, y1 = area['rect']
        for field, value in zip(self.coordinates, [x0, y0, x1-x0, y1-y0]):
            field.setValue(value)
        self.refreshing = False

    def snapshot(self):
        self.undo_stack.append(copy.deepcopy(self.doc.review))
        self.undo_stack = self.undo_stack[-30:]
        self.doc.review['checked_pages'] = [p for p in self.doc.review['checked_pages'] if p != self.page]
        self.page_check.setChecked(False)
        self.approval.setChecked(False)
        self.exported = False
        self.open_output.hide()

    def after_edit(self):
        self.populate_pages()
        self.refresh_areas()

    def toggle_draw(self, enabled):
        self.view.draw_mode(enabled)
        if enabled:
            self.activity_text.setText('Disegna un rettangolo trascinando sulla pagina. Per modificare un’area esistente, disattiva Area manuale.')

    def add_area(self, rect):
        if not self.doc:
            return
        self.snapshot()
        area_id = str(uuid.uuid4())
        self.doc.review['redactions'].append({'id': area_id, 'page': self.page, 'rect': rect,
            'label': 'MANUALE', 'text': 'Area manuale', 'lite': '[omesso]', 'source': 'manuale'})
        self.selected_id = area_id
        self.draw_button.setChecked(False)
        self.after_edit()

    def move_area(self, area_id, rect):
        area = next(a for a in self.page_areas() if a['id'] == area_id)
        if area['rect'] == rect:
            return
        self.snapshot()
        area['rect'] = rect
        self.selected_id = area_id
        # The graphics item is delivering its release event. Rebuild after that event finishes.
        QTimer.singleShot(0, self.after_edit)

    def update_geometry(self):
        area = self.selected_area()
        if self.refreshing or not area:
            return
        x, y, width, height = [f.value() for f in self.coordinates]
        page = self.doc.review['pages'][self.page]
        if width < 2 or height < 2 or x+width > page['width'] or y+height > page['height']:
            self.update_inspector()
            self.activity_text.setText('L’area deve rimanere nella pagina e misurare almeno 2 × 2 punti.')
            return
        rect = [x, y, x+width, y+height]
        if max(abs(a-b) for a, b in zip(rect, area['rect'])) < .15:
            return
        self.snapshot()
        area['rect'] = rect
        self.after_edit()

    def update_lite(self):
        import re
        area = self.selected_area()
        if self.refreshing or not area:
            return
        value = self.lite_input.text().strip()
        if value == area['lite']:
            return
        if not re.fullmatch(r'(?:[A-ZÀ-Ý]\.){1,12}|\[omesso\]', value):
            self.lite_input.setText(area['lite'])
            self.activity_text.setText('Usa iniziali maiuscole con punti, per esempio A.B., oppure [omesso].')
            return
        self.snapshot()
        area['lite'] = value
        self.after_edit()

    def remove_area(self):
        if not self.selected_area():
            return
        self.snapshot()
        self.doc.review['redactions'] = [a for a in self.doc.review['redactions'] if a['id'] != self.selected_id]
        self.selected_id = ''
        self.after_edit()

    def undo(self):
        if self.job or not self.undo_stack:
            return
        self.doc.review = self.undo_stack.pop()
        self.selected_id = ''
        self.approval.setChecked(False)
        self.exported = False
        self.open_output.hide()
        self.populate_pages()
        self.display_page()

    def check_page(self, checked):
        if not self.doc:
            return
        pages = self.doc.review['checked_pages']
        if checked and self.page not in pages:
            pages.append(self.page)
        elif not checked and self.page in pages:
            pages.remove(self.page)
        self.populate_pages()

    def update_export_button(self):
        self.export_button.setEnabled(self.doc is not None and self.approval.isChecked() and self.job is None)

    def export_files(self):
        if self.job or not self.doc or not self.approval.isChecked():
            return
        folder = QFileDialog.getExistingDirectory(self, 'Dove salvare le due copie?', str(self.doc.path.parent))
        if folder:
            review = copy.deepcopy(self.doc.review)
            dpi = self.quality_combo.currentData()
            self.start_job(lambda progress: self.doc.export(folder, review, progress, dpi=dpi), self.export_done)

    def export_done(self, paths):
        self.last_exports = paths
        self.exported = True
        self.open_output.show()
        self.activity_text.setText('Due copie salvate in: ' + str(Path(paths[0]).parent))

    def open_export_folder(self):
        if self.last_exports:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_exports[0]).parent)))

    def start_job(self, work, callback):
        if self.job:
            return
        self.job = Job(work, self)
        self.view.preview_timer.stop()
        self.result_callback = callback
        self._job_result = None
        self._job_error = None
        self._job_cancelled = False
        self.stack.setEnabled(False)
        self.resources_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.activity_text.setText('Preparazione…')
        self.job.progress.connect(self.on_progress)
        self.job.result.connect(self.store_result)
        self.job.failed.connect(self.store_error)
        self.job.cancelled.connect(self.store_cancelled)
        self.job.finished.connect(self.finish_job)
        self.job.start()

    def store_result(self, value):
        self._job_result = value

    def store_error(self, value):
        self._job_error = value

    def store_cancelled(self):
        self._job_cancelled = True

    def on_progress(self, message, done, total):
        self.activity_text.setText(message)
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def cancel_job(self):
        if self.job:
            self.job.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.activity_text.setText('Annullamento in corso… attendo la fine del blocco corrente.')

    def finish_job(self):
        job = self.job
        self.job = None
        self.stack.setEnabled(True)
        self.resources_button.setEnabled(True)
        self.progress.hide()
        self.cancel_button.hide()
        if self._job_error:
            self.error(self._job_error)
        elif self._job_cancelled:
            self.activity_text.setText('Operazione annullata. Puoi riprendere quando vuoi.')
        else:
            try:
                self.result_callback(self._job_result)
            except Exception as exc:
                self.error(str(exc))
        job.deleteLater()
        self.update_export_button()
        self.view.schedule_detail()

    def error(self, message):
        self.activity_text.setText(message)
        QMessageBox.warning(self, 'Doc Anon', message)

    def closeEvent(self, event):
        if self.job:
            self.cancel_job()
            self.activity_text.setText('Annullamento in corso. Chiudi nuovamente quando l’operazione è terminata.')
            event.ignore()
            return
        if self.doc and not self.exported:
            answer = QMessageBox.question(self, 'Chiudere senza esportare?',
                'Le modifiche di revisione sono in memoria. Vuoi chiudere senza esportare le due copie?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.view.preview_timer.stop()
        event.accept()


def main():
    configure_offline()
    app = QApplication(sys.argv)
    app.setApplicationName('Doc Anon')
    app.setOrganizationName('DocAnon')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
