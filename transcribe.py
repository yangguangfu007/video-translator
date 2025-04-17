import time
import json
import boto3
import urllib.request
from logger import get_logger

# 获取 logger
logger = get_logger()

def transcribe_video(transcribe_client, bucket_name, video_s3_key, language_code):
    """
    Transcribe the audio from a video file.
    
    Args:
        transcribe_client: AWS Transcribe client
        bucket_name: S3 bucket name
        video_s3_key: S3 key for the video file
        language_code: Language code for transcription (e.g., 'zh-CN', 'en-US')
        
    Returns:
        Dictionary with transcript text and word-level timing information
    """
    job_name = f"transcribe-{int(time.time())}"
    
    logger.info(f"Starting transcription job for video: {video_s3_key}")
    
    # Start the transcription job with corrected parameters
    if language_code and language_code.lower() != 'auto':
        logger.info(f"Using specified language: {language_code}")
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': f"s3://{bucket_name}/{video_s3_key}"},
            MediaFormat='mp4',
            LanguageCode=language_code,
            Settings={
                'ShowSpeakerLabels': False,
                'ShowAlternatives': False
            }
        )
    else:
        logger.info("Using automatic language identification")
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': f"s3://{bucket_name}/{video_s3_key}"},
            MediaFormat='mp4',
            IdentifyLanguage=True,
            Settings={
                'ShowSpeakerLabels': False,
                'ShowAlternatives': False
            }
        )
    
    logger.info(f"Started transcription job: {job_name}")
    
    # Wait for the job to complete
    while True:
        status = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
        job_status = status['TranscriptionJob']['TranscriptionJobStatus']
        logger.info(f"Transcription job status: {job_status}")
        
        if job_status in ['COMPLETED', 'FAILED']:
            break
        time.sleep(5)
    
    if job_status == 'FAILED':
        failure_reason = status['TranscriptionJob'].get('FailureReason', 'Unknown error')
        logger.error(f"Transcription job failed: {failure_reason}")
        raise Exception(f"Transcription job failed: {failure_reason}")
    
    # Get the transcript URI directly from the job result
    transcript_uri = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
    logger.info(f"Transcript URI: {transcript_uri}")
    
    # Download the transcript directly from the URI
    with urllib.request.urlopen(transcript_uri) as response:
        transcript_data = json.loads(response.read().decode('utf-8'))
    
    # Extract the transcript text and word-level timing information
    transcript_text = transcript_data['results']['transcripts'][0]['transcript']
    
    # 输出识别出的全部文字
    logger.info("\n===== 识别出的原始文字 =====")
    logger.info(transcript_text)
    logger.info("===== 识别出的原始文字结束 =====\n")
    
    # Get the detected language if auto-detection was used
    detected_language = transcript_data['results'].get('language_code', language_code)
    logger.info(f"Detected language: {detected_language}")
    
    # Extract word-level timing information
    words = []
    for item in transcript_data['results'].get('items', []):
        if item['type'] == 'pronunciation':
            word_info = {
                'word': item['alternatives'][0]['content'],
                'start_time': float(item.get('start_time', 0)),
                'end_time': float(item.get('end_time', 0))
            }
            words.append(word_info)
    
    logger.info(f"Transcription completed. Extracted {len(words)} words.")
    
    # Return the transcript and word-level timing information
    return {
        "transcript": transcript_text,
        "words": words,
        "detected_language": detected_language
    }
