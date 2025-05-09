# --- START OF FILE utils.py ---

import os
import math
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QFontMetrics, QPen, QBrush
from PyQt6.QtCore import Qt, QRectF, QPointF

from config_manager import ConfigManager # 假设存在

try:
    from PIL import Image, ImageDraw, ImageFont as PILImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    PILImageFont = None
    Image = None
    ImageDraw = None
    print("警告(utils): Pillow 库未安装，图像处理和显示功能将受限。")

if PILLOW_AVAILABLE:
    from .font_utils import get_pil_font, get_font_line_height, wrap_text_pil, find_font_path


def pil_to_qpixmap(pil_image: Image.Image) -> QPixmap | None:
    if not PILLOW_AVAILABLE or not pil_image:
        return None
    try:
        if pil_image.mode == 'P':
            pil_image = pil_image.convert("RGBA")
        elif pil_image.mode == 'L':
            pil_image = pil_image.convert("RGB")
        elif pil_image.mode not in ("RGB", "RGBA"):
             pil_image = pil_image.convert("RGBA") # Default to RGBA if unknown

        data = pil_image.tobytes("raw", pil_image.mode)

        qimage_format = QImage.Format.Format_Invalid
        if pil_image.mode == "RGBA":
            qimage_format = QImage.Format.Format_RGBA8888
        elif pil_image.mode == "RGB":
            qimage_format = QImage.Format.Format_RGB888
        # Add other formats if necessary, e.g., RGBX for RGB with an unused alpha channel

        if qimage_format == QImage.Format.Format_Invalid:
            print(f"警告(pil_to_qpixmap): 不支持的Pillow图像模式 {pil_image.mode} 转换为QImage。")
            # Attempt a final conversion to RGBA as a fallback
            pil_image_rgba = pil_image.convert("RGBA")
            data = pil_image_rgba.tobytes("raw", "RGBA")
            qimage = QImage(data, pil_image_rgba.width, pil_image_rgba.height, QImage.Format.Format_RGBA8888)
            if qimage.isNull(): return None
            return QPixmap.fromImage(qimage)


        qimage = QImage(data, pil_image.width, pil_image.height, qimage_format)

        # For some systems/Qt versions, RGB byte order might be an issue
        # If colors are swapped (BGR vs RGB), you might need:
        # if pil_image.mode == "RGB":
        # qimage = qimage.rgbSwapped()

        if qimage.isNull():
            print(f"警告(pil_to_qpixmap): QImage.isNull() 为 True，模式: {pil_image.mode}")
            return None
        return QPixmap.fromImage(qimage)
    except Exception as e:
        print(f"错误(pil_to_qpixmap): {e}")
        return None


def crop_image_to_circle(pil_image: Image.Image) -> Image.Image | None:
    if not PILLOW_AVAILABLE or not pil_image: return None
    try:
        img = pil_image.copy().convert("RGBA")
        width, height = img.size
        size = min(width, height)

        mask = Image.new('L', (width, height), 0)
        draw_mask = ImageDraw.Draw(mask)

        left = (width - size) // 2
        top = (height - size) // 2
        right = left + size
        bottom = top + size

        draw_mask.ellipse((left, top, right, bottom), fill=255)
        
        # Create a new image with transparent background
        output_img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        output_img.paste(img, (0,0), mask=mask) # Paste using the circle mask

        return output_img
    except Exception as e:
        print(f"错误(crop_image_to_circle): {e}")
        return None


def check_dependencies_availability():
    dependencies = {
        "Pillow": PILLOW_AVAILABLE,
        "google.generativeai": False,
        "paddleocr_lib_present": False,
        "google-cloud-vision_lib_present": False,
        "openai_lib": False
    }
    try:
        import google.generativeai
        dependencies["google.generativeai"] = True
    except ImportError: pass
    try:
        import paddleocr
        dependencies["paddleocr_lib_present"] = True
    except ImportError: pass
    try:
        import google.cloud.vision
        dependencies["google-cloud-vision_lib_present"] = True
    except ImportError: pass
    try:
        import openai
        dependencies["openai_lib"] = True
    except ImportError: pass
    return dependencies


def is_sentence_end(text: str) -> bool:
    text = text.strip()
    if not text: return False
    end_chars = ('。', '、', '！', '？', '.', '!', '?') # Chinese/Japanese/English punctuation
    closing_brackets = ('」', '』', '）', ')', '】', ']', '"', "'") # Closing brackets

    last_char = ''
    for char_val in reversed(text): # Find the last non-space character
        if not char_val.isspace():
            last_char = char_val
            break
    if not last_char: return False # Should not happen if text.strip() is not empty

    # Case 1: Ends with a standard punctuation mark
    if last_char in end_chars:
        return True

    # Case 2: Ends with a closing bracket, check character before it
    if last_char in closing_brackets:
        if len(text) > 1: # Need at least one char before the bracket
            # Remove the last char (bracket) and any trailing spaces before it
            temp_text = text
            while temp_text.endswith(last_char) or temp_text.endswith(' '):
                if temp_text.endswith(last_char):
                    temp_text = temp_text[:-len(last_char)]
                else: # ends with space
                    temp_text = temp_text[:-1]
            
            second_last_char = ''
            if temp_text:
                for char_val_inner in reversed(temp_text):
                    if not char_val_inner.isspace():
                        second_last_char = char_val_inner
                        break
                if second_last_char in end_chars:
                    return True
    return False


def check_horizontal_proximity(box1_data, box2_data, max_vertical_diff_ratio=0.6, max_horizontal_gap_ratio=1.5, min_overlap_ratio=-0.2):
    # Ensure 'bbox' key exists and is valid
    if 'bbox' not in box1_data or 'bbox' not in box2_data: return False
    box1 = box1_data['bbox']
    box2 = box2_data['bbox']

    if not (box1 and box2 and len(box1) == 4 and len(box2) == 4): return False

    b1_x0, b1_y0, b1_x1, b1_y1 = box1
    b2_x0, b2_y0, b2_x1, b2_y1 = box2

    # Basic check: if box1 is entirely to the right of box2, they are not in left-to-right sequence
    # This check assumes box1 is supposed to be to the left of box2
    if b1_x0 > b2_x0 and b1_x1 > b2_x1 and b1_x0 > b2_x1 : # box1 is completely to the right of box2
        return False # Not suitable for merging as box1 then box2

    h1 = b1_y1 - b1_y0; h2 = b2_y1 - b2_y0
    if h1 <= 0 or h2 <=0: return False # Invalid box height

    center1_y = (b1_y0 + b1_y1) / 2
    center2_y = (b2_y0 + b2_y1) / 2
    avg_h = (h1 + h2) / 2
    if avg_h <= 0: return False # Avoid division by zero if heights are problematic

    vertical_diff = abs(center1_y - center2_y)
    if vertical_diff > avg_h * max_vertical_diff_ratio:
        return False # Too far apart vertically

    # Horizontal gap/overlap logic
    # Box1 is to the left of Box2 (or they overlap)
    if b1_x1 <= b2_x0: # Box1 is strictly to the left of Box2 (gap)
        horizontal_gap = b2_x0 - b1_x1
        if horizontal_gap > avg_h * max_horizontal_gap_ratio: # Gap is too large
            return False
    else: # Boxes overlap horizontally, or Box2 is to the left of Box1 (which we might want to penalize)
        # If Box2 starts before Box1, it's not a simple left-to-right merge for box1 THEN box2
        if b2_x0 < b1_x0:
            # How much is box2 to the left of box1's start?
            # If box2 significantly preceeds box1, it's not a good candidate for "box1 + box2"
            if b1_x0 - b2_x0 > avg_h * 0.5 : # Box2 starts significantly before Box1
                return False
        # Overlap calculation (positive if overlap, negative if gap)
        # overlap_x = min(b1_x1, b2_x1) - max(b1_x0, b2_x0)
        # min_overlap_pixels = avg_h * min_overlap_ratio
        # if overlap_x < min_overlap_pixels: # Not enough overlap, or too much of a "reverse" gap
        #     return False
    return True


def process_ocr_results_merge_lines(ocr_output_raw_segments: list, lang_hint='ja'):
    if not ocr_output_raw_segments or not isinstance(ocr_output_raw_segments, list):
        return []

    raw_blocks = []
    try:
        for i, item_data in enumerate(ocr_output_raw_segments):
            if not isinstance(item_data, (list, tuple)) or len(item_data) != 2:
                # print(f"Skipping invalid item_data: {item_data}")
                continue

            box_info_raw = item_data[0]
            text_info_raw = item_data[1]
            text_content_str = ""

            # Extract text content
            if isinstance(text_info_raw, tuple) and len(text_info_raw) >= 1 and isinstance(text_info_raw[0], str):
                text_content_str = text_info_raw[0].strip()
            elif isinstance(text_info_raw, list) and len(text_info_raw) >= 1 and isinstance(text_info_raw[0], str): # PaddleOCR format
                text_content_str = text_info_raw[0].strip()
            elif isinstance(text_info_raw, str): # Simpler format
                text_content_str = text_info_raw.strip()
            else:
                # print(f"Skipping item due to unhandled text_info_raw: {text_info_raw}")
                continue
            
            if not text_content_str: # Skip if text is empty after stripping
                continue

            # Parse bounding box vertices
            vertices_parsed = []
            if isinstance(box_info_raw, list) and len(box_info_raw) == 4: # List of 4 points
                valid_points = True
                for p_idx, p in enumerate(box_info_raw):
                    if isinstance(p, (list, tuple)) and len(p) == 2:
                        try:
                            vertices_parsed.append((int(round(float(p[0]))), int(round(float(p[1])))))
                        except (ValueError, TypeError):
                            valid_points = False; break
                    else:
                        valid_points = False; break
                if not valid_points:
                    # print(f"Skipping item due to invalid points in box_info_raw (list of 4): {box_info_raw}")
                    vertices_parsed = [] # Reset if any point was invalid
            # Handle flat list of 8 coordinates (e.g., [x1,y1,x2,y2,x3,y3,x4,y4])
            elif isinstance(box_info_raw, list) and len(box_info_raw) == 8:
                try:
                    temp_v = []
                    for k in range(0, 8, 2):
                        temp_v.append( (int(round(float(box_info_raw[k]))), int(round(float(box_info_raw[k+1]))) ) )
                    if len(temp_v) == 4:
                        vertices_parsed = temp_v
                    else: # Should not happen if len is 8 and loop is correct
                        vertices_parsed = []
                except (ValueError, TypeError):
                    # print(f"Skipping item due to invalid values in box_info_raw (list of 8): {box_info_raw}")
                    vertices_parsed = [] 
            else: # Unhandled box format
                # print(f"Skipping item due to unhandled box_info_raw format: {box_info_raw}")
                vertices_parsed = []


            if not vertices_parsed: # If parsing failed or format was wrong
                continue

            # Create a rectangular bounding box [x_min, y_min, x_max, y_max] from vertices
            x_coords_list = [v[0] for v in vertices_parsed]
            y_coords_list = [v[1] for v in vertices_parsed]
            bbox_rect = [min(x_coords_list), min(y_coords_list), max(x_coords_list), max(y_coords_list)]

            # Ensure the bounding box has a positive area
            if not (bbox_rect[2] > bbox_rect[0] and bbox_rect[3] > bbox_rect[1]):
                # print(f"Skipping item due to invalid bbox_rect (zero or negative area): {bbox_rect}")
                continue

            raw_blocks.append({'id': i, 'text': text_content_str, 'bbox': bbox_rect, 'vertices': vertices_parsed})

    except Exception as e:
        print(f"错误(process_ocr_results_merge_lines) - initial parsing: {e}")
        return []

    if not raw_blocks:
        return []

    # Sort blocks primarily by top-y coordinate, then by left-x coordinate for stable ordering
    raw_blocks.sort(key=lambda b: (b['bbox'][1], b['bbox'][0]))

    merged_results = []
    processed_block_ids = set() # To keep track of blocks already merged into a line

    for i in range(len(raw_blocks)):
        if raw_blocks[i]['id'] in processed_block_ids:
            continue # Skip if this block has already been processed as part of a previous line

        current_block_data = raw_blocks[i]
        current_text_line = current_block_data['text']
        # For merged lines, the "vertices" become less meaningful if boxes are not perfectly aligned.
        # We can either take the vertices of the first block, or try to compute a combined bounding polygon.
        # For simplicity, let's start with the first block's vertices.
        # A more robust approach would be to store all involved original bboxes or compute a convex hull.
        current_line_vertices = list(current_block_data['vertices']) # Use a copy
        current_line_bbox = list(current_block_data['bbox']) # Overall bbox for the merged line

        last_merged_block_in_this_line = current_block_data # Keep track of the last block added to the current line
        processed_block_ids.add(current_block_data['id'])

        # Try to merge subsequent blocks
        for j in range(i + 1, len(raw_blocks)):
            next_block_candidate_data = raw_blocks[j]
            if next_block_candidate_data['id'] in processed_block_ids:
                continue # Skip if already processed

            should_merge_flag = False
            # Only try to merge if the current line doesn't look like it ended
            if not is_sentence_end(current_text_line):
                # Check proximity with the *last* block added to the current line
                if check_horizontal_proximity(last_merged_block_in_this_line, next_block_candidate_data):
                    should_merge_flag = True
            
            if should_merge_flag:
                joiner = ""
                # Add a space for non-CJK languages if needed
                if lang_hint not in ['ja', 'zh', 'ko', 'jpn', 'chi_sim', 'kor', 'chinese_sim']: # Added 'chinese_sim'
                    if current_text_line and next_block_candidate_data['text']: # Both have text
                        # Simple check: don't add space if current ends with hyphen, or next starts with punctuation
                        if not current_text_line.endswith(('-', '=', '#')) and \
                           not next_block_candidate_data['text'][0] in ('.', ',', '!', '?', ':', ';'):
                            joiner = " "
                
                current_text_line += joiner + next_block_candidate_data['text']
                
                # Update the overall bounding box for the merged line
                next_bbox = next_block_candidate_data['bbox']
                current_line_bbox[0] = min(current_line_bbox[0], next_bbox[0])
                current_line_bbox[1] = min(current_line_bbox[1], next_bbox[1])
                current_line_bbox[2] = max(current_line_bbox[2], next_bbox[2])
                current_line_bbox[3] = max(current_line_bbox[3], next_bbox[3])
                # For simplicity, we are not updating current_line_vertices for merged blocks here.
                # If precise merged vertices are needed, a convex hull of all involved vertices would be better.

                last_merged_block_in_this_line = next_block_candidate_data # Update the last merged block
                processed_block_ids.add(next_block_candidate_data['id'])
            else:
                # If this block cannot be merged, subsequent blocks (which are sorted further down/right)
                # are unlikely to merge with the current line either.
                break 
        
        # For the merged result, use the combined text and the overall bounding box.
        # The 'vertices' will be from the first block of the line or a calculated hull if implemented.
        # Here, we are just passing the text and the first block's vertices.
        # It might be better to pass the calculated `current_line_bbox` instead of `current_line_vertices`
        # or alongside it, if the `ProcessedBlock` can store both.
        # Let's assume the calling code (ImageProcessor) will use the bbox.
        # The tuple format is (text, vertices_of_first_block_or_bbox_of_merged_line)
        # Let's return (merged_text, current_line_bbox) as the bbox is more representative.
        merged_results.append((current_text_line, current_line_bbox)) # Changed to current_line_bbox

    return merged_results


def _render_single_block_pil_for_preview(
    block: 'ProcessedBlock', # Forward reference for type hint
    font_name_config: str,
    text_main_color_pil: tuple,
    text_outline_color_pil: tuple,
    text_bg_color_pil: tuple,
    outline_thickness: int,
    text_padding: int,
    h_char_spacing_px: int,
    h_line_spacing_px: int,
    v_char_spacing_px: int, # This is char spacing WITHIN a vertical column
    v_col_spacing_px: int,  # This is spacing BETWEEN vertical columns
    h_manual_break_extra_px: int = 0,
    v_manual_break_extra_px: int = 0,
) -> Image.Image | None:
    """
    Renders a single ProcessedBlock to a new, UNROTATED Pillow Image.
    The size of this image is now determined by block.bbox.
    The text background (if enabled) will fill this bbox area (minus internal padding for text placement).
    The block's angle is NOT applied here; rotation is handled by QPainter.
    """
    if not PILLOW_AVAILABLE or not block.translated_text or not block.translated_text.strip():
        # Return a transparent image matching bbox size if no text, but bbox exists
        if PILLOW_AVAILABLE and block.bbox:
            bbox_width = int(block.bbox[2] - block.bbox[0])
            bbox_height = int(block.bbox[3] - block.bbox[1])
            if bbox_width > 0 and bbox_height > 0:
                empty_surface = Image.new('RGBA', (bbox_width, bbox_height), (0, 0, 0, 0))
                # Optionally draw the background color if specified, even for empty text
                if text_bg_color_pil and len(text_bg_color_pil) == 4 and text_bg_color_pil[3] > 0:
                    draw = ImageDraw.Draw(empty_surface)
                    draw.rectangle([(0,0), (bbox_width-1, bbox_height-1)], fill=text_bg_color_pil)
                return empty_surface
        return None


    font_size_to_use = int(block.font_size_pixels)
    pil_font = get_pil_font(font_name_config, font_size_to_use)
    if not pil_font:
        print(f"警告(_render_single_block_pil_for_preview): 无法加载字体 '{font_name_config}' (大小: {font_size_to_use}px)")
        # Fallback: create an image matching bbox with error text if possible
        bbox_width_err = int(block.bbox[2] - block.bbox[0]) if block.bbox else 100
        bbox_height_err = int(block.bbox[3] - block.bbox[1]) if block.bbox else 50
        err_img = Image.new("RGBA", (max(1,bbox_width_err), max(1,bbox_height_err)), (255,0,0,100))
        ImageDraw.Draw(err_img).text((5,5), "字体错误", font=ImageFont.load_default(), fill=(255,255,255,255))
        return err_img


    text_to_draw = block.translated_text
    
    dummy_metric_img = Image.new('RGBA', (1, 1))
    pil_draw_metric = ImageDraw.Draw(dummy_metric_img)

    wrapped_segments: list[str]
    actual_text_render_width_unpadded: int # Width of text content itself
    actual_text_render_height_unpadded: int # Height of text content itself
    segment_secondary_dim_with_spacing: int 

    # --- Determine the size of the final image surface based on block.bbox ---
    # This is the crucial change: the canvas for drawing is now bbox-sized.
    target_surface_width = int(block.bbox[2] - block.bbox[0])
    target_surface_height = int(block.bbox[3] - block.bbox[1])

    if target_surface_width <= 0 or target_surface_height <= 0:
        print(f"警告(_render_single_block_pil_for_preview): block.bbox '{block.bbox}' 尺寸无效。")
        # Create a small placeholder with error text
        err_img_bbox = Image.new("RGBA", (100, 50), (255,0,0,100))
        ImageDraw.Draw(err_img_bbox).text((5,5), "BBox错误", font=ImageFont.load_default(), fill=(255,255,255,255))
        return err_img_bbox

    # The area available for text content *inside* the bbox, after accounting for text_padding on all sides
    max_content_width_for_wrapping = target_surface_width - (2 * text_padding)
    max_content_height_for_wrapping = target_surface_height - (2 * text_padding)

    if max_content_width_for_wrapping <=0 or max_content_height_for_wrapping <=0:
        # Padding is too large for the bbox, cannot render text.
        # Return an image of bbox size with background color only.
        block_surface_nopad = Image.new('RGBA', (target_surface_width, target_surface_height), (0, 0, 0, 0))
        draw_nopad = ImageDraw.Draw(block_surface_nopad)
        if text_bg_color_pil and len(text_bg_color_pil) == 4 and text_bg_color_pil[3] > 0:
            draw_nopad.rectangle([(0, 0), (target_surface_width -1 , target_surface_height -1)], fill=text_bg_color_pil)
        return block_surface_nopad

    # --- Text wrapping and metrics calculation (similar to before, but using max_content_width/height) ---
    if block.orientation == "horizontal":
        wrap_dim_for_pil = max(1, int(max_content_width_for_wrapping))
        wrapped_segments, initial_total_height, seg_secondary_dim_with_spacing, actual_text_render_width_unpadded = wrap_text_pil(
            pil_draw_metric, text_to_draw, pil_font,
            max_dim=wrap_dim_for_pil,
            orientation="horizontal",
            char_spacing_px=h_char_spacing_px,
            line_or_col_spacing_px=h_line_spacing_px
        )
        actual_text_render_height_unpadded = 0
        if wrapped_segments:
            for seg_text in wrapped_segments:
                actual_text_render_height_unpadded += seg_secondary_dim_with_spacing
                if seg_text == "": actual_text_render_height_unpadded += h_manual_break_extra_px
        elif text_to_draw:
             actual_text_render_height_unpadded = seg_secondary_dim_with_spacing if seg_secondary_dim_with_spacing > 0 else get_font_line_height(pil_font, font_size_to_use, h_line_spacing_px)
             actual_text_render_width_unpadded = pil_draw_metric.textlength(text_to_draw, font=pil_font) + \
                                                 (h_char_spacing_px * (len(text_to_draw) -1) if len(text_to_draw)>1 else 0)
    else:  # Vertical
        wrap_dim_for_pil = max(1, int(max_content_height_for_wrapping))
        wrapped_segments, initial_total_width, seg_secondary_dim_with_spacing, actual_text_render_height_unpadded = wrap_text_pil(
            pil_draw_metric, text_to_draw, pil_font,
            max_dim=wrap_dim_for_pil,
            orientation="vertical",
            char_spacing_px=v_char_spacing_px,
            line_or_col_spacing_px=0 
        )
        actual_text_render_width_unpadded = 0
        if wrapped_segments:
            try:
                single_col_visual_width_metric = pil_font.getlength("M") 
                if single_col_visual_width_metric == 0: single_col_visual_width_metric = pil_font.size if hasattr(pil_font, 'size') else font_size_to_use
            except AttributeError: single_col_visual_width_metric = pil_font.size if hasattr(pil_font, 'size') else font_size_to_use

            num_cols_pil = len(wrapped_segments)
            for seg_idx, seg_text in enumerate(wrapped_segments):
                actual_text_render_width_unpadded += single_col_visual_width_metric
                if seg_idx < num_cols_pil - 1:
                    actual_text_render_width_unpadded += v_col_spacing_px
                    if seg_text == "": actual_text_render_width_unpadded += v_manual_break_extra_px
        elif text_to_draw:
            try: single_col_visual_width_metric = pil_font.getlength("M")
            except: single_col_visual_width_metric = font_size_to_use
            actual_text_render_width_unpadded = single_col_visual_width_metric
            actual_text_render_height_unpadded = (seg_secondary_dim_with_spacing if seg_secondary_dim_with_spacing > 0 else get_font_line_height(pil_font, font_size_to_use, v_char_spacing_px)) * len(text_to_draw)


    if not wrapped_segments and text_to_draw: # Fallback if wrap_text_pil returns empty
        wrapped_segments = [text_to_draw]
        # ... (rest of this fallback logic as before, ensuring actual_text_render_width/height_unpadded are set) ...
        if block.orientation == "horizontal":
            if actual_text_render_width_unpadded <=0:
                 actual_text_render_width_unpadded = pil_draw_metric.textlength(text_to_draw, font=pil_font) + \
                                                     (h_char_spacing_px * (len(text_to_draw)-1) if len(text_to_draw) > 1 else 0)
            if actual_text_render_height_unpadded <=0:
                 actual_text_render_height_unpadded = get_font_line_height(pil_font, font_size_to_use, h_line_spacing_px)
            seg_secondary_dim_with_spacing = actual_text_render_height_unpadded
        else: # Vertical
            if actual_text_render_width_unpadded <=0:
                try: actual_text_render_width_unpadded = pil_font.getlength("M")
                except: actual_text_render_width_unpadded = font_size_to_use
            if actual_text_render_height_unpadded <=0:
                 actual_text_render_height_unpadded = (get_font_line_height(pil_font, font_size_to_use, v_char_spacing_px)) * len(text_to_draw)
            seg_secondary_dim_with_spacing = get_font_line_height(pil_font, font_size_to_use, v_char_spacing_px)


    if not wrapped_segments or actual_text_render_width_unpadded <= 0 or actual_text_render_height_unpadded <= 0:
        if text_to_draw:
            print(f"警告(_render_single_block_pil_for_preview): 文本 '{text_to_draw[:20]}...' 的渲染尺寸为零或负（BBox阶段）。")
            # Create image matching bbox with error text
            err_img_dim = Image.new("RGBA", (target_surface_width, target_surface_height), (255,0,0,100))
            ImageDraw.Draw(err_img_dim).text((text_padding,text_padding), "渲染尺寸错误", font=ImageFont.load_default(), fill=(255,255,255,255))
            return err_img_dim
        # If no text to draw, surface has already been created at the top or will be.
        # For safety, ensure a surface is returned if execution reaches here with no text.
        empty_surface_fallback = Image.new('RGBA', (target_surface_width, target_surface_height), (0,0,0,0))
        if text_bg_color_pil and len(text_bg_color_pil) == 4 and text_bg_color_pil[3] > 0:
            ImageDraw.Draw(empty_surface_fallback).rectangle([(0,0),(target_surface_width-1, target_surface_height-1)], fill=text_bg_color_pil)
        return empty_surface_fallback


    # --- Create the surface based on bbox dimensions ---
    block_surface = Image.new('RGBA', (target_surface_width, target_surface_height), (0, 0, 0, 0)) # Transparent
    draw_on_block_surface = ImageDraw.Draw(block_surface)

    # 1. Draw text background (if any) - this now fills the entire block_surface
    if text_bg_color_pil and len(text_bg_color_pil) == 4 and text_bg_color_pil[3] > 0:
        draw_on_block_surface.rectangle([(0, 0), (target_surface_width -1 , target_surface_height -1)], fill=text_bg_color_pil)

    # 2. Draw text (outline then main)
    #    Text needs to be positioned *within* the target_surface_width/height,
    #    respecting text_padding and block.text_align.
    
    # Calculate top-left (x,y) for the *content area* where text will be drawn, after padding.
    content_area_x_start = text_padding
    content_area_y_start = text_padding
    
    # Available width/height for the text content itself *within* the padded area.
    # This is max_content_width_for_wrapping and max_content_height_for_wrapping computed earlier.

    # Calculate the starting position for the first line/column of text based on overall text_align
    # This positions the *block* of text lines/columns within the content_area.
    
    text_block_start_x = content_area_x_start
    text_block_start_y = content_area_y_start

    if block.orientation == "horizontal":
        if block.text_align == "center":
            text_block_start_x = content_area_x_start + (max_content_width_for_wrapping - actual_text_render_width_unpadded) / 2.0
        elif block.text_align == "right":
            text_block_start_x = content_area_x_start + max_content_width_for_wrapping - actual_text_render_width_unpadded
        # For vertical alignment of the whole text block within the available height:
        # (Could add a vertical_align property to ProcessedBlock if needed)
        # Defaulting to top-aligning the text block within the content area's height
        # text_block_start_y = content_area_y_start + (max_content_height_for_wrapping - actual_text_render_height_unpadded) / 2.0 # for vertical center
    else: # Vertical
        if block.text_align == "center": # Center the columns block horizontally
            text_block_start_x = content_area_x_start + (max_content_width_for_wrapping - actual_text_render_width_unpadded) / 2.0
        elif block.text_align == "right": # Align columns block to the right of content area
            text_block_start_x = content_area_x_start + max_content_width_for_wrapping - actual_text_render_width_unpadded
        # For vertical alignment of text within each column:
        # (This is more complex; for now, assume text in columns is top-aligned within column's max_content_height_for_wrapping)
        # To vertically center the *entire block* of columns:
        # text_block_start_y = content_area_y_start + (max_content_height_for_wrapping - actual_text_render_height_unpadded) / 2.0


    # --- Drawing loop for text segments (lines or columns) ---
    # This part is largely the same, but `line_draw_x_pil` (for horizontal)
    # and `current_x_pil_col_start_abs` (for vertical) are now relative to `text_block_start_x`.
    # And `current_y_pil` and `current_y_pil_char` are relative to `text_block_start_y`.

    if block.orientation == "horizontal":
        current_y_pil = text_block_start_y # Initial Y for the first line, within the text block
        for line_idx, line_text in enumerate(wrapped_segments):
            is_manual_break_line = (line_text == "")
            if not is_manual_break_line:
                line_w_specific_pil = pil_draw_metric.textlength(line_text, font=pil_font)
                if len(line_text) > 1 and h_char_spacing_px != 0:
                    line_w_specific_pil += h_char_spacing_px * (len(line_text) - 1)

                # X position of *this line* relative to the text_block_start_x
                # This handles alignment of individual lines if actual_text_render_width_unpadded
                # was based on the longest line, and other lines are shorter.
                # However, wrap_text_pil now gives actual_text_render_width_unpadded as the max achieved.
                # So, for horizontal, if alignment is left, lines start at text_block_start_x.
                # If center/right, alignment is based on actual_text_render_width_unpadded (max line width).
                
                line_offset_x_within_block = 0
                if block.text_align == "center":
                     # Align line relative to the overall text block width, not the smaller content_area_width
                    line_offset_x_within_block = (actual_text_render_width_unpadded - line_w_specific_pil) / 2.0
                elif block.text_align == "right":
                    line_offset_x_within_block = actual_text_render_width_unpadded - line_w_specific_pil
                
                line_draw_x_pil = text_block_start_x + line_offset_x_within_block
                
                # Draw outline
                if outline_thickness > 0 and text_outline_color_pil and len(text_outline_color_pil) == 4 and text_outline_color_pil[3] > 0:
                    for dx_o in range(-outline_thickness, outline_thickness + 1):
                        for dy_o in range(-outline_thickness, outline_thickness + 1):
                            if dx_o == 0 and dy_o == 0: continue
                            if h_char_spacing_px != 0:
                                temp_x_char_outline = line_draw_x_pil + dx_o
                                for char_ol in line_text:
                                    draw_on_block_surface.text((temp_x_char_outline, current_y_pil + dy_o), char_ol, font=pil_font, fill=text_outline_color_pil)
                                    temp_x_char_outline += pil_draw_metric.textlength(char_ol, font=pil_font) + h_char_spacing_px
                            else:
                                draw_on_block_surface.text((line_draw_x_pil + dx_o, current_y_pil + dy_o), line_text, font=pil_font, fill=text_outline_color_pil, spacing=0)
                # Draw main text
                if h_char_spacing_px != 0:
                    temp_x_char_main = line_draw_x_pil
                    for char_m in line_text:
                        draw_on_block_surface.text((temp_x_char_main, current_y_pil), char_m, font=pil_font, fill=text_main_color_pil)
                        temp_x_char_main += pil_draw_metric.textlength(char_m, font=pil_font) + h_char_spacing_px
                else:
                    draw_on_block_surface.text((line_draw_x_pil, current_y_pil), line_text, font=pil_font, fill=text_main_color_pil, spacing=0)
            
            current_y_pil += seg_secondary_dim_with_spacing 
            if is_manual_break_line:
                current_y_pil += h_manual_break_extra_px
    
    else:  # Vertical
        try:
            single_col_visual_width_metric = pil_font.getlength("M")
            if single_col_visual_width_metric == 0: single_col_visual_width_metric = pil_font.size if hasattr(pil_font, 'size') else font_size_to_use
        except AttributeError:
            single_col_visual_width_metric = pil_font.size if hasattr(pil_font, 'size') else font_size_to_use

        # text_block_start_x is already set according to overall horizontal alignment of columns block.
        # Now determine the starting X for the first column based on LTR/RTL within that block.
        current_x_pil_col_start_abs = text_block_start_x
        if block.orientation == "vertical_rtl":
            # actual_text_render_width_unpadded is total width of all columns
            # single_col_visual_width_metric is width of one column's content
            current_x_pil_col_start_abs = text_block_start_x + actual_text_render_width_unpadded - single_col_visual_width_metric

        for col_idx, col_text in enumerate(wrapped_segments):
            is_manual_break_col = (col_text == "")
            # Initial Y for characters in this column, relative to the text_block_start_y
            current_y_pil_char = text_block_start_y 
            
            # Vertical alignment of current column's content within available vertical space (max_content_height_for_wrapping)
            # This could be "top", "center", "bottom" for how the text within *this column* aligns vertically.
            # Let's use block.text_align to control this for vertical text.
            # "left" (default for vertical) -> top of column
            # "center" -> center of column
            # "right" -> bottom of column
            
            this_col_content_actual_height = 0
            if not is_manual_break_col:
                this_col_content_actual_height = len(col_text) * seg_secondary_dim_with_spacing
                # Note: v_char_spacing_px is already in seg_secondary_dim_with_spacing

            col_vert_offset = 0
            if block.text_align == "center": # Center this column's text vertically within max_content_height_for_wrapping
                col_vert_offset = (max_content_height_for_wrapping - this_col_content_actual_height) / 2.0
            elif block.text_align == "right": # Align this column's text to bottom within max_content_height_for_wrapping
                col_vert_offset = max_content_height_for_wrapping - this_col_content_actual_height
            current_y_pil_char += col_vert_offset


            if not is_manual_break_col:
                for char_in_col_idx, char_in_col in enumerate(col_text):
                    char_w_specific_pil = pil_draw_metric.textlength(char_in_col, font=pil_font)
                    
                    # Horizontal alignment of individual character within its column slot (single_col_visual_width_metric)
                    # Let's simplify: for vertical, text_align (left/center/right) applied to columns vertically.
                    # The horizontal position of char within column slot is usually centered or font-default.
                    # For now, assume characters are drawn starting at current_x_pil_col_start_abs (left of slot).
                    # Or, to center char in its slot:
                    char_x_offset_in_col_slot = (single_col_visual_width_metric - char_w_specific_pil) / 2.0
                    final_char_draw_x = current_x_pil_col_start_abs + char_x_offset_in_col_slot

                    if outline_thickness > 0 and text_outline_color_pil and len(text_outline_color_pil) == 4 and text_outline_color_pil[3] > 0:
                        for dx_o in range(-outline_thickness, outline_thickness + 1):
                            for dy_o in range(-outline_thickness, outline_thickness + 1):
                                if dx_o == 0 and dy_o == 0: continue
                                draw_on_block_surface.text((final_char_draw_x + dx_o, current_y_pil_char + dy_o), char_in_col, font=pil_font, fill=text_outline_color_pil)
                    draw_on_block_surface.text((final_char_draw_x, current_y_pil_char), char_in_col, font=pil_font, fill=text_main_color_pil)
                    
                    current_y_pil_char += seg_secondary_dim_with_spacing
            
            if col_idx < len(wrapped_segments) - 1:
                spacing_to_next_col = single_col_visual_width_metric + v_col_spacing_px
                if is_manual_break_col:
                    spacing_to_next_col += v_manual_break_extra_px
                
                if block.orientation == "vertical_rtl":
                    current_x_pil_col_start_abs -= spacing_to_next_col
                else: # vertical_ltr
                    current_x_pil_col_start_abs += spacing_to_next_col
    
    return block_surface


def _draw_single_block_pil(
    draw_target_image: Image.Image, # This is the main image to draw ONTO
    block: 'ProcessedBlock', 
    font_name_config: str,
    text_main_color_pil: tuple,
    text_outline_color_pil: tuple,
    text_bg_color_pil: tuple,
    outline_thickness: int,
    text_padding: int,
    h_char_spacing_px: int,
    h_line_spacing_px: int,
    v_char_spacing_px: int,
    v_col_spacing_px: int,
    h_manual_break_extra_px: int = 0,
    v_manual_break_extra_px: int = 0
) -> None:
    """
    Draws a single processed block onto the draw_target_image.
    This version now USES _render_single_block_pil_for_preview to get the block's visual content.
    """
    if not PILLOW_AVAILABLE or not block.translated_text or not block.translated_text.strip():
        return

    # 1. Render the block's content to a separate, unrotated PIL Image
    rendered_block_content_pil = _render_single_block_pil_for_preview(
        block=block,
        font_name_config=font_name_config,
        text_main_color_pil=text_main_color_pil,
        text_outline_color_pil=text_outline_color_pil,
        text_bg_color_pil=text_bg_color_pil,
        outline_thickness=outline_thickness,
        text_padding=text_padding,
        h_char_spacing_px=h_char_spacing_px,
        h_line_spacing_px=h_line_spacing_px,
        v_char_spacing_px=v_char_spacing_px,
        v_col_spacing_px=v_col_spacing_px,
        h_manual_break_extra_px=h_manual_break_extra_px,
        v_manual_break_extra_px=v_manual_break_extra_px
    )

    if not rendered_block_content_pil:
        # print(f"Warning (_draw_single_block_pil): Failed to render block content for '{block.translated_text[:20]}...'")
        return

    # 2. Rotate this rendered_block_content_pil if block.angle is not 0
    final_surface_to_paste = rendered_block_content_pil
    if block.angle != 0:
        # Expand is true to make sure the rotated image is not cropped.
        # The background of newly exposed areas after rotation will be transparent
        # because rendered_block_content_pil is RGBA with transparent bg.
        try:
            final_surface_to_paste = rendered_block_content_pil.rotate(
                -block.angle, # Pillow rotates counter-clockwise for positive angles
                expand=True, 
                resample=Image.Resampling.BICUBIC # Good quality for rotation
            )
        except Exception as e:
            print(f"Error rotating block content: {e}")
            # Fallback to unrotated if rotation fails
            final_surface_to_paste = rendered_block_content_pil


    # 3. Calculate paste position on draw_target_image
    # The block.bbox defines the original unrotated rectangle in the target image's coordinates.
    # We want to paste the (potentially rotated) content centered at the center of this original bbox.
    
    block_center_x_orig_coords = (block.bbox[0] + block.bbox[2]) / 2.0
    block_center_y_orig_coords = (block.bbox[1] + block.bbox[3]) / 2.0

    # The final_surface_to_paste has its own width and height.
    # Its top-left corner should be placed such that its center aligns with (block_center_x_orig_coords, block_center_y_orig_coords).
    paste_x = int(round(block_center_x_orig_coords - (final_surface_to_paste.width / 2.0)))
    paste_y = int(round(block_center_y_orig_coords - (final_surface_to_paste.height / 2.0)))

    # 4. Composite onto draw_target_image
    # Ensure draw_target_image is RGBA for alpha compositing
    if draw_target_image.mode != 'RGBA':
        # This should ideally be handled by the caller (draw_processed_blocks_pil) once.
        # However, to be safe:
        try:
            draw_target_image = draw_target_image.convert('RGBA') # This creates a copy if mode changes
        except Exception as e:
            print(f"Error converting draw_target_image to RGBA: {e}")
            return # Cannot proceed if conversion fails

    # Use alpha_composite for proper transparency handling.
    # The final_surface_to_paste is RGBA.
    try:
        # Pillow's paste with a mask derived from alpha channel is often more robust
        # than alpha_composite for some use cases, but alpha_composite is designed for this.
        # If final_surface_to_paste has an alpha channel, it's used as the mask.
        if final_surface_to_paste.mode == 'RGBA':
             # Create a temporary image if draw_target_image is not RGBA,
             # or ensure it's RGBA before this function.
             # Assuming draw_target_image is already RGBA by now.
            draw_target_image.alpha_composite(final_surface_to_paste, (paste_x, paste_y))
        else: # Should not happen if _render_single_block_pil_for_preview returns RGBA
            draw_target_image.paste(final_surface_to_paste, (paste_x, paste_y))

    except Exception as e:
        print(f"Error compositing block '{block.translated_text[:20]}...' onto target image: {e}")
        # Attempt a simpler paste if alpha_composite fails (less ideal for transparency)
        try:
            if final_surface_to_paste.mode == 'RGBA':
                draw_target_image.paste(final_surface_to_paste, (paste_x, paste_y), mask=final_surface_to_paste)
            else:
                draw_target_image.paste(final_surface_to_paste, (paste_x, paste_y))
        except Exception as e_paste:
            print(f"Fallback paste also failed for block: {e_paste}")


def draw_processed_blocks_pil(pil_image_original: Image.Image, processed_blocks: list, config_manager: ConfigManager) -> Image.Image | None:
    if not PILLOW_AVAILABLE or not pil_image_original or not processed_blocks:
        return pil_image_original # Return original if no processing needed or possible

    try:
        if pil_image_original.mode != 'RGBA':
            base_image = pil_image_original.convert('RGBA')
        else:
            base_image = pil_image_original.copy() # Work on a copy

        # Load all configuration settings needed by _draw_single_block_pil
        font_name_conf = config_manager.get('UI', 'font_name', 'msyh.ttc')
        text_pad_conf = config_manager.getint('UI', 'text_padding', 3)

        main_color_str = config_manager.get('UI', 'text_main_color', '255,255,255,255')
        outline_color_str = config_manager.get('UI', 'text_outline_color', '0,0,0,255')
        outline_thick_conf = config_manager.getint('UI', 'text_outline_thickness', 2)
        bg_color_str = config_manager.get('UI', 'text_background_color', '0,0,0,128')

        h_char_spacing_conf = config_manager.getint('UI', 'h_text_char_spacing_px', 0)
        h_line_spacing_conf = config_manager.getint('UI', 'h_text_line_spacing_px', 0)
        v_char_spacing_conf = config_manager.getint('UI', 'v_text_char_spacing_px', 0)
        v_col_spacing_conf = config_manager.getint('UI', 'v_text_column_spacing_px', 0)
        
        h_manual_break_extra_conf = config_manager.getint('UI', 'h_manual_break_extra_spacing_px', 0)
        v_manual_break_extra_conf = config_manager.getint('UI', 'v_manual_break_extra_spacing_px', 0)

        # Parse colors
        try:
            mc_parts = list(map(int, main_color_str.split(',')))
            oc_parts = list(map(int, outline_color_str.split(',')))
            bc_parts = list(map(int, bg_color_str.split(',')))
            main_color_pil = tuple(mc_parts) if len(mc_parts) in [3,4] else (255,255,255,255)
            outline_color_pil = tuple(oc_parts) if len(oc_parts) in [3,4] else (0,0,0,255)
            bg_color_pil = tuple(bc_parts) if len(bc_parts) in [3,4] else (0,0,0,128)
            # Ensure 4 components (RGBA)
            if len(main_color_pil) == 3: main_color_pil += (255,)
            if len(outline_color_pil) == 3: outline_color_pil += (255,)
            if len(bg_color_pil) == 3: bg_color_pil += (128,) # Default alpha for bg if not specified
        except ValueError: # Fallback to defaults if parsing fails
            main_color_pil=(255,255,255,255); outline_color_pil=(0,0,0,255); bg_color_pil=(0,0,0,128)

        for idx, block_item in enumerate(processed_blocks): 
            # Basic validation of block_item
            if not hasattr(block_item, 'translated_text') or not block_item.translated_text or not block_item.translated_text.strip():
                continue
            if not hasattr(block_item, 'font_size_pixels') or not hasattr(block_item, 'bbox'):
                print(f"Skipping block {idx} due to missing attributes (font_size_pixels or bbox).")
                continue
            if not hasattr(block_item, 'orientation'): # Default orientation if missing
                block_item.orientation = "horizontal"
            if not hasattr(block_item, 'text_align'): # Default alignment if missing
                block_item.text_align = "center" if block_item.orientation == "horizontal" else "left" # 'left' for vertical often means top-aligned for chars
            if not hasattr(block_item, 'angle'): # Default angle if missing
                block_item.angle = 0.0

            _draw_single_block_pil(
                draw_target_image=base_image, # Pass the main image to draw onto
                block=block_item, 
                font_name_config=font_name_conf,
                text_main_color_pil=main_color_pil,
                text_outline_color_pil=outline_color_pil,
                text_bg_color_pil=bg_color_pil,
                outline_thickness=outline_thick_conf,
                text_padding=text_pad_conf,
                h_char_spacing_px=h_char_spacing_conf,
                h_line_spacing_px=h_line_spacing_conf,
                v_char_spacing_px=v_char_spacing_conf,
                v_col_spacing_px=v_col_spacing_conf,
                h_manual_break_extra_px=h_manual_break_extra_conf, 
                v_manual_break_extra_px=v_manual_break_extra_conf  
            )
        return base_image

    except Exception as e:
        print(f"错误(draw_processed_blocks_pil): {e}")
        import traceback
        traceback.print_exc()
        return pil_image_original # Return original on error
# --- END OF FILE utils.py ---