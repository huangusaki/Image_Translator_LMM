import sys
import os
import time
import threading
import math
import io
from PyQt6.QtWidgets import (
    QMainWindow,
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QFrame,
    QFileDialog,
    QMessageBox,
    QSpacerItem,
    QSizePolicy,
    QDialog,
    QProgressBar,
    QTextEdit,
    QLineEdit,
    QDoubleSpinBox,
    QToolButton,
    QMenu,
    QColorDialog,
    QSpinBox,
)
from PyQt6.QtGui import (
    QAction,
    QIcon,
    QPixmap,
    QPalette,
    QBrush,
    QPainter,
    QColor,
    QImage,
    QPen,
    QTransform,
    QFont,
    QFontMetrics,
    QPainterPath,
    QPolygonF,
    QMouseEvent,
    QWheelEvent,
    QContextMenuEvent,
    QCursor,
    QResizeEvent,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSlot,
    QSize,
    QThread,
    pyqtSignal,
    QPointF,
    QRectF,
    QLineF,
    QEvent,
    QBuffer,
    QIODevice,
    QTimer,
)
from config_manager import ConfigManager
from image_processor import ImageProcessor, ProcessedBlock
from utils.utils import (
    PILLOW_AVAILABLE,
    pil_to_qpixmap,
    crop_image_to_circle,
    check_dependencies_availability,
    draw_processed_blocks_pil,
    _render_single_block_pil_for_preview,
)
from utils.font_utils import find_font_path
from ui.glossary_settings_dialog import GlossarySettingsDialog
from ui.settings_dialog import SettingsDialog
from ui.text_style_settings_dialog import TextStyleSettingsDialog
from ui.text_detail_panel import TextDetailPanel

if PILLOW_AVAILABLE:
    from PIL import Image, UnidentifiedImageError, ImageDraw, ImageFont as PILImageFont
CORNER_HANDLE_SIZE = 10
ROTATION_HANDLE_OFFSET = 20


class EditableTextDialog(QDialog):
    def __init__(self, initial_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑文本")
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlainText(initial_text)
        layout.addWidget(self.text_edit)
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("确定", self)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("取消", self)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def get_text(self):
        return self.text_edit.toPlainText()


class InteractiveLabel(QWidget):
    block_modified_signal = pyqtSignal(object)
    selection_changed_signal = pyqtSignal(object)

    def _scale_background_and_view(self):
        if self.background_pixmap and not self.background_pixmap.isNull():
            widget_size = self.size()
            img_size = self.background_pixmap.size()
            if (
                img_size.width() <= 0
                or img_size.height() <= 0
                or widget_size.width() <= 0
                or widget_size.height() <= 0
            ):
                self.scaled_background_pixmap = None
                self.current_scale_factor = 1.0
                self.update()
                return
            scale_x = widget_size.width() / img_size.width()
            scale_y = widget_size.height() / img_size.height()
            self.current_scale_factor = min(scale_x, scale_y)
            scaled_width = int(img_size.width() * self.current_scale_factor)
            scaled_height = int(img_size.height() * self.current_scale_factor)
            if scaled_width > 0 and scaled_height > 0:
                self.scaled_background_pixmap = self.background_pixmap.scaled(
                    scaled_width,
                    scaled_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            else:
                self.scaled_background_pixmap = None
        else:
            self.scaled_background_pixmap = None
            self.current_scale_factor = 1.0
        self.update()

    def set_background_image(self, pixmap: QPixmap | None):
        """Sets the background image for the interactive area."""
        self.background_pixmap = pixmap
        self.pan_offset = QPointF(0, 0)
        self._scale_background_and_view()
        self.update()

    def clear_all(self):
        """Resets the interactive area completely."""
        self.background_pixmap = None
        self.scaled_background_pixmap = None
        self.processed_blocks = []
        self.set_selected_block(None)
        self._invalidate_block_cache()
        self.current_scale_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.dragging_block = False
        self.resizing_block = False
        self.rotating_block = False
        self.initial_block_bbox_on_drag = None
        self.initial_mouse_pos_on_drag = None
        self.resize_anchor_opposite_corner_orig = None
        self.resize_corner = -1
        self.rotation_center_on_rotate = QPointF()
        self.update()

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setMinimumSize(300, 300)
        self.background_pixmap: QPixmap | None = None
        self.scaled_background_pixmap: QPixmap | None = None
        self.processed_blocks: list[ProcessedBlock] = []
        self.selected_block: ProcessedBlock | None = None
        self._block_render_cache: dict[str, tuple[int, QPixmap]] = {}
        self.current_scale_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.dragging_block = False
        self.resizing_block = False
        self.rotating_block = False
        self.drag_offset = QPointF()
        self.resize_corner = -1
        self.initial_block_bbox_on_drag: list[float] | None = None
        self.initial_mouse_pos_on_drag: QPointF | None = None
        self.initial_angle_on_rotate = 0.0
        self.rotation_center_on_rotate = QPointF()
        self.resize_anchor_opposite_corner_orig: QPointF | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.font_size_mapping = {}
        self.reload_style_configs()
        self.update()

    def _parse_color_str(self, color_str: str, default_color_tuple: tuple) -> tuple:
        try:
            parts = list(map(int, color_str.split(",")))
            if len(parts) == 3:
                return (parts[0], parts[1], parts[2], 255)
            if len(parts) == 4:
                return (parts[0], parts[1], parts[2], parts[3])
        except:
            pass
        return default_color_tuple

    def reload_style_configs(self):
        self._font_name_config = self.config_manager.get("UI", "font_name", "msyh.ttc")
        self._text_main_color_pil = self._parse_color_str(
            self.config_manager.get("UI", "text_main_color", "255,255,255,255"),
            (255, 255, 255, 255),
        )
        self._text_outline_color_pil = self._parse_color_str(
            self.config_manager.get("UI", "text_outline_color", "0,0,0,255"),
            (0, 0, 0, 255),
        )
        self._text_bg_color_pil = self._parse_color_str(
            self.config_manager.get("UI", "text_background_color", "0,0,0,128"),
            (0, 0, 0, 128),
        )
        self._outline_thickness = self.config_manager.getint(
            "UI", "text_outline_thickness", 2
        )
        self._text_padding = self.config_manager.getint("UI", "text_padding", 3)
        self._h_char_spacing_px = self.config_manager.getint(
            "UI", "h_text_char_spacing_px", 0
        )
        self._h_line_spacing_px = self.config_manager.getint(
            "UI", "h_text_line_spacing_px", 0
        )
        self._v_char_spacing_px = self.config_manager.getint(
            "UI", "v_text_char_spacing_px", 0
        )
        self._v_col_spacing_px = self.config_manager.getint(
            "UI", "v_text_column_spacing_px", 0
        )
        self._h_manual_break_extra_px = self.config_manager.getint(
            "UI", "h_manual_break_extra_spacing_px", 0
        )
        self._v_manual_break_extra_px = self.config_manager.getint(
            "UI", "v_manual_break_extra_spacing_px", 0
        )
        self.font_size_mapping = {
            "very_small": self.config_manager.getint(
                "FontSizeMapping", "very_small", 12
            ),
            "small": self.config_manager.getint("FontSizeMapping", "small", 16),
            "medium": self.config_manager.getint("FontSizeMapping", "medium", 22),
            "large": self.config_manager.getint("FontSizeMapping", "large", 28),
            "very_large": self.config_manager.getint(
                "FontSizeMapping", "very_large", 36
            ),
        }
        fixed_font_size_override = self.config_manager.getint(
            "UI", "fixed_font_size", 0
        )
        for block_item in self.processed_blocks:
            if fixed_font_size_override > 0:
                block_item.font_size_pixels = fixed_font_size_override
            else:
                block_item.font_size_pixels = self.font_size_mapping.get(
                    block_item.font_size_category,
                    self.font_size_mapping.get("medium", 22),
                )
            if not hasattr(block_item, "main_color"):
                block_item.main_color = None
            if not hasattr(block_item, "outline_color"):
                block_item.outline_color = None
            if not hasattr(block_item, "background_color"):
                block_item.background_color = None
            if not hasattr(block_item, "outline_thickness"):
                block_item.outline_thickness = None
            self._invalidate_block_cache(block_item)
        self.update()

    def _invalidate_block_cache(self, block: ProcessedBlock | None = None):
        if block and hasattr(block, "id"):
            self._block_render_cache.pop(block.id, None)
        else:
            self._block_render_cache.clear()
        self.update()

    def _get_block_visual_hash(self, block: ProcessedBlock) -> int:
        main_color_to_hash = (
            block.main_color
            if hasattr(block, "main_color") and block.main_color is not None
            else self._text_main_color_pil
        )
        outline_color_to_hash = (
            block.outline_color
            if hasattr(block, "outline_color") and block.outline_color is not None
            else self._text_outline_color_pil
        )
        bg_color_to_hash = (
            block.background_color
            if hasattr(block, "background_color") and block.background_color is not None
            else self._text_bg_color_pil
        )
        outline_thickness_to_hash = (
            block.outline_thickness
            if hasattr(block, "outline_thickness")
            and block.outline_thickness is not None
            else self._outline_thickness
        )
        relevant_attrs = (
            block.translated_text,
            block.font_size_pixels,
            block.orientation,
            block.text_align,
            tuple(block.bbox) if block.bbox else None,
            self._font_name_config,
            main_color_to_hash,
            outline_color_to_hash,
            bg_color_to_hash,
            outline_thickness_to_hash,
            self._text_padding,
            self._h_char_spacing_px,
            self._h_line_spacing_px,
            self._v_char_spacing_px,
            self._v_col_spacing_px,
            self._h_manual_break_extra_px,
            self._v_manual_break_extra_px,
        )
        return hash(relevant_attrs)

    def _get_or_render_block_qpixmap(self, block: ProcessedBlock) -> QPixmap | None:
        if not PILLOW_AVAILABLE or not hasattr(block, "id"):
            return None
        block_id = block.id
        current_version_hash = self._get_block_visual_hash(block)
        if block_id in self._block_render_cache:
            cached_version_hash, cached_pixmap = self._block_render_cache[block_id]
            if (
                cached_version_hash == current_version_hash
                and not cached_pixmap.isNull()
            ):
                return cached_pixmap
        main_color = (
            block.main_color
            if hasattr(block, "main_color") and block.main_color is not None
            else self._text_main_color_pil
        )
        outline_color = (
            block.outline_color
            if hasattr(block, "outline_color") and block.outline_color is not None
            else self._text_outline_color_pil
        )
        bg_color = (
            block.background_color
            if hasattr(block, "background_color") and block.background_color is not None
            else self._text_bg_color_pil
        )
        thickness = (
            block.outline_thickness
            if hasattr(block, "outline_thickness")
            and block.outline_thickness is not None
            else self._outline_thickness
        )
        pil_image = _render_single_block_pil_for_preview(
            block=block,
            font_name_config=self._font_name_config,
            text_main_color_pil=main_color,
            text_outline_color_pil=outline_color,
            text_bg_color_pil=bg_color,
            outline_thickness=thickness,
            text_padding=self._text_padding,
            h_char_spacing_px=self._h_char_spacing_px,
            h_line_spacing_px=self._h_line_spacing_px,
            v_char_spacing_px=self._v_char_spacing_px,
            v_col_spacing_px=self._v_col_spacing_px,
            h_manual_break_extra_px=self._h_manual_break_extra_px,
            v_manual_break_extra_px=self._v_manual_break_extra_px,
        )
        if pil_image:
            q_pixmap = pil_to_qpixmap(pil_image)
            if q_pixmap and not q_pixmap.isNull():
                self._block_render_cache[block_id] = (current_version_hash, q_pixmap)
                return q_pixmap
            else:
                self._block_render_cache.pop(block_id, None)
                return None
        self._block_render_cache.pop(block_id, None)
        return None

    def set_processed_blocks(self, blocks: list[ProcessedBlock]):
        self.processed_blocks = blocks
        self._block_render_cache.clear()
        if self.selected_block not in self.processed_blocks:
            self.set_selected_block(None)
        for i, block in enumerate(self.processed_blocks):
            if not hasattr(block, "id") or block.id is None:
                block.id = f"block_{time.time_ns()}_{i}"
            if not hasattr(block, "main_color"):
                block.main_color = None
            if not hasattr(block, "outline_color"):
                block.outline_color = None
            if not hasattr(block, "background_color"):
                block.background_color = None
            if not hasattr(block, "outline_thickness"):
                block.outline_thickness = None
            fixed_font_size_override = self.config_manager.getint(
                "UI", "fixed_font_size", 0
            )
            if fixed_font_size_override > 0:
                block.font_size_pixels = fixed_font_size_override
            else:
                block.font_size_pixels = self.font_size_mapping.get(
                    getattr(block, "font_size_category", "medium"),
                    self.font_size_mapping.get("medium", 22),
                )
        self.update()

    def get_current_render_as_pil_image(self) -> Image.Image | None:
        if not self.background_pixmap or not PILLOW_AVAILABLE:
            return None
        q_img_bg = self.background_pixmap.toImage().convertToFormat(
            QImage.Format.Format_RGBA8888
        )
        if q_img_bg.isNull():
            return None
        img_buffer = QBuffer()
        img_buffer.open(QIODevice.OpenModeFlag.ReadWrite)
        if not q_img_bg.save(img_buffer, "PNG"):
            return None
        img_buffer.seek(0)
        try:
            pil_bg_image = Image.open(io.BytesIO(img_buffer.data()))
        except Exception:
            return None
        finally:
            img_buffer.close()
        if pil_bg_image.mode != "RGBA":
            pil_bg_image = pil_bg_image.convert("RGBA")
        final_pil_image = draw_processed_blocks_pil(
            pil_bg_image, self.processed_blocks, self.config_manager
        )
        return final_pil_image

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bg_draw_x, bg_draw_y = 0, 0
        if self.scaled_background_pixmap and not self.scaled_background_pixmap.isNull():
            bg_draw_x = (self.width() - self.scaled_background_pixmap.width()) / 2.0
            bg_draw_y = (self.height() - self.scaled_background_pixmap.height()) / 2.0
            painter.drawPixmap(
                QPointF(bg_draw_x, bg_draw_y), self.scaled_background_pixmap
            )
        else:
            painter.fillRect(self.rect(), self.palette().window())
            if not self.processed_blocks:
                painter.setPen(Qt.GlobalColor.gray)
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "翻译结果")
        bg_img_to_display_scale_x, bg_img_to_display_scale_y = (
            self._get_bg_fit_scale_factors()
        )
        for block in self.processed_blocks:
            block_qpixmap = self._get_or_render_block_qpixmap(block)
            painter.save()
            block_center_x_orig = (block.bbox[0] + block.bbox[2]) / 2.0
            block_center_y_orig = (block.bbox[1] + block.bbox[3]) / 2.0
            block_display_center_x_rel_bg = (
                block_center_x_orig * bg_img_to_display_scale_x
            )
            block_display_center_y_rel_bg = (
                block_center_y_orig * bg_img_to_display_scale_y
            )
            block_display_center_widget_x = bg_draw_x + block_display_center_x_rel_bg
            block_display_center_widget_y = bg_draw_y + block_display_center_y_rel_bg
            content_transform = QTransform()
            content_transform.translate(
                block_display_center_widget_x, block_display_center_widget_y
            )
            content_transform.rotate(block.angle)
            content_transform.scale(
                bg_img_to_display_scale_x, bg_img_to_display_scale_y
            )
            current_painter_transform = painter.worldTransform()
            painter.setWorldTransform(content_transform, combine=True)
            if block_qpixmap and not block_qpixmap.isNull():
                pixmap_draw_x = -block_qpixmap.width() / 2.0
                pixmap_draw_y = -block_qpixmap.height() / 2.0
                painter.drawPixmap(QPointF(pixmap_draw_x, pixmap_draw_y), block_qpixmap)
            painter.setWorldTransform(current_painter_transform)
            painter.restore()
            if block == self.selected_block:
                painter.save()
                bbox_width_orig = block.bbox[2] - block.bbox[0]
                bbox_height_orig = block.bbox[3] - block.bbox[1]
                unscaled_local_bbox_rect = QRectF(
                    -bbox_width_orig / 2.0,
                    -bbox_height_orig / 2.0,
                    bbox_width_orig,
                    bbox_height_orig,
                )
                painter.setWorldTransform(content_transform, combine=False)
                effective_display_scale_x = (
                    bg_img_to_display_scale_x
                    if bg_img_to_display_scale_x > 0.001
                    else 1.0
                )
                effective_display_scale_y = (
                    bg_img_to_display_scale_y
                    if bg_img_to_display_scale_y > 0.001
                    else 1.0
                )
                effective_display_scale_avg = (
                    effective_display_scale_x + effective_display_scale_y
                ) / 2.0
                selection_pen_width = 2.0 / effective_display_scale_avg
                selection_pen = QPen(QColor(0, 120, 215, 200), selection_pen_width)
                selection_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(selection_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(unscaled_local_bbox_rect)
                painter.setBrush(QColor(0, 120, 215, 200))
                painter.setPen(Qt.PenStyle.NoPen)
                handle_local_w = float(CORNER_HANDLE_SIZE) / effective_display_scale_x
                handle_local_h = float(CORNER_HANDLE_SIZE) / effective_display_scale_y
                corners_local_unscaled = [
                    unscaled_local_bbox_rect.topLeft(),
                    unscaled_local_bbox_rect.topRight(),
                    unscaled_local_bbox_rect.bottomRight(),
                    unscaled_local_bbox_rect.bottomLeft(),
                ]
                for corner_pt_local in corners_local_unscaled:
                    painter.drawRect(
                        QRectF(
                            corner_pt_local.x() - handle_local_w / 2.0,
                            corner_pt_local.y() - handle_local_h / 2.0,
                            handle_local_w,
                            handle_local_h,
                        )
                    )
                rot_handle_offset_local_y = (
                    float(ROTATION_HANDLE_OFFSET) / effective_display_scale_y
                )
                rot_handle_center_x_local = unscaled_local_bbox_rect.center().x()
                rot_handle_center_y_local = (
                    unscaled_local_bbox_rect.top() - rot_handle_offset_local_y
                )
                rot_center_qpointf_local = QPointF(
                    rot_handle_center_x_local, rot_handle_center_y_local
                )
                ellipse_rx_local = handle_local_w / 2.0
                ellipse_ry_local = handle_local_h / 2.0
                painter.drawEllipse(
                    rot_center_qpointf_local, ellipse_rx_local, ellipse_ry_local
                )
                painter.setPen(selection_pen)
                painter.drawLine(
                    QPointF(
                        unscaled_local_bbox_rect.center().x(),
                        unscaled_local_bbox_rect.top(),
                    ),
                    rot_center_qpointf_local,
                )
                painter.restore()
        painter.end()

    def _get_transformed_rect_for_block_interaction(
        self, block: ProcessedBlock
    ) -> tuple[QPolygonF, QRectF, QPointF, QTransform]:
        bg_draw_x, bg_draw_y = 0, 0
        if self.scaled_background_pixmap:
            bg_draw_x = (self.width() - self.scaled_background_pixmap.width()) / 2.0
            bg_draw_y = (self.height() - self.scaled_background_pixmap.height()) / 2.0
        bg_img_to_display_scale_x, bg_img_to_display_scale_y = (
            self._get_bg_fit_scale_factors()
        )
        content_width_orig = block.bbox[2] - block.bbox[0]
        content_height_orig = block.bbox[3] - block.bbox[1]
        if content_width_orig <= 0:
            content_width_orig = 1
        if content_height_orig <= 0:
            content_height_orig = 1
        local_bbox_rect_orig_scale = QRectF(
            -content_width_orig / 2.0,
            -content_height_orig / 2.0,
            content_width_orig,
            content_height_orig,
        )
        block_center_x_orig = (block.bbox[0] + block.bbox[2]) / 2.0
        block_center_y_orig = (block.bbox[1] + block.bbox[3]) / 2.0
        block_display_center_x_rel_bg = block_center_x_orig * bg_img_to_display_scale_x
        block_display_center_y_rel_bg = block_center_y_orig * bg_img_to_display_scale_y
        block_display_center_widget_x = bg_draw_x + block_display_center_x_rel_bg
        block_display_center_widget_y = bg_draw_y + block_display_center_y_rel_bg
        block_display_center_qpoint = QPointF(
            block_display_center_widget_x, block_display_center_widget_y
        )
        transform = QTransform()
        transform.translate(
            block_display_center_widget_x, block_display_center_widget_y
        )
        transform.rotate(block.angle)
        transform.scale(bg_img_to_display_scale_x, bg_img_to_display_scale_y)
        p1 = transform.map(local_bbox_rect_orig_scale.topLeft())
        p2 = transform.map(local_bbox_rect_orig_scale.topRight())
        p3 = transform.map(local_bbox_rect_orig_scale.bottomRight())
        p4 = transform.map(local_bbox_rect_orig_scale.bottomLeft())
        transformed_qpolygon = QPolygonF([p1, p2, p3, p4])
        screen_bounding_rect = transformed_qpolygon.boundingRect()
        return (
            transformed_qpolygon,
            screen_bounding_rect,
            block_display_center_qpoint,
            transform,
        )

    def _get_handle_rects_for_block(
        self, block: ProcessedBlock
    ) -> tuple[list[QRectF], QRectF]:
        _, _, _, effective_transform = self._get_transformed_rect_for_block_interaction(
            block
        )
        content_width_orig = block.bbox[2] - block.bbox[0]
        content_height_orig = block.bbox[3] - block.bbox[1]
        if content_width_orig <= 0:
            content_width_orig = 1
        if content_height_orig <= 0:
            content_height_orig = 1
        local_rect_from_bbox_orig_scale = QRectF(
            -content_width_orig / 2.0,
            -content_height_orig / 2.0,
            content_width_orig,
            content_height_orig,
        )
        handle_sz_view = float(CORNER_HANDLE_SIZE)
        corners_local_orig_scale = [
            local_rect_from_bbox_orig_scale.topLeft(),
            local_rect_from_bbox_orig_scale.topRight(),
            local_rect_from_bbox_orig_scale.bottomRight(),
            local_rect_from_bbox_orig_scale.bottomLeft(),
        ]
        bg_img_to_display_scale_x, bg_img_to_display_scale_y = (
            self._get_bg_fit_scale_factors()
        )
        unscale_x = (
            1.0 / bg_img_to_display_scale_x if bg_img_to_display_scale_x != 0 else 1.0
        )
        unscale_y = (
            1.0 / bg_img_to_display_scale_y if bg_img_to_display_scale_y != 0 else 1.0
        )
        rot_handle_offset_on_screen = float(ROTATION_HANDLE_OFFSET)
        effective_scale_y = (
            bg_img_to_display_scale_y if bg_img_to_display_scale_y > 0.001 else 1.0
        )
        rot_handle_offset_local_y_orig = rot_handle_offset_on_screen / effective_scale_y
        rot_handle_center_local_orig_scale = QPointF(
            local_rect_from_bbox_orig_scale.center().x(),
            local_rect_from_bbox_orig_scale.top() - rot_handle_offset_local_y_orig,
        )
        screen_corner_handle_rects = []
        for pt_local_orig in corners_local_orig_scale:
            screen_pt = effective_transform.map(pt_local_orig)
            screen_corner_handle_rects.append(
                QRectF(
                    screen_pt.x() - handle_sz_view / 2,
                    screen_pt.y() - handle_sz_view / 2,
                    handle_sz_view,
                    handle_sz_view,
                )
            )
        screen_rot_handle_center = effective_transform.map(
            rot_handle_center_local_orig_scale
        )
        screen_rotation_handle_rect = QRectF(
            screen_rot_handle_center.x() - handle_sz_view / 2,
            screen_rot_handle_center.y() - handle_sz_view / 2,
            handle_sz_view,
            handle_sz_view,
        )
        return screen_corner_handle_rects, screen_rotation_handle_rect

    def set_selected_block(self, block: ProcessedBlock | None):
        if self.selected_block != block:
            self.selected_block = block
            self.selection_changed_signal.emit(self.selected_block)
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        clicked_on_block_or_handle = False
        current_pos_widget = event.position()
        if self.selected_block:
            corner_rects_screen, rot_rect_screen = self._get_handle_rects_for_block(
                self.selected_block
            )
            if rot_rect_screen.contains(current_pos_widget):
                self.rotating_block = True
                self.resizing_block = False
                self.dragging_block = False
                clicked_on_block_or_handle = True
                self.initial_mouse_pos_on_drag = current_pos_widget
                _, _, self.rotation_center_on_rotate, _ = (
                    self._get_transformed_rect_for_block_interaction(
                        self.selected_block
                    )
                )
                self.initial_angle_on_rotate = self.selected_block.angle
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                for i, corner_rect_s in enumerate(corner_rects_screen):
                    if corner_rect_s.contains(current_pos_widget):
                        self.resizing_block = True
                        self.rotating_block = False
                        self.dragging_block = False
                        self.resize_corner = i
                        clicked_on_block_or_handle = True
                        self.initial_mouse_pos_on_drag = current_pos_widget
                        self.initial_block_bbox_on_drag = list(self.selected_block.bbox)
                        orig_bbox = self.selected_block.bbox
                        corners_orig_bbox_coords = [
                            QPointF(orig_bbox[0], orig_bbox[1]),
                            QPointF(orig_bbox[2], orig_bbox[1]),
                            QPointF(orig_bbox[2], orig_bbox[3]),
                            QPointF(orig_bbox[0], orig_bbox[3]),
                        ]
                        opposite_corner_idx_map = {0: 2, 1: 3, 2: 0, 3: 1}
                        self.resize_anchor_opposite_corner_orig = (
                            corners_orig_bbox_coords[opposite_corner_idx_map[i]]
                        )
                        self.set_resize_cursor(i, self.selected_block.angle)
                        break
        if not clicked_on_block_or_handle:
            newly_selected_block = None
            for block_item in reversed(self.processed_blocks):
                polygon_screen, _, _, _ = (
                    self._get_transformed_rect_for_block_interaction(block_item)
                )
                if polygon_screen.containsPoint(
                    current_pos_widget, Qt.FillRule.WindingFill
                ):
                    newly_selected_block = block_item
                    break
            if newly_selected_block:
                if self.selected_block != newly_selected_block:
                    self.set_selected_block(newly_selected_block)
                if event.button() == Qt.MouseButton.LeftButton:
                    self.dragging_block = True
                    self.resizing_block = False
                    self.rotating_block = False
                    clicked_on_block_or_handle = True
                    self.initial_mouse_pos_on_drag = current_pos_widget
                    self.initial_block_bbox_on_drag = list(self.selected_block.bbox)
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                if event.button() == Qt.MouseButton.LeftButton:
                    if self.selected_block is not None:
                        self.set_selected_block(None)
                self.dragging_block = False
        if (
            not clicked_on_block_or_handle
            and event.button() == Qt.MouseButton.LeftButton
        ):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        current_pos_widget = event.position()
        fit_scale_x, fit_scale_y = self._get_bg_fit_scale_factors()
        if (
            self.dragging_block
            and self.selected_block
            and self.initial_block_bbox_on_drag
            and self.initial_mouse_pos_on_drag
        ):
            delta_mouse_screen = current_pos_widget - self.initial_mouse_pos_on_drag
            delta_x_orig = (
                delta_mouse_screen.x() / fit_scale_x if fit_scale_x != 0 else 0
            )
            delta_y_orig = (
                delta_mouse_screen.y() / fit_scale_y if fit_scale_y != 0 else 0
            )
            new_x0 = self.initial_block_bbox_on_drag[0] + delta_x_orig
            new_y0 = self.initial_block_bbox_on_drag[1] + delta_y_orig
            new_x1 = self.initial_block_bbox_on_drag[2] + delta_x_orig
            new_y1 = self.initial_block_bbox_on_drag[3] + delta_y_orig
            self.selected_block.bbox = [new_x0, new_y0, new_x1, new_y1]
            self._invalidate_block_cache(self.selected_block)
            self.block_modified_signal.emit(self.selected_block)
        elif (
            self.rotating_block
            and self.selected_block
            and self.initial_mouse_pos_on_drag
            and self.rotation_center_on_rotate
        ):
            vec_initial = (
                self.initial_mouse_pos_on_drag - self.rotation_center_on_rotate
            )
            vec_current = current_pos_widget - self.rotation_center_on_rotate
            angle_initial_rad = math.atan2(vec_initial.y(), vec_initial.x())
            angle_current_rad = math.atan2(vec_current.y(), vec_current.x())
            delta_angle_rad = angle_current_rad - angle_initial_rad
            delta_angle_deg = math.degrees(delta_angle_rad)
            new_angle = (self.initial_angle_on_rotate + delta_angle_deg) % 360.0
            self.selected_block.angle = new_angle
            self.update()
            self.block_modified_signal.emit(self.selected_block)
        elif (
            self.resizing_block
            and self.selected_block
            and self.initial_block_bbox_on_drag
            and self.initial_mouse_pos_on_drag
            and self.resize_anchor_opposite_corner_orig
        ):
            bg_draw_x, bg_draw_y = 0, 0
            if self.scaled_background_pixmap:
                bg_draw_x = (self.width() - self.scaled_background_pixmap.width()) / 2.0
                bg_draw_y = (
                    self.height() - self.scaled_background_pixmap.height()
                ) / 2.0
            mouse_on_scaled_bg_x = current_pos_widget.x() - bg_draw_x
            mouse_on_scaled_bg_y = current_pos_widget.y() - bg_draw_y
            mouse_on_orig_img_x = (
                mouse_on_scaled_bg_x / fit_scale_x
                if fit_scale_x != 0
                else mouse_on_scaled_bg_x
            )
            mouse_on_orig_img_y = (
                mouse_on_scaled_bg_y / fit_scale_y
                if fit_scale_y != 0
                else mouse_on_scaled_bg_y
            )
            current_mouse_orig = QPointF(mouse_on_orig_img_x, mouse_on_orig_img_y)
            fixed_anchor_x = self.resize_anchor_opposite_corner_orig.x()
            fixed_anchor_y = self.resize_anchor_opposite_corner_orig.y()
            new_x0, new_y0, new_x1, new_y1 = 0.0, 0.0, 0.0, 0.0
            if self.resize_corner == 0:
                new_x0, new_y0 = current_mouse_orig.x(), current_mouse_orig.y()
                new_x1, new_y1 = fixed_anchor_x, fixed_anchor_y
            elif self.resize_corner == 1:
                new_x1, new_y0 = current_mouse_orig.x(), current_mouse_orig.y()
                new_x0, new_y1 = fixed_anchor_x, fixed_anchor_y
            elif self.resize_corner == 2:
                new_x1, new_y1 = current_mouse_orig.x(), current_mouse_orig.y()
                new_x0, new_y0 = fixed_anchor_x, fixed_anchor_y
            elif self.resize_corner == 3:
                new_x0, new_y1 = current_mouse_orig.x(), current_mouse_orig.y()
                new_x1, new_y0 = fixed_anchor_x, fixed_anchor_y
            final_x0 = min(new_x0, new_x1)
            final_x1 = max(new_x0, new_x1)
            final_y0 = min(new_y0, new_y1)
            final_y1 = max(new_y0, new_y1)
            min_bbox_dim_orig = 10
            if final_x1 - final_x0 < min_bbox_dim_orig:
                if self.resize_corner == 0 or self.resize_corner == 3:
                    final_x0 = final_x1 - min_bbox_dim_orig
                else:
                    final_x1 = final_x0 + min_bbox_dim_orig
            if final_y1 - final_y0 < min_bbox_dim_orig:
                if self.resize_corner == 0 or self.resize_corner == 1:
                    final_y0 = final_y1 - min_bbox_dim_orig
                else:
                    final_y1 = final_y0 + min_bbox_dim_orig
            self.selected_block.bbox = [final_x0, final_y0, final_x1, final_y1]
            self._invalidate_block_cache(self.selected_block)
            self.block_modified_signal.emit(self.selected_block)
        else:
            self.update_cursor_on_hover(current_pos_widget)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.dragging_block = False
        self.resizing_block = False
        self.rotating_block = False
        self.initial_block_bbox_on_drag = None
        self.initial_mouse_pos_on_drag = None
        self.resize_anchor_opposite_corner_orig = None
        self.resize_corner = -1
        self.rotation_center_on_rotate = QPointF()
        self.update_cursor_on_hover(event.position())
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.selected_block:
            polygon_screen, _, _, _ = self._get_transformed_rect_for_block_interaction(
                self.selected_block
            )
            if polygon_screen.containsPoint(event.position(), Qt.FillRule.WindingFill):
                dialog = EditableTextDialog(self.selected_block.translated_text, self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    new_text = dialog.get_text()
                    if self.selected_block.translated_text != new_text:
                        self.selected_block.translated_text = new_text
                        self._invalidate_block_cache(self.selected_block)
                        self.block_modified_signal.emit(self.selected_block)
                return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        event.ignore()

    def _get_bg_fit_scale_factors(self) -> tuple[float, float]:
        if (
            self.scaled_background_pixmap
            and self.background_pixmap
            and self.background_pixmap.width() > 0
            and self.background_pixmap.height() > 0
            and self.scaled_background_pixmap.width() > 0
            and self.scaled_background_pixmap.height() > 0
        ):
            scale_x = (
                self.scaled_background_pixmap.width() / self.background_pixmap.width()
            )
            scale_y = (
                self.scaled_background_pixmap.height() / self.background_pixmap.height()
            )
            return (scale_x, scale_y)
        return 1.0, 1.0

    def update_cursor_on_hover(self, event_pos_widget: QPointF):
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        cursor_set = False
        if self.selected_block:
            corner_rects_s, rot_rect_s = self._get_handle_rects_for_block(
                self.selected_block
            )
            if rot_rect_s.contains(event_pos_widget):
                self.setCursor(Qt.CursorShape.CrossCursor)
                cursor_set = True
            else:
                for i, corner_s_rect in enumerate(corner_rects_s):
                    if corner_s_rect.contains(event_pos_widget):
                        self.set_resize_cursor(i, self.selected_block.angle)
                        cursor_set = True
                        break
        if not cursor_set:
            hovered_block = None
            for block_item in reversed(self.processed_blocks):
                polygon_s, _, _, _ = self._get_transformed_rect_for_block_interaction(
                    block_item
                )
                if polygon_s.containsPoint(event_pos_widget, Qt.FillRule.WindingFill):
                    hovered_block = block_item
                    break
            if hovered_block:
                if hovered_block == self.selected_block:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                cursor_set = True
        if not cursor_set:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_resize_cursor(self, corner_index: int, angle_degrees: float = 0):
        effective_angle = angle_degrees % 360.0
        if effective_angle < 0:
            effective_angle += 360.0
        if corner_index == 0 or corner_index == 2:
            base_cursor_type = Qt.CursorShape.SizeBDiagCursor
        elif corner_index == 1 or corner_index == 3:
            base_cursor_type = Qt.CursorShape.SizeFDiagCursor
        else:
            base_cursor_type = Qt.CursorShape.ArrowCursor
        if (45 <= effective_angle < 135) or (225 <= effective_angle < 315):
            if base_cursor_type == Qt.CursorShape.SizeFDiagCursor:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif base_cursor_type == Qt.CursorShape.SizeBDiagCursor:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            else:
                self.setCursor(base_cursor_type)
        else:
            self.setCursor(base_cursor_type)

    def contextMenuEvent(self, event: QContextMenuEvent):
        block_under_mouse = None
        for block_item in reversed(self.processed_blocks):
            polygon_screen, _, _, _ = self._get_transformed_rect_for_block_interaction(
                block_item
            )
            if polygon_screen.containsPoint(
                QPointF(event.pos()), Qt.FillRule.WindingFill
            ):
                block_under_mouse = block_item
                break
        menu = QMenu(self)
        if block_under_mouse:
            if self.selected_block != block_under_mouse:
                self.set_selected_block(block_under_mouse)
            edit_action = menu.addAction("编辑文本 (&E)")
            delete_action = menu.addAction("删除文本 (&D)")
            menu.addSeparator()
            orientation_menu = menu.addMenu("文本方向 (&O)")
            set_horiz_action = orientation_menu.addAction("横排")
            set_vert_rtl_action = orientation_menu.addAction("竖排/从右向左")
            set_vert_ltr_action = orientation_menu.addAction("竖排/从左向右")
            current_orientation = getattr(
                self.selected_block, "orientation", "horizontal"
            )
            set_horiz_action.setCheckable(True)
            set_vert_rtl_action.setCheckable(True)
            set_vert_ltr_action.setCheckable(True)
            set_horiz_action.setChecked(current_orientation == "horizontal")
            set_vert_rtl_action.setChecked(current_orientation == "vertical_rtl")
            set_vert_ltr_action.setChecked(current_orientation == "vertical_ltr")
            menu.addSeparator()
            align_menu = menu.addMenu("对齐方式")
            set_align_left_action = align_menu.addAction("左对齐")
            set_align_center_action = align_menu.addAction("居中对齐")
            set_align_right_action = align_menu.addAction("右对齐")
            current_align = getattr(self.selected_block, "text_align", "left")
            set_align_left_action.setCheckable(True)
            set_align_center_action.setCheckable(True)
            set_align_right_action.setCheckable(True)
            set_align_left_action.setChecked(current_align == "left")
            set_align_center_action.setChecked(current_align == "center")
            set_align_right_action.setChecked(current_align == "right")
            action = menu.exec(event.globalPos())
            if action == edit_action:
                fake_mouse_event = QMouseEvent(
                    QEvent.Type.MouseButtonDblClick,
                    QPointF(event.pos()),
                    QPointF(event.globalPos()),
                    Qt.MouseButton.LeftButton,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                self.mouseDoubleClickEvent(fake_mouse_event)
            elif action == delete_action and self.selected_block:
                block_to_delete = self.selected_block
                self.processed_blocks.remove(block_to_delete)
                self._invalidate_block_cache(block_to_delete)
                self.set_selected_block(None)
                self.update()
            elif (
                action in [set_horiz_action, set_vert_rtl_action, set_vert_ltr_action]
                and self.selected_block
            ):
                new_orientation = self.selected_block.orientation
                if action == set_horiz_action:
                    new_orientation = "horizontal"
                elif action == set_vert_rtl_action:
                    new_orientation = "vertical_rtl"
                elif action == set_vert_ltr_action:
                    new_orientation = "vertical_ltr"
                if self.selected_block.orientation != new_orientation:
                    self.selected_block.orientation = new_orientation
                    self._invalidate_block_cache(self.selected_block)
                    self.block_modified_signal.emit(self.selected_block)
            elif (
                action
                in [
                    set_align_left_action,
                    set_align_center_action,
                    set_align_right_action,
                ]
                and self.selected_block
            ):
                new_align = self.selected_block.text_align
                if action == set_align_left_action:
                    new_align = "left"
                elif action == set_align_center_action:
                    new_align = "center"
                elif action == set_align_right_action:
                    new_align = "right"
                if self.selected_block.text_align != new_align:
                    self.selected_block.text_align = new_align
                    self._invalidate_block_cache(self.selected_block)
                    self.block_modified_signal.emit(self.selected_block)
        else:
            add_text_action = menu.addAction("新建文本框 (&N)")
            action = menu.exec(event.globalPos())
            if action == add_text_action:
                self._add_new_text_block(QPointF(event.pos()))

    def _add_new_text_block(self, pos_widget: QPointF):
        if not self.background_pixmap:
            QMessageBox.warning(self, "操作无效", "请先加载背景图片才能添加文本框。")
            return
        fit_scale_x, fit_scale_y = self._get_bg_fit_scale_factors()
        if fit_scale_x == 0 or fit_scale_y == 0:
            return
        bg_draw_x, bg_draw_y = 0, 0
        if self.scaled_background_pixmap:
            bg_draw_x = (self.width() - self.scaled_background_pixmap.width()) / 2.0
            bg_draw_y = (self.height() - self.scaled_background_pixmap.height()) / 2.0
        pos_on_scaled_bg_x = pos_widget.x() - bg_draw_x
        pos_on_scaled_bg_y = pos_widget.y() - bg_draw_y
        center_x_orig = pos_on_scaled_bg_x / fit_scale_x
        center_y_orig = pos_on_scaled_bg_y / fit_scale_y
        default_width_orig = 150
        default_height_orig = 50
        default_font_size_category = "medium"
        default_font_size_px = self.font_size_mapping.get(
            default_font_size_category, 22
        )
        fixed_font_size_override = self.config_manager.getint(
            "UI", "fixed_font_size", 0
        )
        if fixed_font_size_override > 0:
            default_font_size_px = fixed_font_size_override
        new_bbox = [
            center_x_orig - default_width_orig / 2,
            center_y_orig - default_height_orig / 2,
            center_x_orig + default_width_orig / 2,
            center_y_orig + default_height_orig / 2,
        ]
        new_id = f"manual_block_{time.time_ns()}_{len(self.processed_blocks)}"
        new_block = ProcessedBlock(
            id=new_id,
            original_text="",
            translated_text="新文本框",
            bbox=new_bbox,
            orientation="horizontal",
            font_size_pixels=default_font_size_px,
            angle=0.0,
            text_align="left",
            font_size_category=default_font_size_category,
        )
        new_block.main_color = None
        new_block.outline_color = None
        new_block.background_color = None
        new_block.outline_thickness = None
        self.processed_blocks.append(new_block)
        self._invalidate_block_cache(new_block)
        self.set_selected_block(new_block)
        self.block_modified_signal.emit(new_block)
        self.update()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._scale_background_and_view()


class TranslationWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(object, object, str, str)

    def __init__(self, image_processor: ImageProcessor, image_path: str, parent=None):
        super().__init__(parent)
        self.image_processor = image_processor
        self.image_path = image_path
        self.cancellation_event = threading.Event()

    def run(self):
        try:

            def _progress_update(percentage, message):
                if self.cancellation_event.is_set():
                    raise InterruptedError("处理已取消")
                self.progress_signal.emit(percentage, message)

            result_tuple = self.image_processor.process_image(
                self.image_path,
                progress_callback=_progress_update,
                cancellation_event=self.cancellation_event,
            )
            if self.cancellation_event.is_set():
                self.finished_signal.emit(None, None, self.image_path, "处理已取消。")
            elif result_tuple:
                original_img, blocks = result_tuple
                for block in blocks:
                    if not hasattr(block, "main_color"):
                        block.main_color = None
                    if not hasattr(block, "outline_color"):
                        block.outline_color = None
                    if not hasattr(block, "background_color"):
                        block.background_color = None
                    if not hasattr(block, "outline_thickness"):
                        block.outline_thickness = None
                self.finished_signal.emit(
                    original_img,
                    blocks,
                    self.image_path,
                    self.image_processor.get_last_error(),
                )
            else:
                self.finished_signal.emit(
                    None,
                    None,
                    self.image_path,
                    self.image_processor.get_last_error() or "图片处理失败",
                )
        except InterruptedError:
            self.finished_signal.emit(None, None, self.image_path, "处理已取消。")
        except Exception as e:
            import traceback

            print(f"Error in TranslationWorker: {e}\n{traceback.format_exc()}")
            self.finished_signal.emit(
                None, None, self.image_path, f"工作线程意外错误: {e}"
            )

    def cancel(self):
        self.cancellation_event.set()


class BatchTranslationWorker(QThread):
    overall_progress_signal = pyqtSignal(int, str)
    file_completed_signal = pyqtSignal(str, str, bool)
    batch_finished_signal = pyqtSignal(int, int, float, bool)

    def __init__(
        self,
        image_processor: ImageProcessor,
        config_manager: ConfigManager,
        file_paths: list[str],
        output_dir: str,
        parent=None,
    ):
        super().__init__(parent)
        self.image_processor = image_processor
        self.config_manager = config_manager
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.cancellation_event = threading.Event()

    def run(self):
        processed_count = 0
        error_count = 0
        start_batch_time = time.time()
        total_files = len(self.file_paths)
        cancelled_early = False
        if total_files == 0:
            self.batch_finished_signal.emit(0, 0, 0, False)
            return
        for i, file_path in enumerate(self.file_paths):
            if self.cancellation_event.is_set():
                cancelled_early = True
                break
            current_file_basename = os.path.basename(file_path)
            self.overall_progress_signal.emit(
                int((i / total_files) * 100),
                f"处理中: {current_file_basename} ({i+1}/{total_files})",
            )
            try:
                result_tuple = self.image_processor.process_image(
                    file_path,
                    progress_callback=None,
                    cancellation_event=self.cancellation_event,
                )
            except InterruptedError:
                cancelled_early = True
                break
            except Exception as proc_e:
                self.file_completed_signal.emit(
                    file_path, f"处理时发生意外错误 {proc_e}", False
                )
                error_count += 1
                continue
            if self.cancellation_event.is_set():
                cancelled_early = True
                break
            if result_tuple:
                original_pil, blocks = result_tuple
                last_proc_error = self.image_processor.get_last_error()
                for block in blocks:
                    if not hasattr(block, "main_color"):
                        block.main_color = None
                    if not hasattr(block, "outline_color"):
                        block.outline_color = None
                    if not hasattr(block, "background_color"):
                        block.background_color = None
                    if not hasattr(block, "outline_thickness"):
                        block.outline_thickness = None
                final_drawn_pil_image = draw_processed_blocks_pil(
                    original_pil, blocks, self.config_manager
                )
                if final_drawn_pil_image:
                    base, ext = os.path.splitext(current_file_basename)
                    output_filename = f"{base}_translated{ext if ext.lower() in ['.png', '.jpg', '.jpeg', '.bmp'] else '.png'}"
                    output_path = os.path.join(self.output_dir, output_filename)
                    try:
                        save_format = "PNG"
                        if output_filename.lower().endswith((".jpg", ".jpeg")):
                            save_format = "JPEG"
                        elif output_filename.lower().endswith(".bmp"):
                            save_format = "BMP"
                        if (
                            save_format == "JPEG"
                            and final_drawn_pil_image.mode == "RGBA"
                        ):
                            bg = Image.new(
                                "RGB", final_drawn_pil_image.size, (255, 255, 255)
                            )
                            bg.paste(
                                final_drawn_pil_image,
                                mask=final_drawn_pil_image.split()[3],
                            )
                            bg.save(output_path, save_format, quality=95)
                        else:
                            final_drawn_pil_image.save(output_path, save_format)
                        self.file_completed_signal.emit(file_path, output_path, True)
                        processed_count += 1
                    except Exception as e:
                        self.file_completed_signal.emit(
                            file_path, f"保存失败 {output_path}: {e}", False
                        )
                        error_count += 1
                else:
                    err_msg = f"绘制文本块失败: {current_file_basename}" + (
                        f" (原始处理错误: {last_proc_error})" if last_proc_error else ""
                    )
                    self.file_completed_signal.emit(file_path, err_msg, False)
                    error_count += 1
            else:
                self.file_completed_signal.emit(
                    file_path,
                    self.image_processor.get_last_error()
                    or f"处理失败: {current_file_basename}",
                    False,
                )
                error_count += 1
        duration = time.time() - start_batch_time
        total_attempted = processed_count + error_count
        final_progress = (
            int(((total_attempted) / total_files) * 100) if total_files > 0 else 100
        )
        status_msg = "批量处理已取消。" if cancelled_early else "批量处理完成。"
        self.overall_progress_signal.emit(final_progress, status_msg)
        self.batch_finished_signal.emit(
            processed_count, error_count, duration, cancelled_early
        )

    def cancel(self):
        self.cancellation_event.set()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Translator")
        self.setGeometry(100, 100, 1200, 800)
        self.config_manager = ConfigManager()
        self.image_processor = ImageProcessor(self.config_manager)
        self.original_pil_for_display: Image.Image | None = None
        self.current_image_path: str | None = None
        self.current_bg_image_path: str | None = None
        self.current_icon_path: str | None = None
        self.translation_worker: TranslationWorker | None = None
        self.batch_worker: BatchTranslationWorker | None = None
        self.text_detail_panel: TextDetailPanel | None = None
        self.splitter = None
        self.original_preview_area = None
        self.interactive_translate_area = None
        self.block_controls_widget = None
        self.block_text_edit_proxy = None
        self.block_font_size_spin = None
        self.block_angle_spin = None
        self.main_color_button = None
        self.outline_color_button = None
        self.background_color_button = None
        self.outline_thickness_spin = None
        self.translate_button = None
        self.download_button = None
        self.progress_widget = None
        self.status_label = None
        self.progress_bar = None
        self.cancel_button = None
        self.setAutoFillBackground(True)
        self._check_dependencies_on_startup()
        self._create_actions()
        self._create_menu_bar()
        self._create_central_widget()
        self._connect_signals()
        self._apply_initial_settings()
        QTimer.singleShot(100, self._initial_splitter_setup)

    def _initial_splitter_setup(self):
        if hasattr(self, "splitter") and self.splitter and self.splitter.count() == 3:
            total_width = self.splitter.width()
            if total_width > 50:
                self.splitter.setSizes(
                    [total_width // 3, total_width // 3, total_width // 3]
                )

    def _check_dependencies_on_startup(self):
        deps = check_dependencies_availability()
        missing = [
            name
            for name, available in deps.items()
            if not available and name == "Pillow"
        ]
        if missing:
            QMessageBox.critical(
                self, "依赖缺失", f"{', '.join(missing)} 库未安装！部分功能将无法使用。"
            )

    def _apply_initial_settings(self):
        bg_path = self.config_manager.get("UI", "background_image_path", fallback="")
        if bg_path and os.path.exists(bg_path):
            bg_pix = QPixmap(bg_path)
            if not bg_pix.isNull():
                self.current_bg_image_path = bg_path
                self._apply_window_background(bg_pix)
            else:
                print(f"Warning: Failed to load background image: {bg_path}")
                self.config_manager.set("UI", "background_image_path", "")
        elif bg_path:
            self.config_manager.set("UI", "background_image_path", "")
        icon_path = self.config_manager.get("UI", "window_icon_path", fallback="")
        if icon_path and os.path.exists(icon_path):
            if self._apply_window_icon(icon_path):
                self.current_icon_path = icon_path
            else:
                print(f"Warning: Failed to apply window icon: {icon_path}")
                self.config_manager.set("UI", "window_icon_path", "")
        elif icon_path:
            self.config_manager.set("UI", "window_icon_path", "")
        if (
            hasattr(self, "interactive_translate_area")
            and self.interactive_translate_area
        ):
            self.interactive_translate_area.reload_style_configs()

    def _create_actions(self):
        self.load_action = QAction("&载入图片", self)
        self.load_batch_action = QAction("批量载入图片(&B)", self)
        self.exit_action = QAction("&退出", self)
        self.api_settings_action = QAction("&API及代理设置", self)
        self.glossary_settings_action = QAction("术语表设置(&T)", self)
        self.text_style_settings_action = QAction("文本样式设置(&Y)", self)
        self.change_bg_action = QAction("更换窗口背景(&G)", self)
        self.set_icon_action = QAction("设置窗口图标(&I)", self)

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&文件")
        file_menu.addAction(self.load_action)
        file_menu.addAction(self.load_batch_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        option_menu = menu_bar.addMenu("&选项")
        option_menu.addAction(self.change_bg_action)
        option_menu.addAction(self.set_icon_action)
        setting_menu = menu_bar.addMenu("&设置")
        setting_menu.addAction(self.api_settings_action)
        setting_menu.addAction(self.glossary_settings_action)
        setting_menu.addAction(self.text_style_settings_action)

    def _create_central_widget(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.original_preview_area = QLabel("原图")
        self.original_preview_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_preview_area.setFrameStyle(
            QFrame.Shape.Panel | QFrame.Shadow.Sunken
        )
        self.original_preview_area.setMinimumSize(250, 300)
        self.original_preview_area.setWordWrap(True)
        self.splitter.addWidget(self.original_preview_area)
        self.interactive_translate_area = InteractiveLabel(self.config_manager, self)
        self.interactive_translate_area.setMinimumSize(250, 300)
        self.splitter.addWidget(self.interactive_translate_area)
        self.text_detail_panel = TextDetailPanel(self)
        self.text_detail_panel.setMinimumSize(250, 300)
        self.splitter.addWidget(self.text_detail_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 1)
        main_layout.addWidget(self.splitter, 1)
        self.block_controls_widget = QWidget()
        block_controls_layout = QHBoxLayout(self.block_controls_widget)
        block_controls_layout.setContentsMargins(0, 2, 0, 2)
        block_controls_layout.setSpacing(5)
        block_controls_layout.addWidget(QLabel("选中:"))
        self.block_text_edit_proxy = QLineEdit()
        self.block_text_edit_proxy.setReadOnly(True)
        block_controls_layout.addWidget(self.block_text_edit_proxy, 1)
        block_controls_layout.addWidget(QLabel("字号:"))
        self.block_font_size_spin = QDoubleSpinBox()
        self.block_font_size_spin.setRange(5, 200)
        self.block_font_size_spin.setSingleStep(1)
        self.block_font_size_spin.setDecimals(0)
        self.block_font_size_spin.setButtonSymbols(
            QDoubleSpinBox.ButtonSymbols.PlusMinus
        )
        block_controls_layout.addWidget(self.block_font_size_spin)
        block_controls_layout.addWidget(QLabel("角度:"))
        self.block_angle_spin = QDoubleSpinBox()
        self.block_angle_spin.setRange(-360, 360)
        self.block_angle_spin.setSingleStep(1)
        self.block_angle_spin.setDecimals(1)
        self.block_angle_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
        self.block_angle_spin.setWrapping(True)
        block_controls_layout.addWidget(self.block_angle_spin)
        block_controls_layout.addSpacing(10)
        block_controls_layout.addWidget(QLabel("主色:"))
        self.main_color_button = self._create_color_button()
        block_controls_layout.addWidget(self.main_color_button)
        block_controls_layout.addWidget(QLabel("描边色:"))
        self.outline_color_button = self._create_color_button()
        block_controls_layout.addWidget(self.outline_color_button)
        block_controls_layout.addWidget(QLabel("描边厚:"))
        self.outline_thickness_spin = QSpinBox()
        self.outline_thickness_spin.setRange(0, 20)
        self.outline_thickness_spin.setSingleStep(1)
        self.outline_thickness_spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        block_controls_layout.addWidget(self.outline_thickness_spin)
        block_controls_layout.addWidget(QLabel("背景色:"))
        self.background_color_button = self._create_color_button()
        block_controls_layout.addWidget(self.background_color_button)
        block_controls_layout.addStretch(0)
        self.block_controls_widget.setVisible(False)
        main_layout.addWidget(self.block_controls_widget, 0)
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 5, 0, 5)
        self.translate_button = QPushButton("翻译当前图片")
        self.download_button = QPushButton("导出翻译结果")
        self.translate_button.setEnabled(False)
        self.download_button.setEnabled(False)
        button_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        button_layout.addWidget(self.translate_button)
        button_layout.addSpacing(20)
        button_layout.addWidget(self.download_button)
        button_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        main_layout.addWidget(button_widget, 0)
        self.progress_widget = QWidget()
        progress_layout = QHBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("状态: 空闲")
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.cancel_button = QPushButton("取消处理")
        self.cancel_button.setEnabled(False)
        progress_layout.addWidget(self.status_label, 1)
        progress_layout.addWidget(self.progress_bar, 2)
        progress_layout.addWidget(self.cancel_button, 0)
        main_layout.addWidget(self.progress_widget)
        self.progress_widget.setVisible(False)
        self.setCentralWidget(central_widget)

    def _create_color_button(
        self, initial_color: QColor = Qt.GlobalColor.gray
    ) -> QPushButton:
        button = QPushButton()
        button.setFixedSize(QSize(24, 24))
        button.setFlat(False)
        self._set_button_color(button, initial_color)
        return button

    def _set_button_color(self, button: QPushButton, color: QColor):
        if not isinstance(color, QColor):
            try:
                if len(color) == 4:
                    color = QColor(color[0], color[1], color[2], color[3])
                elif len(color) == 3:
                    color = QColor(color[0], color[1], color[2], 255)
                else:
                    color = QColor(Qt.GlobalColor.gray)
            except:
                color = QColor(Qt.GlobalColor.gray)
        button.setStyleSheet(
            f"background-color: {color.name(QColor.NameFormat.HexArgb)}; border: 1px solid gray;"
        )
        button.setToolTip(f"当前颜色: {color.name(QColor.NameFormat.HexArgb)}")
        button.setProperty(
            "currentColorTuple",
            (color.red(), color.green(), color.blue(), color.alpha()),
        )

    def _parse_color_str(self, color_str: str, default_color_tuple: tuple) -> tuple:
        try:
            parts = list(map(int, color_str.split(",")))
            if len(parts) == 3:
                return (parts[0], parts[1], parts[2], 255)
            if len(parts) == 4:
                return (parts[0], parts[1], parts[2], parts[3])
        except:
            pass
        return default_color_tuple

    def _update_block_controls(self, block: ProcessedBlock | None):
        is_block_selected = block is not None
        self.block_controls_widget.setVisible(True)
        self.block_text_edit_proxy.setEnabled(False)
        self.block_text_edit_proxy.setText(
            ""
            if not is_block_selected
            else (
                block.translated_text[:50] + "..."
                if len(block.translated_text) > 50
                else block.translated_text
            )
        )
        self.block_font_size_spin.setEnabled(False)
        self.block_angle_spin.setEnabled(False)
        self.outline_thickness_spin.setEnabled(False)
        self.main_color_button.setEnabled(False)
        self.outline_color_button.setEnabled(False)
        self.background_color_button.setEnabled(False)
        self.block_font_size_spin.blockSignals(True)
        self.block_angle_spin.blockSignals(True)
        self.outline_thickness_spin.blockSignals(True)
        self.main_color_button.blockSignals(True)
        self.outline_color_button.blockSignals(True)
        self.background_color_button.blockSignals(True)
        self.block_font_size_spin.setValue(
            block.font_size_pixels
            if is_block_selected
            else self.interactive_translate_area.font_size_mapping.get("medium", 22)
        )
        self.block_angle_spin.setValue(block.angle if is_block_selected else 0.0)
        default_thickness = (
            self.interactive_translate_area._outline_thickness
            if hasattr(self.interactive_translate_area, "_outline_thickness")
            else 2
        )
        self.outline_thickness_spin.setValue(
            block.outline_thickness
            if is_block_selected
            and hasattr(block, "outline_thickness")
            and block.outline_thickness is not None
            else default_thickness
        )
        default_main_color = (
            self.interactive_translate_area._text_main_color_pil
            if hasattr(self.interactive_translate_area, "_text_main_color_pil")
            else (255, 255, 255, 255)
        )
        main_color_tuple = (
            block.main_color
            if is_block_selected
            and hasattr(block, "main_color")
            and block.main_color is not None
            else default_main_color
        )
        self._set_button_color(self.main_color_button, QColor(*main_color_tuple))
        default_outline_color = (
            self.interactive_translate_area._text_outline_color_pil
            if hasattr(self.interactive_translate_area, "_text_outline_color_pil")
            else (0, 0, 0, 255)
        )
        outline_color_tuple = (
            block.outline_color
            if is_block_selected
            and hasattr(block, "outline_color")
            and block.outline_color is not None
            else default_outline_color
        )
        self._set_button_color(self.outline_color_button, QColor(*outline_color_tuple))
        default_bg_color = (
            self.interactive_translate_area._text_bg_color_pil
            if hasattr(self.interactive_translate_area, "_text_bg_color_pil")
            else (0, 0, 0, 128)
        )
        bg_color_tuple = (
            block.background_color
            if is_block_selected
            and hasattr(block, "background_color")
            and block.background_color is not None
            else default_bg_color
        )
        self._set_button_color(self.background_color_button, QColor(*bg_color_tuple))
        self.block_font_size_spin.blockSignals(False)
        self.block_angle_spin.blockSignals(False)
        self.outline_thickness_spin.blockSignals(False)
        self.main_color_button.blockSignals(False)
        self.outline_color_button.blockSignals(False)
        self.background_color_button.blockSignals(False)
        if is_block_selected:
            self.block_text_edit_proxy.setEnabled(True)
            self.block_font_size_spin.setEnabled(True)
            self.block_angle_spin.setEnabled(True)
            self.outline_thickness_spin.setEnabled(True)
            self.main_color_button.setEnabled(True)
            self.outline_color_button.setEnabled(True)
            self.background_color_button.setEnabled(True)
            if self.text_detail_panel:
                self.text_detail_panel.update_texts(
                    block.original_text, block.translated_text, block.id
                )
        else:
            if self.text_detail_panel:
                self.text_detail_panel.clear_texts()

    @pyqtSlot()
    def _on_selected_block_spinbox_changed(self):
        if self.interactive_translate_area.selected_block:
            s_block = self.interactive_translate_area.selected_block
            changed = False
            new_font_size = int(self.block_font_size_spin.value())
            if s_block.font_size_pixels != new_font_size:
                s_block.font_size_pixels = new_font_size
                changed = True
            new_angle = self.block_angle_spin.value()
            if abs(s_block.angle - new_angle) > 0.01:
                s_block.angle = new_angle % 360.0
                changed = True
            new_thickness = self.outline_thickness_spin.value()
            current_thickness = (
                s_block.outline_thickness
                if hasattr(s_block, "outline_thickness")
                else None
            )
            if current_thickness != new_thickness:
                s_block.outline_thickness = new_thickness
                changed = True
            if changed:
                self.interactive_translate_area._invalidate_block_cache(s_block)
                self.interactive_translate_area.block_modified_signal.emit(s_block)

    @pyqtSlot()
    def _on_pick_color(self):
        sender_button = self.sender()
        if not sender_button or not self.interactive_translate_area.selected_block:
            return
        s_block = self.interactive_translate_area.selected_block
        attribute_name = None
        current_color_tuple = None
        if sender_button == self.main_color_button:
            attribute_name = "main_color"
            current_color_tuple = (
                s_block.main_color
                if hasattr(s_block, "main_color") and s_block.main_color
                else self.interactive_translate_area._text_main_color_pil
            )
        elif sender_button == self.outline_color_button:
            attribute_name = "outline_color"
            current_color_tuple = (
                s_block.outline_color
                if hasattr(s_block, "outline_color") and s_block.outline_color
                else self.interactive_translate_area._text_outline_color_pil
            )
        elif sender_button == self.background_color_button:
            attribute_name = "background_color"
            current_color_tuple = (
                s_block.background_color
                if hasattr(s_block, "background_color") and s_block.background_color
                else self.interactive_translate_area._text_bg_color_pil
            )
        else:
            return
        initial_qcolor = QColor(*current_color_tuple)
        new_qcolor = QColorDialog.getColor(
            initial_qcolor,
            self,
            "选择颜色",
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if new_qcolor.isValid():
            new_color_tuple = (
                new_qcolor.red(),
                new_qcolor.green(),
                new_qcolor.blue(),
                new_qcolor.alpha(),
            )
            if new_color_tuple != current_color_tuple:
                self._set_button_color(sender_button, new_qcolor)
                setattr(s_block, attribute_name, new_color_tuple)
                self.interactive_translate_area._invalidate_block_cache(s_block)
                self.interactive_translate_area.block_modified_signal.emit(s_block)

    def _connect_signals(self):
        self.load_action.triggered.connect(self._on_load_image)
        self.load_batch_action.triggered.connect(self._on_load_batch_images)
        self.exit_action.triggered.connect(self.close)
        self.change_bg_action.triggered.connect(self._on_change_window_background)
        self.set_icon_action.triggered.connect(self._on_set_window_icon)
        self.api_settings_action.triggered.connect(self._on_open_api_settings)
        self.glossary_settings_action.triggered.connect(self._on_open_glossary_settings)
        self.text_style_settings_action.triggered.connect(
            self._on_open_text_style_settings
        )
        self.translate_button.clicked.connect(self._on_translate_clicked)
        self.download_button.clicked.connect(self._on_download_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_processing)
        self.interactive_translate_area.block_modified_signal.connect(
            self._update_block_controls_from_interaction
        )
        self.interactive_translate_area.selection_changed_signal.connect(
            self._update_block_controls
        )
        if self.text_detail_panel:
            self.text_detail_panel.translated_text_changed_externally_signal.connect(
                self._on_detail_panel_text_changed
            )
        self.block_font_size_spin.valueChanged.connect(
            self._on_selected_block_spinbox_changed
        )
        self.block_angle_spin.valueChanged.connect(
            self._on_selected_block_spinbox_changed
        )
        self.outline_thickness_spin.valueChanged.connect(
            self._on_selected_block_spinbox_changed
        )
        self.main_color_button.clicked.connect(self._on_pick_color)
        self.outline_color_button.clicked.connect(self._on_pick_color)
        self.background_color_button.clicked.connect(self._on_pick_color)

    @pyqtSlot(str)
    def _on_detail_panel_text_changed(self, new_translated_text: str):
        if (
            self.interactive_translate_area
            and self.interactive_translate_area.selected_block
        ):
            selected_block = self.interactive_translate_area.selected_block
            if selected_block.translated_text != new_translated_text:
                selected_block.translated_text = new_translated_text
                self.interactive_translate_area._invalidate_block_cache(selected_block)
                self.interactive_translate_area.block_modified_signal.emit(
                    selected_block
                )
                self.block_text_edit_proxy.setText(
                    selected_block.translated_text[:50] + "..."
                    if len(selected_block.translated_text) > 50
                    else selected_block.translated_text
                )

    def _update_block_controls_from_interaction(self, modified_block: ProcessedBlock):
        if self.interactive_translate_area.selected_block == modified_block:
            self._update_block_controls(modified_block)

    @pyqtSlot()
    def _on_load_image(self):
        if (self.translation_worker and self.translation_worker.isRunning()) or (
            self.batch_worker and self.batch_worker.isRunning()
        ):
            QMessageBox.warning(
                self, "操作繁忙", "当前有处理任务，请等待完成后再加载。"
            )
            return
        img_filter = "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff);;所有文件 (*)"
        start_dir = self.config_manager.get(
            "UI", "last_image_dir", os.path.expanduser("~")
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "载入图片", start_dir, img_filter
        )
        if file_path:
            if not PILLOW_AVAILABLE:
                QMessageBox.critical(self, "依赖缺失", "Pillow未安装，无法加载图片。")
                return
            try:
                pil_img = Image.open(file_path)
                if pil_img.mode != "RGBA":
                    pil_img = pil_img.convert("RGBA")
                self.original_pil_for_display = pil_img
                preview_pixmap = pil_to_qpixmap(pil_img)
                if not preview_pixmap or preview_pixmap.isNull():
                    raise ValueError("无法将图片转换为界面格式 (QPixmap)")
                self.current_image_path = file_path
                self._display_image_in_label(self.original_preview_area, preview_pixmap)
                self.interactive_translate_area.clear_all()
                self.interactive_translate_area.set_background_image(preview_pixmap)
                if self.text_detail_panel:
                    self.text_detail_panel.clear_texts()
                self.translate_button.setEnabled(True)
                self.download_button.setEnabled(False)
                self._update_block_controls(None)
                self.config_manager.set(
                    "UI", "last_image_dir", os.path.dirname(file_path)
                )
                self.status_label.setText("状态: 图片已加载")
                self.progress_bar.setValue(0)
                self.progress_widget.setVisible(False)
            except UnidentifiedImageError:
                self._reset_image_state(f"无法识别的图片格式:\n{file_path}")
            except Exception as e:
                import traceback

                print(f"Error loading image: {e}\n{traceback.format_exc()}")
                self._reset_image_state(f"加载图片时发生错误: {e}\n路径: {file_path}")

    def _reset_image_state(self, error_message: str | None = None):
        if error_message:
            QMessageBox.warning(self, "加载错误", error_message)
        self.original_pil_for_display = None
        self.current_image_path = None
        self.original_preview_area.clear()
        self.original_preview_area.setText("原图")
        self.interactive_translate_area.clear_all()
        if self.text_detail_panel:
            self.text_detail_panel.clear_texts()
        self.translate_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self._update_block_controls(None)
        self.status_label.setText("状态: 空闲")
        self.progress_bar.setValue(0)
        self.progress_widget.setVisible(False)

    def _display_image_in_label(self, label: QLabel, pixmap: QPixmap):
        if not pixmap or pixmap.isNull():
            label.setText("无图片")
            return
        margin = 5
        label_w = max(1, label.width() - margin * 2)
        label_h = max(1, label.height() - margin * 2)
        scaled_pixmap = pixmap.scaled(
            label_w,
            label_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled_pixmap)

    @pyqtSlot()
    def _on_change_window_background(self):
        img_filter = "图片 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*)"
        start_dir = self.config_manager.get(
            "UI", "last_bg_dir", os.path.expanduser("~")
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择窗口背景", start_dir, img_filter
        )
        if file_path:
            bg_pixmap = QPixmap(file_path)
            if bg_pixmap.isNull():
                QMessageBox.warning(self, "加载错误", f"无法加载背景图片: {file_path}")
                return
            if self._apply_window_background(bg_pixmap):
                self.config_manager.set("UI", "background_image_path", file_path)
                self.config_manager.set("UI", "last_bg_dir", os.path.dirname(file_path))
                self.current_bg_image_path = file_path
            else:
                QMessageBox.warning(self, "应用错误", f"无法应用背景图片: {file_path}")

    def _apply_window_background(self, bg_pixmap: QPixmap) -> bool:
        if not bg_pixmap or bg_pixmap.isNull():
            return False
        try:
            opacity = self.config_manager.getfloat("UI", "background_opacity", 0.15)
            target_size = self.size()
            if target_size.width() <= 0 or target_size.height() <= 0:
                return False
            temp_image = QImage(target_size, QImage.Format.Format_ARGB32_Premultiplied)
            temp_image.fill(Qt.GlobalColor.transparent)
            painter_temp = QPainter(temp_image)
            painter_temp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            aspect_mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding
            scaled_user_bg = bg_pixmap.scaled(
                target_size, aspect_mode, Qt.TransformationMode.SmoothTransformation
            )
            draw_x = (target_size.width() - scaled_user_bg.width()) // 2
            draw_y = (target_size.height() - scaled_user_bg.height()) // 2
            painter_temp.setOpacity(max(0.0, min(1.0, opacity)))
            painter_temp.drawPixmap(draw_x, draw_y, scaled_user_bg)
            painter_temp.end()
            palette = self.palette()
            palette.setBrush(
                QPalette.ColorRole.Window, QBrush(QPixmap.fromImage(temp_image))
            )
            self.setPalette(palette)
            self.setAutoFillBackground(True)
            return True
        except Exception as e:
            print(f"应用窗口背景时出错: {e}")
            import traceback

            traceback.print_exc()
            return False

    @pyqtSlot()
    def _on_set_window_icon(self):
        img_filter = "图标/图片 (*.png *.ico *.jpg *.jpeg *.bmp);;所有文件 (*)"
        start_dir = self.config_manager.get(
            "UI", "last_icon_dir", os.path.expanduser("~")
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择窗口图标", start_dir, img_filter
        )
        if file_path:
            if self._apply_window_icon(file_path):
                self.config_manager.set("UI", "window_icon_path", file_path)
                self.config_manager.set(
                    "UI", "last_icon_dir", os.path.dirname(file_path)
                )
                self.current_icon_path = file_path
            else:
                QMessageBox.warning(
                    self, "图标错误", f"无法加载或应用图标: {file_path}"
                )

    def _apply_window_icon(self, icon_path: str) -> bool:
        if not icon_path or not os.path.exists(icon_path):
            return False
        applied = False
        if PILLOW_AVAILABLE:
            try:
                pil_icon = Image.open(icon_path).convert("RGBA")
                width, height = pil_icon.size
                radius = min(width, height) // 6
                mask = Image.new("L", (width * 4, height * 4), 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.rounded_rectangle(
                    (0, 0, width * 4, height * 4), fill=255, radius=radius * 4
                )
                mask = mask.resize((width, height), Image.Resampling.LANCZOS)
                rounded_icon_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                rounded_icon_img.paste(pil_icon, (0, 0), mask=mask)
                qpixmap_icon = pil_to_qpixmap(rounded_icon_img)
                if qpixmap_icon and not qpixmap_icon.isNull():
                    self.setWindowIcon(QIcon(qpixmap_icon))
                    applied = True
            except Exception as pillow_err:
                print(
                    f"Pillow icon processing for rounding failed: {pillow_err}. Trying direct QIcon."
                )
        if not applied:
            original_icon = QIcon(icon_path)
            if not original_icon.isNull():
                self.setWindowIcon(original_icon)
                applied = True
            else:
                pass
        return applied

    @pyqtSlot()
    def _on_open_api_settings(self):
        dialog = SettingsDialog(self.config_manager, self)
        if dialog.exec():
            self.image_processor = ImageProcessor(self.config_manager)
            QMessageBox.information(self, "设置", "API设置已更新。")

    @pyqtSlot()
    def _on_open_glossary_settings(self):
        dialog = GlossarySettingsDialog(self.config_manager, self)
        if dialog.exec():
            QMessageBox.information(self, "设置", "术语表设置已保存。")
            self.image_processor.reload_glossary()

    @pyqtSlot()
    def _handle_text_style_settings_applied_live(self):
        self.interactive_translate_area.reload_style_configs()
        self.interactive_translate_area._invalidate_block_cache()
        self._update_block_controls(self.interactive_translate_area.selected_block)

    @pyqtSlot()
    def _on_open_text_style_settings(self):
        dialog = TextStyleSettingsDialog(self.config_manager, self)
        dialog.settings_applied.connect(self._handle_text_style_settings_applied_live)
        result = dialog.exec()
        try:
            dialog.settings_applied.disconnect(
                self._handle_text_style_settings_applied_live
            )
        except TypeError:
            pass
        if result == QDialog.DialogCode.Accepted:
            self.interactive_translate_area.reload_style_configs()
            self.interactive_translate_area._invalidate_block_cache()
            self._update_block_controls(self.interactive_translate_area.selected_block)
            QMessageBox.information(self, "设置", "文本样式设置已保存并应用。")

    def _handle_error_message(
        self,
        title: str,
        message: str,
        informative_text: str = "",
        show_settings_option: bool = False,
    ):
        msg_box = QMessageBox(self)
        msg_box.setIcon(
            QMessageBox.Icon.Warning if "警告" in title else QMessageBox.Icon.Critical
        )
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        msg_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if show_settings_option:
            settings_button = msg_box.addButton(
                "打开API设置", QMessageBox.ButtonRole.ActionRole
            )
            msg_box.addButton(QMessageBox.StandardButton.Cancel)
            msg_box.exec()
            if msg_box.clickedButton() == settings_button:
                self._on_open_api_settings()
        else:
            msg_box.addButton(QMessageBox.StandardButton.Ok)
            msg_box.exec()

    @pyqtSlot()
    def _on_translate_clicked(self):
        if not self.current_image_path or not self.original_pil_for_display:
            self._handle_error_message("操作无效", "请先加载图片。")
            return
        if not PILLOW_AVAILABLE:
            self._handle_error_message("依赖缺失", "Pillow 库未安装，无法处理图片。")
            return
        if self.translation_worker and self.translation_worker.isRunning():
            QMessageBox.information(self, "处理中", "当前翻译任务仍在进行中，请稍候。")
            return
        if self.batch_worker and self.batch_worker.isRunning():
            QMessageBox.information(
                self, "处理中", "当前有批量任务仍在进行中，请稍候。"
            )
            return
        self.interactive_translate_area.set_processed_blocks([])
        current_bg = self.interactive_translate_area.background_pixmap
        if not current_bg and self.original_pil_for_display:
            bg_pix = pil_to_qpixmap(self.original_pil_for_display)
            if bg_pix:
                self.interactive_translate_area.set_background_image(bg_pix)
        if self.text_detail_panel:
            self.text_detail_panel.clear_texts()
        self._update_block_controls(None)
        self.translate_button.setEnabled(False)
        self.load_action.setEnabled(False)
        self.load_batch_action.setEnabled(False)
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_widget.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("状态: 开始处理...")
        self.setWindowTitle(f"翻译中 - {os.path.basename(self.current_image_path)}")
        self.translation_worker = TranslationWorker(
            self.image_processor, self.current_image_path
        )
        self.translation_worker.progress_signal.connect(self._on_translation_progress)
        self.translation_worker.finished_signal.connect(self._on_translation_finished)
        self.translation_worker.start()

    @pyqtSlot(int, str)
    def _on_translation_progress(self, percentage: int, message: str):
        self.progress_bar.setValue(percentage)
        self.status_label.setText(f"状态: {message}")

    @pyqtSlot(object, object, str, str)
    def _on_translation_finished(
        self,
        original_pil_image_from_worker: Image.Image | None,
        processed_blocks: list | None,
        original_image_path_processed: str,
        error_message_str: str | None,
    ):
        if self.current_image_path != original_image_path_processed and not (
            self.batch_worker and self.batch_worker.isRunning()
        ):
            print(
                f"Ignoring stale translation result for: {original_image_path_processed}"
            )
            self._restore_ui_after_processing()
            self.translation_worker = None
            return
        current_bg_for_interactive = None
        if original_pil_image_from_worker:
            current_bg_for_interactive = pil_to_qpixmap(original_pil_image_from_worker)
        elif self.original_pil_for_display:
            current_bg_for_interactive = pil_to_qpixmap(self.original_pil_for_display)
        if current_bg_for_interactive and not current_bg_for_interactive.isNull():
            self.interactive_translate_area.set_background_image(
                current_bg_for_interactive
            )
        if self.text_detail_panel:
            self.text_detail_panel.clear_texts()
        if error_message_str and not processed_blocks:
            self.interactive_translate_area.set_processed_blocks([])
            self._handle_error_message(
                "处理失败",
                f"处理图片时出错:\n{error_message_str}",
                informative_text=f"图片路径: {original_image_path_processed}",
                show_settings_option=(
                    "API" in error_message_str
                    or "Key" in error_message_str
                    or "认证" in error_message_str
                ),
            )
            self.status_label.setText(
                f"状态: 失败 - {error_message_str.splitlines()[0]}"
            )
            self.download_button.setEnabled(False)
            self._update_block_controls(None)
        elif isinstance(processed_blocks, list):
            self.interactive_translate_area.set_processed_blocks(processed_blocks)
            if processed_blocks:
                self.download_button.setEnabled(True)
                self.status_label.setText("状态: 处理完成。")
                if not self.interactive_translate_area.selected_block:
                    self.interactive_translate_area.set_selected_block(
                        processed_blocks[0]
                    )
                else:
                    self._update_block_controls(
                        self.interactive_translate_area.selected_block
                    )
                if error_message_str:
                    QMessageBox.warning(
                        self,
                        "处理警告",
                        f"处理完成，但出现以下问题:\n{error_message_str}",
                    )
            else:
                self.download_button.setEnabled(False)
                no_text_msg = "完成，未检测到文本。"
                final_status = (
                    no_text_msg
                    if not error_message_str
                    else f"状态: {error_message_str.splitlines()[0]}"
                )
                self.status_label.setText(final_status)
                if error_message_str:
                    QMessageBox.information(
                        self, "处理信息", f"处理完成但报告:\n{error_message_str}"
                    )
                self._update_block_controls(None)
        else:
            self.interactive_translate_area.set_processed_blocks([])
            self.status_label.setText("状态: 失败 - 未知原因或意外结果。")
            self._update_block_controls(None)
            self.download_button.setEnabled(False)
            if error_message_str:
                self._handle_error_message(
                    "处理异常",
                    f"处理返回意外结果。\n错误信息: {error_message_str}",
                    informative_text=f"图片: {original_image_path_processed}",
                )
        self._restore_ui_after_processing()
        self.translation_worker = None
        self.setWindowTitle("Image Translator")

    def _restore_ui_after_processing(self):
        is_busy = bool(
            (self.translation_worker and self.translation_worker.isRunning())
            or (self.batch_worker and self.batch_worker.isRunning())
        )
        self.translate_button.setEnabled(
            self.current_image_path is not None and not is_busy
        )
        self.load_action.setEnabled(not is_busy)
        self.load_batch_action.setEnabled(not is_busy)
        self.cancel_button.setEnabled(is_busy)
        if not is_busy:
            self.progress_widget.setVisible(False)
            self.setWindowTitle("Image Translator")

    @pyqtSlot()
    def _on_download_clicked(self):
        if not self.interactive_translate_area.background_pixmap:
            QMessageBox.warning(self, "导出错误", "没有背景图像可导出。")
            return
        if not self.interactive_translate_area.processed_blocks:
            reply = QMessageBox.question(
                self,
                "导出确认",
                "当前没有文本块。是否要导出原始背景图片？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
            bg_qimage = self.interactive_translate_area.background_pixmap.toImage().convertToFormat(
                QImage.Format.Format_RGBA8888
            )
            if bg_qimage.isNull():
                QMessageBox.warning(self, "导出错误", "无法获取背景图像数据。")
                return
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.ReadWrite)
            bg_qimage.save(buffer, "PNG")
            buffer.seek(0)
            try:
                final_pil_to_save = Image.open(io.BytesIO(buffer.data()))
            except Exception as e:
                QMessageBox.warning(self, "导出错误", f"转换背景图像时出错: {e}")
                return
            finally:
                buffer.close()
            if final_pil_to_save.mode != "RGBA":
                final_pil_to_save = final_pil_to_save.convert("RGBA")
        else:
            final_pil_to_save = (
                self.interactive_translate_area.get_current_render_as_pil_image()
            )
            if not final_pil_to_save:
                QMessageBox.warning(self, "导出错误", "无法生成最终的渲染图像。")
                return
        save_filter = "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;BMP 图片 (*.bmp)"
        start_dir = self.config_manager.get(
            "UI", "last_save_dir", os.path.expanduser("~")
        )
        default_name = "translated_image.png"
        if self.current_image_path:
            base, _ = os.path.splitext(os.path.basename(self.current_image_path))
            default_name = f"{base}_translated.png"
        save_path, selected_filter = QFileDialog.getSaveFileName(
            self, "保存翻译后的图片", os.path.join(start_dir, default_name), save_filter
        )
        if save_path:
            format_map = {
                "PNG 图片 (*.png)": "PNG",
                "JPEG 图片 (*.jpg *.jpeg)": "JPEG",
                "BMP 图片 (*.bmp)": "BMP",
            }
            img_format = format_map.get(selected_filter, "PNG")
            save_dir = os.path.dirname(save_path)
            if not os.path.exists(save_dir):
                try:
                    os.makedirs(save_dir)
                except OSError as e:
                    QMessageBox.warning(
                        self, "保存错误", f"无法创建目录:\n{save_dir}\n错误: {e}"
                    )
                    return
            try:
                if img_format == "JPEG" and final_pil_to_save.mode == "RGBA":
                    print(
                        "Converting RGBA to RGB for JPEG export with white background."
                    )
                    rgb_image = Image.new(
                        "RGB", final_pil_to_save.size, (255, 255, 255)
                    )
                    rgb_image.paste(
                        final_pil_to_save, mask=final_pil_to_save.split()[3]
                    )
                    rgb_image.save(save_path, img_format, quality=95)
                else:
                    final_pil_to_save.save(save_path, img_format)
                QMessageBox.information(self, "成功", f"图片已成功保存至:\n{save_path}")
                self.config_manager.set(
                    "UI", "last_save_dir", os.path.dirname(save_path)
                )
            except Exception as e:
                import traceback

                print(f"Error saving file: {e}\n{traceback.format_exc()}")
                QMessageBox.warning(
                    self, "保存错误", f"无法保存图片至:\n{save_path}\n错误: {e}"
                )

    @pyqtSlot()
    def _on_load_batch_images(self):
        if (self.translation_worker and self.translation_worker.isRunning()) or (
            self.batch_worker and self.batch_worker.isRunning()
        ):
            QMessageBox.warning(
                self, "操作繁忙", "当前已有任务在进行中，请等待完成后再开始批量处理。"
            )
            return
        if not PILLOW_AVAILABLE:
            self._handle_error_message("依赖缺失", "Pillow 库未安装，无法处理图片。")
            return
        img_filter = "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff);;所有文件 (*)"
        start_dir = self.config_manager.get(
            "UI", "last_image_dir", os.path.expanduser("~")
        )
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择需要批量翻译的图片", start_dir, img_filter
        )
        if not file_paths:
            return
        output_dir = QFileDialog.getExistingDirectory(
            self, "选择翻译结果保存目录", start_dir
        )
        if not output_dir:
            return
        self.load_action.setEnabled(False)
        self.load_batch_action.setEnabled(False)
        self.translate_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_widget.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"状态: 开始批量处理 {len(file_paths)} 张图片...")
        self.setWindowTitle(f"批量处理中... (0%)")
        self.batch_worker = BatchTranslationWorker(
            self.image_processor, self.config_manager, file_paths, output_dir
        )
        self.batch_worker.overall_progress_signal.connect(
            self._on_batch_overall_progress
        )
        self.batch_worker.file_completed_signal.connect(self._on_batch_file_completed)
        self.batch_worker.batch_finished_signal.connect(self._on_batch_finished)
        self.batch_worker.start()

    @pyqtSlot(int, str)
    def _on_batch_overall_progress(self, percentage: int, message: str):
        self.progress_bar.setValue(percentage)
        self.status_label.setText(f"状态: {message}")
        self.setWindowTitle(
            f"批量处理中... ({percentage}%) {message.split(':')[-1].strip() if ':' in message else ''}"
        )

    @pyqtSlot(str, str, bool)
    def _on_batch_file_completed(
        self, original_path: str, output_info: str, success: bool
    ):
        self.config_manager.set("UI", "last_image_dir", os.path.dirname(original_path))

    @pyqtSlot(int, int, float, bool)
    def _on_batch_finished(
        self, processed_count: int, error_count: int, duration: float, cancelled: bool
    ):
        self.setWindowTitle("Image Translator")
        output_dir_msg = (
            getattr(self.batch_worker, "output_dir", "N/A")
            if self.batch_worker
            else "N/A"
        )
        self.batch_worker = None
        self._restore_ui_after_processing()
        status_prefix = "批量处理已取消" if cancelled else "批量处理完成"
        total_files = processed_count + error_count
        summary = (
            f"{status_prefix}。\n\n"
            f"总文件数: {total_files}\n"
            f"成功处理: {processed_count}\n"
            f"失败/跳过: {error_count}\n"
            f"总耗时: {duration:.2f} 秒\n\n"
            f"结果已保存至:\n{output_dir_msg}"
        )
        self.status_label.setText(
            f"状态: {status_prefix}。成功: {processed_count}, 失败/错误: {error_count}"
        )
        self.progress_bar.setValue(100)
        QMessageBox.information(self, status_prefix, summary)

    @pyqtSlot()
    def _on_cancel_processing(self):
        cancelled = False
        if self.translation_worker and self.translation_worker.isRunning():
            print("Cancelling single translation worker...")
            self.translation_worker.cancel()
            self.status_label.setText("状态: 正在取消单张图片处理...")
            cancelled = True
        elif self.batch_worker and self.batch_worker.isRunning():
            print("Cancelling batch translation worker...")
            self.batch_worker.cancel()
            self.status_label.setText("状态: 正在取消批量处理...")
            cancelled = True
        if cancelled:
            self.cancel_button.setEnabled(False)
        else:
            self.cancel_button.setEnabled(False)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self.original_pil_for_display:
            preview_pix = pil_to_qpixmap(self.original_pil_for_display)
            if preview_pix:
                self._display_image_in_label(self.original_preview_area, preview_pix)
        if self.current_bg_image_path and os.path.exists(self.current_bg_image_path):
            bg_pixmap_resized = QPixmap(self.current_bg_image_path)
            if not bg_pixmap_resized.isNull():
                self._apply_window_background(bg_pixmap_resized)
        if (
            hasattr(self, "interactive_translate_area")
            and self.interactive_translate_area
        ):
            self.interactive_translate_area._scale_background_and_view()
        if hasattr(self, "splitter") and self.splitter and self.splitter.count() == 3:
            sizes = self.splitter.sizes()
            if not sizes or sum(sizes) == 0 or sizes[0] == 0:
                total_width = self.splitter.width()
                if total_width > 50:
                    self.splitter.setSizes(
                        [total_width // 3, total_width // 3, total_width // 3]
                    )

    def closeEvent(self, event):
        reply = QMessageBox.StandardButton.Yes
        if (self.translation_worker and self.translation_worker.isRunning()) or (
            self.batch_worker and self.batch_worker.isRunning()
        ):
            reply = QMessageBox.question(
                self,
                "退出确认",
                "当前有处理任务正在进行中，确定要退出吗？\n（未完成的任务将被取消）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        if reply == QMessageBox.StandardButton.Yes:
            print("退出应用")
            if self.translation_worker and self.translation_worker.isRunning():
                print("停止翻译任务")
                self.translation_worker.cancel()
                if not self.translation_worker.wait(500):
                    print("Translation worker did not stop gracefully.")
            if self.batch_worker and self.batch_worker.isRunning():
                print("停止批量翻译任务")
                self.batch_worker.cancel()
                if not self.batch_worker.wait(500):
                    print("批量翻译任务停止失败")
            print("保存配置...")
            self.config_manager.save()
            print("配置已保存，关闭。")
            event.accept()
        else:
            print("Close event ignored.")
            event.ignore()


if __name__ == "__main__":
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec())
