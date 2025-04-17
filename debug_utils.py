from logger import get_logger

# 获取 logger
logger = get_logger()

def print_section(title, content):
    """
    Print a section with a title and content.
    
    Args:
        title: Section title
        content: Section content
    """
    logger.info(f"\n===== {title} =====")
    logger.info(content)
    logger.info(f"===== {title}结束 =====\n")

def print_subtitle_info(subtitles):
    """
    Print information about subtitles.
    
    Args:
        subtitles: List of subtitle entries
    """
    logger.info("\n===== 字幕信息 =====")
    for i, subtitle in enumerate(subtitles):
        logger.info(f"字幕 {i+1}:")
        logger.info(f"  时间范围: {subtitle['start']:.2f}s - {subtitle['end']:.2f}s")
        logger.info(f"  文本: {subtitle['text']}")
        logger.info("---")
    logger.info("===== 字幕信息结束 =====\n")

def print_sentence_pairs(original_sentences, translated_sentences):
    """
    Print pairs of original and translated sentences.
    
    Args:
        original_sentences: List of original sentences
        translated_sentences: List of translated sentences
    """
    logger.info("\n===== 拆分后的句子对照 =====")
    for i, (orig, trans) in enumerate(zip(original_sentences, translated_sentences)):
        logger.info(f"句子 {i+1}:")
        logger.info(f"  原文: {orig}")
        logger.info(f"  译文: {trans}")
        logger.info("---")
    logger.info("===== 拆分后的句子对照结束 =====\n")

def print_audio_segment_info(segment):
    """
    Print information about an audio segment.
    
    Args:
        segment: Audio segment information
    """
    logger.info(f"\n生成音频片段 {segment['index']+1}:")
    logger.info(f"  时间范围: {segment['start']:.2f}s - {segment['end']:.2f}s")
    logger.info(f"  文本: {segment['text']}")
    logger.info(f"  生成的音频时长: {segment['duration']:.2f}s")
