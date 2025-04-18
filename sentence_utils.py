from logger import get_logger
import re
# 获取 logger
logger = get_logger()

def extract_sentences(words):
    """
    Extract sentence boundaries from word-level timing information.
    
    Args:
        words: List of words with timing information
        
    Returns:
        List of sentence timing information
    """
    sentences = []
    current_sentence = {"start": 0, "end": 0, "words": []}
    
    for word in words:
        # Add word to current sentence
        current_sentence["words"].append(word)
        
        # Update sentence end time
        current_sentence["end"] = word["end_time"]
        
        # If word ends with sentence-ending punctuation, end the sentence
        if word["word"].endswith(('.', '!', '?', '。', '！', '？')):
            # Set sentence start time to the start time of the first word
            current_sentence["start"] = current_sentence["words"][0]["start_time"]
            
            # Add sentence to list
            sentences.append(current_sentence)
            
            # Start a new sentence
            current_sentence = {"start": word["end_time"], "end": word["end_time"], "words": []}
    
    # Add the last sentence if it's not empty
    if current_sentence["words"]:
        current_sentence["start"] = current_sentence["words"][0]["start_time"]
        sentences.append(current_sentence)
    
    # Adjust sentence end times to ensure subtitles stay on screen longer
    for i in range(len(sentences) - 1):
        # Calculate the gap between this sentence end and next sentence start
        gap = sentences[i+1]["start"] - sentences[i]["end"]
        
        # If there's a gap, extend this sentence's end time to fill part of the gap
        if gap > 0.2:  # If gap is more than 200ms
            # Extend the end time to fill 80% of the gap
            sentences[i]["end"] += gap * 0.8
    
    logger.info(f"Extracted {len(sentences)} sentences from {len(words)} words")
    return sentences

def split_into_matching_sentences(text, target_count):
    """
    Split text into approximately the same number of sentences as the original.
    
    Args:
        text: Text to split
        target_count: Target number of sentences
        
    Returns:
        List of sentences
    """
    # First, split by common sentence-ending punctuation
    for char in ['.', '!', '?', '。', '！', '？']:
        text = text.replace(char, char + '|')
    
    initial_sentences = [s.strip() for s in text.split('|') if s.strip()]
    
    # If we have exactly the right number, return as is
    if len(initial_sentences) == target_count:
        logger.info(f"Split text into exactly {target_count} sentences")
        return initial_sentences
    
    # If we have too few sentences, try splitting by commas or other punctuation
    if len(initial_sentences) < target_count:
        logger.info(f"Initial split resulted in {len(initial_sentences)} sentences, need {target_count}")
        # Try splitting by commas, semicolons, etc.
        more_sentences = []
        for sentence in initial_sentences:
            for char in [',', ';', ':', '，', '；', '：']:
                sentence = sentence.replace(char, char + '|')
            parts = [p.strip() for p in sentence.split('|') if p.strip()]
            more_sentences.extend(parts)
        
        # If we now have enough sentences, use these
        if len(more_sentences) >= target_count:
            logger.info(f"After splitting by punctuation, got {len(more_sentences)} sentences")
            # If we have too many, combine some
            if len(more_sentences) > target_count:
                return combine_sentences(more_sentences, target_count)
            return more_sentences
    
    # If we have too many sentences, combine some
    if len(initial_sentences) > target_count:
        logger.info(f"Initial split resulted in {len(initial_sentences)} sentences, need to combine to {target_count}")
        return combine_sentences(initial_sentences, target_count)
    
    # If all else fails, just return what we have
    logger.info(f"Using {len(initial_sentences)} sentences (target was {target_count})")
    return initial_sentences

def combine_sentences(sentences, target_count):
    """
    Combine sentences to reach the target count.
    
    Args:
        sentences: List of sentences
        target_count: Target number of sentences
        
    Returns:
        Combined list of sentences
    """
    # Calculate how many sentences to combine
    sentences_per_group = len(sentences) / target_count
    
    # Combine sentences
    combined_sentences = []
    current_group = []
    
    for i, sentence in enumerate(sentences):
        current_group.append(sentence)
        
        # If we've reached the end of a group, combine and add to result
        if (i + 1) / sentences_per_group >= len(combined_sentences) + 1:
            combined_sentences.append(' '.join(current_group))
            current_group = []
    
    # Add any remaining sentences
    if current_group:
        combined_sentences.append(' '.join(current_group))
    
    logger.info(f"Combined {len(sentences)} sentences into {len(combined_sentences)} sentences")
    return combined_sentences


def split_text_advanced(paragraph):
    # 添加更多中文标点符号：逗号、句号、问号、感叹号、分号
    pattern = r'(?<=[、。！？])'
    segments = re.split(pattern, paragraph)
    return [seg.strip() for seg in segments if seg.strip()]

def format_sentence_for_display(sentence, max_line_length=50, target_language=None):
    """
    Format a sentence to fit within display constraints.
    If the sentence is too long for one line, it will be split into multiple lines.
    优先使用目标语言的断句标点符号来拆分行，并根据目标语言设置不同的最大行长度。
    
    Args:
        sentence: The sentence to format
        max_line_length: Maximum characters per line (默认值会根据目标语言自动调整)
        target_language: 目标语言代码 (如 'en', 'ja', 'zh' 等)
        
    Returns:
        List of formatted lines
    """

    # 根据目标语言调整最大行长度
    if target_language:
        if target_language == 'en':
            max_line_length = 50  # 英文
        elif target_language == 'ja':
            max_line_length = 15  # 日语
        elif target_language in ['zh', 'ko']:
            max_line_length = 30  # 中文、韩文
        else:
            max_line_length = 40  # 其他语言

    # If sentence is short enough, return as a single line
    if len(sentence) <= max_line_length:
        return [sentence]

    if target_language == 'ja':
        words = split_text_advanced(sentence)
    else:
        words = sentence.split()
    lines = []
    current_line = ""
    
    for word in words:
        # Check if adding this word would exceed the max line length
        if len(current_line) + len(word) + 1 > max_line_length and current_line:
            lines.append(current_line)
            current_line = word
        else:
            if current_line:
                current_line += " " + word
            else:
                current_line = word
    
    # Add the last line if it's not empty
    if current_line:
        lines.append(current_line)
    
    return lines

def format_time_srt(seconds):
    """
    Format time in seconds to SRT format (HH:MM:SS,mmm).
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds_remainder = seconds % 60
    milliseconds = int((seconds_remainder - int(seconds_remainder)) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{int(seconds_remainder):02d},{milliseconds:03d}"
