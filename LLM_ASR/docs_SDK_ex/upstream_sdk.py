#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASR转写模块 - 上游SDK
为上游同学提供音频推送的Python SDK
"""

import asyncio
import json
import time
import uuid
import base64
import requests
import websockets
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AudioConfig:
    """音频配置"""
    format: str = "wav"
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16
    max_file_size: int = 50 * 1024 * 1024  # 50MB

@dataclass
class TranscriptionConfig:
    """转写配置"""
    language: str = "zh-CN"
    enable_punctuation: bool = True
    enable_speaker_diarization: bool = False
    custom_vocabulary: List[str] = None
    confidence_threshold: float = 0.7

@dataclass
class CallbackConfig:
    """回调配置"""
    result_callback_url: Optional[str] = None
    status_callback_url: Optional[str] = None
    retry_policy: Dict[str, int] = None

    def __post_init__(self):
        if self.retry_policy is None:
            self.retry_policy = {"max_retries": 3, "retry_interval": 5}

@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    status: str
    created_at: datetime
    expires_at: datetime
    upload_urls: Dict[str, str]
    progress: int = 0
    error_message: Optional[str] = None

class ASRUpstreamClient:
    """ASR上游客户端 - 用于接收Web前端音频并推送到ASR系统"""
    
    def __init__(self, 
                 api_key: str,
                 base_url: str = "https://asr-api.com",
                 timeout: int = 30,
                 max_retries: int = 3):
        """
        初始化ASR上游客户端
        
        Args:
            api_key: API密钥 (上游同学专用)
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
            'User-Agent': 'ASR-Upstream-SDK/1.0.0'
        })
        
        # 任务缓存
        self.tasks: Dict[str, TaskInfo] = {}
        
        logger.info(f"ASR上游客户端初始化完成: {base_url}")
        logger.info("职责: 接收Web前端音频流 → 推送到ASR系统")
    
    def receive_audio_from_frontend(self, 
                                  audio_data: bytes, 
                                  user_id: str = None,
                                  session_id: str = None,
                                  metadata: Dict[str, Any] = None) -> Optional[str]:
        """
        接收来自Web前端的音频数据并推送到ASR系统
        
        Args:
            audio_data: 音频数据 (来自Web前端)
            user_id: 用户ID
            session_id: 会话ID
            metadata: 额外元数据
            
        Returns:
            str: 任务ID，如果失败返回None
        """
        try:
            logger.info(f"📥 接收Web前端音频数据: {len(audio_data)} bytes")
            
            # 构建任务元数据
            task_metadata = {
                "source": "web_frontend",
                "user_id": user_id,
                "session_id": session_id,
                "received_at": datetime.now().isoformat()
            }
            
            if metadata:
                task_metadata.update(metadata)
            
            # 创建转写任务
            task = self.create_task(
                task_id=f"frontend_{user_id}_{int(time.time())}" if user_id else None,
                metadata=task_metadata
            )
            
            if not task:
                logger.error("❌ 创建转写任务失败")
                return None
            
            # 上传音频数据到ASR系统
            success = self.upload_audio_data(task.task_id, audio_data)
            
            if success:
                logger.info(f"✅ 音频数据已推送到ASR系统: {task.task_id}")
                return task.task_id
            else:
                logger.error(f"❌ 音频数据推送失败: {task.task_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 接收前端音频异常: {e}")
            return None
    
    def process_frontend_audio_stream(self, 
                                    audio_stream: bytes, 
                                    chunk_size: int = 1024 * 1024,
                                    user_id: str = None,
                                    session_id: str = None) -> Optional[str]:
        """
        处理来自Web前端的音频流 (实时流式处理)
        
        Args:
            audio_stream: 音频流数据
            chunk_size: 分片大小
            user_id: 用户ID
            session_id: 会话ID
            
        Returns:
            str: 任务ID，如果失败返回None
        """
        try:
            logger.info(f"📥 接收Web前端音频流: {len(audio_stream)} bytes")
            
            # 创建任务
            task = self.create_task(
                task_id=f"stream_{user_id}_{int(time.time())}" if user_id else None,
                metadata={
                    "source": "web_frontend_stream",
                    "user_id": user_id,
                    "session_id": session_id,
                    "stream_mode": True
                }
            )
            
            if not task:
                return None
            
            # 流式上传音频数据
            success = self.upload_audio_data(task.task_id, audio_stream, chunk_size)
            
            if success:
                logger.info(f"✅ 音频流已推送到ASR系统: {task.task_id}")
                return task.task_id
            else:
                logger.error(f"❌ 音频流推送失败: {task.task_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 处理前端音频流异常: {e}")
            return None
    
    def create_task(self,
                   task_id: Optional[str] = None,
                   audio_config: Optional[AudioConfig] = None,
                   transcription_config: Optional[TranscriptionConfig] = None,
                   callback_config: Optional[CallbackConfig] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> TaskInfo:
        """
        创建转写任务
        
        Args:
            task_id: 任务ID，不提供则自动生成
            audio_config: 音频配置
            transcription_config: 转写配置
            callback_config: 回调配置
            metadata: 额外元数据
            
        Returns:
            TaskInfo: 任务信息
        """
        try:
            if not task_id:
                task_id = f"task_{uuid.uuid4().hex[:8]}"
            
            if not audio_config:
                audio_config = AudioConfig()
            
            if not transcription_config:
                transcription_config = TranscriptionConfig()
            
            if not callback_config:
                callback_config = CallbackConfig()
            
            # 构建请求数据
            request_data = {
                "task_id": task_id,
                "audio_config": asdict(audio_config),
                "transcription_config": asdict(transcription_config),
                "callback_config": asdict(callback_config),
                "metadata": metadata or {}
            }
            
            # 发送请求
            response = self._make_request(
                'POST',
                '/api/v1/tasks',
                json=request_data
            )
            
            if response.status_code == 200:
                data = response.json()['data']
                
                task_info = TaskInfo(
                    task_id=data['task_id'],
                    status=data['status'],
                    created_at=datetime.fromisoformat(data['created_at'].replace('Z', '+00:00')),
                    expires_at=datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00')),
                    upload_urls=data['upload_urls']
                )
                
                self.tasks[task_id] = task_info
                logger.info(f"✅ 任务创建成功: {task_id}")
                return task_info
            else:
                error_msg = f"创建任务失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"❌ 创建任务异常: {e}")
            raise
    
    def upload_audio_file(self, 
                         task_id: str, 
                         file_path: Union[str, Path],
                         chunk_size: int = 1024 * 1024) -> bool:
        """
        上传音频文件
        
        Args:
            task_id: 任务ID
            file_path: 音频文件路径
            chunk_size: 分片大小(字节)
            
        Returns:
            bool: 上传是否成功
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"音频文件不存在: {file_path}")
            
            # 检查文件大小
            file_size = file_path.stat().st_size
            if file_size > 50 * 1024 * 1024:  # 50MB限制
                raise ValueError(f"文件过大: {file_size} bytes")
            
            # 计算分片数量
            total_chunks = (file_size + chunk_size - 1) // chunk_size
            
            logger.info(f"📤 开始上传音频文件: {file_path}")
            logger.info(f"📊 文件大小: {file_size} bytes, 分片数: {total_chunks}")
            
            with open(file_path, 'rb') as f:
                for chunk_index in range(total_chunks):
                    # 读取分片数据
                    chunk_data = f.read(chunk_size)
                    is_final = (chunk_index == total_chunks - 1)
                    
                    # 上传分片
                    success = self._upload_chunk(
                        task_id, 
                        chunk_data, 
                        chunk_index, 
                        total_chunks, 
                        is_final
                    )
                    
                    if not success:
                        logger.error(f"❌ 分片 {chunk_index} 上传失败")
                        return False
                    
                    logger.info(f"📤 分片 {chunk_index + 1}/{total_chunks} 上传成功")
            
            logger.info(f"✅ 音频文件上传完成: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 上传音频文件异常: {e}")
            return False
    
    def upload_audio_data(self, 
                         task_id: str, 
                         audio_data: bytes,
                         chunk_size: int = 1024 * 1024) -> bool:
        """
        上传音频数据
        
        Args:
            task_id: 任务ID
            audio_data: 音频数据
            chunk_size: 分片大小(字节)
            
        Returns:
            bool: 上传是否成功
        """
        try:
            # 计算分片数量
            total_chunks = (len(audio_data) + chunk_size - 1) // chunk_size
            
            logger.info(f"📤 开始上传音频数据")
            logger.info(f"📊 数据大小: {len(audio_data)} bytes, 分片数: {total_chunks}")
            
            for chunk_index in range(total_chunks):
                # 获取分片数据
                start = chunk_index * chunk_size
                end = min(start + chunk_size, len(audio_data))
                chunk_data = audio_data[start:end]
                is_final = (chunk_index == total_chunks - 1)
                
                # 上传分片
                success = self._upload_chunk(
                    task_id, 
                    chunk_data, 
                    chunk_index, 
                    total_chunks, 
                    is_final
                )
                
                if not success:
                    logger.error(f"❌ 分片 {chunk_index} 上传失败")
                    return False
                
                logger.info(f"📤 分片 {chunk_index + 1}/{total_chunks} 上传成功")
            
            logger.info(f"✅ 音频数据上传完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 上传音频数据异常: {e}")
            return False
    
    def get_task_status(self, task_id: str) -> Optional[TaskInfo]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            TaskInfo: 任务信息
        """
        try:
            response = self._make_request(
                'GET',
                f'/api/v1/tasks/{task_id}/status'
            )
            
            if response.status_code == 200:
                data = response.json()['data']
                
                task_info = TaskInfo(
                    task_id=data['task_id'],
                    status=data['status'],
                    created_at=datetime.fromisoformat(data.get('created_at', '').replace('Z', '+00:00')),
                    expires_at=datetime.fromisoformat(data.get('expires_at', '').replace('Z', '+00:00')),
                    upload_urls=data.get('upload_urls', {}),
                    progress=data.get('progress', 0),
                    error_message=data.get('error_message')
                )
                
                # 更新缓存
                self.tasks[task_id] = task_info
                
                logger.info(f"📊 任务状态: {task_id} - {task_info.status} ({task_info.progress}%)")
                return task_info
            else:
                logger.error(f"❌ 获取任务状态失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取任务状态异常: {e}")
            return None
    
    def wait_for_completion(self, 
                           task_id: str, 
                           timeout: int = 300,
                           poll_interval: int = 5,
                           progress_callback: Optional[Callable[[TaskInfo], None]] = None) -> Optional[TaskInfo]:
        """
        等待任务完成
        
        Args:
            task_id: 任务ID
            timeout: 超时时间(秒)
            poll_interval: 轮询间隔(秒)
            progress_callback: 进度回调函数
            
        Returns:
            TaskInfo: 最终任务信息
        """
        try:
            start_time = time.time()
            logger.info(f"⏳ 等待任务完成: {task_id}")
            
            while time.time() - start_time < timeout:
                task_info = self.get_task_status(task_id)
                if not task_info:
                    logger.error(f"❌ 无法获取任务状态: {task_id}")
                    return None
                
                # 调用进度回调
                if progress_callback:
                    progress_callback(task_info)
                
                if task_info.status == "completed":
                    logger.info(f"✅ 任务完成: {task_id}")
                    return task_info
                elif task_info.status == "failed":
                    logger.error(f"❌ 任务失败: {task_id} - {task_info.error_message}")
                    return task_info
                
                logger.info(f"⏳ 任务进行中: {task_id} - {task_info.progress}%")
                time.sleep(poll_interval)
            
            logger.warning(f"⏰ 等待超时: {task_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ 等待任务完成异常: {e}")
            return None
    
    def get_task_results(self, task_id: str) -> List[Dict[str, Any]]:
        """
        获取任务转写结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            List[Dict]: 转写结果列表
        """
        try:
            response = self._make_request(
                'GET',
                f'/api/v1/tasks/{task_id}/results'
            )
            
            if response.status_code == 200:
                results = response.json()['data']
                logger.info(f"📝 获取到 {len(results)} 个转写结果")
                return results
            else:
                logger.error(f"❌ 获取转写结果失败: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ 获取转写结果异常: {e}")
            return []
    
    def download_results(self, task_id: str, output_dir: Union[str, Path] = ".") -> List[Path]:
        """
        下载转写结果文件
        
        Args:
            task_id: 任务ID
            output_dir: 输出目录
            
        Returns:
            List[Path]: 下载的文件路径列表
        """
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            response = self._make_request(
                'GET',
                f'/api/v1/tasks/{task_id}/results/download',
                headers={'Accept': 'application/zip'}
            )
            
            if response.status_code == 200:
                # 保存结果文件
                result_file = output_dir / f"{task_id}_results.zip"
                with open(result_file, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"💾 结果文件已下载: {result_file}")
                return [result_file]
            else:
                logger.error(f"❌ 下载结果文件失败: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ 下载结果文件异常: {e}")
            return []
    
    def _upload_chunk(self, 
                     task_id: str, 
                     chunk_data: bytes, 
                     chunk_index: int, 
                     total_chunks: int, 
                     is_final: bool) -> bool:
        """上传音频分片"""
        try:
            files = {
                'file': ('chunk', chunk_data, 'application/octet-stream')
            }
            data = {
                'chunk_index': chunk_index,
                'chunk_size': len(chunk_data),
                'total_chunks': total_chunks,
                'is_final': is_final
            }
            
            # 临时移除Content-Type头，让requests自动设置
            headers = {k: v for k, v in self.session.headers.items() if k.lower() != 'content-type'}
            
            response = requests.post(
                f"{self.base_url}/api/v1/tasks/{task_id}/audio",
                files=files,
                data=data,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"分片上传失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"分片上传异常: {e}")
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

class AsyncASRUpstreamClient:
    """异步ASR上游客户端"""
    
    def __init__(self, 
                 api_key: str,
                 base_url: str = "https://asr-api.com",
                 timeout: int = 30):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.tasks: Dict[str, TaskInfo] = {}
        
        logger.info(f"异步ASR上游客户端初始化完成: {base_url}")
    
    async def create_task(self,
                         task_id: Optional[str] = None,
                         audio_config: Optional[AudioConfig] = None,
                         transcription_config: Optional[TranscriptionConfig] = None,
                         callback_config: Optional[CallbackConfig] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> TaskInfo:
        """异步创建转写任务"""
        try:
            if not task_id:
                task_id = f"task_{uuid.uuid4().hex[:8]}"
            
            if not audio_config:
                audio_config = AudioConfig()
            
            if not transcription_config:
                transcription_config = TranscriptionConfig()
            
            if not callback_config:
                callback_config = CallbackConfig()
            
            request_data = {
                "task_id": task_id,
                "audio_config": asdict(audio_config),
                "transcription_config": asdict(transcription_config),
                "callback_config": asdict(callback_config),
                "metadata": metadata or {}
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/v1/tasks",
                    json=request_data,
                    headers={'Authorization': f'Bearer {self.api_key}'},
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = (await response.json())['data']
                        
                        task_info = TaskInfo(
                            task_id=data['task_id'],
                            status=data['status'],
                            created_at=datetime.fromisoformat(data['created_at'].replace('Z', '+00:00')),
                            expires_at=datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00')),
                            upload_urls=data['upload_urls']
                        )
                        
                        self.tasks[task_id] = task_info
                        logger.info(f"✅ 异步任务创建成功: {task_id}")
                        return task_info
                    else:
                        error_text = await response.text()
                        raise Exception(f"创建任务失败: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.error(f"❌ 异步创建任务异常: {e}")
            raise

# 使用示例
def example_usage():
    """使用示例"""
    # 初始化客户端
    client = ASRUpstreamClient(
        api_key="your_api_key",
        base_url="https://asr-api.com"
    )
    
    # 配置音频和转写参数
    audio_config = AudioConfig(
        format="wav",
        sample_rate=16000,
        channels=1
    )
    
    transcription_config = TranscriptionConfig(
        language="zh-CN",
        enable_punctuation=True,
        enable_speaker_diarization=True
    )
    
    callback_config = CallbackConfig(
        result_callback_url="https://your-app.com/webhook/asr-result"
    )
    
    try:
        # 创建转写任务
        task = client.create_task(
            task_id="my_task_001",
            audio_config=audio_config,
            transcription_config=transcription_config,
            callback_config=callback_config,
            metadata={"session_id": "session_123", "user_id": "user_456"}
        )
        
        print(f"任务创建成功: {task.task_id}")
        
        # 上传音频文件
        success = client.upload_audio_file(task.task_id, "audio.wav")
        if success:
            print("音频文件上传成功")
            
            # 等待任务完成
            def progress_callback(task_info):
                print(f"进度: {task_info.progress}%")
            
            final_task = client.wait_for_completion(
                task.task_id, 
                timeout=300,
                progress_callback=progress_callback
            )
            
            if final_task and final_task.status == "completed":
                print("任务完成！")
                
                # 获取转写结果
                results = client.get_task_results(task.task_id)
                for i, result in enumerate(results):
                    print(f"结果 {i+1}: {result['text']}")
                    print(f"置信度: {result['confidence']}")
                
                # 下载结果文件
                downloaded_files = client.download_results(task.task_id, "./results")
                print(f"结果文件已下载: {downloaded_files}")
            else:
                print("任务失败或超时")
        else:
            print("音频文件上传失败")
    
    except Exception as e:
        print(f"操作失败: {e}")

if __name__ == "__main__":
    example_usage()
