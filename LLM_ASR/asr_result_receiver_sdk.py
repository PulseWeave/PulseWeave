#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASR结果接收SDK - 供下一个模块接收ASR转写结果
支持多种消息队列后端：文件队列、Redis、RabbitMQ
"""

import json
import time
import os
import threading
import logging
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
import glob

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ASRResultReceiver:
    """ASR结果接收器 - 从消息队列接收转写结果"""
    
    def __init__(self, backend="file", **kwargs):
        """
        初始化ASR结果接收器
        
        Args:
            backend: 后端类型 ("file", "redis", "rabbitmq")
            **kwargs: 后端特定配置
        """
        self.backend = backend
        self.config = kwargs
        self.is_running = False
        self.received_messages = set()  # 记录已接收的消息，防止重复处理
        self.callbacks = []  # 结果处理回调函数列表
        
        # 根据后端类型初始化
        if backend == "file":
            self.queue_dir = kwargs.get("queue_dir", "message_queue")
            self.processed_dir = os.path.join(self.queue_dir, "processed")
            os.makedirs(self.processed_dir, exist_ok=True)
            logger.info(f"文件队列接收器初始化完成: {self.queue_dir}")
            
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
                logger.info("Redis队列接收器初始化完成")
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
                logger.info("RabbitMQ队列接收器初始化完成")
            except ImportError:
                logger.error("pika库未安装，请运行: pip install pika")
                raise
            except Exception as e:
                logger.error(f"RabbitMQ连接失败: {e}")
                raise
        else:
            raise ValueError(f"不支持的后端类型: {backend}")
    
    def add_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        添加结果处理回调函数
        
        Args:
            callback: 处理ASR结果的回调函数，接收一个字典参数
        """
        self.callbacks.append(callback)
        logger.info(f"已添加结果处理回调函数: {callback.__name__}")
    
    def _is_duplicate(self, message_id: str) -> bool:
        """检查是否为重复消息"""
        return message_id in self.received_messages
    
    def _mark_received(self, message_id: str):
        """标记消息已接收"""
        self.received_messages.add(message_id)
        # 限制缓存大小，避免内存泄漏
        if len(self.received_messages) > 1000:
            # 保留最近500个
            self.received_messages = set(list(self.received_messages)[-500:])
    
    def _process_message(self, message: Dict[str, Any]):
        """处理接收到的消息"""
        try:
            message_id = message.get("message_id")
            if not message_id:
                logger.warning("消息缺少message_id，跳过处理")
                return
            
            # 检查重复
            if self._is_duplicate(message_id):
                logger.debug(f"检测到重复消息，跳过处理: {message_id}")
                return
            
            # 标记已接收
            self._mark_received(message_id)
            
            # 提取ASR结果数据
            asr_data = message.get("data", {})
            if asr_data.get("type") != "asr_result":
                logger.debug(f"非ASR结果消息，跳过处理: {asr_data.get('type')}")
                return
            
            logger.info(f"收到ASR转写结果: {asr_data.get('filename', 'unknown')}")
            
            # 调用所有回调函数
            for callback in self.callbacks:
                try:
                    callback(asr_data)
                except Exception as e:
                    logger.error(f"回调函数 {callback.__name__} 处理异常: {e}")
            
        except Exception as e:
            logger.error(f"处理消息异常: {e}")
    
    def _receive_from_file(self):
        """从文件队列接收消息"""
        try:
            topic_dir = os.path.join(self.queue_dir, "asr_results")
            if not os.path.exists(topic_dir):
                return
            
            # 查找所有未处理的JSON文件
            pattern = os.path.join(topic_dir, "*.json")
            files = glob.glob(pattern)
            
            for filepath in sorted(files):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        message = json.load(f)
                    
                    # 处理消息
                    self._process_message(message)
                    
                    # 移动文件到已处理目录
                    filename = os.path.basename(filepath)
                    processed_path = os.path.join(self.processed_dir, filename)
                    os.rename(filepath, processed_path)
                    logger.debug(f"消息文件已移动到已处理目录: {filename}")
                    
                except Exception as e:
                    logger.error(f"处理文件 {filepath} 异常: {e}")
                    # 移动失败的文件到错误目录
                    error_dir = os.path.join(self.queue_dir, "error")
                    os.makedirs(error_dir, exist_ok=True)
                    try:
                        error_path = os.path.join(error_dir, os.path.basename(filepath))
                        os.rename(filepath, error_path)
                    except:
                        pass
            
        except Exception as e:
            logger.error(f"从文件队列接收消息异常: {e}")
    
    def _receive_from_redis(self):
        """从Redis队列接收消息"""
        try:
            queue_key = "queue:asr_results"
            
            # 使用BRPOP阻塞式接收消息
            result = self.redis_client.brpop(queue_key, timeout=1)
            if result:
                _, message_json = result
                message = json.loads(message_json)
                self._process_message(message)
            
        except Exception as e:
            logger.error(f"从Redis队列接收消息异常: {e}")
    
    def _receive_from_rabbitmq(self):
        """从RabbitMQ队列接收消息"""
        try:
            # 设置消费者
            def callback(ch, method, properties, body):
                try:
                    message = json.loads(body)
                    self._process_message(message)
                    # 确认消息
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    logger.error(f"处理RabbitMQ消息异常: {e}")
                    # 拒绝消息，不重新入队
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            # 开始消费
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=callback
            )
            
            # 处理一个消息后返回
            self.channel.connection.process_data_events(time_limit=1)
            
        except Exception as e:
            logger.error(f"从RabbitMQ队列接收消息异常: {e}")
    
    def receive_once(self) -> bool:
        """
        接收一次消息
        
        Returns:
            bool: 是否成功接收并处理了消息
        """
        try:
            if self.backend == "file":
                self._receive_from_file()
            elif self.backend == "redis":
                self._receive_from_rabbitmq()
            elif self.backend == "rabbitmq":
                self._receive_from_rabbitmq()
            
            return True
            
        except Exception as e:
            logger.error(f"接收消息异常: {e}")
            return False
    
    def start_listening(self, interval: float = 1.0):
        """
        开始持续监听消息队列
        
        Args:
            interval: 检查间隔（秒）
        """
        if self.is_running:
            logger.warning("接收器已在运行中")
            return
        
        self.is_running = True
        logger.info(f"开始监听消息队列，检查间隔: {interval}秒")
        
        try:
            while self.is_running:
                self.receive_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("用户中断监听")
        except Exception as e:
            logger.error(f"监听异常: {e}")
        finally:
            self.is_running = False
            logger.info("监听已停止")
    
    def stop_listening(self):
        """停止监听"""
        self.is_running = False
        logger.info("正在停止监听...")
    
    def get_status(self) -> Dict[str, Any]:
        """获取接收器状态"""
        return {
            "backend": self.backend,
            "is_running": self.is_running,
            "received_count": len(self.received_messages),
            "callback_count": len(self.callbacks),
            "config": self.config
        }
    
    def close(self):
        """关闭接收器"""
        self.stop_listening()
        
        try:
            if self.backend == "redis" and hasattr(self, 'redis_client'):
                self.redis_client.close()
            elif self.backend == "rabbitmq" and hasattr(self, 'connection'):
                self.connection.close()
            logger.info("接收器已关闭")
        except Exception as e:
            logger.error(f"关闭接收器异常: {e}")

# 便捷函数
def create_asr_receiver(backend="file", **kwargs) -> ASRResultReceiver:
    """
    创建ASR结果接收器
    
    Args:
        backend: 后端类型
        **kwargs: 配置参数
        
    Returns:
        ASRResultReceiver: 接收器实例
    """
    return ASRResultReceiver(backend, **kwargs)

def process_asr_result(result_data: Dict[str, Any]):
    """
    默认的ASR结果处理函数（示例）
    
    Args:
        result_data: ASR结果数据
    """
    print("="*60)
    print("🎯 收到ASR转写结果")
    print("="*60)
    print(f"📝 文件名: {result_data.get('filename', 'unknown')}")
    print(f"📄 内容: {result_data.get('content', '')}")
    print(f"🎯 原因: {result_data.get('reason', 'unknown')}")
    print(f"⚡ 强制输出: {result_data.get('force', False)}")
    print(f"🆔 流ID: {result_data.get('stream_id', 'unknown')}")
    print(f"⏰ 时间戳: {result_data.get('timestamp', 'unknown')}")
    print("="*60)

# 使用示例
if __name__ == "__main__":
    # 创建接收器
    receiver = create_asr_receiver(
        backend="file",
        queue_dir="message_queue"
    )
    
    # 添加处理回调
    receiver.add_callback(process_asr_result)
    
    # 开始监听
    try:
        receiver.start_listening(interval=1.0)
    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        receiver.close()
