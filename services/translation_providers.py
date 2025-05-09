# --- START OF translation_providers.py ---
import time
import requests
import threading 
from abc import ABC, abstractmethod

# --- 1. Dependency availability checks FIRST ---
try:
    from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError
    OPENAI_LIB_AVAILABLE = True
except ImportError:
    OPENAI_LIB_AVAILABLE = False
    OpenAI = None 
    APIConnectionError = RateLimitError = APIStatusError = None 
    print("警告: 未安装 openai 库。调用本地 LLM 需要安装此库。")

try:
    import google.generativeai as genai
    import google.api_core.exceptions
    GEMINI_LIB_FOR_TRANSLATION_AVAILABLE = True
except ImportError:
    GEMINI_LIB_FOR_TRANSLATION_AVAILABLE = False
    genai = None 
    google = None 

# --- 2. Base classes and result classes NEXT ---
class TranslationResult:
    def __init__(self, original_text: str, translated_text: str, source_lang: str | None = None, target_lang: str | None = None):
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
    def translate_batch(self, texts: list[str], target_language: str, source_language: str = "auto",
                        cancellation_event: threading.Event = None, item_progress_callback=None) -> list[TranslationResult] | None:
        pass

    def get_last_error(self) -> str | None:
        return self.last_error

# --- 3. Derived provider classes AFTER base classes ---
class LocalLLMTranslationProvider(TranslationProvider):
    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.base_url = self.config_manager.get('LocalTranslationAPI', 'translation_url')
        self.model_name = self.config_manager.get('LocalTranslationAPI', 'model_name')
        self.request_timeout = self.config_manager.getint('LocalTranslationAPI', 'request_timeout', 90)
        self.client = None
        self._setup_client()

    def _setup_client(self):
        # ... (implementation as before)
        if not OPENAI_LIB_AVAILABLE:
            self.last_error = "OpenAI 库未安装，无法使用本地 LLM 翻译。"
            return
        if not self.base_url:
            self.last_error = "未配置本地翻译 API 地址。"
            return
        try:
            self.client = OpenAI(base_url=self.base_url, api_key="nokey", timeout=self.request_timeout)
        except Exception as e:
            self.last_error = f"初始化本地 LLM 客户端失败: {e}"
            print(self.last_error)
            self.client = None
    
    def _get_proxies(self):
        # ... (implementation as before)
        proxies = None
        if self.config_manager.getboolean('Proxy', 'enabled', fallback=False):
            proxy_host = self.config_manager.get('Proxy', 'host')
            proxy_port = self.config_manager.get('Proxy', 'port')
            if proxy_host and proxy_port and proxy_port.isdigit():
                proxy_url = f"http://{proxy_host}:{proxy_port}"
                proxies = {'http': proxy_url, 'https': proxy_url}
        return proxies

    def translate_batch(self, texts: list[str], target_language: str, source_language: str = "Japanese",
                        cancellation_event: threading.Event = None, item_progress_callback=None) -> list[TranslationResult] | None:
        # ... (implementation as before, ensure self.last_error is handled and results are appended)
        self.last_error = None
        if not self.client and OPENAI_LIB_AVAILABLE:
            self._setup_client()
        if not self.client:
            if not OPENAI_LIB_AVAILABLE: self.last_error = "OpenAI 库未安装。"
            elif not self.base_url: self.last_error = "未配置本地翻译 API 地址。"
            else: self.last_error = "本地 LLM 客户端未初始化或初始化失败。"
            return None
        if not self.model_name:
            self.last_error = "未配置本地 LLM 模型名称。"
            return None

        results = []
        raw_glossary_text = self.config_manager.get('LocalTranslationAPI', 'glossary_text', fallback='').strip()
        gpt_dict_raw_text = ""
        if raw_glossary_text:
            glossary_lines = [line.strip() for line in raw_glossary_text.splitlines() if line.strip() and '->' in line.strip()]
            if glossary_lines: gpt_dict_raw_text = "\n".join(glossary_lines)

        http_proxies = self._get_proxies()
        print(f"    使用本地 LLM ({self.model_name} at {self.base_url}, 超时: {self.request_timeout}s) 翻译 {len(texts)} 个文本块到 {target_language}...")
        if http_proxies: print(f"      使用代理: {http_proxies}")

        total_translation_time = 0
        total_items = len(texts)
        for i, original_text in enumerate(texts):
            if cancellation_event and cancellation_event.is_set():
                self.last_error = "本地LLM翻译被取消。"
                print(f"      翻译块 {i+1}/{total_items}: 操作已取消。")
                for _ in range(i, total_items):
                    results.append(TranslationResult(texts[_] if _ < total_items else "", "[翻译取消]", source_language, target_language))
                return results 

            if item_progress_callback:
                item_progress_callback(i, total_items, f"翻译块 {i+1}/{total_items}")


            if not original_text.strip():
                results.append(TranslationResult(original_text, "", source_language, target_language))
                print(f"      翻译块 {i+1}/{total_items}: 空白文本，跳过翻译。")
                continue

            print(f"      翻译块 {i+1}/{total_items}: '{original_text[:30]}...'")
            start_trans_time = time.time()

            system_content = f"You are a translation model. Translate the user-provided {source_language} text into fluent and natural {target_language}."
            if gpt_dict_raw_text:
                 user_prompt = f"Considering the following glossary (which may be empty):\n{gpt_dict_raw_text}\n\nTranslate the following {source_language} text into {target_language}, adhering to the glossary and context:\n\n{original_text}"
            else:
                 user_prompt = f"Translate the following {source_language} text into {target_language}:\n\n{original_text}"

            messages = [{"role": "system", "content": system_content}, {"role": "user", "content": user_prompt}]
            translated_text_content = f"[翻译失败]"
            try:
                if self.base_url.startswith("http"): 
                    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer nokey'}
                    payload = {"model": self.model_name, "messages": messages, "temperature": 0.1, "top_p": 0.3, "max_tokens": 1024, "stream": False}
                    response = requests.post(self.base_url, headers=headers, json=payload, timeout=self.request_timeout, proxies=http_proxies)
                    response.raise_for_status()
                    data = response.json()
                    if "choices" in data and data["choices"] and "message" in data["choices"][0] and "content" in data["choices"][0]["message"]:
                        translated_text_content = data["choices"][0]["message"]["content"].strip()
                    else:
                        self.last_error = f"本地 LLM API ({self.model_name}) 返回格式不符: {str(data)[:200]}"
                        print(f"      警告: {self.last_error}")
                else: 
                    chat_completion = self.client.chat.completions.create(model=self.model_name, messages=messages, temperature=0.1, top_p=0.3, max_tokens=1024)
                    if chat_completion.choices and chat_completion.choices[0].message:
                        translated_text_content = chat_completion.choices[0].message.content.strip()
                
                results.append(TranslationResult(original_text, translated_text_content, source_language, target_language))
                # print(f"      -> '{translated_text_content[:50]}...'") # Keep this if you want detailed logging

            except (APIConnectionError, requests.exceptions.ConnectionError) as e:
                self.last_error = f"无法连接到本地 LLM API ({self.model_name} at {self.base_url}): {e}"
                print(f"      错误: {self.last_error}")
                results.append(TranslationResult(original_text, f"[连接错误]", source_language, target_language))
            # ... (other except blocks as before) ...
            except RateLimitError as e:
                self.last_error = f"本地 LLM API ({self.model_name}) 速率限制: {e}"
                print(f"      错误: {self.last_error}")
                results.append(TranslationResult(original_text, f"[速率限制]", source_language, target_language))
            except APIStatusError as e:
                self.last_error = f"本地 LLM API ({self.model_name}) 状态错误 (code {e.status_code}): {e.response.text if hasattr(e, 'response') and hasattr(e.response, 'text') else e}"
                print(f"      错误: {self.last_error}")
                results.append(TranslationResult(original_text, f"[API状态错误]", source_language, target_language))
            except requests.exceptions.HTTPError as e:
                self.last_error = f"本地 LLM API ({self.model_name}) HTTP 错误: {e.response.status_code} - {e.response.text[:200]}"
                print(f"      错误: {self.last_error}")
                results.append(TranslationResult(original_text, f"[HTTP错误]", source_language, target_language))
            except requests.exceptions.Timeout:
                self.last_error = f"本地 LLM API ({self.model_name}) 请求超时 (超过 {self.request_timeout} 秒)。"
                print(f"      错误: {self.last_error}")
                results.append(TranslationResult(original_text, f"[请求超时]", source_language, target_language))
            except requests.exceptions.RequestException as e:
                self.last_error = f"调用本地 LLM API ({self.model_name}) (requests) 失败: {e}"
                print(f"      错误: {self.last_error}")
                results.append(TranslationResult(original_text, f"[请求错误]", source_language, target_language))
            except Exception as e:
                self.last_error = f"翻译时 ({self.model_name}) 发生未知错误: {e}"
                print(f"      错误: {self.last_error}")
                import traceback; traceback.print_exc()
                results.append(TranslationResult(original_text, f"[未知翻译错误]", source_language, target_language))
            
            end_trans_time = time.time()
            total_translation_time += (end_trans_time - start_trans_time)
            
            if cancellation_event and cancellation_event.is_set(): 
                self.last_error = "本地LLM翻译在网络调用后被取消。"
                print(f"      翻译块 {i+1}/{total_items}: 操作在网络调用后取消。")
                if results[-1].translated_text not in ["[连接错误]", "[速率限制]", "[API状态错误]", "[HTTP错误]", "[请求超时]", "[请求错误]", "[未知翻译错误]"]:
                    results[-1] = TranslationResult(original_text, "[翻译取消]", source_language, target_language)
                for k_fill in range(i + 1, total_items):
                    results.append(TranslationResult(texts[k_fill], "[翻译取消]", source_language, target_language))
                return results


        if item_progress_callback and total_items > 0 : 
             item_progress_callback(total_items, total_items, "本地LLM翻译批处理完成")

        print(f"    本地 LLM 翻译完成。总耗时: {total_translation_time:.2f} 秒")
        return results

class GeminiTextTranslationProvider(TranslationProvider):
    def __init__(self, config_manager, gemini_model_instance=None):
        super().__init__(config_manager)
        self.gemini_model = gemini_model_instance
        self.request_timeout = self.config_manager.getint('GeminiAPI', 'request_timeout', fallback=60)
        self.target_language_gemini = self.config_manager.get('GeminiAPI', 'target_language', 'Chinese')

        if not GEMINI_LIB_FOR_TRANSLATION_AVAILABLE:
            self.last_error = "Gemini 库 (google-generativeai) 未安装。"
            self.gemini_model = None
        elif self.gemini_model is None:
            self.last_error = "Gemini 模型未提供给翻译器。"

    def translate_batch(self, texts: list[str], target_language: str, source_language: str = "Japanese",
                        cancellation_event: threading.Event = None, item_progress_callback=None) -> list[TranslationResult] | None:
        # ... (implementation as before, ensure self.last_error is handled and results are appended)
        self.last_error = None
        if not self.gemini_model:
            if not GEMINI_LIB_FOR_TRANSLATION_AVAILABLE:
                 self.last_error = "Gemini 库 (google-generativeai) 未安装。"
            elif not self.last_error: 
                 self.last_error = "Gemini 模型不可用或未配置。"
            return None

        results = []
        raw_glossary_text = self.config_manager.get('LocalTranslationAPI', 'glossary_text', fallback='').strip() 
        glossary_prompt_segment = ""
        if raw_glossary_text:
            glossary_lines = [line.strip() for line in raw_glossary_text.splitlines() if line.strip() and '->' in line.strip()]
            if glossary_lines:
                formatted_glossary = "\n".join(glossary_lines)
                glossary_prompt_segment = f"""Strictly adhere to the following glossary if terms are present:
<glossary>
{formatted_glossary}
</glossary>
"""
        
        effective_target_language = target_language if target_language else self.target_language_gemini

        print(f"    使用 Gemini ({self.gemini_model.model_name if hasattr(self.gemini_model, 'model_name') else '未知模型'}) 翻译 {len(texts)} 个文本块从 {source_language} 到 {effective_target_language}...")
        
        total_translation_time = 0
        total_items = len(texts)

        for i, original_text in enumerate(texts):
            if cancellation_event and cancellation_event.is_set():
                self.last_error = "Gemini 文本翻译被取消。"
                for _ in range(i, total_items): 
                    results.append(TranslationResult(texts[_] if _ < total_items else "", "[翻译取消]", source_language, effective_target_language))
                return results

            if item_progress_callback:
                item_progress_callback(i, total_items, f"Gemini 翻译块 {i+1}/{total_items}")

            if not original_text.strip():
                results.append(TranslationResult(original_text, "", source_language, effective_target_language))
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
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                response = self.gemini_model.generate_content(
                    prompt_for_translation,
                    safety_settings=safety_settings_req,
                    request_options={"timeout": self.request_timeout}
                )
                translated_text_content = response.text.strip()
                results.append(TranslationResult(original_text, translated_text_content, source_language, effective_target_language))

            except google.api_core.exceptions.DeadlineExceeded as timeout_error:
                self.last_error = f"Gemini 文本翻译请求超时 (超过 {self.request_timeout} 秒): {timeout_error}"
                results.append(TranslationResult(original_text, f"[Gemini翻译超时]", source_language, effective_target_language))
            # ... (other except blocks for Gemini as before) ...
            except google.api_core.exceptions.GoogleAPIError as api_error:
                self.last_error = f"Gemini 文本翻译 API 调用失败: {api_error}"
                results.append(TranslationResult(original_text, f"[Gemini API错误]", source_language, effective_target_language))
            except AttributeError as attr_err: 
                feedback_info = ""
                if 'response' in locals() and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                     feedback_info = f" Reason: {response.prompt_feedback.block_reason.name if response.prompt_feedback.block_reason else 'Unknown'}"
                self.last_error = f"无法从 Gemini 文本翻译响应获取文本 (可能被安全过滤器阻止): {attr_err}.{feedback_info}"
                results.append(TranslationResult(original_text, f"[Gemini响应错误]", source_language, effective_target_language))
            except Exception as e:
                self.last_error = f"Gemini 文本翻译时发生未知错误: {e}"
                results.append(TranslationResult(original_text, f"[Gemini未知错误]", source_language, effective_target_language))
                import traceback; traceback.print_exc()

            end_trans_time = time.time()
            total_translation_time += (end_trans_time - start_trans_time)

            if cancellation_event and cancellation_event.is_set(): 
                self.last_error = "Gemini 文本翻译在网络调用后被取消。"
                if results[-1].translated_text.startswith("[Gemini"): 
                    pass
                else: 
                    results[-1] = TranslationResult(original_text, "[翻译取消]", source_language, effective_target_language)
                for k_fill in range(i + 1, total_items):
                    results.append(TranslationResult(texts[k_fill], "[翻译取消]", source_language, effective_target_language))
                return results
        
        if item_progress_callback and total_items > 0:
             item_progress_callback(total_items, total_items, "Gemini 文本翻译批处理完成")
        
        print(f"    Gemini 文本翻译完成。总耗时: {total_translation_time:.2f} 秒")
        return results

# --- 4. Factory function at the END ---
def get_translation_provider(config_manager, provider_name: str, gemini_model_instance_for_text_translation=None) -> TranslationProvider | None:
    provider_name_lower = provider_name.lower()
    if "local" in provider_name_lower or "sakura" in provider_name_lower:
        return LocalLLMTranslationProvider(config_manager)
    elif "gemini" in provider_name_lower:
        # Ensure Gemini library is available before attempting to instantiate
        if not GEMINI_LIB_FOR_TRANSLATION_AVAILABLE:
            print("警告: Gemini 库不可用，无法创建 GeminiTextTranslationProvider。")
            return None
        return GeminiTextTranslationProvider(config_manager, gemini_model_instance=gemini_model_instance_for_text_translation)
    else:
        print(f"未知的翻译Provider名称: {provider_name}")
        return None

# --- END OF translation_providers.py ---