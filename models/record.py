"""
戦績データのモデル（前作データベース対応も含む）
"""
import logging
from typing import List, Dict, Optional, Any
from sqlalchemy import text
from config.database import engine
from sqlalchemy.orm import sessionmaker

class RecordModel:
    """戦績データのモデル"""
    
    def __init__(self):
        self.engine = engine
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_user_current_season_record(self, discord_id: str) -> Optional[Dict]:
        """ユーザーの現在シーズン戦績を取得"""
        try:
            query = text("""
                SELECT 
                    u.user_name,
                    u.rating,
                    COUNT(m.id) as total_matches,
                    SUM(CASE WHEN 
                        (m.player1_id = u.id AND m.player1_wins > m.player2_wins) OR 
                        (m.player2_id = u.id AND m.player2_wins > m.player1_wins) 
                        THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN 
                        (m.player1_id = u.id AND m.player1_wins < m.player2_wins) OR 
                        (m.player2_id = u.id AND m.player2_wins < m.player1_wins) 
                        THEN 1 ELSE 0 END) as losses
                FROM beyond_users u
                LEFT JOIN beyond_matches m ON (u.id = m.player1_id OR u.id = m.player2_id)
                WHERE u.discord_id = :discord_id
                GROUP BY u.id, u.user_name, u.rating
            """)
            
            result = self.session.execute(query, {'discord_id': discord_id})
            row = result.fetchone()
            
            if row:
                total_matches = row[2] or 0
                wins = row[3] or 0
                losses = row[4] or 0
                win_rate = (wins / total_matches * 100) if total_matches > 0 else 0
                
                return {
                    'user_name': row[0],
                    'rating': row[1] or 1500,
                    'total_matches': total_matches,
                    'wins': wins,
                    'losses': losses,
                    'win_rate': win_rate
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting current season record for {discord_id}: {e}")
            return None
    
    def get_user_last_n_matches(self, discord_id: str, limit: int = 50) -> List[Dict]:
        """ユーザーの直近N戦の試合履歴を取得"""
        try:
            query = text("""
                SELECT 
                    m.match_date,
                    u1.user_name as player1_name,
                    u2.user_name as player2_name,
                    m.player1_wins,
                    m.player2_wins,
                    m.player1_rating_before,
                    m.player2_rating_before,
                    m.player1_rating_after,
                    m.player2_rating_after,
                    u.id as user_id,
                    m.player1_id,
                    m.player2_id
                FROM beyond_matches m
                JOIN beyond_users u1 ON m.player1_id = u1.id
                JOIN beyond_users u2 ON m.player2_id = u2.id
                JOIN beyond_users u ON u.discord_id = :discord_id
                WHERE (m.player1_id = u.id OR m.player2_id = u.id)
                ORDER BY m.match_date DESC
                LIMIT :limit
            """)
            
            result = self.session.execute(query, {
                'discord_id': discord_id,
                'limit': limit
            })
            
            matches = []
            for row in result:
                user_id = row[9]
                is_player1 = (user_id == row[10])
                
                if is_player1:
                    user_wins = row[3]
                    opponent_wins = row[4]
                    opponent_name = row[2]
                    rating_before = row[5]
                    rating_after = row[7]
                else:
                    user_wins = row[4]
                    opponent_wins = row[3]
                    opponent_name = row[1]
                    rating_before = row[6]
                    rating_after = row[8]
                
                result_text = "WIN" if user_wins > opponent_wins else "LOSS"
                rating_change = rating_after - rating_before
                
                matches.append({
                    'match_date': row[0],
                    'opponent_name': opponent_name,
                    'user_wins': user_wins,
                    'opponent_wins': opponent_wins,
                    'result': result_text,
                    'rating_change': rating_change,
                    'rating_before': rating_before,
                    'rating_after': rating_after
                })
            
            return matches
            
        except Exception as e:
            self.logger.error(f"Error getting last {limit} matches for {discord_id}: {e}")
            return []
    
    # ===== 前作データベース対応メソッド =====
    
    def get_legacy_seasons(self) -> List[Dict]:
        """前作の全シーズンを取得（seasonテーブル）"""
        try:
            query = text("""
                SELECT id, season_name, start_date, end_date
                FROM season
                ORDER BY start_date DESC
            """)
            result = self.session.execute(query)
            seasons = []
            for row in result:
                seasons.append({
                    'id': row[0],
                    'season_name': row[1],
                    'start_date': row[2],
                    'end_date': row[3]
                })
            return seasons
        except Exception as e:
            self.logger.error(f"Error getting legacy seasons: {e}")
            return []
    
    def get_legacy_season_ranking(self, season_id: int, limit: int = 100) -> List[Dict]:
        """前作の指定シーズンランキングを取得（user_season_recordテーブル）"""
        try:
            query = text("""
                SELECT 
                    usr.user_id,
                    usr.rating,
                    usr.total_matches,
                    usr.win_count,
                    usr.loss_count,
                    CASE WHEN usr.total_matches > 0 
                         THEN ROUND((CAST(usr.win_count AS FLOAT) / usr.total_matches) * 100, 1)
                         ELSE 0 END as win_rate,
                    usr.rank
                FROM user_season_record usr
                WHERE usr.season_id = :season_id
                  AND usr.total_matches >= 5
                ORDER BY usr.rating DESC
                LIMIT :limit
            """)
            
            result = self.session.execute(query, {
                'season_id': season_id,
                'limit': limit
            })
            
            ranking = []
            # ユーザー名を取得するため、beyond_userテーブルを参照
            for i, row in enumerate(result, 1):
                user_query = text("SELECT user_name FROM beyond_user WHERE id = :user_id")
                user_result = self.session.execute(user_query, {'user_id': row[0]})
                user_row = user_result.fetchone()
                user_name = user_row[0] if user_row else "Unknown"
                
                ranking.append({
                    'rank': i,  # 実際の順位で上書き
                    'user_name': user_name,
                    'user_id': row[0],
                    'rating': row[1],
                    'total_matches': row[2],
                    'wins': row[3],
                    'losses': row[4],
                    'win_rate': row[5]
                })
            
            return ranking
            
        except Exception as e:
            self.logger.error(f"Error getting legacy season ranking for season {season_id}: {e}")
            return []
    
    def get_legacy_user_season_records(self, discord_id: str) -> List[Dict]:
        """前作のユーザー全シーズン戦績を取得（user_season_recordテーブル）"""
        try:
            # まず beyond_user テーブルからuser_idを取得
            user_query = text("SELECT id, user_name FROM beyond_user WHERE discord_id = :discord_id")
            user_result = self.session.execute(user_query, {'discord_id': discord_id})
            user_row = user_result.fetchone()
            
            if not user_row:
                return []
            
            user_id = user_row[0]
            user_name = user_row[1]
            
            # user_season_record から前作の戦績を取得
            query = text("""
                SELECT 
                    usr.rating,
                    usr.total_matches,
                    usr.win_count,
                    usr.loss_count,
                    CASE WHEN usr.total_matches > 0 
                         THEN ROUND((CAST(usr.win_count AS FLOAT) / usr.total_matches) * 100, 1)
                         ELSE 0 END as win_rate,
                    usr.season_id,
                    s.season_name,
                    s.start_date,
                    s.end_date,
                    usr.rank
                FROM user_season_record usr
                JOIN season s ON usr.season_id = s.id
                WHERE usr.user_id = :user_id
                ORDER BY s.start_date DESC
            """)
            
            result = self.session.execute(query, {'user_id': user_id})
            
            records = []
            for row in result:
                records.append({
                    'user_name': user_name,
                    'rating': row[0],
                    'total_matches': row[1],
                    'wins': row[2],
                    'losses': row[3],
                    'win_rate': row[4],
                    'season_id': row[5],
                    'season_name': row[6],
                    'start_date': row[7],
                    'end_date': row[8],
                    'rank': row[9]
                })
            
            return records
            
        except Exception as e:
            self.logger.error(f"Error getting legacy user season records for {discord_id}: {e}")
            return []