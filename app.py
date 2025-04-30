import streamlit as st
import os
import tempfile
import uuid
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
import subprocess

# Import our custom modules
from transcribe import transcribe_video
from translate import translate_content
from tts import generate_speech
from subtitle import create_subtitles
from video_processor import process_video
from logger import setup_logger

# 设置日志记录器
logger = setup_logger()

# Load environment variables
load_dotenv()

# Set page config
st.set_page_config(
    page_title="多语言视频翻译器 | Multilingual Video Translator",
    page_icon="🎬",
    layout="wide"
)

# Check if FFmpeg is installed
def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        return False

# Check AWS credentials
def check_aws_credentials():
    required_vars = [
        'AWS_ACCESS_KEY_ID', 
        'AWS_SECRET_ACCESS_KEY', 
        'AWS_REGION', 
        'S3_BUCKET_NAME', 
        'MEDIACONVERT_ROLE_ARN'
    ]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        st.error(f"缺少必要的环境变量: {', '.join(missing_vars)}")
        st.info("请确保您已创建 .env 文件并包含所有必要的环境变量。")
        st.stop()

# Initialize AWS clients
@st.cache_resource
def init_aws_clients():
    aws_region = os.getenv('AWS_REGION')
    return {
        'transcribe': boto3.client('transcribe', region_name=aws_region),
        'translate': boto3.client('translate', region_name=aws_region),
        'polly': boto3.client('polly', region_name=aws_region),
        's3': boto3.client('s3', region_name=aws_region),
        'mediaconvert': boto3.client('mediaconvert', region_name=aws_region),
        'bedrock': boto3.client('bedrock-runtime', region_name=aws_region)
    }

# Generate presigned URL for downloading files
def generate_presigned_url(bucket_name, object_name, expiration=3600):
    """
    Generate a presigned URL for downloading a file from S3.
    
    Args:
        bucket_name: S3 bucket name
        object_name: S3 object key
        expiration: URL expiration time in seconds
        
    Returns:
        Presigned URL for downloading the file
    """
    try:
        aws_region = os.getenv('AWS_REGION')
        s3_client = boto3.client('s3', region_name=aws_region)
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_name},
            ExpiresIn=expiration
        )
        return response
    except ClientError as e:
        st.error(f"生成预签名URL时出错: {str(e)}")
        return None

def main():
    # Check AWS credentials
    check_aws_credentials()
    
    # Check if FFmpeg is installed
    ffmpeg_installed = check_ffmpeg()
    if not ffmpeg_installed:
        st.warning("⚠️ FFmpeg 未安装。字幕功能可能无法正常工作。请安装 FFmpeg 以获得完整功能。")
        st.markdown("""
        ### 安装 FFmpeg:
        - **macOS**: `brew install ffmpeg`
        - **Windows**: 下载并安装 [FFmpeg](https://ffmpeg.org/download.html)
        - **Linux**: `sudo apt install ffmpeg` 或 `sudo yum install ffmpeg`
        """)
    
    # Initialize AWS clients
    aws_clients = init_aws_clients()
    
    # App title and description
    st.title("🎬 多语言视频翻译器 | Multilingual Video Translator")
    st.markdown("""
    将视频翻译成其他语言，包括语音和字幕翻译。
    
    Translate videos into other languages, including both voice and subtitles.
    """)
    
    # Sidebar for language selection
    st.sidebar.header("翻译设置 | Translation Settings")
    
    source_language = st.sidebar.selectbox(
        "选择原始视频语言 | Select Source Language",
        ["中文 (Chinese)", "英文 (English)"]
    )
    
    # Map source language to language code
    source_language_map = {
        "中文 (Chinese)": {
            "code": "zh-CN",
            "translate_code": "zh",
            "name": "Chinese"
        },
        "英文 (English)": {
            "code": "en-US",
            "translate_code": "en",
            "name": "English"
        }
    }
    
    selected_source_language = source_language_map[source_language]
    
    # Only show target languages that are different from source
    if source_language == "中文 (Chinese)":
        target_language_options = ["英语 (English)", "法语 (French)", "德语 (German)", "日语 (Japanese)", "韩语 (Korean)", "意大利语 (Italian)"]
    else:  # English source
        target_language_options = ["中文 (Chinese)", "法语 (French)", "德语 (German)", "日语 (Japanese)", "韩语 (Korean)", "意大利语 (Italian)"]
    
    target_language = st.sidebar.selectbox(
        "选择目标语言 | Select Target Language",
        target_language_options
    )
    
    # Map selected language to language code and voice ID
    language_map = {
        "英语 (English)": {
            "code": "en-US", 
            "translate_code": "en",
            "voices": {
                "male": "Matthew",
                "female": "Joanna"
            },
            "name": "English"
        },
        "中文 (Chinese)": {
            "code": "cmn-CN",
            "translate_code": "zh",
            "voices": {
                "male": "Zhiyu",
                "female": "Zhiyu"  # Amazon Polly only has one Chinese voice
            },
            "name": "Chinese"
        },
        "法语 (French)": {
            "code": "fr-FR", 
            "translate_code": "fr",
            "voices": {
                "male": "Mathieu",
                "female": "Léa"
            },
            "name": "French"
        },
        "德语 (German)": {
            "code": "de-DE", 
            "translate_code": "de",
            "voices": {
                "male": "Daniel",
                "female": "Vicki"
            },
            "name": "German"
        },
        "日语 (Japanese)": {
            "code": "ja-JP", 
            "translate_code": "ja",
            "voices": {
                "male": "Takumi",
                "female": "Mizuki"
            },
            "name": "Japanese"
        },
        "韩语 (Korean)": {
            "code": "ko-KR", 
            "translate_code": "ko",
            "voices": {
                "male": "Seoyeon",  # Amazon Polly only has one Korean voice
                "female": "Seoyeon"
            },
            "name": "Korean"
        },
        "意大利语 (Italian)": {
            "code": "it-IT", 
            "translate_code": "it",
            "voices": {
                "male": "Giorgio",
                "female": "Bianca"
            },
            "name": "Italian"
        }
    }
    
    selected_language = language_map[target_language]
    
    # Advanced settings
    with st.sidebar.expander("高级设置 | Advanced Settings"):
        use_bedrock = st.checkbox("使用 Amazon Bedrock 进行高质量翻译", value=True)
        add_subtitles = st.checkbox("添加字幕 | Add Subtitles", value=True)
        if add_subtitles and not ffmpeg_installed:
            st.warning("添加字幕需要安装 FFmpeg")
        
        voice_gender = st.radio(
            "语音性别 | Voice Gender",
            ["男声 | Male", "女声 | Female"],
            index=0
        )
        
        voice_id = selected_language["voices"]["male"] if voice_gender == "男声 | Male" else selected_language["voices"]["female"]
        
        video_quality = st.select_slider(
            "视频质量 | Video Quality",
            options=["标准 | Standard", "高质量 | High Quality"],
            value="高质量 | High Quality"
        )
        
        processing_method = st.radio(
            "处理方法 | Processing Method",
            ["AWS MediaConvert", "本地 FFmpeg | Local FFmpeg"],
            index=1
        )
        
        if processing_method == "本地 FFmpeg | Local FFmpeg" and not ffmpeg_installed:
            st.error("选择本地处理需要安装 FFmpeg")
    
    # Main content area
    st.header("上传视频 | Upload Video")
    uploaded_file = st.file_uploader(f"上传{selected_source_language['name']}视频文件 | Upload {selected_source_language['name']} Video File", type=["mp4", "mov", "avi", "mkv"])
    
    # Display local output directory
    local_output_dir = os.path.expanduser("~/video_translator_output")
    if os.path.exists(local_output_dir):
        st.info(f"本地输出目录 | Local output directory: {local_output_dir}")
    
    if uploaded_file is not None:
        # Display video preview
        st.video(uploaded_file)
        
        # Process button
        if st.button("开始翻译 | Start Translation"):
            # Check if FFmpeg is required but not installed
            if (add_subtitles or processing_method == "本地 FFmpeg | Local FFmpeg") and not ffmpeg_installed:
                st.error("此操作需要安装 FFmpeg。请安装后再试。")
                st.stop()
            
            # Create a progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Variable to track the temporary file path
            video_path = None
            
            try:
                # Save uploaded video to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
                    temp_video.write(uploaded_file.read())
                    video_path = temp_video.name
                
                # Step 1: Upload to S3
                status_text.text("上传视频到 S3... | Uploading video to S3...")
                bucket_name = os.getenv('S3_BUCKET_NAME')
                video_s3_key = f"input/{uuid.uuid4()}.mp4"
                aws_clients['s3'].upload_file(video_path, bucket_name, video_s3_key)
                logger.info(f"Uploaded video to S3: {video_s3_key}")
                progress_bar.progress(10)
                
                # Step 2: Transcribe video
                status_text.text(f"识别原始视频中的语音... | Transcribing original video...")
                try:
                    transcript = transcribe_video(
                        aws_clients['transcribe'], 
                        bucket_name, 
                        video_s3_key, 
                        selected_source_language["code"]
                    )
                    progress_bar.progress(30)
                except Exception as e:
                    st.error(f"转录失败: {str(e)}")
                    logger.error(f"转录失败: {str(e)}")
                    return
                
                # Step 3: Translate content
                status_text.text(f"将内容翻译成{selected_language['name']}... | Translating content to {selected_language['name']}...")
                try:
                    # 如果使用 Bedrock，确保传递 bedrock_client
                    if use_bedrock:
                        bedrock_client = aws_clients['bedrock']
                    else:
                        bedrock_client = None
                        
                    translated_text = translate_content(
                        aws_clients['translate'],
                        bedrock_client,
                        transcript,
                        selected_language['translate_code'],
                        selected_source_language['translate_code'],
                        use_bedrock
                    )
                    progress_bar.progress(50)
                except Exception as e:
                    st.error(f"翻译失败: {str(e)}")
                    logger.error(f"翻译失败: {str(e)}")
                    return
                
                # Step 4: Generate speech
                status_text.text("生成目标语言的语音... | Generating speech in target language...")
                try:
                    audio_s3_key, audio_timing = generate_speech(
                        aws_clients['polly'],
                        aws_clients['s3'],
                        bucket_name,
                        translated_text,
                        voice_id,  # Use the selected voice ID
                        selected_language['code']
                    )
                    progress_bar.progress(70)
                except Exception as e:
                    st.error(f"语音生成失败: {str(e)}")
                    logger.error(f"语音生成失败: {str(e)}")
                    return
                
                # 如果有音频时间信息，添加到翻译数据中
                if audio_timing:
                    translated_text["audio_timing"] = audio_timing
                    logger.info(f"添加音频时间信息到翻译数据，共 {len(audio_timing)} 条")
                
                # Step 5: Create subtitles if requested
                subtitle_s3_key = None
                if add_subtitles:
                    status_text.text("创建字幕... | Creating subtitles...")
                    try:
                        subtitle_keys = create_subtitles(
                            aws_clients['s3'],
                            bucket_name,
                            translated_text,
                            selected_language['translate_code']
                        )
                        # Use SRT format for better compatibility
                        subtitle_s3_key = subtitle_keys["srt"]
                        # Debug info
                        logger.info(f"字幕文件已创建: {subtitle_s3_key}")
                    except Exception as e:
                        st.warning(f"字幕创建失败，将继续处理视频但没有字幕: {str(e)}")
                        logger.error(f"字幕创建失败: {str(e)}")
                        subtitle_s3_key = None
                progress_bar.progress(80)
                
                # Step 6: Process video
                status_text.text("处理视频... | Processing video...")
                
                # Choose processing method based on user selection
                force_local = (processing_method == "本地 FFmpeg | Local FFmpeg")
                
                try:
                    result = process_video(
                        aws_clients['mediaconvert'],
                        aws_clients['s3'],
                        bucket_name,
                        video_s3_key,
                        audio_s3_key,
                        subtitle_s3_key if add_subtitles else None,
                        os.getenv('MEDIACONVERT_ROLE_ARN'),
                        video_quality == "高质量 | High Quality",
                        force_local,
                        video_path  # Pass the local video path to avoid re-downloading
                    )
                    
                    # Unpack the result (now returns both S3 key and local path)
                    output_key = result["s3_key"]
                    local_output_path = result["local_path"]
                    
                    progress_bar.progress(100)
                    
                    # Step 7: Generate download link
                    status_text.text("生成下载链接... | Generating download link...")
                    download_url = generate_presigned_url(bucket_name, output_key)
                    
                    if download_url:
                        # Display success message and download link
                        st.success(f"视频已成功翻译成{selected_language['name']}! | Video successfully translated to {selected_language['name']}!")
                        st.markdown(f"### [点击下载翻译后的视频 | Click to download translated video]({download_url})")
                        
                        # Display the local video file directly in the app
                        if local_output_path and os.path.exists(local_output_path):
                            st.write("### 预览翻译后的视频 | Preview translated video")
                            st.video(local_output_path)
                            st.info(f"本地视频文件保存在: {local_output_path}")
                    else:
                        st.error("无法生成下载链接。请联系管理员。")
                except Exception as e:
                    st.error(f"视频处理失败: {str(e)}")
                    logger.error(f"视频处理失败: {str(e)}")
                    st.info("提供原始音频和视频的下载链接，您可以使用本地工具合并它们。")
                    
                    # Generate download links for the original video and translated audio
                    video_url = generate_presigned_url(bucket_name, video_s3_key)
                    audio_url = generate_presigned_url(bucket_name, audio_s3_key)
                    
                    if video_url and audio_url:
                        st.markdown(f"### [下载原始视频 | Download original video]({video_url})")
                        st.markdown(f"### [下载翻译后的音频 | Download translated audio]({audio_url})")
                        
                        if subtitle_s3_key:
                            subtitle_url = generate_presigned_url(bucket_name, subtitle_s3_key)
                            if subtitle_url:
                                st.markdown(f"### [下载字幕文件 | Download subtitle file]({subtitle_url})")
                    else:
                        st.error("无法生成下载链接。请联系管理员。")
                    
                    st.markdown("""
                    ### 如何在本地合并视频和音频
                    
                    您可以使用以下工具之一来合并视频和音频：
                    
                    1. **iMovie** (macOS)
                    2. **Adobe Premiere Pro** (Windows/macOS)
                    3. **DaVinci Resolve** (免费版本可用于 Windows/macOS/Linux)
                    4. **FFmpeg** (命令行工具，所有平台)
                    
                    使用 FFmpeg 的示例命令：
                    ```
                    ffmpeg -i video.mp4 -i audio.mp3 -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 output.mp4
                    ```
                    
                    如果要添加字幕：
                    ```
                    ffmpeg -i video.mp4 -i audio.mp3 -vf subtitles=subtitle.srt -c:a aac -map 0:v:0 -map 1:a:0 output.mp4
                    ```
                    """)
                
                # Clean up temporary file - safely delete if it exists
                if video_path and os.path.exists(video_path):
                    try:
                        os.unlink(video_path)
                    except Exception as e:
                        print(f"Warning: Could not delete temporary file {video_path}: {str(e)}")
                
            except Exception as e:
                st.error(f"处理过程中出错: {str(e)} | Error during processing: {str(e)}")
                # Clean up temporary file - safely delete if it exists
                if video_path and os.path.exists(video_path):
                    try:
                        os.unlink(video_path)
                    except Exception as e:
                        print(f"Warning: Could not delete temporary file {video_path}: {str(e)}")

if __name__ == "__main__":
    main()
