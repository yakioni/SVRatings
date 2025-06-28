import asyncio
import logging
import signal
import sys
import traceback
from config.bot_config import create_bots
from config.settings import setup_logging

class BotManager:
    def __init__(self):
        self.bots = []
        self.running = True
        
    async def start_bots(self):
        """2つのボットを並行して起動"""
        try:
            # 最初にログ設定を実行
            setup_logging()
            # 2つのボットインスタンスを作成
            logging.info("🤖 Creating bot instances...")
            bot1, bot2 = create_bots()
            self.bots = [bot1, bot2]
            logging.info("✅ Bot instances created successfully")
            
            # シグナルハンドラーの設定
            if sys.platform != 'win32':
                loop = asyncio.get_event_loop()
                for sig in (signal.SIGTERM, signal.SIGINT):
                    loop.add_signal_handler(sig, self.signal_handler)
                logging.info("✅ Signal handlers configured")
            
            # 並行してボットを実行
            logging.info("🚀 Starting bots...")
            tasks = [
                asyncio.create_task(bot1.start(bot1.token)),
                asyncio.create_task(bot2.start(bot2.token))
            ]
            
            logging.info("⏳ Waiting for bots to start...")
            await asyncio.gather(*tasks)
            
        except KeyboardInterrupt:
            logging.info("⌨️ Received keyboard interrupt, shutting down...")
        except Exception as e:
            logging.error(f"❌ Error starting bots: {e}")
            logging.error(traceback.format_exc())
        finally:
            await self.cleanup()
    
    def signal_handler(self):
        """シグナル受信時の処理"""
        self.running = False
        
    async def cleanup(self):
        """クリーンアップ処理"""
        logging.info("🧹 Cleaning up...")
        for i, bot in enumerate(self.bots, 1):
            if not bot.is_closed():
                logging.info(f"🔌 Closing bot {i}...")
                await bot.close()
        logging.info("✅ Cleanup completed")

async def main():
    """メイン実行関数"""
    manager = BotManager()
    await manager.start_bots()

if __name__ == "__main__":
    try:
        # Python実行時の基本ログ設定（setup_logging()の前）
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        print("=== Discord Bot Starting ===")
        print("Python version:", sys.version)
        print("Platform:", sys.platform)
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n=== Bot stopped by user ===")
    except Exception as e:
        print(f"=== Fatal error: {e} ===")
        traceback.print_exc()
        sys.exit(1)