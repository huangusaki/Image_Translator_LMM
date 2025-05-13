import time
import requests
import threading
from abc import ABC, abstractmethod

try:
    import google.generativeai as genai
    import google.api_core.exceptions

    GEMINI_LIB_FOR_TRANSLATION_AVAILABLE = True
except ImportError:
    GEMINI_LIB_FOR_TRANSLATION_AVAILABLE = False
    genai = None
    google = None


class TranslationResult:
    def __init__(
        self,
        original_text: str,
        translated_text: str,
        source_lang: str | None = None,
        target_lang: str | None = None,
    ):
        self.original_text = original_text
        self.translated_text = translated_text
        self.source_lang = source_lang
        self.target_lang = target_lang

    def __repr__(self):
        return f"TranslationResult(original='{self.original_text[:20]}...', translated='{self.translated_text[:20]}...')"


class TranslationProvider(ABC):
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.last_error = None

    @abstractmethod
    def translate_batch(
        self,
        texts: list[str],
        target_language: str,
        source_language: str = "auto",
        cancellation_event: threading.Event = None,
        item_progress_callback=None,
    ) -> list[TranslationResult] | None:
        pass

    def get_last_error(self) -> str | None:
        return self.last_error


class GeminiTextTranslationProvider(TranslationProvider):
    def __init__(self, config_manager, gemini_model_instance=None):
        super().__init__(config_manager)
        self.gemini_model = gemini_model_instance
        self.request_timeout = self.config_manager.getint(
            "GeminiAPI", "request_timeout", fallback=60
        )
        self.target_language_gemini = self.config_manager.get(
            "GeminiAPI", "target_language", "Chinese"
        )
        if not GEMINI_LIB_FOR_TRANSLATION_AVAILABLE:
            self.last_error = "Gemini 库 (google-generativeai) 未安装。"
            self.gemini_model = None
        elif self.gemini_model is None:
            self.last_error = "Gemini 模型未提供给翻译器。"

    def translate_batch(
        self,
        texts: list[str],
        target_language: str,
        source_language: str = "Japanese",
        cancellation_event: threading.Event = None,
        item_progress_callback=None,
    ) -> list[TranslationResult] | None:
        self.last_error = None
        if not self.gemini_model:
            if not GEMINI_LIB_FOR_TRANSLATION_AVAILABLE:
                self.last_error = "Gemini 库 (google-generativeai) 未安装。"
            elif not self.last_error:
                self.last_error = "Gemini 模型不可用或未配置。"
            return None
        results = []
        raw_glossary_text = self.config_manager.get(
            "GeminiAPI", "glossary_text", fallback=""
        ).strip()
        glossary_prompt_segment = ""
        if raw_glossary_text:
            glossary_lines = [
                line.strip()
                for line in raw_glossary_text.splitlines()
                if line.strip() and "->" in line.strip()
            ]
            if glossary_lines:
                formatted_glossary = "\n".join(glossary_lines)
                glossary_prompt_segment = f"""Strictly adhere to the following glossary if terms are present:
<glossary>
{formatted_glossary}
</glossary>
"""
        effective_target_language = (
            target_language if target_language else self.target_language_gemini
        )
        print(
            f"    使用 Gemini ({self.gemini_model.model_name if hasattr(self.gemini_model, 'model_name') else '未知模型'}) 翻译 {len(texts)} 个文本块从 {source_language} 到 {effective_target_language}..."
        )
        total_translation_time = 0
        total_items = len(texts)
        for i, original_text in enumerate(texts):
            if cancellation_event and cancellation_event.is_set():
                self.last_error = "Gemini 文本翻译被取消。"
                for _ in range(i, total_items):
                    results.append(
                        TranslationResult(
                            texts[_] if _ < total_items else "",
                            "[翻译取消]",
                            source_language,
                            effective_target_language,
                        )
                    )
                return results
            if item_progress_callback:
                item_progress_callback(
                    i, total_items, f"Gemini 翻译块 {i+1}/{total_items}"
                )
            if not original_text.strip():
                results.append(
                    TranslationResult(
                        original_text, "", source_language, effective_target_language
                    )
                )
                continue
            start_trans_time = time.time()
            prompt_for_translation = f"""{glossary_prompt_segment}
Translate the following {source_language} text into fluent and natural {effective_target_language}. Output only the translated text, without any additional explanations, commentary, or quotation marks unless they are part of the translation itself.
{source_language} Text:
\"\"\"
{original_text}
\"\"\"
{effective_target_language} Translation:
"""
            translated_text_content = f"[Gemini翻译失败]"
            try:
                safety_settings_req = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE",
                    },
                ]
                response = self.gemini_model.generate_content(
                    prompt_for_translation,
                    safety_settings=safety_settings_req,
                    request_options={"timeout": self.request_timeout},
                )
                translated_text_content = response.text.strip()
                results.append(
                    TranslationResult(
                        original_text,
                        translated_text_content,
                        source_language,
                        effective_target_language,
                    )
                )
            except google.api_core.exceptions.DeadlineExceeded as timeout_error:
                self.last_error = f"Gemini 文本翻译请求超时 (超过 {self.request_timeout} 秒): {timeout_error}"
                results.append(
                    TranslationResult(
                        original_text,
                        f"[Gemini翻译超时]",
                        source_language,
                        effective_target_language,
                    )
                )
            except google.api_core.exceptions.GoogleAPIError as api_error:
                self.last_error = f"Gemini 文本翻译 API 调用失败: {api_error}"
                results.append(
                    TranslationResult(
                        original_text,
                        f"[Gemini API错误]",
                        source_language,
                        effective_target_language,
                    )
                )
            except AttributeError as attr_err:
                feedback_info = ""
                if (
                    "response" in locals()
                    and hasattr(response, "prompt_feedback")
                    and response.prompt_feedback
                ):
                    feedback_info = f" Reason: {response.prompt_feedback.block_reason.name if response.prompt_feedback.block_reason else 'Unknown'}"
                self.last_error = f"无法从 Gemini 文本翻译响应获取文本 (可能被安全过滤器阻止): {attr_err}.{feedback_info}"
                results.append(
                    TranslationResult(
                        original_text,
                        f"[Gemini响应错误]",
                        source_language,
                        effective_target_language,
                    )
                )
            except Exception as e:
                self.last_error = f"Gemini 文本翻译时发生未知错误: {e}"
                results.append(
                    TranslationResult(
                        original_text,
                        f"[Gemini未知错误]",
                        source_language,
                        effective_target_language,
                    )
                )
                import traceback

                traceback.print_exc()
            end_trans_time = time.time()
            total_translation_time += end_trans_time - start_trans_time
            if cancellation_event and cancellation_event.is_set():
                self.last_error = "Gemini 文本翻译在网络调用后被取消。"
                if results[-1].translated_text.startswith("[Gemini"):
                    pass
                else:
                    results[-1] = TranslationResult(
                        original_text,
                        "[翻译取消]",
                        source_language,
                        effective_target_language,
                    )
                for k_fill in range(i + 1, total_items):
                    results.append(
                        TranslationResult(
                            texts[k_fill],
                            "[翻译取消]",
                            source_language,
                            effective_target_language,
                        )
                    )
                return results
        if item_progress_callback and total_items > 0:
            item_progress_callback(
                total_items, total_items, "Gemini 文本翻译批处理完成"
            )
        print(f"    Gemini 文本翻译完成。总耗时: {total_translation_time:.2f} 秒")
        return results


def get_translation_provider(
    config_manager, provider_name: str, gemini_model_instance_for_text_translation=None
) -> TranslationProvider | None:
    provider_name_lower = provider_name.lower()
    if "gemini" in provider_name_lower:
        if not GEMINI_LIB_FOR_TRANSLATION_AVAILABLE:
            print("警告: Gemini 库不可用，无法创建 GeminiTextTranslationProvider。")
            return None
        return GeminiTextTranslationProvider(
            config_manager,
            gemini_model_instance=gemini_model_instance_for_text_translation,
        )
    else:
        print(f"尝试获取非Gemini翻译Provider ('{provider_name}')，但当前仅支持Gemini。")
        if GEMINI_LIB_FOR_TRANSLATION_AVAILABLE:
            print("默认返回Gemini翻译Provider。")
            return GeminiTextTranslationProvider(
                config_manager,
                gemini_model_instance=gemini_model_instance_for_text_translation,
            )
        return None
