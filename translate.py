import boto3
import json
import time
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
        # Create the prompt for translation with the required Claude format
        prompt = f"Human: Translate the following {source_lang_name} text to {target_lang_name}. Only provide the translation, without any additional text or explanations:\n\n{chunk}\n\nAssistant:"
        
        # Call Bedrock with Claude model
        response = bedrock_client.invoke_model(
            modelId="anthropic.claude-v2",
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 8000,
                "temperature": 0.1
            })
        )
        
        # Parse the response
        response_body = json.loads(response["body"].read())
        translated_text = response_body["completion"].strip()
        
        # Remove any "Assistant:" prefix that might be in the response
        if translated_text.startswith("Assistant:"):
            translated_text = translated_text[len("Assistant:"):].strip()
        
        translated_chunks.append(translated_text)
    
    # Combine the translated chunks
    return " ".join(translated_chunks)

# For backward compatibility
def translate_content(translate_client, transcript, target_language, source_language, use_bedrock=False):
    """
    Backward compatibility wrapper for translate_text.
    """
    bedrock_client = None
    if use_bedrock:
        try:
            import boto3
            bedrock_client = boto3.client('bedrock-runtime')
            logger.info("Successfully initialized Bedrock client")
        except Exception as e:
            logger.error(f"Error initializing Bedrock client: {str(e)}")
    
    return translate_text(translate_client, bedrock_client, transcript, source_language, target_language)
