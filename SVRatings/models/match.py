from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from models.base import BaseModel
from config.database import MatchHistory, User
from config.settings import JST, BASE_RATING_CHANGE, RATING_DIFF_MULTIPLIER

class MatchModel(BaseModel):
    """試合履歴関連のデータベース操作"""
    
    def __init__(self):
        super().__init__()
        self.MatchHistory = MatchHistory
        self.User = User
    
    def create_match_placeholder(self, user1_id: int, user2_id: int, season_name: str,
                                user1_class_a: str, user1_class_b: str,
                                user2_class_a: str, user2_class_b: str,
                                before_user1_rating: float, before_user2_rating: float) -> Optional[MatchHistory]:
        """マッチング成立時のプレースホルダー試合記録を作成"""
        def _create_placeholder(session: Session):
            user1 = session.query(self.User).filter_by(id=user1_id).first()
            user2 = session.query(self.User).filter_by(id=user2_id).first()
            
            if not user1 or not user2:
                raise ValueError("One or both users not found")
            
            match_date = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
            
            new_match = self.MatchHistory(
                user1_id=user1_id,
                user2_id=user2_id,
                match_date=match_date,
                season_name=season_name,
                user1_class_a=user1_class_a,
                user1_class_b=user1_class_b,
                user2_class_a=user2_class_a,
                user2_class_b=user2_class_b,
                user1_rating_change=0,
                user2_rating_change=0,
                winner_user_id=None,
                loser_user_id=None,
                before_user1_rating=before_user1_rating,
                before_user2_rating=before_user2_rating,
                after_user1_rating=None,
                after_user2_rating=None,
                user1_stay_flag=user1.stay_flag,
                user2_stay_flag=user2.stay_flag
            )
            
            session.add(new_match)
            return new_match
        
        return self.execute_with_session(_create_placeholder)
    
    def finalize_match_result(self, user1_id: int, user2_id: int, 
                             user1_wins: int, user2_wins: int,
                             before_user1_rating: float, before_user2_rating: float,
                             after_user1_rating: float, after_user2_rating: float) -> Optional[MatchHistory]:
        """試合結果を確定"""
        def _finalize_match(session: Session):
            # プレースホルダー試合を検索
            match = session.query(self.MatchHistory).filter(
                self.MatchHistory.user1_id == user1_id,
                self.MatchHistory.user2_id == user2_id,
                self.MatchHistory.before_user1_rating == before_user1_rating,
                self.MatchHistory.before_user2_rating == before_user2_rating,
                self.MatchHistory.after_user1_rating.is_(None)
            ).order_by(desc(self.MatchHistory.id)).first()
            
            # レーティング変動を計算
            user1_rating_change = after_user1_rating - before_user1_rating
            user2_rating_change = after_user2_rating - before_user2_rating
            
            # 勝者・敗者を決定
            if user1_wins > user2_wins:
                winner_user_id, loser_user_id = user1_id, user2_id
            else:
                winner_user_id, loser_user_id = user2_id, user1_id
            
            if match:
                # 既存のプレースホルダーを更新
                match.user1_rating_change = user1_rating_change
                match.user2_rating_change = user2_rating_change
                match.after_user1_rating = after_user1_rating
                match.after_user2_rating = after_user2_rating
                match.winner_user_id = winner_user_id
                match.loser_user_id = loser_user_id
                return match
            else:
                # プレースホルダーが見つからない場合は新規作成
                return self._create_new_match_record(
                    session, user1_id, user2_id, user1_rating_change, user2_rating_change,
                    winner_user_id, loser_user_id, before_user1_rating, before_user2_rating,
                    after_user1_rating, after_user2_rating
                )
        
        return self.execute_with_session(_finalize_match)
    
    def _create_new_match_record(self, session: Session, user1_id: int, user2_id: int,
                                user1_rating_change: float, user2_rating_change: float,
                                winner_user_id: int, loser_user_id: int,
                                before_user1_rating: float, before_user2_rating: float,
                                after_user1_rating: float, after_user2_rating: float) -> MatchHistory:
        """新しい試合記録を作成（プレースホルダーが見つからない場合）"""
        user1 = session.query(self.User).filter_by(id=user1_id).first()
        user2 = session.query(self.User).filter_by(id=user2_id).first()
        
        match_date = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        
        new_match = self.MatchHistory(
            user1_id=user1_id,
            user2_id=user2_id,
            match_date=match_date,
            season_name="Unknown",  # 通常はプレースホルダーから取得
            user1_class_a=user1.class1 if user1 else None,
            user1_class_b=user1.class2 if user1 else None,
            user2_class_a=user2.class1 if user2 else None,
            user2_class_b=user2.class2 if user2 else None,
            user1_rating_change=user1_rating_change,
            user2_rating_change=user2_rating_change,
            winner_user_id=winner_user_id,
            loser_user_id=loser_user_id,
            before_user1_rating=before_user1_rating,
            before_user2_rating=before_user2_rating,
            after_user1_rating=after_user1_rating,
            after_user2_rating=after_user2_rating,
            user1_stay_flag=user1.stay_flag if user1 else 0,
            user2_stay_flag=user2.stay_flag if user2 else 0
        )
        
        session.add(new_match)
        return new_match
    
    def get_user_match_history(self, user_id: int, limit: int = 50) -> List[MatchHistory]:
        """ユーザーの試合履歴を取得"""
        def _get_history(session: Session):
            return session.query(self.MatchHistory).filter(
                or_(
                    self.MatchHistory.user1_id == user_id,
                    self.MatchHistory.user2_id == user_id
                )
            ).order_by(desc(self.MatchHistory.match_date)).limit(limit).all()
        
        return self.safe_execute(_get_history) or []
    
    def get_user_vs_user_history(self, user1_id: int, user2_id: int) -> List[MatchHistory]:
        """特定のユーザー間の対戦履歴を取得"""
        def _get_vs_history(session: Session):
            return session.query(self.MatchHistory).filter(
                or_(
                    and_(self.MatchHistory.user1_id == user1_id, self.MatchHistory.user2_id == user2_id),
                    and_(self.MatchHistory.user1_id == user2_id, self.MatchHistory.user2_id == user1_id)
                )
            ).order_by(desc(self.MatchHistory.match_date)).all()
        
        return self.safe_execute(_get_vs_history) or []
    
    def get_user_season_matches(self, user_id: int, season_name: str, 
                               user_stay_flag: int = None) -> List[MatchHistory]:
        """ユーザーの特定シーズンの試合履歴を取得"""
        def _get_season_matches(session: Session):
            query = session.query(self.MatchHistory).filter(
                or_(
                    self.MatchHistory.user1_id == user_id,
                    self.MatchHistory.user2_id == user_id
                ),
                self.MatchHistory.season_name == season_name
            )
            
            # stay_flagが指定されている場合はフィルタリング
            if user_stay_flag is not None:
                query = query.filter(
                    or_(
                        and_(self.MatchHistory.user1_id == user_id, 
                             self.MatchHistory.user1_stay_flag == user_stay_flag),
                        and_(self.MatchHistory.user2_id == user_id, 
                             self.MatchHistory.user2_stay_flag == user_stay_flag)
                    )
                )
            
            return query.order_by(desc(self.MatchHistory.match_date)).all()
        
        return self.safe_execute(_get_season_matches) or []
    
    def get_user_class_matches(self, user_id: int, classes: List[str], 
                              season_name: str = None) -> List[MatchHistory]:
        """ユーザーの特定クラスでの試合履歴を取得"""
        def _get_class_matches(session: Session):
            if len(classes) == 1:
                # 単一クラス
                class_name = classes[0]
                query = session.query(self.MatchHistory).filter(
                    or_(
                        and_(self.MatchHistory.user1_id == user_id,
                             or_(self.MatchHistory.user1_class_a == class_name,
                                 self.MatchHistory.user1_class_b == class_name)),
                        and_(self.MatchHistory.user2_id == user_id,
                             or_(self.MatchHistory.user2_class_a == class_name,
                                 self.MatchHistory.user2_class_b == class_name))
                    )
                )
            elif len(classes) == 2:
                # クラスの組み合わせ
                class1, class2 = classes
                query = session.query(self.MatchHistory).filter(
                    or_(
                        and_(self.MatchHistory.user1_id == user_id,
                             or_(
                                 and_(self.MatchHistory.user1_class_a == class1,
                                      self.MatchHistory.user1_class_b == class2),
                                 and_(self.MatchHistory.user1_class_a == class2,
                                      self.MatchHistory.user1_class_b == class1)
                             )),
                        and_(self.MatchHistory.user2_id == user_id,
                             or_(
                                 and_(self.MatchHistory.user2_class_a == class1,
                                      self.MatchHistory.user2_class_b == class2),
                                 and_(self.MatchHistory.user2_class_a == class2,
                                      self.MatchHistory.user2_class_b == class1)
                             ))
                    )
                )
            else:
                return []
            
            if season_name:
                query = query.filter(self.MatchHistory.season_name == season_name)
            
            return query.order_by(desc(self.MatchHistory.match_date)).all()
        
        return self.safe_execute(_get_class_matches) or []
    
    def calculate_rating_change(self, player_rating: float, opponent_rating: float, 
                               player_wins: int, opponent_wins: int) -> float:
        """レーティング変動を計算"""
        rating_diff = player_rating - opponent_rating
        increment_per_win = RATING_DIFF_MULTIPLIER * abs(rating_diff)
        
        if player_rating > opponent_rating:
            if player_wins > opponent_wins:
                rating_change = BASE_RATING_CHANGE - increment_per_win
            else:
                rating_change = -(BASE_RATING_CHANGE + increment_per_win)
        else:
            if player_wins > opponent_wins:
                rating_change = BASE_RATING_CHANGE + increment_per_win
            else:
                rating_change = -(BASE_RATING_CHANGE - increment_per_win)
        
        return rating_change
    
    def get_match_by_id(self, match_id: int) -> Optional[MatchHistory]:
        """IDで試合履歴を取得"""
        def _get_match(session: Session):
            return session.query(self.MatchHistory).filter_by(id=match_id).first()
        
        return self.safe_execute(_get_match)
    
    def reverse_match_result(self, match_id: int) -> bool:
        """試合結果を反転"""
        def _reverse_match(session: Session):
            match = session.query(self.MatchHistory).filter_by(id=match_id).first()
            if not match:
                return False
            
            # 勝敗とレート変動を反転
            match.winner_user_id, match.loser_user_id = match.loser_user_id, match.winner_user_id
            match.user1_rating_change = -match.user1_rating_change
            match.user2_rating_change = -match.user2_rating_change
            
            # ユーザーのレートも調整
            user1 = session.query(self.User).filter_by(id=match.user1_id).first()
            user2 = session.query(self.User).filter_by(id=match.user2_id).first()
            
            if user1:
                user1.rating += (-2 * match.user1_rating_change)  # 元の変動の2倍分を加算
                # 勝敗数も調整
                if match.winner_user_id == user1.id:
                    user1.win_count += 1
                    user1.loss_count -= 1
                else:
                    user1.win_count -= 1
                    user1.loss_count += 1
            
            if user2:
                user2.rating += (-2 * match.user2_rating_change)
                # 勝敗数も調整
                if match.winner_user_id == user2.id:
                    user2.win_count += 1
                    user2.loss_count -= 1
                else:
                    user2.win_count -= 1
                    user2.loss_count += 1
            
            return True
        
        return self.execute_with_session(_reverse_match)
    
    def get_recent_matches(self, limit: int = 100) -> List[MatchHistory]:
        """最近の試合履歴を取得"""
        def _get_recent(session: Session):
            return session.query(self.MatchHistory).filter(
                self.MatchHistory.winner_user_id.isnot(None)
            ).order_by(desc(self.MatchHistory.match_date)).limit(limit).all()
        
        return self.safe_execute(_get_recent) or []