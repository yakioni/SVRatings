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
<<<<<<< HEAD
        """ユーザーの直近N戦の試合履歴を取得（BO1対応、クラス情報付き）"""
=======
        """ユーザーの直近N戦の試合履歴を取得"""
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
        try:
            # まずはbeyond_match_historyテーブルから試してみる
            query = text("""
                SELECT 
                    m.match_date,
                    CASE 
                        WHEN m.user1_id = u.id THEN u2.user_name
                        ELSE u1.user_name
                    END as opponent_name,
                    CASE 
                        WHEN m.user1_id = u.id THEN 
                            CASE WHEN m.winner_user_id = u.id THEN 1 ELSE 0 END
                        ELSE 
                            CASE WHEN m.winner_user_id = u.id THEN 1 ELSE 0 END
                    END as user_won,
                    m.before_user1_rating,
                    m.before_user2_rating,
                    m.after_user1_rating,
                    m.after_user2_rating,
                    m.user1_rating_change,
                    m.user2_rating_change,
                    u.id as user_id,
                    m.user1_id,
<<<<<<< HEAD
                    m.user2_id,
                    m.user1_selected_class,
                    m.user2_selected_class,
                    m.user1_class_a,
                    m.user1_class_b,
                    m.user2_class_a,
                    m.user2_class_b
=======
                    m.user2_id
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
                FROM beyond_match_history m
                JOIN beyond_user u1 ON m.user1_id = u1.id
                JOIN beyond_user u2 ON m.user2_id = u2.id
                JOIN beyond_user u ON u.discord_id = :discord_id
                WHERE (m.user1_id = u.id OR m.user2_id = u.id)
                    AND m.winner_user_id IS NOT NULL
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
                    rating_before = row[3]
                    rating_after = row[5]
                    rating_change = row[7]
<<<<<<< HEAD
                    # クラス情報を取得（新しいカラムを優先）
                    user_selected_class = row[12]  # user1_selected_class
                    opponent_selected_class = row[13]  # user2_selected_class
                    # 新しいカラムがNullの場合は古いカラムを使用
                    if not user_selected_class:
                        user_selected_class = row[14] or row[15]  # user1_class_a or user1_class_b
                    if not opponent_selected_class:
                        opponent_selected_class = row[16] or row[17]  # user2_class_a or user2_class_b
=======
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
                else:
                    rating_before = row[4]
                    rating_after = row[6]
                    rating_change = row[8]
<<<<<<< HEAD
                    # クラス情報を取得（新しいカラムを優先）
                    user_selected_class = row[13]  # user2_selected_class
                    opponent_selected_class = row[12]  # user1_selected_class
                    # 新しいカラムがNullの場合は古いカラムを使用
                    if not user_selected_class:
                        user_selected_class = row[16] or row[17]  # user2_class_a or user2_class_b
                    if not opponent_selected_class:
                        opponent_selected_class = row[14] or row[15]  # user1_class_a or user1_class_b
                
                result_text = "WIN" if row[2] == 1 else "LOSS"
                
                matches.append({
                    'match_date': row[0],
                    'opponent_name': row[1],
                    'result': result_text,
                    'rating_change': rating_change,
                    'rating_before': rating_before,
                    'rating_after': rating_after,
                    'user_class': user_selected_class or "不明",
                    'opponent_class': opponent_selected_class or "不明"
=======
                
                result_text = "WIN" if row[2] == 1 else "LOSS"
                
                # user_wins と opponent_wins を計算（簡略化）
                if row[2] == 1:  # ユーザーが勝利
                    user_wins = 2  # 仮の値
                    opponent_wins = 1
                else:  # ユーザーが敗北
                    user_wins = 1
                    opponent_wins = 2
                
                matches.append({
                    'match_date': row[0],
                    'opponent_name': row[1],
                    'user_wins': user_wins,
                    'opponent_wins': opponent_wins,
                    'result': result_text,
                    'rating_change': rating_change,
                    'rating_before': rating_before,
                    'rating_after': rating_after
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
                })
            
            return matches
            
        except Exception as e:
            self.logger.error(f"Error getting last {limit} matches for {discord_id}: {e}")
            # fallback to old table structure
            return self._get_user_last_n_matches_legacy(discord_id, limit)
    
    def _get_user_last_n_matches_legacy(self, discord_id: str, limit: int = 50) -> List[Dict]:
        """ユーザーの直近N戦の試合履歴を取得（旧テーブル構造）"""
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
<<<<<<< HEAD
                    m.player2_id,
                    m.player1_class_a,
                    m.player1_class_b,
                    m.player2_class_a,
                    m.player2_class_b
=======
                    m.player2_id
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
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
<<<<<<< HEAD
                    # 旧形式では使用クラスは不明
                    user_class = row[12] or row[13] or "不明"  # player1_class_a or player1_class_b
                    opponent_class = row[14] or row[15] or "不明"  # player2_class_a or player2_class_b
=======
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
                else:
                    user_wins = row[4]
                    opponent_wins = row[3]
                    opponent_name = row[1]
                    rating_before = row[6]
                    rating_after = row[8]
<<<<<<< HEAD
                    # 旧形式では使用クラスは不明
                    user_class = row[14] or row[15] or "不明"  # player2_class_a or player2_class_b
                    opponent_class = row[12] or row[13] or "不明"  # player1_class_a or player1_class_b
=======
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
                
                result_text = "WIN" if user_wins > opponent_wins else "LOSS"
                rating_change = rating_after - rating_before
                
                matches.append({
                    'match_date': row[0],
                    'opponent_name': opponent_name,
<<<<<<< HEAD
                    'result': result_text,
                    'rating_change': rating_change,
                    'rating_before': rating_before,
                    'rating_after': rating_after,
                    'user_class': user_class,
                    'opponent_class': opponent_class
=======
                    'user_wins': user_wins,
                    'opponent_wins': opponent_wins,
                    'result': result_text,
                    'rating_change': rating_change,
                    'rating_before': rating_before,
                    'rating_after': rating_after
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
                })
            
            return matches
            
        except Exception as e:
            self.logger.error(f"Error getting last {limit} matches (legacy) for {discord_id}: {e}")
            return []
    
    def close_session(self):
        """セッションを閉じる"""
        try:
            self.session.close()
        except Exception as e:
            self.logger.error(f"Error closing session: {e}")
    
    def __del__(self):
        """デストラクタでセッションを閉じる"""
        self.close_session()