import tempfile
import uuid
import os
import math
from sentence_utils import extract_sentences, split_into_matching_sentences, format_sentence_for_display, format_time_srt
from logger import get_logger

# 获取 logger
logger = get_logger()

def create_subtitles(s3_client, bucket_name, translated_data, language_code):
    """
    Create subtitle file from translated text with timing information.
    Each sentence maintains its original timing, ensuring sync with audio.
    
    Args:
        s3_client: AWS S3 client
        bucket_name: S3 bucket name
        translated_data: Dictionary containing translated text and timing information
        language_code: Language code for subtitles
        
    Returns:
        S3 key for the subtitle file
    """
    # Get the translated text and word timing information
    translated_text = translated_data["translated"]
    original_words = translated_data["words"]
    target_language = translated_data["target_language"]
    
    # Extract sentence boundaries from original transcript
    original_sentences = extract_sentences(original_words)
    logger.info(f"Extracted {len(original_sentences)} sentences from original transcript")
    
    # 尝试使用 AI 拆分方法
    try:
        from ai_split import ai_split_sentences
        # 获取 bedrock 客户端
        bedrock_client = None
        try:
            import boto3
            bedrock_client = boto3.client('bedrock-runtime', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            logger.info("成功初始化 Bedrock 客户端用于字幕 AI 拆分")
        except Exception as e:
            logger.warning(f"初始化 Bedrock 客户端失败: {str(e)}")
        
        # 使用 AI 拆分
        translated_sentences = ai_split_sentences(translated_text, original_sentences, target_language, bedrock_client)
        logger.info(f"字幕使用 AI 拆分方法，得到 {len(translated_sentences)} 个句子")
    except Exception as e:
        logger.error(f"字幕 AI 拆分失败: {str(e)}，回退到手动拆分")
        # 回退到手动拆分
        try:
            from manual_split import manual_split_sentences
            translated_sentences = manual_split_sentences(translated_text, original_sentences, target_language)
            logger.info(f"字幕使用手动拆分方法，得到 {len(translated_sentences)} 个句子")
        except Exception as e2:
            logger.error(f"字幕手动拆分也失败: {str(e2)}，回退到自动拆分")
            # 回退到原来的拆分方法
            translated_sentences = split_into_matching_sentences(translated_text, len(original_sentences))
            logger.info(f"字幕拆分为 {len(translated_sentences)} 个句子")
    
    # 输出字幕信息
    logger.info("\n===== 字幕信息 =====")
    for i, (sentence, timing) in enumerate(zip(translated_sentences, original_sentences)):
        # 获取原始句子的文本
        orig_text = " ".join([w["word"] for w in timing["words"]])
        
        # 直接使用原始翻译文本进行断句，不要修改内容
        formatted_lines = format_sentence_for_display(sentence, target_language=target_language)
        
        # 验证断句后的内容与原始内容一致
        combined = ''.join(formatted_lines)
        if combined != sentence:
            logger.warning(f"字幕 {i+1} 断句后内容与原始内容不一致!")
            logger.warning(f"原始: {sentence}")
            logger.warning(f"断句后: {combined}")
        
        logger.info(f"字幕 {i+1}:")
        logger.info(f"  时间范围: {timing['start']:.2f}s - {timing['end']:.2f}s")
        logger.info(f"  原文: {orig_text}")
        logger.info(f"  译文: {sentence}")
        logger.info(f"  格式化后的字幕行: {len(formatted_lines)}行")
        for j, line in enumerate(formatted_lines):
            logger.info(f"    行 {j+1}: {line}")
        logger.info("---")
    logger.info("===== 字幕信息结束 =====\n")
    
    # 获取音频片段的顺序播放时间信息（如果有）
    audio_timing = translated_data.get("audio_timing", None)
    use_sequential_timing = audio_timing is not None
    
    if use_sequential_timing:
        logger.info("检测到顺序播放时间信息，字幕将使用顺序播放时间")
    else:
        logger.info("未检测到顺序播放时间信息，字幕将使用原始时间")
    
    # Create an SRT file with timing from original sentences
    srt_content = ""
    subtitle_index = 1
    
    # Process each sentence with its original timing
    for i, (sentence, timing) in enumerate(zip(translated_sentences, original_sentences)):
        # Format the sentence into lines based on target language
        formatted_lines = format_sentence_for_display(sentence, target_language=target_language)
        
        # 获取时间范围
        if use_sequential_timing and i < len(audio_timing):
            # 使用顺序播放时间
            start_time = audio_timing[i]["sequential_start"]
            end_time = audio_timing[i]["sequential_end"]
            logger.info(f"字幕 {i+1} 使用顺序时间: {start_time:.2f}s-{end_time:.2f}s (原始: {timing['start']:.2f}s-{timing['end']:.2f}s)")
        else:
            # 使用原始时间
            start_time = timing["start"]
            end_time = timing["end"]
        
        total_duration = end_time - start_time
        
        # 如果字幕超过2行，则拆分成多条字幕
        if len(formatted_lines) > 2:
            # 计算需要拆分成几条字幕
            num_subtitle_parts = math.ceil(len(formatted_lines) / 2)
            
            # 计算每条字幕的显示时长
            base_duration = total_duration / num_subtitle_parts
            
            # 拆分字幕并分配时间
            for part_idx in range(num_subtitle_parts):
                part_start_idx = part_idx * 2
                part_end_idx = min(part_start_idx + 2, len(formatted_lines))
                part_lines = formatted_lines[part_start_idx:part_end_idx]
                
                # 计算这部分字幕的时间范围
                part_duration = base_duration
                
                # 如果是最后一部分且只有1行，可以缩短显示时间
                if part_idx == num_subtitle_parts - 1 and len(part_lines) == 1:
                    part_duration = base_duration / 2 + 1  # 按照公式: 基础时长/2 + 1秒
                
                part_start = start_time + part_idx * base_duration
                part_end = part_start + part_duration
                
                # 确保时间不超过原始结束时间
                part_end = min(part_end, end_time)
                
                # 添加到SRT内容
                srt_content += f"{subtitle_index}\n"
                srt_content += f"{format_time_srt(part_start)} --> {format_time_srt(part_end)}\n"
                srt_content += "\n".join(part_lines) + "\n\n"
                subtitle_index += 1
        else:
            # 字幕不超过2行，保持原始时间范围
            srt_content += f"{subtitle_index}\n"
            srt_content += f"{format_time_srt(start_time)} --> {format_time_srt(end_time)}\n"
            srt_content += "\n".join(formatted_lines) + "\n\n"
            subtitle_index += 1
    
    # Save the SRT file to a temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode="w", encoding="utf-8") as temp_srt:
        temp_srt.write(srt_content)
        srt_path = temp_srt.name
    
    # Upload the SRT file to S3
    subtitle_s3_key = f"subtitles/{uuid.uuid4()}.srt"
    s3_client.upload_file(srt_path, bucket_name, subtitle_s3_key)
    logger.info(f"Uploaded subtitle file to S3: {subtitle_s3_key}")
    
    # 打印字幕文件内容
    logger.info("\n===== 字幕文件内容 =====")
    with open(srt_path, 'r', encoding='utf-8') as f:
        logger.info(f.read())
    logger.info("===== 字幕文件内容结束 =====\n")
    
    # Clean up temporary file
    os.unlink(srt_path)
    
    # Return the subtitle key
    return {
        "srt": subtitle_s3_key
    }
