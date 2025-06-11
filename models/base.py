from abc import ABC, abstractmethod
from typing import Optional, List, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
import os
import shutil

class BaseModel(ABC):
    """ベースモデルクラス"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_session(self) -> Session:
        """新しいセッションを取得"""
        from config.database import get_session
        return get_session()
    
    def execute_with_session(self, func, *args, **kwargs):
        """セッションを使用して関数を実行"""
        session = self.get_session()
        try:
            result = func(session, *args, **kwargs)
            session.commit()
            return result
        except SQLAlchemyError as e:
            session.rollback()
            self.logger.error(f"Database error in {func.__name__}: {e}")
            raise
        except Exception as e:
            session.rollback()
            self.logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise
        finally:
            session.close()
    
    def safe_execute(self, func, *args, **kwargs):
        """安全に関数を実行（例外をキャッチ）"""
        try:
            return self.execute_with_session(func, *args, **kwargs)
        except Exception as e:
            self.logger.error(f"Error in safe_execute: {e}")
            return None

class DatabaseManager:
    """データベース操作の共通管理クラス"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def create_tables_if_not_exist(self):
        """テーブルが存在しない場合は作成"""
        try:
            from config.database import get_session, User
            session = get_session()
            
            # テーブルの存在確認
            user_count = session.query(User).count()
            self.logger.info(f"User table contains {user_count} records")
            
            session.close()
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking tables: {e}")
            return False
    
    def backup_database(self, backup_path: str) -> bool:
        """データベースのバックアップを作成"""
        try:
            from config.database import db_path
            
            if os.path.exists(db_path):
                shutil.copy2(db_path, backup_path)
                self.logger.info(f"Database backed up to {backup_path}")
                return True
            else:
                self.logger.error(f"Database file not found: {db_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error backing up database: {e}")
            return False
    
    def get_database_stats(self) -> dict:
        """データベースの統計情報を取得"""
        try:
            from config.database import get_session, User, Season, MatchHistory, DeckClass, UserSeasonRecord
            session = get_session()
            
            stats = {
                'users': session.query(User).count(),
                'seasons': session.query(Season).count(),
                'matches': session.query(MatchHistory).count(),
                'classes': session.query(DeckClass).count(),
                'user_season_records': session.query(UserSeasonRecord).count()
            }
            
            session.close()
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting database stats: {e}")
            return {}

# グローバルなデータベースマネージャーインスタンス
db_manager = DatabaseManager()