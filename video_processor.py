import uuid
import time
import boto3
import json
import os
import tempfile
import subprocess
import shutil
from logger import get_logger

# 获取 logger
logger = get_logger()

def process_video(mediaconvert_client, s3_client, bucket_name, video_s3_key, audio_s3_key, subtitle_s3_key, role_arn, high_quality=True, force_local=False, local_video_path=None):
    """
    Process the video by replacing audio and adding subtitles.
    
    Args:
        mediaconvert_client: AWS MediaConvert client
        s3_client: AWS S3 client
        bucket_name: S3 bucket name
        video_s3_key: S3 key for the input video
        audio_s3_key: S3 key for the generated audio
        subtitle_s3_key: S3 key for the subtitle file (or None if no subtitles)
        role_arn: ARN for the MediaConvert role
        high_quality: Whether to use high quality settings
        force_local: Whether to force local processing with FFmpeg
        local_video_path: Path to the local video file (if available)
        
    Returns:
        Dictionary containing S3 key and local path for the output video
    """
    # If force_local is True, use local processing
    if force_local:
        print("Forced local FFmpeg processing...")
        return process_locally(s3_client, bucket_name, video_s3_key, audio_s3_key, subtitle_s3_key, high_quality, local_video_path)
    
    # Otherwise, try MediaConvert first
    try:
        print("Using AWS MediaConvert for video processing...")
        result = process_with_mediaconvert(mediaconvert_client, s3_client, bucket_name, video_s3_key, audio_s3_key, subtitle_s3_key, role_arn, high_quality)
        return result
    except Exception as e:
        print(f"MediaConvert processing failed: {str(e)}. Falling back to local processing...")
        return process_locally(s3_client, bucket_name, video_s3_key, audio_s3_key, subtitle_s3_key, high_quality, local_video_path)

def process_with_mediaconvert(mediaconvert_client, s3_client, bucket_name, video_s3_key, audio_s3_key, subtitle_s3_key, role_arn, high_quality=True):
    """
    Process the video using AWS MediaConvert.
    
    Returns:
        Dictionary containing S3 key and local path for the output video
    """
    try:
        # Create a unique output key
        output_key_prefix = f"output/mediaconvert_{uuid.uuid4()}"
        output_s3_key = f"{output_key_prefix}.mp4"
        
        # Create a job settings dictionary
        job_settings = {
            "Inputs": [
                {
                    "FileInput": f"s3://{bucket_name}/{video_s3_key}",
                    "AudioSelectors": {
                        "Audio Selector 1": {
                            "DefaultSelection": "DEFAULT"
                        }
                    },
                    "VideoSelector": {},
                    "TimecodeSource": "EMBEDDED"
                }
            ],
            "OutputGroups": [
                {
                    "Name": "File Group",
                    "OutputGroupSettings": {
                        "Type": "FILE_GROUP_SETTINGS",
                        "FileGroupSettings": {
                            "Destination": f"s3://{bucket_name}/{output_key_prefix}.mp4"
                        }
                    },
                    "Outputs": [
                        {
                            "VideoDescription": {
                                "CodecSettings": {
                                    "Codec": "H_264",
                                    "H264Settings": {
                                        "RateControlMode": "QVBR",
                                        "QvbrSettings": {
                                            "QvbrQualityLevel": 8 if high_quality else 6
                                        },
                                        "CodecProfile": "HIGH",
                                        "CodecLevel": "AUTO"
                                    }
                                }
                            },
                            "AudioDescriptions": [
                                {
                                    "CodecSettings": {
                                        "Codec": "AAC",
                                        "AacSettings": {
                                            "Bitrate": 192000 if high_quality else 128000,
                                            "CodecProfile": "LC",
                                            "CodingMode": "CODING_MODE_2_0",
                                            "SampleRate": 48000
                                        }
                                    },
                                    "AudioSourceName": "Audio Selector 1"
                                }
                            ],
                            "ContainerSettings": {
                                "Container": "MP4",
                                "Mp4Settings": {}
                            }
                        }
                    ]
                }
            ],
            "TimecodeConfig": {
                "Source": "EMBEDDED"
            }
        }
        
        # Add audio file as input
        job_settings["Inputs"].append({
            "FileInput": f"s3://{bucket_name}/{audio_s3_key}",
            "AudioSelectors": {
                "Audio Selector 1": {
                    "DefaultSelection": "DEFAULT"
                }
            },
            "TimecodeSource": "EMBEDDED"
        })
        
        # Update audio source to use the second input (from the second input file)
        job_settings["OutputGroups"][0]["Outputs"][0]["AudioDescriptions"][0]["AudioSourceName"] = "Audio Selector 1"
        # Note: AudioSelectorName is not a valid parameter, removed
        
        # Add subtitle if provided
        if subtitle_s3_key:
            # Add caption selector to the first input
            job_settings["Inputs"][0]["CaptionSelectors"] = {
                "Caption Selector 1": {
                    "SourceSettings": {
                        "SourceType": "SRT",
                        "FileSourceSettings": {
                            "SourceFile": f"s3://{bucket_name}/{subtitle_s3_key}"
                        }
                    }
                }
            }
            
            # Add caption description to the output with improved settings
            job_settings["OutputGroups"][0]["Outputs"][0]["CaptionDescriptions"] = [
                {
                    "CaptionSelectorName": "Caption Selector 1",
                    "DestinationSettings": {
                        "DestinationType": "BURN_IN",
                        "BurnInSettings": {
                            "BackgroundColor": "BLACK",
                            "BackgroundOpacity": 60,
                            "FontColor": "WHITE",
                            "FontOpacity": 100,
                            "OutlineColor": "BLACK",
                            "OutlineSize": 2
                        }
                    }
                }
            ]
        
        # Create the job
        response = mediaconvert_client.create_job(
            Role=role_arn,
            Settings=job_settings
        )
        
        job_id = response['Job']['Id']
        print(f"MediaConvert job created with ID: {job_id}")
        
        # Wait for the job to complete
        while True:
            job_response = mediaconvert_client.get_job(Id=job_id)
            status = job_response['Job']['Status']
            
            if status == 'COMPLETE':
                print("MediaConvert job completed successfully")
                break
            elif status in ['ERROR', 'CANCELED']:
                error_message = job_response['Job'].get('ErrorMessage', 'Unknown error')
                raise Exception(f"MediaConvert job failed: {error_message}")
            
            print(f"MediaConvert job status: {status}")
            time.sleep(10)
        
        # Download the processed video to local directory
        local_output_dir = os.path.expanduser("~/video_translator_output")
        os.makedirs(local_output_dir, exist_ok=True)
        local_output_path = os.path.join(local_output_dir, f"translated_video_{int(time.time())}.mp4")
        
        # Download the processed video from S3
        s3_client.download_file(bucket_name, output_s3_key, local_output_path)
        print(f"Downloaded processed video to: {local_output_path}")
        
        return {
            "s3_key": output_s3_key,
            "local_path": local_output_path
        }
    
    except Exception as e:
        print(f"Error in MediaConvert processing: {str(e)}")
        raise

def process_locally(s3_client, bucket_name, video_s3_key, audio_s3_key, subtitle_s3_key, high_quality=True, local_video_path=None):
    """
    Process the video locally using FFmpeg.
    
    Args:
        s3_client: AWS S3 client
        bucket_name: S3 bucket name
        video_s3_key: S3 key for the input video
        audio_s3_key: S3 key for the generated audio
        subtitle_s3_key: S3 key for the subtitle file (or None if no subtitles)
        high_quality: Whether to use high quality settings
        local_video_path: Path to the local video file (if available)
        
    Returns:
        Dictionary containing S3 key and local path for the output video
    """
    try:
        # Create temporary directory for all files
        temp_dir = tempfile.mkdtemp()
        
        # Create paths for temporary files
        temp_video_path = os.path.join(temp_dir, "input_video.mp4")
        temp_audio_path = os.path.join(temp_dir, "translated_audio.mp3")
        temp_output_path = os.path.join(temp_dir, "output.mp4")
        
        # Create a local output directory in the user's home directory
        local_output_dir = os.path.expanduser("~/video_translator_output")
        os.makedirs(local_output_dir, exist_ok=True)
        
        # Create a unique local output path
        local_output_path = os.path.join(local_output_dir, f"translated_video_{int(time.time())}.mp4")
        
        # Use local video file if available, otherwise download from S3
        if local_video_path and os.path.exists(local_video_path):
            logger.info(f"Using local video file: {local_video_path}")
            shutil.copy2(local_video_path, temp_video_path)
        else:
            logger.info(f"Downloading video from S3: {video_s3_key}")
            s3_client.download_file(bucket_name, video_s3_key, temp_video_path)
        
        logger.info(f"Downloading audio from S3: {audio_s3_key}")
        s3_client.download_file(bucket_name, audio_s3_key, temp_audio_path)
        
        # Download subtitle file if provided
        temp_subtitle_path = None
        if subtitle_s3_key:
            temp_subtitle_path = os.path.join(temp_dir, "subtitle.srt")
            s3_client.download_file(bucket_name, subtitle_s3_key, temp_subtitle_path)
            
            logger.info(f"Downloaded subtitle from S3: {subtitle_s3_key}")
            
            # 输出字幕文件内容
            logger.info("\n===== 字幕文件内容 =====")
            try:
                with open(temp_subtitle_path, 'r', encoding='utf-8') as f:
                    subtitle_content = f.read()
                    logger.info(subtitle_content)
            except Exception as e:
                logger.error(f"读取字幕文件时出错: {str(e)}")
            logger.info("===== 字幕文件内容结束 =====\n")
            
            # Fix subtitle encoding if needed
            fix_subtitle_encoding(temp_subtitle_path)
        
        # Create a version of the video with no audio
        temp_video_no_audio_path = os.path.join(temp_dir, "video_no_audio.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", temp_video_path, "-an",
            "-c:v", "copy", temp_video_no_audio_path
        ], check=True)
        
        # Now combine the video with the audio and subtitles
        if temp_subtitle_path:
            logger.info("Processing video with FFmpeg (with subtitles)...")
            
            # Get video dimensions
            video_info_cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-select_streams", "v:0", temp_video_path
            ]
            video_info = json.loads(subprocess.check_output(video_info_cmd).decode())
            video_width = int(video_info["streams"][0]["width"])
            video_height = int(video_info["streams"][0]["height"])
            
            # Calculate appropriate font size based on video dimensions - medium size
            font_size = max(16, min(20, int(video_height / 30)))  # Medium font size
            
            # Create a temporary SRT file with proper formatting
            temp_formatted_srt = os.path.join(temp_dir, "formatted_subtitle.srt")
            format_srt_file(temp_subtitle_path, temp_formatted_srt)
            
            # 使用 ASS 格式字幕，可以更好地控制字幕显示和消失
            temp_ass_path = os.path.join(temp_dir, "subtitle.ass")
            
            # 将 SRT 转换为 ASS 格式，设置字体大小和位置
            font_size = max(16, min(24, int(video_height / 25)))  # 适当增大字体
            line_spacing = int(font_size * 1.5)  # 行间距
            margin_v = int(video_height / 10)  # 底部边距
            
            # 使用 FFmpeg 的 subtitles 滤镜将 SRT 转换为 ASS 并应用样式
            subprocess.run([
                "ffmpeg", "-y",
                "-i", temp_formatted_srt,
                "-c:s", "ass",
                temp_ass_path
            ], check=True)
            
            # 使用 ASS 字幕滤镜，提供更好的字幕控制
            subprocess.run([
                "ffmpeg", "-y", 
                "-i", temp_video_no_audio_path,  # Video with no audio
                "-i", temp_audio_path,           # Translated audio
                "-vf", f"ass={temp_ass_path}",   # 使用 ASS 格式字幕
                "-map", "0:v",                   # Use video from first input
                "-map", "1:a",                   # Use audio from second input
                "-c:v", "libx264",               # Video codec
                "-preset", "medium",
                "-crf", "22" if high_quality else "26",
                "-c:a", "aac",                   # Audio codec
                "-b:a", "192k" if high_quality else "128k",  # Higher audio bitrate
                "-af", "volume=2.0",             # Increase volume by 2x (6dB)
                temp_output_path
            ], check=True)
        else:
            logger.info("Processing video with FFmpeg (audio only)...")
            subprocess.run([
                "ffmpeg", "-y", 
                "-i", temp_video_no_audio_path,  # Video with no audio
                "-i", temp_audio_path,           # Translated audio
                "-map", "0:v",                   # Use video from first input
                "-map", "1:a",                   # Use audio from second input
                "-c:v", "copy",                  # Copy video codec
                "-c:a", "aac",                   # Audio codec
                "-b:a", "192k" if high_quality else "128k",  # Higher audio bitrate
                "-af", "volume=2.0",             # Increase volume by 2x (6dB)
                temp_output_path
            ], check=True)
        
        # Copy the output to the local output directory
        shutil.copy2(temp_output_path, local_output_path)
        logger.info(f"Saved processed video to local path: {local_output_path}")
        
        # Upload the result back to S3
        output_s3_key = f"output/processed_{uuid.uuid4()}.mp4"
        logger.info(f"Uploading processed video to S3: {output_s3_key}")
        s3_client.upload_file(temp_output_path, bucket_name, output_s3_key)
        
        # Clean up temporary directory
        shutil.rmtree(temp_dir)
        
        # Return both the S3 key and local path
        return {
            "s3_key": output_s3_key,
            "local_path": local_output_path
        }
    
    except Exception as e:
        logger.error(f"Error processing video locally: {str(e)}")
        # Clean up temporary directory if it exists
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        # Try a simpler approach without speed adjustment or subtitles
        return fallback_process_video(s3_client, bucket_name, video_s3_key, audio_s3_key, local_video_path)

def format_srt_file(input_srt, output_srt):
    """
    Format an SRT file to ensure lines aren't too long and fix timing issues.
    
    Args:
        input_srt: Path to the input SRT file
        output_srt: Path to the output SRT file
    """
    try:
        with open(input_srt, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split into subtitle blocks
        blocks = content.strip().split('\n\n')
        formatted_blocks = []
        
        for block in blocks:
            lines = block.split('\n')
            if len(lines) >= 3:  # Valid subtitle block has at least 3 lines
                # Extract subtitle number and timing
                subtitle_num = lines[0]
                timing = lines[1]
                
                # 保留原始时间，不做修改
                # 因为我们已经在subtitle.py中根据行数拆分了字幕并分配了合适的时间
                
                # 提取文本行
                text_lines = lines[2:]
                
                # 确保每个字幕块最多只有2行文本
                if len(text_lines) > 2:
                    text_lines = text_lines[:2]
                
                # 重建字幕块
                formatted_block = f"{subtitle_num}\n{timing}\n" + "\n".join(text_lines)
                formatted_blocks.append(formatted_block)
        
        # Join blocks and write to output file
        with open(output_srt, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(formatted_blocks))
        
        logger.info(f"Formatted SRT file with {len(formatted_blocks)} subtitles")
    
    except Exception as e:
        logger.error(f"Error formatting SRT file: {str(e)}")
        # If formatting fails, just copy the original file
        shutil.copy2(input_srt, output_srt)

def format_subtitle_text(text, max_line_length=40):
    """
    Format subtitle text to limit line length.
    
    Args:
        text: The subtitle text
        max_line_length: Maximum characters per line
        
    Returns:
        Formatted subtitle text
    """
    # If text is short enough, return as is
    if len(text) <= max_line_length:
        return text
    
    words = text.split()
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
    
    # 不限制行数，返回所有行
    return "\n".join(lines)
    if current_line:
        lines.append(current_line)
    
    # Join lines with newline character
    return '\n'.join(lines)

def fallback_process_video(s3_client, bucket_name, video_s3_key, audio_s3_key, local_video_path=None):
    """
    Fallback method with simpler settings if the main method fails.
    
    Returns:
        Dictionary containing S3 key and local path for the output video
    """
    try:
        # Create temporary directory for all files
        temp_dir = tempfile.mkdtemp()
        
        # Create paths for temporary files
        temp_video_path = os.path.join(temp_dir, "input_video.mp4")
        temp_audio_path = os.path.join(temp_dir, "audio.mp3")
        temp_output_path = os.path.join(temp_dir, "output.mp4")
        
        # Create a local output directory in the user's home directory
        local_output_dir = os.path.expanduser("~/video_translator_output")
        os.makedirs(local_output_dir, exist_ok=True)
        
        # Create a unique local output path
        local_output_path = os.path.join(local_output_dir, f"fallback_video_{int(time.time())}.mp4")
        
        # Use local video file if available, otherwise download from S3
        if local_video_path and os.path.exists(local_video_path):
            print(f"Using local video file (fallback): {local_video_path}")
            shutil.copy2(local_video_path, temp_video_path)
        else:
            print(f"Downloading video from S3 (fallback): {video_s3_key}")
            s3_client.download_file(bucket_name, video_s3_key, temp_video_path)
        
        print(f"Downloading audio from S3 (fallback): {audio_s3_key}")
        s3_client.download_file(bucket_name, audio_s3_key, temp_audio_path)
        
        # Create a version of the video with no audio
        temp_video_no_audio_path = os.path.join(temp_dir, "video_no_audio.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", temp_video_path, "-an",
            "-c:v", "copy", temp_video_no_audio_path
        ], check=True)
        
        # Simple audio replacement without any fancy options
        print("Processing video with FFmpeg (fallback method)...")
        subprocess.run([
            "ffmpeg", "-y", 
            "-i", temp_video_no_audio_path,  # Video with no audio
            "-i", temp_audio_path,           # Translated audio
            "-map", "0:v",                   # Use video from first input
            "-map", "1:a",                   # Use audio from second input
            "-c:v", "copy",                  # Copy video codec
            "-c:a", "aac",                   # Audio codec
            "-b:a", "128k",
            temp_output_path
        ], check=True)
        
        # Copy the output to the local output directory
        shutil.copy2(temp_output_path, local_output_path)
        print(f"Saved processed video to local path: {local_output_path}")
        
        # Upload the result back to S3
        output_s3_key = f"output/fallback_{uuid.uuid4()}.mp4"
        print(f"Uploading processed video to S3 (fallback): {output_s3_key}")
        s3_client.upload_file(temp_output_path, bucket_name, output_s3_key)
        
        # Clean up temporary directory
        shutil.rmtree(temp_dir)
        
        # Return both the S3 key and local path
        return {
            "s3_key": output_s3_key,
            "local_path": local_output_path
        }
    
    except Exception as e:
        print(f"Error in fallback processing: {str(e)}")
        # Clean up temporary directory if it exists
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise Exception(f"All video processing methods failed. Last error: {str(e)}")

def fix_subtitle_encoding(subtitle_path):
    """
    Fix subtitle encoding issues if any.
    """
    try:
        # Read the subtitle file
        with open(subtitle_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Write it back with explicit UTF-8 encoding
        with open(subtitle_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except UnicodeDecodeError:
        # If UTF-8 fails, try other common encodings
        for encoding in ['latin-1', 'iso-8859-1', 'cp1252']:
            try:
                with open(subtitle_path, 'r', encoding=encoding) as f:
                    content = f.read()
                
                with open(subtitle_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                break
            except UnicodeDecodeError:
                continue
