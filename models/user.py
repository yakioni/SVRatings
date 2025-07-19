from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, case, and_
from models.base import BaseModel
from config.database import User, DeckClass
from config.settings import DEFAULT_RATING, DEFAULT_TRUST_POINTS, JST
import logging

class UserModel(BaseModel):
    """ユーザー関連のデータベース操作"""
    
    def __init__(self):
        super().__init__()
        self.User = User
        self.DeckClass = DeckClass
    
    def create_user(self, discord_id: str, user_name: str, shadowverse_id: str) -> Optional[Dict[str, Any]]:
        """新しいユーザーを作成"""
        def _create_user(session: Session):
            # 重複チェック
            existing_user = session.query(self.User).filter_by(discord_id=discord_id).first()
            if existing_user:
                raise ValueError("このDiscordアカウントは既に登録されています")
            
            existing_name = session.query(self.User).filter_by(user_name=user_name).first()
            if existing_name:
                raise ValueError("このユーザー名は既に使用されています")
            
            existing_sv_id = session.query(self.User).filter_by(shadowverse_id=shadowverse_id).first()
            if existing_sv_id:
                raise ValueError("このShadowverse IDは既に使用されています")
            
            # 新しいユーザーを作成
            new_user = self.User(
                discord_id=discord_id,
                user_name=user_name,
                shadowverse_id=shadowverse_id,
                rating=DEFAULT_RATING,
                trust_points=DEFAULT_TRUST_POINTS,
                win_count=0,
                loss_count=0,
                total_matches=0,
                win_streak=0,
                max_win_streak=0,
                stayed_rating=DEFAULT_RATING,
                stayed_win_count=0,
                stayed_loss_count=0,
                stayed_total_matches=0,
                stay_flag=0,
                latest_season_matched=False,
                class1=None,
                class2=None
            )
            
            # 名前変更権フィールドが存在する場合のみ設定
            if hasattr(new_user, 'name_change_available'):
                new_user.name_change_available = True
            
            session.add(new_user)
            session.flush()  # IDを取得するためにflush
            
            # セッション外で使用するためにデータをコピー
            return self._user_to_dict(new_user)
        
        return self.execute_with_session(_create_user)
    
    def get_user_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Discord IDでユーザーを取得（セッション外でアクセス可能な形式）"""
        def _get_user(session: Session):
            user = session.query(self.User).filter_by(discord_id=discord_id).first()
            return self._user_to_dict(user) if user else None
        
        return self.safe_execute(_get_user)
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """IDでユーザーを取得（セッション外でアクセス可能な形式）"""
        def _get_user(session: Session):
            user = session.query(self.User).filter_by(id=user_id).first()
            return self._user_to_dict(user) if user else None
        
        return self.safe_execute(_get_user)
    
    def _user_to_dict(self, user) -> Dict[str, Any]:
        """SQLAlchemyオブジェクトを辞書に変換"""
        if not user:
            return None
        
        result = {
            'id': user.id,
            'discord_id': user.discord_id,
            'user_name': user.user_name,
            'shadowverse_id': user.shadowverse_id,
            'rating': user.rating,
            'trust_points': user.trust_points,
            'win_count': user.win_count,
            'loss_count': user.loss_count,
            'total_matches': user.total_matches,
            'win_streak': user.win_streak,
            'max_win_streak': user.max_win_streak,
            'stayed_rating': user.stayed_rating,
            'stayed_win_count': user.stayed_win_count,
            'stayed_loss_count': user.stayed_loss_count,
            'stayed_total_matches': user.stayed_total_matches,
            'stay_flag': user.stay_flag,
            'latest_season_matched': user.latest_season_matched,
            'class1': user.class1,
            'class2': user.class2
        }
        
        # 名前変更権フィールドが存在する場合のみ追加
        if hasattr(user, 'name_change_available'):
            result['name_change_available'] = user.name_change_available
        else:
            result['name_change_available'] = True  # デフォルト値
        
        return result
    
    def change_user_name(self, discord_id: str, new_name: str) -> Dict[str, Any]:
        """ユーザー名を変更（名前変更権を消費）"""
        def _change_name(session: Session):
            user = session.query(self.User).filter_by(discord_id=discord_id).first()
            if not user:
                return {'success': False, 'message': 'ユーザーが見つかりません。'}
            
            # 名前変更権の確認
            name_change_available = getattr(user, 'name_change_available', True)
            if not name_change_available:
                return {
                    'success': False, 
                    'message': '名前変更権は来月1日まで利用できません。'
                }
            
            # 新しい名前の重複チェック
            existing_user = session.query(self.User).filter(
                and_(self.User.user_name == new_name, self.User.id != user.id)
            ).first()
            if existing_user:
                return {'success': False, 'message': 'その名前は既に使用されています。'}
            
            # 名前を変更
            old_name = user.user_name
            user.user_name = new_name
            
            # 名前変更権を無効化
            if hasattr(user, 'name_change_available'):
                user.name_change_available = False
            
            return {
                'success': True,
                'message': f'名前を "{old_name}" から "{new_name}" に変更しました。',
                'old_name': old_name,
                'new_name': new_name
            }
        
        return self.execute_with_session(_change_name)
    
    def reset_name_change_permissions(self) -> int:
        """全ユーザーの名前変更権をリセット（月次実行用）"""
        def _reset_permissions(session: Session):
            reset_count = 0
            
            # 名前変更権が無効なユーザーを取得
            if hasattr(self.User, 'name_change_available'):
                users = session.query(self.User).filter(
                    self.User.name_change_available == False
                ).all()
                
                for user in users:
                    user.name_change_available = True
                    reset_count += 1
            else:
                # フィールドが存在しない場合はログに記録
                self.logger.warning("name_change_available field not found in User table")
            
            return reset_count
        
        return self.execute_with_session(_reset_permissions)
    
    def update_user_classes(self, discord_id: str, class1: str, class2: str) -> bool:
        """ユーザーのクラスを更新"""
        def _update_classes(session: Session):
            user = session.query(self.User).filter_by(discord_id=discord_id).first()
            if user:
                user.class1 = class1
                user.class2 = class2
                return True
            return False
        
        return self.execute_with_session(_update_classes)
    
    def update_trust_points(self, discord_id: str, change: int) -> Optional[int]:
        """信用ポイントを更新"""
        def _update_trust(session: Session):
            user = session.query(self.User).filter_by(discord_id=discord_id).first()
            if user:
                user.trust_points += change
                return user.trust_points
            return None
        
        return self.execute_with_session(_update_trust)
    
    def get_user_rank(self, discord_id: str) -> Optional[int]:
        """ユーザーの現在の順位を取得"""
        def _get_rank(session: Session):
            user_data = self.get_user_by_discord_id(discord_id)
            if not user_data or not user_data['latest_season_matched']:
                return None
            
            # 効果的レートを計算
            effective_rating = case(
                (and_(self.User.stay_flag == 1, self.User.stayed_rating > self.User.rating), 
                 self.User.stayed_rating),
                else_=self.User.rating
            ).label('effective_rating')
            
            # 自分より高いレートのユーザー数を数える
            user_effective_rating = max(user_data['rating'], user_data['stayed_rating'] or 0)
            
            higher_users = session.query(self.User).filter(
                and_(
                    self.User.latest_season_matched == True,
                    effective_rating > user_effective_rating
                )
            ).count()
            
            return higher_users + 1
        
        return self.safe_execute(_get_rank)
    
    def toggle_stay_flag(self, discord_id: str) -> Dict[str, Any]:
        """Stay機能の切り替え"""
        def _toggle_stay(session: Session):
            user = session.query(self.User).filter_by(discord_id=discord_id).first()
            if not user:
                raise ValueError("ユーザーが見つかりません")
            
            if user.stay_flag == 0 and user.stayed_rating == DEFAULT_RATING:
                # stay機能を有効化
                user.stayed_rating = user.rating
                user.stayed_win_count = user.win_count
                user.stayed_loss_count = user.loss_count
                user.stayed_total_matches = user.total_matches
                user.stay_flag = 1
                
                # メインアカウントをリセット
                user.rating = DEFAULT_RATING
                user.win_count = 0
                user.loss_count = 0
                user.total_matches = 0
                user.win_streak = 0
                
                return {
                    'success': True,
                    'action': 'stay_enabled',
                    'message': 'stay機能が有効化されました。メインアカウントがリセットされました。'
                }
            
            elif user.stay_flag == 1:
                # stay機能を無効化（stayedデータをメインに復元）
                user.rating = user.stayed_rating
                user.win_count = user.stayed_win_count
                user.loss_count = user.stayed_loss_count
                user.total_matches = user.stayed_total_matches
                user.stay_flag = 0
                
                # stayedデータをリセット
                user.stayed_rating = DEFAULT_RATING
                user.stayed_win_count = 0
                user.stayed_loss_count = 0
                user.stayed_total_matches = 0
                
                return {
                    'success': True,
                    'action': 'stay_disabled',
                    'message': 'stay機能が無効化され、stayedデータがメインアカウントに復元されました。'
                }
            
            else:
                raise ValueError("現在、stay機能を使用できる状態ではありません")
        
        return self.execute_with_session(_toggle_stay)
    
    def reset_users_for_new_season(self) -> int:
        """新シーズン用にユーザーをリセット"""
        def _reset_users(session: Session):
            users = session.query(self.User).filter(
                self.User.latest_season_matched == True
            ).all()
            
            reset_count = 0
            for user in users:
                # レートをリセット
                user.rating = DEFAULT_RATING
                user.win_count = 0
                user.loss_count = 0
                user.total_matches = 0
                user.win_streak = 0
                user.max_win_streak = 0
                
                # stayedデータもリセット
                user.stayed_rating = DEFAULT_RATING
                user.stayed_win_count = 0
                user.stayed_loss_count = 0
                user.stayed_total_matches = 0
                user.stay_flag = 0
                
                # 最新シーズンマッチフラグをリセット
                user.latest_season_matched = False
                
                reset_count += 1
            
            return reset_count
        
        return self.execute_with_session(_reset_users)
    
    def get_valid_classes(self) -> List[str]:
        """有効なクラス一覧を取得"""
        def _get_classes(session: Session):
            classes = session.query(self.DeckClass).all()
            return [cls.class_name for cls in classes]
        
        return self.safe_execute(_get_classes) or []
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """全ユーザーを取得"""
        def _get_all(session: Session):
            users = session.query(self.User).all()
            return [self._user_to_dict(user) for user in users]
        
        return self.safe_execute(_get_all) or []
    
    def get_active_users(self) -> List[Dict[str, Any]]:
        """アクティブなユーザーを取得"""
        def _get_active(session: Session):
            users = session.query(self.User).filter(
                self.User.latest_season_matched == True
            ).all()
            return [self._user_to_dict(user) for user in users]
        
        return self.safe_execute(_get_active) or []
    
    def update_user_rating(self, user_id: int, new_rating: float) -> bool:
        """ユーザーのレーティングを更新"""
        def _update_rating(session: Session):
            user = session.query(self.User).filter_by(id=user_id).first()
            if user:
                user.rating = new_rating
                return True
            return False
        
        return self.execute_with_session(_update_rating)
    
    def increment_match_stats(self, user_id: int, won: bool) -> bool:
        """試合統計を更新"""
        def _increment_stats(session: Session):
            user = session.query(self.User).filter_by(id=user_id).first()
            if user:
                user.total_matches += 1
                if won:
                    user.win_count += 1
                    user.win_streak += 1
                    user.max_win_streak = max(user.max_win_streak, user.win_streak)
                else:
                    user.loss_count += 1
                    user.win_streak = 0
                return True
            return False
        
        return self.execute_with_session(_increment_stats)
    
    def search_users(self, query: str) -> List[Dict[str, Any]]:
        """ユーザーを検索"""
        def _search(session: Session):
            users = session.query(self.User).filter(
                self.User.user_name.like(f'%{query}%')
            ).all()
            return [self._user_to_dict(user) for user in users]
        
        return self.safe_execute(_search) or []