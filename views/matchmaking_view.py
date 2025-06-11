import discord
from discord.ui import View, Button, Select
from discord.ext import commands
import asyncio
from typing import Dict, Any, Optional
from viewmodels.matchmaking_vm import MatchmakingViewModel, ResultViewModel, CancelViewModel
from config.settings import BATTLE_CHANNEL_ID, RESULT_REPORT_TIMEOUT, THREAD_DELETE_DELAY
from utils.helpers import safe_create_thread, safe_add_user_to_thread, safe_send_message
from utils.helpers import assign_role, remove_role
import logging

class MatchmakingView(View):
    """マッチング待機ボタンを含むView"""
    
    def __init__(self, viewmodel: MatchmakingViewModel):
        super().__init__(timeout=None)
        self.viewmodel = viewmodel
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="マッチング待機", style=discord.ButtonStyle.primary)
    async def start_matching(self, button: Button, interaction: discord.Interaction):
        """マッチング待機ボタンの処理"""
        user = interaction.user
        await interaction.response.defer(ephemeral=True)
        
        # 試合中ロールチェック
        role_name = "試合中"
        active_role = discord.utils.get(user.roles, name=role_name)
        if active_role:
            message = await interaction.followup.send(
                f"{user.mention} 現在試合中のため、マッチング待機リストに入ることができません。", 
                ephemeral=True
            )
            asyncio.create_task(self._delete_message_after_delay(message, 60))
            return
        
        # ViewModelに処理を委譲
        success, message = await self.viewmodel.add_to_waiting_list(user, interaction)
        
        response_message = await interaction.followup.send(
            f"{user.mention} {message}", ephemeral=True
        )
        asyncio.create_task(self._delete_message_after_delay(response_message, 60))
    
    async def _delete_message_after_delay(self, message, delay: int):
        """指定時間後にメッセージを削除"""
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except (discord.errors.NotFound, discord.errors.Forbidden):
            pass
        except Exception as e:
            self.logger.error(f"Failed to delete message: {e}")

class ClassSelectView(View):
    """クラス選択用のView"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ClassSelect())

class ClassSelect(Select):
    """クラス選択のSelectメニュー"""
    
    def __init__(self):
        from models.user import UserModel
        user_model = UserModel()
        valid_classes = user_model.get_valid_classes()
        
        options = [
            discord.SelectOption(label=cls, value=f"{cls}_{i}") 
            for i, cls in enumerate(valid_classes)
        ]
        
        super().__init__(
            placeholder="Select your classes...", 
            min_values=2, 
            max_values=2, 
            options=options
        )
        self.user_model = user_model
    
    async def callback(self, interaction: discord.Interaction):
        """クラス選択の処理"""
        user_id = interaction.user.id
        
        # 選択されたクラスを取得
        selected_classes = [cls.split('_')[0] for cls in self.values]
        
        # 試合中ロールチェック
        role_name = "試合中"
        active_role = discord.utils.get(interaction.user.roles, name=role_name)
        if active_role:
            await interaction.response.send_message(
                f"{interaction.user.mention} 現在試合中のため、クラスを変更できません。", 
                ephemeral=True
            )
            await asyncio.sleep(10)
            await interaction.delete_original_response()
            return
        
        if len(selected_classes) != 2:
            await interaction.response.send_message(
                "クラスを2つ選択してください。", ephemeral=True
            )
            await asyncio.sleep(10)
            await interaction.delete_original_response()
            return
        
        # ViewModelを使用してクラスを更新
        success = self.user_model.update_user_classes(
            str(user_id), selected_classes[0], selected_classes[1]
        )
        
        if success:
            await interaction.response.send_message(
                f"Update selected classes: {', '.join(selected_classes)}", ephemeral=True
            )
            await asyncio.sleep(30)
            await interaction.delete_original_response()
        else:
            await interaction.response.send_message(
                "ユーザー未登録です。", ephemeral=True
            )
            await asyncio.sleep(15)
            await interaction.delete_original_response()

class ResultView(View):
    """試合結果入力用のView"""
    
    def __init__(self, player1_id: int, player2_id: int, matching_classes: Dict, 
                 thread: discord.Thread, matchmaking_view: MatchmakingView,
                 active_result_views: dict = None):
        super().__init__(timeout=None)
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.matching_classes = matching_classes
        self.thread = thread
        self.matchmaking_view = matchmaking_view
        self.active_result_views = active_result_views or {}
        
        # 結果の状態管理
        self.player1_result = None
        self.player2_result = None
        self.results_locked = False
        self.timeout_task = None
        
        # ViewModelの初期化
        self.result_vm = ResultViewModel()
        self.cancel_vm = CancelViewModel()
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="2勝", style=discord.ButtonStyle.success)
    async def two_wins(self, button: Button, interaction: discord.Interaction):
        await remove_role(interaction.user, "試合中")
        await self.handle_result(interaction, 2)
    
    @discord.ui.button(label="1勝", style=discord.ButtonStyle.primary)
    async def one_win(self, button: Button, interaction: discord.Interaction):
        await remove_role(interaction.user, "試合中")
        await self.handle_result(interaction, 1)
    
    @discord.ui.button(label="0勝", style=discord.ButtonStyle.danger)
    async def zero_wins(self, button: Button, interaction: discord.Interaction):
        await remove_role(interaction.user, "試合中")
        await self.handle_result(interaction, 0)
    
    @discord.ui.button(label="リセット", style=discord.ButtonStyle.secondary)
    async def reset(self, button: Button, interaction: discord.Interaction):
        await self.handle_reset(interaction)
    
    async def handle_result(self, interaction: discord.Interaction, result: int):
        """結果入力の処理"""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        # 参加者チェック
        if user_id != self.player1_id and user_id != self.player2_id:
            await self._send_response(interaction, "あなたはこの試合の参加者ではありません。")
            return
        
        # ロック済みチェック
        if self.results_locked:
            await self._send_response(interaction, "結果は既に確定しています。")
            return
        
        # 既に入力済みチェック
        if user_id == self.player1_id and self.player1_result is not None:
            await self._send_response(interaction, "あなたは既に結果を入力しています。")
            return
        elif user_id == self.player2_id and self.player2_result is not None:
            await self._send_response(interaction, "あなたは既に結果を入力しています。")
            return
        
        # 結果を設定
        if user_id == self.player1_id:
            self.player1_result = result
        else:
            self.player2_result = result
        
        await self._send_response(
            interaction, 
            f"{interaction.user.display_name} が {result} 勝を選択しました。"
        )
        
        # 両方の結果が揃ったかチェック
        if self.player1_result is not None and self.player2_result is not None:
            self.cancel_timeout()
            await self.check_results()
        else:
            # タイマー開始
            if self.timeout_task is None:
                self.timeout_task = asyncio.create_task(self.timeout_wait())
    
    async def handle_reset(self, interaction: discord.Interaction):
        """リセット処理"""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        # 参加者チェック
        if user_id != self.player1_id and user_id != self.player2_id:
            await self._send_response(interaction, "この試合の参加者ではありません。")
            return
        
        # 結果をリセット
        if user_id == self.player1_id:
            self.player1_result = None
        elif user_id == self.player2_id:
            self.player2_result = None
        
        # 試合中ロールを再付与
        await assign_role(interaction.user, "試合中")
        
        # タイマーキャンセル
        self.cancel_timeout()
        
        await self._send_response(
            interaction, 
            f"{interaction.user.display_name} さんの勝利数の入力をリセットしました。"
        )
    
    async def check_results(self):
        """結果をチェックして処理"""
        if self.results_locked:
            return
        
        try:
            self.logger.info(f"Player1 ID: {self.player1_id}, Result: {self.player1_result}")
            self.logger.info(f"Player2 ID: {self.player2_id}, Result: {self.player2_result}")
            
            # ViewModelで結果を処理
            from models.user import UserModel
            user_model = UserModel()
            
            user1_data = user_model.get_user_by_discord_id(str(self.player1_id))
            user2_data = user_model.get_user_by_discord_id(str(self.player2_id))
            
            if not user1_data or not user2_data:
                await self.thread.send("ユーザー情報が見つかりませんでした。")
                return
            
            # user_dataが辞書かオブジェクトかを判定して適切にアクセス
            def get_attr(data, attr_name, default=None):
                if isinstance(data, dict):
                    return data.get(attr_name, default)
                else:
                    return getattr(data, attr_name, default)
            
            user1_id = get_attr(user1_data, 'id')
            user2_id = get_attr(user2_data, 'id')
            user1_rating = get_attr(user1_data, 'rating', 1500)
            user2_rating = get_attr(user2_data, 'rating', 1500)
            user1_name = get_attr(user1_data, 'user_name', 'Unknown')
            user2_name = get_attr(user2_data, 'user_name', 'Unknown')
            
            result = self.result_vm.finalize_match(
                user1_id, user2_id, 
                self.player1_result, self.player2_result,
                user1_rating, user2_rating
            )
            
            if result['success']:
                self.results_locked = True
                
                # 最新シーズンでマッチングしたフラグをオンにする
                user_model.execute_with_session(self._update_season_flag, user1_id, user2_id)
                
                # 結果メッセージを作成
                user1_change = result['user1_rating_change']
                user2_change = result['user2_rating_change']
                user1_change_sign = "+" if user1_change > 0 else ""
                user2_change_sign = "+" if user2_change > 0 else ""
                
                message = (
                    f"{user1_name}さんのレーティングが更新されました。\n"
                    f"変動前: {user1_rating:.0f} -> 変動後: {result['after_user1_rating']:.0f} "
                    f"({user1_change_sign}{user1_change:.0f})\n"
                    f"{user2_name}さんのレーティングが更新されました。\n"
                    f"変動前: {user2_rating:.0f} -> 変動後: {result['after_user2_rating']:.0f} "
                    f"({user2_change_sign}{user2_change:.0f})"
                )
                
                self.logger.info(message)
                await self.thread.send(message)
                
                await asyncio.sleep(5)
                
                # メッセージを収集してログに保存
                await self._collect_and_save_messages()
                
                # active_result_viewsから削除
                if self.active_result_views and self.thread.id in self.active_result_views:
                    del self.active_result_views[self.thread.id]
                    self.logger.info(f"✅ Removed thread {self.thread.id} from active_result_views")
                
                # スレッドを削除
                await self.thread.delete()
                
            else:
                # 結果が一致しない場合
                self.player1_result = None
                self.player2_result = None
                await self.thread.send(
                    f"<@{self.player1_id}>と<@{self.player2_id}>、結果が一致しません。再度入力してください。",
                    view=self
                )
        
        except Exception as e:
            self.logger.error(f"Error in check_results: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await self.thread.send("エラーが発生しました。管理者にお問い合わせください。")
            try:
                # active_result_viewsから削除
                if self.active_result_views and self.thread.id in self.active_result_views:
                    del self.active_result_views[self.thread.id]
                await self.thread.delete()
            except Exception as delete_exception:
                self.logger.error(f"Failed to delete thread after error: {delete_exception}")
    
    async def timeout_wait(self):
        """タイムアウト処理"""
        guild = self.thread.guild
        try:
            await asyncio.sleep(RESULT_REPORT_TIMEOUT)
            
            if self.player1_result is None and self.player2_result is not None:
                # プレイヤー1が未入力、プレイヤー2の勝利
                self.player1_result = 0
                self.player2_result = 2
                await self.thread.send(
                    f"<@{self.player1_id}> が勝利数を報告しなかったため、"
                    f"<@{self.player2_id}> の勝利となります。\n"
                    f"このスレッドは{THREAD_DELETE_DELAY//3600}時間後に削除されます。"
                )
                
                player1_member = guild.get_member(self.player1_id)
                if player1_member:
                    await remove_role(player1_member, "試合中")
                
                # ペナルティ適用
                self.cancel_vm.apply_timeout_penalty(self.player1_id)
                
                await self.check_results_by_timeout()
                
            elif self.player2_result is None and self.player1_result is not None:
                # プレイヤー2が未入力、プレイヤー1の勝利
                self.player1_result = 2
                self.player2_result = 0
                await self.thread.send(
                    f"<@{self.player2_id}> が勝利数を報告しなかったため、"
                    f"<@{self.player1_id}> の勝利となります。\n"
                    f"このスレッドは{THREAD_DELETE_DELAY//3600}時間後に削除されます。"
                )
                
                player2_member = guild.get_member(self.player2_id)
                if player2_member:
                    await remove_role(player2_member, "試合中")
                
                # ペナルティ適用
                self.cancel_vm.apply_timeout_penalty(self.player2_id)
                
                await self.check_results_by_timeout()
        
        except asyncio.CancelledError:
            player1_member = guild.get_member(self.player1_id)
            player2_member = guild.get_member(self.player2_id)
            self.logger.info(
                f"{self.player1_id}({player1_member.display_name if player1_member else 'Unknown'})"
                f"と{self.player2_id}({player2_member.display_name if player2_member else 'Unknown'})"
                f"のタスクがキャンセルされました。"
            )
    
    async def check_results_by_timeout(self):
        """タイムアウトによる結果確定処理"""
        if self.results_locked:
            return
        
        try:
            # 通常の結果確定処理と同様
            await self.check_results()
            
            # 長時間後にスレッド削除
            await asyncio.sleep(THREAD_DELETE_DELAY)
            await self._collect_and_save_messages()
            
            # active_result_viewsから削除
            if self.active_result_views and self.thread.id in self.active_result_views:
                del self.active_result_views[self.thread.id]
            
            await self.thread.delete()
            
        except Exception as e:
            self.logger.error(f"Error in check_results_by_timeout: {e}")
    
    def cancel_timeout(self):
        """タイマータスクをキャンセル"""
        if self.timeout_task is not None:
            self.timeout_task.cancel()
            self.timeout_task = None
    
    async def _send_response(self, interaction: discord.Interaction, content: str):
        """レスポンスを送信"""
        if not interaction.response.is_done():
            await interaction.response.send_message(content)
        else:
            await interaction.followup.send(content)
    
    def _update_season_flag(self, session, user1_id: int, user2_id: int):
        """シーズンマッチングフラグを更新"""
        from config.database import User
        user1 = session.query(User).filter_by(id=user1_id).first()
        user2 = session.query(User).filter_by(id=user2_id).first()
        
        if user1:
            user1.latest_season_matched = True
        if user2:
            user2.latest_season_matched = True
    
    async def _collect_and_save_messages(self):
        """スレッドのメッセージを収集してログに保存"""
        try:
            messages = []
            async for message in self.thread.history(limit=None, oldest_first=True):
                if message.author.id == self.player1_id or message.author.id == self.player2_id:
                    # 対戦相手の情報を取得
                    if message.author.id == self.player1_id:
                        opponent_member = self.thread.guild.get_member(self.player2_id)
                    else:
                        opponent_member = self.thread.guild.get_member(self.player1_id)
                    
                    messages.append({
                        'timestamp': message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        'sender_display_name': message.author.display_name,
                        'sender_discord_id': message.author.id,
                        'content': message.content,
                        'opponent_display_name': opponent_member.display_name if opponent_member else 'Unknown',
                        'opponent_discord_id': opponent_member.id if opponent_member else 'Unknown'
                    })
            
            # メッセージをファイルに保存
            with open('messagelog.txt', 'a', encoding='utf-8') as f:
                for msg in messages:
                    f.write(
                        f"Timestamp: {msg['timestamp']}, "
                        f"Sender: {msg['sender_display_name']} ({msg['sender_discord_id']}), "
                        f"Opponent: {msg['opponent_display_name']} ({msg['opponent_discord_id']}), "
                        f"Content: {msg['content']}\n"
                    )
        except Exception as e:
            self.logger.error(f"Failed to collect messages: {e}")

class RateDisplayView(View):
    """レート表示用のView"""
    
    def __init__(self, p1_id: str, p2_id: str, p1_name: str, p2_name: str,
                 p1_rating: float, p2_rating: float):
        super().__init__(timeout=None)
        self.p1_id, self.p2_id = p1_id, p2_id
        self.p1_name, self.p2_name = p1_name, p2_name
        self.p1_rating, self.p2_rating = p1_rating, p2_rating
    
    @discord.ui.button(label="レートを表示", style=discord.ButtonStyle.secondary)
    async def show_rate(self, button: Button, interaction: discord.Interaction):
        if str(interaction.user.id) not in (self.p1_id, self.p2_id):
            await interaction.response.send_message(
                "この試合の参加者のみレートを確認できます。", ephemeral=True
            )
            return
        
        # ユーザーの設定を確認
        from models.user import UserModel
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        if str(interaction.user.id) == self.p1_id:
            your_rating = self.p1_rating
            opp_rating = self.p2_rating
        else:
            your_rating = self.p2_rating
            opp_rating = self.p1_rating
        
        content = f"あなたのレート: {int(your_rating)}\n"
        if user and getattr(user, 'display_opponent_rating', True):
            content += f"相手のレート: {int(opp_rating)}"
        
        await interaction.response.send_message(content, ephemeral=True)

class CancelConfirmationView(View):
    """試合中止確認用のView"""
    
    def __init__(self, user1, user2, thread):
        super().__init__(timeout=None)
        self.user1 = user1  # キャンセルを提案したユーザー
        self.user2 = user2  # 対戦相手
        self.thread = thread
        self.cancel_vm = CancelViewModel()
        self.accept_timer_task = asyncio.create_task(self.accept_timer())
    
    @discord.ui.button(label="はい", style=discord.ButtonStyle.success)
    async def yes_button(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id == self.user2.id:
            await interaction.response.send_message(
                "回答が完了しました。次の試合を開始できます。", ephemeral=True
            )
            
            self.accept_timer_task.cancel()
            await self._increment_cancelled_count()
            await self.thread.send(
                f"{interaction.user.mention} が中止を受け入れ、対戦が無効になりました。このスレッドを削除します。"
            )
            await remove_role(self.user2, "試合中")
            
            await asyncio.sleep(6)
            await self.thread.delete()
        else:
            await interaction.response.send_message(
                "対戦相手のみがこのボタンを使用できます。", ephemeral=True
            )
    
    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.danger)
    async def no_button(self, button: Button, interaction: discord.Interaction):
        if interaction.user.id == self.user2.id:
            self.accept_timer_task.cancel()
            await remove_role(self.user2, "試合中")
            await interaction.response.send_message(
                "回答が完了しました。次の試合を開始できます。", ephemeral=True
            )
            
            await self.thread.send(
                "チャットで状況を説明し、必要であれば関連する画像をアップロードしてください。スタッフが対応します。"
            )
            staff_role = discord.utils.get(interaction.guild.roles, name="staff")
            if staff_role:
                await self.thread.send(f"{staff_role.mention}")
        else:
            await interaction.response.send_message(
                "対戦相手のみがこのボタンを使用できます。", ephemeral=True
            )
    
    async def accept_timer(self):
        """48時間後に自動的に「はい」とみなす"""
        await asyncio.sleep(48 * 60 * 60)
        await self.thread.send(
            f"48時間が経過しました。{self.user2.mention} が応答しなかったため、"
            f"対戦中止を受け入れたとみなします。このスレッドを削除します。"
        )
        await self._increment_cancelled_count()
        await remove_role(self.user2, "試合中")
        
        await asyncio.sleep(6)
        await self.thread.delete()
    
    async def _increment_cancelled_count(self):
        """キャンセル回数を増加"""
        from models.user import UserModel
        user_model = UserModel()
        
        user1_data = user_model.get_user_by_discord_id(str(self.user1.id))
        user2_data = user_model.get_user_by_discord_id(str(self.user2.id))
        
        if user1_data and user2_data:
            # キャンセル回数の増加処理（必要に応じてUserModelに追加）
            pass