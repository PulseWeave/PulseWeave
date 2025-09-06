# -*- encoding:utf-8 -*-
import hashlib
import hmac
import base64
import json
import time
import threading
import urllib.parse
import logging
import uuid
import os
import queue
import requests
from websocket import create_connection, WebSocketException
import websocket
import datetime

# 异步 WebSocket 服务端库
import asyncio
import websockets


# ---------------- WebSocket 服务端管理类 ----------------
class WebSocketServerManager:
    """WebSocket服务器管理器 - 用于向前端推送ASR结果"""

    def __init__(self, host="0.0.0.0", port=9000):
        self.host = host
        self.port = port
        self.clients = set()  # 存放所有连接的前端客户端
        self.ws_loop = None  # 后台 WebSocket 服务所用的事件循环对象
        self.ws_ready = threading.Event()  # 服务启动完成标志
        self.server_thread = None
        self.is_running = False
        self.connection_count = 0
        self.total_messages_sent = 0

    def log(self, level, message):
        """统一的日志记录方法"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [WebSocket-{level}] {message}")

    async def handle_client(self, websocket, path=None):
        """处理每个 WebSocket 客户端连接"""
        client_id = f"client_{self.connection_count}"
        self.connection_count += 1
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"

        # 处理不同版本的websockets库参数差异
        if path is None:
            path = getattr(websocket, 'path', '/')

        self.log("INFO", f"新客户端连接: {client_id} from {client_ip}, 路径: {path}")

        self.clients.add(websocket)
        self.log("INFO", f"客户端 {client_id} 已连接，当前连接数: {len(self.clients)}")

        try:
            # 发送连接成功消息
            welcome_msg = {
                "type": "connection",
                "status": "success",
                "client_id": client_id,
                "message": "连接成功，等待ASR结果推送",
                "timestamp": time.time()
            }
            await websocket.send(json.dumps(welcome_msg, ensure_ascii=False))
            self.log("INFO", f"已向客户端 {client_id} 发送欢迎消息")

            # 保持连接活跃 - 简化心跳机制
            while True:
                try:
                    # 等待客户端消息，设置较长的超时时间
                    message = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                    self.log("DEBUG", f"收到客户端 {client_id} 消息: {message}")

                    # 处理客户端消息
                    try:
                        msg_data = json.loads(message)
                        if msg_data.get("type") == "ping":
                            # 响应客户端心跳
                            pong_msg = {
                                "type": "pong",
                                "timestamp": time.time()
                            }
                            await websocket.send(json.dumps(pong_msg, ensure_ascii=False))
                            self.log("DEBUG", f"向客户端 {client_id} 发送心跳响应")
                        elif msg_data.get("type") == "pong":
                            # 客户端响应服务器心跳
                            self.log("DEBUG", f"收到客户端 {client_id} 心跳响应")
                    except json.JSONDecodeError:
                        # 忽略非JSON消息
                        pass

                except asyncio.TimeoutError:
                    # 超时发送心跳，保持连接活跃
                    try:
                        ping_msg = {
                            "type": "ping",
                            "timestamp": time.time()
                        }
                        await websocket.send(json.dumps(ping_msg, ensure_ascii=False))
                        self.log("DEBUG", f"向客户端 {client_id} 发送心跳")
                    except websockets.exceptions.ConnectionClosed:
                        self.log("INFO", f"客户端 {client_id} 连接已关闭（心跳发送失败）")
                        break
                    except Exception as e:
                        self.log("WARNING", f"向客户端 {client_id} 发送心跳失败: {e}")
                        break

                except websockets.exceptions.ConnectionClosed:
                    self.log("INFO", f"客户端 {client_id} 主动关闭连接")
                    break

                except Exception as e:
                    self.log("ERROR", f"处理客户端 {client_id} 消息时出错: {e}")
                    break

        except websockets.exceptions.ConnectionClosed:
            self.log("INFO", f"客户端 {client_id} 连接已关闭")
        except Exception as e:
            self.log("ERROR", f"客户端 {client_id} 连接处理出错: {e}")
        finally:
            try:
                self.clients.remove(websocket)
                self.log("INFO", f"客户端 {client_id} 已断开，当前连接数: {len(self.clients)}")
            except Exception:
                pass

    async def start_server_async(self):
        """异步启动WebSocket服务器"""
        try:
            self.log("INFO", f"正在启动WebSocket服务器...")
            self.log("INFO", f"监听地址: {self.host}:{self.port}")

            # 检查端口是否被占用
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind((self.host, self.port))
                sock.close()
                self.log("INFO", f"端口 {self.port} 可用")
            except OSError as e:
                if e.errno == 98:  # Address already in use
                    self.log("ERROR", f"端口 {self.port} 已被占用，请检查是否有其他服务在使用此端口")
                elif e.errno == 99:  # Cannot assign requested address
                    self.log("ERROR", f"无法绑定到地址 {self.host}，请检查IP地址配置")
                else:
                    self.log("ERROR", f"端口检查失败: {e}")
                raise

            # 创建兼容的处理函数，支持不同版本的websockets库
            async def handler(websocket, path=None):
                try:
                    # 记录连接信息
                    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
                    self.log("INFO", f"新连接尝试: {client_ip}, 路径: {path}")

                    # 尝试不同的参数组合
                    if path is not None:
                        await self.handle_client(websocket, path)
                    else:
                        # 对于新版本的websockets库，可能只传递websocket参数
                        await self.handle_client(websocket)
                except websockets.exceptions.InvalidMessage as e:
                    # WebSocket握手失败
                    self.log("WARNING", f"WebSocket握手失败: {e}")
                    self.log("INFO", "这通常是因为客户端发送了HTTP请求而不是WebSocket请求")
                    try:
                        await websocket.close(code=1002, reason="Invalid WebSocket request")
                    except:
                        pass
                except websockets.exceptions.ConnectionClosed as e:
                    # 连接已关闭
                    self.log("INFO", f"连接已关闭: {e}")
                except TypeError as e:
                    # 如果参数不匹配，尝试其他方式
                    self.log("WARNING", f"处理函数参数不匹配，尝试兼容模式: {e}")
                    try:
                        await self.handle_client(websocket, '/')
                    except Exception as e2:
                        self.log("ERROR", f"兼容模式也失败: {e2}")
                        try:
                            await websocket.close()
                        except:
                            pass
                except Exception as e:
                    # 其他异常
                    self.log("ERROR", f"处理连接时发生异常: {e}")
                    try:
                        await websocket.close()
                    except:
                        pass

            # 启动WebSocket服务器，添加额外的错误处理
            server = await websockets.serve(
                handler,
                self.host,
                self.port,
                ping_interval=60,  # 增加心跳间隔到60秒
                ping_timeout=10,  # 减少心跳超时时间
                max_size=1024 * 1024,  # 1MB max message size
                compression=None,
                close_timeout=10  # 关闭超时时间
            )

            self.is_running = True
            self.ws_ready.set()
            self.log("SUCCESS", f"WebSocket服务器启动成功！")
            self.log("SUCCESS", f"服务器地址: ws://{self.host}:{self.port}")
            self.log("SUCCESS", f"前端可通过此地址连接获取ASR结果")

            # 保持服务器运行
            await asyncio.Future()

        except Exception as e:
            self.log("ERROR", f"WebSocket服务器启动失败: {e}")
            self.log("ERROR", f"错误类型: {type(e).__name__}")
            if "Address already in use" in str(e):
                self.log("ERROR", "解决方案: 请检查端口是否被其他程序占用，或更换端口号")
            elif "Cannot assign requested address" in str(e):
                self.log("ERROR", "解决方案: 请检查IP地址配置，确保使用正确的服务器IP")
            raise

    def start_server(self):
        """启动WebSocket服务器（在单独线程中）"""
        if self.is_running:
            self.log("WARNING", "WebSocket服务器已在运行")
            return True

        try:
            self.log("INFO", "正在创建WebSocket服务器线程...")
            self.server_thread = threading.Thread(
                target=self._run_server_thread,
                daemon=True,
                name="WebSocketServer"
            )
            self.server_thread.start()

            # 等待服务器启动完成
            if self.ws_ready.wait(timeout=10):
                self.log("SUCCESS", "WebSocket服务器线程启动成功")
                return True
            else:
                self.log("ERROR", "WebSocket服务器启动超时")
                return False

        except Exception as e:
            self.log("ERROR", f"启动WebSocket服务器失败: {e}")
            return False

    def _run_server_thread(self):
        """在单独线程中运行WebSocket服务器"""
        try:
            self.ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.ws_loop)
            self.ws_loop.run_until_complete(self.start_server_async())
        except Exception as e:
            self.log("ERROR", f"WebSocket服务器线程异常: {e}")
        finally:
            try:
                if self.ws_loop:
                    self.ws_loop.close()
            except Exception:
                pass

    async def broadcast_message(self, message_data):
        """异步广播消息给所有连接的客户端"""
        if not self.clients:
            self.log("WARNING", "没有连接的客户端，无法推送消息")
            return 0

        if not isinstance(message_data, dict):
            message_data = {"content": str(message_data), "timestamp": time.time()}

        # 添加消息类型和元数据
        if "type" not in message_data:
            message_data["type"] = "asr_result"
        if "timestamp" not in message_data:
            message_data["timestamp"] = time.time()

        message_json = json.dumps(message_data, ensure_ascii=False)
        dead_clients = []
        success_count = 0

        self.log("INFO", f"开始向 {len(self.clients)} 个客户端推送消息")

        for websocket in self.clients:
            try:
                await websocket.send(message_json)
                success_count += 1
                self.log("DEBUG", f"消息推送成功到客户端")
            except Exception as e:
                self.log("WARNING", f"向客户端推送消息失败: {e}")
                dead_clients.append(websocket)

        # 清理断开的连接
        for ws in dead_clients:
            try:
                self.clients.remove(ws)
                self.log("INFO", f"已清理断开连接的客户端，当前连接数: {len(self.clients)}")
            except Exception:
                pass

        self.total_messages_sent += success_count
        self.log("SUCCESS",
                 f"消息推送完成，成功推送 {success_count} 个客户端，总计推送 {self.total_messages_sent} 条消息")
        return success_count

    def broadcast_message_sync(self, message_data):
        """同步广播消息给所有连接的客户端（线程安全）"""
        if not self.ws_loop or not self.is_running:
            self.log("WARNING", "WebSocket服务器未运行，无法推送消息")
            return 0

        try:
            # 使用线程安全的方式提交协程到事件循环
            future = asyncio.run_coroutine_threadsafe(
                self.broadcast_message(message_data),
                self.ws_loop
            )
            return future.result(timeout=5)  # 5秒超时
        except Exception as e:
            self.log("ERROR", f"同步推送消息失败: {e}")
            return 0

    def get_status(self):
        """获取服务器状态"""
        return {
            "is_running": self.is_running,
            "host": self.host,
            "port": self.port,
            "client_count": len(self.clients),
            "total_messages_sent": self.total_messages_sent,
            "connection_count": self.connection_count
        }

    def stop_server(self):
        """停止WebSocket服务器"""
        if not self.is_running:
            self.log("WARNING", "WebSocket服务器未运行")
            return

        self.log("INFO", "正在停止WebSocket服务器...")
        self.is_running = False

        if self.ws_loop:
            try:
                # 关闭所有客户端连接
                for websocket in list(self.clients):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            websocket.close(),
                            self.ws_loop
                        )
                    except Exception:
                        pass

                # 停止事件循环
                asyncio.run_coroutine_threadsafe(
                    self._stop_loop(),
                    self.ws_loop
                )
            except Exception as e:
                self.log("ERROR", f"停止WebSocket服务器时出错: {e}")

        self.log("SUCCESS", "WebSocket服务器已停止")

    async def _stop_loop(self):
        """停止事件循环"""
        if self.ws_loop and self.ws_loop.is_running():
            self.ws_loop.stop()

    def process_request(self, path, request_headers):
        """处理非WebSocket请求（如HTTP请求）"""
        try:
            # 兼容不同版本的websockets库
            connection_header = ""

            # 尝试不同的方式获取connection头
            if hasattr(request_headers, 'headers'):
                # 新版本websockets库
                connection_header = request_headers.headers.get("connection", "")
            elif hasattr(request_headers, 'get'):
                # 旧版本websockets库，request_headers是字典
                connection_header = request_headers.get("connection", "")
            elif isinstance(request_headers, dict):
                # 直接是字典
                connection_header = request_headers.get("connection", "")
            else:
                # 其他情况，尝试获取属性
                connection_header = getattr(request_headers, "connection", "")

            # 检查是否是WebSocket升级请求
            if "upgrade" in connection_header.lower():
                return None  # 让WebSocket处理

            # 返回HTTP响应给非WebSocket请求
            return (200, {"Content-Type": "text/html; charset=utf-8"}, self.get_info_page())

        except Exception as e:
            self.log("ERROR", f"处理HTTP请求时出错: {e}")
            self.log("DEBUG", f"request_headers类型: {type(request_headers)}")
            self.log("DEBUG", f"request_headers内容: {request_headers}")

            # 返回简单的错误响应
            return (400, {"Content-Type": "text/plain"}, b"Bad Request")

    def get_info_page(self):
        """获取信息页面HTML"""
        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASR实时转写系统</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; text-align: center; }}
        .info {{ background: #e7f3ff; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .warning {{ background: #fff3cd; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .code {{ background: #f8f9fa; padding: 15px; border-radius: 5px; font-family: monospace; margin: 10px 0; }}
        .status {{ text-align: center; margin: 20px 0; }}
        .connected {{ color: #28a745; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎤 ASR实时转写系统</h1>

        <div class="status">
            <p class="connected">✅ WebSocket服务器运行正常</p>
            <p>服务器地址: <strong>ws://{self.host}:{self.port}</strong></p>
            <p>当前连接数: <strong>{len(self.clients)}</strong></p>
        </div>

        <div class="info">
            <h3>📋 系统信息</h3>
            <p><strong>WebSocket地址:</strong> ws://{self.host}:{self.port}</p>
            <p><strong>服务器状态:</strong> 运行中</p>
            <p><strong>已推送消息:</strong> {self.total_messages_sent} 条</p>
            <p><strong>总连接数:</strong> {self.connection_count}</p>
        </div>

        <div class="warning">
            <h3>⚠️ 重要提示</h3>
            <p>这是一个WebSocket服务器，不能通过浏览器直接访问。</p>
            <p>请使用WebSocket客户端连接到此地址获取ASR转写结果。</p>
        </div>

        <div class="info">
            <h3>🔗 连接方式</h3>
            <p><strong>Python客户端:</strong></p>
            <div class="code">
import asyncio<br>
import websockets<br>
<br>
async def connect():<br>
&nbsp;&nbsp;&nbsp;&nbsp;uri = "ws://{self.host}:{self.port}"<br>
&nbsp;&nbsp;&nbsp;&nbsp;async with websockets.connect(uri) as websocket:<br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;message = await websocket.recv()<br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;print(message)<br>
<br>
asyncio.run(connect())
            </div>

            <p><strong>JavaScript客户端:</strong></p>
            <div class="code">
const ws = new WebSocket('ws://{self.host}:{self.port}');<br>
ws.onmessage = function(event) {{<br>
&nbsp;&nbsp;&nbsp;&nbsp;console.log(event.data);<br>
}};
            </div>
        </div>

        <div class="info">
            <h3>📚 使用文档</h3>
            <p>• <strong>上游用户:</strong> 请参考 UPSTREAM_USER_MANUAL.md</p>
            <p>• <strong>下游用户:</strong> 请参考 DOWNSTREAM_USER_MANUAL.md</p>
            <p>• <strong>部署指南:</strong> 请参考 DEPLOYMENT_GUIDE.md</p>
        </div>

        <div class="status">
            <p><em>最后更新: {time.strftime('%Y-%m-%d %H:%M:%S')}</em></p>
        </div>
    </div>
</body>
</html>
        """.encode('utf-8')


# 全局WebSocket服务器实例
ws_server_manager = WebSocketServerManager(host="0.0.0.0", port=9000)


# ------------ 音频流队列管理类 ------------
class TimestampAudioQueue:
    """基于时间戳的音频流队列管理器 - 支持多音频流处理"""

    # 文件类型分类字典
    FILE_TYPE_MAP = {
        'audio': ['.wav', '.mp3', '.pcm', '.raw'],
        'end_msg': ['.json'],
        'config': ['.cfg', '.conf'],
        'log': ['.log', '.txt']
    }

    def __init__(self, input_dir, output_dir, timeout_seconds=30):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.timeout_seconds = timeout_seconds  # 超时时间（秒）
        self.processed_files = set()  # 已处理的文件集合
        self.current_stream_id = None  # 当前流ID
        self.buffer_start_time = None  # 缓冲区开始时间
        self.has_processed_audio = False  # 是否已处理过音频文件
        self.last_audio_time = None  # 最后处理音频的时间
        self.connection_lost_time = None  # 连接断开时间
        self.is_waiting_for_timeout = False  # 是否在等待超时

    def _extract_timestamp(self, filename):
        """从文件名中提取时间戳"""
        try:
            # 支持格式: timestamp_audio.wav, timestamp_end_msg.json
            parts = filename.split('_')
            if len(parts) >= 2:
                timestamp_str = parts[0]
                # 尝试解析为整数时间戳
                return int(timestamp_str)
            return None
        except (ValueError, IndexError):
            return None

    def _get_file_type(self, filename):
        """根据文件扩展名确定文件类型"""
        _, ext = os.path.splitext(filename.lower())
        for file_type, extensions in self.FILE_TYPE_MAP.items():
            if ext in extensions:
                return file_type
        return 'unknown'

    def _is_end_message(self, filename):
        """判断是否为结束消息文件"""
        file_type = self._get_file_type(filename)
        return file_type == 'end_msg' and 'end' in filename.lower()

    def scan_and_sort_files(self):
        """扫描目录并按时间戳排序文件"""
        if not os.path.exists(self.input_dir):
            return []

        files = []
        for filename in os.listdir(self.input_dir):
            if filename in self.processed_files:
                continue  # 跳过已处理的文件

            filepath = os.path.join(self.input_dir, filename)
            if not os.path.isfile(filepath):
                continue

            timestamp = self._extract_timestamp(filename)
            if timestamp is None:
                print(f"【警告】无法解析时间戳: {filename}")
                continue

            file_type = self._get_file_type(filename)
            files.append({
                'filename': filename,
                'filepath': filepath,
                'timestamp': timestamp,
                'type': file_type,
                'is_end': self._is_end_message(filename)
            })

        # 按时间戳排序
        files.sort(key=lambda x: x['timestamp'])
        return files

    def get_next_file_to_process(self):
        """获取下一个要处理的文件（按时间戳顺序）"""
        files = self.scan_and_sort_files()
        if not files:
            return None

        # 返回第一个未处理的文件
        return files[0]

    def mark_file_processed_and_delete(self, file_info):
        """标记文件为已处理并立即删除"""
        if not file_info:
            return False

        filename = file_info['filename']
        filepath = file_info['filepath']

        try:
            # 立即删除文件
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"【删除】已删除处理完的文件: {filename}")

            # 标记为已处理
            self.processed_files.add(filename)
            return True
        except Exception as e:
            print(f"【删除失败】{filename}: {str(e)}")
            return False

    def check_timeout(self):
        """检查是否超时（基于最后处理音频的时间）"""
        # 如果缓冲区为空，不需要超时检查
        if not self.has_processed_audio:
            return False

        # 检查是否有待处理的文件（包括end_msg.json）
        files = self.scan_and_sort_files()
        if files:
            # 如果有end_msg.json文件，绝对不触发超时
            for file_info in files:
                if file_info['is_end']:
                    print("【超时检查】检测到结束消息文件，跳过超时检查，等待处理结束消息")
                    return False

            # 如果有其他文件，重置计时
            print("【超时检查】检测到待处理文件，重置超时计时")
            self.last_audio_time = time.time()
            self.is_waiting_for_timeout = False
            return False

        # input_chunks为空且缓冲区非空，检查是否超时
        if self.last_audio_time is None:
            print("【超时检查】开始超时计时")
            self.last_audio_time = time.time()
            self.is_waiting_for_timeout = True
            return False

        # 如果已经超时过，不再检查
        if self.last_audio_time == -1:
            return False

        # 检查是否超时
        elapsed = time.time() - self.last_audio_time
        if elapsed >= self.timeout_seconds:
            print(f"【超时检查】超时触发！已等待 {elapsed:.1f} 秒，超过限制 {self.timeout_seconds} 秒")
            self.is_waiting_for_timeout = False
            # 设置为特殊值，避免重复超时
            self.last_audio_time = -1  # 使用-1表示已经超时过
            return True

        # 标记为等待超时状态
        if not self.is_waiting_for_timeout:
            self.is_waiting_for_timeout = True
            print(f"【超时检查】开始等待超时，等待 {self.timeout_seconds} 秒，当前已等待 {elapsed:.1f} 秒")

        return False

    def has_connection_issue(self):
        """检查是否有连接问题"""
        return self.has_processed_audio and self.buffer_start_time is not None

    def reset_buffer_state(self):
        """重置缓冲区状态"""
        self.buffer_start_time = None
        self.has_processed_audio = False
        self.current_stream_id = None
        self.last_audio_time = None
        self.connection_lost_time = None
        self.is_waiting_for_timeout = False
        print("【缓冲区状态重置】回到初始状态，等待新的音频流")

    def mark_audio_processed(self):
        """标记已处理音频文件"""
        self.has_processed_audio = True
        self.last_audio_time = time.time()
        self.is_waiting_for_timeout = False
        if self.buffer_start_time is None:
            self.buffer_start_time = time.time()

    def get_current_stream_id(self):
        """获取当前流ID"""
        if self.current_stream_id is None:
            self.current_stream_id = f"stream_{int(time.time())}"
        return self.current_stream_id


# ------------ API集成类 ------------
class AudioStreamProcessor:
    """音频流处理器API集成类 - 支持多音频流处理和自动重连"""

    def __init__(self, app_id, access_key_id, access_key_secret, input_dir, output_dir, timeout_seconds=30):
        self.app_id = app_id
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.audio_queue = TimestampAudioQueue(input_dir, output_dir, timeout_seconds)
        self.ws_server_manager = ws_server_manager  # WebSocket服务器管理器
        self.current_client = None  # 当前ASR客户端
        self.is_processing = False  # 是否正在处理
        self.reconnect_attempts = 0  # 重连尝试次数
        self.max_reconnect_attempts = 3  # 最大重连次数
        self.is_reconnecting = False  # 是否正在重连
        self.connection_lost_time = None  # 连接断开时间
        self.should_reconnect = True  # 是否应该重连
        self.force_output_attempted = False  # 是否已尝试强制输出

    def set_websocket_loop(self, ws_loop):
        """设置WebSocket事件循环（用于结果广播）"""
        self.ws_loop = ws_loop

    def start_asr_connection(self):
        """启动ASR连接"""
        print("【连接检查】检查ASR连接状态...")
        if self.current_client is None or not self.current_client.is_connected:
            print("【连接检查】需要建立新连接")
            self.current_client = RTASRClient(self.app_id, self.access_key_id, self.access_key_secret, audio_path=None)
            if not self.current_client.connect():
                print("【ASR连接失败】无法建立连接")
                self.current_client = None
                return False
            self.current_client.reset_result_buffer()
            print("【ASR连接成功】连接已建立")
            # 重置重连计数
            self.reconnect_attempts = 0
            self.is_reconnecting = False
            self.connection_lost_time = None
        else:
            print("【连接检查】连接状态正常")
        return True

    def attempt_reconnection(self):
        """尝试重新连接"""
        if self.is_reconnecting:
            print("【重连检查】正在重连中，跳过重复请求")
            return False

        self.is_reconnecting = True
        self.reconnect_attempts += 1

        print(f"【重连开始】第 {self.reconnect_attempts}/{self.max_reconnect_attempts} 次尝试重新连接...")

        try:
            # 关闭旧连接
            if self.current_client:
                print("【重连准备】关闭旧连接")
                self.current_client.close()
                self.current_client = None

            # 尝试新连接
            print("【重连执行】建立新连接")
            if self.start_asr_connection():
                print(f"【重连成功】第 {self.reconnect_attempts} 次重连成功，连接已恢复")
                return True
            else:
                print(f"【重连失败】第 {self.reconnect_attempts} 次重连失败，连接未建立")
                return False

        except Exception as e:
            print(f"【重连异常】第 {self.reconnect_attempts} 次重连异常: {str(e)}")
            return False
        finally:
            self.is_reconnecting = False
            print(f"【重连完成】第 {self.reconnect_attempts} 次重连尝试结束")

    def should_attempt_reconnection(self):
        """判断是否应该尝试重连"""
        # 如果重连次数未达到上限，且不在重连中
        return (self.reconnect_attempts < self.max_reconnect_attempts and
                not self.is_reconnecting and
                self.audio_queue.has_processed_audio)  # 只有处理过音频才重连

    def process_audio_file(self, file_info):
        """处理单个音频文件"""
        if not self.start_asr_connection():
            return False

        filename = file_info['filename']
        filepath = file_info['filepath']

        if os.path.getsize(filepath) == 0:
            print(f"【跳过】空音频文件：{filename}")
            return True

        self.current_client.audio_path = filepath
        success = self.current_client._send_chunk_file_without_end()
        if success:
            print(f"【发送成功】音频文件: {filename}")
            self.audio_queue.mark_audio_processed()  # 标记已处理音频
            # 重置重连状态
            self.reconnect_attempts = 0
            self.should_reconnect = True
            # 重置强制输出标志，允许新的超时处理
            self.force_output_attempted = False
        else:
            print(f"【发送失败】音频文件: {filename}")
            # 发送失败时，检查连接状态
            if not self.current_client.is_connected:
                print("【连接已断开】记录断开时间")
                self.connection_lost_time = time.time()
                return False

        return success

    def process_end_message(self, file_info):
        """处理结束消息文件"""
        filename = file_info['filename']
        filepath = file_info['filepath']

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                msg = json.load(f)
            if msg.get('end') is True:
                print("【检测到结束消息】准备输出缓冲区")
                return True
            else:
                print("【警告】结束消息文件未包含 end=true")
                return False
        except Exception as e:
            print(f"【结束消息解析失败】{str(e)}")
            return False

    def handle_connection_lost(self):
        """处理连接断开情况"""
        # 连接断开后，不立即重连，而是等待超时
        print("【连接断开】等待超时后再决定是否重连（讯飞API正常超时行为）")
        self.should_reconnect = False
        return False

    def output_buffer_and_reset(self, reason="manual", keep_connection=False):
        """输出缓冲区并重置状态"""
        print(f"【缓冲区输出】开始处理，原因: {reason}, 保持连接: {keep_connection}")

        if not self.current_client:
            print("【缓冲区输出失败】没有活跃的ASR客户端")
            return False

        try:
            # 检查连接状态
            if not self.current_client.is_connected:
                print(f"【缓冲区输出】连接已断开，直接导出缓冲区内容")
                return self._force_export_buffer(reason)

            # 向服务端发送结束标记
            end_msg = {"end": True}
            if self.current_client.session_id:
                end_msg["sessionId"] = self.current_client.session_id

            try:
                self.current_client.ws.send(json.dumps(end_msg, ensure_ascii=False))
                print(f"【缓冲区输出】已通知服务端结束当前流")
            except Exception as e:
                print(f"【缓冲区输出】发送结束标记失败: {str(e)}，直接导出缓冲区")
                return self._force_export_buffer(reason)

            # 等待尾部结果到达
            print("【缓冲区输出】等待尾部结果到达...")
            tail_wait_start = time.time()
            self.current_client.last_result_time = time.time()
            while True:
                now = time.time()
                if now - self.current_client.last_result_time > 1.0:
                    print("【缓冲区输出】尾部结果等待完成")
                    break
                if now - tail_wait_start > 10.0:
                    print("【缓冲区输出】等待尾部结果超时，继续导出")
                    break
                time.sleep(0.1)

            # 导出结果
            print("【缓冲区输出】开始导出结果")
            success = self._export_results(reason)

            # 根据参数决定是否保持连接
            if not keep_connection:
                print("【缓冲区输出】关闭连接，准备下一批")
                # 关闭连接，准备下一批
                if self.current_client:
                    self.current_client.close()
                    self.current_client = None
                # 重置所有状态，回到初始状态
                self.audio_queue.reset_buffer_state()
                self.force_output_attempted = False
                self.reconnect_attempts = 0
                self.is_reconnecting = False
                self.should_reconnect = True
                print("【缓冲区输出】连接已关闭，系统回归初始状态，准备建立新连接")
            else:
                print("【缓冲区输出】保持连接，重置缓冲区状态")
                # 保持连接，重置缓冲区状态但保持连接
                self.audio_queue.reset_buffer_state()
                # 重置强制输出标志，允许下次超时处理
                self.force_output_attempted = False
                print("【缓冲区输出】连接保持，继续等待下一个音频流")

            print(f"【缓冲区输出】处理完成，结果: {'成功' if success else '失败'}")
            return success

        except Exception as e:
            print(f"【缓冲区输出失败】{str(e)}，尝试强制导出")
            return self._force_export_buffer(reason)

    def _force_export_buffer(self, reason):
        """强制导出缓冲区内容（连接断开时使用）"""
        try:
            print(f"【强制导出】{reason} - 连接断开，直接导出已缓存的结果")

            # 检查是否有可导出的结果
            if not self.current_client or not hasattr(self.current_client, 'result_messages'):
                print("【强制导出】没有ASR客户端或结果缓存")
                return False

            if not self.current_client.result_messages:
                print("【强制导出】没有可导出的结果")
                return False

            # 导出结果
            return self._export_results(reason, force=True)

        except Exception as e:
            print(f"【强制导出失败】{str(e)}")
            return False

    def _export_results(self, reason, force=False):
        """导出识别结果"""
        try:
            ts = time.strftime('%Y%m%d-%H%M%S')
            stream_id = self.audio_queue.get_current_stream_id()

            # 添加后缀标注方便识别
            suffix = "_FORCED" if force else ""
            output_txt = os.path.join(self.audio_queue.output_dir, f"{stream_id}_{reason}{suffix}_{ts}.txt")

            if force:
                # 强制导出模式：直接导出已缓存的结果
                if hasattr(self.current_client, 'result_messages') and self.current_client.result_messages:
                    with open(output_txt, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(self.current_client.result_messages))
                    print(f"【强制导出完成】结果保存至: {output_txt}")
                else:
                    print("【强制导出】没有可导出的结果")
                    return False
            else:
                # 正常导出模式
                self.current_client.export_results_to_txt(output_txt)

            # 通过WebSocket广播识别结果
            try:
                with open(output_txt, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 构建推送消息
                push_message = {
                    "type": "asr_result",
                    "content": content,
                    "filename": os.path.basename(output_txt),
                    "reason": reason,
                    "force": force,
                    "timestamp": time.time(),
                    "stream_id": stream_id
                }

                # 通过WebSocket服务器管理器推送消息
                success_count = self.ws_server_manager.broadcast_message_sync(push_message)
                if success_count > 0:
                    print(f"【WebSocket推送】已向 {success_count} 个客户端推送识别结果")
                else:
                    print("【WebSocket推送】没有连接的客户端，结果已保存到文件")

            except Exception as e:
                print(f"【WebSocket推送失败】{e}")
                print("【WebSocket推送】结果已保存到文件，但推送失败")

            # 注意：不在这里重置缓冲区状态，由调用者决定
            print(f"【缓冲区输出完成】结果保存至: {output_txt}")
            return True

        except Exception as e:
            print(f"【导出结果失败】{str(e)}")
            return False

    def run_multi_stream_processing(self):
        """运行多音频流处理模式（主循环）"""
        try:
            print("【启动多音频流处理模式】")
            self.is_processing = True

            while True:
                # 获取下一个要处理的文件
                file_info = self.audio_queue.get_next_file_to_process()

                # 优先级1：如果有文件，优先处理文件（end_msg.json优先级最高）
                if file_info is not None:
                    filename = file_info['filename']
                    file_type = file_info['type']
                    is_end = file_info['is_end']

                    print(f"【处理文件】{filename} (类型: {file_type}, 时间戳: {file_info['timestamp']})")

                    if is_end:
                        # 处理结束消息文件 - 最高优先级
                        print("【检测到结束消息】立即处理，优先级最高")
                        if self.process_end_message(file_info):
                            # 删除结束消息文件
                            self.audio_queue.mark_file_processed_and_delete(file_info)
                            # 输出缓冲区，结束消息时关闭连接
                            success = self.output_buffer_and_reset("end_message", keep_connection=False)
                            if not success:
                                print("【结束消息输出失败】重置状态")
                                self.audio_queue.reset_buffer_state()
                            print("【结束消息处理完成】系统回归初始状态，等待下一个音频流")
                        else:
                            # 删除无效的结束消息文件
                            self.audio_queue.mark_file_processed_and_delete(file_info)

                    elif file_type == 'audio':
                        # 处理音频文件
                        success = self.process_audio_file(file_info)
                        # 立即删除已处理的音频文件
                        self.audio_queue.mark_file_processed_and_delete(file_info)

                        # 如果处理失败，处理连接断开情况
                        if not success:
                            if self.current_client and not self.current_client.is_connected:
                                print("【连接断开】等待超时后再决定是否重连")
                                self.handle_connection_lost()
                            else:
                                print("【处理失败】跳过此文件")

                    else:
                        # 跳过非音频文件
                        print(f"【跳过】非音频文件: {filename} (类型: {file_type})")
                        self.audio_queue.mark_file_processed_and_delete(file_info)

                    # 短暂休眠，避免CPU占用过高
                    time.sleep(0.1)
                    continue

                # 优先级2：没有文件时，检查超时和连接状态
                if self.audio_queue.check_timeout():
                    print("【主循环】检测到超时，开始强制输出缓冲区")
                    if not self.force_output_attempted:
                        self.force_output_attempted = True
                        print("【主循环】执行超时强制输出")
                        # 超时时保持连接，继续等待下一个音频流
                        success = self.output_buffer_and_reset("timeout", keep_connection=True)
                        if not success:
                            print("【主循环】超时输出失败，重置状态，继续等待")
                            self.audio_queue.reset_buffer_state()
                        # 重置标志，允许下次超时处理
                        self.force_output_attempted = False
                        print("【主循环】超时处理完成，系统回归初始状态，等待下一个音频流")
                    else:
                        print("【主循环】超时输出已尝试，继续等待")
                elif self.audio_queue.has_processed_audio and not self.current_client and self.should_reconnect:
                    # 有缓冲区但没有连接，且允许重连
                    print("【主循环】检测到连接断开，开始重连处理")
                    if self.should_attempt_reconnection():
                        print("【主循环】尝试重新连接...")
                        if self.attempt_reconnection():
                            print("【主循环】重连成功，继续等待新文件")
                            self.should_reconnect = True
                        else:
                            print("【主循环】重连失败，继续等待...")
                    else:
                        print("【主循环】重连次数已达上限，强制输出缓冲区")
                        if not self.force_output_attempted:
                            self.force_output_attempted = True
                            print("【主循环】执行重连失败强制输出")
                            # 重连失败时保持连接，继续等待
                            success = self.output_buffer_and_reset("reconnect_failed", keep_connection=True)
                            if not success:
                                self.audio_queue.reset_buffer_state()
                            # 重置标志，允许下次超时处理
                            self.force_output_attempted = False
                            print("【主循环】重连失败处理完成，系统回归初始状态，等待下一个音频流")
                else:
                    # 缓冲区为空时，不打印大量日志
                    if not self.audio_queue.has_processed_audio:
                        time.sleep(1)  # 短暂等待
                    else:
                        time.sleep(0.5)  # 有缓冲区时更频繁检查

        except KeyboardInterrupt:
            print("【程序退出】用户手动中断")
        except Exception as e:
            print(f"【致命异常】{str(e)}")
        finally:
            self.stop_processing()

    def stop_processing(self):
        """停止处理模式"""
        print("【停止处理模式】")
        self.is_processing = False

        if self.current_client:
            self.current_client.close()
            self.current_client = None

        # 重置缓冲区状态
        self.audio_queue.reset_buffer_state()

        # 重置重连状态
        self.reconnect_attempts = 0
        self.is_reconnecting = False
        self.connection_lost_time = None
        self.should_reconnect = True
        self.force_output_attempted = False


# ------------ 原后端代码 ------------
# 全局配置：与服务端确认的固定参数
FIXED_PARAMS = {
    "audio_encode": "pcm_s16le",
    "lang": "autodialect",
    "samplerate": "16000"  # 固定16k采样率，对应每40ms发送1280字节
}
AUDIO_FRAME_SIZE = 1280  # 每帧音频字节数（16k采样率、16bit位深、40ms）
FRAME_INTERVAL_MS = 40  # 每帧发送间隔（毫秒）


class RTASRClient():
    def __init__(self, app_id, access_key_id, access_key_secret, audio_path):
        self.app_id = app_id
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.audio_path = audio_path
        self.base_ws_url = "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1"
        self.ws = None
        self.is_connected = False
        self.recv_thread = None
        self.session_id = None
        self.is_sending_audio = False  # 防止并发发送
        self.audio_file_size = 0  # 音频文件大小（字节）
        self.result_messages = []  # 存储服务端返回消息（当前流）
        self.last_result_time = 0  # 最近一次收到服务端消息的时间戳（秒）

    def _extract_text_from_msg(self, msg_json):
        """从服务端返回的JSON消息中提取纯文本及是否为最终结果。"""
        try:
            if not isinstance(msg_json, dict):
                return "", None, False
            if msg_json.get('msg_type') != 'result':
                return "", None, False
            if msg_json.get('res_type') not in (None, 'asr', 'iat'):
                # 只处理ASR文本结果
                return "", None, False
            data = msg_json.get('data') or {}
            seg_id = data.get('seg_id')
            cn = (data.get('cn') or {})
            st = (cn.get('st') or {})
            is_final = False
            try:
                if data.get('ls') is True:
                    is_final = True
                tval = st.get('type')
                if isinstance(tval, str) and tval == '0':
                    is_final = True
                if isinstance(tval, int) and tval == 0:
                    is_final = True
            except Exception:
                pass
            rts = st.get('rt') or []
            words = []
            for rt in rts:
                ws_list = rt.get('ws') or []
                for ws in ws_list:
                    cws = ws.get('cw') or []
                    for cw in cws:
                        w = cw.get('w')
                        if isinstance(w, str):
                            words.append(w)
            return ''.join(words).strip(), seg_id, is_final
        except Exception:
            return "", None, False

    def reset_result_buffer(self):
        """重置当前流的结果缓存。"""
        self.result_messages = []

    def export_results_to_txt(self, output_txt_path):
        """将当前缓冲的识别结果导出为txt文件（简单拼接data里的文本字段）。"""
        try:
            lines = []
            for msg in self.result_messages:
                # 根据服务端协议提取文本
                if isinstance(msg, dict):
                    data = msg.get('data') or {}
                    # 常见结构：data.text 或 data.result 或 msg['text']
                    text = (
                            data.get('text')
                            or data.get('result')
                            or msg.get('text')
                            or ''
                    )
                    if isinstance(text, (list, tuple)):
                        text = ' '.join(str(x) for x in text)
                    lines.append(str(text))
                else:
                    lines.append(str(msg))
            content = '\n'.join([ln for ln in lines if ln])

            # 使用 LLM 进行轻润色（失败则回退原文）
            try:
                provider = os.getenv('LLM_PROVIDER', 'deepseek').lower()
                model = os.getenv('LLM_MODEL', 'deepseek-chat')
                api_key = os.getenv('LLM_API_KEY', '')
                base_url = os.getenv('LLM_BASE_URL', 'https://api.deepseek.com')
                polished = self._polish_text_with_llm(
                    content,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                )
                if isinstance(polished, str) and polished.strip():
                    content = polished.strip()
            except Exception:
                pass
            with open(output_txt_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"【结果导出】已写入：{output_txt_path}")
            return True
        except Exception as e:
            print(f"【结果导出失败】{str(e)}")
            return False

    def _polish_text_with_llm(self, text, provider='', model='', api_key='', base_url=''):
        """调用LLM对文本做轻度润色：删除口头禅、重复或无效字，不新增信息。"""
        if not isinstance(text, str) or not text.strip():
            return text

        provider = (provider or '').lower()

        def _fallback_clean(s):
            try:
                fillers = ['啊', '哦', '嗯', '呃', '噢', '额', '呃嗯', '嗯嗯']
                for f in fillers:
                    s = s.replace(f, '')
                import re
                s = re.sub(r'(.)\1{2,}', r'\1\1', s)
                s = re.sub(r'[ \t\u3000]+', ' ', s)
                s = re.sub(r'\n{3,}', '\n\n', s)
                return s.strip()
            except Exception:
                return s

        try:
            if provider in ('deepseek', 'qwen') or base_url or api_key:
                if not base_url:
                    if provider == 'deepseek':
                        base_url = 'https://api.deepseek.com'
                    elif provider == 'qwen':
                        base_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
                endpoint = base_url.rstrip('/') + '/chat/completions'
                if not model:
                    model = 'deepseek-chat' if provider == 'deepseek' else 'qwen2.5-7b-instruct'
                headers = {
                    'Authorization': f'Bearer {api_key}'.strip(),
                    'Content-Type': 'application/json',
                }
                system_prompt = (
                    '你是文本润色助手。请在不新增信息的前提下，去除口头禅/语气词/重复字符，'
                    '修正明显识别错误，保持语义不变，尽量保持简洁自然。只输出润色后的文本。'
                )
                payload = {
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text},
                    ],
                    'temperature': 0.2,
                }
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    choice = (data.get('choices') or [{}])[0]
                    message = (choice.get('message') or {})
                    content = message.get('content')
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                return _fallback_clean(text)
        except Exception:
            return _fallback_clean(text)
        return _fallback_clean(text)

    def _get_audio_file_size(self):
        """获取音频文件大小（新增方法，修复AttributeError）"""
        try:
            with open(self.audio_path, "rb") as f:
                f.seek(0, 2)  # 移动到文件末尾
                return f.tell()  # 返回文件大小
        except Exception as e:
            print(f"【获取文件大小失败】{str(e)}")
            return 0

    def _generate_auth_params(self):
        """生成鉴权参数（严格按字典序排序，匹配Java TreeMap）"""
        auth_params = {
            "accessKeyId": self.access_key_id,
            "appId": self.app_id,
            "uuid": uuid.uuid4().hex,
            "utc": self._get_utc_time(),
            **FIXED_PARAMS
        }
        sorted_params = dict(sorted([
            (k, v) for k, v in auth_params.items()
            if v is not None and str(v).strip() != ""
        ]))
        base_str = "&".join([
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted_params.items()
        ])
        signature = hmac.new(
            self.access_key_secret.encode("utf-8"),
            base_str.encode("utf-8"),
            hashlib.sha1
        ).digest()
        auth_params["signature"] = base64.b64encode(signature).decode("utf-8")
        return auth_params

    def _get_utc_time(self):
        """生成服务端要求的UTC时间格式：yyyy-MM-dd'T'HH:mm:ss+0800"""
        beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
        now = datetime.datetime.now(beijing_tz)
        return now.strftime("%Y-%m-%dT%H:%M:%S%z")

    def connect(self):
        """建立WebSocket连接（增加稳定性配置）"""
        try:
            auth_params = self._generate_auth_params()
            params_str = urllib.parse.urlencode(auth_params)
            full_ws_url = f"{self.base_ws_url}?{params_str}"
            print(f"【连接信息】完整URL：{full_ws_url}")
            self.ws = create_connection(
                full_ws_url,
                timeout=15,
                enable_multithread=True  # 支持多线程并发
            )
            self.is_connected = True
            print("【连接成功】WebSocket握手完成，等待服务端就绪...")
            time.sleep(1.5)  # 确保服务端完全初始化
            # 启动接收线程（单独处理服务端消息）
            self.recv_thread = threading.Thread(target=self._recv_msg, daemon=True)
            self.recv_thread.start()
            return True
        except WebSocketException as e:
            print(f"【连接失败】WebSocket错误：{str(e)}")
            if hasattr(e, 'status_code'):
                print(f"【服务端状态码】{e.status_code}")
            return False
        except Exception as e:
            print(f"【连接异常】其他错误：{str(e)}")
            return False

    def _recv_msg(self):
        """接收服务端消息（增加连接状态判断，修复非套接字操作错误）"""
        while True:
            if not self.is_connected or not self.ws:
                print("【接收线程】连接已关闭，退出接收循环")
                break
            try:
                msg = self.ws.recv()
                if not msg:
                    print("【接收消息】服务端关闭连接")
                    self.close()
                    break
                if isinstance(msg, str):
                    try:
                        msg_json = json.loads(msg)
                        print(f"【接收消息】{msg_json}")
                        text, seg_id, is_final = self._extract_text_from_msg(msg_json)
                        if is_final and text:
                            self.result_messages.append(text)
                        self.last_result_time = time.time()
                        if (msg_json.get('msg_type') == 'action'
                                and 'sessionId' in msg_json.get('data', {})):
                            self.session_id = msg_json['data']['sessionId']
                    except json.JSONDecodeError:
                        print(f"【接收异常】非JSON文本消息：{msg[:50]}...")
                else:
                    print(f"【接收提示】收到二进制消息（长度：{len(msg)}字节），忽略")
            except WebSocketException as e:
                # 区分不同类型的连接异常
                error_msg = str(e)
                if "The read operation timed out" in error_msg:
                    print(f"【连接超时】讯飞API主动断开连接（正常行为）")
                elif "Connection to remote host was lost" in error_msg:
                    print(f"【连接丢失】网络连接中断")
                else:
                    print(f"【接收异常】连接中断：{error_msg}")
                self.close()
                break
            except OSError as e:
                print(f"【接收异常】系统套接字错误：{str(e)}")
                self.close()
                break
            except Exception as e:
                print(f"【接收异常】未知错误：{str(e)}")
                self.close()
                break

    def send_audio(self):
        """
        精确控制音频发送节奏：
        1. 16k采样率每40ms发送1280字节
        2. 基于起始时间计算理论发送时间，抵消累计误差
        """
        if not self.is_connected or not self.ws:
            print("【发送失败】WebSocket未连接")
            return False
        if self.is_sending_audio:
            print("【发送失败】已有发送任务在执行")
            return False

        self.is_sending_audio = True
        frame_index = 0
        start_time = None
        self.audio_file_size = self._get_audio_file_size()

        try:
            with open(self.audio_path, "rb") as f:
                total_frames = self.audio_file_size // AUDIO_FRAME_SIZE
                remaining_bytes = self.audio_file_size % AUDIO_FRAME_SIZE
                if remaining_bytes > 0:
                    total_frames += 1
                estimated_duration = (total_frames * FRAME_INTERVAL_MS) / 1000
                print(
                    f"【发送配置】音频文件大小：{self.audio_file_size}字节 | 总帧数：{total_frames} | 预估时长：{estimated_duration:.1f}秒")
                print(f"【发送配置】每{FRAME_INTERVAL_MS}ms发送{FRAME_INTERVAL_MS}字节，严格控制节奏")
                f.seek(0)
                while True:
                    chunk = f.read(AUDIO_FRAME_SIZE)
                    if not chunk:
                        print(f"【发送完成】所有音频帧发送完毕（共{frame_index}帧）")
                        break
                    if start_time is None:
                        start_time = time.time() * 1000
                        print(f"【发送开始】起始时间：{start_time:.0f}ms（基准时间）")
                    expected_send_time = start_time + (frame_index * FRAME_INTERVAL_MS)
                    current_time = time.time() * 1000
                    time_diff = expected_send_time - current_time
                    if time_diff > 0.1:
                        time.sleep(time_diff / 1000)
                        if frame_index % 10 == 0:
                            actual_send_time = time.time() * 1000
                            print(
                                f"【节奏控制】帧{frame_index} | 理论时间：{expected_send_time:.0f}ms | 实际时间：{actual_send_time:.0f}ms | 误差：{actual_send_time - expected_send_time:.1f}ms")
                    self.ws.send_binary(chunk)
                    frame_index += 1
                end_msg = {"end": True}
                if self.session_id:
                    end_msg["sessionId"] = self.session_id
                end_msg_str = json.dumps(end_msg, ensure_ascii=False)
                self.ws.send(end_msg_str)
                print(f"【发送结束】已发送标准JSON结束标记：{end_msg_str}")
            return True
        except FileNotFoundError:
            print(f"【发送失败】音频文件不存在：{self.audio_path}")
            return False
        except PermissionError:
            print(f"【发送失败】无权限读取音频文件：{self.audio_path}")
            return False
        except WebSocketException as e:
            print(f"【发送失败】WebSocket连接中断：{str(e)}")
            self.close()
            return False
        except Exception as e:
            print(f"【发送异常】未知错误：{str(e)}")
            self.close()
            return False
        finally:
            self.is_sending_audio = False

    def _send_chunk_file_without_end(self):
        """发送单个分片文件（严格40ms一帧），不发送结束标记。"""
        if not self.is_connected or not self.ws:
            print("【发送失败】WebSocket未连接")
            return False
        if self.is_sending_audio:
            print("【发送失败】已有发送任务在执行")
            return False

        if not self.audio_path:
            print("【发送失败】未设置音频分片路径")
            return False

        self.is_sending_audio = True
        frame_index = 0
        start_time = None
        try:
            size_bytes = os.path.getsize(self.audio_path)
            with open(self.audio_path, 'rb') as f:
                while True:
                    chunk = f.read(AUDIO_FRAME_SIZE)
                    if not chunk:
                        break
                    if start_time is None:
                        start_time = time.time() * 1000
                    expected_send_time = start_time + (frame_index * FRAME_INTERVAL_MS)
                    current_time = time.time() * 1000
                    time_diff = expected_send_time - current_time
                    if time_diff > 0.1:
                        time.sleep(time_diff / 1000)
                    self.ws.send_binary(chunk)
                    frame_index += 1
            print(f"【分片发送完成】文件={os.path.basename(self.audio_path)}，帧数={frame_index}，大小={size_bytes}字节")
            return True
        except Exception as e:
            print(f"【分片发送异常】{str(e)}")
            return False
        finally:
            self.is_sending_audio = False

    def close(self):
        """安全关闭WebSocket连接（增加状态保护）"""
        if self.is_connected and self.ws:
            self.is_connected = False
            try:
                if self.ws.connected:
                    self.ws.close(status=1000, reason="客户端正常关闭")
                print("【连接关闭】WebSocket已安全关闭")
            except Exception as e:
                print(f"【关闭异常】关闭时出错：{str(e)}")
        else:
            print("【连接关闭】WebSocket已断开或未初始化")


if __name__ == "__main__":
    # 配置日志（过滤冗余信息）
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("websocket").setLevel(logging.WARNING)

    print("=" * 80)
    print("ASR实时转写系统 - 后端服务器")
    print("=" * 80)

    # 1. 启动WebSocket服务器（用于前端连接）
    print("\n【系统启动】正在启动WebSocket服务器...")
    if ws_server_manager.start_server():
        print("【系统启动】WebSocket服务器启动成功")
        status = ws_server_manager.get_status()
        print(f"【系统启动】服务器地址: ws://{status['host']}:{status['port']}")
        print("【系统启动】前端可通过此地址连接获取ASR结果")
    else:
        print("【系统启动】WebSocket服务器启动失败，但ASR功能仍可正常使用")
        print("【系统启动】结果将仅保存到文件，无法推送到前端")

    # 2. 从控制台获取密钥信息：https://console.xfyun.cn/services/rta_new
    APP_ID = "4520e15c"
    ACCESS_KEY_ID = "e4e89b97b933bd6f2c7b143d0d8d8dae"
    ACCESS_KEY_SECRET = "NTdkOTUzMmIyMGIxY2NjOGYxYjhhMGNh"

    print(f"\n【系统配置】ASR服务配置完成")
    print(f"【系统配置】APP_ID: {APP_ID}")
    print(f"【系统配置】ACCESS_KEY_ID: {ACCESS_KEY_ID[:8]}...")

    # 3. 执行核心流程：使用多音频流处理模式
    input_dir = os.path.join(os.path.dirname(__file__), 'input_chunks')
    output_dir = os.path.join(os.path.dirname(__file__), 'outputs')
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n【系统配置】输入目录: {input_dir}")
    print(f"【系统配置】输出目录: {output_dir}")

    # 4. 初始化音频流处理器（设置30秒超时）
    processor = AudioStreamProcessor(APP_ID, ACCESS_KEY_ID, ACCESS_KEY_SECRET, input_dir, output_dir,
                                     timeout_seconds=30)

    print(f"\n【系统启动】音频流处理器初始化完成")
    print(f"【系统启动】超时时间: 30秒")
    print(f"【系统启动】最大重连次数: 3次")

    # 5. 显示系统状态
    ws_status = ws_server_manager.get_status()
    print(f"\n【系统状态】WebSocket服务器: {'运行中' if ws_status['is_running'] else '未运行'}")
    print(f"【系统状态】当前连接数: {ws_status['client_count']}")
    print(f"【系统状态】已推送消息: {ws_status['total_messages_sent']} 条")

    print(f"\n【系统启动】开始监听音频文件...")
    print(f"【系统启动】请将音频文件放入 {input_dir} 目录")
    print(f"【系统启动】结果将保存到 {output_dir} 目录")
    print(f"【系统启动】前端连接地址: ws://{ws_status['host']}:{ws_status['port']}")
    print("=" * 80)

    try:
        # 6. 启动多音频流处理模式
        processor.run_multi_stream_processing()
    except KeyboardInterrupt:
        print("\n【系统关闭】用户手动中断")
    except Exception as e:
        print(f"\n【系统错误】致命异常: {e}")
    finally:
        print("\n【系统关闭】正在关闭WebSocket服务器...")
        ws_server_manager.stop_server()
        print("【系统关闭】系统已安全关闭")
