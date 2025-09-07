#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息队列管理器 - 用于ASR结果推送和接收
支持多种消息队列后端：Redis、RabbitMQ、文件队列等
"""

import json
import time
import os
import threading
import uuid
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MessageQueueManager:
    """消息队列管理器 - 统一接口支持多种后端"""
    
    def __init__(self, backend="file", **kwargs):
        """
        初始化消息队列管理器
        
        Args:
            backend: 后端类型 ("file", "redis", "rabbitmq")
            **kwargs: 后端特定配置
        """
        self.backend = backend
        self.config = kwargs
        self.sent_messages = set()  # 记录已发送的消息，防止重复
        
        # 根据后端类型初始化
        if backend == "file":
            self.queue_dir = kwargs.get("queue_dir", "message_queue")
            self.max_file_size = kwargs.get("max_file_size", 10 * 1024 * 1024)  # 10MB
            os.makedirs(self.queue_dir, exist_ok=True)
            logger.info(f"文件队列初始化完成: {self.queue_dir}")
            
        elif backend == "redis":
            try:
                import redis
                self.redis_client = redis.Redis(
                    host=kwargs.get("host", "localhost"),
                    port=kwargs.get("port", 6379),
                    db=kwargs.get("db", 0),
                    password=kwargs.get("password", None)
                )
                # 测试连接
                self.redis_client.ping()
                logger.info("Redis队列初始化完成")
            except ImportError:
                logger.error("Redis库未安装，请运行: pip install redis")
                raise
            except Exception as e:
                logger.error(f"Redis连接失败: {e}")
                raise
                
        elif backend == "rabbitmq":
            try:
                import pika
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=kwargs.get("host", "localhost"),
                        port=kwargs.get("port", 5672),
                        virtual_host=kwargs.get("virtual_host", "/"),
                        credentials=pika.PlainCredentials(
                            kwargs.get("username", "guest"),
                            kwargs.get("password", "guest")
                        )
                    )
                )
                self.channel = self.connection.channel()
                self.queue_name = kwargs.get("queue_name", "asr_results")
                self.channel.queue_declare(queue=self.queue_name, durable=True)
                logger.info("RabbitMQ队列初始化完成")
            except ImportError:
                logger.error("pika库未安装，请运行: pip install pika")
                raise
            except Exception as e:
                logger.error(f"RabbitMQ连接失败: {e}")
                raise
        else:
            raise ValueError(f"不支持的后端类型: {backend}")
    
    def _generate_message_id(self, content: str) -> str:
        """生成消息唯一ID，用于防重复"""
        import hashlib
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        timestamp = int(time.time())
        return f"{timestamp}_{content_hash[:8]}"
    
    def _is_duplicate(self, message_id: str) -> bool:
        """检查是否为重复消息"""
        return message_id in self.sent_messages
    
    def _mark_sent(self, message_id: str):
        """标记消息已发送"""
        self.sent_messages.add(message_id)
        # 限制缓存大小，避免内存泄漏
        if len(self.sent_messages) > 1000:
            # 保留最近500个
            self.sent_messages = set(list(self.sent_messages)[-500:])
    
    def send_message(self, message_data: Dict[str, Any], topic: str = "asr_results") -> bool:
        """
        发送消息到队列
        
        Args:
            message_data: 消息数据
            topic: 主题/队列名称
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 生成消息ID
            message_id = self._generate_message_id(json.dumps(message_data, sort_keys=True))
            
            # 检查重复
            if self._is_duplicate(message_id):
                logger.warning(f"检测到重复消息，跳过发送: {message_id}")
                return True  # 重复消息视为成功
            
            # 构建完整消息
            full_message = {
                "message_id": message_id,
                "topic": topic,
                "timestamp": datetime.now().isoformat(),
                "data": message_data
            }
            
            # 根据后端发送消息
            if self.backend == "file":
                return self._send_to_file(full_message, topic)
            elif self.backend == "redis":
                return self._send_to_redis(full_message, topic)
            elif self.backend == "rabbitmq":
                return self._send_to_rabbitmq(full_message, topic)
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    def _send_to_file(self, message: Dict[str, Any], topic: str) -> bool:
        """发送消息到文件队列"""
        try:
            # 创建主题目录
            topic_dir = os.path.join(self.queue_dir, topic)
            os.makedirs(topic_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = int(time.time() * 1000)  # 毫秒时间戳
            filename = f"{timestamp}_{message['message_id']}.json"
            filepath = os.path.join(topic_dir, filename)
            
            # 写入消息
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(message, f, ensure_ascii=False, indent=2)
            
            # 标记已发送
            self._mark_sent(message['message_id'])
            
            logger.info(f"消息已发送到文件队列: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"发送到文件队列失败: {e}")
            return False
    
    def _send_to_redis(self, message: Dict[str, Any], topic: str) -> bool:
        """发送消息到Redis队列"""
        try:
            queue_key = f"queue:{topic}"
            message_json = json.dumps(message, ensure_ascii=False)
            
            # 使用LPUSH添加到队列头部
            self.redis_client.lpush(queue_key, message_json)
            
            # 标记已发送
            self._mark_sent(message['message_id'])
            
            logger.info(f"消息已发送到Redis队列: {queue_key}")
            return True
            
        except Exception as e:
            logger.error(f"发送到Redis队列失败: {e}")
            return False
    
    def _send_to_rabbitmq(self, message: Dict[str, Any], topic: str) -> bool:
        """发送消息到RabbitMQ队列"""
        try:
            message_json = json.dumps(message, ensure_ascii=False)
            
            # 发布消息
            self.channel.basic_publish(
                exchange='',
                routing_key=topic,
                body=message_json,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 消息持久化
                    message_id=message['message_id'],
                    timestamp=int(time.time())
                )
            )
            
            # 标记已发送
            self._mark_sent(message['message_id'])
            
            logger.info(f"消息已发送到RabbitMQ队列: {topic}")
            return True
            
        except Exception as e:
            logger.error(f"发送到RabbitMQ队列失败: {e}")
            return False
    
    def close(self):
        """关闭连接"""
        try:
            if self.backend == "redis" and hasattr(self, 'redis_client'):
                self.redis_client.close()
            elif self.backend == "rabbitmq" and hasattr(self, 'connection'):
                self.connection.close()
            logger.info("消息队列连接已关闭")
        except Exception as e:
            logger.error(f"关闭消息队列连接失败: {e}")

# 全局消息队列管理器实例
mq_manager = None

def init_message_queue(backend="file", **kwargs):
    """初始化全局消息队列管理器"""
    global mq_manager
    try:
        mq_manager = MessageQueueManager(backend, **kwargs)
        logger.info(f"全局消息队列管理器初始化完成: {backend}")
        return True
    except Exception as e:
        logger.error(f"初始化消息队列失败: {e}")
        return False

def send_asr_result(content: str, filename: str, reason: str, force: bool = False, stream_id: str = None) -> bool:
    """
    发送ASR转写结果到消息队列
    
    Args:
        content: 转写结果内容
        filename: 输出文件名
        reason: 输出原因 (end_message, timeout, etc.)
        force: 是否为强制输出
        stream_id: 流ID
        
    Returns:
        bool: 发送是否成功
    """
    global mq_manager
    
    if mq_manager is None:
        logger.warning("消息队列管理器未初始化，跳过消息发送")
        return False
    
    try:
        # 构建ASR结果消息
        asr_message = {
            "type": "asr_result",
            "content": content,
            "filename": filename,
            "reason": reason,
            "force": force,
            "stream_id": stream_id,
            "timestamp": time.time(),
            "source": "asr_system"
        }
        
        # 发送到队列
        success = mq_manager.send_message(asr_message, topic="asr_results")
        
        if success:
            logger.info(f"ASR结果已发送到消息队列: {filename}")
        else:
            logger.error(f"ASR结果发送到消息队列失败: {filename}")
        
        return success
        
    except Exception as e:
        logger.error(f"发送ASR结果到消息队列异常: {e}")
        return False

def close_message_queue():
    """关闭全局消息队列管理器"""
    global mq_manager
    if mq_manager:
        mq_manager.close()
        mq_manager = None
        logger.info("全局消息队列管理器已关闭")
