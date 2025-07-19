import discord
from discord.ui import View, Button, Select, Modal, InputText
import asyncio
from typing import Optional
from collections import defaultdict
from utils.helpers import safe_create_register_thread, safe_add_user_to_thread, count_characters
import logging

class RegisterView(View):
    """ユーザー登録View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RegisterButton())

class RegisterButton(Button):
    """ユーザー登録ボタン"""
    
    def __init__(self):
        super().__init__(label="Register", style=discord.ButtonStyle.primary)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        """登録ボタンのコールバック"""
        # スレッドを作成
        thread = await safe_create_register_thread(
            interaction.channel, 
            interaction.user, 
        )
        
        if thread:
            await interaction.response.defer()
            await safe_add_user_to_thread(thread, interaction.user)
            
            # スレッド内で register_user の処理を行う
            await self.register_user(interaction, thread)
        else:
            await interaction.response.send_message(
                "スレッドの作成に失敗しました。しばらく待ってから再試行してください。", 
                ephemeral=True
            )
    
    async def register_user(self, interaction: discord.Interaction, thread: discord.Thread):
        """ユーザー登録処理"""
        username = str(interaction.user.display_name)
        user_id = interaction.user.id
        
        try:
            # 遅延インポートで循環インポートを回避
            from models.user import UserModel
            user_model = UserModel()
            
            # 既存ユーザーをチェック
            existing_user = user_model.get_user_by_discord_id(str(user_id))
            if existing_user and existing_user['discord_id'] and existing_user['trust_points']:
                await thread.send("あなたはすでに登録されています。")
                await asyncio.sleep(8)
                await self._safe_delete_thread(thread)
                return
            
            # ユーザーにゲーム内の名前の入力を求める
            while True:
                await thread.send("ゲーム内で使用している名前を入力してください。名前は後で1回だけ変更可能です。")
                
                def check(m):
                    return m.author == interaction.user and m.channel == thread
                
                try:
                    msg = await interaction.client.wait_for('message', check=check, timeout=180.0)
                    username = msg.content
                    
                    # ニックネームの長さを確認（12文字以内）
                    if count_characters(username) > 12:
                        await thread.send("ニックネームは12文字以内にしてください（全角・半角問わず）。")
                        continue
                    
                    if not username:
                        await thread.send("無効な入力です。再度ゲーム内の名前を入力してください。")
                        continue
                    
                    break
                except asyncio.TimeoutError:
                    await thread.send("タイムアウトしました。もう一度お試しください。")
                    await self._safe_delete_thread(thread)
                    return
            
            # SHADOWVERSE_IDの入力を求める（13桁に変更）
            shadowverse_id = None
            while not shadowverse_id:
                await thread.send("SHADOWVERSE_ID（13桁の数字）を入力してください：")
                
                try:
                    msg = await interaction.client.wait_for('message', check=check, timeout=180.0)
                    input_id = msg.content
                    if not input_id.isdigit() or len(input_id) != 13:
                        await thread.send("入力に不備があります。13桁の数字であることを確認し、やり直してください。")
                        continue
                    shadowverse_id = input_id
                except asyncio.TimeoutError:
                    await thread.send("登録がタイムアウトしました。もう一度お試しください。")
                    await self._safe_delete_thread(thread)
                    return
            
            # ユーザーを作成
            user = user_model.create_user(str(user_id), username, shadowverse_id)
            
            if user:
                await thread.send(
                    f"**ユーザー {username} の登録が完了しました。**\n\n"
                    f"📝 名前変更権: 1回利用可能\n"
                    f"💡 名前変更は `/change_name` コマンドで行えます。\n"
                    f"⚠️ 権限は使用後、毎月1日に復活します。"
                )
                self.logger.info(f"User {username} (ID: {user_id}) registered successfully")
            else:
                await thread.send("登録に失敗しました。管理者にお問い合わせください。")
        
        except ValueError as e:
            await thread.send(f"登録エラー: {str(e)}")
            self.logger.error(f"Registration error for user {user_id}: {e}")
        except Exception as e:
            await thread.send("予期しないエラーが発生しました。管理者にお問い合わせください。")
            self.logger.error(f"Unexpected error during registration for user {user_id}: {e}")
        finally:
            await asyncio.sleep(6)
            await self._safe_delete_thread(thread)
    
    async def _safe_delete_thread(self, thread: discord.Thread):
        """スレッドを安全に削除"""
        try:
            # スレッドが存在するかチェック（guild.get_threadを使用）
            guild_thread = thread.guild.get_thread(thread.id)
            if guild_thread is None:
                # スレッドが見つからない場合はguild.fetch_channelで確認
                try:
                    await thread.guild.fetch_channel(thread.id)
                except discord.errors.NotFound:
                    # スレッドが既に削除されている
                    self.logger.info(f"Thread {thread.id} was already deleted")
                    return
            
            # スレッドが存在する場合は削除
            await thread.delete()
            self.logger.info(f"Thread {thread.id} deleted successfully")
            
        except discord.errors.NotFound:
            # スレッドが既に削除されている
            self.logger.info(f"Thread {thread.id} was already deleted")
        except discord.errors.Forbidden:
            # 削除権限がない
            self.logger.error(f"No permission to delete thread {thread.id}")
        except AttributeError as e:
            # オブジェクトの属性エラー
            self.logger.error(f"Attribute error when deleting thread {thread.id}: {e}")
            # 単純に削除を試行
            try:
                await thread.delete()
                self.logger.info(f"Thread {thread.id} deleted successfully (fallback)")
            except Exception as fallback_e:
                self.logger.error(f"Fallback deletion failed for thread {thread.id}: {fallback_e}")
        except Exception as e:
            # その他のエラー
            self.logger.error(f"Error deleting thread {thread.id}: {e}")

class NameChangeModal(Modal):
    """名前変更用のモーダル"""
    
    def __init__(self):
        super().__init__(title="名前変更")
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.name_input = InputText(
            label="新しい名前",
            placeholder="12文字以内で入力してください",
            max_length=12,
            required=True
        )
        self.add_item(self.name_input)
    
    async def callback(self, interaction: discord.Interaction):
        """名前変更の処理"""
        new_name = self.name_input.value.strip()
        
        if not new_name:
            await interaction.response.send_message("名前が入力されていません。", ephemeral=True)
            return
        
        if count_characters(new_name) > 12:
            await interaction.response.send_message("名前は12文字以内にしてください。", ephemeral=True)
            return
        
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            # 名前変更を実行
            result = user_model.change_user_name(str(interaction.user.id), new_name)
            
            if result['success']:
                # サーバーニックネームを変更
                try:
                    await interaction.user.edit(nick=new_name)
                    await interaction.response.send_message(
                        f"✅ 名前を **{new_name}** に変更しました。\n"
                        f"名前変更権を使用したため、次回は来月1日から利用可能です。",
                        ephemeral=True
                    )
                    self.logger.info(f"User {interaction.user.id} changed name to {new_name}")
                except discord.Forbidden:
                    await interaction.response.send_message(
                        f"✅ データベースの名前を **{new_name}** に変更しました。\n"
                        f"⚠️ サーバーニックネームの変更に失敗しました（権限不足）。\n"
                        f"名前変更権を使用したため、次回は来月1日から利用可能です。",
                        ephemeral=True
                    )
                except Exception as e:
                    self.logger.error(f"Error changing nickname for user {interaction.user.id}: {e}")
                    await interaction.response.send_message(
                        f"✅ データベースの名前を **{new_name}** に変更しました。\n"
                        f"⚠️ サーバーニックネームの変更でエラーが発生しました。\n"
                        f"名前変更権を使用したため、次回は来月1日から利用可能です。",
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message(f"❌ {result['message']}", ephemeral=True)
                
        except Exception as e:
            self.logger.error(f"Error in name change for user {interaction.user.id}: {e}")
            await interaction.response.send_message(
                "名前変更中にエラーが発生しました。管理者にお問い合わせください。",
                ephemeral=True
            )

class ProfileView(View):
    """プロフィール表示View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProfileButton())

class ProfileButton(Button):
    """プロフィール表示ボタン"""
    
    def __init__(self):
        super().__init__(label="プロフィール表示", style=discord.ButtonStyle.primary)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        """プロフィール表示のコールバック"""
        user_id = str(interaction.user.id)
        
        try:
            # 遅延インポートで循環インポートを回避
            from models.user import UserModel
            user_model = UserModel()
            
            user_instance = user_model.get_user_by_discord_id(user_id)
            
            if user_instance:
                # ユーザー情報の取得（辞書形式）
                user_name = user_instance['user_name']
                shadowverse_id = user_instance['shadowverse_id']
                rating = round(user_instance['rating'], 3)
                trust_points = user_instance['trust_points']
                win_count = user_instance['win_count']
                loss_count = user_instance['loss_count']
                
                # 効果的レート
                effective_rating = max(user_instance['rating'], user_instance['stayed_rating'] or 0)
                
                # ユーザーの順位を計算
                rank = user_model.get_user_rank(user_id)
                if rank is None:
                    rank = "未参加です"
                
                # 名前変更権の状態
                name_change_status = "✅ 利用可能" if user_instance.get('name_change_available', True) else "❌ 使用済み（来月1日復活）"
                
                # プロフィールメッセージの作成
                profile_message = (
                    f"**ユーザープロフィール**\n"
                    f"ユーザー名 : {user_name}\n"
                    f"Shadowverse ID : {shadowverse_id}\n"
                    f"レーティング : {rating}\n"
                )
                
                # stay_flag が 1 の場合、stayed_ratingを表示
                if user_instance['stay_flag'] == 1:
                    stayed_rating_rounded = round(user_instance['stayed_rating'], 2)
                    profile_message += f"（stay時のレート : {stayed_rating_rounded}）\n"
                
                profile_message += (
                    f"信用ポイント : {trust_points}\n"
                    f"勝敗 : {win_count}勝 {loss_count}敗\n"
                    f"順位 : {rank}\n"
                    f"名前変更権 : {name_change_status}\n"
                )
                
                # StayButtonViewを作成
                view = None
                # '試合中' ロールを持っているか確認
                ongoing_match_role = discord.utils.get(interaction.guild.roles, name='試合中')
                is_in_match = ongoing_match_role in interaction.user.roles
                
                if not is_in_match:
                    view = StayButtonView(user_instance, interaction)
                
                await interaction.response.send_message(profile_message, ephemeral=True, view=view)
            else:
                await interaction.response.send_message(
                    "ユーザー情報が見つかりません。ユーザー登録を行ってください。", 
                    ephemeral=True
                )
        except Exception as e:
            self.logger.error(f"Error in profile display for user {user_id}: {e}")
            await interaction.response.send_message(
                "プロフィールの取得中にエラーが発生しました。", 
                ephemeral=True
            )

class StayButtonView(View):
    """Stay機能用のView"""
    
    def __init__(self, user_instance, interaction):
        super().__init__()
        self.user_instance = user_instance
        
        # '試合中' ロールを持っているか確認
        ongoing_match_role = discord.utils.get(interaction.guild.roles, name='試合中')
        is_in_match = ongoing_match_role in interaction.user.roles
        
        # ボタンのラベルや有効・無効を分岐
        if self.user_instance['stay_flag'] == 0 and self.user_instance['stayed_rating'] == 1500:
            label = "stay機能を使用する"
            disabled = is_in_match
        elif self.user_instance['stay_flag'] == 1:
            label = "stayを元に戻す"
            disabled = is_in_match
        else:
            label = "stay機能は使用できません"
            disabled = True
        
        button = StayButton(user_instance, interaction, label, disabled)
        self.add_item(button)

class StayButton(Button):
    """Stay機能ボタン"""
    
    def __init__(self, user_instance, interaction, label: str, disabled: bool = False):
        super().__init__(label=label, style=discord.ButtonStyle.primary, disabled=disabled)
        self.user_instance = user_instance
        self.interaction = interaction
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        """Stay機能のコールバック"""
        user_id = str(interaction.user.id)
        
        try:
            # 遅延インポートで循環インポートを回避
            from models.user import UserModel
            user_model = UserModel()
            
            user_instance = user_model.get_user_by_discord_id(user_id)
            
            # ロール確認
            ongoing_match_role = discord.utils.get(interaction.guild.roles, name='試合中')
            if ongoing_match_role in interaction.user.roles:
                await interaction.response.send_message(
                    "現在、試合中のためレートを切り替えることはできません。", 
                    ephemeral=True
                )
                return
            
            if not user_instance:
                await interaction.response.send_message("ユーザー情報が見つかりません。", ephemeral=True)
                return
            
            # stay_flag の状態に応じて処理を分岐
            if user_instance['stay_flag'] == 0 and user_instance['stayed_rating'] == 1500:
                confirm_view = StayConfirmView(user_instance, mode="stay")
                await interaction.response.send_message(
                    "stay機能を使用すると、現在のレートと勝敗数が保存され、レートが1500,勝敗数が0にリセットされます。\n本当に実行しますか？",
                    view=confirm_view,
                    ephemeral=True
                )
            elif user_instance['stay_flag'] == 1:
                confirm_view = StayConfirmView(user_instance, mode="revert")
                await interaction.response.send_message(
                    "stayを元に戻すと、stayedに保存されているレートと勝敗数をメインアカウントに復元します。現在のレート，試合数などは削除されます。\n本当に実行しますか？",
                    view=confirm_view,
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "現在、stay機能を使用できる状態ではありません。", 
                    ephemeral=True
                )
        except Exception as e:
            self.logger.error(f"Error in stay button callback: {e}")
            await interaction.response.send_message(
                "エラーが発生しました。", 
                ephemeral=True
            )

class StayConfirmView(View):
    """Stay確認用のView"""
    
    def __init__(self, user_instance, mode: str, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.user_instance = user_instance
        self.mode = mode
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="はい", style=discord.ButtonStyle.success)
    async def confirm(self, button: Button, interaction: discord.Interaction):
        """確認ボタンのコールバック"""
        # 実行者確認
        if interaction.user.id != int(self.user_instance['discord_id']):
            await interaction.response.send_message(
                "このボタンはあなたのためのものではありません。", 
                ephemeral=True
            )
            return
        
        # '試合中' ロールを持っているか確認
        ongoing_match_role = discord.utils.get(interaction.guild.roles, name='試合中')
        if ongoing_match_role in interaction.user.roles:
            await interaction.response.send_message(
                "現在、試合中のためレートを切り替えることはできません。", 
                ephemeral=True
            )
            return
        
        try:
            # 遅延インポートで循環インポートを回避
            from models.user import UserModel
            user_model = UserModel()
            
            # ViewModelでStay機能を実行
            result = user_model.toggle_stay_flag(self.user_instance['discord_id'])
            
            if result:
                await interaction.response.edit_message(
                    content=result['message'], 
                    view=None
                )
                self.logger.info(f"Stay function executed for user {self.user_instance['discord_id']}: {result['action']}")
            else:
                await interaction.response.edit_message(
                    content="Stay機能の実行に失敗しました。", 
                    view=None
                )
        
        except ValueError as e:
            await interaction.response.edit_message(
                content=f"エラー: {str(e)}", 
                view=None
            )
        except Exception as e:
            self.logger.error(f"Error in stay function for user {self.user_instance['discord_id']}: {e}")
            await interaction.response.edit_message(
                content="予期しないエラーが発生しました。", 
                view=None
            )
    
    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.danger)
    async def cancel(self, button: Button, interaction: discord.Interaction):
        """キャンセルボタンのコールバック"""
        # ボタンを押したユーザーがコマンド実行者か確認
        if interaction.user.id != int(self.user_instance['discord_id']):
            await interaction.response.send_message(
                "このボタンはあなたのためのものではありません。", 
                ephemeral=True
            )
            return
        
        await interaction.response.edit_message(
            content="stay操作はキャンセルされました。", 
            view=None
        )

class AchievementButtonView(View):
    """実績表示View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(AchievementButton())

class AchievementButton(Button):
    """実績表示ボタン"""
    
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="実績")
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        """実績表示のコールバック"""
        # ボタンを押したユーザーを取得
        user = interaction.user
        
        # ユーザーの実績を取得
        achievements = self.get_user_achievements(user)
        
        # 実績をユーザーに送信し、1分後に削除
        if achievements:
            await interaction.response.send_message(achievements, ephemeral=True)
        else:
            await interaction.response.send_message(
                "実績条件を満たすとその回数がカウントされます。", 
                ephemeral=True
            )
        
        # 60秒後にメッセージを削除
        await asyncio.sleep(60)
        try:
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            pass
    
    def get_user_achievements(self, user) -> Optional[str]:
        """ユーザーの実績を取得"""
        try:
            # 遅延インポートで循環インポートを回避
            from models.user import UserModel
            from models.season import SeasonModel
            
            user_model = UserModel()
            season_model = SeasonModel()
            
            # データベースからユーザーを取得
            db_user = user_model.get_user_by_discord_id(str(user.id))
            if not db_user:
                return None
            
            # season.end_date が NULL でないシーズンを id 昇順で取得
            seasons = season_model.get_past_seasons()
            
            # 各カテゴリごとの実績カウントを初期化
            achievements_count = {
                '最終順位': defaultdict(int),
                '最終レート': defaultdict(int),
                '勝率': defaultdict(int),
            }
            
            # 実績があるかどうかのフラグ
            has_achievements = False
            
            # 各シーズンごとに処理（セッション管理対応）
            for season in seasons:
                season_id = season['id']
                
                # そのシーズンのユーザーの記録を取得（セッション内で安全に処理）
                def _get_season_record(session):
                    from config.database import UserSeasonRecord
                    record = session.query(UserSeasonRecord).filter_by(
                        user_id=db_user['id'], season_id=season_id
                    ).first()
                    
                    if record:
                        return {
                            'rank': record.rank,
                            'rating': record.rating,
                            'total_matches': record.total_matches,
                            'win_count': record.win_count
                        }
                    return None
                
                user_season_record_data = season_model.safe_execute(_get_season_record)
                
                if not user_season_record_data:
                    continue
                
                # そのシーズンでのカテゴリごとの最高実績を格納
                season_highest_achievements = {}
                
                # 最終順位の実績
                rank = user_season_record_data['rank']
                if rank is not None:
                    from config.settings import RANK_ACHIEVEMENTS
                    for level, achievement in RANK_ACHIEVEMENTS:
                        if (
                            (level == 1 and rank == 1) or
                            (level == 2 and rank == 2) or
                            (level == 3 and rank == 3) or
                            (level == 4 and rank <= 8) or
                            (level == 5 and rank <= 16) or
                            (level == 6 and rank <= 100)
                        ):
                            season_highest_achievements['最終順位'] = (level, achievement)
                            has_achievements = True
                            break
                
                # 最終レートの実績
                rating = user_season_record_data['rating']
                if rating is not None:
                    rating = int(rating)
                    # 1700以上からユーザーのレートまで100刻みで実績を設定
                    if rating >= 1700:
                        start_rating = 1700
                        max_rating = (rating // 100) * 100
                        rating_levels = []
                        level = 1
                        for r in range(start_rating, max_rating + 1, 100):
                            rating_levels.append(r)
                            level += 1
                        
                        # そのシーズンでの最高のレート実績を取得
                        season_highest_rating = max(r for r in rating_levels if r <= rating)
                        highest_achievement = f"{season_highest_rating}台"
                        level = len([r for r in rating_levels if r <= season_highest_rating])
                        season_highest_achievements['最終レート'] = (level, highest_achievement)
                        has_achievements = True
                
                # 勝率の実績
                total_matches = user_season_record_data['total_matches']
                win_count = user_season_record_data['win_count']
                if total_matches is not None and win_count is not None:
                    if total_matches >= 50:
                        win_rate = (win_count / total_matches) * 100
                        from config.settings import WIN_RATE_ACHIEVEMENTS
                        for level, achievement in WIN_RATE_ACHIEVEMENTS:
                            threshold = 70 - (level - 1) * 5  # 70, 65, 60
                            if win_rate >= threshold:
                                season_highest_achievements['勝率'] = (level, achievement)
                                has_achievements = True
                                break
                
                # 実績のカウントを更新
                for category, (level, achievement) in season_highest_achievements.items():
                    achievements_count[category][achievement] += 1
            
            if not has_achievements:
                return None
            
            # 結果を整形して出力
            output = f"**{user.display_name}さんの実績一覧**\n"
            
            # カテゴリごとに実績を表示
            for category in ['最終順位', '最終レート', '勝率']:
                category_achievements = achievements_count.get(category, {})
                if category_achievements:
                    output += f"\n**{category}：**\n"
                    # 実績をレベル順または数値順にソート
                    if category == '最終レート':
                        # レートは高い順にソート
                        sorted_achievements = sorted(
                            category_achievements.items(),
                            key=lambda x: self._get_rating_value(x[0]),
                            reverse=True
                        )
                    else:
                        sorted_achievements = sorted(
                            category_achievements.items(),
                            key=lambda x: self._get_achievement_level(category, x[0])
                        )
                    for ach, count in sorted_achievements:
                        indent = '　'  # 全角スペースでインデント
                        output += f"{indent}{ach}：**{count}回**\n"
            
            return output
        
        except Exception as e:
            self.logger.error(f"実績の取得中にエラーが発生しました: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    def _get_achievement_level(self, category: str, achievement_name: str) -> int:
        """実績のレベルを取得"""
        if category == '最終順位':
            level_dict = {
                "1位": 1,
                "2位": 2,
                "3位": 3,
                "TOP8": 4,
                "TOP16": 5,
                "100位以内": 6,
            }
        elif category == '勝率':
            level_dict = {
                "70%以上": 1,
                "65%以上": 2,
                "60%以上": 3,
            }
        else:
            return 999
        return level_dict.get(achievement_name, 999)
    
    def _get_rating_value(self, achievement_name: str) -> int:
        """レート実績から数値を取得"""
        try:
            return int(achievement_name.replace('台', ''))
        except ValueError:
            return 0