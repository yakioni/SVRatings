from sqlalchemy import create_engine, Column, Integer, Text, Boolean, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# データベースエンジンの作成
DATABASE_URL = "sqlite:///beyond_ratings.db"
engine = create_engine(DATABASE_URL)

# ベースクラスの作成
Base = declarative_base()

class BeyondUser(Base):
    __tablename__ = 'beyond_user'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_id = Column(Text)
    user_name = Column(Text)
    shadowverse_id = Column(Text)
    rating = Column(Integer, default=1500)
    stayed_rating = Column(Integer, default=1500)
    stay_flag = Column(Boolean, default=False)
    total_matches = Column(Integer, default=0)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    win_streak = Column(Integer, default=0)
    max_win_streak = Column(Integer, default=0)
    latest_season_matched = Column(Boolean, default=False)
    cancelled_matched_count = Column(Integer, default=0)
    class1 = Column(Text)
    class2 = Column(Text)
    stayed_total_matches = Column(Integer, default=0)
    stayed_win_count = Column(Integer, default=0)
    stayed_loss_count = Column(Integer, default=0)
    stayed_win_streak = Column(Integer, default=0)
    stayed_max_win_streak = Column(Integer, default=0)
    stayed_latest_season_matched = Column(Boolean, default=False)
    stayed_cancelled_matched_count = Column(Integer, default=0)
    stayed_class1 = Column(Text)
    stayed_class2 = Column(Text)
    trust_points = Column(Integer, default=100)
    created_at = Column(Text, default='CURRENT_TIMESTAMP')
    updated_at = Column(Text, default='CURRENT_TIMESTAMP')
    name_change_available = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)
    note_account_name = Column(Text)


class BeyondSeason(Base):
    __tablename__ = 'beyond_season'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    season_name = Column(Text)
    start_date = Column(Text)
    end_date = Column(Text)
    created_at = Column(Text, default='CURRENT_TIMESTAMP')


class BeyondDeckClass(Base):
    __tablename__ = 'beyond_deck_class'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    class_name = Column(Text)
    delete_flag = Column(Boolean, default=False)
    created_at = Column(Text, default='CURRENT_TIMESTAMP')


class BeyondMatchHistory(Base):
    __tablename__ = 'beyond_match_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user1_id = Column(Integer, ForeignKey('beyond_user.id'))
    user2_id = Column(Integer, ForeignKey('beyond_user.id'))
    match_date = Column(Text)
    season_name = Column(Text)
    user1_class_a = Column(Text)
    user1_class_b = Column(Text)
    user2_class_a = Column(Text)
    user2_class_b = Column(Text)
    user1_rating_change = Column(Integer)
    user2_rating_change = Column(Integer)
    winner_user_id = Column(Integer, ForeignKey('beyond_user.id'))
    loser_user_id = Column(Integer, ForeignKey('beyond_user.id'))
    user1_stay_flag = Column(Boolean, default=False)
    user2_stay_flag = Column(Boolean, default=False)
    before_user1_rating = Column(Integer)
    before_user2_rating = Column(Integer)
    after_user1_rating = Column(Integer)
    after_user2_rating = Column(Integer)
    user1_selected_class = Column(String(20))
    user2_selected_class = Column(String(20))


class BeyondUserSeasonRecord(Base):
    __tablename__ = 'beyond_user_season_record'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('beyond_user.id'))
    season_id = Column(Integer, ForeignKey('beyond_season.id'))
    rating = Column(Integer)
    rank = Column(Integer)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    updated_at = Column(Text, default='CURRENT_TIMESTAMP')
    total_matches = Column(Integer, default=0)
    max_win_streak = Column(Integer, default=0)


def create_database():
    """空のデータベースとテーブルを作成"""
    Base.metadata.create_all(bind=engine)
    print("データベースが作成されました: beyond_database.db")


def add_deck_classes():
    """デッキクラスを追加"""
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 既存のデータがあるかチェック
        existing_count = session.query(BeyondDeckClass).count()
        if existing_count > 0:
            print("デッキクラスは既に存在します。")
            return
        
        # デッキクラスのリスト
        deck_classes = [
            "エルフ",
            "ロイヤル", 
            "ウィッチ",
            "ドラゴン",
            "ビショップ",
            "ネメシス",
            "ナイトメア"
        ]
        
        # デッキクラスを追加
        for class_name in deck_classes:
            deck_class = BeyondDeckClass(class_name=class_name)
            session.add(deck_class)
        
        session.commit()
        print("デッキクラスが追加されました。")
        
    except Exception as e:
        session.rollback()
        print(f"エラーが発生しました: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    create_database()
    add_deck_classes()