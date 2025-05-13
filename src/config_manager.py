import configparser
import os

CONFIG_FILE = "config.ini"
DEFAULT_CONFIG = {
    "UI": {
        "background_image_path": "",
        "window_icon_path": "",
        "background_fill_mode": "contain",
        "background_opacity": "0.15",
        "last_image_dir": os.path.expanduser("~"),
        "last_bg_dir": os.path.expanduser("~"),
        "last_icon_dir": os.path.expanduser("~"),
        "last_save_dir": os.path.expanduser("~"),
        "last_glossary_dir": os.path.expanduser("~"),
        "font_name": "msyh.ttc",
        "fixed_font_size": "0",
        "text_padding": "3",
        "min_font_size": "20",
        "max_font_size": "96",
        "text_main_color": "255,255,255,255",
        "text_outline_color": "0,0,0,255",
        "text_outline_thickness": "2",
        "text_background_color": "0,0,0,128",
        "h_text_char_spacing_px": "0",
        "h_text_line_spacing_px": "0",
        "v_text_column_spacing_px": "0",
        "v_text_char_spacing_px": "0",
        "h_manual_break_extra_spacing_px": "0",
        "v_manual_break_extra_spacing_px": "0",
        "auto_adjust_bbox_to_fit_text": "True",
    },
    "FontSizeMapping": {
        "very_small": "12",
        "small": "16",
        "medium": "22",
        "large": "28",
        "very_large": "36",
    },
    "API": {
        "ocr_provider": "gemini",
        "translation_provider": "gemini",
        "fallback_ocr_provider": "google cloud vision",
    },
    "GeminiAPI": {
        "api_key": "",
        "model_name": "gemini-1.5-flash-latest",
        "gemini_base_url": "",
        "request_timeout": "60",
        "target_language": "Chinese",
        "source_language": "Japanese",
        "glossary_text": "",
    },
    "GoogleAPI": {
        "service_account_json": "",
    },
    "Proxy": {
        "enabled": "False",
        "type": "http",
        "host": "127.0.0.1",
        "port": "21524",
    },
    "LLMImagePreprocessing": {
        "enabled": "False",
        "upscale_factor": "1.5",
        "contrast_factor": "1.2",
        "upscale_resample_method": "LANCZOS",
    },
}


class ConfigManager:
    def __init__(self, config_path=CONFIG_FILE):
        self.config_path = config_path
        self.config = configparser.ConfigParser(interpolation=None)
        self._load_or_create_config()

    def _load_or_create_config(self):
        if not os.path.exists(self.config_path):
            print(f"配置文件 '{self.config_path}' 不存在，将使用默认值创建。")
            for section, options in DEFAULT_CONFIG.items():
                if not self.config.has_section(section):
                    self.config.add_section(section)
                for option, value in options.items():
                    self.config.set(section, option, str(value))
            self._save_config_to_file()
        else:
            try:
                self.config.read(self.config_path, encoding="utf-8")
                self._ensure_config_integrity()
            except Exception as e:
                print(
                    f"读取配置文件 '{self.config_path}' 时出错: {e}。将使用内存中的默认配置。"
                )
                self.config = configparser.ConfigParser(interpolation=None)
                for section, options in DEFAULT_CONFIG.items():
                    if not self.config.has_section(section):
                        self.config.add_section(section)
                    for option, value in options.items():
                        self.config.set(section, option, str(value))

    def _ensure_config_integrity(self):
        needs_update = False
        for section, default_options in DEFAULT_CONFIG.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
                needs_update = True
                print(f"配置文件缺少节 '[{section}]', 已添加。")
            current_options_in_section = (
                set(self.config.options(section))
                if self.config.has_section(section)
                else set()
            )
            for option, default_value in default_options.items():
                if not self.config.has_option(section, option):
                    self.config.set(section, option, str(default_value))
                    needs_update = True
                    print(
                        f"配置文件缺少选项 '{option}' 在节 '[{section}]' 下, 已添加默认值 '{default_value}'。"
                    )
        if needs_update:
            self._save_config_to_file()

    def _save_config_to_file(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as configfile:
                self.config.write(configfile)
        except Exception as e:
            print(f"保存配置文件 '{self.config_path}' 时出错: {e}")

    def get(self, section, option, fallback=None):
        try:
            return self.config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if (
                fallback is None
                and section in DEFAULT_CONFIG
                and option in DEFAULT_CONFIG[section]
            ):
                return str(DEFAULT_CONFIG[section][option])
            return fallback

    def getboolean(self, section, option, fallback=False):
        try:
            return self.config.getboolean(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if section in DEFAULT_CONFIG and option in DEFAULT_CONFIG[section]:
                val_str = str(DEFAULT_CONFIG[section][option]).lower()
                return val_str in ("true", "yes", "1", "on")
            return fallback
        except ValueError:
            if section in DEFAULT_CONFIG and option in DEFAULT_CONFIG[section]:
                val_str = str(DEFAULT_CONFIG[section][option]).lower()
                return val_str in ("true", "yes", "1", "on")
            return fallback

    def getint(self, section, option, fallback=0):
        try:
            return self.config.getint(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if section in DEFAULT_CONFIG and option in DEFAULT_CONFIG[section]:
                try:
                    return int(DEFAULT_CONFIG[section][option])
                except (ValueError, TypeError):
                    return fallback
            return fallback
        except ValueError:
            if section in DEFAULT_CONFIG and option in DEFAULT_CONFIG[section]:
                try:
                    return int(DEFAULT_CONFIG[section][option])
                except (ValueError, TypeError):
                    return fallback
            return fallback

    def getfloat(self, section, option, fallback=0.0):
        try:
            return self.config.getfloat(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if section in DEFAULT_CONFIG and option in DEFAULT_CONFIG[section]:
                try:
                    return float(DEFAULT_CONFIG[section][option])
                except (ValueError, TypeError):
                    return fallback
            return fallback
        except ValueError:
            if section in DEFAULT_CONFIG and option in DEFAULT_CONFIG[section]:
                try:
                    return float(DEFAULT_CONFIG[section][option])
                except (ValueError, TypeError):
                    return fallback
            return fallback

    def set(self, section, option, value):
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, option, str(value))

    def save(self):
        self._save_config_to_file()

    def get_raw_config_parser(self):
        return self.config
