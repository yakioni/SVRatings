from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from sqlalchemy import desc, case, and_
import asyncio
import logging

class RankingViewModel:
    """ランキング関連のビジネスロジック"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # キャッシュ設定
        self.cache_expiry = 300  # 5分
        self.cached_rankings = {}
        self.cache_lock = asyncio.Lock()
        
        # 遅延初期化用の変数
        self._user_model = None
        self._season_model = None
    
    @property
    def user_model(self):
        """UserModelの遅延ロード"""
        if self._user_model is None:
            from models.user import UserModel
            self._user_model = UserModel()
        return self._user_model
    
    @property
    def season_model(self):
        """SeasonModelの遅延ロード"""
        if self._season_model is None:
            from models.season import SeasonModel
            self._season_model = SeasonModel()
        return self._season_model
    
    async def get_cached_ranking(self, ranking_type: str) -> List[Any]:
        """キャッシュからランキングを取得、期限切れの場合は再取得"""
        async with self.cache_lock:
            now = datetime.now()
            cache = self.cached_rankings.get(ranking_type)
            
            if cache and (now - cache['timestamp']).total_seconds() < self.cache_expiry:
                return cache['data']
            else:
                # キャッシュがないか期限切れの場合、データを再取得
                data = await self.fetch_ranking_data(ranking_type)
                self.cached_rankings[ranking_type] = {'data': data, 'timestamp': now}
                return data
    
    async def fetch_ranking_data(self, ranking_type: str) -> List[Any]:
        """ランキングデータを取得"""
        if ranking_type == "rating":
            return self.get_rating_ranking()
        elif ranking_type == "win_streak":
            return self.get_win_streak_ranking()
        elif ranking_type == "win_rate":
            return self.get_win_rate_ranking()
        else:
            return []
    
    def get_rating_ranking(self, limit: int = 100) -> List[Dict[str, Any]]:
        """レーティングランキングを取得"""
        try:
            from config.database import get_session, User
            session = get_session()
            
            # 効果的レートを計算
            effective_rating = case(
                (and_(User.stay_flag == 1, User.stayed_rating > User.rating), User.stayed_rating),
                else_=User.rating
            ).label('effective_rating')
            
            ranking = session.query(
                User.user_name,
                effective_rating,
                User.rating,
                User.stayed_rating,
                User.stay_flag
            ).filter(User.latest_season_matched == True)\
             .order_by(desc('effective_rating'))\
             .limit(limit).all()
            
            session.close()
            
            result = []
            for i, (user_name, effective_rating_value, rating_value, stayed_rating_value, stay_flag) in enumerate(ranking, 1):
                rounded_rating = round(effective_rating_value, 3)
                
                # 表示用レート情報
                if stay_flag == 1 and stayed_rating_value == effective_rating_value:
                    rate_display = f"{rounded_rating} (stayed)"
                else:
                    rate_display = f"{rounded_rating}"
                
                result.append({
                    'rank': i,
                    'user_name': user_name,
                    'rating': rounded_rating,
                    'rate_display': rate_display,
                    'is_stayed': stay_flag == 1 and stayed_rating_value == effective_rating_value
                })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting rating ranking: {e}")
            return []
    
    def get_win_streak_ranking(self, limit: int = 100) -> List[Dict[str, Any]]:
        """連勝数ランキングを取得"""
        try:
            from config.database import get_session, User
            session = get_session()
            
            ranking = session.query(User).filter(
                User.latest_season_matched == True
            ).order_by(desc(User.max_win_streak)).limit(limit).all()
            
            session.close()
            
            result = []
            for i, user in enumerate(ranking, 1):
                result.append({
                    'rank': i,
                    'user_name': user.user_name,
                    'max_win_streak': user.max_win_streak,
                    'current_win_streak': user.win_streak
                })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting win streak ranking: {e}")
            return []
    
    def get_win_rate_ranking(self, min_matches: int = 50, limit: int = 16) -> List[Dict[str, Any]]:
        """勝率ランキングを取得"""
        try:
            from config.database import get_session, User
            session = get_session()
            
            users = session.query(User).filter(User.latest_season_matched == True).all()
            session.close()
            
            ranking_with_win_rate = []
            
            for user in users:
                # current値
                current_total = user.total_matches or 0
                current_win = user.win_count or 0
                current_loss = user.loss_count or 0
                current_win_rate = (current_win / current_total) * 100 if current_total > 0 else 0.0
                
                # stayed値
                stayed_total = user.stayed_total_matches or 0
                stayed_win = user.stayed_win_count or 0
                stayed_loss = user.stayed_loss_count or 0
                stayed_win_rate = (stayed_win / stayed_total) * 100 if stayed_total > 0 else 0.0
                
                used_stayed = False
                effective_total = current_total
                effective_win = current_win
                effective_loss = current_loss
                effective_win_rate = current_win_rate
                
                # stay_flag == 0 → current のみ使用
                if user.stay_flag == 1:
                    if user.rating < user.stayed_rating:
                        # stayed側がcurrentより大きい場合 → stayedを優先
                        effective_total = stayed_total
                        effective_win = stayed_win
                        effective_loss = stayed_loss
                        effective_win_rate = stayed_win_rate
                        used_stayed = True
                
                # 最小試合数以上のもののみランキング対象
                if effective_total >= min_matches:
                    ranking_with_win_rate.append({
                        'user': user,
                        'win_rate': effective_win_rate,
                        'win_count': effective_win,
                        'loss_count': effective_loss,
                        'total_matches': effective_total,
                        'used_stayed': used_stayed
                    })
            
            # 勝率の降順で並べて上位を取得
            ranking_with_win_rate.sort(key=lambda x: x['win_rate'], reverse=True)
            
            result = []
            for i, data in enumerate(ranking_with_win_rate[:limit], 1):
                result.append({
                    'rank': i,
                    'user_name': data['user'].user_name,
                    'win_rate': data['win_rate'],
                    'win_count': data['win_count'],
                    'loss_count': data['loss_count'],
                    'total_matches': data['total_matches'],
                    'used_stayed': data['used_stayed']
                })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting win rate ranking: {e}")
            return []
    
    def get_past_season_rating_ranking(self, season_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """過去シーズンのレーティングランキングを取得"""
        try:
            season_records = self.season_model.get_season_rankings(season_id, limit)
            
            result = []
            for i, record in enumerate(season_records, 1):
                user = self.user_model.get_user_by_id(record.user_id)
                if user:
                    result.append({
                        'rank': i,
                        'user_name': user.user_name,
                        'rating': int(record.rating),
                        'win_count': record.win_count,
                        'loss_count': record.loss_count,
                        'total_matches': record.total_matches
                    })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting past season rating ranking: {e}")
            return []
    
    def get_past_season_win_rate_ranking(self, season_id: int, min_matches: int = 50, limit: int = 16) -> List[Dict[str, Any]]:
        """過去シーズンの勝率ランキングを取得"""
        try:
            from config.database import get_session
            session = get_session()
            
            records = session.query(self.season_model.UserSeasonRecord).filter(
                and_(
                    self.season_model.UserSeasonRecord.season_id == season_id,
                    self.season_model.UserSeasonRecord.total_matches >= min_matches
                )
            ).all()
            
            session.close()
            
            # 勝率で並び替え
            ranking = sorted(
                records, 
                key=lambda r: (r.win_count / r.total_matches) * 100 if r.total_matches > 0 else 0, 
                reverse=True
            )[:limit]
            
            result = []
            for i, record in enumerate(ranking, 1):
                user = self.user_model.get_user_by_id(record.user_id)
                if user:
                    win_rate = (record.win_count / record.total_matches) * 100 if record.total_matches > 0 else 0
                    result.append({
                        'rank': i,
                        'user_name': user.user_name,
                        'win_rate': win_rate,
                        'win_count': record.win_count,
                        'loss_count': record.loss_count,
                        'total_matches': record.total_matches
                    })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting past season win rate ranking: {e}")
            return []
    
    def get_past_season_win_streak_ranking(self, season_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """過去シーズンの連勝数ランキングを取得"""
        try:
            from config.database import get_session
            session = get_session()
            
            records = session.query(self.season_model.UserSeasonRecord).filter_by(
                season_id=season_id
            ).order_by(desc(self.season_model.UserSeasonRecord.max_win_streak)).limit(limit).all()
            
            session.close()
            
            result = []
            for i, record in enumerate(records, 1):
                user = self.user_model.get_user_by_id(record.user_id)
                if user:
                    result.append({
                        'rank': i,
                        'user_name': user.user_name,
                        'max_win_streak': record.max_win_streak
                    })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting past season win streak ranking: {e}")
            return []
    
    def clear_cache(self):
        """キャッシュをクリア"""
        self.cached_rankings.clear()
        self.logger.info("Ranking cache cleared")
    
    def get_user_ranking_info(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """特定ユーザーのランキング情報を取得"""
        try:
            user = self.user_model.get_user_by_discord_id(discord_id)
            if not user or not user.latest_season_matched:
                return None
            
            # 現在の順位を取得
            rank = self.user_model.get_user_rank(discord_id)
            
            # 効果的レートを計算
            effective_rating = max(user.rating, user.stayed_rating or 0)
            
            return {
                'user_name': user.user_name,
                'rank': rank,
                'rating': user.rating,
                'effective_rating': effective_rating,
                'stay_flag': user.stay_flag,
                'win_count': user.win_count,
                'loss_count': user.loss_count,
                'total_matches': user.total_matches,
                'max_win_streak': user.max_win_streak,
                'current_win_streak': user.win_streak
            }
            
        except Exception as e:
            self.logger.error(f"Error getting user ranking info: {e}")
            return None