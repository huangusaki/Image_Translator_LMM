import sys
import os
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QSpacerItem,
    QSizePolicy,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSlot, pyqtSignal


class TextStyleSettingsDialog(QDialog):
    settings_applied = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文本样式设置（全局）")
        self.config_manager = config_manager
        self.setMinimumWidth(500)
        self._init_ui()
        self._load_settings()
        self._connect_signals()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        text_style_group = QGroupBox("文本样式")
        text_style_layout = QVBoxLayout(text_style_group)
        text_style_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        font_name_layout = QHBoxLayout()
        font_name_label = QLabel("字体名称/路径:")
        self.font_name_edit = QLineEdit()
        font_name_layout.addWidget(font_name_label)
        font_name_layout.addWidget(self.font_name_edit, 1)
        text_style_layout.addLayout(font_name_layout)
        fixed_font_size_layout = QHBoxLayout()
        fixed_font_size_label = QLabel("固定字体大小 (0 则动态):")
        self.fixed_font_size_edit = QLineEdit()
        self.fixed_font_size_edit.setPlaceholderText("例如: 28 (0 表示动态调整)")
        self.fixed_font_size_edit.setToolTip(
            "设置一个固定的字体大小。如果为0或空，则使用LLM建议的类别映射。"
        )
        fixed_font_size_layout.addWidget(fixed_font_size_label)
        fixed_font_size_layout.addWidget(self.fixed_font_size_edit, 0)
        text_style_layout.addLayout(fixed_font_size_layout)
        h_text_spacing_group = QGroupBox("横排文本间距")
        h_text_spacing_layout = QVBoxLayout(h_text_spacing_group)
        h_char_spacing_layout = QHBoxLayout()
        h_char_spacing_label = QLabel("字符间距 (像素):")
        self.h_text_char_spacing_edit = QLineEdit()
        self.h_text_char_spacing_edit.setPlaceholderText("例如: 1 (可为负)")
        h_char_spacing_layout.addWidget(h_char_spacing_label)
        h_char_spacing_layout.addWidget(self.h_text_char_spacing_edit, 0)
        h_text_spacing_layout.addLayout(h_char_spacing_layout)
        h_line_spacing_layout = QHBoxLayout()
        h_line_spacing_label = QLabel("行间距 (像素):")
        self.h_text_line_spacing_edit = QLineEdit()
        self.h_text_line_spacing_edit.setPlaceholderText("例如: 2 (可为负)")
        h_line_spacing_layout.addWidget(h_line_spacing_label)
        h_line_spacing_layout.addWidget(self.h_text_line_spacing_edit, 0)
        h_text_spacing_layout.addLayout(h_line_spacing_layout)
        text_style_layout.addWidget(h_text_spacing_group)
        v_text_spacing_group = QGroupBox("竖排文本间距")
        v_text_spacing_layout = QVBoxLayout(v_text_spacing_group)
        v_column_spacing_layout = QHBoxLayout()
        v_column_spacing_label = QLabel("列间距 (像素):")
        self.v_text_column_spacing_edit = QLineEdit()
        self.v_text_column_spacing_edit.setPlaceholderText("例如: 5 (可为负)")
        v_column_spacing_layout.addWidget(v_column_spacing_label)
        v_column_spacing_layout.addWidget(self.v_text_column_spacing_edit, 0)
        v_text_spacing_layout.addLayout(v_column_spacing_layout)
        v_char_spacing_layout = QHBoxLayout()
        v_char_spacing_label = QLabel("字间距 (像素):")
        self.v_text_char_spacing_edit = QLineEdit()
        self.v_text_char_spacing_edit.setPlaceholderText("例如: 2 (可为负)")
        v_char_spacing_layout.addWidget(v_char_spacing_label)
        v_char_spacing_layout.addWidget(self.v_text_char_spacing_edit, 0)
        v_text_spacing_layout.addLayout(v_char_spacing_layout)
        text_style_layout.addWidget(v_text_spacing_group)
        manual_break_spacing_group = QGroupBox("手动换行/换列额外间距")
        manual_break_spacing_layout = QVBoxLayout(manual_break_spacing_group)
        h_manual_break_layout = QHBoxLayout()
        h_manual_break_label = QLabel("横排手动换行额外间距 (像素):")
        self.h_manual_break_extra_spacing_edit = QLineEdit()
        self.h_manual_break_extra_spacing_edit.setPlaceholderText("例如: 0 (可为负)")
        h_manual_break_layout.addWidget(h_manual_break_label)
        h_manual_break_layout.addWidget(self.h_manual_break_extra_spacing_edit, 0)
        manual_break_spacing_layout.addLayout(h_manual_break_layout)
        v_manual_break_layout = QHBoxLayout()
        v_manual_break_label = QLabel("竖排手动换列额外间距 (像素):")
        self.v_manual_break_extra_spacing_edit = QLineEdit()
        self.v_manual_break_extra_spacing_edit.setPlaceholderText("例如: 0 (可为负)")
        v_manual_break_layout.addWidget(v_manual_break_label)
        v_manual_break_layout.addWidget(self.v_manual_break_extra_spacing_edit, 0)
        manual_break_spacing_layout.addLayout(v_manual_break_layout)
        text_style_layout.addWidget(manual_break_spacing_group)
        main_color_layout = QHBoxLayout()
        main_color_label = QLabel("文本主颜色 (R,G,B,A):")
        self.text_main_color_edit = QLineEdit()
        self.text_main_color_edit.setPlaceholderText("例如: 255,255,255,255")
        main_color_layout.addWidget(main_color_label)
        main_color_layout.addWidget(self.text_main_color_edit, 1)
        text_style_layout.addLayout(main_color_layout)
        outline_color_layout = QHBoxLayout()
        outline_color_label = QLabel("文本描边颜色 (R,G,B,A):")
        self.text_outline_color_edit = QLineEdit()
        self.text_outline_color_edit.setPlaceholderText("例如: 0,0,0,255")
        outline_color_layout.addWidget(outline_color_label)
        outline_color_layout.addWidget(self.text_outline_color_edit, 1)
        text_style_layout.addLayout(outline_color_layout)
        outline_thickness_layout = QHBoxLayout()
        outline_thickness_label = QLabel("文本描边厚度 (像素):")
        self.text_outline_thickness_edit = QLineEdit()
        self.text_outline_thickness_edit.setPlaceholderText("例如: 2")
        outline_thickness_layout.addWidget(outline_thickness_label)
        outline_thickness_layout.addWidget(self.text_outline_thickness_edit, 0)
        text_style_layout.addLayout(outline_thickness_layout)
        text_bg_color_layout = QHBoxLayout()
        text_bg_color_label = QLabel("文本背景颜色 (R,G,B,A):")
        self.text_bg_color_edit = QLineEdit()
        self.text_bg_color_edit.setPlaceholderText("例如: 0,0,0,128")
        text_bg_color_layout.addWidget(text_bg_color_label)
        text_bg_color_layout.addWidget(self.text_bg_color_edit, 1)
        text_style_layout.addLayout(text_bg_color_layout)
        main_layout.addWidget(text_style_group)
        button_layout = QHBoxLayout()
        button_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        self.apply_button = QPushButton("应用")
        self.save_button = QPushButton("保存")
        self.cancel_button = QPushButton("取消")
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

    def _load_settings(self):
        self.font_name_edit.setText(
            self.config_manager.get("UI", "font_name", fallback="msyh.ttc")
        )
        self.fixed_font_size_edit.setText(
            self.config_manager.get("UI", "fixed_font_size", fallback="0")
        )
        self.h_text_char_spacing_edit.setText(
            self.config_manager.get("UI", "h_text_char_spacing_px", fallback="0")
        )
        self.h_text_line_spacing_edit.setText(
            self.config_manager.get("UI", "h_text_line_spacing_px", fallback="0")
        )
        self.v_text_column_spacing_edit.setText(
            self.config_manager.get("UI", "v_text_column_spacing_px", fallback="0")
        )
        self.v_text_char_spacing_edit.setText(
            self.config_manager.get("UI", "v_text_char_spacing_px", fallback="0")
        )
        self.h_manual_break_extra_spacing_edit.setText(
            self.config_manager.get(
                "UI", "h_manual_break_extra_spacing_px", fallback="0"
            )
        )
        self.v_manual_break_extra_spacing_edit.setText(
            self.config_manager.get(
                "UI", "v_manual_break_extra_spacing_px", fallback="0"
            )
        )
        self.text_main_color_edit.setText(
            self.config_manager.get("UI", "text_main_color", fallback="255,255,255,255")
        )
        self.text_outline_color_edit.setText(
            self.config_manager.get("UI", "text_outline_color", fallback="0,0,0,255")
        )
        self.text_outline_thickness_edit.setText(
            self.config_manager.get("UI", "text_outline_thickness", fallback="2")
        )
        self.text_bg_color_edit.setText(
            self.config_manager.get("UI", "text_background_color", fallback="0,0,0,128")
        )

    def _save_settings(self):
        self.config_manager.set("UI", "font_name", self.font_name_edit.text())
        fixed_font_size_to_save = self.fixed_font_size_edit.text().strip()
        if not fixed_font_size_to_save:
            fixed_font_size_to_save = "0"
        self.config_manager.set("UI", "fixed_font_size", fixed_font_size_to_save)
        self.config_manager.set(
            "UI",
            "h_text_char_spacing_px",
            self.h_text_char_spacing_edit.text().strip() or "0",
        )
        self.config_manager.set(
            "UI",
            "h_text_line_spacing_px",
            self.h_text_line_spacing_edit.text().strip() or "0",
        )
        self.config_manager.set(
            "UI",
            "v_text_column_spacing_px",
            self.v_text_column_spacing_edit.text().strip() or "0",
        )
        self.config_manager.set(
            "UI",
            "v_text_char_spacing_px",
            self.v_text_char_spacing_edit.text().strip() or "0",
        )
        self.config_manager.set(
            "UI",
            "h_manual_break_extra_spacing_px",
            self.h_manual_break_extra_spacing_edit.text().strip() or "0",
        )
        self.config_manager.set(
            "UI",
            "v_manual_break_extra_spacing_px",
            self.v_manual_break_extra_spacing_edit.text().strip() or "0",
        )
        self.config_manager.set(
            "UI", "text_main_color", self.text_main_color_edit.text()
        )
        self.config_manager.set(
            "UI", "text_outline_color", self.text_outline_color_edit.text()
        )
        self.config_manager.set(
            "UI", "text_outline_thickness", self.text_outline_thickness_edit.text()
        )
        self.config_manager.set(
            "UI", "text_background_color", self.text_bg_color_edit.text()
        )
        return True

    def _connect_signals(self):
        self.save_button.clicked.connect(self.on_save)
        self.apply_button.clicked.connect(self.on_apply)
        self.cancel_button.clicked.connect(self.reject)

    def _perform_validation(self):
        fixed_font_size_str = self.fixed_font_size_edit.text().strip()
        if fixed_font_size_str:
            if not fixed_font_size_str.isdigit() or int(fixed_font_size_str) < 0:
                QMessageBox.warning(
                    self,
                    "输入错误",
                    "固定字体大小必须是一个非负整数。\n如果想使用动态大小，请留空或填0。",
                )
                self.fixed_font_size_edit.setFocus()
                return False
        for edit_field, name in [
            (self.h_text_char_spacing_edit, "横排文本字符间距"),
            (self.h_text_line_spacing_edit, "横排文本行间距"),
            (self.v_text_column_spacing_edit, "竖排文本列间距"),
            (self.v_text_char_spacing_edit, "竖排文本字间距"),
            (self.h_manual_break_extra_spacing_edit, "横排手动换行额外间距"),
            (self.v_manual_break_extra_spacing_edit, "竖排手动换列额外间距"),
        ]:
            spacing_str = edit_field.text().strip()
            if spacing_str:
                try:
                    int(spacing_str)
                except ValueError:
                    QMessageBox.warning(self, "输入错误", f"{name}必须是一个整数。")
                    edit_field.setFocus()
                    return False
        for edit_field, name in [
            (self.text_main_color_edit, "文本主颜色"),
            (self.text_outline_color_edit, "文本描边颜色"),
            (self.text_bg_color_edit, "文本背景颜色"),
        ]:
            color_str = edit_field.text().strip()
            if not color_str:
                QMessageBox.warning(self, "输入错误", f"{name} 不能为空。")
                edit_field.setFocus()
                return False
            parts = color_str.split(",")
            if not (len(parts) == 3 or len(parts) == 4) or not all(
                p.strip().isdigit() for p in parts
            ):
                QMessageBox.warning(
                    self,
                    "输入错误",
                    f"{name} 格式不正确。应为 R,G,B 或 R,G,B,A 格式，例如 255,255,255,255。",
                )
                edit_field.setFocus()
                return False
            for part_str in parts:
                try:
                    val = int(part_str.strip())
                    if not (0 <= val <= 255):
                        QMessageBox.warning(
                            self, "输入错误", f"{name} 中的颜色值必须在 0 到 255 之间。"
                        )
                        edit_field.setFocus()
                        return False
                except ValueError:
                    QMessageBox.warning(self, "输入错误", f"{name} 包含无效数字。")
                    edit_field.setFocus()
                    return False
        thickness_str = self.text_outline_thickness_edit.text().strip()
        if not thickness_str.isdigit():
            QMessageBox.warning(
                self, "输入错误", "文本描边厚度必须是一个非负整数数字。"
            )
            self.text_outline_thickness_edit.setFocus()
            return False
        return True

    @pyqtSlot()
    def on_apply(self):
        if self._perform_validation():
            if self._save_settings():
                self.config_manager.save()
                self.settings_applied.emit()
                QMessageBox.information(
                    self, "应用成功", "设置已应用。更改应在预览中实时显示。"
                )

    @pyqtSlot()
    def on_save(self):
        if self._perform_validation():
            if self._save_settings():
                self.accept()


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication

    class MockConfigManager:
        def __init__(self):
            self.config = {"UI": {}}
            self.config["UI"]["font_name"] = "msyh.ttc"
            self.config["UI"]["fixed_font_size"] = "0"
            self.config["UI"]["h_text_char_spacing_px"] = "0"
            self.config["UI"]["h_text_line_spacing_px"] = "0"
            self.config["UI"]["v_text_column_spacing_px"] = "0"
            self.config["UI"]["v_text_char_spacing_px"] = "0"
            self.config["UI"]["h_manual_break_extra_spacing_px"] = "0"
            self.config["UI"]["v_manual_break_extra_spacing_px"] = "0"
            self.config["UI"]["text_main_color"] = "255,255,255,255"
            self.config["UI"]["text_outline_color"] = "0,0,0,255"
            self.config["UI"]["text_outline_thickness"] = "2"
            self.config["UI"]["text_background_color"] = "0,0,0,128"

        def get(self, section, key, fallback=None):
            return self.config.get(section, {}).get(key, fallback)

        def set(self, section, key, value):
            if section not in self.config:
                self.config[section] = {}
            self.config[section][key] = value

        def save(self):
            pass

    app = QApplication(sys.argv)
    config_manager = MockConfigManager()
    dialog = TextStyleSettingsDialog(config_manager)
    dialog.show()
    sys.exit(app.exec())
