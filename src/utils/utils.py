import os 
import math 
from PyQt6 .QtGui import QPixmap ,QImage ,QPainter ,QColor ,QFontMetrics ,QPen ,QBrush 
from PyQt6 .QtCore import Qt ,QRectF ,QPointF 
from config_manager import ConfigManager 
try :
    from PIL import Image ,ImageDraw ,ImageFont as PILImageFont 
    PILLOW_AVAILABLE =True 
except ImportError :
    PILLOW_AVAILABLE =False 
    PILImageFont =None 
    Image =None 
    ImageDraw =None 
    print ("警告(utils): Pillow 库未安装，图像处理和显示功能将受限。")
if PILLOW_AVAILABLE :
    from .font_utils import get_pil_font ,get_font_line_height ,wrap_text_pil ,find_font_path 
def pil_to_qpixmap (pil_image :Image .Image )->QPixmap |None :
    if not PILLOW_AVAILABLE or not pil_image :
        return None 
    try :
        if pil_image .mode =='P':
            pil_image =pil_image .convert ("RGBA")
        elif pil_image .mode =='L':
            pil_image =pil_image .convert ("RGB")
        elif pil_image .mode not in ("RGB","RGBA"):
             pil_image =pil_image .convert ("RGBA")
        data =pil_image .tobytes ("raw",pil_image .mode )
        qimage_format =QImage .Format .Format_Invalid 
        if pil_image .mode =="RGBA":
            qimage_format =QImage .Format .Format_RGBA8888 
        elif pil_image .mode =="RGB":
            qimage_format =QImage .Format .Format_RGB888 
        if qimage_format ==QImage .Format .Format_Invalid :
            print (f"警告(pil_to_qpixmap): 不支持的Pillow图像模式 {pil_image.mode} 转换为QImage。")
            pil_image_rgba =pil_image .convert ("RGBA")
            data =pil_image_rgba .tobytes ("raw","RGBA")
            qimage =QImage (data ,pil_image_rgba .width ,pil_image_rgba .height ,QImage .Format .Format_RGBA8888 )
            if qimage .isNull ():return None 
            return QPixmap .fromImage (qimage )
        qimage =QImage (data ,pil_image .width ,pil_image .height ,qimage_format )
        if qimage .isNull ():
            print (f"警告(pil_to_qpixmap): QImage.isNull() 为 True，模式: {pil_image.mode}")
            return None 
        return QPixmap .fromImage (qimage )
    except Exception as e :
        print (f"错误(pil_to_qpixmap): {e}")
        return None 
def crop_image_to_circle (pil_image :Image .Image )->Image .Image |None :
    if not PILLOW_AVAILABLE or not pil_image :return None 
    try :
        img =pil_image .copy ().convert ("RGBA")
        width ,height =img .size 
        size =min (width ,height )
        mask =Image .new ('L',(width ,height ),0 )
        draw_mask =ImageDraw .Draw (mask )
        left =(width -size )//2 
        top =(height -size )//2 
        right =left +size 
        bottom =top +size 
        draw_mask .ellipse ((left ,top ,right ,bottom ),fill =255 )
        output_img =Image .new ('RGBA',(width ,height ),(0 ,0 ,0 ,0 ))
        output_img .paste (img ,(0 ,0 ),mask =mask )
        return output_img 
    except Exception as e :
        print (f"错误(crop_image_to_circle): {e}")
        return None 
def check_dependencies_availability ():
    dependencies ={
    "Pillow":PILLOW_AVAILABLE ,
    "google.generativeai":False ,
    "google-cloud-vision_lib_present":False ,
    "openai_lib":False 
    }
    try :
        import google .generativeai 
        dependencies ["google.generativeai"]=True 
    except ImportError :pass 
    try :
        import google .cloud .vision 
        dependencies ["google-cloud-vision_lib_present"]=True 
    except ImportError :pass 
    try :
        import openai 
        dependencies ["openai_lib"]=True 
    except ImportError :pass 
    return dependencies 
def is_sentence_end (text :str )->bool :
    text =text .strip ()
    if not text :return False 
    end_chars =('。','、','！','？','.','!','?')
    closing_brackets =('」','』','）',')','】',']','"',"'")
    last_char =''
    for char_val in reversed (text ):
        if not char_val .isspace ():
            last_char =char_val 
            break 
    if not last_char :return False 
    if last_char in end_chars :
        return True 
    if last_char in closing_brackets :
        if len (text )>1 :
            temp_text =text 
            while temp_text .endswith (last_char )or temp_text .endswith (' '):
                if temp_text .endswith (last_char ):
                    temp_text =temp_text [:-len (last_char )]
                else :
                    temp_text =temp_text [:-1 ]
            second_last_char =''
            if temp_text :
                for char_val_inner in reversed (temp_text ):
                    if not char_val_inner .isspace ():
                        second_last_char =char_val_inner 
                        break 
                if second_last_char in end_chars :
                    return True 
    return False 
def check_horizontal_proximity (box1_data ,box2_data ,max_vertical_diff_ratio =0.6 ,max_horizontal_gap_ratio =1.5 ,min_overlap_ratio =-0.2 ):
    if 'bbox'not in box1_data or 'bbox'not in box2_data :return False 
    box1 =box1_data ['bbox']
    box2 =box2_data ['bbox']
    if not (box1 and box2 and len (box1 )==4 and len (box2 )==4 ):return False 
    b1_x0 ,b1_y0 ,b1_x1 ,b1_y1 =box1 
    b2_x0 ,b2_y0 ,b2_x1 ,b2_y1 =box2 
    if b1_x0 >b2_x0 and b1_x1 >b2_x1 and b1_x0 >b2_x1 :
        return False 
    h1 =b1_y1 -b1_y0 ;h2 =b2_y1 -b2_y0 
    if h1 <=0 or h2 <=0 :return False 
    center1_y =(b1_y0 +b1_y1 )/2 
    center2_y =(b2_y0 +b2_y1 )/2 
    avg_h =(h1 +h2 )/2 
    if avg_h <=0 :return False 
    vertical_diff =abs (center1_y -center2_y )
    if vertical_diff >avg_h *max_vertical_diff_ratio :
        return False 
    if b1_x1 <=b2_x0 :
        horizontal_gap =b2_x0 -b1_x1 
        if horizontal_gap >avg_h *max_horizontal_gap_ratio :
            return False 
    else :
        if b2_x0 <b1_x0 :
            if b1_x0 -b2_x0 >avg_h *0.5 :
                return False 
    return True 
def process_ocr_results_merge_lines (ocr_output_raw_segments :list ,lang_hint ='ja'):
    if not ocr_output_raw_segments or not isinstance (ocr_output_raw_segments ,list ):
        return []
    raw_blocks =[]
    try :
        for i ,item_data in enumerate (ocr_output_raw_segments ):
            if not isinstance (item_data ,(list ,tuple ))or len (item_data )!=2 :
                continue 
            box_info_raw =item_data [0 ]
            text_info_raw =item_data [1 ]
            text_content_str =""
            if isinstance (text_info_raw ,tuple )and len (text_info_raw )>=1 and isinstance (text_info_raw [0 ],str ):
                text_content_str =text_info_raw [0 ].strip ()
            elif isinstance (text_info_raw ,list )and len (text_info_raw )>=1 and isinstance (text_info_raw [0 ],str ):
                text_content_str =text_info_raw [0 ].strip ()
            elif isinstance (text_info_raw ,str ):
                text_content_str =text_info_raw .strip ()
            else :
                continue 
            if not text_content_str :
                continue 
            vertices_parsed =[]
            if isinstance (box_info_raw ,list )and len (box_info_raw )==4 :
                valid_points =True 
                for p_idx ,p in enumerate (box_info_raw ):
                    if isinstance (p ,(list ,tuple ))and len (p )==2 :
                        try :
                            vertices_parsed .append ((int (round (float (p [0 ]))),int (round (float (p [1 ])))))
                        except (ValueError ,TypeError ):
                            valid_points =False ;break 
                    else :
                        valid_points =False ;break 
                if not valid_points :
                    vertices_parsed =[]
            elif isinstance (box_info_raw ,list )and len (box_info_raw )==8 :
                try :
                    temp_v =[]
                    for k in range (0 ,8 ,2 ):
                        temp_v .append ((int (round (float (box_info_raw [k ]))),int (round (float (box_info_raw [k +1 ])))))
                    if len (temp_v )==4 :
                        vertices_parsed =temp_v 
                    else :
                        vertices_parsed =[]
                except (ValueError ,TypeError ):
                    vertices_parsed =[]
            else :
                vertices_parsed =[]
            if not vertices_parsed :
                continue 
            x_coords_list =[v [0 ]for v in vertices_parsed ]
            y_coords_list =[v [1 ]for v in vertices_parsed ]
            bbox_rect =[min (x_coords_list ),min (y_coords_list ),max (x_coords_list ),max (y_coords_list )]
            if not (bbox_rect [2 ]>bbox_rect [0 ]and bbox_rect [3 ]>bbox_rect [1 ]):
                continue 
            raw_blocks .append ({'id':i ,'text':text_content_str ,'bbox':bbox_rect ,'vertices':vertices_parsed })
    except Exception as e :
        print (f"错误(process_ocr_results_merge_lines) - initial parsing: {e}")
        return []
    if not raw_blocks :
        return []
    raw_blocks .sort (key =lambda b :(b ['bbox'][1 ],b ['bbox'][0 ]))
    merged_results =[]
    processed_block_ids =set ()
    for i in range (len (raw_blocks )):
        if raw_blocks [i ]['id']in processed_block_ids :
            continue 
        current_block_data =raw_blocks [i ]
        current_text_line =current_block_data ['text']
        current_line_vertices =list (current_block_data ['vertices'])
        current_line_bbox =list (current_block_data ['bbox'])
        last_merged_block_in_this_line =current_block_data 
        processed_block_ids .add (current_block_data ['id'])
        for j in range (i +1 ,len (raw_blocks )):
            next_block_candidate_data =raw_blocks [j ]
            if next_block_candidate_data ['id']in processed_block_ids :
                continue 
            should_merge_flag =False 
            if not is_sentence_end (current_text_line ):
                if check_horizontal_proximity (last_merged_block_in_this_line ,next_block_candidate_data ):
                    should_merge_flag =True 
            if should_merge_flag :
                joiner =""
                if lang_hint not in ['ja','zh','ko','jpn','chi_sim','kor','chinese_sim']:
                    if current_text_line and next_block_candidate_data ['text']:
                        if not current_text_line .endswith (('-','=','#'))and not next_block_candidate_data ['text'][0 ]in ('.',',','!','?',':',';'):
                            joiner =" "
                current_text_line +=joiner +next_block_candidate_data ['text']
                next_bbox =next_block_candidate_data ['bbox']
                current_line_bbox [0 ]=min (current_line_bbox [0 ],next_bbox [0 ])
                current_line_bbox [1 ]=min (current_line_bbox [1 ],next_bbox [1 ])
                current_line_bbox [2 ]=max (current_line_bbox [2 ],next_bbox [2 ])
                current_line_bbox [3 ]=max (current_line_bbox [3 ],next_bbox [3 ])
                last_merged_block_in_this_line =next_block_candidate_data 
                processed_block_ids .add (next_block_candidate_data ['id'])
            else :
                break 
        merged_results .append ((current_text_line ,current_line_bbox ))
    return merged_results 
def _render_single_block_pil_for_preview (
block :'ProcessedBlock',
font_name_config :str ,
text_main_color_pil :tuple ,
text_outline_color_pil :tuple ,
text_bg_color_pil :tuple ,
outline_thickness :int ,
text_padding :int ,
h_char_spacing_px :int ,
h_line_spacing_px :int ,
v_char_spacing_px :int ,
v_col_spacing_px :int ,
h_manual_break_extra_px :int =0 ,
v_manual_break_extra_px :int =0 ,
)->Image .Image |None :
    """
    Renders a single ProcessedBlock to a new, UNROTATED Pillow Image.
    The size of this image is now determined by block.bbox.
    The text background (if enabled) will fill this bbox area (minus internal padding for text placement).
    The block's angle is NOT applied here; rotation is handled by QPainter.
    """
    if not PILLOW_AVAILABLE or not block .translated_text or not block .translated_text .strip ():
        if PILLOW_AVAILABLE and block .bbox :
            bbox_width =int (block .bbox [2 ]-block .bbox [0 ])
            bbox_height =int (block .bbox [3 ]-block .bbox [1 ])
            if bbox_width >0 and bbox_height >0 :
                empty_surface =Image .new ('RGBA',(bbox_width ,bbox_height ),(0 ,0 ,0 ,0 ))
                if text_bg_color_pil and len (text_bg_color_pil )==4 and text_bg_color_pil [3 ]>0 :
                    draw =ImageDraw .Draw (empty_surface )
                    draw .rectangle ([(0 ,0 ),(bbox_width -1 ,bbox_height -1 )],fill =text_bg_color_pil )
                return empty_surface 
        return None 
    font_size_to_use =int (block .font_size_pixels )
    pil_font =get_pil_font (font_name_config ,font_size_to_use )
    if not pil_font :
        print (f"警告(_render_single_block_pil_for_preview): 无法加载字体 '{font_name_config}' (大小: {font_size_to_use}px)")
        bbox_width_err =int (block .bbox [2 ]-block .bbox [0 ])if block .bbox else 100 
        bbox_height_err =int (block .bbox [3 ]-block .bbox [1 ])if block .bbox else 50 
        err_img =Image .new ("RGBA",(max (1 ,bbox_width_err ),max (1 ,bbox_height_err )),(255 ,0 ,0 ,100 ))
        ImageDraw .Draw (err_img ).text ((5 ,5 ),"字体错误",font =ImageFont .load_default (),fill =(255 ,255 ,255 ,255 ))
        return err_img 
    text_to_draw =block .translated_text 
    dummy_metric_img =Image .new ('RGBA',(1 ,1 ))
    pil_draw_metric =ImageDraw .Draw (dummy_metric_img )
    wrapped_segments :list [str ]
    actual_text_render_width_unpadded :int 
    actual_text_render_height_unpadded :int 
    segment_secondary_dim_with_spacing :int 
    target_surface_width =int (block .bbox [2 ]-block .bbox [0 ])
    target_surface_height =int (block .bbox [3 ]-block .bbox [1 ])
    if target_surface_width <=0 or target_surface_height <=0 :
        print (f"警告(_render_single_block_pil_for_preview): block.bbox '{block.bbox}' 尺寸无效。")
        err_img_bbox =Image .new ("RGBA",(100 ,50 ),(255 ,0 ,0 ,100 ))
        ImageDraw .Draw (err_img_bbox ).text ((5 ,5 ),"BBox错误",font =ImageFont .load_default (),fill =(255 ,255 ,255 ,255 ))
        return err_img_bbox 
    max_content_width_for_wrapping =target_surface_width -(2 *text_padding )
    max_content_height_for_wrapping =target_surface_height -(2 *text_padding )
    if max_content_width_for_wrapping <=0 or max_content_height_for_wrapping <=0 :
        block_surface_nopad =Image .new ('RGBA',(target_surface_width ,target_surface_height ),(0 ,0 ,0 ,0 ))
        draw_nopad =ImageDraw .Draw (block_surface_nopad )
        if text_bg_color_pil and len (text_bg_color_pil )==4 and text_bg_color_pil [3 ]>0 :
            draw_nopad .rectangle ([(0 ,0 ),(target_surface_width -1 ,target_surface_height -1 )],fill =text_bg_color_pil )
        return block_surface_nopad 
    if block .orientation =="horizontal":
        wrap_dim_for_pil =max (1 ,int (max_content_width_for_wrapping ))
        wrapped_segments ,initial_total_height ,seg_secondary_dim_with_spacing ,actual_text_render_width_unpadded =wrap_text_pil (
        pil_draw_metric ,text_to_draw ,pil_font ,
        max_dim =wrap_dim_for_pil ,
        orientation ="horizontal",
        char_spacing_px =h_char_spacing_px ,
        line_or_col_spacing_px =h_line_spacing_px 
        )
        actual_text_render_height_unpadded =0 
        if wrapped_segments :
            for seg_text in wrapped_segments :
                actual_text_render_height_unpadded +=seg_secondary_dim_with_spacing 
                if seg_text =="":actual_text_render_height_unpadded +=h_manual_break_extra_px 
        elif text_to_draw :
             actual_text_render_height_unpadded =seg_secondary_dim_with_spacing if seg_secondary_dim_with_spacing >0 else get_font_line_height (pil_font ,font_size_to_use ,h_line_spacing_px )
             actual_text_render_width_unpadded =pil_draw_metric .textlength (text_to_draw ,font =pil_font )+(h_char_spacing_px *(len (text_to_draw )-1 )if len (text_to_draw )>1 else 0 )
    else :
        wrap_dim_for_pil =max (1 ,int (max_content_height_for_wrapping ))
        wrapped_segments ,initial_total_width ,seg_secondary_dim_with_spacing ,actual_text_render_height_unpadded =wrap_text_pil (
        pil_draw_metric ,text_to_draw ,pil_font ,
        max_dim =wrap_dim_for_pil ,
        orientation ="vertical",
        char_spacing_px =v_char_spacing_px ,
        line_or_col_spacing_px =0 
        )
        actual_text_render_width_unpadded =0 
        if wrapped_segments :
            try :
                single_col_visual_width_metric =pil_font .getlength ("M")
                if single_col_visual_width_metric ==0 :single_col_visual_width_metric =pil_font .size if hasattr (pil_font ,'size')else font_size_to_use 
            except AttributeError :single_col_visual_width_metric =pil_font .size if hasattr (pil_font ,'size')else font_size_to_use 
            num_cols_pil =len (wrapped_segments )
            for seg_idx ,seg_text in enumerate (wrapped_segments ):
                actual_text_render_width_unpadded +=single_col_visual_width_metric 
                if seg_idx <num_cols_pil -1 :
                    actual_text_render_width_unpadded +=v_col_spacing_px 
                    if seg_text =="":actual_text_render_width_unpadded +=v_manual_break_extra_px 
        elif text_to_draw :
            try :single_col_visual_width_metric =pil_font .getlength ("M")
            except :single_col_visual_width_metric =font_size_to_use 
            actual_text_render_width_unpadded =single_col_visual_width_metric 
            actual_text_render_height_unpadded =(seg_secondary_dim_with_spacing if seg_secondary_dim_with_spacing >0 else get_font_line_height (pil_font ,font_size_to_use ,v_char_spacing_px ))*len (text_to_draw )
    if not wrapped_segments and text_to_draw :
        wrapped_segments =[text_to_draw ]
        if block .orientation =="horizontal":
            if actual_text_render_width_unpadded <=0 :
                 actual_text_render_width_unpadded =pil_draw_metric .textlength (text_to_draw ,font =pil_font )+(h_char_spacing_px *(len (text_to_draw )-1 )if len (text_to_draw )>1 else 0 )
            if actual_text_render_height_unpadded <=0 :
                 actual_text_render_height_unpadded =get_font_line_height (pil_font ,font_size_to_use ,h_line_spacing_px )
            seg_secondary_dim_with_spacing =actual_text_render_height_unpadded 
        else :
            if actual_text_render_width_unpadded <=0 :
                try :actual_text_render_width_unpadded =pil_font .getlength ("M")
                except :actual_text_render_width_unpadded =font_size_to_use 
            if actual_text_render_height_unpadded <=0 :
                 actual_text_render_height_unpadded =(get_font_line_height (pil_font ,font_size_to_use ,v_char_spacing_px ))*len (text_to_draw )
            seg_secondary_dim_with_spacing =get_font_line_height (pil_font ,font_size_to_use ,v_char_spacing_px )
    if not wrapped_segments or actual_text_render_width_unpadded <=0 or actual_text_render_height_unpadded <=0 :
        if text_to_draw :
            print (f"警告(_render_single_block_pil_for_preview): 文本 '{text_to_draw[:20]}...' 的渲染尺寸为零或负（BBox阶段）。")
            err_img_dim =Image .new ("RGBA",(target_surface_width ,target_surface_height ),(255 ,0 ,0 ,100 ))
            ImageDraw .Draw (err_img_dim ).text ((text_padding ,text_padding ),"渲染尺寸错误",font =ImageFont .load_default (),fill =(255 ,255 ,255 ,255 ))
            return err_img_dim 
        empty_surface_fallback =Image .new ('RGBA',(target_surface_width ,target_surface_height ),(0 ,0 ,0 ,0 ))
        if text_bg_color_pil and len (text_bg_color_pil )==4 and text_bg_color_pil [3 ]>0 :
            ImageDraw .Draw (empty_surface_fallback ).rectangle ([(0 ,0 ),(target_surface_width -1 ,target_surface_height -1 )],fill =text_bg_color_pil )
        return empty_surface_fallback 
    block_surface =Image .new ('RGBA',(target_surface_width ,target_surface_height ),(0 ,0 ,0 ,0 ))
    draw_on_block_surface =ImageDraw .Draw (block_surface )
    if text_bg_color_pil and len (text_bg_color_pil )==4 and text_bg_color_pil [3 ]>0 :
        draw_on_block_surface .rectangle ([(0 ,0 ),(target_surface_width -1 ,target_surface_height -1 )],fill =text_bg_color_pil )
    content_area_x_start =text_padding 
    content_area_y_start =text_padding 
    text_block_start_x =content_area_x_start 
    text_block_start_y =content_area_y_start 
    if block .orientation =="horizontal":
        if block .text_align =="center":
            text_block_start_x =content_area_x_start +(max_content_width_for_wrapping -actual_text_render_width_unpadded )/2.0 
        elif block .text_align =="right":
            text_block_start_x =content_area_x_start +max_content_width_for_wrapping -actual_text_render_width_unpadded 
    else :
        if block .text_align =="center":
            text_block_start_x =content_area_x_start +(max_content_width_for_wrapping -actual_text_render_width_unpadded )/2.0 
        elif block .text_align =="right":
            text_block_start_x =content_area_x_start +max_content_width_for_wrapping -actual_text_render_width_unpadded 
    if block .orientation =="horizontal":
        current_y_pil =text_block_start_y 
        for line_idx ,line_text in enumerate (wrapped_segments ):
            is_manual_break_line =(line_text =="")
            if not is_manual_break_line :
                line_w_specific_pil =pil_draw_metric .textlength (line_text ,font =pil_font )
                if len (line_text )>1 and h_char_spacing_px !=0 :
                    line_w_specific_pil +=h_char_spacing_px *(len (line_text )-1 )
                line_offset_x_within_block =0 
                if block .text_align =="center":
                    line_offset_x_within_block =(actual_text_render_width_unpadded -line_w_specific_pil )/2.0 
                elif block .text_align =="right":
                    line_offset_x_within_block =actual_text_render_width_unpadded -line_w_specific_pil 
                line_draw_x_pil =text_block_start_x +line_offset_x_within_block 
                if outline_thickness >0 and text_outline_color_pil and len (text_outline_color_pil )==4 and text_outline_color_pil [3 ]>0 :
                    for dx_o in range (-outline_thickness ,outline_thickness +1 ):
                        for dy_o in range (-outline_thickness ,outline_thickness +1 ):
                            if dx_o ==0 and dy_o ==0 :continue 
                            if h_char_spacing_px !=0 :
                                temp_x_char_outline =line_draw_x_pil +dx_o 
                                for char_ol in line_text :
                                    draw_on_block_surface .text ((temp_x_char_outline ,current_y_pil +dy_o ),char_ol ,font =pil_font ,fill =text_outline_color_pil )
                                    temp_x_char_outline +=pil_draw_metric .textlength (char_ol ,font =pil_font )+h_char_spacing_px 
                            else :
                                draw_on_block_surface .text ((line_draw_x_pil +dx_o ,current_y_pil +dy_o ),line_text ,font =pil_font ,fill =text_outline_color_pil ,spacing =0 )
                if h_char_spacing_px !=0 :
                    temp_x_char_main =line_draw_x_pil 
                    for char_m in line_text :
                        draw_on_block_surface .text ((temp_x_char_main ,current_y_pil ),char_m ,font =pil_font ,fill =text_main_color_pil )
                        temp_x_char_main +=pil_draw_metric .textlength (char_m ,font =pil_font )+h_char_spacing_px 
                else :
                    draw_on_block_surface .text ((line_draw_x_pil ,current_y_pil ),line_text ,font =pil_font ,fill =text_main_color_pil ,spacing =0 )
            current_y_pil +=seg_secondary_dim_with_spacing 
            if is_manual_break_line :
                current_y_pil +=h_manual_break_extra_px 
    else :
        try :
            single_col_visual_width_metric =pil_font .getlength ("M")
            if single_col_visual_width_metric ==0 :single_col_visual_width_metric =pil_font .size if hasattr (pil_font ,'size')else font_size_to_use 
        except AttributeError :
            single_col_visual_width_metric =pil_font .size if hasattr (pil_font ,'size')else font_size_to_use 
        current_x_pil_col_start_abs =text_block_start_x 
        if block .orientation =="vertical_rtl":
            current_x_pil_col_start_abs =text_block_start_x +actual_text_render_width_unpadded -single_col_visual_width_metric 
        for col_idx ,col_text in enumerate (wrapped_segments ):
            is_manual_break_col =(col_text =="")
            current_y_pil_char =text_block_start_y 
            this_col_content_actual_height =0 
            if not is_manual_break_col :
                this_col_content_actual_height =len (col_text )*seg_secondary_dim_with_spacing 
            if not is_manual_break_col :
                for char_in_col_idx ,char_in_col in enumerate (col_text ):
                    char_w_specific_pil =pil_draw_metric .textlength (char_in_col ,font =pil_font )
                    char_x_offset_in_col_slot =(single_col_visual_width_metric -char_w_specific_pil )/2.0 
                    final_char_draw_x =current_x_pil_col_start_abs +char_x_offset_in_col_slot 
                    if outline_thickness >0 and text_outline_color_pil and len (text_outline_color_pil )==4 and text_outline_color_pil [3 ]>0 :
                        for dx_o in range (-outline_thickness ,outline_thickness +1 ):
                            for dy_o in range (-outline_thickness ,outline_thickness +1 ):
                                if dx_o ==0 and dy_o ==0 :continue 
                                draw_on_block_surface .text ((final_char_draw_x +dx_o ,current_y_pil_char +dy_o ),char_in_col ,font =pil_font ,fill =text_outline_color_pil )
                    draw_on_block_surface .text ((final_char_draw_x ,current_y_pil_char ),char_in_col ,font =pil_font ,fill =text_main_color_pil )
                    current_y_pil_char +=seg_secondary_dim_with_spacing 
            if col_idx <len (wrapped_segments )-1 :
                spacing_to_next_col =single_col_visual_width_metric +v_col_spacing_px 
                if is_manual_break_col :
                    spacing_to_next_col +=v_manual_break_extra_px 
                if block .orientation =="vertical_rtl":
                    current_x_pil_col_start_abs -=spacing_to_next_col 
                else :
                    current_x_pil_col_start_abs +=spacing_to_next_col 
    return block_surface 
def _draw_single_block_pil (
draw_target_image :Image .Image ,
block :'ProcessedBlock',
font_name_config :str ,
text_main_color_pil :tuple ,
text_outline_color_pil :tuple ,
text_bg_color_pil :tuple ,
outline_thickness :int ,
text_padding :int ,
h_char_spacing_px :int ,
h_line_spacing_px :int ,
v_char_spacing_px :int ,
v_col_spacing_px :int ,
h_manual_break_extra_px :int =0 ,
v_manual_break_extra_px :int =0 
)->None :
    """
    Draws a single processed block onto the draw_target_image.
    This version now USES _render_single_block_pil_for_preview to get the block's visual content.
    """
    if not PILLOW_AVAILABLE or not block .translated_text or not block .translated_text .strip ():
        return 
    rendered_block_content_pil =_render_single_block_pil_for_preview (
    block =block ,
    font_name_config =font_name_config ,
    text_main_color_pil =text_main_color_pil ,
    text_outline_color_pil =text_outline_color_pil ,
    text_bg_color_pil =text_bg_color_pil ,
    outline_thickness =outline_thickness ,
    text_padding =text_padding ,
    h_char_spacing_px =h_char_spacing_px ,
    h_line_spacing_px =h_line_spacing_px ,
    v_char_spacing_px =v_char_spacing_px ,
    v_col_spacing_px =v_col_spacing_px ,
    h_manual_break_extra_px =h_manual_break_extra_px ,
    v_manual_break_extra_px =v_manual_break_extra_px 
    )
    if not rendered_block_content_pil :
        return 
    final_surface_to_paste =rendered_block_content_pil 
    if block .angle !=0 :
        try :
            final_surface_to_paste =rendered_block_content_pil .rotate (
            -block .angle ,
            expand =True ,
            resample =Image .Resampling .BICUBIC 
            )
        except Exception as e :
            print (f"Error rotating block content: {e}")
            final_surface_to_paste =rendered_block_content_pil 
    block_center_x_orig_coords =(block .bbox [0 ]+block .bbox [2 ])/2.0 
    block_center_y_orig_coords =(block .bbox [1 ]+block .bbox [3 ])/2.0 
    paste_x =int (round (block_center_x_orig_coords -(final_surface_to_paste .width /2.0 )))
    paste_y =int (round (block_center_y_orig_coords -(final_surface_to_paste .height /2.0 )))
    if draw_target_image .mode !='RGBA':
        try :
            draw_target_image =draw_target_image .convert ('RGBA')
        except Exception as e :
            print (f"Error converting draw_target_image to RGBA: {e}")
            return 
    try :
        if final_surface_to_paste .mode =='RGBA':
            draw_target_image .alpha_composite (final_surface_to_paste ,(paste_x ,paste_y ))
        else :
            draw_target_image .paste (final_surface_to_paste ,(paste_x ,paste_y ))
    except Exception as e :
        print (f"Error compositing block '{block.translated_text[:20]}...' onto target image: {e}")
        try :
            if final_surface_to_paste .mode =='RGBA':
                draw_target_image .paste (final_surface_to_paste ,(paste_x ,paste_y ),mask =final_surface_to_paste )
            else :
                draw_target_image .paste (final_surface_to_paste ,(paste_x ,paste_y ))
        except Exception as e_paste :
            print (f"Fallback paste also failed for block: {e_paste}")
def draw_processed_blocks_pil (pil_image_original :Image .Image ,processed_blocks :list ,config_manager :ConfigManager )->Image .Image |None :
    if not PILLOW_AVAILABLE or not pil_image_original or not processed_blocks :
        return pil_image_original 
    try :
        if pil_image_original .mode !='RGBA':
            base_image =pil_image_original .convert ('RGBA')
        else :
            base_image =pil_image_original .copy ()
        font_name_conf =config_manager .get ('UI','font_name','msyh.ttc')
        text_pad_conf =config_manager .getint ('UI','text_padding',3 )
        main_color_str =config_manager .get ('UI','text_main_color','255,255,255,255')
        outline_color_str =config_manager .get ('UI','text_outline_color','0,0,0,255')
        outline_thick_conf =config_manager .getint ('UI','text_outline_thickness',2 )
        bg_color_str =config_manager .get ('UI','text_background_color','0,0,0,128')
        h_char_spacing_conf =config_manager .getint ('UI','h_text_char_spacing_px',0 )
        h_line_spacing_conf =config_manager .getint ('UI','h_text_line_spacing_px',0 )
        v_char_spacing_conf =config_manager .getint ('UI','v_text_char_spacing_px',0 )
        v_col_spacing_conf =config_manager .getint ('UI','v_text_column_spacing_px',0 )
        h_manual_break_extra_conf =config_manager .getint ('UI','h_manual_break_extra_spacing_px',0 )
        v_manual_break_extra_conf =config_manager .getint ('UI','v_manual_break_extra_spacing_px',0 )
        try :
            mc_parts =list (map (int ,main_color_str .split (',')))
            oc_parts =list (map (int ,outline_color_str .split (',')))
            bc_parts =list (map (int ,bg_color_str .split (',')))
            main_color_pil =tuple (mc_parts )if len (mc_parts )in [3 ,4 ]else (255 ,255 ,255 ,255 )
            outline_color_pil =tuple (oc_parts )if len (oc_parts )in [3 ,4 ]else (0 ,0 ,0 ,255 )
            bg_color_pil =tuple (bc_parts )if len (bc_parts )in [3 ,4 ]else (0 ,0 ,0 ,128 )
            if len (main_color_pil )==3 :main_color_pil +=(255 ,)
            if len (outline_color_pil )==3 :outline_color_pil +=(255 ,)
            if len (bg_color_pil )==3 :bg_color_pil +=(128 ,)
        except ValueError :
            main_color_pil =(255 ,255 ,255 ,255 );outline_color_pil =(0 ,0 ,0 ,255 );bg_color_pil =(0 ,0 ,0 ,128 )
        for idx ,block_item in enumerate (processed_blocks ):
            if not hasattr (block_item ,'translated_text')or not block_item .translated_text or not block_item .translated_text .strip ():
                continue 
            if not hasattr (block_item ,'font_size_pixels')or not hasattr (block_item ,'bbox'):
                print (f"Skipping block {idx} due to missing attributes (font_size_pixels or bbox).")
                continue 
            if not hasattr (block_item ,'orientation'):
                block_item .orientation ="horizontal"
            if not hasattr (block_item ,'text_align')or not block_item .text_align :
                if block_item .orientation !="horizontal":
                    block_item .text_align ="right"
                else :
                    block_item .text_align ="left"
                print (f"警告(draw_processed_blocks_pil): Block {getattr(block_item, 'id', 'N/A')} 缺少有效的 text_align，已设置为 '{block_item.text_align}'。")
            if not hasattr (block_item ,'angle'):
                block_item .angle =0.0 
            _draw_single_block_pil (
            draw_target_image =base_image ,
            block =block_item ,
            font_name_config =font_name_conf ,
            text_main_color_pil =main_color_pil ,
            text_outline_color_pil =outline_color_pil ,
            text_bg_color_pil =bg_color_pil ,
            outline_thickness =outline_thick_conf ,
            text_padding =text_pad_conf ,
            h_char_spacing_px =h_char_spacing_conf ,
            h_line_spacing_px =h_line_spacing_conf ,
            v_char_spacing_px =v_char_spacing_conf ,
            v_col_spacing_px =v_col_spacing_conf ,
            h_manual_break_extra_px =h_manual_break_extra_conf ,
            v_manual_break_extra_px =v_manual_break_extra_conf 
            )
        return base_image 
    except Exception as e :
        print (f"错误(draw_processed_blocks_pil): {e}")
        import traceback 
        traceback .print_exc ()
        return pil_image_original 