import os
from dotenv import load_dotenv
import logging
import sys
from zoneinfo import ZoneInfo

# 環境変数を読み込み
load_dotenv()

# Bot設定
BOT_TOKEN_1 = os.getenv('TOKEN2')  # マッチング・ユーザー管理担当
BOT_TOKEN_2 = os.getenv('TOKEN3')  # ランキング・戦績担当

# タイムゾーン設定
JST = ZoneInfo('Asia/Tokyo')

# チャンネルID設定
WELCOME_CHANNEL_ID = 1296838522237358161
PROFILE_CHANNEL_ID = 1296838573789810699
RANKING_CHANNEL_ID = 1296838290313580544
RANKING_UPDATE_CHANNEL_ID = 1389726519399547102
PAST_RANKING_CHANNEL_ID = 1296838259246235763
RECORD_CHANNEL_ID = 1296838337117552710
PAST_RECORD_CHANNEL_ID = 1296838359616061450
LAST_50_MATCHES_RECORD_CHANNEL_ID = 1296838394734973020
MATCHING_CHANNEL_ID = 1296838229903020124
BATTLE_CHANNEL_ID = 1296838449948786768
COMMAND_CHANNEL_ID = 1372690526289137705

# メッセージ設定
BATTLE_GUIDE_TEXT = "「トラブルの際は、必ず対戦相手とのチャットでコミュニケーションを取って下さい。細かいルールは「battle-guide」を参照して下さい。」"

# ゲーム設定
VALID_CLASSES = ['エルフ', 'ロイヤル', 'ウィッチ', 'ドラゴン', 'ナイトメア', 'ビショップ', 'ネメシス']
# クラス略称マッピング
CLASS_ABBREVIATIONS = {
    "エルフ": "E",
    "ロイヤル": "R",
    "ウィッチ": "W",
    "ナイトメア": "Ni",
    "ドラゴン": "D",
    "ビショップ": "B",
    "ネメシス": "Nm"
}

# レーティング設定
DEFAULT_RATING = 1500
DEFAULT_TRUST_POINTS = 100
BASE_RATING_CHANGE = 20
RATING_DIFF_MULTIPLIER = 0.025
MAX_RATING_DIFF_FOR_MATCH = 300

# タイムアウト設定
MATCHMAKING_TIMEOUT = 60  # マッチング待機タイムアウト（秒）
RESULT_REPORT_TIMEOUT = 3 * 60 * 60  # 結果報告タイムアウト（3時間）
THREAD_DELETE_DELAY = 20 * 60 * 60  # スレッド削除遅延（20時間）

# 実績設定
RANK_ACHIEVEMENTS = [
    (1, "1位"),
    (2, "2位"),
    (3, "3位"),
    (4, "TOP8"),
    (5, "TOP16"),
    (6, "100位以内"),
]

WIN_RATE_ACHIEVEMENTS = [
    (1, "70%以上"),
    (2, "65%以上"),
    (3, "60%以上"),
]

# API制限設定
API_CALL_SEMAPHORE_LIMIT = 5
REQUEST_QUEUE_SLEEP = 0.1

def setup_logging():
    """ログ設定の初期化"""
    import os
    
    # ログディレクトリを作成
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 既存のハンドラーをクリア
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # カスタムフォーマッター
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # コンソールハンドラー
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # ファイルハンドラー
    file_handler = logging.FileHandler("logs/bot.log", encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # エラー専用ファイルハンドラー
    error_handler = logging.FileHandler("logs/error.log", encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # ルートロガーの設定
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    
    # SQLAlchemyのログレベルを調整
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('discord').setLevel(logging.INFO)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    
    # テストログを出力
    logging.info("🎯 Logging system initialized successfully")
    logging.debug("🔧 Debug logging is enabled")
    logging.warning("⚠️ Warning logging is enabled")
    
    return True

def validate_config():
    """設定の検証"""
    if not BOT_TOKEN_1:
        raise ValueError("BOT_TOKEN_1 (TOKEN2) is not set in environment variables")
    if not BOT_TOKEN_2:
        raise ValueError("BOT_TOKEN_2 (TOKEN3) is not set in environment variables")
    
    logging.info("✅ Configuration validated successfully")
    return True