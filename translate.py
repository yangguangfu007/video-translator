import json
import os
import boto3
from logger import get_logger

# 获取 logger
logger = get_logger()

def translate_text(translate_client, bedrock_client, transcript_data, source_language, target_language):
    """
    Translate text using Amazon Translate or Amazon Bedrock.
    
    Args:
        translate_client: AWS Translate client
        bedrock_client: AWS Bedrock client (optional)
        transcript_data: Dictionary containing transcript data
        source_language: Source language code
        target_language: Target language code
        
    Returns:
        Dictionary containing translated text and timing information
    """
    try:
        # Get the transcript text
        transcript = transcript_data["transcript"]
        
        # Log the transcript length
        logger.info(f"Translating text of length {len(transcript)}")
        
        # Check if we should use Bedrock
        use_bedrock = bedrock_client is not None
        
        if use_bedrock:
            logger.info("Using Amazon Bedrock for translation")
            translated_text = translate_with_bedrock(bedrock_client, transcript, source_language, target_language)
        else:
            logger.info("Using Amazon Translate for translation")
            translated_text = translate_with_amazon_translate(translate_client, transcript, source_language, target_language)
        
        # 输出翻译后的全部文字
        logger.info("\n===== 翻译后的文字 =====")
        logger.info(translated_text)
        logger.info("===== 翻译后的文字结束 =====\n")
        
        # 分析原始文本和翻译文本的结构
        logger.info("\n===== 文本结构分析 =====")
        # 分析原始文本
        logger.info(f"原始文本长度: {len(transcript)} 字符")
        orig_sentences_count = transcript.count('。') + transcript.count('.') + transcript.count('!') + transcript.count('?')
        logger.info(f"原始文本句子数量估计: {orig_sentences_count} (基于标点符号)")
        
        # 分析翻译文本
        logger.info(f"翻译文本长度: {len(translated_text)} 字符")
        trans_sentences_count = translated_text.count('。') + translated_text.count('.') + translated_text.count('!') + translated_text.count('?')
        logger.info(f"翻译文本句子数量估计: {trans_sentences_count} (基于标点符号)")
        
        # 检查是否有明显的句子结构不匹配
        if abs(orig_sentences_count - trans_sentences_count) > 1:
            logger.warning(f"警告: 原始文本和翻译文本的句子结构可能不匹配 (原始: {orig_sentences_count}, 翻译: {trans_sentences_count})")
        logger.info("===== 文本结构分析结束 =====\n")
        
        # Return the translated data
        return {
            "transcript": transcript,
            "translated": translated_text,
            "words": transcript_data["words"],
            "source_language": source_language,
            "target_language": target_language
        }
    
    except Exception as e:
        logger.error(f"Error in translate_text: {str(e)}")
        raise

def translate_with_amazon_translate(translate_client, text, source_language, target_language):
    """
    Translate text using Amazon Translate.
    
    Args:
        translate_client: AWS Translate client
        text: Text to translate
        source_language: Source language code
        target_language: Target language code
        
    Returns:
        Translated text
    """
    # Amazon Translate has a limit of 10,000 characters per request
    # Split the text into chunks if necessary
    max_chunk_size = 9000  # Slightly less than the limit to be safe
    chunks = [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]
    
    translated_chunks = []
    for i, chunk in enumerate(chunks):
        logger.info(f"Translating chunk {i+1}/{len(chunks)} ({len(chunk)} characters)")
        response = translate_client.translate_text(
            Text=chunk,
            SourceLanguageCode=source_language,
            TargetLanguageCode=target_language
        )
        translated_chunks.append(response["TranslatedText"])
    
    # Combine the translated chunks
    return " ".join(translated_chunks)

def translate_with_bedrock(bedrock_client, text, source_language, target_language):
    """
    Translate text using Amazon Bedrock.
    
    Args:
        bedrock_client: AWS Bedrock client
        text: Text to translate
        source_language: Source language code
        target_language: Target language code
        
    Returns:
        Translated text
    """
    # Map language codes to full language names for Bedrock
    language_map = {
        "en": "English",
        "zh": "Chinese",
        "ja": "Japanese",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "ko": "Korean",
        "pt": "Portuguese",
        "es": "Spanish"
    }
    
    source_lang_name = language_map.get(source_language, "English")
    target_lang_name = language_map.get(target_language, "English")
    
    # Amazon Bedrock has a limit on input size
    # Split the text into chunks if necessary
    max_chunk_size = 4000  # Adjust based on model limits
    chunks = [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]
    
    translated_chunks = []
    for i, chunk in enumerate(chunks):
        logger.info(f"Translating chunk {i+1}/{len(chunks)} with Bedrock ({len(chunk)} characters)")
        
        # 使用 Messages API 格式调用 Claude 3.7 模型
        try:
            # 创建翻译提示
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Translate the following {source_lang_name} text to {target_lang_name}. Only provide the translation, without any additional text or explanations:\n\n{chunk}"
                        }
                    ]
                }
            ]
            
            # 调用 Bedrock 的 Messages API
            response = bedrock_client.invoke_model(
                modelId=os.getenv('BEDROCK_MODEL_ID', "anthropic.claude-3-7-sonnet-20250219"),
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 8000,
                    "temperature": 0.1,
                    "messages": messages
                })
            )
            
            # 解析响应
            response_body = json.loads(response["body"].read())
            translated_text = response_body["content"][0]["text"].strip()
            
            translated_chunks.append(translated_text)
            
        except Exception as e:
            logger.error(f"Error translating chunk with Bedrock: {str(e)}")
            # 如果 Bedrock 翻译失败，尝试使用 Amazon Translate 作为备选
            try:
                logger.info(f"Falling back to Amazon Translate for chunk {i+1}")
                translate_client = boto3.client('translate', region_name=os.getenv('AWS_REGION'))
                response = translate_client.translate_text(
                    Text=chunk,
                    SourceLanguageCode=source_language,
                    TargetLanguageCode=target_language
                )
                translated_chunks.append(response["TranslatedText"])
            except Exception as fallback_error:
                logger.error(f"Fallback translation also failed: {str(fallback_error)}")
                # 如果备选也失败，返回原文
                translated_chunks.append(chunk)
    
    # 合并翻译后的文本块
    return " ".join(translated_chunks)

# For backward compatibility
def translate_content(translate_client, bedrock_client, transcript, target_language, source_language, use_bedrock=False):
    """
    Backward compatibility wrapper for translate_text.
    """
    # 如果没有提供 bedrock_client 但需要使用 Bedrock，则创建一个
    if use_bedrock and bedrock_client is None:
        try:
            bedrock_client = boto3.client('bedrock-runtime', region_name=os.getenv('AWS_REGION'))
            logger.info("Successfully initialized Bedrock client")
        except Exception as e:
            logger.error(f"Error initializing Bedrock client: {str(e)}")
            bedrock_client = None
    
    return translate_text(translate_client, bedrock_client, transcript, source_language, target_language)
