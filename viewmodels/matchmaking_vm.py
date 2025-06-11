import asyncio
import heapq
import random
from typing import List, Tuple, Dict, Optional
from datetime import datetime, timedelta
from config.database import get_session, User
from models.user import UserModel
from models.season import SeasonModel
from models.match import MatchModel
from config.settings import MAX_RATING_DIFF_FOR_MATCH, MATCHMAKING_TIMEOUT, BASE_RATING_CHANGE, RATING_DIFF_MULTIPLIER
import logging

def calculate_rating_change(player_rating: float, opponent_rating: float, 
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

class MatchmakingViewModel:
    """マッチング関連のビジネスロジック"""
    
    def __init__(self):
        self.user_model = UserModel()
        self.season_model = SeasonModel()
        self.match_model = MatchModel()
        self.waiting_queue = []  # (rating, user_id, user_discord_object)
        self.match_lock = asyncio.Lock()
        self.previous_opponents = {}  # 連続マッチ防止
        self.user_interactions = {}  # ユーザーのインタラクションを保存
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # バックグラウンドタスク
        self.background_task = None
        self.request_queue = asyncio.Queue()
        self.processing_task = None
        
        # マッチ作成時のコールバック（bot_configから設定される）
        self.match_creation_callback = None
        
        self.logger.info("🏗️ MatchmakingViewModel initialized")
        
    def set_match_creation_callback(self, callback):
        """マッチ作成時のコールバックを設定"""
        self.match_creation_callback = callback
        self.logger.info(f"🔗 Match creation callback set: {callback.__name__ if hasattr(callback, '__name__') else str(callback)}")
    
    def set_match_creation_callback(self, callback):
        """マッチ作成時のコールバックを設定"""
        self.match_creation_callback = callback
        self.logger.info(f"🔗 Match creation callback set: {callback.__name__ if hasattr(callback, '__name__') else str(callback)}")
    
    def get_match_creation_callback(self):
        """現在のコールバックを取得（デバッグ用）"""
        return self.match_creation_callback
    
    def start_background_tasks(self):
        """バックグラウンドタスクを開始"""
        try:
            if not self.background_task or self.background_task.done():
                self.background_task = asyncio.create_task(self.background_match_check())
                self.logger.info("🚀 Background match check task started")
            else:
                self.logger.warning("⚠️ Background match check task already running")
                
            if not self.processing_task or self.processing_task.done():
                self.processing_task = asyncio.create_task(self.process_queue())
                self.logger.info("🚀 Request processing task started")
            else:
                self.logger.warning("⚠️ Request processing task already running")
                
            # コールバックが設定されているかチェック
            if self.match_creation_callback:
                self.logger.info("✅ Match creation callback is set")
            else:
                self.logger.warning("⚠️ Match creation callback is NOT set - matches will not be processed!")
                
            # タスク開始の確認
            asyncio.create_task(self._verify_tasks_running())
            
        except Exception as e:
            self.logger.error(f"❌ Error starting background tasks: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    async def _verify_tasks_running(self):
        """タスクが実際に動作しているか確認"""
        await asyncio.sleep(1)  # 少し待ってから確認
        
        bg_status = "RUNNING" if self.background_task and not self.background_task.done() else "NOT RUNNING"
        proc_status = "RUNNING" if self.processing_task and not self.processing_task.done() else "NOT RUNNING"
        
        self.logger.info(f"📊 Task Status Check - Background: {bg_status}, Processing: {proc_status}")
        
        if self.background_task and self.background_task.done():
            try:
                # タスクが終了している場合、例外をチェック
                exception = self.background_task.exception()
                if exception:
                    self.logger.error(f"❌ Background task failed with exception: {exception}")
            except Exception as e:
                self.logger.error(f"❌ Error checking background task exception: {e}")
    
    def stop_background_tasks(self):
        """バックグラウンドタスクを停止"""
        if self.background_task:
            self.background_task.cancel()
            self.background_task = None
        if self.processing_task:
            self.processing_task.cancel()
            self.processing_task = None
    
    async def process_queue(self):
        """リクエストキューを処理"""
        while True:
            try:
                batch_requests = []
                while not self.request_queue.empty():
                    batch_requests.append(await self.request_queue.get())
                
                if batch_requests:
                    await asyncio.gather(*(request() for request in batch_requests))
                
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in process_queue: {e}")
    
    async def add_to_waiting_list(self, user, interaction) -> Tuple[bool, str]:
        """ユーザーを待機リストに追加"""
        try:
            # ランダム遅延
            delay = random.uniform(0.1, 0.5)
            await asyncio.sleep(delay)
            
            # ユーザーデータの取得 - FIX: str(user.id)に変更
            user_data = self.user_model.get_user_by_discord_id(str(user.id))
            if not user_data:
                self.logger.warning(f"User {user.display_name} ({user.id}) not found in database")
                return False, "ユーザー登録を行ってください。"
            
            # ユーザーデータの型をログで確認
            self.logger.debug(f"🔍 User data type: {type(user_data)}, data: {user_data}")
            
            # user_dataが辞書かオブジェクトかを判定して適切にアクセス
            def get_attr(data, attr_name, default=None):
                if isinstance(data, dict):
                    return data.get(attr_name, default)
                else:
                    return getattr(data, attr_name, default)
            
            user_name = get_attr(user_data, 'user_name', 'Unknown')
            
            # シーズン期間チェック
            if not self.season_model.is_season_active():
                self.logger.warning(f"User {user_name} ({user.display_name}) tried to join queue but season is not active")
                return False, "シーズン期間外です。"
            
            # クラス設定チェック
            class1 = get_attr(user_data, 'class1')
            class2 = get_attr(user_data, 'class2')
            
            if not class1 or not class2:
                self.logger.warning(f"User {user_name} ({user.display_name}) classes not set: class1={class1}, class2={class2}")
                return False, "クラスを選択してください。"
            
            # レーティング取得
            rating = get_attr(user_data, 'rating')
            user_rating = rating if rating is not None else 1500
            
            async with self.match_lock:
                # 重複チェック
                if any(queued_user.id == user.id for _, _, queued_user in self.waiting_queue):
                    self.logger.info(f"User {user_name} ({user.display_name}) already in waiting list")
                    return False, "既に待機リストにいます。"
                
                # データベースIDを取得
                db_id = get_attr(user_data, 'id', 0)
                
                heapq.heappush(self.waiting_queue, (user_rating, db_id, user))
                self.user_interactions[user.id] = interaction
                
                self.logger.info(f"★ User {user_name} ({user.display_name}) added to waiting list with rating {user_rating}. Queue size: {len(self.waiting_queue)}")
            
            # タイムアウト後の削除をスケジュール
            asyncio.create_task(self.remove_user_after_timeout(user))
            
            return True, "待機リストに追加されました。"
            
        except Exception as e:
            self.logger.error(f"Error in add_to_waiting_list for user {user.display_name}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False, "エラーが発生しました。"
    
    async def remove_user_after_timeout(self, user):
        """タイムアウト後にユーザーを待機リストから削除"""
        await asyncio.sleep(MATCHMAKING_TIMEOUT)
        
        async with self.match_lock:
            for i, (_, _, queued_user) in enumerate(self.waiting_queue):
                if queued_user.id == user.id:
                    del self.waiting_queue[i]
                    heapq.heapify(self.waiting_queue)
                    
                    self.logger.info(f"⏰ User {user.display_name} removed from waiting list due to timeout")
                    
                    # インタラクションに通知
                    interaction = self.user_interactions.get(user.id)
                    if interaction:
                        try:
                            await interaction.followup.send("マッチング相手が見つかりませんでした。", ephemeral=True)
                        except Exception as e:
                            self.logger.error(f"Failed to send timeout message to {user.display_name}: {e}")
                        finally:
                            del self.user_interactions[user.id]
                    
                    break
    
    async def background_match_check(self):
        """定期的にマッチングをチェック"""
        self.logger.info("🔄 Background match check task started and running")
        check_count = 0
        while True:
            try:
                check_count += 1
                await asyncio.sleep(0.5)  # 0.5秒間隔でチェック
                
                # 詳細ログは10回に1回出力（約5秒間隔）
                if check_count % 10 == 0:
                    queue_size = len(self.waiting_queue)
                    if queue_size > 0:
                        self.logger.info(f"🔍 Background check #{check_count}: {queue_size} users in queue")
                        
                        # user_dataが辞書かオブジェクトかを判定して適切にアクセス
                        def get_attr(data, attr_name, default=None):
                            if isinstance(data, dict):
                                return data.get(attr_name, default)
                            else:
                                return getattr(data, attr_name, default)
                        
                        # 待機中のユーザー名をログ出力
                        user_names = []
                        for rating, db_id, user in self.waiting_queue:
                            user_data = self.user_model.get_user_by_discord_id(str(user.id))
                            user_name = get_attr(user_data, 'user_name', user.display_name) if user_data else user.display_name
                            user_names.append(f"{user_name}({rating:.0f})")
                        self.logger.info(f"  📋 Queue contents: {', '.join(user_names)}")
                    else:
                        # キューが空の場合も定期的にログ出力
                        if check_count % 100 == 0:  # 50秒に1回
                            self.logger.debug(f"🔍 Background check #{check_count}: Queue is empty")
                
                # マッチングを試行
                matches = await self.find_and_create_matches()
                
                # マッチが見つかった場合の処理
                if matches:
                    if self.match_creation_callback:
                        self.logger.info(f"🎯 Found {len(matches)} matches!")
                        for user1, user2 in matches:
                            self.logger.info(f"  ⚔️ Creating match: {user1.display_name} vs {user2.display_name}")
                            try:
                                asyncio.create_task(self.match_creation_callback(user1, user2))
                            except Exception as e:
                                self.logger.error(f"❌ Error creating match task: {e}")
                    else:
                        self.logger.error(f"❌ Found {len(matches)} matches but no callback set!")
                        
            except asyncio.CancelledError:
                self.logger.info("🛑 Background match check task cancelled")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in background_match_check: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                # エラーが発生してもタスクを続行
                await asyncio.sleep(1)
    
    async def find_and_create_matches(self) -> List[Tuple]:
        """マッチングを検索して作成"""
        matches = []
        
        async with self.match_lock:
            matched_users_ids = set()
            queue_copy = list(self.waiting_queue)
            
            if len(queue_copy) < 2:
                return matches  # 2人未満の場合は早期リターン
            
            self.logger.debug(f"🔍 Checking for matches in queue of {len(queue_copy)} users")
            
            for i in range(len(queue_copy) - 1):
                user1_rating, user1_db_id, user1 = queue_copy[i]
                if user1.id in matched_users_ids:
                    continue
                
                # 試合中ロールを持つユーザーを削除
                if self._user_has_battle_role(user1):
                    self.logger.info(f"🚫 Removing {user1.display_name} from queue (has battle role)")
                    self._remove_user_from_queue(user1.id)
                    continue
                
                self.logger.debug(f"🔍 Checking user1: {user1.display_name} (rating: {user1_rating})")
                
                for j in range(i + 1, len(queue_copy)):
                    user2_rating, user2_db_id, user2 = queue_copy[j]
                    if user2.id in matched_users_ids or user1.id == user2.id:
                        continue
                    
                    self.logger.debug(f"  🔍 Against user2: {user2.display_name} (rating: {user2_rating})")
                    
                    # 試合中ロールを持つユーザーを削除
                    if self._user_has_battle_role(user2):
                        self.logger.info(f"🚫 Removing {user2.display_name} from queue (has battle role)")
                        self._remove_user_from_queue(user2.id)
                        continue
                    
                    # 連続マッチ防止
                    if self.previous_opponents.get(user1.id) == user2.id:
                        self.logger.debug(f"⏭️ Skipping consecutive match: {user1.display_name} vs {user2.display_name}")
                        continue
                    
                    # レーティング差チェック
                    rating_diff = abs(user1_rating - user2_rating)
                    self.logger.debug(f"📊 Rating check: {user1.display_name}({user1_rating:.0f}) vs {user2.display_name}({user2_rating:.0f}) = diff {rating_diff:.0f}")
                    
                    if rating_diff <= MAX_RATING_DIFF_FOR_MATCH:
                        matched_users_ids.update([user1.id, user2.id])
                        self.previous_opponents[user1.id] = user2.id
                        self.previous_opponents[user2.id] = user1.id
                        matches.append((user1, user2))
                        self.logger.info(f"✅ Match created: {user1.display_name} vs {user2.display_name} (rating diff: {rating_diff:.0f})")
                        break
                    else:
                        self.logger.debug(f"❌ Rating diff too large: {rating_diff:.0f} > {MAX_RATING_DIFF_FOR_MATCH}")
                
                # マッチが見つかった場合、次のユーザーへ
                if user1.id in matched_users_ids:
                    break
            
            if matches:
                self.logger.info(f"🎯 Total matches found: {len(matches)}")
            else:
                if len(queue_copy) >= 2:
                    self.logger.debug(f"❌ No matches found despite {len(queue_copy)} users in queue")
                    # なぜマッチしなかったかの詳細情報
                    for i, (rating1, _, user1) in enumerate(queue_copy):
                        for j, (rating2, _, user2) in enumerate(queue_copy[i+1:], i+1):
                            rating_diff = abs(rating1 - rating2)
                            consecutive = self.previous_opponents.get(user1.id) == user2.id
                            role1 = self._user_has_battle_role(user1)
                            role2 = self._user_has_battle_role(user2)
                            
                            reason = []
                            if rating_diff > MAX_RATING_DIFF_FOR_MATCH:
                                reason.append(f"rating_diff:{rating_diff:.0f}>{MAX_RATING_DIFF_FOR_MATCH}")
                            if consecutive:
                                reason.append("consecutive_match")
                            if role1:
                                reason.append(f"{user1.display_name}_has_battle_role")
                            if role2:
                                reason.append(f"{user2.display_name}_has_battle_role")
                            
                            if reason:
                                self.logger.debug(f"  🚫 {user1.display_name} vs {user2.display_name}: {', '.join(reason)}")
            
            # マッチしたユーザーを待機キューから削除
            original_queue_size = len(self.waiting_queue)
            self.waiting_queue = [
                (rating, id_, user) for rating, id_, user in self.waiting_queue 
                if user.id not in matched_users_ids
            ]
            heapq.heapify(self.waiting_queue)
            
            if matched_users_ids:
                self.logger.info(f"📝 Removed {len(matched_users_ids)} users from queue. Queue size: {original_queue_size} -> {len(self.waiting_queue)}")
            
            # マッチしたユーザーのインタラクションを削除
            for user1, user2 in matches:
                self.user_interactions.pop(user1.id, None)
                self.user_interactions.pop(user2.id, None)
        
        return matches
    
    def _user_has_battle_role(self, user) -> bool:
        """ユーザーが試合中ロールを持っているかチェック"""
        return "試合中" in [role.name for role in user.roles]
    
    def _remove_user_from_queue(self, user_id: int):
        """待機キューからユーザーを削除"""
        original_size = len(self.waiting_queue)
        self.waiting_queue = [
            (rating, id_, user) for rating, id_, user in self.waiting_queue 
            if user.id != user_id
        ]
        heapq.heapify(self.waiting_queue)
        new_size = len(self.waiting_queue)
        if original_size != new_size:
            self.logger.info(f"🗑️ Removed user {user_id} from queue. Queue size: {original_size} -> {new_size}")
        else:
            self.logger.warning(f"⚠️ Tried to remove user {user_id} but not found in queue")
    
    async def create_match_data(self, user1, user2) -> Dict[str, any]:
        """マッチデータを作成"""
        user1_data = self.user_model.get_user_by_discord_id(str(user1.id))  # FIX: str()追加
        user2_data = self.user_model.get_user_by_discord_id(str(user2.id))  # FIX: str()追加
        
        if not user1_data or not user2_data:
            raise ValueError("User data not found")
        
        # user_dataが辞書かオブジェクトかを判定して適切にアクセス
        def get_attr(data, attr_name, default=None):
            if isinstance(data, dict):
                return data.get(attr_name, default)
            else:
                return getattr(data, attr_name, default)
        
        current_season_name = self.season_model.get_current_season_name()
        
        # マッチングプレースホルダーを作成
        match_record = self.match_model.create_match_placeholder(
            get_attr(user1_data, 'id'), 
            get_attr(user2_data, 'id'), 
            current_season_name,
            get_attr(user1_data, 'class1'), 
            get_attr(user1_data, 'class2'),
            get_attr(user2_data, 'class1'), 
            get_attr(user2_data, 'class2'),
            get_attr(user1_data, 'rating', 1500), 
            get_attr(user2_data, 'rating', 1500)
        )
        
        return {
            'user1_data': user1_data,
            'user2_data': user2_data,
            'matching_classes': {
                user1.id: (get_attr(user1_data, 'class1'), get_attr(user1_data, 'class2')),
                user2.id: (get_attr(user2_data, 'class1'), get_attr(user2_data, 'class2'))
            },
            'season_name': current_season_name,
            'match_record': match_record
        }
    
    def get_waiting_count(self) -> int:
        """待機中のユーザー数を取得"""
        return len(self.waiting_queue)
    
    def get_waiting_users(self) -> List[Dict[str, any]]:
        """待機中のユーザー情報を取得"""
        result = []
        
        # user_dataが辞書かオブジェクトかを判定して適切にアクセス
        def get_attr(data, attr_name, default=None):
            if isinstance(data, dict):
                return data.get(attr_name, default)
            else:
                return getattr(data, attr_name, default)
        
        for rating, db_id, user in self.waiting_queue:
            # データベースからユーザー名を取得
            user_data = self.user_model.get_user_by_discord_id(str(user.id))
            user_name = get_attr(user_data, 'user_name', 'Unknown') if user_data else 'Unknown'
            
            result.append({
                'user_id': user.id,
                'display_name': user.display_name,
                'user_name': user_name,
                'rating': rating,
                'db_id': db_id,
                'has_battle_role': self._user_has_battle_role(user),
                'wait_time': None  # 実装が必要であれば追加
            })
        return result

class ResultViewModel:
    """試合結果処理のビジネスロジック"""
    
    def __init__(self):
        self.user_model = UserModel()
        self.match_model = MatchModel()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def validate_result(self, player1_wins: int, player2_wins: int) -> Tuple[bool, str]:
        """試合結果の妥当性をチェック"""
        if not (0 <= player1_wins <= 2 and 0 <= player2_wins <= 2):
            return False, "勝利数は0から2の間で入力してください。"
        
        total_wins = player1_wins + player2_wins
        if total_wins not in [2, 3]:
            return False, "勝利数の合計が正しくありません。"
        
        if player1_wins == player2_wins:
            return False, "引き分けは無効です。"
        
        return True, "OK"
    
    def calculate_rating_changes(self, user1_rating: float, user2_rating: float, 
                                user1_wins: int, user2_wins: int) -> Tuple[float, float]:
        """レーティング変動を計算"""
        user1_change = calculate_rating_change(user1_rating, user2_rating, user1_wins, user2_wins)
        user2_change = calculate_rating_change(user2_rating, user1_rating, user2_wins, user1_wins)
        
        return user1_change, user2_change
    
    def update_user_stats(self, user1_id: int, user2_id: int, 
                         user1_wins: int, user2_wins: int,
                         user1_rating_change: float, user2_rating_change: float) -> bool:
        """ユーザーの統計を更新"""
        try:
            from config.database import get_session
            session = get_session()
            
            user1 = session.query(User).filter_by(id=user1_id).first()
            user2 = session.query(User).filter_by(id=user2_id).first()
            
            if not user1 or not user2:
                session.close()
                return False
            
            # レーティング更新
            user1.rating += user1_rating_change
            user2.rating += user2_rating_change
            
            # 試合数更新
            user1.total_matches += 1
            user2.total_matches += 1
            
            # 勝敗数更新
            if user1_wins > user2_wins:
                user1.win_count += 1
                user2.loss_count += 1
                # 連勝数更新
                user1.win_streak += 1
                user2.win_streak = 0
                user1.max_win_streak = max(user1.max_win_streak, user1.win_streak)
            else:
                user2.win_count += 1
                user1.loss_count += 1
                # 連勝数更新
                user2.win_streak += 1
                user1.win_streak = 0
                user2.max_win_streak = max(user2.max_win_streak, user2.win_streak)
            
            # 最新シーズンマッチフラグ
            user1.latest_season_matched = True
            user2.latest_season_matched = True
            
            session.commit()
            session.close()
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating user stats: {e}")
            if 'session' in locals():
                session.rollback()
                session.close()
            return False
    
    def finalize_match(self, user1_id: int, user2_id: int, user1_wins: int, user2_wins: int,
                      before_user1_rating: float, before_user2_rating: float) -> Dict[str, any]:
        """試合を確定"""
        try:
            # 結果の妥当性チェック
            is_valid, message = self.validate_result(user1_wins, user2_wins)
            if not is_valid:
                return {'success': False, 'message': message}
            
            # レーティング変動を計算
            user1_change, user2_change = self.calculate_rating_changes(
                before_user1_rating, before_user2_rating, user1_wins, user2_wins
            )
            
            after_user1_rating = before_user1_rating + user1_change
            after_user2_rating = before_user2_rating + user2_change
            
            # 試合記録を確定
            match_record = self.match_model.finalize_match_result(
                user1_id, user2_id, user1_wins, user2_wins,
                before_user1_rating, before_user2_rating,
                after_user1_rating, after_user2_rating
            )
            
            # ユーザー統計を更新
            success = self.update_user_stats(
                user1_id, user2_id, user1_wins, user2_wins,
                user1_change, user2_change
            )
            
            return {
                'success': True,
                'user1_rating_change': user1_change,
                'user2_rating_change': user2_change,
                'after_user1_rating': after_user1_rating,
                'after_user2_rating': after_user2_rating,
                'match_record': match_record
            }
            
        except Exception as e:
            self.logger.error(f"Error finalizing match: {e}")
            return {'success': False, 'message': 'エラーが発生しました。'}

class CancelViewModel:
    """試合中止処理のビジネスロジック"""
    
    def __init__(self):
        self.user_model = UserModel()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def process_cancel_request(self, requesting_user_id: int, opponent_user_id: int) -> Dict[str, any]:
        """中止リクエストを処理"""
        try:
            # 信用ポイントの調整などがあれば実装
            # 現在は基本的な情報を返すのみ
            
            return {
                'success': True,
                'requesting_user_id': requesting_user_id,
                'opponent_user_id': opponent_user_id,
                'message': 'キャンセルリクエストが送信されました。'
            }
            
        except Exception as e:
            self.logger.error(f"Error processing cancel request: {e}")
            return {'success': False, 'message': 'エラーが発生しました。'}
    
    def apply_timeout_penalty(self, user_id: int) -> bool:
        """タイムアウトペナルティを適用"""
        try:
            user = self.user_model.get_user_by_id(user_id)
            if user:
                # 信用ポイントを1減点
                self.user_model.update_trust_points(user.discord_id, -1)
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Error applying timeout penalty: {e}")
            return False