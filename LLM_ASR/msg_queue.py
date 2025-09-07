from asr_result_receiver_sdk import create_asr_receiver
import time


def process_asr_result(result_data):
    """处理ASR转写结果"""
    print("=" * 50)
    print("🎯 收到ASR转写结果")
    print("=" * 50)
    print(f"📝 文件名: {result_data.get('filename', 'unknown')}")
    print(f"📄 内容: {result_data.get('content', '')}")
    print(f"🎯 原因: {result_data.get('reason', 'unknown')}")
    print(f"⚡ 强制输出: {result_data.get('force', False)}")
    print(f"🆔 流ID: {result_data.get('stream_id', 'unknown')}")
    print("=" * 50)

    # 在这里添加你的处理逻辑
    # 例如：语义分析、数据库存储、API调用等
    perform_semantic_analysis(result_data['content'])


def perform_semantic_analysis(text):
    """执行语义分析（示例）"""
    print(f"🧠 开始语义分析: {text}")
    # 在这里实现你的语义分析逻辑
    time.sleep(1)  # 模拟处理时间
    print("✅ 语义分析完成")


def main():
    """主函数"""
    print("🚀 启动下游处理模块")

    # 创建接收器
    receiver = create_asr_receiver(
        backend="file",
        queue_dir="outputs"  # 与ASR系统使用相同的目录
    )

    # 添加处理回调
    receiver.add_callback(process_asr_result)

    print("✅ 接收器初始化完成")
    print("🎯 开始监听ASR转写结果...")
    print("⏹️ 按 Ctrl+C 停止监听")

    try:
        # 开始监听
        receiver.start_listening(interval=1.0)
    except KeyboardInterrupt:
        print("\n⏹️ 用户停止监听")
    finally:
        receiver.close()
        print("✅ 下游模块已关闭")


if __name__ == "__main__":
    main()