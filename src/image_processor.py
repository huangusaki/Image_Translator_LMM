import os
import time
import json
import sys
import threading
import base64
from io import BytesIO
from config_manager import ConfigManager
from utils.utils import _render_single_block_pil_for_preview
from utils.font_utils import (
    PILLOW_AVAILABLE,
    get_pil_font,
    get_font_line_height,
    wrap_text_pil,
)

if PILLOW_AVAILABLE:
    from PIL import Image, ImageDraw, ImageFont
try:
    from google import genai
    from google.genai import types as google_genai_types

    GENAI_LIB_AVAILABLE = True
except ImportError:
    GENAI_LIB_AVAILABLE = False
    genai = None
    google_genai_types = None
    print(
        "警告: 未安装 google-genai 库。Gemini 功能将不可用。请确认已执行 pip install -U -q 'google-genai'"
    )
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("警告: 未安装 numpy 库。LLM图像对比度增强功能将不可用。")


class ProcessedBlock:
    def __init__(
        self,
        original_text: str,
        translated_text: str,
        bbox: list[int],
        orientation: str = "horizontal",
        font_size_category: str = "medium",
        font_size_pixels: int = 22,
        angle: float = 0.0,
        id: str | int | None = None,
        text_align: str | None = None,
    ):
        self.id = id if id is not None else str(time.time_ns())
        self.original_text = original_text
        self.translated_text = translated_text
        self.bbox = bbox
        if orientation not in ["horizontal", "vertical_ltr", "vertical_rtl"]:
            self.orientation = "horizontal"
        else:
            self.orientation = orientation
        valid_categories = ["very_small", "small", "medium", "large", "very_large"]
        if font_size_category not in valid_categories:
            self.font_size_category = "medium"
        else:
            self.font_size_category = font_size_category
        self.font_size_pixels = font_size_pixels
        self.angle = angle
        if text_align is None:
            if self.orientation != "horizontal":
                self.text_align = "right"
            else:
                self.text_align = "left"
        else:
            self.text_align = text_align

    def __repr__(self):
        return (
            f"ProcessedBlock(id='{self.id}', original='{self.original_text[:10]}...', translated='{self.translated_text[:10]}...', "
            f"bbox={self.bbox}, orientation='{self.orientation}', font_size_category='{self.font_size_category}', "
            f"font_px={self.font_size_pixels}, angle={self.angle}, text_align='{self.text_align}')"
        )


class ImageProcessor:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.last_error = None
        self.dependencies = self._check_internal_dependencies()
        self.genai_client: genai.Client | None = None
        self.configured_model_name: str | None = None
        self._apply_proxy_settings_to_env()
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

    def _apply_proxy_settings_to_env(self):
        if self.config_manager.getboolean("Proxy", "enabled", fallback=False):
            proxy_host = self.config_manager.get("Proxy", "host")
            proxy_port = self.config_manager.get("Proxy", "port")
            if proxy_host and proxy_port:
                proxy_url = f"http://{proxy_host}:{proxy_port}"
                os.environ["HTTPS_PROXY"] = proxy_url
                os.environ["HTTP_PROXY"] = proxy_url
        else:
            current_https_proxy = os.environ.get("HTTPS_PROXY", "")
            current_http_proxy = os.environ.get("HTTP_PROXY", "")
            proxy_host_check = self.config_manager.get("Proxy", "host", "")
            if "HTTPS_PROXY" in os.environ and (
                current_https_proxy.startswith("http://127.0.0.1")
                or (proxy_host_check and proxy_host_check in current_https_proxy)
            ):
                del os.environ["HTTPS_PROXY"]
            if "HTTP_PROXY" in os.environ and (
                current_http_proxy.startswith("http://127.0.0.1")
                or (proxy_host_check and proxy_host_check in current_http_proxy)
            ):
                del os.environ["HTTP_PROXY"]

    def _check_internal_dependencies(self):
        return {
            "pillow": PILLOW_AVAILABLE,
            "genai_lib": GENAI_LIB_AVAILABLE,
            "numpy": NUMPY_AVAILABLE,
        }

    def _configure_genai_client_if_needed(self) -> bool:
        if not self.dependencies["genai_lib"] or not genai:
            self.last_error = "Google Gen AI 库 (google-genai) 未加载。"
            return False
        api_key = self.config_manager.get("GeminiAPI", "api_key")
        try:
            if api_key:
                self.genai_client = genai.Client(api_key=api_key)
            else:
                self.genai_client = genai.Client()
            self.configured_model_name = self.config_manager.get(
                "GeminiAPI", "model_name", "gemini-1.5-flash-latest"
            )
            if self.configured_model_name.startswith("models/"):
                print(
                    f"Info: Model name starts with 'models/'. The new SDK might not require this prefix. Using '{self.configured_model_name}'."
                )
            return True
        except Exception as e:
            self.last_error = (
                f"配置 Google Gen AI SDK (google-genai) 客户端时发生错误: {e}"
            )
            self.genai_client = None
            self.configured_model_name = None
            return False

    def get_last_error(self) -> str | None:
        return self.last_error

    def _encode_pil_image_to_base64(
        self, pil_image: Image.Image, image_format="PNG"
    ) -> str:
        buffered = BytesIO()
        save_format = image_format.upper()
        if save_format not in ["PNG", "JPEG", "WEBP"]:
            save_format = "PNG"
        try:
            if save_format == "JPEG":
                if pil_image.mode == "RGBA" or pil_image.mode == "LA":
                    rgb_image = pil_image.convert("RGB")
                    rgb_image.save(buffered, format="JPEG", quality=90)
                else:
                    pil_image.save(buffered, format="JPEG", quality=90)
            else:
                pil_image.save(buffered, format=save_format)
        except Exception as e:
            print(
                f"Warning: Error saving image to buffer with format {save_format}: {e}. Falling back to PNG."
            )
            pil_image.save(buffered, format="PNG")
        img_byte = buffered.getvalue()
        return base64.b64encode(img_byte).decode("utf-8")

    def _adjust_block_bbox_for_text_fit(
        self,
        block: ProcessedBlock,
        pil_font_for_calc: ImageFont.FreeTypeFont | ImageFont.ImageFont | None,
    ):
        if not self.config_manager.getboolean(
            "UI", "auto_adjust_bbox_to_fit_text", fallback=True
        ):
            return
        if (
            not block.translated_text
            or not block.translated_text.strip()
            or not pil_font_for_calc
            or not PILLOW_AVAILABLE
        ):
            return
        text_padding = self.config_manager.getint("UI", "text_padding", 3)
        h_char_spacing_px = self.config_manager.getint(
            "UI", "h_text_char_spacing_px", 0
        )
        h_line_spacing_px = self.config_manager.getint(
            "UI", "h_text_line_spacing_px", 0
        )
        v_char_spacing_px = self.config_manager.getint(
            "UI", "v_text_char_spacing_px", 0
        )
        v_col_spacing_px = self.config_manager.getint(
            "UI", "v_text_column_spacing_px", 0
        )
        current_bbox_width = block.bbox[2] - block.bbox[0]
        current_bbox_height = block.bbox[3] - block.bbox[1]
        if current_bbox_width <= 0 or current_bbox_height <= 0:
            return
        max_content_width_for_wrapping = max(1, current_bbox_width - (2 * text_padding))
        max_content_height_for_wrapping = max(
            1, current_bbox_height - (2 * text_padding)
        )
        dummy_draw = None
        try:
            dummy_img = Image.new("RGBA", (1, 1))
            dummy_draw = ImageDraw.Draw(dummy_img)
        except Exception:
            if hasattr(pil_font_for_calc, "getlength"):

                class DummyDrawMock:
                    def textlength(self, text, font):
                        return font.getlength(text)

                dummy_draw = DummyDrawMock()
            else:
                return
        if not dummy_draw:
            return
        needed_content_width_unpadded, needed_content_height_unpadded = 0, 0
        if block.orientation == "horizontal":
            _, total_h, _, max_w_achieved = wrap_text_pil(
                dummy_draw,
                block.translated_text,
                pil_font_for_calc,
                int(max_content_width_for_wrapping),
                "horizontal",
                h_char_spacing_px,
                h_line_spacing_px,
            )
            needed_content_width_unpadded, needed_content_height_unpadded = (
                max_w_achieved,
                total_h,
            )
        else:
            _, total_w, _, max_h_achieved = wrap_text_pil(
                dummy_draw,
                block.translated_text,
                pil_font_for_calc,
                int(max_content_height_for_wrapping),
                "vertical",
                v_char_spacing_px,
                v_col_spacing_px,
            )
            needed_content_width_unpadded, needed_content_height_unpadded = (
                total_w,
                max_h_achieved,
            )
        if (
            needed_content_width_unpadded <= 0
            and needed_content_height_unpadded <= 0
            and block.translated_text
            and block.translated_text.strip()
        ):
            return
        required_bbox_width, required_bbox_height = needed_content_width_unpadded + (
            2 * text_padding
        ), needed_content_height_unpadded + (2 * text_padding)
        if required_bbox_width <= 0 or required_bbox_height <= 0:
            return
        center_x, center_y = (block.bbox[0] + block.bbox[2]) / 2.0, (
            block.bbox[1] + block.bbox[3]
        ) / 2.0
        min_dim_after_adjust = 10
        final_bbox_width, final_bbox_height = max(
            required_bbox_width, min_dim_after_adjust
        ), max(required_bbox_height, min_dim_after_adjust)
        block.bbox = [
            center_x - final_bbox_width / 2.0,
            center_y - final_bbox_height / 2.0,
            center_x + final_bbox_width / 2.0,
            center_y + final_bbox_height / 2.0,
        ]

    def process_image(
        self,
        image_path: str,
        progress_callback=None,
        cancellation_event: threading.Event = None,
    ) -> tuple[Image.Image, list[ProcessedBlock]] | None:
        self.last_error = None

        def _report_progress(percentage, message):
            if progress_callback:
                progress_callback(percentage, message)

        def _check_cancelled():
            if cancellation_event and cancellation_event.is_set():
                self.last_error = "处理已取消。"
                return True
            return False

        _report_progress(0, f"开始处理: {os.path.basename(image_path)}")
        if _check_cancelled():
            return None
        if not self.dependencies["pillow"]:
            self.last_error = "Pillow 库缺失，无法处理图片。"
            _report_progress(100, "错误: Pillow缺失")
            return None
        if not os.path.exists(image_path):
            self.last_error = f"图片文件不存在: {image_path}"
            _report_progress(100, "错误: 文件不存在")
            return None
        pil_image_original: Image.Image | None = None
        img_width, img_height = 0, 0
        try:
            pil_image_original = Image.open(image_path).convert("RGBA")
            img_width, img_height = pil_image_original.size
            _report_progress(5, "图片加载完成。")
        except Exception as e:
            self.last_error = f"使用 Pillow 加载图片失败: {e}"
            _report_progress(100, f"错误: {self.last_error}")
            return None
        if _check_cancelled():
            return None
        pil_image_for_llm = pil_image_original.copy()
        preprocess_enabled = self.config_manager.getboolean(
            "LLMImagePreprocessing", "enabled", fallback=False
        )
        if preprocess_enabled and PILLOW_AVAILABLE:
            _report_progress(6, "LLM图像预处理...")
            upscale_factor_conf = self.config_manager.getfloat(
                "LLMImagePreprocessing", "upscale_factor", fallback=1.0
            )
            contrast_factor_conf = self.config_manager.getfloat(
                "LLMImagePreprocessing", "contrast_factor", fallback=1.0
            )
            resample_method_str = self.config_manager.get(
                "LLMImagePreprocessing", "upscale_resample_method", "LANCZOS"
            ).upper()
            resample_filter = Image.Resampling.LANCZOS
            if resample_method_str == "NEAREST":
                resample_filter = Image.Resampling.NEAREST
            elif resample_method_str == "BILINEAR":
                resample_filter = Image.Resampling.BILINEAR
            elif resample_method_str == "BICUBIC":
                resample_filter = Image.Resampling.BICUBIC
            try:
                if upscale_factor_conf > 1.0 and upscale_factor_conf != 1.0:
                    original_llm_width, original_llm_height = pil_image_for_llm.size
                    new_llm_width, new_llm_height = int(
                        original_llm_width * upscale_factor_conf
                    ), int(original_llm_height * upscale_factor_conf)
                    pil_image_for_llm = pil_image_for_llm.resize(
                        (new_llm_width, new_llm_height), resample_filter
                    )
                    _report_progress(
                        7, f"LLM图像已放大 (至 {new_llm_width}x{new_llm_height})"
                    )
                if contrast_factor_conf != 1.0 and NUMPY_AVAILABLE:
                    img_array = np.array(pil_image_for_llm).astype(np.float32)
                    if img_array.ndim == 3 and img_array.shape[2] == 4:
                        rgb_channels, alpha_channel = (
                            img_array[:, :, :3],
                            img_array[:, :, 3],
                        )
                        rgb_channels = np.clip(
                            contrast_factor_conf * (rgb_channels - 128.0) + 128.0,
                            0,
                            255,
                        )
                        pil_image_for_llm = Image.fromarray(
                            np.dstack((rgb_channels, alpha_channel)).astype(np.uint8),
                            "RGBA",
                        )
                    elif img_array.ndim == 3 and img_array.shape[2] == 3:
                        img_array = np.clip(
                            contrast_factor_conf * (img_array - 128.0) + 128.0, 0, 255
                        )
                        pil_image_for_llm = Image.fromarray(
                            img_array.astype(np.uint8), "RGB"
                        )
                    elif img_array.ndim == 2:
                        img_array = np.clip(
                            contrast_factor_conf * (img_array - 128.0) + 128.0, 0, 255
                        )
                        pil_image_for_llm = Image.fromarray(
                            img_array.astype(np.uint8), "L"
                        )
                    _report_progress(
                        8, f"LLM图像对比度已调整 (系数: {contrast_factor_conf})"
                    )
                elif contrast_factor_conf != 1.0 and not NUMPY_AVAILABLE:
                    _report_progress(8, f"警告: Numpy未安装，跳过LLM图像对比度调整。")
            except Exception as e_preprocess:
                _report_progress(8, f"警告: LLM图像预处理失败: {e_preprocess}")
                pil_image_for_llm = pil_image_original.copy()
        intermediate_blocks_for_processing: list[dict] = []
        _report_progress(10, "使用 Gemini (google-genai SDK) 进行OCR和翻译...")
        if not self.dependencies["genai_lib"] or not genai or not google_genai_types:
            self.last_error = "Google Gen AI 库 (google-genai) 或其类型模块未正确加载。"
            _report_progress(100, f"错误: {self.last_error}")
            return None
        if (
            not self._configure_genai_client_if_needed()
            or not self.genai_client
            or not self.configured_model_name
        ):
            _report_progress(
                100,
                f"错误: {self.last_error or 'Google Gen AI Client 或模型名称配置失败。'}",
            )
            return None
        _report_progress(25, f"模型: {self.configured_model_name}...")
        raw_response_text = ""
        cleaned_json_text = ""
        try:
            target_language = self.config_manager.get(
                "GeminiAPI", "target_language", "Chinese"
            )
            source_language_from_config = self.config_manager.get(
                "GeminiAPI", "source_language", fallback="Japanese"
            ).strip()
            if not source_language_from_config:
                source_language_from_config = "Japanese"
            raw_glossary_text = self.config_manager.get(
                "GeminiAPI", "glossary_text", fallback=""
            ).strip()
            glossary_section_for_prompt = ""
            if raw_glossary_text:
                glossary_lines = [
                    line.strip()
                    for line in raw_glossary_text.splitlines()
                    if line.strip() and "->" in line.strip()
                ]
                if glossary_lines:
                    actual_glossary_content = "\n".join(glossary_lines)
                    glossary_section_for_prompt = f"""
IMPORTANT: When translating, strictly adhere to the following glossary (source_term->target_term format). Apply these translations wherever applicable:
<glossary>
{actual_glossary_content}
</glossary>
"""
            prompt_text_for_api = f"""You are an expert AI assistant specializing in image understanding, OCR (Optical Character Recognition), and translation. Your task is to meticulously analyze the provided image, identify {source_language_from_config} text blocks, extract their content, and translate them into {target_language}, adhering strictly to the output format.
Follow these steps precisely:
1.  **Image Type Analysis:**
    *   First, determine if the image is primarily:
        a.  A manga/comic page (characterized by panels, speech bubbles, stylized art).
        b.  A general image (e.g., photograph, document, illustration with informational text, poster, application screenshot).
2.  **{source_language_from_config} Text Block Identification and Extraction (Conditional on Image Type):**
    *   **For Manga/Comic Pages (1.a):**
        *   Prioritize {source_language_from_config} text within speech bubbles, dialogue balloons, and thought bubbles.
        *   Extract clearly legible {source_language_from_config} onomatopoeia (e.g., {"ドン, バン, ゴゴゴ" if source_language_from_config.lower() == 'japanese' else "SFX, SOUND_EFFECT"}) if visually prominent and part of the narrative.
        *   Extract {source_language_from_config} text from distinct narrative boxes.
        *   Extract significant, long {source_language_from_config} dialogue/narrative passages not in bubbles/boxes but clearly part of storytelling.
        *   Generally, ignore {source_language_from_config} text in complex backgrounds, tiny ancillary details, or decorative elements unless they are crucial narrative/onomatopoeia. Focus on text essential for story/dialogue.
    *   **For General Images (1.b):**
        *   Identify all distinct visual text blocks containing significant {source_language_from_config} text.
        *   Ignore very small, unclear, or isolated {source_language_from_config} text fragments that don't convey significant meaning.
3.  **For EACH identified {source_language_from_config} text block:**
    a.  **Original Text:** Extract the complete, exact {source_language_from_config} text.
    b.  **Orientation:** Determine its primary orientation: "horizontal", "vertical_ltr" (left-to-right), or "vertical_rtl" (right-to-left).
    c.  **Bounding Box (Critical):**
        *   Provide a **PRECISE and TIGHT** bounding box for the *{source_language_from_config} text characters themselves*.
        *   Format: `[y_min_norm, x_min_norm, y_max_norm, x_max_norm]`.
        *   Coordinates must be normalized **integers** between 0 and 1000 (e.g., 152, not 0.152).
        *   The box must be the smallest rectangle that **fully encloses all {source_language_from_config} text characters** of that block.
        *   Minimize surrounding whitespace, but ensure the box has a sensible, non-zero width and height appropriate for the text.
        *   **Crucially, DO NOT include non-text elements** like speech bubble outlines, tails, or large empty areas of a dialogue box, unless these are unavoidably intertwined with the text characters. Focus on the text's actual footprint.
        *   Ensure `x_min_norm < x_max_norm` and `y_min_norm < y_max_norm`. The box must have a non-zero area.
    d.  **Font Size Category:** Classify its visual size relative to the image and other text as: "very_small", "small", "medium", "large", or "very_large".
    e.  **Translation:** Translate the extracted {source_language_from_config} text into fluent and natural {target_language}. **Pay attention to the visual context (scene, character expressions) and dialogue flow/atmosphere to ensure the translation accurately reflects the original tone, mood, and nuance, maintaining translation accuracy.**
{glossary_section_for_prompt}
4.  **Output Format (Strictly JSON):**
    *   Return a JSON list of objects. Each object represents one processed text block.
    *   Each object MUST contain these exact keys: "original_text" (string), "translated_text" (string), "orientation" (string), "bounding_box" (list of 4 integers, representing y_min, x_min, y_max, x_max normalized to 0-1000), "font_size_category" (string).
    *   Example (if {source_language_from_config} is Japanese and target_language is English, for a manga image):
      ```json
      [
        {{
          "original_text": "何だ！？",
          "translated_text": "What is it!?",
          "orientation": "vertical_rtl",
          "bounding_box": [201, 152, 355, 250],
          "font_size_category": "medium"
        }},
        {{
          "original_text": "ドーン！",
          "translated_text": "BOOM!",
          "orientation": "horizontal",
          "bounding_box": [705, 600, 800, 780],
          "font_size_category": "large"
        }}
      ]
      ```
5.  **No Text Found:** If no qualifying {source_language_from_config} text blocks are found in the image, return an empty JSON list: `[]`.
6.  **JSON Purity:** The output MUST be *only* the raw JSON string. Do NOT include any explanatory text, comments, or markdown formatting (like ` ```json ... ``` `) outside of the JSON list itself.
"""
            if pil_image_for_llm is None:
                raise ValueError("PIL Image for LLM is None before API call.")
            if _check_cancelled():
                return None
            request_contents = [prompt_text_for_api, pil_image_for_llm]
            current_generation_config = None
            if google_genai_types:
                thinking_config_obj = google_genai_types.ThinkingConfig(
                    thinking_budget=21145
                )
                current_generation_config = google_genai_types.GenerateContentConfig(
                    temperature=0.5,
                    response_mime_type="application/json",
                    thinking_config=thinking_config_obj,
                )
            else:
                self.last_error = "Google Gen AI types 模块不可用，无法设置 thinking_config (内部错误)。"
                _report_progress(100, f"错误: {self.last_error}")
                return None
            response = self.genai_client.models.generate_content(
                model=self.configured_model_name,
                contents=request_contents,
                config=current_generation_config,
            )
            if hasattr(response, "text") and response.text:
                raw_response_text = response.text
            elif (
                hasattr(response, "candidates")
                and response.candidates
                and hasattr(response.candidates[0], "content")
                and response.candidates[0].content
                and hasattr(response.candidates[0].content, "parts")
                and response.candidates[0].content.parts
            ):
                raw_response_text = "".join(
                    part.text
                    for part in response.candidates[0].content.parts
                    if hasattr(part, "text")
                )
            else:
                feedback_msg = ""
                if hasattr(response, "prompt_feedback"):
                    feedback_msg = f" Prompt Feedback: {response.prompt_feedback}"
                self.last_error = (
                    f"Gemini API (google-genai) 未返回有效内容文本.{feedback_msg}"
                )
                _report_progress(75, f"错误: {self.last_error}")
                return None
            cleaned_json_text = raw_response_text.strip()
            if cleaned_json_text.startswith("```json"):
                cleaned_json_text = cleaned_json_text[7:]
                if cleaned_json_text.endswith("```"):
                    cleaned_json_text = cleaned_json_text[:-3]
            elif cleaned_json_text.startswith("```"):
                cleaned_json_text = cleaned_json_text[3:]
                if cleaned_json_text.endswith("```"):
                    cleaned_json_text = cleaned_json_text[:-3]
            cleaned_json_text = cleaned_json_text.strip()
            if not cleaned_json_text or cleaned_json_text == "[]":
                _report_progress(75, "Gemini 未检测到文本或返回空列表。")
            else:
                gemini_data_list = json.loads(cleaned_json_text)
                if isinstance(gemini_data_list, list):
                    for item_idx, item_data in enumerate(gemini_data_list):
                        if (
                            isinstance(item_data, dict)
                            and all(
                                k in item_data
                                for k in [
                                    "original_text",
                                    "translated_text",
                                    "orientation",
                                    "bounding_box",
                                    "font_size_category",
                                ]
                            )
                            and isinstance(item_data["bounding_box"], list)
                            and len(item_data["bounding_box"]) == 4
                            and item_data["orientation"]
                            in ["horizontal", "vertical_ltr", "vertical_rtl"]
                            and item_data["font_size_category"]
                            in self.font_size_mapping.keys()
                        ):
                            try:
                                gemini_bbox_values = [
                                    int(c) for c in item_data["bounding_box"]
                                ]
                                y_gem_min, x_gem_min, y_gem_max, x_gem_max = (
                                    gemini_bbox_values
                                )
                                internal_x_min_n = x_gem_min / 1000.0
                                internal_y_min_n = y_gem_min / 1000.0
                                internal_x_max_n = x_gem_max / 1000.0
                                internal_y_max_n = y_gem_max / 1000.0
                                internal_x_min_n = max(0.0, min(1.0, internal_x_min_n))
                                internal_y_min_n = max(0.0, min(1.0, internal_y_min_n))
                                internal_x_max_n = max(0.0, min(1.0, internal_x_max_n))
                                internal_y_max_n = max(0.0, min(1.0, internal_y_max_n))
                                final_x_min_n = min(internal_x_min_n, internal_x_max_n)
                                final_y_min_n = min(internal_y_min_n, internal_y_max_n)
                                final_x_max_n = max(internal_x_min_n, internal_x_max_n)
                                final_y_max_n = max(internal_y_min_n, internal_y_max_n)
                                normalized_bbox_for_internal_use = [
                                    final_x_min_n,
                                    final_y_min_n,
                                    final_x_max_n,
                                    final_y_max_n,
                                ]
                                intermediate_blocks_for_processing.append(
                                    {
                                        "id": f"gemini_multimodal_{item_idx}",
                                        "original_text": str(
                                            item_data["original_text"]
                                        ),
                                        "translated_text": str(
                                            item_data["translated_text"]
                                        ),
                                        "bbox_norm": normalized_bbox_for_internal_use,
                                        "orientation": str(item_data["orientation"]),
                                        "font_size_category": str(
                                            item_data["font_size_category"]
                                        ),
                                    }
                                )
                            except (ValueError, TypeError) as e:
                                _report_progress(
                                    75,
                                    f"警告: 解析Gemini某数据块时出错 (bbox): {e} - {item_data}",
                                )
                        else:
                            _report_progress(
                                75, f"警告: Gemini某数据块结构不符: {item_data}"
                            )
                    _report_progress(
                        75,
                        f"Gemini 解析到 {len(intermediate_blocks_for_processing)} 块。",
                    )
                else:
                    self.last_error = (
                        f"Gemini 返回非JSON列表: {cleaned_json_text[:200]}"
                    )
                    _report_progress(75, "错误: Gemini 返回格式不正确 (非列表)。")
        except json.JSONDecodeError as json_err:
            self.last_error = f"解析 Gemini JSON失败: {json_err}. 响应: {cleaned_json_text[:500] if cleaned_json_text else raw_response_text[:500]}"
            _report_progress(75, "错误: 解析Gemini JSON失败。")
        except Exception as gemini_err:
            self.last_error = (
                f"Gemini API (google-genai) 调用/处理时发生错误: {gemini_err}"
            )
            import traceback

            traceback.print_exc()
            _report_progress(75, f"错误: {self.last_error}")
        if _check_cancelled():
            return None
        _report_progress(
            85, f"转换 {len(intermediate_blocks_for_processing)} 个中间块..."
        )
        final_processed_blocks: list[ProcessedBlock] = []
        for iblock_data in intermediate_blocks_for_processing:
            pixel_bbox = []
            if "bbox_norm" in iblock_data:
                norm_bbox = iblock_data["bbox_norm"]
                if not (
                    isinstance(norm_bbox, list)
                    and len(norm_bbox) == 4
                    and all(isinstance(c, float) for c in norm_bbox)
                ):
                    print(
                        f"警告: 无效的内部 bbox_norm 格式: {norm_bbox} for block data: {iblock_data.get('original_text', '')[:20]}"
                    )
                    continue
                x_min_n, y_min_n, x_max_n, y_max_n = norm_bbox
                if img_width > 0 and img_height > 0:
                    pixel_bbox = [
                        x_min_n * img_width,
                        y_min_n * img_height,
                        x_max_n * img_width,
                        y_max_n * img_height,
                    ]
                else:
                    print("警告: 图像尺寸无效，无法转换归一化BBox。")
                    continue
            else:
                print(
                    f"警告: 中间数据块缺少 bbox_norm: {iblock_data.get('original_text', '')[:20]}"
                )
                continue
            if not (
                pixel_bbox
                and len(pixel_bbox) == 4
                and all(isinstance(c, (int, float)) for c in pixel_bbox)
            ):
                print(
                    f"警告: 无效的像素 BBox (类型或长度): {pixel_bbox} for block data: {iblock_data.get('original_text', '')[:20]}"
                )
                continue
            if not (pixel_bbox[2] > pixel_bbox[0] and pixel_bbox[3] > pixel_bbox[1]):
                print(
                    f"警告: 无效的像素 BBox (width/height non-positive): {pixel_bbox} for block data: {iblock_data.get('original_text', '')[:20]}"
                )
                continue
            font_size_cat = iblock_data.get("font_size_category", "medium")
            orientation = iblock_data.get("orientation", "horizontal")
            font_size_px = self.font_size_mapping.get(
                font_size_cat, self.font_size_mapping["medium"]
            )
            fixed_font_size_override = self.config_manager.getint(
                "UI", "fixed_font_size", 0
            )
            if fixed_font_size_override > 0:
                font_size_px = fixed_font_size_override
            current_block = ProcessedBlock(
                id=iblock_data.get("id"),
                original_text=iblock_data["original_text"],
                translated_text=iblock_data["translated_text"],
                bbox=pixel_bbox,
                orientation=orientation,
                font_size_category=font_size_cat,
                font_size_pixels=font_size_px,
                angle=0.0,
                text_align=iblock_data.get("text_align", None),
            )
            if (
                self.config_manager.getboolean(
                    "UI", "auto_adjust_bbox_to_fit_text", fallback=True
                )
                and PILLOW_AVAILABLE
            ):
                font_name_for_adjust = self.config_manager.get(
                    "UI", "font_name", "msyh.ttc"
                )
                pil_font_instance_for_adjust = get_pil_font(
                    font_name_for_adjust, current_block.font_size_pixels
                )
                if pil_font_instance_for_adjust:
                    self._adjust_block_bbox_for_text_fit(
                        current_block, pil_font_instance_for_adjust
                    )
            final_processed_blocks.append(current_block)
        if not final_processed_blocks and not self.last_error:
            self.last_error = "未在图像中检测到可处理的文本块。"
        _report_progress(100, "图像处理完成。")
        return pil_image_original, final_processed_blocks
