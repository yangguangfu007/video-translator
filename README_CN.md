# 多语言视频翻译器

这是一个基于AWS服务和大语言模型的应用程序，可以将中文视频翻译成英文、法语和德语。应用程序会自动处理视频的语音和字幕，确保音画同步。

## 功能特点

1. **视频语音翻译**
   - 将中文视频的语音翻译并转换为英文、法语或德语
   - 使用自然的语音合成，保持原始语调和情感

2. **字幕翻译与同步**
   - 自动提取原始视频中的语音内容
   - 翻译字幕内容到目标语言
   - 确保字幕与语音同步

3. **大模型增强翻译**
   - 利用Amazon Bedrock上的大语言模型进行高质量翻译
   - 保持语境和文化适应性

4. **视频处理**
   - 合成新的语音与原始视频
   - 添加翻译后的字幕
   - 保持视频质量和音画同步

## 技术架构

- **前端**: Streamlit
- **后端服务**:
  - Amazon Transcribe: 语音识别
  - Amazon Bedrock: 高质量翻译
  - Amazon Translate: 辅助翻译
  - Amazon Polly: 语音合成
  - Amazon S3: 存储视频和音频文件
  - Amazon MediaConvert: 视频处理和合成

## 前提条件

- Python 3.8+
- AWS账户，具有以下服务的访问权限：
  - Amazon Transcribe
  - Amazon Translate
  - Amazon Polly
  - Amazon S3
  - Amazon MediaConvert
  - Amazon Bedrock
- 配置好的AWS CLI凭证

## 安装步骤

1. 克隆仓库:
   ```
   git clone https://github.com/yourusername/video-translator.git
   cd video-translator
   ```

2. 创建并激活虚拟环境:
   ```
   python -m venv venv
   source venv/bin/activate  # 在Windows上使用 `venv\Scripts\activate`
   ```

3. 安装所需的包:
   ```
   pip install -r requirements.txt
   ```

4. 设置AWS资源:
   ```
   python setup_aws_resources.py --bucket-name your-unique-bucket-name
   ```

5. 编辑`.env`文件，添加您的AWS凭证:
   ```
   AWS_ACCESS_KEY_ID=your_access_key_id
   AWS_SECRET_ACCESS_KEY=your_secret_access_key
   BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
   ```

## 使用方法

1. 运行Streamlit应用:
   ```
   streamlit run app.py
   ```

2. 在浏览器中打开Streamlit提供的URL（通常是 http://localhost:8501）。

3. 上传中文视频并选择目标语言（英语、法语或德语）。

4. 点击"开始翻译"按钮，等待处理完成。

5. 下载翻译后的视频。

## 工作流程

1. **上传视频**: 用户上传中文视频文件
2. **选择目标语言**: 用户选择英语、法语或德语作为目标语言
3. **语音识别**: 使用Amazon Transcribe从原始视频中提取中文语音内容
4. **内容翻译**: 使用Amazon Bedrock大语言模型将提取的内容翻译成目标语言
5. **语音合成**: 使用Amazon Polly将翻译后的文本转换为目标语言的语音
6. **字幕生成**: 创建翻译后的字幕文件，确保与新语音同步
7. **视频处理**: 使用Amazon MediaConvert将新语音和字幕与原始视频合并
8. **结果下载**: 用户可以下载翻译后的视频文件

## 安全说明

此应用程序需要AWS凭证才能运行。确保您的AWS凭证安全，不要公开共享。建议在生产环境中部署此应用程序时，使用遵循最小权限原则的IAM角色。
