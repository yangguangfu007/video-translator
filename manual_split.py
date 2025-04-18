import os
import json
from logger import get_logger

# 获取 logger
logger = get_logger()

def manual_split_sentences(translated_text, original_sentences, target_language):
    """
    手动拆分翻译文本，确保与原始句子数量匹配。
    这个函数可以根据不同语言的特点进行特殊处理。
    
    Args:
        translated_text: 翻译后的文本
        original_sentences: 原始句子列表
        target_language: 目标语言代码
        
    Returns:
        拆分后的翻译句子列表
    """
    # 如果原始句子只有1个，直接返回整个翻译文本
    if len(original_sentences) == 1:
        return [translated_text]
    
    # 如果原始句子有2个，这是最常见的情况，需要特殊处理
    if len(original_sentences) == 2:
        # 获取原始句子的文本和时间信息
        first_orig = " ".join([w["word"] for w in original_sentences[0]["words"]])
        second_orig = " ".join([w["word"] for w in original_sentences[1]["words"]])
        
        first_time = original_sentences[0]["end"] - original_sentences[0]["start"]
        second_time = original_sentences[1]["end"] - original_sentences[1]["start"]
        
        # 计算原始句子的时间比例
        total_time = first_time + second_time
        first_ratio = first_time / total_time
        
        logger.info(f"原始句子时间比例: 第一句 {first_ratio:.2f}, 第二句 {1-first_ratio:.2f}")
        logger.info(f"原始句子字符比例: 第一句 {len(first_orig)}/{len(first_orig)+len(second_orig)}={len(first_orig)/(len(first_orig)+len(second_orig)):.2f}, 第二句 {len(second_orig)/(len(first_orig)+len(second_orig)):.2f}")
        
        # 根据目标语言选择不同的拆分策略
        if target_language in ['ja', 'zh']:  # 日语或中文
            # 尝试按句号拆分
            if '。' in translated_text:
                parts = translated_text.split('。')
                # 过滤空字符串并重新添加句号
                parts = [p.strip() + '。' for p in parts if p.strip()]
                
                # 如果拆分后的句子数量正好是2，直接返回
                if len(parts) == 2:
                    logger.info("按句号成功拆分为2个句子")
                    
                    # 验证拆分后的内容是否与原始翻译内容一致
                    combined = ''.join(parts)
                    # 移除所有空格后比较
                    translated_no_space = ''.join(translated_text.split())
                    combined_no_space = ''.join(combined.split())
                    
                    if combined_no_space != translated_no_space:
                        logger.warning("拆分后的内容与原始翻译内容不一致，尝试其他方法")
                    else:
                        return parts
                
                # 如果拆分后的句子数量大于2，需要合并
                elif len(parts) > 2:
                    logger.info(f"按句号拆分得到{len(parts)}个句子，需要合并")
                    # 计算合并点
                    merge_point = max(1, int(len(parts) * first_ratio))
                    first_part = ''.join(parts[:merge_point])
                    second_part = ''.join(parts[merge_point:])
                    
                    # 验证拆分后的内容是否与原始翻译内容一致
                    combined = first_part + second_part
                    # 移除所有空格后比较
                    translated_no_space = ''.join(translated_text.split())
                    combined_no_space = ''.join(combined.split())
                    
                    if combined_no_space != translated_no_space:
                        logger.warning("拆分后的内容与原始翻译内容不一致，尝试其他方法")
                    else:
                        return [first_part, second_part]
            
            # 如果没有句号或拆分后句子数量不足，尝试按长度比例拆分
            # 计算拆分点
            split_point = int(len(translated_text) * first_ratio)
            
            # 尝试在拆分点附近找一个更好的分割位置（如逗号、顿号等）
            window = min(20, len(translated_text) // 4)  # 搜索窗口大小
            best_split = split_point
            
            # 在拆分点附近搜索标点符号
            for i in range(max(0, split_point - window), min(len(translated_text), split_point + window)):
                if translated_text[i] in ['、', '，', '。', '！', '？', ' ']:
                    # 找到标点符号，更新拆分点
                    best_split = i + 1  # +1 是为了包含标点符号
                    break
            
            first_part = translated_text[:best_split].strip()
            second_part = translated_text[best_split:].strip()
            
            logger.info(f"按比例拆分: 第一部分 {len(first_part)} 字符, 第二部分 {len(second_part)} 字符")
            return [first_part, second_part]
            
        else:  # 其他语言
            # 尝试按句号、问号、感叹号拆分
            for char in ['. ', '! ', '? ']:
                if char in translated_text:
                    parts = []
                    current = ""
                    for part in translated_text.split(char):
                        if current:
                            parts.append(current + char.strip())
                            current = part.strip()
                        else:
                            current = part.strip()
                    
                    if current:  # 添加最后一部分
                        parts.append(current)
                    
                    # 如果拆分后的句子数量正好是2，直接返回
                    if len(parts) == 2:
                        logger.info(f"按'{char}'成功拆分为2个句子")
                        return parts
                    
                    # 如果拆分后的句子数量大于2，需要合并
                    elif len(parts) > 2:
                        logger.info(f"按'{char}'拆分得到{len(parts)}个句子，需要合并")
                        # 计算合并点
                        merge_point = max(1, int(len(parts) * first_ratio))
                        first_part = ' '.join(parts[:merge_point])
                        second_part = ' '.join(parts[merge_point:])
                        return [first_part, second_part]
            
            # 如果没有找到合适的标点符号，按长度比例拆分
            split_point = int(len(translated_text) * first_ratio)
            
            # 尝试在拆分点附近找一个更好的分割位置（如空格）
            window = min(20, len(translated_text) // 4)  # 搜索窗口大小
            best_split = split_point
            
            # 在拆分点附近搜索空格
            for i in range(max(0, split_point - window), min(len(translated_text), split_point + window)):
                if translated_text[i] == ' ':
                    # 找到空格，更新拆分点
                    best_split = i
                    break
            
            first_part = translated_text[:best_split].strip()
            second_part = translated_text[best_split:].strip()
            
            logger.info(f"按比例拆分: 第一部分 {len(first_part)} 字符, 第二部分 {len(second_part)} 字符")
            return [first_part, second_part]
    
    # 如果原始句子数量大于2，使用更通用的方法
    # 这里可以根据需要实现更复杂的逻辑
    # 目前简单地按比例拆分
    result = []
    total_length = len(translated_text)
    
    for i, orig_sentence in enumerate(original_sentences):
        # 计算当前句子在原始文本中的比例
        orig_words = [w["word"] for w in orig_sentence["words"]]
        orig_text = " ".join(orig_words)
        
        # 如果是最后一个句子，直接取剩余部分
        if i == len(original_sentences) - 1:
            start_idx = int(total_length * (i / len(original_sentences)))
            result.append(translated_text[start_idx:].strip())
        else:
            start_idx = int(total_length * (i / len(original_sentences)))
            end_idx = int(total_length * ((i + 1) / len(original_sentences)))
            result.append(translated_text[start_idx:end_idx].strip())
    
    return result
