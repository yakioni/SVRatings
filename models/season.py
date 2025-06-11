from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from models.base import BaseModel
from config.database import Season, UserSeasonRecord, User
from config.settings import JST

class SeasonModel(BaseModel):
    """シーズン関連のデータベース操作"""
    
    def __init__(self):
        super().__init__()
        self.Season = Season
        self.UserSeasonRecord = UserSeasonRecord
        self.User = User
    
    def get_current_season(self) -> Optional[Season]:
        """現在のシーズンを取得（データをコピーして返す）"""
        def _get_current(session: Session):
            season = session.query(self.Season).filter(
                self.Season.end_date == None
            ).order_by(desc(self.Season.id)).first()
            
            if season:
                # セッション外で使用するためにデータをコピー
                return {
                    'id': season.id,
                    'season_name': season.season_name,
                    'start_date': season.start_date,
                    'end_date': season.end_date,
                    'created_at': getattr(season, 'created_at', None)
                }
            return None
        
        season_data = self.safe_execute(_get_current)
        if season_data:
            # 辞書データから簡単なオブジェクトを作成
            class SeasonInfo:
                def __init__(self, data):
                    self.id = data['id']
                    self.season_name = data['season_name']
                    self.start_date = data['start_date']
                    self.end_date = data['end_date']
                    self.created_at = data.get('created_at')
            
            return SeasonInfo(season_data)
        return None
    
    def get_current_season_name(self) -> Optional[str]:
        """現在のシーズン名を取得"""
        def _get_current_name(session: Session):
            season = session.query(self.Season).filter(
                self.Season.end_date == None
            ).order_by(desc(self.Season.id)).first()
            return season.season_name if season else None
        
        return self.safe_execute(_get_current_name)
    
    def get_current_season_id(self) -> Optional[int]:
        """現在のシーズンIDを取得"""
        def _get_current_id(session: Session):
            season = session.query(self.Season).filter(
                self.Season.end_date == None
            ).order_by(desc(self.Season.id)).first()
            return season.id if season else None
        
        return self.safe_execute(_get_current_id)
    
    def is_season_active(self) -> bool:
        """シーズンがアクティブかチェック"""
        def _is_active(session: Session):
            season = session.query(self.Season).filter(
                self.Season.end_date == None
            ).order_by(desc(self.Season.id)).first()
            
            if not season:
                return False
            
            return (season.start_date is not None and 
                    season.end_date is None)
        
        return self.safe_execute(_is_active) or False
    
    def create_season(self, season_name: str) -> Optional[Dict[str, Any]]:
        """新しいシーズンを作成"""
        def _create_season(session: Session):
            # 既存のアクティブシーズンをチェック
            active_season = session.query(self.Season).filter(
                self.Season.end_date == None
            ).first()
            
            if active_season:
                raise ValueError("Active season already exists. End current season first.")
            
            # 重複する名前をチェック
            existing_season = session.query(self.Season).filter_by(
                season_name=season_name
            ).first()
            
            if existing_season:
                raise ValueError(f"Season with name '{season_name}' already exists")
            
            now = datetime.now(JST)
            new_season = self.Season(
                season_name=season_name,
                start_date=now.strftime('%Y-%m-%d %H:%M:%S'),
                end_date=None,
                created_at=now.strftime('%Y-%m-%d %H:%M:%S')
            )
            
            session.add(new_season)
            session.flush()  # IDを取得するためにflush
            
            # 辞書として返す
            return {
                'id': new_season.id,
                'season_name': new_season.season_name,
                'start_date': new_season.start_date,
                'end_date': new_season.end_date,
                'created_at': getattr(new_season, 'created_at', None)
            }
        
        return self.execute_with_session(_create_season)
    
    def end_season(self) -> Optional[Dict[str, Any]]:
        """現在のシーズンを終了"""
        def _end_season(session: Session):
            current_season = session.query(self.Season).filter(
                self.Season.end_date == None
            ).order_by(desc(self.Season.id)).first()
            
            if not current_season:
                raise ValueError("No active season found")
            
            now = datetime.now(JST)
            current_season.end_date = now.strftime('%Y-%m-%d %H:%M:%S')
            
            # 辞書として返す
            return {
                'id': current_season.id,
                'season_name': current_season.season_name,
                'start_date': current_season.start_date,
                'end_date': current_season.end_date,
                'created_at': getattr(current_season, 'created_at', None)
            }
        
        return self.execute_with_session(_end_season)
    
    def get_past_seasons(self) -> List[Dict[str, Any]]:
        """過去のシーズン一覧を取得"""
        def _get_past_seasons(session: Session):
            seasons = session.query(self.Season).filter(
                self.Season.end_date.isnot(None)
            ).order_by(desc(self.Season.id)).all()
            
            return [
                {
                    'id': season.id,
                    'season_name': season.season_name,
                    'start_date': season.start_date,
                    'end_date': season.end_date,
                    'created_at': getattr(season, 'created_at', None)
                }
                for season in seasons
            ]
        
        return self.safe_execute(_get_past_seasons) or []
    
    def get_season_by_id(self, season_id: int) -> Optional[Dict[str, Any]]:
        """IDでシーズンを取得"""
        def _get_season(session: Session):
            season = session.query(self.Season).filter_by(id=season_id).first()
            if season:
                return {
                    'id': season.id,
                    'season_name': season.season_name,
                    'start_date': season.start_date,
                    'end_date': season.end_date,
                    'created_at': getattr(season, 'created_at', None)
                }
            return None
        
        return self.safe_execute(_get_season)
    
    def get_all_seasons(self) -> List[Dict[str, Any]]:
        """全シーズンを取得"""
        def _get_all_seasons(session: Session):
            seasons = session.query(self.Season).order_by(desc(self.Season.id)).all()
            
            return [
                {
                    'id': season.id,
                    'season_name': season.season_name,
                    'start_date': season.start_date,
                    'end_date': season.end_date,
                    'created_at': getattr(season, 'created_at', None)
                }
                for season in seasons
            ]
        
        return self.safe_execute(_get_all_seasons) or []
    
    def create_user_season_record(self, user_id: int, season_id: int, 
                                 rating: float, rank: int, win_count: int, 
                                 loss_count: int, total_matches: int, 
                                 max_win_streak: int) -> Optional[UserSeasonRecord]:
        """ユーザーのシーズン記録を作成"""
        def _create_record(session: Session):
            # 既存の記録をチェック
            existing_record = session.query(self.UserSeasonRecord).filter_by(
                user_id=user_id, season_id=season_id
            ).first()
            
            if existing_record:
                # 既存の記録を更新
                existing_record.rating = rating
                existing_record.rank = rank
                existing_record.win_count = win_count
                existing_record.loss_count = loss_count
                existing_record.total_matches = total_matches
                existing_record.max_win_streak = max_win_streak
                existing_record.updated_at = datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')
                return existing_record
            else:
                # 新しい記録を作成
                new_record = self.UserSeasonRecord(
                    user_id=user_id,
                    season_id=season_id,
                    rating=rating,
                    rank=rank,
                    win_count=win_count,
                    loss_count=loss_count,
                    total_matches=total_matches,
                    max_win_streak=max_win_streak,
                    updated_at=datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')
                )
                session.add(new_record)
                return new_record
        
        return self.execute_with_session(_create_record)
    
    def get_user_season_record(self, user_id: int, season_id: int) -> Optional[UserSeasonRecord]:
        """ユーザーの特定シーズン記録を取得"""
        def _get_record(session: Session):
            return session.query(self.UserSeasonRecord).filter_by(
                user_id=user_id, season_id=season_id
            ).first()
        
        return self.safe_execute(_get_record)
    
    def get_user_all_season_records(self, user_id: int) -> List[UserSeasonRecord]:
        """ユーザーの全シーズン記録を取得"""
        def _get_all_records(session: Session):
            return session.query(self.UserSeasonRecord).filter_by(
                user_id=user_id
            ).order_by(desc(self.UserSeasonRecord.season_id)).all()
        
        return self.safe_execute(_get_all_records) or []
    
    def get_season_rankings(self, season_id: int, limit: int = 100) -> List[UserSeasonRecord]:
        """シーズンのランキングを取得"""
        def _get_rankings(session: Session):
            return session.query(self.UserSeasonRecord).filter_by(
                season_id=season_id
            ).order_by(desc(self.UserSeasonRecord.rating)).limit(limit).all()
        
        return self.safe_execute(_get_rankings) or []
    
    def finalize_season(self, season_id: int) -> Dict[str, Any]:
        """シーズンを確定し、ユーザー統計を保存"""
        def _finalize_season(session: Session):
            # シーズンの存在確認
            season = session.query(self.Season).filter_by(id=season_id).first()
            if not season:
                raise ValueError(f"Season with ID {season_id} not found")
            
            # latest_season_matched が True のユーザーを取得
            users = session.query(self.User).filter(
                self.User.latest_season_matched == True
            ).all()
            
            if not users:
                return {'message': 'No users participated in this season', 'count': 0}
            
            # 効果的レートでユーザーをソート
            user_final_ratings = []
            for user in users:
                if user.stay_flag == 1:
                    if user.rating > user.stayed_rating:
                        final_rating = user.rating
                        win_count = user.win_count
                        loss_count = user.loss_count
                        total_matches = user.total_matches
                    else:
                        final_rating = user.stayed_rating
                        win_count = user.stayed_win_count
                        loss_count = user.stayed_loss_count
                        total_matches = user.stayed_total_matches
                else:
                    final_rating = user.rating
                    win_count = user.win_count
                    loss_count = user.loss_count
                    total_matches = user.total_matches
                
                user_final_ratings.append((
                    user.id, final_rating, win_count, loss_count, 
                    total_matches, user.max_win_streak
                ))
            
            # レートでソートして順位を計算
            user_final_ratings.sort(key=lambda x: x[1], reverse=True)
            
            user_rankings = {}
            current_rank = 1
            previous_rating = None
            
            for idx, (user_id, final_rating, win_count, loss_count, total_matches, max_win_streak) in enumerate(user_final_ratings):
                if final_rating != previous_rating:
                    current_rank = idx + 1
                user_rankings[user_id] = (current_rank, final_rating, win_count, loss_count, total_matches, max_win_streak)
                previous_rating = final_rating
            
            # ユーザーシーズン記録を作成
            records_created = 0
            for user_id, (rank, rating, win_count, loss_count, total_matches, max_win_streak) in user_rankings.items():
                self.create_user_season_record(
                    user_id=user_id,
                    season_id=season_id,
                    rating=rating,
                    rank=rank,
                    win_count=win_count,
                    loss_count=loss_count,
                    total_matches=total_matches,
                    max_win_streak=max_win_streak
                )
                records_created += 1
            
            return {
                'message': f'Season {season.season_name} finalized successfully',
                'season_id': season_id,
                'season_name': season.season_name,
                'participants': len(users),
                'records_created': records_created
            }
        
        return self.execute_with_session(_finalize_season)
    
    def get_season_statistics(self, season_id: int) -> Dict[str, Any]:
        """シーズンの統計情報を取得"""
        def _get_stats(session: Session):
            season = session.query(self.Season).filter_by(id=season_id).first()
            if not season:
                return {}
            
            records = session.query(self.UserSeasonRecord).filter_by(
                season_id=season_id
            ).all()
            
            if not records:
                return {
                    'season_name': season.season_name,
                    'participants': 0,
                    'total_matches': 0,
                    'average_rating': 0,
                    'highest_rating': 0,
                    'lowest_rating': 0
                }
            
            total_matches = sum(record.total_matches for record in records)
            ratings = [record.rating for record in records]
            
            return {
                'season_name': season.season_name,
                'participants': len(records),
                'total_matches': total_matches,
                'average_rating': sum(ratings) / len(ratings) if ratings else 0,
                'highest_rating': max(ratings) if ratings else 0,
                'lowest_rating': min(ratings) if ratings else 0,
                'start_date': season.start_date,
                'end_date': season.end_date
            }
        
        return self.safe_execute(_get_stats) or {}