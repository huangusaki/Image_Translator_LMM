# --- START OF FILE font_utils.py ---
import os
import sys

try:
    from PIL import ImageFont, ImageDraw
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    ImageFont = None
    ImageDraw = None
    print("警告(font_utils): Pillow 库未安装，字体处理功能将受限。")

def find_font_path(font_name_or_path: str) -> str | None:
    if not PILLOW_AVAILABLE: return None
    if os.path.isabs(font_name_or_path) and os.path.exists(font_name_or_path):
        return font_name_or_path
    
    system_font_paths = []
    if sys.platform == "win32":
        system_font_paths.append(os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"))
    elif sys.platform == "linux":
        system_font_paths.extend(["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")])
    elif sys.platform == "darwin":
        system_font_paths.extend(["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")])
    
    font_name_lower = font_name_or_path.lower()
    has_extension = any(font_name_lower.endswith(ext) for ext in [".ttf", ".otf", ".ttc"])

    if not has_extension:
        for ext_to_try in [".ttf", ".otf", ".ttc"]: # Prioritize common extensions
            font_file_to_try = font_name_or_path + ext_to_try
            for base_path in system_font_paths:
                if os.path.isdir(base_path):
                    potential_path = os.path.join(base_path, font_file_to_try)
                    if os.path.exists(potential_path): return potential_path
                    # Case-insensitive check for font file name (common on Linux)
                    try:
                        for f_name in os.listdir(base_path):
                            if f_name.lower() == font_file_to_try.lower():
                                potential_path_case_insensitive = os.path.join(base_path, f_name)
                                if os.path.exists(potential_path_case_insensitive): return potential_path_case_insensitive
                    except OSError:
                        pass # os.listdir might fail due to permissions
    else: 
        for base_path in system_font_paths:
            if os.path.isdir(base_path):
                potential_path = os.path.join(base_path, font_name_or_path)
                if os.path.exists(potential_path): return potential_path
                # Case-insensitive check
                try:
                    for f_name in os.listdir(base_path):
                        if f_name.lower() == font_name_or_path.lower():
                            potential_path_case_insensitive = os.path.join(base_path, f_name)
                            if os.path.exists(potential_path_case_insensitive): return potential_path_case_insensitive
                except OSError:
                    pass
    
    # If it was specified with an extension but not found, and that extension wasn't .ttc,
    # try adding .ttc specifically if the original name didn't imply it was a collection.
    # This is a bit of a heuristic.
    if has_extension and not font_name_lower.endswith(".ttc"):
        base_name_no_ext, _ = os.path.splitext(font_name_or_path)
        font_file_to_try_ttc = base_name_no_ext + ".ttc"
        for base_path in system_font_paths:
             if os.path.isdir(base_path):
                potential_path = os.path.join(base_path, font_file_to_try_ttc)
                if os.path.exists(potential_path): return potential_path
                try:
                    for f_name in os.listdir(base_path):
                        if f_name.lower() == font_file_to_try_ttc.lower():
                            potential_path_case_insensitive = os.path.join(base_path, f_name)
                            if os.path.exists(potential_path_case_insensitive): return potential_path_case_insensitive
                except OSError:
                    pass


    print(f"警告(find_font_path): 字体 '{font_name_or_path}' 未在标准路径或作为绝对路径找到。")
    return None

def get_pil_font(font_path_or_name: str | None, size: int, font_index: int = 0) -> ImageFont.FreeTypeFont | ImageFont.ImageFont | None:
    if not PILLOW_AVAILABLE: return None
    
    actual_font_path = font_path_or_name
    if font_path_or_name and not os.path.isabs(font_path_or_name): 
        resolved_path = find_font_path(font_path_or_name)
        if resolved_path:
            actual_font_path = resolved_path
        # If not resolved, actual_font_path remains font_path_or_name,
        # ImageFont.truetype might still find it if it's a system font name Pillow recognizes.

    try:
        if actual_font_path and (os.path.exists(actual_font_path) or not os.path.isabs(actual_font_path)): # try even if not abs path
            return ImageFont.truetype(actual_font_path, size, index=font_index)
        else: 
            # This path might be taken if find_font_path returned None and font_path_or_name was an absolute path that didn't exist.
            # Or if font_path_or_name was None.
            # print(f"警告(get_pil_font): 无法加载字体 '{font_path_or_name}' (解析路径: {actual_font_path})。尝试Pillow默认字体。")
            return ImageFont.load_default(size=size) # Pass size to load_default
    except Exception as e:
        print(f"加载字体 '{font_path_or_name}' (大小: {size}px, 索引: {font_index}) 失败: {e}。尝试Pillow默认字体。")
        try:
            return ImageFont.load_default(size=size)
        except Exception as e_default:
            print(f"加载Pillow默认字体也失败了: {e_default}")
            return None

def get_font_line_height(font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None, default_size: int = 16, vertical_spacing_px: int = 0) -> int:
    if not PILLOW_AVAILABLE or not font: 
        return int(default_size * 1.2) + vertical_spacing_px # Fallback if no font or Pillow
    
    line_height = 0
    font_size_from_font = default_size
    if hasattr(font, 'size'): 
        font_size_from_font = font.size
    
    try:
        # For TrueType fonts, getbbox is generally preferred and more accurate.
        if hasattr(font, 'getbbox'):
            # Using a string with ascenders and descenders
            # "AgyQÍ" includes common cases. Add a space for some fonts.
            # (left, top, right, bottom) - top is negative for ascent above baseline
            bbox = font.getbbox("AgyQÍ M") 
            ascent = abs(bbox[1]) # typically negative
            descent = bbox[3] # distance from baseline to bottom
            
            # A common way to calculate line height is ascent + descent.
            # Pillow's getbbox bottom (bbox[3]) is the distance from baseline to the lowest pixel.
            # Pillow's getbbox top (bbox[1]) is the distance from baseline to the highest pixel (often negative).
            # So, height of the text content is bbox[3] - bbox[1].
            calculated_height = descent - bbox[1] # bbox[1] is negative or zero
            
            if calculated_height > 0:
                # Add a small leading, typically 10-20% of font size, if not covered by font metrics.
                # Some fonts might already include internal leading in their metrics.
                # This is a heuristic.
                leading = max(1, int(font_size_from_font * 0.15)) # Adjusted leading
                line_height = calculated_height + leading
            else: # Fallback if getbbox gives unexpected results
                line_height = int(font_size_from_font * 1.25) # Adjusted fallback multiplier

        # Fallback for non-TrueType fonts or if getbbox failed
        if line_height <= 0 :
            if hasattr(font, 'getmask'): # For ImageFont (bitmap)
                mask = font.getmask("A") 
                if mask and hasattr(mask, 'size') and len(mask.size) == 2:
                    line_height = mask.size[1] + max(2, int(font_size_from_font * 0.15)) 
            # This is an older way, might not be available/accurate for FreeTypeFont
            elif hasattr(font, 'font') and hasattr(font.font, 'getsize'): 
                 (width, baseline), (offset_x, offset_y) = font.font.getsize("A") # (width, height_above_baseline), (offset_x, offset_y_from_top_left_of_char_cell)
                 # baseline here is often ascent. The second tuple is about character placement, not total line height.
                 # This path is less reliable for line height.
                 line_height = baseline + max(2, int(font_size_from_font * 0.15)) # Simplified

        if line_height <= 0: # Final fallback if all else fails
            line_height = int(font_size_from_font * 1.20) 

    except Exception as e:
        print(f"警告(get_font_line_height): 获取字体指标时出错: {e}。使用后备值。")
        line_height = int(font_size_from_font * 1.20)

    # Ensure a minimum line height, then add the explicit vertical_spacing_px
    final_line_height = max(int(line_height), int(font_size_from_font * 0.5)) + vertical_spacing_px
    return final_line_height


def wrap_text_pil(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None,
                  max_dim: int,
                  orientation: str = "horizontal",
                  char_spacing_px: int = 0,
                  line_or_col_spacing_px: int = 0 # For horizontal: this is line spacing. For vertical: this is column spacing.
                  ) -> tuple[list[str], int, int, int]:
    """
    Wraps text for Pillow.
    For horizontal: max_dim is max_width.
                    char_spacing_px is horizontal char spacing.
                    line_or_col_spacing_px is vertical line spacing.
                    Returns (lines_list, total_text_height, single_line_height_with_spacing, max_line_width_achieved)
    For vertical:   max_dim is max_height (column height).
                    char_spacing_px is vertical char spacing (within a column).
                    line_or_col_spacing_px is horizontal column spacing (between columns).
                    Returns (columns_list, total_text_width, single_char_height_with_spacing_in_col, max_col_height_achieved)
    """
    default_font_size = 16
    if PILLOW_AVAILABLE and font and hasattr(font, 'size'):
        default_font_size = font.size
    
    if not text or max_dim <= 0 or not PILLOW_AVAILABLE or not font or not draw:
        if orientation == "horizontal":
            # For horizontal, line_or_col_spacing_px is line spacing
            line_h_calc = get_font_line_height(font, default_font_size, line_or_col_spacing_px)
            text_len_approx = 0
            if text and font:
                try: text_len_approx = draw.textlength(text, font=font)
                except: text_len_approx = len(text) * default_font_size // 2
            
            return [text] if text else [], line_h_calc if text else 0, line_h_calc, int(text_len_approx)
        else: # vertical
            # For vertical, char_spacing_px is spacing between chars in a column
            char_h_in_col_calc = get_font_line_height(font, default_font_size, char_spacing_px)
            avg_char_width_approx = default_font_size
            if text and font:
                try: avg_char_width_approx = font.getlength("M") if hasattr(font, 'getlength') else font.size
                except: avg_char_width_approx = font.size if hasattr(font, 'size') else default_font_size
                if avg_char_width_approx == 0: avg_char_width_approx = default_font_size

            return [text] if text else [], int(avg_char_width_approx) if text else 0, char_h_in_col_calc, len(text) * char_h_in_col_calc if text else 0

    output_segments = [] 

    if orientation == "horizontal":
        # single_segment_dim_secondary is single line height, including its spacing (line_or_col_spacing_px)
        single_segment_dim_secondary = get_font_line_height(font, default_font_size, line_or_col_spacing_px)
        current_line_text = ""
        max_line_width_achieved = 0
        
        words = text.split(' ') # Basic word splitting for better wrapping (optional, can be complex for CJK)
                            # For CJK, char-by-char is often fine. This is a compromise.
                            # If CJK, can iterate char by char directly.
                            # Let's assume char by char for now to match previous logic more closely.

        current_char_idx = 0
        while current_char_idx < len(text):
            char_val = text[current_char_idx]

            if char_val == '\n':
                if current_line_text: # Add accumulated line before newline
                    output_segments.append(current_line_text)
                    current_w = draw.textlength(current_line_text, font=font) + \
                                (char_spacing_px * (len(current_line_text) -1) if len(current_line_text)>1 and char_spacing_px != 0 else 0)
                    max_line_width_achieved = max(max_line_width_achieved, current_w)
                output_segments.append("") # Represent the newline itself as an empty segment
                current_line_text = ""
                current_char_idx += 1
                continue

            test_line = current_line_text + char_val
            current_test_width = draw.textlength(test_line, font=font)
            if len(test_line) > 1 and char_spacing_px != 0:
                current_test_width += char_spacing_px * (len(test_line) - 1)

            if current_test_width <= max_dim:
                current_line_text = test_line
                current_char_idx += 1
            else: # Word exceeds max_dim or current_line_text + word exceeds
                if current_line_text: # If there's something in the current line, add it
                    output_segments.append(current_line_text)
                    current_w = draw.textlength(current_line_text, font=font) + \
                                (char_spacing_px * (len(current_line_text) -1) if len(current_line_text)>1 and char_spacing_px != 0 else 0)
                    max_line_width_achieved = max(max_line_width_achieved, current_w)
                    current_line_text = "" # Start a new line
                
                # If current_line_text was empty, it means the char_val itself is too long
                # (or the first char of a sequence). Add it and continue.
                # This handles cases where a single character (or a sequence that cannot be broken) exceeds max_dim.
                if not current_line_text: 
                    # We must add the character that caused the overflow to a new line.
                    # If even a single character is too wide, it will still be added.
                    current_line_text = char_val 
                    current_char_idx += 1
                    # If this single char is the end of text, it will be handled by the final append.
                    # If not, the loop continues, and this char forms the start of a new line.
                    # If this single char itself is too wide, it will be added as its own line when the loop ends or next char overflows.

        if current_line_text: # Add any remaining text
            output_segments.append(current_line_text)
            current_w = draw.textlength(current_line_text, font=font) + \
                        (char_spacing_px * (len(current_line_text) -1) if len(current_line_text)>1 and char_spacing_px != 0 else 0)
            max_line_width_achieved = max(max_line_width_achieved, current_w)

        if not output_segments and text: # Should not happen if loop runs, but as a fallback
            output_segments = [text]
            max_line_width_achieved = draw.textlength(text, font=font) + \
                                      (char_spacing_px * (len(text)-1) if len(text)>1 and char_spacing_px !=0 else 0)
        
        total_dim_primary = 0
        if output_segments: # Calculate total height based on number of lines and their height
                           # Note: manual break extra spacing is NOT added here, it's added by the renderer.
            total_dim_primary = len(output_segments) * single_segment_dim_secondary
        
        if not text: total_dim_primary = 0 # No text, no height.

        return output_segments, total_dim_primary, single_segment_dim_secondary, int(max_line_width_achieved)

    else: # Vertical (orientation == "vertical_rtl" or "vertical_ltr")
        # single_char_height_in_col_with_spacing is single char height including its spacing (char_spacing_px)
        single_char_height_in_col_with_spacing = get_font_line_height(font, default_font_size, char_spacing_px)
        
        # Estimate single column width (this is approximate, for total width calculation)
        try:
            col_width_metric_for_total = font.getlength("M")
            if col_width_metric_for_total == 0: col_width_metric_for_total = font.size if hasattr(font, 'size') else default_font_size
        except AttributeError:
            col_width_metric_for_total = font.size if hasattr(font, 'size') else default_font_size
        if col_width_metric_for_total == 0 : col_width_metric_for_total = default_font_size # Final fallback for col width

        current_col_chars_list = []
        current_col_pixel_height = 0
        max_col_height_achieved = 0

        for char_val in text:
            if char_val == '\n': # Newline means new column
                if current_col_chars_list:
                    output_segments.append("".join(current_col_chars_list))
                    max_col_height_achieved = max(max_col_height_achieved, current_col_pixel_height)
                output_segments.append("") # Represent newline as empty column
                current_col_chars_list = []
                current_col_pixel_height = 0
                continue
            
            # If current column is empty, or adding next char doesn't exceed max_dim (max_height)
            if not current_col_chars_list or (current_col_pixel_height + single_char_height_in_col_with_spacing <= max_dim) :
                current_col_chars_list.append(char_val)
                current_col_pixel_height += single_char_height_in_col_with_spacing
            else: # Column is full, start a new one
                output_segments.append("".join(current_col_chars_list))
                max_col_height_achieved = max(max_col_height_achieved, current_col_pixel_height)
                
                current_col_chars_list = [char_val] # New column starts with current char
                current_col_pixel_height = single_char_height_in_col_with_spacing
        
        if current_col_chars_list: # Add the last accumulated column
            output_segments.append("".join(current_col_chars_list))
            max_col_height_achieved = max(max_col_height_achieved, current_col_pixel_height)

        if not output_segments and text: # Fallback if no segments created but text exists
            output_segments = [text]
            max_col_height_achieved = len(text) * single_char_height_in_col_with_spacing

        # total_dim_primary is total width of all columns
        # This calculation uses the estimated col_width_metric_for_total and line_or_col_spacing_px (which is column spacing here)
        # Manual break extra spacing is NOT added here, it's added by the renderer.
        total_dim_primary = 0
        if output_segments:
            num_cols = len(output_segments)
            total_dim_primary = (num_cols * col_width_metric_for_total)
            if num_cols > 1:
                total_dim_primary += (num_cols - 1) * line_or_col_spacing_px # Add inter-column spacing
        
        if not text: total_dim_primary = 0

        return output_segments, int(total_dim_primary), single_char_height_in_col_with_spacing, int(max_col_height_achieved)

# --- END OF FILE font_utils.py ---