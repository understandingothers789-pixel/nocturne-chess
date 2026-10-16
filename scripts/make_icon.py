"""Render our original SVG to a multi-resolution Windows ICO, using Qt only."""

from pathlib import Path
import struct

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


def main():
    app = QApplication.instance() or QApplication([])
    assets = Path(__file__).resolve().parents[1] / "src" / "nocturne" / "assets"
    renderer = QSvgRenderer(str(assets / "icon.svg"))
    if not renderer.isValid():
        raise RuntimeError("Application icon is not a valid SVG")
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = []
    for size in sizes:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Qt could not encode the application icon")
        images.append(bytes(data))
    offset = 6 + 16 * len(sizes)
    directory = struct.pack("<HHH", 0, 1, len(sizes))
    for size, data in zip(sizes, images):
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    (assets / "icon.ico").write_bytes(directory + b"".join(images))
    print("Created", assets / "icon.ico")
    return app


if __name__ == "__main__":
    main()
