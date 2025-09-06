#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASR转写模块 - 下游SDK
为下游同学提供转写结果接收的Python SDK
"""

import asyncio
import json
import time
import uuid
import websockets
import requests
import pika
import redis
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging
from pathlib import Path
import aiohttp
import aiofiles

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TranscriptionResult:
    """转写结果"""
    result_id: str
    task_id: str
    text: str
    confidence: float
    language: str
    speaker_info: Optional[Dict[str, Any]] = None
    timestamps: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = None
    created_at: datetime = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_at is None:
            self.created_at = datetime.now()

@dataclass
class TaskStatus:
    """任务状态"""
    task_id: str
    status: str
    progress: int
    audio_info: Optional[Dict[str, Any]] = None
    transcription_info: Optional[Dict[str, Any]] = None
    estimated_completion: Optional[datetime] = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.now()

class ASRDownstreamClient:
    """ASR下游客户端 - 用于接收ASR转写结果并进行语义分析"""
    
    def __init__(self, 
                 api_key: str,
                 base_url: str = "https://asr-api.com",
                 timeout: int = 30,
                 max_retries: int = 3):
        """
        初始化ASR下游客户端
        
        Args:
            api_key: API密钥 (下游同学专用)
            base_url: ASR系统API基础URL
            timeout: 请求超时时间(秒)
            max_retries: 最大重试次数
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'ASR-Downstream-SDK/1.0.0'
        })
        
        # 结果缓存
        self.results_cache: Dict[str, List[TranscriptionResult]] = {}
        
        logger.info(f"ASR下游客户端初始化完成: {base_url}")
        logger.info("职责: 接收ASR转写结果 → 语义分析 → 推送到Web前端")
    
    def process_transcription_result(self, 
                                   task_id: str,
                                   frontend_ws_url: str = None,
                                   semantic_analyzer: Callable = None) -> Optional[Dict[str, Any]]:
        """
        处理ASR转写结果并进行语义分析
        
        Args:
            task_id: 转写任务ID
            frontend_ws_url: Web前端WebSocket地址
            semantic_analyzer: 语义分析函数
            
        Returns:
            Dict: 语义分析结果，如果失败返回None
        """
        try:
            logger.info(f"📥 开始处理转写结果: {task_id}")
            
            # 1. 获取转写结果
            results = self.get_task_results(task_id)
            if not results:
                logger.error(f"❌ 未找到转写结果: {task_id}")
                return None
            
            # 2. 提取转写文本
            transcription_text = results[0].text
            logger.info(f"📝 转写文本: {transcription_text[:100]}...")
            
            # 3. 进行语义分析
            if semantic_analyzer:
                analysis_result = semantic_analyzer(transcription_text)
            else:
                # 默认语义分析
                analysis_result = self._default_semantic_analysis(transcription_text)
            
            # 4. 推送到Web前端
            if frontend_ws_url:
                self._push_to_frontend(task_id, analysis_result, frontend_ws_url)
            
            logger.info(f"✅ 语义分析完成: {task_id}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"❌ 处理转写结果异常: {e}")
            return None
    
    def _default_semantic_analysis(self, text: str) -> Dict[str, Any]:
        """
        默认语义分析 (下游同学需要实现自己的分析逻辑)
        
        Args:
            text: 转写文本
            
        Returns:
            Dict: 分析结果
        """
        # 这里提供默认的分析框架，下游同学需要实现具体的分析逻辑
        return {
            "text": text,
            "sentiment": "neutral",  # 情感分析
            "intent": "unknown",     # 意图识别
            "entities": [],          # 实体提取
            "keywords": [],          # 关键词提取
            "summary": text[:100],   # 摘要
            "confidence": 0.8,       # 置信度
            "analysis_time": datetime.now().isoformat()
        }
    
    def _push_to_frontend(self, 
                         task_id: str, 
                         analysis_result: Dict[str, Any], 
                         frontend_ws_url: str):
        """
        推送分析结果到Web前端
        
        Args:
            task_id: 任务ID
            analysis_result: 分析结果
            frontend_ws_url: 前端WebSocket地址
        """
        try:
            import websockets
            import json
            
            # 构建推送消息
            push_message = {
                "type": "semantic_analysis_result",
                "task_id": task_id,
                "result": analysis_result,
                "timestamp": datetime.now().isoformat()
            }
            
            # 推送到前端 (这里需要根据实际的前端接口调整)
            logger.info(f"📡 推送分析结果到前端: {frontend_ws_url}")
            # 实际实现需要根据前端的WebSocket接口来调整
            
        except Exception as e:
            logger.error(f"❌ 推送到前端失败: {e}")
    
    def get_task_results(self, task_id: str) -> List[TranscriptionResult]:
        """
        获取任务的转写结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            List[TranscriptionResult]: 转写结果列表
        """
        try:
            response = self._make_request(
                'GET',
                f'/api/v1/tasks/{task_id}/results'
            )
            
            if response.status_code == 200:
                data = response.json()['data']
                results = []
                
                for item in data:
                    result = TranscriptionResult(
                        result_id=item['result_id'],
                        task_id=item['task_id'],
                        text=item['text'],
                        confidence=item['confidence'],
                        language=item['language'],
                        speaker_info=item.get('speaker_info'),
                        timestamps=item.get('timestamps'),
                        metadata=item.get('metadata', {}),
                        created_at=datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
                    )
                    results.append(result)
                
                # 更新缓存
                self.results_cache[task_id] = results
                
                logger.info(f"📝 获取到 {len(results)} 个转写结果: {task_id}")
                return results
            else:
                logger.error(f"❌ 获取转写结果失败: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ 获取转写结果异常: {e}")
            return []
    
    def get_batch_results(self, 
                         task_ids: Optional[List[str]] = None,
                         start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None,
                         status: Optional[str] = None,
                         limit: int = 100,
                         offset: int = 0) -> List[TranscriptionResult]:
        """
        批量获取转写结果
        
        Args:
            task_ids: 任务ID列表
            start_time: 开始时间
            end_time: 结束时间
            status: 状态过滤
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            List[TranscriptionResult]: 转写结果列表
        """
        try:
            params = {
                'limit': limit,
                'offset': offset
            }
            
            if task_ids:
                params['task_ids'] = ','.join(task_ids)
            if start_time:
                params['start_time'] = start_time.isoformat()
            if end_time:
                params['end_time'] = end_time.isoformat()
            if status:
                params['status'] = status
            
            response = self._make_request(
                'GET',
                '/api/v1/results',
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()['data']
                results = []
                
                for item in data:
                    result = TranscriptionResult(
                        result_id=item['result_id'],
                        task_id=item['task_id'],
                        text=item['text'],
                        confidence=item['confidence'],
                        language=item['language'],
                        speaker_info=item.get('speaker_info'),
                        timestamps=item.get('timestamps'),
                        metadata=item.get('metadata', {}),
                        created_at=datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
                    )
                    results.append(result)
                
                logger.info(f"📝 批量获取到 {len(results)} 个转写结果")
                return results
            else:
                logger.error(f"❌ 批量获取转写结果失败: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ 批量获取转写结果异常: {e}")
            return []
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            TaskStatus: 任务状态
        """
        try:
            response = self._make_request(
                'GET',
                f'/api/v1/tasks/{task_id}/status'
            )
            
            if response.status_code == 200:
                data = response.json()['data']
                
                status = TaskStatus(
                    task_id=data['task_id'],
                    status=data['status'],
                    progress=data['progress'],
                    audio_info=data.get('audio_info'),
                    transcription_info=data.get('transcription_info'),
                    estimated_completion=datetime.fromisoformat(data['estimated_completion'].replace('Z', '+00:00')) if data.get('estimated_completion') else None,
                    updated_at=datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
                )
                
                logger.info(f"📊 任务状态: {task_id} - {status.status} ({status.progress}%)")
                return status
            else:
                logger.error(f"❌ 获取任务状态失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取任务状态异常: {e}")
            return None
    
    def download_results(self, 
                        task_id: str, 
                        output_dir: Union[str, Path] = ".",
                        format: str = "json") -> List[Path]:
        """
        下载转写结果文件
        
        Args:
            task_id: 任务ID
            output_dir: 输出目录
            format: 文件格式 (json, txt, zip)
            
        Returns:
            List[Path]: 下载的文件路径列表
        """
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            headers = {'Accept': f'application/{format}'}
            response = self._make_request(
                'GET',
                f'/api/v1/tasks/{task_id}/results/download',
                headers=headers
            )
            
            if response.status_code == 200:
                downloaded_files = []
                
                if format == "json":
                    # 保存JSON格式
                    result_file = output_dir / f"{task_id}_results.json"
                    with open(result_file, 'w', encoding='utf-8') as f:
                        json.dump(response.json(), f, ensure_ascii=False, indent=2)
                    downloaded_files.append(result_file)
                
                elif format == "txt":
                    # 保存文本格式
                    result_file = output_dir / f"{task_id}_results.txt"
                    with open(result_file, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    downloaded_files.append(result_file)
                
                elif format == "zip":
                    # 保存ZIP格式
                    result_file = output_dir / f"{task_id}_results.zip"
                    with open(result_file, 'wb') as f:
                        f.write(response.content)
                    downloaded_files.append(result_file)
                
                logger.info(f"💾 结果文件已下载: {downloaded_files}")
                return downloaded_files
            else:
                logger.error(f"❌ 下载结果文件失败: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ 下载结果文件异常: {e}")
            return []
    
    def save_results_to_file(self, 
                           results: List[TranscriptionResult], 
                           output_file: Union[str, Path],
                           format: str = "json") -> bool:
        """
        保存转写结果到文件
        
        Args:
            results: 转写结果列表
            output_file: 输出文件路径
            format: 文件格式 (json, txt, csv)
            
        Returns:
            bool: 保存是否成功
        """
        try:
            output_file = Path(output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            if format == "json":
                data = []
                for result in results:
                    data.append({
                        'result_id': result.result_id,
                        'task_id': result.task_id,
                        'text': result.text,
                        'confidence': result.confidence,
                        'language': result.language,
                        'speaker_info': result.speaker_info,
                        'timestamps': result.timestamps,
                        'metadata': result.metadata,
                        'created_at': result.created_at.isoformat()
                    })
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            elif format == "txt":
                with open(output_file, 'w', encoding='utf-8') as f:
                    for i, result in enumerate(results):
                        f.write(f"=== 结果 {i+1} ===\n")
                        f.write(f"任务ID: {result.task_id}\n")
                        f.write(f"结果ID: {result.result_id}\n")
                        f.write(f"置信度: {result.confidence}\n")
                        f.write(f"语言: {result.language}\n")
                        f.write(f"文本: {result.text}\n")
                        f.write(f"创建时间: {result.created_at}\n")
                        f.write("-" * 50 + "\n")
            
            elif format == "csv":
                import csv
                with open(output_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['result_id', 'task_id', 'text', 'confidence', 'language', 'created_at'])
                    for result in results:
                        writer.writerow([
                            result.result_id,
                            result.task_id,
                            result.text,
                            result.confidence,
                            result.language,
                            result.created_at.isoformat()
                        ])
            
            logger.info(f"💾 结果已保存到文件: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存结果到文件异常: {e}")
            return False
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """发送HTTP请求"""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=self.timeout,
                    **kwargs
                )
                return response
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning(f"请求失败，重试 {attempt + 1}/{self.max_retries}: {e}")
                time.sleep(2 ** attempt)  # 指数退避
        
        raise Exception("请求失败，已达到最大重试次数")

class WebSocketResultClient:
    """WebSocket结果客户端"""
    
    def __init__(self, 
                 api_key: str,
                 websocket_url: str = "wss://asr-api.com/ws/v1/results"):
        self.api_key = api_key
        self.websocket_url = websocket_url
        self.websocket = None
        self.connected = False
        self.result_handlers: List[Callable[[TranscriptionResult], None]] = []
        self.status_handlers: List[Callable[[TaskStatus], None]] = []
        
        logger.info(f"WebSocket结果客户端初始化完成: {websocket_url}")
    
    def add_result_handler(self, handler: Callable[[TranscriptionResult], None]):
        """添加转写结果处理器"""
        self.result_handlers.append(handler)
    
    def add_status_handler(self, handler: Callable[[TaskStatus], None]):
        """添加状态更新处理器"""
        self.status_handlers.append(handler)
    
    async def connect(self):
        """连接到WebSocket服务器"""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'X-Subscribe-Topics': 'transcription_results,status_updates'
            }
            
            self.websocket = await websockets.connect(
                self.websocket_url,
                extra_headers=headers
            )
            self.connected = True
            
            logger.info("✅ WebSocket连接成功")
            
            # 接收欢迎消息
            welcome_msg = await self.websocket.recv()
            data = json.loads(welcome_msg)
            logger.info(f"📨 收到欢迎消息: {data.get('message')}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ WebSocket连接失败: {e}")
            return False
    
    async def listen(self, timeout: Optional[int] = None):
        """监听转写结果"""
        if not self.connected:
            logger.error("❌ WebSocket未连接")
            return
        
        try:
            start_time = time.time()
            
            while True:
                if timeout and time.time() - start_time > timeout:
                    logger.info("⏰ 监听超时")
                    break
                
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    
                    if data.get("type") == "transcription_result":
                        result = self._parse_transcription_result(data["data"])
                        for handler in self.result_handlers:
                            try:
                                handler(result)
                            except Exception as e:
                                logger.error(f"❌ 结果处理器异常: {e}")
                    
                    elif data.get("type") == "status_update":
                        status = self._parse_task_status(data["data"])
                        for handler in self.status_handlers:
                            try:
                                handler(status)
                            except Exception as e:
                                logger.error(f"❌ 状态处理器异常: {e}")
                    
                    elif data.get("type") == "ping":
                        # 响应心跳
                        pong_msg = {"type": "pong", "timestamp": int(time.time())}
                        await self.websocket.send(json.dumps(pong_msg))
                        logger.debug("💓 响应心跳")
                
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.info("🔌 WebSocket连接已关闭")
                    break
                except Exception as e:
                    logger.error(f"❌ 接收消息异常: {e}")
                    break
            
        except Exception as e:
            logger.error(f"❌ 监听异常: {e}")
    
    async def disconnect(self):
        """断开WebSocket连接"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            logger.info("🔌 WebSocket连接已断开")
    
    def _parse_transcription_result(self, data: Dict[str, Any]) -> TranscriptionResult:
        """解析转写结果"""
        return TranscriptionResult(
            result_id=data['result_id'],
            task_id=data['task_id'],
            text=data['text'],
            confidence=data['confidence'],
            language=data['language'],
            speaker_info=data.get('speaker_info'),
            timestamps=data.get('timestamps'),
            metadata=data.get('metadata', {}),
            created_at=datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
        )
    
    def _parse_task_status(self, data: Dict[str, Any]) -> TaskStatus:
        """解析任务状态"""
        return TaskStatus(
            task_id=data['task_id'],
            status=data['status'],
            progress=data['progress'],
            audio_info=data.get('audio_info'),
            transcription_info=data.get('transcription_info'),
            estimated_completion=datetime.fromisoformat(data['estimated_completion'].replace('Z', '+00:00')) if data.get('estimated_completion') else None,
            updated_at=datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
        )

class MessageQueueResultClient:
    """消息队列结果客户端"""
    
    def __init__(self, 
                 redis_url: str = "redis://localhost:6379",
                 rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"):
        self.redis_url = redis_url
        self.rabbitmq_url = rabbitmq_url
        self.redis_client = None
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        self.result_handlers: List[Callable[[TranscriptionResult], None]] = []
        
        logger.info("消息队列结果客户端初始化完成")
    
    def add_result_handler(self, handler: Callable[[TranscriptionResult], None]):
        """添加转写结果处理器"""
        self.result_handlers.append(handler)
    
    async def connect_redis(self):
        """连接到Redis"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            logger.info("✅ Redis连接成功")
            return True
        except Exception as e:
            logger.error(f"❌ Redis连接失败: {e}")
            return False
    
    async def connect_rabbitmq(self):
        """连接到RabbitMQ"""
        try:
            self.rabbitmq_connection = pika.BlockingConnection(
                pika.URLParameters(self.rabbitmq_url)
            )
            self.rabbitmq_channel = self.rabbitmq_connection.channel()
            
            # 声明结果队列
            self.rabbitmq_channel.queue_declare(queue='asr.results', durable=True)
            
            logger.info("✅ RabbitMQ连接成功")
            return True
        except Exception as e:
            logger.error(f"❌ RabbitMQ连接失败: {e}")
            return False
    
    async def listen_redis_results(self, stream_id: Optional[str] = None, timeout: int = 30):
        """监听Redis转写结果"""
        if not self.redis_client:
            logger.error("❌ Redis未连接")
            return
        
        try:
            start_time = time.time()
            last_id = "0"
            
            while time.time() - start_time < timeout:
                try:
                    # 读取结果流
                    streams = {"asr:result_stream": last_id}
                    messages = await self.redis_client.xread(streams, count=10, block=1000)
                    
                    if messages:
                        for stream, msgs in messages:
                            for message_id, fields in msgs:
                                result_stream_id = fields[b'stream_id'].decode()
                                
                                # 如果指定了stream_id，只处理匹配的消息
                                if stream_id and result_stream_id != stream_id:
                                    continue
                                
                                result = TranscriptionResult(
                                    result_id=fields[b'result_id'].decode(),
                                    task_id=result_stream_id,
                                    text=fields[b'text'].decode(),
                                    confidence=float(fields[b'confidence']),
                                    language=fields.get(b'language', b'zh-CN').decode(),
                                    metadata=json.loads(fields.get(b'metadata', b'{}'))
                                )
                                
                                # 调用处理器
                                for handler in self.result_handlers:
                                    try:
                                        handler(result)
                                    except Exception as e:
                                        logger.error(f"❌ 结果处理器异常: {e}")
                                
                                last_id = message_id
                
                except Exception as e:
                    logger.error(f"❌ 监听Redis结果异常: {e}")
                    await asyncio.sleep(1)
            
            logger.info("⏰ Redis监听超时")
            
        except Exception as e:
            logger.error(f"❌ 监听Redis结果失败: {e}")
    
    def listen_rabbitmq_results(self):
        """监听RabbitMQ转写结果"""
        if not self.rabbitmq_channel:
            logger.error("❌ RabbitMQ未连接")
            return
        
        def process_result(ch, method, properties, body):
            try:
                data = json.loads(body)
                
                result = TranscriptionResult(
                    result_id=data['result_id'],
                    task_id=data['task_id'],
                    text=data['text'],
                    confidence=data['confidence'],
                    language=data.get('language', 'zh-CN'),
                    metadata=data.get('metadata', {})
                )
                
                # 调用处理器
                for handler in self.result_handlers:
                    try:
                        handler(result)
                    except Exception as e:
                        logger.error(f"❌ 结果处理器异常: {e}")
                
                # 确认消息
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except Exception as e:
                logger.error(f"❌ 处理RabbitMQ结果异常: {e}")
        
        try:
            # 消费结果
            self.rabbitmq_channel.basic_consume(
                queue='asr.results',
                on_message_callback=process_result
            )
            
            logger.info("🎧 开始监听RabbitMQ转写结果")
            self.rabbitmq_channel.start_consuming()
            
        except Exception as e:
            logger.error(f"❌ 监听RabbitMQ结果失败: {e}")
    
    async def close(self):
        """关闭连接"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("🔌 Redis连接已关闭")
        
        if self.rabbitmq_connection:
            self.rabbitmq_connection.close()
            logger.info("🔌 RabbitMQ连接已关闭")

# 使用示例
def example_usage():
    """使用示例"""
    # 初始化客户端
    client = ASRDownstreamClient(
        api_key="your_api_key",
        base_url="https://asr-api.com"
    )
    
    try:
        # 获取任务转写结果
        task_id = "task_20241201_001"
        results = client.get_task_results(task_id)
        
        if results:
            print(f"获取到 {len(results)} 个转写结果")
            
            for i, result in enumerate(results):
                print(f"结果 {i+1}:")
                print(f"  文本: {result.text}")
                print(f"  置信度: {result.confidence}")
                print(f"  语言: {result.language}")
                print(f"  创建时间: {result.created_at}")
                print("-" * 50)
            
            # 保存结果到文件
            client.save_results_to_file(results, "results.json", "json")
            client.save_results_to_file(results, "results.txt", "txt")
            
            # 下载结果文件
            downloaded_files = client.download_results(task_id, "./downloads")
            print(f"下载的文件: {downloaded_files}")
        
        # 批量获取结果
        batch_results = client.get_batch_results(
            start_time=datetime.now() - timedelta(days=1),
            end_time=datetime.now(),
            limit=50
        )
        print(f"批量获取到 {len(batch_results)} 个结果")
    
    except Exception as e:
        print(f"操作失败: {e}")

async def websocket_example():
    """WebSocket使用示例"""
    client = WebSocketResultClient(
        api_key="your_api_key",
        websocket_url="wss://asr-api.com/ws/v1/results"
    )
    
    # 添加结果处理器
    def handle_result(result: TranscriptionResult):
        print(f"收到转写结果: {result.text}")
        print(f"置信度: {result.confidence}")
        
        # 这里可以进行语义分析
        # analysis = semantic_analyzer.analyze(result.text)
        # print(f"语义分析结果: {analysis}")
    
    def handle_status(status: TaskStatus):
        print(f"任务状态更新: {status.task_id} - {status.status} ({status.progress}%)")
    
    client.add_result_handler(handle_result)
    client.add_status_handler(handle_status)
    
    try:
        # 连接并监听
        if await client.connect():
            await client.listen(timeout=60)
    finally:
        await client.disconnect()

if __name__ == "__main__":
    # 同步示例
    example_usage()
    
    # 异步示例
    # asyncio.run(websocket_example())
