"""
戦績関連のViewModel（前作データベース対応も含む）
"""
import logging
from typing import List, Dict, Optional, Tuple
from models.record import RecordModel

class RecordViewModel:
    """戦績関連のViewModel"""
    
    def __init__(self):
        self.record_model = RecordModel()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_current_season_record(self, discord_id: str) -> Optional[Dict]:
        """現在シーズンの戦績を取得"""
        try:
            return self.record_model.get_user_current_season_record(discord_id)
        except Exception as e:
            self.logger.error(f"Error getting current season record: {e}")
            return None
    
    def get_last_n_matches(self, discord_id: str, limit: int = 50) -> List[Dict]:
        """直近N戦の試合履歴を取得"""
        try:
            return self.record_model.get_user_last_n_matches(discord_id, limit)
        except Exception as e:
            self.logger.error(f"Error getting last {limit} matches: {e}")
            return []
    
    def format_current_season_record_message(self, record: Dict) -> str:
        """現在シーズンの戦績メッセージをフォーマット"""
        try:
            if not record:
                return "現在シーズンの戦績が見つかりませんでした。"
            
            win_rate = f"{record['win_rate']:.1f}%"
            message = f"**{record['user_name']}さんの現在シーズン戦績**\n\n"
            message += f"現在レート: {record['rating']:.0f}\n"
            message += f"戦績: {record['wins']}勝{record['losses']}敗 ({win_rate})\n"
            message += f"総試合数: {record['total_matches']}戦"
            
            return message
            
        except Exception as e:
            self.logger.error(f"Error formatting current season record message: {e}")
            return "戦績表示でエラーが発生しました。"
    
    def format_last_matches_message(self, matches: List[Dict], user_name: str, limit: int) -> str:
        """直近試合履歴メッセージをフォーマット"""
        try:
            if not matches:
                return f"**{user_name}さんの直近{limit}戦**\n\n試合履歴が見つかりませんでした。"
            
            message = f"**{user_name}さんの直近{len(matches)}戦**\n\n"
            
            for i, match in enumerate(matches[:10], 1):  # 最初の10件のみ表示
                result_emoji = "🟢" if match['result'] == 'WIN' else "🔴"
                rating_change = match['rating_change']
                change_sign = "+" if rating_change > 0 else ""
                
                message += f"{i}. {result_emoji} vs {match['opponent_name']} "
                message += f"({match['user_wins']}-{match['opponent_wins']}) "
                message += f"[{change_sign}{rating_change:.0f}]\n"
            
            if len(matches) > 10:
                message += f"\n... 他 {len(matches) - 10} 件の試合"
            
            return message
            
        except Exception as e:
            self.logger.error(f"Error formatting last matches message: {e}")
            return "試合履歴表示でエラーが発生しました。"

    # ===== 前作データベース対応メソッド =====
    
    def get_legacy_available_seasons(self) -> List[Dict]:
        """前作の利用可能なシーズン一覧を取得（seasonテーブル）"""
        try:
            return self.record_model.get_legacy_seasons()
        except Exception as e:
            self.logger.error(f"Error getting legacy available seasons: {e}")
            return []
    
    def get_legacy_season_ranking(self, season_id: int, page: int = 1, per_page: int = 100) -> Tuple[List[Dict], Dict]:
        """前作の指定シーズンランキングを取得（user_season_recordテーブル）"""
        try:
            # 前作ランキングは基本的にTOP100一括表示
            ranking = self.record_model.get_legacy_season_ranking(season_id, limit=100)
            
            # ページング情報（前作では基本的に不要だが、形式を合わせる）
            pagination_info = {
                'current_page': 1,
                'total_pages': 1,
                'total_users': len(ranking),
                'per_page': 100,
                'has_next': False,
                'has_prev': False
            }
            
            return ranking, pagination_info
            
        except Exception as e:
            self.logger.error(f"Error getting legacy season ranking for season {season_id}: {e}")
            return [], {'current_page': 1, 'total_pages': 1, 'total_users': 0, 'per_page': 100, 'has_next': False, 'has_prev': False}
    
    def get_legacy_user_season_records(self, discord_id: str) -> List[Dict]:
        """前作のユーザー全シーズン戦績を取得（user_season_recordテーブル）"""
        try:
            return self.record_model.get_legacy_user_season_records(discord_id)
        except Exception as e:
            self.logger.error(f"Error getting legacy user season records: {e}")
            return []
    
    def format_legacy_ranking_message(self, ranking: List[Dict], season_info: Dict) -> str:
        """前作ランキングメッセージをフォーマット"""
        try:
            if not ranking:
                return f"**{season_info.get('season_name', 'Unknown Season')}**\n\nランキングデータがありません。"
            
            message = f"**{season_info.get('season_name', 'Unknown Season')} ランキング TOP100**\n\n"
            
            for user in ranking:
                win_rate = f"{user['win_rate']:.1f}%" if user['win_rate'] is not None else "0.0%"
                message += f"**{user['rank']}位** {user['user_name']}\n"
                message += f"レート: {user['rating']:.0f} | 戦績: {user['wins']}勝{user['losses']}敗 ({win_rate})\n\n"
            
            return message
            
        except Exception as e:
            self.logger.error(f"Error formatting legacy ranking message: {e}")
            return "ランキング表示でエラーが発生しました。"
    
    def format_legacy_season_records_message(self, records: List[Dict], user_name: str) -> str:
        """前作シーズン戦績一覧メッセージをフォーマット"""
        try:
            if not records:
                return f"**{user_name}さんの前作シーズン戦績**\n\n前作のシーズン戦績が見つかりませんでした。"
            
            message = f"**{user_name}さんの前作シーズン戦績**\n\n"
            
            for record in records:
                win_rate = f"{record['win_rate']:.1f}%" if record['win_rate'] is not None else "0.0%"
                rank_text = f"{record['rank']}位" if record.get('rank') else "順位不明"
                message += f"**{record['season_name']}**\n"
                message += f"最終レート: {record['rating']:.0f} ({rank_text})\n"
                message += f"戦績: {record['wins']}勝{record['losses']}敗 ({win_rate})\n"
                message += f"総試合数: {record['total_matches']}戦\n\n"
            
            return message
            
        except Exception as e:
            self.logger.error(f"Error formatting legacy season records message: {e}")
            return "戦績表示でエラーが発生しました。"