# --- START OF FILE ocr_providers.py ---
import os
import time
import json
from abc import ABC, abstractmethod

# --- Dependency availability checks FIRST ---
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    PaddleOCR = None # Explicitly set to None if not available
    print("警告：无法导入 paddleocr。本地 PaddleOCR 功能将不可用。")

try:
    from google.cloud import vision
    # import google.auth # Usually handled by library or env vars
    GOOGLE_VISION_AVAILABLE = True
except ImportError:
    GOOGLE_VISION_AVAILABLE = False
    vision = None
    # google = None # google.api_core.exceptions might be needed by image_processor, so don't nullify 'google' itself if only vision fails
    print("警告: 未安装 google-cloud-vision。Google Cloud Vision OCR 功能将不可用。")

from utils.utils import process_ocr_results_merge_lines, PILLOW_AVAILABLE
if PILLOW_AVAILABLE:
    from PIL import Image
# Ensure PaddleOCR is imported if available for type hinting (already handled by try-except)
# Ensure vision is imported if available for type hinting (already handled by try-except)


class OCRResult:
    def __init__(self, text: str, bbox: list[int], original_data=None):
        self.text = text
        self.bbox = bbox # [x_min, y_min, x_max, y_max]
        self.original_data = original_data # e.g., raw vertices from OCR

    def __repr__(self):
        return f"OCRResult(text='{self.text[:20]}...', bbox={self.bbox})"

class OCRProvider(ABC):
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.last_error = None

    @abstractmethod
    def recognize_text(self, image_path_or_pil_image) -> list[OCRResult] | None:
        pass

    def get_last_error(self) -> str | None:
        return self.last_error

class PaddleOCRProvider(OCRProvider):
    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.paddle_ocr_instance = None
        self.lang = self.config_manager.get('LocalOcrAPI', 'paddle_lang', 'japan')
        print(f"*** [PaddleOCRProvider CONSTRUCTOR CALLED] Lang: {self.lang}, PADDLEOCR_AVAILABLE: {PADDLEOCR_AVAILABLE} ***")

    def _get_instance(self):
        print(f"*** [PaddleOCRProvider._get_instance ENTERED] Current instance: {'Exists' if self.paddle_ocr_instance else 'None'} ***")
        if not PADDLEOCR_AVAILABLE: # This check now uses the correctly defined variable
            self.last_error = "PaddleOCR 库未安装。"
            print("*** [PaddleOCRProvider._get_instance] PaddleOCR_AVAILABLE is False. Returning None. ***")
            return None
        if self.paddle_ocr_instance is None:
            print(f"*** [PaddleOCRProvider._get_instance] Attempting to initialize PaddleOCR (lang: {self.lang})... ***")
            try:
                self.paddle_ocr_instance = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=True, use_gpu=False)
                print(f"*** [PaddleOCRProvider._get_instance] PaddleOCR ({self.lang}) initialized successfully. ***")
            except Exception as e:
                self.last_error = f"PaddleOCR 初始化失败: {e}"
                print(f"*** [PaddleOCRProvider._get_instance] ERROR: PaddleOCR initialization failed: {e} ***")
                import traceback; traceback.print_exc()
                return None
        return self.paddle_ocr_instance

    def recognize_text(self, image_path_or_pil_image) -> list[OCRResult] | None:
        self.last_error = None
        print(f"*** [PaddleOCRProvider.recognize_text CALLED] Input type: {type(image_path_or_pil_image)} ***")
        ocr_engine = self._get_instance()
        if not ocr_engine:
            print("*** [PaddleOCRProvider.recognize_text] OCR engine instance is None. Returning None. ***")
            return None

        input_data = image_path_or_pil_image
        if PILLOW_AVAILABLE and isinstance(image_path_or_pil_image, Image.Image):
            import numpy as np
            input_data = np.array(image_path_or_pil_image.convert('RGB'))
            print("*** [PaddleOCRProvider.recognize_text] Input is PIL Image, converted to numpy array. ***")
        elif isinstance(image_path_or_pil_image, str):
             print(f"*** [PaddleOCRProvider.recognize_text] Input is image path: {image_path_or_pil_image} ***")
        else:
            print(f"*** [PaddleOCRProvider.recognize_text] Input is of unknown type: {type(image_path_or_pil_image)} ***")

        try:
            print(f"*** [PaddleOCRProvider.recognize_text] Calling ocr_engine.ocr()... ***")
            start_time = time.time()
            ocr_output_raw_outer_list = ocr_engine.ocr(input_data, cls=True)
            end_time = time.time()
            print(f"*** [PaddleOCRProvider.recognize_text] ocr_engine.ocr() call duration: {end_time - start_time:.2f}s ***")
            print(f"*** [PaddleOCRProvider.recognize_text] Raw PaddleOCR output (ocr_output_raw_outer_list): {ocr_output_raw_outer_list} ***")

            actual_raw_results = []
            if ocr_output_raw_outer_list and isinstance(ocr_output_raw_outer_list, list) and len(ocr_output_raw_outer_list) > 0:
                if ocr_output_raw_outer_list[0] is not None:
                    actual_raw_results = ocr_output_raw_outer_list[0]
            
            if not actual_raw_results:
                print("*** [PaddleOCRProvider.recognize_text] No actual_raw_results from PaddleOCR. Returning []. ***")
                return []

            print(f"*** [PaddleOCRProvider.recognize_text] Data for process_ocr_results_merge_lines: {actual_raw_results} ***")
            merged_paddle_results = process_ocr_results_merge_lines(actual_raw_results, lang_hint=self.lang)
            print(f"*** [PaddleOCRProvider.recognize_text] Merged results: {merged_paddle_results} ***")

            results = []
            for merged_text, first_vertices in merged_paddle_results:
                 if first_vertices and len(first_vertices) == 4: 
                     x_coords = [v[0] for v in first_vertices]; y_coords = [v[1] for v in first_vertices]
                     bbox = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
                     if bbox[0] < bbox[2] and bbox[1] < bbox[3]:
                        results.append(OCRResult(text=merged_text, bbox=bbox, original_data=first_vertices))
                     else:
                        print(f"    [PaddleOCRProvider.recognize_text] Invalid bbox generated for '{merged_text[:20]}...': {bbox}")
                 else:
                     print(f"    [PaddleOCRProvider.recognize_text] Invalid vertices for merged_text '{merged_text[:20]}...': {first_vertices}")
            print(f"*** [PaddleOCRProvider.recognize_text] Final OCRResult objects count: {len(results)} ***")
            return results
        except Exception as e:
            self.last_error = f"本地 PaddleOCR 失败: {e}"
            print(f"*** [PaddleOCRProvider.recognize_text] EXCEPTION: {e} ***")
            import traceback; traceback.print_exc()
            return None

class GoogleVisionOCRProvider(OCRProvider):
    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.client = None
        print(f"*** [GoogleVisionOCRProvider CONSTRUCTOR CALLED] GOOGLE_VISION_AVAILABLE: {GOOGLE_VISION_AVAILABLE} ***")

    def _get_client(self):
        print(f"*** [GoogleVisionOCRProvider._get_client ENTERED] Current client: {'Exists' if self.client else 'None'} ***")
        if not GOOGLE_VISION_AVAILABLE: # This check now uses the correctly defined variable
            self.last_error = "Google Cloud Vision 库或 google-auth 库未安装。"
            print("*** [GoogleVisionOCRProvider._get_client] GOOGLE_VISION_AVAILABLE is False. Returning None. ***")
            return None
        if self.client:
            return self.client

        key_path = self.config_manager.get('GoogleAPI', 'service_account_json')
        if not key_path or not os.path.exists(key_path):
            self.last_error = "未配置或找不到有效的 Google 服务账号 JSON 文件路径。"
            print(f"*** [GoogleVisionOCRProvider._get_client] Google service account JSON path invalid or missing: {key_path} ***")
            return None
        try:
            print(f"*** [GoogleVisionOCRProvider._get_client] Setting GOOGLE_APPLICATION_CREDENTIALS to: {key_path} ***")
            # It's generally better to pass credentials directly to the client if possible,
            # or ensure this environment variable is set *before* the library tries to use it.
            # For now, this follows the previous pattern.
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = key_path
            self.client = vision.ImageAnnotatorClient()
            print("*** [GoogleVisionOCRProvider._get_client] Google Vision client initialized successfully. ***")
            return self.client
        except Exception as e:
            self.last_error = f"初始化 Google Vision 客户端失败: {e}"
            print(f"*** [GoogleVisionOCRProvider._get_client] ERROR: Google Vision client initialization failed: {e} ***")
            import traceback; traceback.print_exc()
            self.client = None
            return None

    def recognize_text(self, image_path_or_pil_image) -> list[OCRResult] | None:
        self.last_error = None
        print(f"*** [GoogleVisionOCRProvider.recognize_text CALLED] Input type: {type(image_path_or_pil_image)} ***")
        client = self._get_client()
        if not client:
            print("*** [GoogleVisionOCRProvider.recognize_text] Client instance is None. Returning None. ***")
            return None

        try:
            print(f"*** [GoogleVisionOCRProvider.recognize_text] Using Google Cloud Vision OCR... ***")
            if isinstance(image_path_or_pil_image, str):
                print(f"    [GoogleVisionOCRProvider.recognize_text] Input is image path: {image_path_or_pil_image}")
                with open(image_path_or_pil_image, 'rb') as image_file:
                    content = image_file.read()
            elif PILLOW_AVAILABLE and isinstance(image_path_or_pil_image, Image.Image):
                import io
                print("    [GoogleVisionOCRProvider.recognize_text] Input is PIL Image, converting to bytes.")
                img_byte_arr = io.BytesIO()
                image_path_or_pil_image.save(img_byte_arr, format='PNG')
                content = img_byte_arr.getvalue()
            else:
                self.last_error = "Google Vision OCR: 无效的图像输入类型。"
                print(f"    [GoogleVisionOCRProvider.recognize_text] ERROR: Invalid image input type: {type(image_path_or_pil_image)}")
                return None

            image = vision.Image(content=content)
            start_time = time.time()
            print(f"*** [GoogleVisionOCRProvider.recognize_text] Calling client.text_detection()... ***")
            response = client.text_detection(image=image, image_context={"language_hints": ["ja"]})
            end_time = time.time()
            print(f"*** [GoogleVisionOCRProvider.recognize_text] client.text_detection() call duration: {end_time - start_time:.2f}s ***")

            if response.error.message:
                self.last_error = f"Google OCR API 错误: {response.error.message}"
                print(f"*** [GoogleVisionOCRProvider.recognize_text] ERROR: Google OCR API error: {response.error.message} ***")
                return None

            texts_annotations = response.text_annotations
            print(f"*** [GoogleVisionOCRProvider.recognize_text] Raw Google Vision output (text_annotations count): {len(texts_annotations)} ***")

            results = []
            # ... (rest of Google Vision result processing as before) ...
            if texts_annotations and len(texts_annotations) > 1: 
                google_raw_output_for_merging = []
                for text_ann in texts_annotations[1:]: 
                    vertices_raw = [(v.x, v.y) for v in text_ann.bounding_poly.vertices]
                    vertices_parsed = [(int(v[0]), int(v[1])) for v in vertices_raw]
                    if len(vertices_parsed) == 4: 
                         google_raw_output_for_merging.append([vertices_parsed, [text_ann.description]])
                print(f"    [GoogleVisionOCRProvider.recognize_text] Data passed to process_ocr_results_merge_lines (google_raw_output_for_merging count): {len(google_raw_output_for_merging)}")
                merged_google_results = process_ocr_results_merge_lines(google_raw_output_for_merging, lang_hint='ja') 
                print(f"    [GoogleVisionOCRProvider.recognize_text] Merged Google Vision results (merged_google_results):\n{merged_google_results}")
                for merged_text, first_vertices in merged_google_results:
                    if first_vertices and len(first_vertices) == 4:
                        x_coords = [v[0] for v in first_vertices]; y_coords = [v[1] for v in first_vertices]
                        bbox = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
                        if bbox[0] < bbox[2] and bbox[1] < bbox[3]:
                            results.append(OCRResult(text=merged_text, bbox=bbox, original_data=first_vertices))
            print(f"*** [GoogleVisionOCRProvider.recognize_text] Final OCRResult objects count: {len(results)} ***")
            return results
        except Exception as e:
            self.last_error = f"Google Cloud Vision OCR 失败: {e}"
            print(f"*** [GoogleVisionOCRProvider.recognize_text] EXCEPTION: {e} ***")
            import traceback; traceback.print_exc()
            return None

def get_ocr_provider(config_manager, provider_name: str) -> OCRProvider | None:
    provider_name_lower = provider_name.lower()
    print(f"*** [get_ocr_provider CALLED] Requested provider: '{provider_name_lower}' ***")
    if "paddle" in provider_name_lower:
        print(f"*** [get_ocr_provider] Matched 'paddle'. PADDLEOCR_AVAILABLE: {PADDLEOCR_AVAILABLE}. Attempting to return PaddleOCRProvider. ***")
        if not PADDLEOCR_AVAILABLE:
            print(f"*** [get_ocr_provider] PaddleOCR not available, cannot return provider. ***")
            return None
        return PaddleOCRProvider(config_manager)
    elif "google" in provider_name_lower:
        print(f"*** [get_ocr_provider] Matched 'google'. GOOGLE_VISION_AVAILABLE: {GOOGLE_VISION_AVAILABLE}. Attempting to return GoogleVisionOCRProvider. ***")
        if not GOOGLE_VISION_AVAILABLE:
            print(f"*** [get_ocr_provider] Google Vision not available, cannot return provider. ***")
            return None
        return GoogleVisionOCRProvider(config_manager)
    else:
        print(f"*** [get_ocr_provider] Unknown OCR Provider name: {provider_name}. Returning None. ***")
        return None
# --- END OF FILE ocr_providers.py ---