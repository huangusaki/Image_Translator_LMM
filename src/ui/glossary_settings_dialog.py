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
    QFileDialog,
    QWidget,
    QSpacerItem,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QTextEdit,
)
from PyQt6.QtCore import Qt, pyqtSlot


class GlossarySettingsDialog(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("术语表设置")
        self.config_manager = config_manager
        self.glossary_terms = []
        self.setMinimumWidth(550)
        self._init_ui()
        self._load_glossary_from_config()
        self._connect_signals()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        glossary_group = QGroupBox("术语表管理")
        glossary_group_layout = QVBoxLayout(glossary_group)
        glossary_add_term_layout = QHBoxLayout()
        self.glossary_source_term_edit = QLineEdit()
        self.glossary_source_term_edit.setPlaceholderText("待翻译译文的术语")
        self.glossary_target_term_edit = QLineEdit()
        self.glossary_target_term_edit.setPlaceholderText("翻译译文")
        self.glossary_add_term_button = QPushButton("添加")
        glossary_add_term_layout.addWidget(self.glossary_source_term_edit, 2)
        glossary_add_term_layout.addWidget(QLabel(" => "), 0)
        glossary_add_term_layout.addWidget(self.glossary_target_term_edit, 2)
        glossary_add_term_layout.addWidget(self.glossary_add_term_button, 1)
        glossary_group_layout.addLayout(glossary_add_term_layout)
        self.glossary_list_widget = QListWidget()
        self.glossary_list_widget.setMinimumHeight(150)
        glossary_group_layout.addWidget(self.glossary_list_widget)
        glossary_list_actions_layout = QHBoxLayout()
        self.glossary_delete_selected_button = QPushButton("删除选中")
        glossary_list_actions_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        glossary_list_actions_layout.addWidget(self.glossary_delete_selected_button)
        glossary_group_layout.addLayout(glossary_list_actions_layout)
        self.glossary_bulk_text_edit = QTextEdit()
        self.glossary_bulk_text_edit.setPlaceholderText(
            "批量导入术语表 (每行格式: 原文->译文[ #可选注释])\n例如:\nリエル->莉艾露\nGloria->格洛丽亚 # 角色名"
        )
        self.glossary_bulk_text_edit.setMinimumHeight(100)
        glossary_group_layout.addWidget(self.glossary_bulk_text_edit)
        glossary_bulk_actions_layout = QHBoxLayout()
        self.glossary_parse_from_text_button = QPushButton("从文本区加载到列表")
        self.glossary_populate_text_from_list_button = QPushButton("从列表填充到文本区")
        glossary_bulk_actions_layout.addWidget(self.glossary_parse_from_text_button)
        glossary_bulk_actions_layout.addWidget(
            self.glossary_populate_text_from_list_button
        )
        glossary_group_layout.addLayout(glossary_bulk_actions_layout)
        glossary_file_actions_layout = QHBoxLayout()
        self.glossary_import_file_button = QPushButton("导入文件")
        self.glossary_export_file_button = QPushButton("导出文件")
        glossary_file_actions_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        glossary_file_actions_layout.addWidget(self.glossary_import_file_button)
        glossary_file_actions_layout.addWidget(self.glossary_export_file_button)
        glossary_group_layout.addLayout(glossary_file_actions_layout)
        main_layout.addWidget(glossary_group)
        button_layout = QHBoxLayout()
        button_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        self.save_button = QPushButton("保存")
        self.cancel_button = QPushButton("取消")
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

    def _parse_glossary_line(self, line: str) -> tuple[str, str, str] | None:
        line = line.strip()
        if not line or "->" not in line:
            return None
        parts = line.split("->", 1)
        source = parts[0].strip()
        target_and_comment = parts[1].split("#", 1)
        target = target_and_comment[0].strip()
        if source and target:
            return source, target, line
        return None

    def _load_glossary_from_config(self):
        self.glossary_terms.clear()
        self.glossary_list_widget.clear()
        self.glossary_bulk_text_edit.clear()
        raw_glossary_text = self.config_manager.get(
            "GeminiAPI", "glossary_text", fallback=""
        )
        self.glossary_bulk_text_edit.setPlainText(raw_glossary_text)
        self._parse_and_load_from_bulk_text()

    def _parse_and_load_from_bulk_text(self):
        self.glossary_terms.clear()
        self.glossary_list_widget.clear()
        lines = self.glossary_bulk_text_edit.toPlainText().splitlines()
        for line in lines:
            parsed_term = self._parse_glossary_line(line)
            if parsed_term:
                source, target, original_line = parsed_term
                self.glossary_terms.append((source, target, original_line))
                display_text = f"{source} => {target}"
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, len(self.glossary_terms) - 1)
                self.glossary_list_widget.addItem(item)

    def _populate_bulk_text_from_list(self):
        all_lines = []
        for source, target, original_line in self.glossary_terms:
            if (
                "#" in original_line
                and original_line.startswith(source)
                and "->" in original_line
            ):
                all_lines.append(original_line)
            else:
                all_lines.append(f"{source}->{target}")
        self.glossary_bulk_text_edit.setPlainText("\n".join(all_lines))

    def _add_glossary_term(self):
        source = self.glossary_source_term_edit.text().strip()
        target = self.glossary_target_term_edit.text().strip()
        if not source or not target:
            QMessageBox.warning(self, "输入错误", "原文和译文均不能为空。")
            return
        for s, _, _ in self.glossary_terms:
            if s == source:
                QMessageBox.warning(
                    self, "重复术语", f"原文 '{source}' 已存在于术语表中。"
                )
                return
        original_line = f"{source}->{target}"
        self.glossary_terms.append((source, target, original_line))
        display_text = f"{source} => {target}"
        item = QListWidgetItem(display_text)
        item.setData(Qt.ItemDataRole.UserRole, len(self.glossary_terms) - 1)
        self.glossary_list_widget.addItem(item)
        self.glossary_source_term_edit.clear()
        self.glossary_target_term_edit.clear()
        self.glossary_source_term_edit.setFocus()

    def _delete_selected_glossary_term(self):
        selected_items = self.glossary_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "提示", "请先从列表中选择要删除的术语。")
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_items)} 条术语吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return
        indices_to_remove_from_terms_list = sorted(
            [item.data(Qt.ItemDataRole.UserRole) for item in selected_items],
            reverse=True,
        )
        for list_item in selected_items:
            self.glossary_list_widget.takeItem(self.glossary_list_widget.row(list_item))
        for idx_in_terms in indices_to_remove_from_terms_list:
            if 0 <= idx_in_terms < len(self.glossary_terms):
                del self.glossary_terms[idx_in_terms]
        self._rebuild_list_widget_from_terms()

    def _rebuild_list_widget_from_terms(self):
        self.glossary_list_widget.clear()
        for i, (source, target, _) in enumerate(self.glossary_terms):
            display_text = f"{source} => {target}"
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.glossary_list_widget.addItem(item)

    def _import_glossary_from_file(self):
        start_dir = self.config_manager.get(
            "UI", "last_glossary_dir", os.path.expanduser("~")
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入术语文件", start_dir, "文本文件 (*.txt);;所有文件 (*)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_text_from_file = f.read()
            reply = QMessageBox.question(
                self,
                "导入模式",
                "追加到当前术语列表还是替换整个列表？\n(Yes=追加, No=替换)",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.No:
                self.glossary_terms.clear()
            newly_parsed_terms_count = 0
            existing_sources = {s for s, _, _ in self.glossary_terms}
            lines = raw_text_from_file.splitlines()
            for line in lines:
                parsed_term = self._parse_glossary_line(line)
                if parsed_term:
                    source, target, original_line = parsed_term
                    if source not in existing_sources:
                        self.glossary_terms.append((source, target, original_line))
                        existing_sources.add(source)
                        newly_parsed_terms_count += 1
            self._rebuild_list_widget_from_terms()
            self.config_manager.set(
                "UI", "last_glossary_dir", os.path.dirname(file_path)
            )
            QMessageBox.information(
                self,
                "导入完成",
                f"成功从文件导入/合并了 {newly_parsed_terms_count} 条新术语。\n总术语数: {len(self.glossary_terms)}",
            )
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"读取或解析文件时发生错误: {e}")

    def _export_glossary_to_file(self):
        if not self.glossary_terms:
            QMessageBox.information(self, "提示", "术语表为空，无需导出。")
            return
        start_dir = self.config_manager.get(
            "UI", "last_glossary_dir", os.path.expanduser("~")
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出术语文件",
            os.path.join(start_dir, "glossary.txt"),
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if not file_path:
            return
        try:
            all_lines = []
            for source, target, original_line in self.glossary_terms:
                if (
                    "#" in original_line
                    and original_line.startswith(source)
                    and "->" in original_line
                ):
                    all_lines.append(original_line)
                else:
                    all_lines.append(f"{source}->{target}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(all_lines))
            self.config_manager.set(
                "UI", "last_glossary_dir", os.path.dirname(file_path)
            )
            QMessageBox.information(
                self, "导出成功", f"术语表已成功导出到: {file_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"保存文件时发生错误: {e}")

    def _connect_signals(self):
        self.save_button.clicked.connect(self.on_save)
        self.cancel_button.clicked.connect(self.reject)
        self.glossary_add_term_button.clicked.connect(self._add_glossary_term)
        self.glossary_delete_selected_button.clicked.connect(
            self._delete_selected_glossary_term
        )
        self.glossary_parse_from_text_button.clicked.connect(
            self._parse_and_load_from_bulk_text
        )
        self.glossary_populate_text_from_list_button.clicked.connect(
            self._populate_bulk_text_from_list
        )
        self.glossary_import_file_button.clicked.connect(
            self._import_glossary_from_file
        )
        self.glossary_export_file_button.clicked.connect(self._export_glossary_to_file)

    def _save_glossary_to_config(self):
        all_lines = []
        for source, target, original_line in self.glossary_terms:
            if (
                "#" in original_line
                and original_line.startswith(source)
                and "->" in original_line
            ):
                all_lines.append(original_line)
            else:
                all_lines.append(f"{source}->{target}")
        self.config_manager.set("GeminiAPI", "glossary_text", "\n".join(all_lines))

    @pyqtSlot()
    def on_save(self):
        self._save_glossary_to_config()
        self.accept()
