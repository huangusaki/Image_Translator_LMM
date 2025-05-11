import sys 
import os 
from PyQt6 .QtWidgets import (
QApplication ,
QDialog ,QVBoxLayout ,QHBoxLayout ,QGroupBox ,QRadioButton ,QLabel ,
QLineEdit ,QPushButton ,QCheckBox ,QFileDialog ,QWidget ,QSpacerItem ,
QSizePolicy ,QComboBox ,QTextEdit ,QMessageBox ,QListWidget ,QListWidgetItem 
)
from PyQt6 .QtCore import Qt ,pyqtSlot 
class SettingsDialog (QDialog ):
    def __init__ (self ,config_manager ,parent =None ):
        super ().__init__ (parent )
        self .setWindowTitle ("API及代理设置")
        self .config_manager =config_manager 
        self .config =self .config_manager .get_raw_config_parser ()
        self .setMinimumWidth (600 )
        self ._init_ui ()
        self ._load_settings ()
        self ._connect_signals ()
    def _init_ui (self ):
        main_layout =QVBoxLayout (self )
        self .ocr_group =QGroupBox ("OCR 设置")
        ocr_layout =QVBoxLayout (self .ocr_group )
        self .ocr_group .setSizePolicy (QSizePolicy .Policy .Preferred ,QSizePolicy .Policy .Preferred )
        primary_ocr_layout =QHBoxLayout ()
        primary_ocr_label =QLabel ("主要 OCR Provider:")
        self .primary_ocr_combo =QComboBox ()
        self .primary_ocr_combo .addItems (["Gemini (推荐)","使用回退 OCR"])
        primary_ocr_layout .addWidget (primary_ocr_label )
        primary_ocr_layout .addWidget (self .primary_ocr_combo ,1 )
        ocr_layout .addLayout (primary_ocr_layout )
        self .fallback_ocr_group =QGroupBox ("回退 OCR 设置 (仅当主要 OCR 非 Gemini 时生效)")
        self .fallback_ocr_group .setSizePolicy (QSizePolicy .Policy .Preferred ,QSizePolicy .Policy .Preferred )
        self .fallback_ocr_group .setVisible (False )
        fallback_ocr_group_layout =QVBoxLayout (self .fallback_ocr_group )
        fallback_ocr_provider_layout =QHBoxLayout ()
        fallback_ocr_provider_label =QLabel ("回退 OCR Provider:")
        self .fallback_ocr_provider_combo =QComboBox ()
        self .fallback_ocr_provider_combo .addItems (["Google Cloud Vision"])
        fallback_ocr_provider_layout .addWidget (fallback_ocr_provider_label )
        fallback_ocr_provider_layout .addWidget (self .fallback_ocr_provider_combo ,1 )
        fallback_ocr_group_layout .addLayout (fallback_ocr_provider_layout )
        self .google_ocr_widget =QWidget ()
        self .google_ocr_widget .setVisible (False )
        google_ocr_layout =QHBoxLayout (self .google_ocr_widget )
        google_key_label =QLabel ("Google 服务账号 JSON:")
        self .google_key_edit =QLineEdit ()
        self .google_key_button =QPushButton ("浏览...")
        google_ocr_layout .addWidget (google_key_label );google_ocr_layout .addWidget (self .google_key_edit ,1 );google_ocr_layout .addWidget (self .google_key_button )
        fallback_ocr_group_layout .addWidget (self .google_ocr_widget )
        ocr_layout .addWidget (self .fallback_ocr_group )
        main_layout .addWidget (self .ocr_group )
        self .trans_group =QGroupBox ("翻译设置")
        trans_layout =QVBoxLayout (self .trans_group )
        self .trans_group .setSizePolicy (QSizePolicy .Policy .Preferred ,QSizePolicy .Policy .Preferred )
        primary_trans_layout =QHBoxLayout ()
        primary_trans_label =QLabel ("主要翻译Provider:")
        self .primary_trans_combo =QComboBox ()
        self .primary_trans_combo .addItems (["Gemini (与OCR一同处理)","使用回退翻译"])
        primary_trans_layout .addWidget (primary_trans_label )
        primary_trans_layout .addWidget (self .primary_trans_combo ,1 )
        trans_layout .addLayout (primary_trans_layout )
        self .fallback_trans_group =QGroupBox ("回退翻译设置 (仅当主要翻译非 Gemini 或主要 OCR 非 Gemini 时生效)")
        self .fallback_trans_group .setSizePolicy (QSizePolicy .Policy .Preferred ,QSizePolicy .Policy .Preferred )
        self .fallback_trans_group .setVisible (False )
        fallback_trans_group_layout =QVBoxLayout (self .fallback_trans_group )
        fallback_trans_provider_layout =QHBoxLayout ()
        fallback_trans_provider_label =QLabel ("回退翻译Provider:")
        self .fallback_trans_provider_combo =QComboBox ()
        self .fallback_trans_provider_combo .addItems (["本地 LLM API (Sakura)"])
        fallback_trans_provider_layout .addWidget (fallback_trans_provider_label )
        fallback_trans_provider_layout .addWidget (self .fallback_trans_provider_combo ,1 )
        fallback_trans_group_layout .addLayout (fallback_trans_provider_layout )
        self .local_trans_widget =QWidget ()
        self .local_trans_widget .setVisible (False )
        local_trans_details_vlayout =QVBoxLayout (self .local_trans_widget )
        local_trans_details_vlayout .setContentsMargins (0 ,0 ,0 ,0 )
        local_trans_url_layout =QHBoxLayout ()
        local_trans_url_label =QLabel ("本地翻译 API 地址:")
        self .local_trans_url_edit =QLineEdit ()
        self .local_trans_url_edit .setPlaceholderText ("例如: http://127.0.0.1:8000/v1/chat/completions")
        local_trans_url_layout .addWidget (local_trans_url_label );local_trans_url_layout .addWidget (self .local_trans_url_edit ,1 )
        local_trans_details_vlayout .addLayout (local_trans_url_layout )
        local_trans_model_layout =QHBoxLayout ()
        local_trans_model_label =QLabel ("本地LLM模型名称:")
        self .local_trans_model_edit =QLineEdit ()
        self .local_trans_model_edit .setPlaceholderText ("例如: sakura-14b-qwen2.5-v1.0")
        local_trans_model_layout .addWidget (local_trans_model_label );local_trans_model_layout .addWidget (self .local_trans_model_edit ,1 )
        local_trans_details_vlayout .addLayout (local_trans_model_layout )
        local_trans_lang_layout =QHBoxLayout ()
        local_trans_lang_label =QLabel ("本地LLM目标语言:")
        self .local_target_lang_edit =QLineEdit ()
        self .local_target_lang_edit .setPlaceholderText ("例如: Chinese, English")
        local_trans_lang_layout .addWidget (local_trans_lang_label );local_trans_lang_layout .addWidget (self .local_target_lang_edit ,1 )
        local_trans_details_vlayout .addLayout (local_trans_lang_layout )
        local_llm_timeout_layout =QHBoxLayout ()
        local_llm_timeout_label =QLabel ("本地LLM请求超时 (秒):")
        self .local_llm_timeout_edit =QLineEdit ()
        self .local_llm_timeout_edit .setPlaceholderText ("例如: 90")
        local_llm_timeout_layout .addWidget (local_llm_timeout_label )
        local_llm_timeout_layout .addWidget (self .local_llm_timeout_edit ,0 )
        local_trans_details_vlayout .addLayout (local_llm_timeout_layout )
        fallback_trans_group_layout .addWidget (self .local_trans_widget )
        trans_layout .addWidget (self .fallback_trans_group )
        main_layout .addWidget (self .trans_group )
        self .gemini_group =QGroupBox ("Gemini API 设置")
        self .gemini_group .setVisible (False )
        gemini_main_layout =QVBoxLayout (self .gemini_group )
        self .gemini_group .setSizePolicy (QSizePolicy .Policy .Preferred ,QSizePolicy .Policy .Fixed )
        gemini_key_layout =QHBoxLayout ()
        gemini_key_label =QLabel ("Gemini API Key:")
        self .gemini_api_key_edit =QLineEdit ()
        self .gemini_api_key_edit .setPlaceholderText ("粘贴你的 Gemini API Key")
        self .gemini_api_key_edit .setEchoMode (QLineEdit .EchoMode .Password )
        gemini_key_layout .addWidget (gemini_key_label );gemini_key_layout .addWidget (self .gemini_api_key_edit ,1 )
        gemini_main_layout .addLayout (gemini_key_layout )
        gemini_model_layout =QHBoxLayout ()
        gemini_model_label =QLabel ("Gemini 模型名称:")
        self .gemini_model_edit =QLineEdit ()
        self .gemini_model_edit .setPlaceholderText ("例如: gemini-1.5-flash-latest")
        gemini_model_layout .addWidget (gemini_model_label );gemini_model_layout .addWidget (self .gemini_model_edit ,1 )
        gemini_main_layout .addLayout (gemini_model_layout )
        gemini_target_lang_layout =QHBoxLayout ()
        gemini_base_url_layout =QHBoxLayout ()
        gemini_base_url_label =QLabel ("Gemini Base URL (可选):")
        self .gemini_base_url_edit =QLineEdit ()
        self .gemini_base_url_edit .setPlaceholderText ("例如: https://generativelanguage.googleapis.com/v1beta/openai/")
        self .gemini_base_url_edit .setToolTip (
        "如果留空，将使用官方默认的 Gemini API 地址"
        )
        gemini_base_url_layout .addWidget (gemini_base_url_label )
        gemini_base_url_layout .addWidget (self .gemini_base_url_edit ,1 )
        gemini_main_layout .addLayout (gemini_base_url_layout )
        gemini_target_lang_label =QLabel ("Gemini 目标翻译语言:")
        self .gemini_target_lang_edit =QLineEdit ()
        self .gemini_target_lang_edit .setPlaceholderText ("例如: Chinese, English")
        gemini_target_lang_layout .addWidget (gemini_target_lang_label )
        gemini_target_lang_layout .addWidget (self .gemini_target_lang_edit ,1 )
        gemini_main_layout .addLayout (gemini_target_lang_layout )
        gemini_timeout_layout =QHBoxLayout ()
        gemini_timeout_label =QLabel ("Gemini 请求超时 (秒):")
        self .gemini_timeout_edit =QLineEdit ()
        self .gemini_timeout_edit .setPlaceholderText ("例如: 60")
        gemini_timeout_layout .addWidget (gemini_timeout_label )
        gemini_timeout_layout .addWidget (self .gemini_timeout_edit ,0 )
        gemini_main_layout .addLayout (gemini_timeout_layout )
        main_layout .addWidget (self .gemini_group )
        proxy_group =QGroupBox ("代理设置 (主要供回退的本地 LLM API, Google Vision, 以及尝试为 Gemini 设置环境变量)")
        proxy_layout =QVBoxLayout ()
        proxy_group .setSizePolicy (QSizePolicy .Policy .Preferred ,QSizePolicy .Policy .Fixed )
        self .proxy_checkbox =QCheckBox ("启用代理")
        proxy_layout .addWidget (self .proxy_checkbox )
        self .proxy_details_widget =QWidget ()
        self .proxy_details_widget .setVisible (False )
        proxy_details_layout =QHBoxLayout (self .proxy_details_widget )
        proxy_details_layout .setContentsMargins (20 ,0 ,0 ,0 )
        type_label =QLabel ("类型: http/https")
        host_label =QLabel ("地址:")
        self .proxy_host_edit =QLineEdit ();self .proxy_host_edit .setPlaceholderText ("例如: 127.0.0.1")
        port_label =QLabel ("端口:")
        self .proxy_port_edit =QLineEdit ();self .proxy_port_edit .setPlaceholderText ("例如: 21524")
        proxy_details_layout .addWidget (type_label );proxy_details_layout .addSpacing (10 )
        proxy_details_layout .addWidget (host_label );proxy_details_layout .addWidget (self .proxy_host_edit ,1 )
        proxy_details_layout .addSpacing (10 )
        proxy_details_layout .addWidget (port_label );proxy_details_layout .addWidget (self .proxy_port_edit ,0 )
        proxy_layout .addWidget (self .proxy_details_widget )
        proxy_group .setLayout (proxy_layout )
        main_layout .addWidget (proxy_group )
        button_layout =QHBoxLayout ()
        button_layout .addSpacerItem (QSpacerItem (40 ,20 ,QSizePolicy .Policy .Expanding ,QSizePolicy .Policy .Minimum ))
        self .save_button =QPushButton ("保存");self .cancel_button =QPushButton ("取消")
        button_layout .addWidget (self .save_button );button_layout .addWidget (self .cancel_button )
        main_layout .addLayout (button_layout )
    def _load_settings (self ):
        ocr_provider =self .config_manager .get ('API','ocr_provider',fallback ='gemini').lower ()
        self .primary_ocr_combo .setCurrentIndex (0 if ocr_provider =='gemini'else 1 )
        fallback_ocr_provider =self .config_manager .get ('API','fallback_ocr_provider',fallback ='google cloud vision').lower ()
        self .fallback_ocr_provider_combo .setCurrentIndex (0 if "google"in fallback_ocr_provider else 0 )
        trans_provider =self .config_manager .get ('API','translation_provider',fallback ='gemini').lower ()
        self .primary_trans_combo .setCurrentIndex (0 if trans_provider =='gemini'else 1 )
        self .fallback_trans_provider_combo .setCurrentIndex (0 )
        self .gemini_api_key_edit .setText (self .config_manager .get ('GeminiAPI','api_key',fallback =''))
        self .gemini_model_edit .setText (self .config_manager .get ('GeminiAPI','model_name',fallback ='gemini-1.5-flash-latest'))
        self .gemini_base_url_edit .setText (self .config_manager .get ('GeminiAPI','gemini_base_url',fallback =''))
        self .gemini_timeout_edit .setText (self .config_manager .get ('GeminiAPI','request_timeout',fallback ='60'))
        self .gemini_target_lang_edit .setText (self .config_manager .get ('GeminiAPI','target_language',fallback ='Chinese'))
        self .google_key_edit .setText (self .config_manager .get ('GoogleAPI','service_account_json',fallback =''))
        self .local_trans_url_edit .setText (self .config_manager .get ('LocalTranslationAPI','translation_url',fallback =''))
        self .local_trans_model_edit .setText (self .config_manager .get ('LocalTranslationAPI','model_name',fallback =''))
        self .local_target_lang_edit .setText (self .config_manager .get ('LocalTranslationAPI','target_language',fallback ='Chinese'))
        self .local_llm_timeout_edit .setText (self .config_manager .get ('LocalTranslationAPI','request_timeout',fallback ='90'))
        proxy_enabled =self .config_manager .getboolean ('Proxy','enabled',fallback =False )
        self .proxy_checkbox .setChecked (proxy_enabled )
        self .proxy_host_edit .setText (self .config_manager .get ('Proxy','host',fallback ='127.0.0.1'))
        self .proxy_port_edit .setText (self .config_manager .get ('Proxy','port',fallback ='21524'))
        self ._toggle_proxy_details (Qt .CheckState .Checked .value if proxy_enabled else Qt .CheckState .Unchecked .value )
        self ._update_provider_sections_visibility ()
    def _save_settings (self ):
        self .config_manager .set ('API','ocr_provider','gemini'if self .primary_ocr_combo .currentIndex ()==0 else 'fallback')
        if self .fallback_ocr_provider_combo .count ()>0 :
             self .config_manager .set ('API','fallback_ocr_provider','google cloud vision')
        else :
             self .config_manager .set ('API','fallback_ocr_provider','google cloud vision')
        self .config_manager .set ('API','translation_provider','gemini'if self .primary_trans_combo .currentIndex ()==0 else 'fallback')
        self .config_manager .set ('API','fallback_translation_provider','本地 llm api (sakura)')
        self .config_manager .set ('GeminiAPI','api_key',self .gemini_api_key_edit .text ())
        self .config_manager .set ('GeminiAPI','model_name',self .gemini_model_edit .text ())
        self .config_manager .set ('GeminiAPI','request_timeout',self .gemini_timeout_edit .text ())
        self .config_manager .set ('GeminiAPI','gemini_base_url',self .gemini_base_url_edit .text ().strip ())
        self .config_manager .set ('GeminiAPI','target_language',self .gemini_target_lang_edit .text ())
        self .config_manager .set ('GoogleAPI','service_account_json',self .google_key_edit .text ())
        self .config_manager .set ('LocalTranslationAPI','translation_url',self .local_trans_url_edit .text ())
        self .config_manager .set ('LocalTranslationAPI','model_name',self .local_trans_model_edit .text ())
        self .config_manager .set ('LocalTranslationAPI','target_language',self .local_target_lang_edit .text ())
        self .config_manager .set ('LocalTranslationAPI','request_timeout',self .local_llm_timeout_edit .text ())
        self .config_manager .set ('Proxy','enabled',str (self .proxy_checkbox .isChecked ()))
        self .config_manager .set ('Proxy','type','http')
        self .config_manager .set ('Proxy','host',self .proxy_host_edit .text ())
        self .config_manager .set ('Proxy','port',self .proxy_port_edit .text ())
        return True 
    def _connect_signals (self ):
        self .save_button .clicked .connect (self .on_save )
        self .cancel_button .clicked .connect (self .reject )
        self .proxy_checkbox .stateChanged .connect (self ._toggle_proxy_details )
        self .google_key_button .clicked .connect (self ._browse_google_key )
        self .primary_ocr_combo .currentIndexChanged .connect (self ._update_provider_sections_visibility )
        self .primary_trans_combo .currentIndexChanged .connect (self ._update_provider_sections_visibility )
        self .fallback_ocr_provider_combo .currentIndexChanged .connect (self ._update_provider_sections_visibility )
    def _toggle_proxy_details (self ,state ):
        is_checked =False 
        if isinstance (state ,Qt .CheckState ):
            is_checked =(state ==Qt .CheckState .Checked )
        elif isinstance (state ,int ):
            is_checked =(state ==Qt .CheckState .Checked .value )
        elif isinstance (state ,bool ):
            is_checked =state 
        self .proxy_details_widget .setVisible (is_checked )
        self .adjustSize ()
    def _update_provider_sections_visibility (self ):
        is_gemini_ocr_primary =(self .primary_ocr_combo .currentIndex ()==0 )
        is_gemini_trans_primary =(self .primary_trans_combo .currentIndex ()==0 )
        show_fallback_ocr_group_flag =not is_gemini_ocr_primary 
        if self .fallback_ocr_group .isVisible ()!=show_fallback_ocr_group_flag :
            self .fallback_ocr_group .setVisible (show_fallback_ocr_group_flag )
        if show_fallback_ocr_group_flag :
            is_google_selected_for_fallback_ocr =(self .fallback_ocr_provider_combo .currentIndex ()==0 and self .fallback_ocr_provider_combo .count ()>0 )
            if self .google_ocr_widget .isVisible ()!=is_google_selected_for_fallback_ocr :
                self .google_ocr_widget .setVisible (is_google_selected_for_fallback_ocr )
        else :
            self .google_ocr_widget .setVisible (False )
        show_fallback_trans_group_flag =(not is_gemini_trans_primary )or (not is_gemini_ocr_primary )
        if self .fallback_trans_group .isVisible ()!=show_fallback_trans_group_flag :
            self .fallback_trans_group .setVisible (show_fallback_trans_group_flag )
        if show_fallback_trans_group_flag :
            should_show_local_trans_widget_now =(self .fallback_trans_provider_combo .currentIndex ()==0 )
            if self .local_trans_widget .isVisible ()!=should_show_local_trans_widget_now :
                 self .local_trans_widget .setVisible (should_show_local_trans_widget_now )
        else :
            self .local_trans_widget .setVisible (False )
        show_gemini_api_settings_group_flag =is_gemini_ocr_primary or is_gemini_trans_primary 
        if self .gemini_group .isVisible ()!=show_gemini_api_settings_group_flag :
            self .gemini_group .setVisible (show_gemini_api_settings_group_flag )
        QApplication .processEvents ()
        self .layout ().activate ()
        self .adjustSize ()
    def _browse_google_key (self ):
        current_path =self .google_key_edit .text ()
        start_dir =os .path .dirname (current_path )if current_path and os .path .exists (os .path .dirname (current_path ))else os .path .expanduser ("~")
        file_path ,_ =QFileDialog .getOpenFileName (self ,"选择 Google 服务账号 JSON 文件",start_dir ,"JSON 文件 (*.json);;所有文件 (*)")
        if file_path :self .google_key_edit .setText (file_path )
    @pyqtSlot ()
    def on_save (self ):
        if self .proxy_checkbox .isChecked ():
            if not self .proxy_host_edit .text ():
                 QMessageBox .warning (self ,"输入错误","启用了代理，但代理地址为空。");self .proxy_host_edit .setFocus ();return 
            if not self .proxy_port_edit .text ().isdigit ():
                 QMessageBox .warning (self ,"输入错误","代理端口必须是一个有效的数字。");self .proxy_port_edit .setFocus ();return 
        if (self .primary_ocr_combo .currentIndex ()==0 or self .primary_trans_combo .currentIndex ()==0 ):
            if not self .gemini_api_key_edit .text ():
                QMessageBox .warning (self ,"输入错误","已选择 Gemini 作为Provider，但未填写 Gemini API Key。");self .gemini_api_key_edit .setFocus ();return 
            if not self .gemini_target_lang_edit .text ():
                QMessageBox .warning (self ,"输入错误","已选择 Gemini 作为Provider，但未填写 Gemini 目标翻译语言。");self .gemini_target_lang_edit .setFocus ();return 
        gemini_timeout_str =self .gemini_timeout_edit .text ()
        if gemini_timeout_str and (not gemini_timeout_str .isdigit ()or int (gemini_timeout_str )<=0 ):
             if gemini_timeout_str :
                QMessageBox .warning (self ,"输入错误","Gemini 请求超时必须是一个正整数。");self .gemini_timeout_edit .setFocus ();return 
        local_llm_timeout_str =self .local_llm_timeout_edit .text ()
        gemini_base_url_str =self .gemini_base_url_edit .text ().strip ()
        if gemini_base_url_str and not (gemini_base_url_str .startswith ("http://")or gemini_base_url_str .startswith ("https://")):
            QMessageBox .warning (self ,"输入错误","Gemini Base URL 如果填写，必须以 http:// 或 https:// 开头。")
            self .gemini_base_url_edit .setFocus ()
            return 
        if local_llm_timeout_str and (not local_llm_timeout_str .isdigit ()or int (local_llm_timeout_str )<=0 ):
            if local_llm_timeout_str :
                QMessageBox .warning (self ,"输入错误","本地LLM 请求超时必须是一个正整数。");self .local_llm_timeout_edit .setFocus ();return 
        if self .fallback_trans_group .isVisible ()and self .local_trans_widget .isVisible ()and not self .local_target_lang_edit .text ():
             QMessageBox .warning (self ,"输入错误","请输入本地LLM的目标翻译语言。");self .local_target_lang_edit .setFocus ();return 
        if self .primary_trans_combo .currentIndex ()==1 and self .fallback_trans_group .isVisible ()and self .local_trans_widget .isVisible ()and not self .local_trans_url_edit .text ():
            QMessageBox .warning (self ,"输入提示","未填写本地翻译 API 地址。\n如果 Gemini API 不可用或未配置，且选择使用回退翻译，则无法进行翻译。")
        if self ._save_settings ():
            if self .proxy_checkbox .isChecked ():
                proxy_host =self .proxy_host_edit .text ()
                proxy_port =self .proxy_port_edit .text ()
                if proxy_host and proxy_port :
                    proxy_url =f"http://{proxy_host}:{proxy_port}"
                    os .environ ['HTTPS_PROXY']=proxy_url 
                    os .environ ['HTTP_PROXY']=proxy_url 
                    print (f"SettingsDialog: Applied proxy to environment: HTTPS_PROXY/HTTP_PROXY = {proxy_url}")
                else :
                    if 'HTTPS_PROXY'in os .environ :del os .environ ['HTTPS_PROXY']
                    if 'HTTP_PROXY'in os .environ :del os .environ ['HTTP_PROXY']
                    print ("SettingsDialog: Proxy enabled but host/port invalid. Cleared HTTPS_PROXY/HTTP_PROXY.")
            else :
                current_https_proxy =os .environ .get ('HTTPS_PROXY','')
                current_http_proxy =os .environ .get ('HTTP_PROXY','')
                proxy_host_check =self .config_manager .get ('Proxy','host','')
                if 'HTTPS_PROXY'in os .environ and (current_https_proxy .startswith ("http://127.0.0.1")or (proxy_host_check and proxy_host_check in current_https_proxy )):
                    del os .environ ['HTTPS_PROXY']
                if 'HTTP_PROXY'in os .environ and (current_http_proxy .startswith ("http://127.0.0.1")or (proxy_host_check and proxy_host_check in current_http_proxy )):
                    del os .environ ['HTTP_PROXY']
                print ("SettingsDialog: Proxy disabled. Ensured related env vars potentially set by app are cleared.")
            self .accept ()
if __name__ =='__main__':
    from config_manager import ConfigManager as DummyCM 
    app =QApplication (sys .argv )
    if not os .path .exists ('config.ini'):
        print ("Creating dummy config.ini for testing.")
        dummy_cfg_writer =DummyCM ('config.ini')
        dummy_cfg_writer .set ('API','ocr_provider','gemini')
        dummy_cfg_writer .set ('API','translation_provider','gemini')
        dummy_cfg_writer .save ()
    cfg_manager =DummyCM ('config.ini')
    dialog =SettingsDialog (cfg_manager )
    dialog .show ()
    sys .exit (app .exec ())