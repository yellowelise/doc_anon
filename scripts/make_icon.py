from pathlib import Path
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QPainterPath

root = Path(__file__).resolve().parents[1]
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(QColor(0, 0, 0, 0))
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setPen(QColor('#244e3c'))
painter.setBrush(QColor('#244e3c'))
painter.drawRoundedRect(QRectF(4, 4, 248, 248), 52, 52)
painter.setPen(QColor('#f4f3ed'))
painter.setBrush(QColor('#f4f3ed'))
painter.drawRoundedRect(QRectF(67, 40, 122, 176), 9, 9)
painter.setBrush(QColor('#b2c59e'))
painter.setPen(QColor('#b2c59e'))
painter.drawRoundedRect(QRectF(89, 70, 78, 8), 3, 3)
painter.setBrush(QColor('#244e3c'))
painter.setPen(QColor('#244e3c'))
for y, width in [(101, 78), (126, 60), (151, 78)]:
    painter.drawRoundedRect(QRectF(89, y, width, 13), 2, 2)
painter.setBrush(QColor('#c98d45'))
painter.setPen(QColor('#c98d45'))
painter.drawEllipse(QRectF(158, 175, 51, 51))
painter.end()
(root / 'assets').mkdir(exist_ok=True)
assert image.save(str(root / 'assets/doc-anon.ico'), 'ICO')
assert image.save(str(root / 'assets/doc-anon.png'), 'PNG')
