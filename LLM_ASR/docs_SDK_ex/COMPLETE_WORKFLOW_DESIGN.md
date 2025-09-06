# ASR转写模块 - 完整工作流程设计

## 系统架构概述

基于你的实际工作流程，整个系统是一个完整的闭环：

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web前端       │    │   上游同学      │    │   ASR转写模块   │    │   下游同学      │    │   Web前端       │
│  (用户界面)     │    │  (音频推送)     │    │   (你的系统)    │    │  (语义分析)     │    │  (结果展示)     │
│                 │    │                 │    │                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ 音频录制    │ │    │ │ 音频接收    │ │    │ │ 实时转写    │ │    │ │ 文本接收    │ │    │ │ 结果展示    │ │
│ │ 用户交互    │ │    │ │ 格式转换    │ │    │ │ 结果生成    │ │    │ │ 语义分析    │ │    │ │ 用户反馈    │ │
│ │ 状态显示    │ │    │ │ 流式推送    │ │    │ │ 文件输出    │ │    │ │ 推理计算    │ │    │ │ 交互响应    │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │                       │                       │
         │ 音频流推送             │ 音频流推送             │ .txt文件推送           │ 分析结果推送           │
         │                       │                       │                       │                       │
         ▼                       ▼                       ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    统一接口层 (API Gateway)                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│  │ WebSocket   │ │ REST API    │ │ 文件传输    │ │ 消息队列    │ │ 结果推送    │ │ 状态同步    │       │
│  │ 实时通信    │ │ 标准HTTP    │ │ 文件共享    │ │ 异步解耦    │ │ 实时通知    │ │ 状态管理    │       │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘       │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 完整工作流程

### 1. 流程步骤详解

#### 步骤1: Web前端 → 上游同学
```
Web前端用户录制音频 → 上游同学接收音频流 → 格式转换和预处理
```

#### 步骤2: 上游同学 → ASR系统
```
上游同学推送音频流 → ASR系统实时转写 → 生成.txt结果文件
```

#### 步骤3: ASR系统 → 下游同学
```
ASR系统推送.txt文件 → 下游同学接收文件 → 准备语义分析
```

#### 步骤4: 下游同学 → Web前端
```
下游同学完成语义分析 → 推送分析结果 → Web前端展示最终结果
```

### 2. 数据流向

```
音频数据流 → 转写文本 → 语义分析结果 → 用户界面展示
```

## 接口设计修正

### 1. 上游同学接口 (音频推送)

#### 1.1 接收Web前端音频流
```python
# 上游同学需要实现的接口
class AudioReceiver:
    def __init__(self):
        self.asr_client = ASRUpstreamClient(api_key="your_api_key")
    
    def receive_audio_from_frontend(self, audio_stream):
        """接收来自Web前端的音频流"""
        # 1. 接收音频数据
        # 2. 格式转换和预处理
        # 3. 推送到ASR系统
        pass
    
    def push_to_asr_system(self, processed_audio):
        """推送处理后的音频到ASR系统"""
        # 创建转写任务
        task = self.asr_client.create_task()
        
        # 上传音频
        self.asr_client.upload_audio_data(task.task_id, processed_audio)
        
        return task.task_id
```

#### 1.2 与ASR系统交互
```python
# 上游同学使用ASR系统接口
def upload_audio_to_asr(audio_data, metadata=None):
    """上传音频到ASR系统"""
    client = ASRUpstreamClient(api_key="upstream_api_key")
    
    # 创建任务
    task = client.create_task(
        task_id=f"frontend_audio_{int(time.time())}",
        metadata={
            "source": "web_frontend",
            "user_id": metadata.get("user_id"),
            "session_id": metadata.get("session_id")
        }
    )
    
    # 上传音频
    success = client.upload_audio_data(task.task_id, audio_data)
    
    if success:
        # 等待转写完成
        final_task = client.wait_for_completion(task.task_id)
        return final_task.task_id if final_task else None
    
    return None
```

### 2. ASR系统接口 (你的模块)

#### 2.1 接收上游音频流
```python
# 你的ASR系统需要提供的接口
class ASRSystem:
    def __init__(self):
        self.processor = AudioStreamProcessor()
        self.ws_server = WebSocketServerManager()
    
    def process_audio_stream(self, task_id, audio_data):
        """处理音频流并生成转写结果"""
        # 1. 实时转写处理
        # 2. 生成.txt文件
        # 3. 通知下游同学
        pass
    
    def notify_downstream(self, task_id, result_file_path):
        """通知下游同学转写完成"""
        # 通过WebSocket或消息队列通知下游同学
        notification = {
            "type": "transcription_complete",
            "task_id": task_id,
            "result_file_path": result_file_path,
            "timestamp": datetime.now().isoformat()
        }
        
        self.ws_server.broadcast_message(notification)
```

#### 2.2 输出.txt文件给下游
```python
def export_result_to_downstream(task_id, result_text):
    """导出转写结果给下游同学"""
    # 生成.txt文件
    result_file = f"outputs/{task_id}_result.txt"
    
    with open(result_file, 'w', encoding='utf-8') as f:
        f.write(result_text)
    
    # 通知下游同学
    notify_downstream_completion(task_id, result_file)
    
    return result_file
```

### 3. 下游同学接口 (语义分析)

#### 3.1 接收ASR转写结果
```python
# 下游同学需要实现的接口
class SemanticAnalyzer:
    def __init__(self):
        self.asr_client = ASRDownstreamClient(api_key="downstream_api_key")
        self.frontend_client = FrontendClient()
    
    def receive_transcription_result(self, task_id, result_file_path):
        """接收ASR转写结果"""
        # 1. 读取.txt文件
        with open(result_file_path, 'r', encoding='utf-8') as f:
            transcription_text = f.read()
        
        # 2. 进行语义分析
        analysis_result = self.perform_semantic_analysis(transcription_text)
        
        # 3. 推送到Web前端
        self.push_result_to_frontend(task_id, analysis_result)
    
    def perform_semantic_analysis(self, text):
        """执行语义分析"""
        # 这里实现你的语义分析逻辑
        # 例如：情感分析、意图识别、实体提取等
        pass
    
    def push_result_to_frontend(self, task_id, analysis_result):
        """推送分析结果到Web前端"""
        # 通过WebSocket推送到前端
        self.frontend_client.send_analysis_result(task_id, analysis_result)
```

#### 3.2 与Web前端交互
```python
class FrontendClient:
    def __init__(self):
        self.websocket = None
    
    def connect_to_frontend(self, frontend_url):
        """连接到Web前端"""
        self.websocket = websockets.connect(frontend_url)
    
    def send_analysis_result(self, task_id, analysis_result):
        """发送分析结果到前端"""
        message = {
            "type": "semantic_analysis_result",
            "task_id": task_id,
            "result": analysis_result,
            "timestamp": datetime.now().isoformat()
        }
        
        self.websocket.send(json.dumps(message))
```

### 4. Web前端接口 (用户界面)

#### 4.1 音频录制和推送
```javascript
// Web前端需要实现的接口
class AudioRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.upstreamClient = new UpstreamClient();
    }
    
    async startRecording() {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.mediaRecorder = new MediaRecorder(stream);
        
        this.mediaRecorder.ondataavailable = (event) => {
            this.audioChunks.push(event.data);
        };
        
        this.mediaRecorder.onstop = () => {
            this.sendAudioToUpstream();
        };
        
        this.mediaRecorder.start();
    }
    
    async sendAudioToUpstream() {
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
        
        // 发送音频到上游同学
        await this.upstreamClient.sendAudio(audioBlob, {
            user_id: this.getCurrentUserId(),
            session_id: this.getCurrentSessionId()
        });
    }
}
```

#### 4.2 接收和展示结果
```javascript
// Web前端接收分析结果
class ResultDisplay {
    constructor() {
        this.websocket = new WebSocket('ws://frontend-server:8080/ws');
        this.setupWebSocket();
    }
    
    setupWebSocket() {
        this.websocket.onmessage = (event) => {
            const message = JSON.parse(event.data);
            
            if (message.type === 'semantic_analysis_result') {
                this.displayAnalysisResult(message.result);
            }
        };
    }
    
    displayAnalysisResult(result) {
        // 展示语义分析结果
        const resultContainer = document.getElementById('analysis-result');
        resultContainer.innerHTML = `
            <div class="result-item">
                <h3>语义分析结果</h3>
                <p>情感: ${result.sentiment}</p>
                <p>意图: ${result.intent}</p>
                <p>实体: ${result.entities.join(', ')}</p>
                <p>置信度: ${result.confidence}</p>
            </div>
        `;
    }
}
```

## 修正后的技术文档结构

### 1. 上游同学技术文档

#### 1.1 职责说明
- 接收Web前端的音频流
- 对音频进行格式转换和预处理
- 将处理后的音频推送到ASR系统
- 监控转写进度和状态

#### 1.2 接口使用
```python
# 上游同学需要实现的接口
from asr_sdk import ASRUpstreamClient

class UpstreamAudioProcessor:
    def __init__(self):
        self.asr_client = ASRUpstreamClient(
            api_key="upstream_api_key",
            base_url="https://asr-api.your-domain.com"
        )
    
    def process_frontend_audio(self, audio_data, metadata):
        """处理来自前端的音频"""
        # 1. 音频预处理
        processed_audio = self.preprocess_audio(audio_data)
        
        # 2. 推送到ASR系统
        task_id = self.push_to_asr_system(processed_audio, metadata)
        
        return task_id
    
    def preprocess_audio(self, audio_data):
        """音频预处理"""
        # 格式转换、降噪、标准化等
        pass
    
    def push_to_asr_system(self, audio_data, metadata):
        """推送到ASR系统"""
        task = self.asr_client.create_task(
            metadata={
                "source": "web_frontend",
                "user_id": metadata.get("user_id"),
                "session_id": metadata.get("session_id")
            }
        )
        
        success = self.asr_client.upload_audio_data(task.task_id, audio_data)
        return task.task_id if success else None
```

### 2. 下游同学技术文档

#### 2.1 职责说明
- 接收ASR系统生成的.txt转写结果
- 对转写文本进行语义分析和推理
- 将分析结果推送到Web前端
- 提供分析结果的API接口

#### 2.2 接口使用
```python
# 下游同学需要实现的接口
from asr_sdk import ASRDownstreamClient

class DownstreamSemanticAnalyzer:
    def __init__(self):
        self.asr_client = ASRDownstreamClient(
            api_key="downstream_api_key",
            base_url="https://asr-api.your-domain.com"
        )
        self.frontend_client = FrontendWebSocketClient()
    
    def process_transcription_result(self, task_id):
        """处理转写结果"""
        # 1. 获取转写结果
        results = self.asr_client.get_task_results(task_id)
        
        if results:
            # 2. 进行语义分析
            analysis_result = self.perform_semantic_analysis(results[0].text)
            
            # 3. 推送到前端
            self.push_to_frontend(task_id, analysis_result)
            
            return analysis_result
        
        return None
    
    def perform_semantic_analysis(self, text):
        """执行语义分析"""
        # 实现你的语义分析逻辑
        # 例如：情感分析、意图识别、实体提取等
        return {
            "sentiment": "positive",
            "intent": "question",
            "entities": ["实体1", "实体2"],
            "confidence": 0.95,
            "summary": "分析摘要"
        }
    
    def push_to_frontend(self, task_id, analysis_result):
        """推送到Web前端"""
        self.frontend_client.send_result(task_id, analysis_result)
```

### 3. Web前端技术文档

#### 3.1 职责说明
- 提供用户界面进行音频录制
- 将音频流推送给上游同学
- 接收并展示语义分析结果
- 提供用户交互和反馈

#### 3.2 接口使用
```javascript
// Web前端需要实现的接口
class FrontendAudioSystem {
    constructor() {
        this.audioRecorder = new AudioRecorder();
        this.resultDisplay = new ResultDisplay();
        this.upstreamClient = new UpstreamClient();
    }
    
    async startAudioProcessing() {
        // 1. 开始录音
        await this.audioRecorder.startRecording();
        
        // 2. 录音完成后发送到上游
        this.audioRecorder.onStop = (audioBlob) => {
            this.sendToUpstream(audioBlob);
        };
    }
    
    async sendToUpstream(audioBlob) {
        // 发送音频到上游同学
        await this.upstreamClient.sendAudio(audioBlob, {
            user_id: this.getCurrentUserId(),
            session_id: this.getCurrentSessionId()
        });
    }
    
    displayAnalysisResult(result) {
        // 展示语义分析结果
        this.resultDisplay.show(result);
    }
}
```

## 数据流和状态管理

### 1. 任务状态流转

```
Web前端录制 → 上游处理 → ASR转写 → 下游分析 → 前端展示
     ↓           ↓          ↓          ↓          ↓
   recording → processing → transcribing → analyzing → completed
```

### 2. 状态同步机制

```python
# 状态同步接口
class StatusManager:
    def __init__(self):
        self.status_websocket = WebSocketClient()
    
    def update_status(self, task_id, status, progress=0):
        """更新任务状态"""
        status_message = {
            "type": "status_update",
            "task_id": task_id,
            "status": status,
            "progress": progress,
            "timestamp": datetime.now().isoformat()
        }
        
        self.status_websocket.broadcast(status_message)
    
    def notify_completion(self, task_id, result_type, result_data):
        """通知任务完成"""
        completion_message = {
            "type": "task_completed",
            "task_id": task_id,
            "result_type": result_type,
            "result_data": result_data,
            "timestamp": datetime.now().isoformat()
        }
        
        self.status_websocket.broadcast(completion_message)
```

## 部署和配置

### 1. 环境配置

```yaml
# docker-compose.yml
version: '3.8'
services:
  web-frontend:
    build: ./web-frontend
    ports:
      - "3000:3000"
    environment:
      - UPSTREAM_API_URL=http://upstream-service:8000
  
  upstream-service:
    build: ./upstream-service
    ports:
      - "8000:8000"
    environment:
      - ASR_API_URL=http://asr-service:9000
  
  asr-service:
    build: ./asr-service
    ports:
      - "9000:9000"
    environment:
      - DOWNSTREAM_API_URL=http://downstream-service:8001
  
  downstream-service:
    build: ./downstream-service
    ports:
      - "8001:8001"
    environment:
      - FRONTEND_WS_URL=ws://web-frontend:3000/ws
```

### 2. 服务发现和配置

```python
# 服务配置
SERVICE_CONFIG = {
    "web_frontend": {
        "url": "http://web-frontend:3000",
        "websocket_url": "ws://web-frontend:3000/ws"
    },
    "upstream_service": {
        "url": "http://upstream-service:8000",
        "api_key": "upstream_api_key"
    },
    "asr_service": {
        "url": "http://asr-service:9000",
        "websocket_url": "ws://asr-service:9000/ws"
    },
    "downstream_service": {
        "url": "http://downstream-service:8001",
        "api_key": "downstream_api_key"
    }
}
```

这个修正后的设计完全符合你的实际工作流程，每个模块都有明确的职责和接口，形成了一个完整的闭环系统。
