import sys
import os
import time
from ui.main_window import MainWindow

from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QSplitter, QFrame, QFileDialog, QMessageBox,
    QSpacerItem, QSizePolicy, QDialog
)
from PyQt6.QtGui import (
    QAction, QIcon, QPixmap, QPalette, QBrush, QPainter, QColor, QImage,
    QPainterPath
)
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QRect

from config_manager import ConfigManager
from ui.settings_dialog import SettingsDialog
from image_processor import ImageProcessor
from utils.utils import (
    PILLOW_AVAILABLE, pil_to_qpixmap, crop_image_to_circle,
    check_dependencies_availability
)

if PILLOW_AVAILABLE:
    from PIL import Image, UnidentifiedImageError

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()