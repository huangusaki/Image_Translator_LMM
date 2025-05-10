import os
import time
import json
import sys
import threading
from config_manager import ConfigManager
from utils.font_utils import PILLOW_AVAILABLE, get_pil_font, get_font_line_height, wrap_text_pil
if PILLOW_AVAILABLE:
    from PIL import Image, ImageDraw, ImageFont
from services.ocr_providers import get_ocr_provider, OCRResult
from services.translation_providers import get_translation_provider, TranslationResult, GeminiTextTranslationProvider
try:
    import google.generativeai as genai
    import google.api_core.exceptions
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    google = None
class ProcessedBlock:
    def __init__(self, original_text: str, translated_text: str, bbox: list[int],
                 orientation: str = "horizontal",
                 font_size_category: str = "medium",
                 font_size_pixels: int = 22,
                 angle: float = 0.0,
                 id: str | int | None = None,
                 text_align: str | None = None                  
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
        return (f"ProcessedBlock(id='{self.id}', original='{self.original_text[:10]}...', translated='{self.translated_text[:10]}...', "
                f"bbox={self.bbox}, orientation='{self.orientation}', font_size_category='{self.font_size_category}', "
                f"font_px={self.font_size_pixels}, angle={self.angle}, text_align='{self.text_align}')")                       
class ImageProcessor:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.last_error = None
        self.dependencies = self._check_internal_dependencies()
        self.gemini_model = None
        self._apply_proxy_settings_to_env()
        if self.dependencies["gemini_lib"]:
            pass
        self.font_size_mapping = {
            "very_small": self.config_manager.getint('FontSizeMapping', 'very_small', 12),
            "small": self.config_manager.getint('FontSizeMapping', 'small', 16),
            "medium": self.config_manager.getint('FontSizeMapping', 'medium', 22),
            "large": self.config_manager.getint('FontSizeMapping', 'large', 28),
            "very_large": self.config_manager.getint('FontSizeMapping', 'very_large', 36),
        }
    def _apply_proxy_settings_to_env(self):
        if self.config_manager.getboolean('Proxy', 'enabled', fallback=False):
            proxy_host = self.config_manager.get('Proxy', 'host')
            proxy_port = self.config_manager.get('Proxy', 'port')
            if proxy_host and proxy_port:
                proxy_url = f"http://{proxy_host}:{proxy_port}"
                os.environ['HTTPS_PROXY'] = proxy_url
                os.environ['HTTP_PROXY'] = proxy_url
        else:
            current_https_proxy = os.environ.get('HTTPS_PROXY', '')
            current_http_proxy = os.environ.get('HTTP_PROXY', '')
            proxy_host_check = self.config_manager.get('Proxy', 'host', '')
            if 'HTTPS_PROXY' in os.environ and (current_https_proxy.startswith("http://127.0.0.1") or (proxy_host_check and proxy_host_check in current_https_proxy)):
                del os.environ['HTTPS_PROXY']
            if 'HTTP_PROXY' in os.environ and (current_http_proxy.startswith("http://127.0.0.1") or (proxy_host_check and proxy_host_check in current_http_proxy)):
                del os.environ['HTTP_PROXY']
    def _check_internal_dependencies(self):
        return {
            "pillow": PILLOW_AVAILABLE,
            "gemini_lib": GEMINI_AVAILABLE,
        }
    def _configure_gemini_if_needed(self) -> bool:
        if not self.dependencies["gemini_lib"]:
            self.last_error = "Gemini 库未加载。"
            return False
        api_key = self.config_manager.get('GeminiAPI', 'api_key')
        model_name = self.config_manager.get('GeminiAPI', 'model_name', 'gemini-1.5-flash-latest')
        if not api_key:
            return False
        try:
            genai.configure(api_key=api_key)
            expected_internal_model_name = f"models/{model_name}"
            if self.gemini_model is None or\
               (hasattr(self.gemini_model, 'model_name') and self.gemini_model.model_name != expected_internal_model_name):
                self.gemini_model = genai.GenerativeModel(model_name)
            return True
        except Exception as e:
            self.last_error = f"配置 Gemini API 或实例化模型时发生错误: {e}"
            self.gemini_model = None
            return False
    def get_last_error(self) -> str | None:
        return self.last_error
    def _adjust_block_bbox_for_text_fit(self, block: ProcessedBlock, pil_font_for_calc: ImageFont.FreeTypeFont | ImageFont.ImageFont | None):
        """
        Adjusts the block's bbox if the provided text, font size, and padding
        require more space than the current bbox provides.
        """
        if not self.config_manager.getboolean('UI', 'auto_adjust_bbox_to_fit_text', fallback=True):
            return
        if not block.translated_text or not block.translated_text.strip() or not pil_font_for_calc or not PILLOW_AVAILABLE:
            return
        text_padding = self.config_manager.getint('UI', 'text_padding', 3)
        h_char_spacing_px = self.config_manager.getint('UI', 'h_text_char_spacing_px', 0)
        h_line_spacing_px = self.config_manager.getint('UI', 'h_text_line_spacing_px', 0)
        v_char_spacing_px = self.config_manager.getint('UI', 'v_text_char_spacing_px', 0)
        v_col_spacing_px = self.config_manager.getint('UI', 'v_text_column_spacing_px', 0)
        current_bbox_width = block.bbox[2] - block.bbox[0]
        current_bbox_height = block.bbox[3] - block.bbox[1]
        if current_bbox_width <= 0 or current_bbox_height <= 0:
            return
        max_content_width_for_wrapping = current_bbox_width - (2 * text_padding)
        max_content_height_for_wrapping = current_bbox_height - (2 * text_padding)
        if max_content_width_for_wrapping <= 0 or max_content_height_for_wrapping <= 0:
             return
        dummy_draw = None
        try:
            dummy_img = Image.new('RGBA', (1,1))
            dummy_draw = ImageDraw.Draw(dummy_img)
        except Exception:
            if hasattr(pil_font_for_calc, 'getlength'):
                class DummyDrawMock:
                    def textlength(self, text, font):
                        return font.getlength(text)
                dummy_draw = DummyDrawMock()
            else:
                return
        if not dummy_draw:
            return
        needed_content_width_unpadded = 0
        needed_content_height_unpadded = 0
        if block.orientation == "horizontal":
            _, total_h, _, max_w_achieved = wrap_text_pil(
                dummy_draw, block.translated_text, pil_font_for_calc,
                max_dim=int(max_content_width_for_wrapping) if max_content_width_for_wrapping > 0 else 1,
                orientation="horizontal",
                char_spacing_px=h_char_spacing_px,
                line_or_col_spacing_px=h_line_spacing_px
            )
            needed_content_width_unpadded = max_w_achieved
            needed_content_height_unpadded = total_h
        else:
            _, total_w, _, max_h_achieved = wrap_text_pil(
                dummy_draw, block.translated_text, pil_font_for_calc,
                max_dim=int(max_content_height_for_wrapping) if max_content_height_for_wrapping > 0 else 1,
                orientation="vertical",
                char_spacing_px=v_char_spacing_px,
                line_or_col_spacing_px=v_col_spacing_px
            )
            needed_content_width_unpadded = total_w
            needed_content_height_unpadded = max_h_achieved
        if needed_content_width_unpadded <=0 and needed_content_height_unpadded <=0 and block.translated_text:
            return
        required_bbox_width = needed_content_width_unpadded + (2 * text_padding)
        required_bbox_height = needed_content_height_unpadded + (2 * text_padding)
        expand_w = required_bbox_width > current_bbox_width
        expand_h = required_bbox_height > current_bbox_height
        if expand_w or expand_h:
            center_x = (block.bbox[0] + block.bbox[2]) / 2.0
            center_y = (block.bbox[1] + block.bbox[3]) / 2.0
            final_bbox_width = max(current_bbox_width, required_bbox_width)
            final_bbox_height = max(current_bbox_height, required_bbox_height)
            min_dim_after_adjust = 10
            final_bbox_width = max(final_bbox_width, min_dim_after_adjust)
            final_bbox_height = max(final_bbox_height, min_dim_after_adjust)
            block.bbox = [
                center_x - final_bbox_width / 2.0,
                center_y - final_bbox_height / 2.0,
                center_x + final_bbox_width / 2.0,
                center_y + final_bbox_height / 2.0,
            ]
    def process_image(self, image_path: str, progress_callback=None, cancellation_event: threading.Event = None) -> tuple[Image.Image, list[ProcessedBlock]] | None:
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
        if _check_cancelled(): return None
        if not self.dependencies["pillow"]:
            self.last_error = "Pillow 库缺失，无法处理图片。"
            _report_progress(100, "错误: Pillow缺失"); return None
        if not os.path.exists(image_path):
            self.last_error = f"图片文件不存在: {image_path}"
            _report_progress(100, "错误: 文件不存在"); return None
        pil_image_original: Image.Image | None = None
        try:
            pil_image_original = Image.open(image_path).convert("RGBA")
            img_width, img_height = pil_image_original.size
            _report_progress(5, "图片加载完成。")
        except Exception as e:
            self.last_error = f"使用 Pillow 加载图片失败: {e}";
            _report_progress(100, f"错误: {self.last_error}"); return None
        if _check_cancelled(): return None
        ocr_main_provider_pref = self.config_manager.get('API', 'ocr_provider', 'gemini').lower()
        trans_main_provider_pref = self.config_manager.get('API', 'translation_provider', 'gemini').lower()
        ocr_results_for_translation: list[OCRResult] = []
        intermediate_blocks_for_processing: list[dict] = []
        gemini_multimodal_attempted = False
        gemini_multimodal_succeeded_with_blocks = False
        if ocr_main_provider_pref == 'gemini':
            gemini_multimodal_attempted = True
            _report_progress(10, "主要 OCR 为 Gemini，尝试 Gemini 多模态处理...")
            if self.dependencies["gemini_lib"]:
                if self._configure_gemini_if_needed() and self.gemini_model:
                    model_display_name = self.gemini_model.model_name if hasattr(self.gemini_model, 'model_name') else "未知 Gemini 模型"
                    _report_progress(20, f"使用 Gemini (模型: {model_display_name.split('/')[-1]}) 进行OCR和翻译...")
                    gemini_timeout = self.config_manager.getint('GeminiAPI', 'request_timeout', fallback=60)
                    try:
                        target_language = self.config_manager.get('GeminiAPI', 'target_language', 'Chinese')
                        raw_glossary_text = self.config_manager.get('LocalTranslationAPI', 'glossary_text', fallback='').strip()
                        glossary_instructions = ""
                        if raw_glossary_text:
                            glossary_lines = [line.strip() for line in raw_glossary_text.splitlines() if line.strip() and '->' in line.strip()]
                            if glossary_lines:
                                formatted_glossary = "\n".join(glossary_lines)
                                glossary_instructions = f"""
IMPORTANT: When translating, strictly adhere to the following glossary (source_term->target_term format). Apply these translations wherever applicable:
<glossary>
{formatted_glossary}
</glossary>
"""
                        else:
                            glossary_instructions = "\nNo specific glossary provided for this translation task.\n"
                        prompt = f"""You are an expert image analysis and translation AI. Your task is to process the provided image by following these steps:
1.  Identify all distinct visual text blocks or groupings (e.g., speech bubbles, info boxes, clear paragraphs or labels) in the image that contain significant Japanese text. Ignore very small, unclear, or isolated text.
2.  For each identified text block/grouping, extract the complete original Japanese text from within it.
3.  Determine the primary orientation of the Japanese text within each block/grouping. Possible values are: "horizontal", "vertical_ltr" (vertical, columns left-to-right), or "vertical_rtl" (vertical, columns right-to-left).
4.  For the *Japanese text content itself* within each block/grouping, provide an *extremely precise and tightly wrapping* normalized bounding box. The format is [x_min_norm, y_min_norm, x_max_norm, y_max_norm]. These coordinates must be decimal numbers between 0.0 and 1.0, representing proportions of the image's total width and height, and should have 3 to 4 decimal places. This bounding box must be the smallest possible rectangle that fully encloses all Japanese text characters within that block/grouping, minimizing any whitespace or padding between the box edges and the outermost text characters. Ensure x_min_norm < x_max_norm and y_min_norm < y_max_norm. Focus on the actual extent of the text characters, not the overall container (like speech bubble tails or large empty backgrounds).
5.  Based on the visual relative size of the Japanese text within the image, determine its font size category. Choose the most appropriate category from: "very_small", "small", "medium", "large", "very_large". Evaluation should be based on the text block's size relative to the overall image dimensions, the area occupied by its bounding box, and its visual prominence compared to other text blocks (if any). For example, large headlines or important emphasized text would typically be "large" or "very_large", while annotations in corners or inconspicuous small dialogues might be "small" or "very_small".
6.  Translate the Japanese text from each block/grouping into fluent, natural, and semantically complete {target_language}. Ensure consistent terminology for nouns.
{glossary_instructions} 
7.  Return your results strictly in the following JSON format: a JSON list of objects. Each object represents one text block/grouping and its content, and must include these five keys:
    - "original_text": string, the identified Japanese text from the block/grouping.
    - "translated_text": string, the translated {target_language} text.
    - "orientation": string, "horizontal", "vertical_ltr", or "vertical_rtl".
    - "bounding_box": list of four floats [x_min_norm, y_min_norm, x_max_norm, y_max_norm], representing the extremely precise, tightly wrapped normalized coordinates (must have 3-4 decimal places) of the *Japanese text characters themselves, not the larger visual container*.
    - "font_size_category": string, the font size category chosen from ["very_small", "small", "medium", "large", "very_large"].
    Example (if target_language is English):
    [
      {{"original_text": "タイトル", "translated_text": "Title", "orientation": "horizontal", "bounding_box": [0.1023, 0.051, 0.450, 0.1505], "font_size_category": "large"}},
      {{"original_text": "今日の天気は？", "translated_text": "How's the weather today?", "orientation": "vertical_rtl", "bounding_box": [0.600, 0.7051, 0.680, 0.850], "font_size_category": "medium"}},
      {{"original_text": "※注釈", "translated_text": "※Annotation", "orientation": "horizontal", "bounding_box": [0.880, 0.920, 0.9803, 0.950], "font_size_category": "small"}}
    ]
8.  If no qualifying text blocks/groupings are detected in the image, or if reliable identification and translation are not possible, return an empty list `[]`.
9.  Ensure your output is a pure, correctly formatted JSON string, without any ```json ... ``` markers or other explanatory text.
"""
                        safety_settings_req = [
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                        ]
                        if _check_cancelled(): return None
                        response = self.gemini_model.generate_content(
                            [prompt, pil_image_original],
                            safety_settings=safety_settings_req,
                            request_options={"timeout": gemini_timeout}
                        )
                        _report_progress(35, "Gemini API (multimodal) 调用完成，解析响应...")
                        raw_response_text = response.text.strip()
                        cleaned_json_text = raw_response_text
                        if cleaned_json_text.startswith("```json"): cleaned_json_text = cleaned_json_text[7:]
                        elif cleaned_json_text.startswith("```"): cleaned_json_text = cleaned_json_text[3:]
                        if cleaned_json_text.endswith("```"): cleaned_json_text = cleaned_json_text[:-3]
                        cleaned_json_text = cleaned_json_text.strip()
                        if not cleaned_json_text or cleaned_json_text == "[]":
                            _report_progress(40, "Gemini 未检测到文本或返回空列表。")
                        else:
                            gemini_data_list = json.loads(cleaned_json_text)
                            if isinstance(gemini_data_list, list):
                                for item_idx, item_data in enumerate(gemini_data_list):
                                    if isinstance(item_data, dict) and\
                                       all(k in item_data for k in ['original_text', 'translated_text', 'orientation', 'bounding_box', 'font_size_category']) and\
                                       isinstance(item_data['bounding_box'], list) and len(item_data['bounding_box']) == 4 and\
                                       item_data['orientation'] in ["horizontal", "vertical_ltr", "vertical_rtl"] and\
                                       item_data['font_size_category'] in self.font_size_mapping.keys():
                                        try:
                                            intermediate_blocks_for_processing.append({
                                                "id": f"gemini_multimodal_{item_idx}",
                                                "original_text": str(item_data['original_text']),
                                                "translated_text": str(item_data['translated_text']),
                                                "bbox_norm": [float(c) for c in item_data['bounding_box']],
                                                "orientation": str(item_data['orientation']),
                                                "font_size_category": str(item_data['font_size_category'])
                                            })
                                        except (ValueError, TypeError):
                                            pass
                                if intermediate_blocks_for_processing:
                                    gemini_multimodal_succeeded_with_blocks = True
                                _report_progress(40, f"Gemini 解析到 {len(intermediate_blocks_for_processing)} 块。")
                            else:
                                self.last_error = f"Gemini 返回的不是预期的 JSON 列表。响应: {cleaned_json_text[:200]}"
                    except json.JSONDecodeError as json_err:
                        self.last_error = f"解析 Gemini 返回的 JSON 失败: {json_err}. 响应: {cleaned_json_text[:200] if 'cleaned_json_text' in locals() else 'N/A'}"
                    except AttributeError as attr_err:
                        feedback_info = ""
                        if 'response' in locals() and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                             feedback_info = f" Reason: {response.prompt_feedback.block_reason.name if response.prompt_feedback.block_reason else 'Unknown'}"
                        self.last_error = f"无法从 Gemini 响应获取文本 (可能被安全过滤器阻止): {attr_err}.{feedback_info}"
                    except google.api_core.exceptions.DeadlineExceeded as timeout_error:
                        self.last_error = f"Gemini API 请求超时 (超过 {gemini_timeout} 秒): {timeout_error}"
                    except google.api_core.exceptions.GoogleAPIError as api_error:
                        self.last_error = f"Gemini API 调用失败 (GoogleAPIError): {api_error}"
                    except Exception as gemini_err:
                        self.last_error = f"调用 Gemini API 时发生未知错误: {gemini_err}"
                else:
                    _report_progress(15, f"Gemini (主要OCR) 配置失败。")
                    if not self.last_error: self.last_error = "Gemini (主要OCR) 配置失败。"
            else:
                 _report_progress(15, "Gemini 库不可用 (主要OCR)。")
                 self.last_error = "Gemini 库不可用 (主要OCR)。"
        if _check_cancelled(): return None
        run_fallback_ocr = False                              
        if ocr_main_provider_pref != 'gemini':
            _report_progress(45, f"主要 OCR 提供者 ('{ocr_main_provider_pref}') 不是 Gemini。准备执行配置的 OCR...")
            run_fallback_ocr = True
        if run_fallback_ocr:
            _report_progress(45, "执行回退 OCR 流程...")
            if gemini_multimodal_attempted:
                self.last_error = None
            fallback_ocr_provider_name = self.config_manager.get('API', 'fallback_ocr_provider', 'local api (paddleocr)')
            ocr_provider_instance = get_ocr_provider(self.config_manager, fallback_ocr_provider_name)
            if ocr_provider_instance:
                _report_progress(50, f"使用备用 OCR: {fallback_ocr_provider_name}...")
                if _check_cancelled(): return None
                ocr_results_temp = ocr_provider_instance.recognize_text(pil_image_original)
                if ocr_results_temp is not None:
                    ocr_results_for_translation = ocr_results_temp
                else:
                    ocr_error = ocr_provider_instance.get_last_error()
                    self.last_error = f"备用 OCR ({fallback_ocr_provider_name}) 失败: {ocr_error if ocr_error else '未知错误'}"
                _report_progress(60, f"备用 OCR 完成，获得 {len(ocr_results_for_translation)} 结果。")
            else:
                self.last_error = f"无法加载备用 OCR Provider: {fallback_ocr_provider_name}"
                _report_progress(60, f"错误: 无法加载备用 OCR {fallback_ocr_provider_name}")
        if _check_cancelled(): return None
        needs_separate_translation_step = False
        if not intermediate_blocks_for_processing and ocr_results_for_translation:
            needs_separate_translation_step = True
        elif not ocr_results_for_translation and not intermediate_blocks_for_processing:
            if not self.last_error:
                self.last_error = "在OCR阶段未能检测到任何文本。"
        if needs_separate_translation_step:
            _report_progress(65, "准备翻译 OCR 结果...")
            texts_to_translate = [ocr_res.text for ocr_res in ocr_results_for_translation]
            gemini_model_for_text_trans = None
            if 'gemini' in trans_main_provider_pref.lower():
                if self._configure_gemini_if_needed() and self.gemini_model:
                    gemini_model_for_text_trans = self.gemini_model
                else:
                    if not self.last_error: self.last_error = "无法配置Gemini进行文本翻译"
            translation_provider_instance = get_translation_provider(
                self.config_manager,
                trans_main_provider_pref,
                gemini_model_instance_for_text_translation=gemini_model_for_text_trans
            )
            actual_translation_provider_name_for_log = trans_main_provider_pref
            if not translation_provider_instance:
                _report_progress(68, f"主要翻译Provider '{trans_main_provider_pref}' 加载失败，尝试回退翻译。")
                fallback_trans_provider_name = self.config_manager.get('API', 'fallback_translation_provider', '本地 llm api (sakura)')
                actual_translation_provider_name_for_log = fallback_trans_provider_name
                if 'gemini' in fallback_trans_provider_name.lower() and not gemini_model_for_text_trans:
                     if self._configure_gemini_if_needed() and self.gemini_model:
                        gemini_model_for_text_trans = self.gemini_model
                translation_provider_instance = get_translation_provider(
                    self.config_manager,
                    fallback_trans_provider_name,
                    gemini_model_instance_for_text_translation=gemini_model_for_text_trans
                )
            if translation_provider_instance:
                if isinstance(translation_provider_instance, GeminiTextTranslationProvider) and gemini_model_for_text_trans:
                     actual_translation_provider_name_for_log = f"Gemini 文本翻译 ({gemini_model_for_text_trans.model_name.split('/')[-1] if hasattr(gemini_model_for_text_trans, 'model_name') else '未知'})"
                _report_progress(70, f"使用翻译服务: {actual_translation_provider_name_for_log}...")
                target_lang_for_trans_step = self.config_manager.get('GeminiAPI', 'target_language', 'Chinese')
                if _check_cancelled(): return None
                translated_results_list: list[TranslationResult] | None = translation_provider_instance.translate_batch(
                    texts_to_translate, target_language=target_lang_for_trans_step, source_language="Japanese", cancellation_event=cancellation_event)
                if translated_results_list and len(translated_results_list) == len(ocr_results_for_translation):
                    for i, ocr_block in enumerate(ocr_results_for_translation):
                        intermediate_blocks_for_processing.append({
                            "id": f"ocr_trans_{i}",
                            "original_text": ocr_block.text,
                            "translated_text": translated_results_list[i].translated_text,
                            "bbox_pixels": ocr_block.bbox,
                            "orientation": "horizontal",
                            "font_size_category": "medium"
                        })
                elif translated_results_list is None:
                    trans_error = translation_provider_instance.get_last_error()
                    self.last_error = f"翻译服务 ({actual_translation_provider_name_for_log}) 失败: {trans_error if trans_error else '未知错误'}"
                else:
                    self.last_error = "翻译结果数量与 OCR 结果不匹配或为空。"
                _report_progress(80, f"翻译完成，获得 {len(intermediate_blocks_for_processing)} 块。")
            else:
                self.last_error = f"无法加载任何翻译Provider (尝试了 '{trans_main_provider_pref}' 和回退)."
                _report_progress(80, f"错误: 无法加载翻译服务。")
        if _check_cancelled(): return None
        _report_progress(85, f"转换 {len(intermediate_blocks_for_processing)} 个中间块...")
        final_processed_blocks: list[ProcessedBlock] = []
        for iblock_data in intermediate_blocks_for_processing:
            pixel_bbox = []
            if "bbox_pixels" in iblock_data:
                pixel_bbox = iblock_data["bbox_pixels"]
            elif "bbox_norm" in iblock_data:
                norm_bbox = iblock_data["bbox_norm"]
                x_min_n = max(0.0, min(1.0, norm_bbox[0]))
                y_min_n = max(0.0, min(1.0, norm_bbox[1]))
                x_max_n = max(0.0, min(1.0, norm_bbox[2]))
                y_max_n = max(0.0, min(1.0, norm_bbox[3]))
                if not (x_min_n < x_max_n and y_min_n < y_max_n):
                    continue
                pixel_bbox = [
                    int(x_min_n * img_width), int(y_min_n * img_height),
                    int(x_max_n * img_width), int(y_max_n * img_height)
                ]
            else:
                continue
            if not (pixel_bbox and len(pixel_bbox) == 4 and pixel_bbox[0] < pixel_bbox[2] and pixel_bbox[1] < pixel_bbox[3]):
                continue
            font_size_cat = iblock_data.get('font_size_category', "medium")
            orientation = iblock_data.get('orientation', "horizontal")
            font_size_px = self.font_size_mapping.get(font_size_cat, self.font_size_mapping["medium"])
            fixed_font_size_override = self.config_manager.getint('UI', 'fixed_font_size', 0)
            if fixed_font_size_override > 0:
                font_size_px = fixed_font_size_override
            current_block = ProcessedBlock(
                id=iblock_data.get("id"),
                original_text=iblock_data['original_text'],
                translated_text=iblock_data['translated_text'],
                bbox=pixel_bbox,
                orientation=orientation,
                font_size_category=font_size_cat,
                font_size_pixels=font_size_px,
                angle=0.0,
                text_align=iblock_data.get("text_align", None)
            )
            if self.config_manager.getboolean('UI', 'auto_adjust_bbox_to_fit_text', fallback=True) and PILLOW_AVAILABLE:
                font_name_for_adjust = self.config_manager.get('UI', 'font_name', 'msyh.ttc')
                pil_font_instance_for_adjust = get_pil_font(font_name_for_adjust, current_block.font_size_pixels)
                if pil_font_instance_for_adjust:
                    self._adjust_block_bbox_for_text_fit(current_block, pil_font_instance_for_adjust)
            final_processed_blocks.append(current_block)
        if not final_processed_blocks and not self.last_error:
             self.last_error = "未在图像中检测到可处理的文本块 (最终检查)。"
        _report_progress(100, "信息提取完成。")
        return pil_image_original, final_processed_blocks
    def _find_font(self, font_name_or_path: str) -> str | None:
        if os.path.isabs(font_name_or_path) and os.path.exists(font_name_or_path):
            return font_name_or_path
        system_font_paths = []
        if sys.platform == "win32":
            system_font_paths.append(os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"))
        elif sys.platform == "linux":
            system_font_paths.extend(["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")])
        elif sys.platform == "darwin":
            system_font_paths.extend(["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")])
        if not any(font_name_or_path.lower().endswith(ext) for ext in [".ttf", ".otf", ".ttc"]):
            for ext in [".ttf", ".otf", ".ttc"]:
                font_file_to_try = font_name_or_path + ext
                for base_path in system_font_paths:
                    if os.path.isdir(base_path):
                        potential_path = os.path.join(base_path, font_file_to_try)
                        if os.path.exists(potential_path): return potential_path
        else:
            for base_path in system_font_paths:
                if os.path.isdir(base_path):
                    potential_path = os.path.join(base_path, font_name_or_path)
                    if os.path.exists(potential_path): return potential_path
        if not font_name_or_path.lower().endswith(".ttc"):
            font_file_to_try_ttc = font_name_or_path + ".ttc"
            for base_path in system_font_paths:
                if os.path.isdir(base_path):
                    potential_path = os.path.join(base_path, font_file_to_try_ttc)
                    if os.path.exists(potential_path): return potential_path
        return None
