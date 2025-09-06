#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASR转写模块 - 完整工作流程集成示例
展示Web前端 → 上游同学 → ASR系统 → 下游同学 → Web前端的完整流程
"""

import asyncio
import json
import time
import uuid
import websockets
from typing import Dict, Any, Optional
import logging
from datetime import datetime

# 导入SDK
from upstream_sdk import ASRUpstreamClient
from downstream_sdk import ASRDownstreamClient

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# 1. 上游同学模块 (音频推送)
# ============================================================================

class UpstreamAudioProcessor:
    """上游同学 - 负责接收Web前端音频并推送到ASR系统"""
    
    def __init__(self, asr_api_key: str, asr_base_url: str):
        self.asr_client = ASRUpstreamClient(
            api_key=asr_api_key,
            base_url=asr_base_url
        )
        self.frontend_ws_server = None
        
    async def start_frontend_server(self, host: str = "localhost", port: int = 8080):
        """启动WebSocket服务器接收前端音频"""
        async def handle_frontend_connection(websocket, path):
            logger.info(f"🔗 Web前端连接: {websocket.remote_address}")
            
            try:
                async for message in websocket:
                    data = json.loads(message)
                    
                    if data.get("type") == "audio_data":
                        # 接收前端音频数据
                        task_id = await self.process_frontend_audio(data)
                        
                        # 发送确认消息给前端
                        response = {
                            "type": "audio_received",
                            "task_id": task_id,
                            "status": "processing" if task_id else "failed",
                            "timestamp": datetime.now().isoformat()
                        }
                        await websocket.send(json.dumps(response))
                    
                    elif data.get("type") == "ping":
                        # 响应心跳
                        pong_response = {"type": "pong", "timestamp": datetime.now().isoformat()}
                        await websocket.send(json.dumps(pong_response))
            
            except websockets.exceptions.ConnectionClosed:
                logger.info("🔌 Web前端连接已关闭")
            except Exception as e:
                logger.error(f"❌ 处理前端连接异常: {e}")
        
        self.frontend_ws_server = await websockets.serve(
            handle_frontend_connection, host, port
        )
        logger.info(f"🚀 上游服务启动: ws://{host}:{port}")
    
    async def process_frontend_audio(self, data: Dict[str, Any]) -> Optional[str]:
        """处理来自前端的音频数据"""
        try:
            # 提取音频数据
            audio_data = data.get("audio_data", "").encode()  # 假设是base64编码
            user_id = data.get("user_id")
            session_id = data.get("session_id")
            
            logger.info(f"📥 接收前端音频: user_id={user_id}, size={len(audio_data)}")
            
            # 推送到ASR系统
            task_id = self.asr_client.receive_audio_from_frontend(
                audio_data=audio_data,
                user_id=user_id,
                session_id=session_id,
                metadata={
                    "frontend_timestamp": data.get("timestamp"),
                    "audio_format": data.get("format", "wav")
                }
            )
            
            if task_id:
                logger.info(f"✅ 音频已推送到ASR系统: {task_id}")
                return task_id
            else:
                logger.error("❌ 音频推送失败")
                return None
                
        except Exception as e:
            logger.error(f"❌ 处理前端音频异常: {e}")
            return None

# ============================================================================
# 2. 下游同学模块 (语义分析)
# ============================================================================

class DownstreamSemanticAnalyzer:
    """下游同学 - 负责接收ASR结果并进行语义分析"""
    
    def __init__(self, asr_api_key: str, asr_base_url: str):
        self.asr_client = ASRDownstreamClient(
            api_key=asr_api_key,
            base_url=asr_base_url
        )
        self.frontend_ws_clients = set()
        
    async def start_frontend_server(self, host: str = "localhost", port: int = 8081):
        """启动WebSocket服务器向前端推送结果"""
        async def handle_frontend_connection(websocket, path):
            logger.info(f"🔗 Web前端连接: {websocket.remote_address}")
            self.frontend_ws_clients.add(websocket)
            
            try:
                async for message in websocket:
                    data = json.loads(message)
                    
                    if data.get("type") == "ping":
                        # 响应心跳
                        pong_response = {"type": "pong", "timestamp": datetime.now().isoformat()}
                        await websocket.send(json.dumps(pong_response))
            
            except websockets.exceptions.ConnectionClosed:
                logger.info("🔌 Web前端连接已关闭")
                self.frontend_ws_clients.discard(websocket)
            except Exception as e:
                logger.error(f"❌ 处理前端连接异常: {e}")
                self.frontend_ws_clients.discard(websocket)
        
        self.frontend_ws_server = await websockets.serve(
            handle_frontend_connection, host, port
        )
        logger.info(f"🚀 下游服务启动: ws://{host}:{port}")
    
    async def process_asr_result(self, task_id: str):
        """处理ASR转写结果"""
        try:
            logger.info(f"📥 开始处理ASR结果: {task_id}")
            
            # 获取转写结果
            results = self.asr_client.get_task_results(task_id)
            if not results:
                logger.error(f"❌ 未找到转写结果: {task_id}")
                return
            
            # 提取转写文本
            transcription_text = results[0].text
            logger.info(f"📝 转写文本: {transcription_text}")
            
            # 进行语义分析
            analysis_result = self.perform_semantic_analysis(transcription_text)
            
            # 推送到前端
            await self.push_to_frontend(task_id, analysis_result)
            
            logger.info(f"✅ 语义分析完成: {task_id}")
            
        except Exception as e:
            logger.error(f"❌ 处理ASR结果异常: {e}")
    
    def perform_semantic_analysis(self, text: str) -> Dict[str, Any]:
        """执行语义分析 (下游同学需要实现具体逻辑)"""
        # 这里实现你的语义分析逻辑
        # 例如：情感分析、意图识别、实体提取等
        
        # 模拟分析结果
        analysis_result = {
            "text": text,
            "sentiment": "positive" if "好" in text or "棒" in text else "neutral",
            "intent": "question" if "?" in text or "？" in text else "statement",
            "entities": self._extract_entities(text),
            "keywords": self._extract_keywords(text),
            "summary": text[:50] + "..." if len(text) > 50 else text,
            "confidence": 0.85,
            "analysis_time": datetime.now().isoformat()
        }
        
        return analysis_result
    
    def _extract_entities(self, text: str) -> list:
        """提取实体 (示例实现)"""
        # 这里实现实体提取逻辑
        entities = []
        if "时间" in text:
            entities.append({"type": "time", "value": "时间"})
        if "地点" in text:
            entities.append({"type": "location", "value": "地点"})
        return entities
    
    def _extract_keywords(self, text: str) -> list:
        """提取关键词 (示例实现)"""
        # 这里实现关键词提取逻辑
        keywords = []
        words = text.split()
        for word in words:
            if len(word) > 2:  # 简单过滤
                keywords.append(word)
        return keywords[:5]  # 返回前5个关键词
    
    async def push_to_frontend(self, task_id: str, analysis_result: Dict[str, Any]):
        """推送分析结果到前端"""
        try:
            message = {
                "type": "semantic_analysis_result",
                "task_id": task_id,
                "result": analysis_result,
                "timestamp": datetime.now().isoformat()
            }
            
            # 推送给所有连接的前端客户端
            disconnected_clients = set()
            for websocket in self.frontend_ws_clients:
                try:
                    await websocket.send(json.dumps(message))
                    logger.info(f"📡 结果已推送到前端: {task_id}")
                except websockets.exceptions.ConnectionClosed:
                    disconnected_clients.add(websocket)
                except Exception as e:
                    logger.error(f"❌ 推送到前端失败: {e}")
                    disconnected_clients.add(websocket)
            
            # 清理断开的连接
            self.frontend_ws_clients -= disconnected_clients
            
        except Exception as e:
            logger.error(f"❌ 推送结果到前端异常: {e}")

# ============================================================================
# 3. Web前端模拟客户端
# ============================================================================

class WebFrontendSimulator:
    """Web前端模拟器 - 模拟用户录音和结果展示"""
    
    def __init__(self, upstream_ws_url: str, downstream_ws_url: str):
        self.upstream_ws_url = upstream_ws_url
        self.downstream_ws_url = downstream_ws_url
        self.upstream_ws = None
        self.downstream_ws = None
        
    async def connect_to_services(self):
        """连接到上游和下游服务"""
        try:
            # 连接上游服务
            self.upstream_ws = await websockets.connect(self.upstream_ws_url)
            logger.info("✅ 已连接到上游服务")
            
            # 连接下游服务
            self.downstream_ws = await websockets.connect(self.downstream_ws_url)
            logger.info("✅ 已连接到下游服务")
            
            return True
        except Exception as e:
            logger.error(f"❌ 连接服务失败: {e}")
            return False
    
    async def simulate_audio_recording(self, audio_text: str = "你好，这是一个测试音频"):
        """模拟音频录制和发送"""
        try:
            # 模拟音频数据 (实际应该是真实的音频数据)
            audio_data = audio_text.encode('utf-8')
            
            # 发送音频到上游
            message = {
                "type": "audio_data",
                "audio_data": audio_data.decode('utf-8'),  # 模拟base64编码
                "user_id": f"user_{uuid.uuid4().hex[:8]}",
                "session_id": f"session_{int(time.time())}",
                "format": "wav",
                "timestamp": datetime.now().isoformat()
            }
            
            await self.upstream_ws.send(json.dumps(message))
            logger.info(f"📤 音频已发送到上游: {audio_text}")
            
            # 等待上游确认
            response = await self.upstream_ws.recv()
            response_data = json.loads(response)
            
            if response_data.get("type") == "audio_received":
                task_id = response_data.get("task_id")
                logger.info(f"📨 上游确认: task_id={task_id}")
                return task_id
            
        except Exception as e:
            logger.error(f"❌ 模拟音频录制异常: {e}")
            return None
    
    async def listen_for_analysis_results(self):
        """监听语义分析结果"""
        try:
            while True:
                message = await self.downstream_ws.recv()
                data = json.loads(message)
                
                if data.get("type") == "semantic_analysis_result":
                    result = data.get("result")
                    task_id = data.get("task_id")
                    
                    logger.info(f"📨 收到语义分析结果: {task_id}")
                    logger.info(f"📝 分析结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
                    
                    # 这里可以更新前端UI显示结果
                    self.display_analysis_result(result)
                    
                elif data.get("type") == "pong":
                    logger.debug("💓 收到下游心跳响应")
        
        except websockets.exceptions.ConnectionClosed:
            logger.info("🔌 下游连接已关闭")
        except Exception as e:
            logger.error(f"❌ 监听分析结果异常: {e}")
    
    def display_analysis_result(self, result: Dict[str, Any]):
        """显示分析结果 (模拟前端UI更新)"""
        print("\n" + "="*60)
        print("🎯 语义分析结果")
        print("="*60)
        print(f"📝 原文: {result.get('text', '')}")
        print(f"😊 情感: {result.get('sentiment', 'unknown')}")
        print(f"🎯 意图: {result.get('intent', 'unknown')}")
        print(f"🏷️  实体: {', '.join([e.get('value', '') for e in result.get('entities', [])])}")
        print(f"🔑 关键词: {', '.join(result.get('keywords', []))}")
        print(f"📄 摘要: {result.get('summary', '')}")
        print(f"🎯 置信度: {result.get('confidence', 0):.2f}")
        print("="*60 + "\n")

# ============================================================================
# 4. 完整工作流程演示
# ============================================================================

async def run_complete_workflow():
    """运行完整的工作流程演示"""
    logger.info("🚀 开始完整工作流程演示")
    
    # 配置参数
    ASR_API_KEY = "your_asr_api_key"
    ASR_BASE_URL = "https://asr-api.your-domain.com"
    
    # 1. 启动上游服务
    upstream_processor = UpstreamAudioProcessor(ASR_API_KEY, ASR_BASE_URL)
    await upstream_processor.start_frontend_server("localhost", 8080)
    
    # 2. 启动下游服务
    downstream_analyzer = DownstreamSemanticAnalyzer(ASR_API_KEY, ASR_BASE_URL)
    await downstream_analyzer.start_frontend_server("localhost", 8081)
    
    # 3. 启动前端模拟器
    frontend_simulator = WebFrontendSimulator(
        "ws://localhost:8080",
        "ws://localhost:8081"
    )
    
    # 连接服务
    if not await frontend_simulator.connect_to_services():
        logger.error("❌ 前端连接失败")
        return
    
    # 4. 模拟用户录音
    test_audios = [
        "你好，今天天气怎么样？",
        "我想预订明天的会议室",
        "这个产品真的很棒，我很满意",
        "请问你们的工作时间是什么时候？"
    ]
    
    for i, audio_text in enumerate(test_audios):
        logger.info(f"\n🎤 模拟录音 {i+1}: {audio_text}")
        
        # 发送音频
        task_id = await frontend_simulator.simulate_audio_recording(audio_text)
        
        if task_id:
            # 等待一段时间让ASR处理
            await asyncio.sleep(2)
            
            # 模拟下游处理ASR结果
            await downstream_analyzer.process_asr_result(task_id)
            
            # 等待前端接收结果
            await asyncio.sleep(1)
        
        # 间隔
        await asyncio.sleep(3)
    
    logger.info("✅ 完整工作流程演示完成")

# ============================================================================
# 5. 单独测试各个模块
# ============================================================================

async def test_upstream_only():
    """单独测试上游模块"""
    logger.info("🧪 测试上游模块")
    
    upstream_processor = UpstreamAudioProcessor("test_api_key", "http://localhost:9000")
    await upstream_processor.start_frontend_server("localhost", 8080)
    
    # 保持服务运行
    await asyncio.sleep(60)

async def test_downstream_only():
    """单独测试下游模块"""
    logger.info("🧪 测试下游模块")
    
    downstream_analyzer = DownstreamSemanticAnalyzer("test_api_key", "http://localhost:9000")
    await downstream_analyzer.start_frontend_server("localhost", 8081)
    
    # 模拟处理ASR结果
    await downstream_analyzer.process_asr_result("test_task_001")
    
    # 保持服务运行
    await asyncio.sleep(60)

async def test_frontend_only():
    """单独测试前端模块"""
    logger.info("🧪 测试前端模块")
    
    frontend_simulator = WebFrontendSimulator(
        "ws://localhost:8080",
        "ws://localhost:8081"
    )
    
    if await frontend_simulator.connect_to_services():
        # 发送测试音频
        await frontend_simulator.simulate_audio_recording("测试音频内容")
        
        # 监听结果
        await frontend_simulator.listen_for_analysis_results()

# ============================================================================
# 主函数
# ============================================================================

async def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        test_mode = sys.argv[1]
        
        if test_mode == "upstream":
            await test_upstream_only()
        elif test_mode == "downstream":
            await test_downstream_only()
        elif test_mode == "frontend":
            await test_frontend_only()
        elif test_mode == "complete":
            await run_complete_workflow()
        else:
            print("用法: python workflow_integration_examples.py [upstream|downstream|frontend|complete]")
    else:
        # 默认运行完整流程
        await run_complete_workflow()

if __name__ == "__main__":
    asyncio.run(main())
