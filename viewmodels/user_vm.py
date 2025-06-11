from typing import Optional, Dict, Any
import logging

class UserViewModel:
    """ユーザー関連のビジネスロジック"""
    
    def __init__(self):
        # 遅延インポートで循環インポートを回避
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def register_user(self, discord_id: str, user_name: str, shadowverse_id: str) -> Dict[str, Any]:
        """ユーザーを登録"""
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            user = user_model.create_user(discord_id, user_name, shadowverse_id)
            if user:
                return {
                    'success': True,
                    'user': user,
                    'message': f"ユーザー {user_name} の登録が完了しました。"
                }
            else:
                return {
                    'success': False,
                    'message': "登録に失敗しました。"
                }
        except ValueError as e:
            return {
                'success': False,
                'message': str(e)
            }
        except Exception as e:
            self.logger.error(f"Error in register_user: {e}")
            return {
                'success': False,
                'message': "予期しないエラーが発生しました。"
            }
    
    def get_user_profile(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """ユーザープロフィールを取得"""
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            user = user_model.get_user_by_discord_id(discord_id)
            if not user:
                return None
            
            # 効果的レート
            effective_rating = max(user.rating, user.stayed_rating or 0)
            
            # 順位を取得
            rank = user_model.get_user_rank(discord_id)
            
            return {
                'user_name': user.user_name,
                'shadowverse_id': user.shadowverse_id,
                'rating': user.rating,
                'stayed_rating': user.stayed_rating,
                'effective_rating': effective_rating,
                'trust_points': user.trust_points,
                'win_count': user.win_count,
                'loss_count': user.loss_count,
                'total_matches': user.total_matches,
                'max_win_streak': user.max_win_streak,
                'current_win_streak': user.win_streak,
                'stay_flag': user.stay_flag,
                'rank': rank,
                'latest_season_matched': user.latest_season_matched
            }
        except Exception as e:
            self.logger.error(f"Error in get_user_profile: {e}")
            return None
    
    def update_user_settings(self, discord_id: str, **settings) -> bool:
        """ユーザー設定を更新"""
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            # 設定項目に応じて処理を分岐
            success = True
            
            if 'display_opponent_rating' in settings:
                # 相手レート表示設定の更新
                # UserModelに該当メソッドを追加する必要があります
                pass
            
            if 'class1' in settings and 'class2' in settings:
                success = user_model.update_user_classes(
                    discord_id, settings['class1'], settings['class2']
                )
            
            return success
        except Exception as e:
            self.logger.error(f"Error in update_user_settings: {e}")
            return False
    
    def execute_stay_function(self, discord_id: str) -> Dict[str, Any]:
        """Stay機能を実行"""
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            return user_model.toggle_stay_flag(discord_id)
        except Exception as e:
            self.logger.error(f"Error in execute_stay_function: {e}")
            return {
                'success': False,
                'message': "Stay機能の実行中にエラーが発生しました。"
            }
    
    def update_trust_points(self, discord_id: str, change: int) -> Dict[str, Any]:
        """信用ポイントを更新"""
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            new_points = user_model.update_trust_points(discord_id, change)
            if new_points is not None:
                return {
                    'success': True,
                    'new_points': new_points,
                    'message': f"信用ポイントが {change:+} 変更されました。現在: {new_points}"
                }
            else:
                return {
                    'success': False,
                    'message': "ユーザーが見つかりません。"
                }
        except Exception as e:
            self.logger.error(f"Error in update_trust_points: {e}")
            return {
                'success': False,
                'message': "信用ポイントの更新中にエラーが発生しました。"
            }