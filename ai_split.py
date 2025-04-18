import os
import json
import boto3
from logger import get_logger

# 获取 logger
logger = get_logger()

def ai_split_sentences(translated_text, original_sentences, target_language, bedrock_client=None):
    """
    使用 Claude 3.7 AI 模型智能拆分翻译文本，确保与原始句子数量匹配。
    
    Args:
        translated_text: 翻译后的文本
        original_sentences: 原始句子列表
        target_language: 目标语言代码
        bedrock_client: Bedrock 客户端
        
    Returns:
        拆分后的翻译句子列表
    """
    # 如果没有提供 bedrock_client，尝试创建一个
    if bedrock_client is None:
        try:
            bedrock_client = boto3.client('bedrock-runtime', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            logger.info("成功初始化 Bedrock 客户端用于 AI 拆分")
        except Exception as e:
            logger.error(f"初始化 Bedrock 客户端失败: {str(e)}")
            # 如果无法创建 Bedrock 客户端，回退到手动拆分
            from manual_split import manual_split_sentences
            return manual_split_sentences(translated_text, original_sentences, target_language)
    
    # 获取原始句子的文本和时间信息
    original_texts = []
    time_ranges = []
    
    for sentence in original_sentences:
        text = " ".join([w["word"] for w in sentence["words"]])
        original_texts.append(text)
        time_ranges.append((sentence["start"], sentence["end"]))
    
    # 构建提示
    prompt = f"""你是一个专业的文本拆分助手。我需要你将翻译后的文本拆分成与原始文本相同数量的句子，确保内容对应。

原始文本（{len(original_sentences)}个句子）:
"""

    for i, text in enumerate(original_texts):
        start_time, end_time = time_ranges[i]
        duration = end_time - start_time
        prompt += f"句子{i+1} ({start_time:.2f}s-{end_time:.2f}s, 持续{duration:.2f}s): {text}\n"
    
    prompt += f"\n翻译文本（需要拆分成{len(original_sentences)}个句子）:\n{translated_text}\n\n"
    
    prompt += """请将翻译文本拆分成与原始文本相同数量的句子，确保内容对应。只返回拆分后的句子，每个句子一行，不要包含任何解释或额外文本。
例如:
句子1: [第一个句子的翻译]
句子2: [第二个句子的翻译]
...
"""

    # 调用 Claude 3.7 模型
    try:
        logger.info("调用 Claude 3.7 进行智能句子拆分")
        
        # 创建消息
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
        
        # 调用 Bedrock 的 Messages API
        response = bedrock_client.invoke_model(
            modelId=os.getenv('BEDROCK_MODEL_ID', "anthropic.claude-3-7-sonnet-20250219"),
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "temperature": 0.1,
                "messages": messages
            })
        )
        
        # 解析响应
        response_body = json.loads(response["body"].read())
        result_text = response_body["content"][0]["text"].strip()
        
        logger.info(f"Claude 3.7 返回的拆分结果:\n{result_text}")
        
        # 解析结果
        split_sentences = []
        for line in result_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            # 尝试提取句子内容
            if ':' in line:
                # 格式可能是 "句子1: 内容" 或 "1: 内容"
                sentence_content = line.split(':', 1)[1].strip()
                split_sentences.append(sentence_content)
            elif line.startswith('句子') and len(line) > 2:
                # 可能是 "句子1内容"
                split_sentences.append(line[2:].strip())
            else:
                # 可能是纯文本
                split_sentences.append(line)
        
        # 验证拆分后的内容是否与原始翻译内容一致
        combined = ''.join(split_sentences)
        # 移除所有空格后比较
        translated_no_space = ''.join(translated_text.split())
        combined_no_space = ''.join(combined.split())
        
        if combined_no_space != translated_no_space:
            logger.warning("AI 拆分后的内容与原始翻译内容不一致")
            logger.warning(f"原始翻译: {translated_text}")
            logger.warning(f"拆分后合并: {combined}")
            # 回退到手动拆分
            from manual_split import manual_split_sentences
            return manual_split_sentences(translated_text, original_sentences, target_language)
        
        # 确保拆分后的句子数量与原始句子数量相同
        if len(split_sentences) == len(original_sentences):
            logger.info(f"AI 成功拆分为 {len(split_sentences)} 个句子")
            return split_sentences
        else:
            logger.warning(f"AI 拆分结果句子数量 ({len(split_sentences)}) 与原始句子数量 ({len(original_sentences)}) 不匹配")
            # 如果句子数量不匹配，尝试手动调整
            if len(split_sentences) > len(original_sentences):
                # 合并多余的句子
                while len(split_sentences) > len(original_sentences):
                    # 找到最短的相邻句子对
                    min_length = float('inf')
                    min_index = 0
                    for i in range(len(split_sentences) - 1):
                        combined_length = len(split_sentences[i]) + len(split_sentences[i+1])
                        if combined_length < min_length:
                            min_length = combined_length
                            min_index = i
                    
                    # 合并这两个句子
                    split_sentences[min_index] = split_sentences[min_index] + " " + split_sentences[min_index + 1]
                    split_sentences.pop(min_index + 1)
                
                logger.info(f"合并后得到 {len(split_sentences)} 个句子")
                return split_sentences
            else:
                # 如果句子数量不足，回退到手动拆分
                logger.info("AI 拆分结果句子数量不足，回退到手动拆分")
                from manual_split import manual_split_sentences
                return manual_split_sentences(translated_text, original_sentences, target_language)
    
    except Exception as e:
        logger.error(f"AI 拆分失败: {str(e)}")
        # 如果 AI 拆分失败，回退到手动拆分
        from manual_split import manual_split_sentences
        return manual_split_sentences(translated_text, original_sentences, target_language)
