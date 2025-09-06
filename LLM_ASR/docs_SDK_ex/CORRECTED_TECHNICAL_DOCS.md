# ASR转写模块 - 修正技术文档

## 工作流程修正说明

根据你的实际工作流程，我已经修正了技术文档，确保完全符合以下流程：

```
Web前端 → 上游同学 → ASR系统(你的模块) → 下游同学 → Web前端
```

## 修正后的系统架构

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

## 各模块职责和接口

### 1. Web前端 (用户界面)

#### 职责
- 提供用户界面进行音频录制
- 将音频流推送给上游同学
- 接收并展示语义分析结果
- 提供用户交互和反馈

#### 接口需求
```javascript
// 音频录制和推送
class AudioRecorder {
    async startRecording() {
        // 开始录音
    }
    
    async sendToUpstream(audioBlob) {
        // 发送音频到上游同学
    }
}

// 结果接收和展示
class ResultDisplay {
    displayAnalysisResult(result) {
        // 展示语义分析结果
    }
}
```

### 2. 上游同学 (音频推送)

#### 职责
- 接收Web前端的音频流
- 对音频进行格式转换和预处理
- 将处理后的音频推送到ASR系统
- 监控转写进度和状态

#### 接口使用
```python
from upstream_sdk import ASRUpstreamClient

class UpstreamAudioProcessor:
    def __init__(self):
        self.asr_client = ASRUpstreamClient(
            api_key="upstream_api_key",
            base_url="https://asr-api.your-domain.com"
        )
    
    def receive_audio_from_frontend(self, audio_data, user_id, session_id):
        """接收前端音频并推送到ASR系统"""
        task_id = self.asr_client.receive_audio_from_frontend(
            audio_data=audio_data,
            user_id=user_id,
            session_id=session_id
        )
        return task_id
```

### 3. ASR系统 (你的模块)

#### 职责
- 接收上游同学的音频流
- 进行实时音频转写
- 生成.txt转写结果文件
- 将结果推送给下游同学

#### 接口提供
```python
# 你的ASR系统需要提供的接口
class ASRSystem:
    def process_audio_stream(self, task_id, audio_data):
        """处理音频流并生成转写结果"""
        # 1. 实时转写处理
        # 2. 生成.txt文件
        # 3. 通知下游同学
        pass
    
    def export_result_to_downstream(self, task_id, result_text):
        """导出转写结果给下游同学"""
        # 生成.txt文件并通知下游
        pass
```

### 4. 下游同学 (语义分析)

#### 职责
- 接收ASR系统生成的.txt转写结果
- 对转写文本进行语义分析和推理
- 将分析结果推送到Web前端
- 提供分析结果的API接口

#### 接口使用
```python
from downstream_sdk import ASRDownstreamClient

class DownstreamSemanticAnalyzer:
    def __init__(self):
        self.asr_client = ASRDownstreamClient(
            api_key="downstream_api_key",
            base_url="https://asr-api.your-domain.com"
        )
    
    def process_transcription_result(self, task_id):
        """处理转写结果并进行语义分析"""
        # 1. 获取转写结果
        # 2. 进行语义分析
        # 3. 推送到前端
        pass
```

## 数据流向

### 1. 音频数据流
```
Web前端录音 → 上游同学处理 → ASR系统转写 → 生成.txt文件
```

### 2. 文本数据流
```
ASR转写结果 → 下游同学分析 → 语义分析结果 → Web前端展示
```

### 3. 状态同步流
```
各模块状态 → 统一状态管理 → 实时状态推送 → 前端状态显示
```

## 接口协议修正

### 1. 上游同学接口

#### 接收前端音频
```python
def receive_audio_from_frontend(self, audio_data, user_id, session_id):
    """接收来自Web前端的音频数据并推送到ASR系统"""
    task_metadata = {
        "source": "web_frontend",
        "user_id": user_id,
        "session_id": session_id,
        "received_at": datetime.now().isoformat()
    }
    
    # 创建转写任务
    task = self.create_task(metadata=task_metadata)
    
    # 上传音频数据到ASR系统
    success = self.upload_audio_data(task.task_id, audio_data)
    
    return task.task_id if success else None
```

#### 推送到ASR系统
```python
def push_to_asr_system(self, audio_data, metadata):
    """推送处理后的音频到ASR系统"""
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

### 2. 下游同学接口

#### 接收ASR结果
```python
def process_transcription_result(self, task_id):
    """处理ASR转写结果并进行语义分析"""
    # 1. 获取转写结果
    results = self.asr_client.get_task_results(task_id)
    
    if results:
        # 2. 进行语义分析
        analysis_result = self.perform_semantic_analysis(results[0].text)
        
        # 3. 推送到前端
        self.push_to_frontend(task_id, analysis_result)
        
        return analysis_result
    
    return None
```

#### 推送到前端
```python
def push_to_frontend(self, task_id, analysis_result):
    """推送分析结果到Web前端"""
    message = {
        "type": "semantic_analysis_result",
        "task_id": task_id,
        "result": analysis_result,
        "timestamp": datetime.now().isoformat()
    }
    
    # 通过WebSocket推送到前端
    self.frontend_client.send_result(message)
```

## 部署配置修正

### 1. 服务配置
```yaml
# docker-compose.yml
version: '3.8'
services:
  web-frontend:
    build: ./web-frontend
    ports:
      - "3000:3000"
    environment:
      - UPSTREAM_WS_URL=ws://upstream-service:8080
  
  upstream-service:
    build: ./upstream-service
    ports:
      - "8080:8080"
    environment:
      - ASR_API_URL=http://asr-service:9000
      - ASR_API_KEY=upstream_api_key
  
  asr-service:
    build: ./asr-service
    ports:
      - "9000:9000"
    environment:
      - DOWNSTREAM_API_URL=http://downstream-service:8081
  
  downstream-service:
    build: ./downstream-service
    ports:
      - "8081:8081"
    environment:
      - ASR_API_URL=http://asr-service:9000
      - ASR_API_KEY=downstream_api_key
      - FRONTEND_WS_URL=ws://web-frontend:3000/ws
```

### 2. 环境变量配置
```bash
# 上游同学环境变量
UPSTREAM_ASR_API_KEY="upstream_api_key"
UPSTREAM_ASR_BASE_URL="https://asr-api.your-domain.com"
UPSTREAM_FRONTEND_WS_PORT="8080"

# 下游同学环境变量
DOWNSTREAM_ASR_API_KEY="downstream_api_key"
DOWNSTREAM_ASR_BASE_URL="https://asr-api.your-domain.com"
DOWNSTREAM_FRONTEND_WS_URL="ws://web-frontend:3000/ws"

# Web前端环境变量
FRONTEND_UPSTREAM_WS_URL="ws://upstream-service:8080"
FRONTEND_DOWNSTREAM_WS_URL="ws://downstream-service:8081"
```

## 测试和验证

### 1. 完整流程测试
```python
# 运行完整工作流程测试
python WORKFLOW_INTEGRATION_EXAMPLES.py complete
```

### 2. 单独模块测试
```python
# 测试上游模块
python WORKFLOW_INTEGRATION_EXAMPLES.py upstream

# 测试下游模块
python WORKFLOW_INTEGRATION_EXAMPLES.py downstream

# 测试前端模块
python WORKFLOW_INTEGRATION_EXAMPLES.py frontend
```

### 3. 集成测试
```python
# 测试Web前端 → 上游同学
def test_frontend_to_upstream():
    # 模拟前端发送音频
    # 验证上游接收和处理
    pass

# 测试上游同学 → ASR系统
def test_upstream_to_asr():
    # 模拟上游推送音频
    # 验证ASR转写结果
    pass

# 测试ASR系统 → 下游同学
def test_asr_to_downstream():
    # 模拟ASR生成结果
    # 验证下游接收和处理
    pass

# 测试下游同学 → Web前端
def test_downstream_to_frontend():
    # 模拟下游推送结果
    # 验证前端接收和展示
    pass
```

## 监控和日志

### 1. 流程监控
```python
# 监控整个流程的状态
class WorkflowMonitor:
    def track_audio_flow(self, task_id):
        """跟踪音频流转写流程"""
        pass
    
    def track_analysis_flow(self, task_id):
        """跟踪分析结果流程"""
        pass
    
    def get_workflow_status(self, task_id):
        """获取完整流程状态"""
        pass
```

### 2. 性能监控
```python
# 监控各模块性能
class PerformanceMonitor:
    def monitor_upstream_performance(self):
        """监控上游模块性能"""
        pass
    
    def monitor_asr_performance(self):
        """监控ASR模块性能"""
        pass
    
    def monitor_downstream_performance(self):
        """监控下游模块性能"""
        pass
```

## 总结

修正后的技术文档完全符合你的实际工作流程：

1. ✅ **Web前端** → 录制音频并推送给上游同学
2. ✅ **上游同学** → 接收前端音频并推送到ASR系统
3. ✅ **ASR系统** → 转写音频并生成.txt文件给下游同学
4. ✅ **下游同学** → 接收转写结果并进行语义分析
5. ✅ **Web前端** → 接收分析结果并展示给用户

每个模块都有明确的职责和接口，形成了一个完整的闭环系统。所有技术文档、SDK和示例代码都已经修正，确保符合你的实际工作流程。
