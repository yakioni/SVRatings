from sqlalchemy import create_engine
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session, scoped_session, sessionmaker
import logging

# データベース設定
db_path = 'db/beyond_ratings.db'
engine = create_engine(f'sqlite:///{db_path}', echo=False)

Base = automap_base()
Base.metadata.clear()

# テーブルマッピング
Base.prepare(engine, reflect=True,
  reflection_options={'only': [
    'beyond_user','beyond_deck_class','beyond_match_history',
    'beyond_season','beyond_user_season_record',
  ]})

# セッション作成
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

def get_session():
    """新しいセッションを取得"""
    return Session(engine)

def get_scoped_session():
    """スコープ付きセッションを取得"""
    return SessionLocal()

def close_session():
    """スコープ付きセッションを閉じる"""
    SessionLocal.remove()

# モデルクラスのマッピング - 循環インポートを避けるため、ここで定義
try:
    # Beyond系テーブル
    User = Base.classes.beyond_user
    DeckClass = Base.classes.beyond_deck_class
    MatchHistory = Base.classes.beyond_match_history
    Season = Base.classes.beyond_season
    UserSeasonRecord = Base.classes.beyond_user_season_record
    
    logging.info("Database models mapped successfully")
    
except Exception as e:
    logging.error(f"Failed to map database models: {e}")
    raise

# グローバルセッション（互換性のため）
session = get_session()