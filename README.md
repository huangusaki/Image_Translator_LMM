Image Translator is a desktop application built with PyQt6, designed to facilitate the optical character recognition (OCR) and translation of text embedded within images. It provides an interactive environment for users to load images, process them using various AI-powered services, and meticulously edit the resulting translated text overlays.
![Sample Image 4](sample/4.png)
![Sample Image 3](sample/3.png)
![Sample Image 2](sample/2.png)
![Sample Image 1](sample/1.png)
## Key Features:

*   **Flexible Image Loading:**
    *   Load single images for detailed, interactive translation.
    *   Batch process multiple images for efficient bulk translation and export.
*   **Advanced OCR Capabilities:**
    *   **Primary OCR with Gemini:** Utilizes Google's Gemini model (via its OpenAI-compatible API) for integrated multi-modal OCR and translation, or as a standalone OCR step.
    *   **Fallback OCR Options:**
        *   Google Cloud Vision API.
        *   Local PaddleOCR (supports multiple languages, including Japanese).
    *   Users can select their preferred primary and fallback OCR providers.
*   **Versatile Translation Services:**
    *   **Primary Translation with Gemini:** Leverages Gemini for text translation, either as part of the multi-modal OCR process or as a separate step for text extracted by other OCR engines.
    *   **Fallback Translation with Local LLM:** Supports translation via a local Large Language Model API (e.g., compatible with Sakura, Llama.cpp server endpoints).
    *   Provider preferences are configurable.
*   **Interactive Text Block Manipulation:**
    *   **Visual Editing:** Directly on a preview of the image, users can:
        *   **Select** individual text blocks.
        *   **Move** text blocks to new positions.
        *   **Resize** the bounding box of text blocks.
        *   **Rotate** text blocks to any angle.
    *   **Content Editing:**
        *   Edit translated text via a dedicated detail panel or an in-place dialog.
        *   View original (OCR'd) text alongside the translation.
    *   **Add/Delete Blocks:** Create new text blocks manually or delete existing ones.
*   **Comprehensive Text Styling:**
    *   **Font Customization:** Choose system fonts or provide font file paths.
    *   **Font Size:** Set a fixed font size or allow dynamic sizing based on LLM suggestions.
    *   **Colors:** Customize main text color, outline color, and text background color (all with RGBA support).
    *   **Outline:** Control the thickness of the text outline.
    *   **Spacing:** Adjust horizontal character/line spacing and vertical character/column spacing.
    *   **Orientation & Alignment:** Set text orientation (horizontal, vertical LTR/RTL) and alignment (left, center, right) per block.
*   **Configuration and Customization:**
    *   **API & Proxy Settings:** Dedicated dialog to manage API keys (Gemini, Google), provider choices, model names, timeouts, and HTTP/HTTPS proxy settings.
    *   **Glossary Management:** Create, import, and export a glossary for consistent terminology when using the local LLM translator.
    *   **UI Personalization:** Change the main window's background image and application icon.
    *   All settings are persisted in a `config.ini` file.
*   **User Experience:**
    *   **Graphical User Interface:** Built with PyQt6 for a responsive desktop experience.
    *   **Progress Indication:** Visual feedback with progress bars and status messages for long-running operations (image processing, batch translation).
    *   **Cancellable Operations:** Ability to cancel ongoing single or batch processing tasks.
    *   **Export Functionality:** Save the final image with all translated and styled text blocks rendered onto it.
  AI总结的，懒得写
