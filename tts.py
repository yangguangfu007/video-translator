import tempfile
import uuid
import os
import json
import time
import subprocess
from sentence_utils import extract_sentences, split_into_matching_sentences
from logger import get_logger

# 获取 logger
logger = get_logger()

def generate_speech(polly_client, s3_client, bucket_name, translated_data, voice_id, language_code):
    """
    Generate speech from translated text using Amazon Polly with consistent speech rate.
    
    Args:
        polly_client: AWS Polly client
        s3_client: AWS S3 client
        bucket_name: S3 bucket name
        translated_data: Dictionary containing translated text and timing information
        voice_id: Polly voice ID to use
        language_code: Language code for the voice
        
    Returns:
        S3 key for the generated audio file
    """
    try:
        # Get the translated text and original timing information
        translated_text = translated_data["translated"]
        original_words = translated_data["words"]
        
        # Language code mapping for Polly
        language_code_map = {
            "en": "en-US",
            "zh": "cmn-CN",  # 中文普通话
            "ja": "ja-JP",   # 日语
            "fr": "fr-FR",
            "de": "de-DE",
            "it": "it-IT",
            "ko": "ko-KR",
            "pt": "pt-BR",
            "es": "es-ES"
        }
        
        # Use the mapped language code if available
        target_language = translated_data.get("target_language", "en")
        polly_language_code = language_code_map.get(target_language, language_code)
        logger.info(f"Using Polly language code: {polly_language_code} for target language: {target_language}")
        
        # Check if the voice supports neural engine
        try:
            voice_info = None
            voices_response = polly_client.describe_voices(LanguageCode=polly_language_code)
            for voice in voices_response.get('Voices', []):
                if voice.get('Id') == voice_id:
                    voice_info = voice
                    break
            
            # Determine which engine to use
            engine = 'neural'
            if voice_info and 'SupportedEngines' in voice_info:
                if 'neural' not in voice_info['SupportedEngines']:
                    engine = 'standard'
                    logger.info(f"Voice {voice_id} does not support neural engine, using standard engine instead")
            else:
                # If we can't determine supported engines, try neural first, fall back to standard
                try:
                    # Test if neural works with a small sample
                    polly_client.synthesize_speech(
                        Text="Test",
                        OutputFormat='mp3',
                        VoiceId=voice_id,
                        Engine='neural',
                        LanguageCode=polly_language_code
                    )
                except Exception as e:
                    if "ValidationException" in str(e):
                        engine = 'standard'
                        logger.info(f"Voice {voice_id} does not support neural engine, using standard engine instead")
                    else:
                        raise
        except Exception as e:
            logger.error(f"Error checking voice capabilities: {str(e)}. Falling back to standard engine.")
            engine = 'standard'
        
        logger.info(f"Using engine: {engine} for voice: {voice_id}")
        
        # Print original and translated text lengths for diagnostics
        original_text = " ".join([word["word"] for word in original_words])
        logger.info(f"Original text length: {len(original_text)} characters")
        logger.info(f"Translated text length: {len(translated_text)} characters")
        logger.info(f"Original text sample: {original_text[:100]}...")
        logger.info(f"Translated text sample: {translated_text[:100]}...")
        
        # Get the duration of the original audio/video
        if original_words:
            max_end_time = max(word["end_time"] for word in original_words)
            logger.info(f"Original content duration: {max_end_time:.2f} seconds")
        else:
            logger.warning("WARNING: No original word timing information!")
            max_end_time = 0
        
        # If original content duration is 0, this is a serious issue
        if max_end_time <= 0:
            logger.error("ERROR: Original content duration is 0 or negative!")
            raise ValueError("Invalid original content duration")
        
        # Extract sentence boundaries from original transcript - using shared function
        original_sentences = extract_sentences(original_words)
        logger.info(f"Extracted {len(original_sentences)} sentences from original transcript")
        
        # 记录原始句子的内容，用于调试
        logger.info("\n===== 原始句子内容 =====")
        for i, orig_sentence in enumerate(original_sentences):
            orig_text = " ".join([w["word"] for w in orig_sentence["words"]])
            logger.info(f"原始句子 {i+1}: {orig_text}")
        logger.info("===== 原始句子内容结束 =====\n")
        
        # 记录翻译文本，用于调试
        logger.info("\n===== 完整翻译文本 =====")
        logger.info(translated_text)
        logger.info("===== 完整翻译文本结束 =====\n")
        
        # 尝试使用 AI 拆分方法
        try:
            from ai_split import ai_split_sentences
            # 获取 bedrock 客户端
            bedrock_client = None
            try:
                import boto3
                bedrock_client = boto3.client('bedrock-runtime', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                logger.info("成功初始化 Bedrock 客户端用于 AI 拆分")
            except Exception as e:
                logger.warning(f"初始化 Bedrock 客户端失败: {str(e)}")
            
            # 使用 AI 拆分
            translated_sentences = ai_split_sentences(translated_text, original_sentences, target_language, bedrock_client)
            logger.info(f"使用 AI 拆分方法，得到 {len(translated_sentences)} 个句子")
        except Exception as e:
            logger.error(f"AI 拆分失败: {str(e)}，回退到手动拆分")
            # 回退到手动拆分
            try:
                from manual_split import manual_split_sentences
                translated_sentences = manual_split_sentences(translated_text, original_sentences, target_language)
                logger.info(f"使用手动拆分方法，得到 {len(translated_sentences)} 个句子")
            except Exception as e2:
                logger.error(f"手动拆分也失败: {str(e2)}，回退到自动拆分")
                # 回退到原来的拆分方法
                translated_sentences = split_into_matching_sentences(translated_text, len(original_sentences))
                logger.info(f"Split translated text into {len(translated_sentences)} sentences")
        
        # 输出拆分后的原文和翻译文本
        logger.info("\n===== 拆分后的句子对照 =====")
        for i, (orig_sentence, trans_sentence) in enumerate(zip(original_sentences, translated_sentences)):
            # 获取原始句子的文本
            orig_text = " ".join([w["word"] for w in orig_sentence["words"]])
            logger.info(f"句子 {i+1}:")
            logger.info(f"  时间范围: {orig_sentence['start']:.2f}s - {orig_sentence['end']:.2f}s")
            logger.info(f"  原文: {orig_text}")
            logger.info(f"  译文: {trans_sentence}")
            logger.info("---")
        logger.info("===== 拆分后的句子对照结束 =====\n")
        
        # Create a temporary directory for audio files
        temp_dir = tempfile.mkdtemp()
        
        # Create a silent base audio track that's as long as the original audio/video
        silent_path = os.path.join(temp_dir, "silent_base.wav")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(max_end_time), silent_path
        ], check=True)
        
        # Generate individual audio files for each sentence
        audio_segments = []
        
        # 打印更多调试信息
        logger.info("\n===== 句子匹配调试信息 =====")
        logger.info(f"原始句子数量: {len(original_sentences)}")
        logger.info(f"翻译句子数量: {len(translated_sentences)}")
        
        # 检查句子长度是否匹配
        if len(original_sentences) != len(translated_sentences):
            logger.warning(f"警告: 原始句子数量 ({len(original_sentences)}) 与翻译句子数量 ({len(translated_sentences)}) 不匹配!")
        
        # 打印每个句子的详细信息
        for i in range(max(len(original_sentences), len(translated_sentences))):
            logger.info(f"\n句子 {i+1} 详细信息:")
            
            # 打印原始句子信息
            if i < len(original_sentences):
                orig_sentence = original_sentences[i]
                orig_text = " ".join([w["word"] for w in orig_sentence["words"]])
                orig_start = orig_sentence["start"]
                orig_end = orig_sentence["end"]
                orig_duration = orig_end - orig_start
                logger.info(f"  原始句子: {orig_text}")
                logger.info(f"  原始时间范围: {orig_start:.2f}s - {orig_end:.2f}s (持续时间: {orig_duration:.2f}s)")
            else:
                logger.info("  原始句子: [超出索引范围]")
            
            # 打印翻译句子信息
            if i < len(translated_sentences):
                trans_sentence = translated_sentences[i]
                logger.info(f"  翻译句子: {trans_sentence}")
                logger.info(f"  翻译句子长度: {len(trans_sentence)} 字符")
            else:
                logger.info("  翻译句子: [超出索引范围]")
        
        logger.info("===== 句子匹配调试信息结束 =====\n")
        
        # 打印zip后的匹配情况
        logger.info("\n===== ZIP匹配后的句子对照 =====")
        for i, (sentence, timing) in enumerate(zip(translated_sentences, original_sentences)):
            orig_text = " ".join([w["word"] for w in timing["words"]])
            logger.info(f"匹配 {i+1}:")
            logger.info(f"  原文: {orig_text}")
            logger.info(f"  译文: {sentence}")
            logger.info(f"  时间范围: {timing['start']:.2f}s - {timing['end']:.2f}s")
            logger.info("---")
        logger.info("===== ZIP匹配后的句子对照结束 =====\n")
        
        for i, (sentence, timing) in enumerate(zip(translated_sentences, original_sentences)):
            try:
                if not sentence.strip():  # Skip empty sentences
                    logger.info(f"跳过空句子 {i}")
                    continue
                
                # 获取原始句子的文本
                orig_text = " ".join([w["word"] for w in timing["words"]])
                
                # Generate speech for this sentence
                sentence_audio_path = os.path.join(temp_dir, f"sentence_{i}.mp3")
                
                # Use the determined engine
                response = polly_client.synthesize_speech(
                    Text=sentence,
                    OutputFormat='mp3',
                    VoiceId=voice_id,
                    Engine=engine,
                    LanguageCode=polly_language_code
                )
                
                # Save the audio to a file
                with open(sentence_audio_path, 'wb') as f:
                    f.write(response['AudioStream'].read())
                
                # Get the duration of the generated audio
                duration = get_audio_duration(sentence_audio_path)
                if duration <= 0:
                    logger.warning(f"WARNING: Audio for sentence {i} has zero duration, skipping")
                    continue
                
                # 输出音频片段信息
                logger.info(f"\n生成音频片段 {i+1}:")
                logger.info(f"  时间范围: {timing['start']:.2f}s - {timing['end']:.2f}s")
                logger.info(f"  原文: {orig_text}")
                logger.info(f"  译文: {sentence}")
                logger.info(f"  生成的音频时长: {duration:.2f}s")
                
                # Store information about this audio segment
                audio_segments.append({
                    "path": sentence_audio_path,
                    "start": timing["start"],
                    "end": timing["end"],
                    "duration": duration,
                    "text": sentence,
                    "index": i
                })
            
            except Exception as e:
                logger.error(f"处理句子 {i} 时出错: {str(e)}")
                # Continue with the next sentence instead of breaking the whole process
                continue
        
        # Sort audio segments by start time
        audio_segments.sort(key=lambda x: x["start"])
        
        # Create a temporary file for the final audio
        final_audio_path = os.path.join(temp_dir, "final_audio.mp3")
        
        # Check if we have any audio segments
        if not audio_segments:
            logger.warning("No audio segments were generated. Creating an empty audio file.")
            # Create an empty audio file with the same duration as the original
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", str(max_end_time), "-c:a", "libmp3lame", "-q:a", "2", final_audio_path
            ], check=True)
        else:
            # Use a simpler approach: create a filter complex to place each audio at its exact time
            inputs = ["-i", silent_path]
            filter_complex = ""
            
            # 检查是否有重叠的音频片段
            for i in range(len(audio_segments)-1):
                current = audio_segments[i]
                next_seg = audio_segments[i+1]
                
                # 如果当前片段的结束时间超过了下一个片段的开始时间-2s，调整当前片段的结束时间
                if current["start"] + current["duration"] - 2> next_seg["start"]:
                    logger.warning(f"检测到音频重叠: 片段 {i+1} 结束时间 ({current['start'] + current['duration']:.2f}s) 超过了片段 {i+2} 开始时间 ({next_seg['start']:.2f}s)")
                    logger.info("采用顺序播放策略，重新计算音频时间")
                    
                    # 重新计算所有片段的开始和结束时间，采用顺序播放策略
                    current_time = 0
                    for j, segment in enumerate(audio_segments):
                        # 记录原始时间信息，用于调试
                        orig_start = segment["start"]
                        orig_end = orig_start + segment["duration"]
                        
                        # 更新为顺序播放的时间
                        segment["sequential_start"] = current_time
                        segment["sequential_end"] = current_time + segment["duration"]
                        
                        logger.info(f"片段 {j+1}: 原始时间 {orig_start:.2f}s-{orig_end:.2f}s -> 顺序时间 {segment['sequential_start']:.2f}s-{segment['sequential_end']:.2f}s")
                        
                        # 更新当前时间
                        current_time += segment["duration"] + 0.1  # 添加0.1秒间隔
                    
                    # 设置标志，表示使用顺序播放策略
                    use_sequential_timing = True
                    break
            else:
                # 如果没有检测到重叠，使用原始时间
                use_sequential_timing = False
                logger.info("未检测到音频重叠，使用原始时间策略")
            
            # 使用一个更简单的方法：创建一个静音音频，然后在适当的时间点添加每个音频片段
            inputs = ["-i", silent_path]
            filter_complex = ""
            
            # 添加所有音频输入
            for i, audio in enumerate(audio_segments):
                inputs.extend(["-i", audio["path"]])
                
                # 根据播放策略选择延迟时间
                if use_sequential_timing:
                    delay_ms = int(audio["sequential_start"] * 1000)
                else:
                    # 使用原始时间
                    delay_ms = int(audio["start"] * 1000)
                
                # Add audio at the exact start time
                filter_complex += f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[a{i}];"
            
            # Mix all audio streams
            for i in range(len(audio_segments)):
                filter_complex += f"[a{i}]"
            
            # Complete the filter complex with volume adjustment in the same complex filter
            filter_complex += f"[0:a]amix=inputs={len(audio_segments)+1}:duration=longest[aout];[aout]volume=2.0[afinal]"
            
            # Run ffmpeg command to combine all audio files
            cmd = ["ffmpeg", "-y"] + inputs + [
                "-filter_complex", filter_complex,
                "-map", "[afinal]",
                "-c:a", "libmp3lame", "-q:a", "2",
                "-t", str(max_end_time),  # Explicitly limit output duration to match original
                final_audio_path
            ]
            
            logger.info(f"Running FFmpeg command to combine {len(audio_segments)} audio files")
            subprocess.run(cmd, check=True)
        
        # Verify the final audio duration
        final_duration = get_audio_duration(final_audio_path)
        logger.info(f"Final audio duration: {final_duration:.2f}s (original: {max_end_time:.2f}s)")
        
        # 如果使用了顺序播放策略，保存音频时间信息，供字幕使用
        if use_sequential_timing:
            audio_timing = []
            for segment in audio_segments:
                audio_timing.append({
                    "index": segment["index"],
                    "sequential_start": segment["sequential_start"],
                    "sequential_end": segment["sequential_end"],
                    "original_start": segment["start"],
                    "original_end": segment["start"] + segment["duration"],
                    "duration": segment["duration"]
                })
            logger.info(f"生成顺序播放时间信息，共 {len(audio_timing)} 条")
        else:
            audio_timing = None
        
        # Upload the audio file to S3
        audio_s3_key = f"audio/{uuid.uuid4()}.mp3"
        s3_client.upload_file(final_audio_path, bucket_name, audio_s3_key)
        logger.info(f"Uploaded final audio to S3: {audio_s3_key}")
        
        # Clean up temporary files
        try:
            # First remove all files in the temp directory
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        import shutil
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {str(e)}")
            
            # Then remove the directory itself
            os.rmdir(temp_dir)
        except Exception as e:
            logger.error(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
            # This is not a critical error, so we can continue
        
        # 返回音频S3键和时间信息
        return audio_s3_key, audio_timing
    
    except Exception as e:
        logger.error(f"Error in generate_speech: {str(e)}")
        raise

def get_audio_duration(audio_path):
    """
    Get the duration of an audio file using ffprobe.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        Duration in seconds
    """
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", audio_path
    ]
    
    try:
        output = subprocess.check_output(cmd).decode('utf-8')
        data = json.loads(output)
        return float(data["format"]["duration"])
    except Exception as e:
        logger.error(f"Error getting audio duration: {str(e)}")
        return 0
