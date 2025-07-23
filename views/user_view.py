import discord
from discord.ui import View, Button, Select, Modal, InputText
import asyncio
import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from collections import defaultdict
from utils.helpers import count_characters, assign_role, remove_role
import logging

# 合言葉設定ファイル
PREMIUM_PASSWORDS_FILE = "config/premium_passwords.json"
PREMIUM_ROLE_NAME = "premium"

class PremiumPasswordManager:
    """Premium合言葉管理クラス"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.passwords = self.load_passwords()
    
    def load_passwords(self) -> Dict[str, int]:
        """合言葉を読み込み"""
        try:
            os.makedirs(os.path.dirname(PREMIUM_PASSWORDS_FILE), exist_ok=True)
            
            if os.path.exists(PREMIUM_PASSWORDS_FILE):
                with open(PREMIUM_PASSWORDS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # デフォルト合言葉
                default_passwords = {
                    "premium2025": 30,  # 1か月
                    "premiumhalf": 180  # 6か月
                }
                self.save_passwords(default_passwords)
                return default_passwords
        except Exception as e:
            self.logger.error(f"Error loading premium passwords: {e}")
            return {"premium2025": 30, "premiumhalf": 180}
    
    def save_passwords(self, passwords: Dict[str, int]):
        """合言葉を保存"""
        try:
            os.makedirs(os.path.dirname(PREMIUM_PASSWORDS_FILE), exist_ok=True)
            with open(PREMIUM_PASSWORDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(passwords, f, ensure_ascii=False, indent=2)
            self.passwords = passwords
        except Exception as e:
            self.logger.error(f"Error saving premium passwords: {e}")
    
    def set_password(self, days: int, password: str):
        """合言葉を設定"""
        # 既存の同じ日数の合言葉を削除
        self.passwords = {k: v for k, v in self.passwords.items() if v != days}
        # 新しい合言葉を追加
        self.passwords[password] = days
        self.save_passwords(self.passwords)
    
    def get_days_for_password(self, password: str) -> Optional[int]:
        """合言葉から日数を取得"""
        return self.passwords.get(password)
    
    def get_passwords_info(self) -> Dict[str, int]:
        """現在の合言葉情報を取得"""
        return self.passwords.copy()

# グローバルな合言葉マネージャー
password_manager = PremiumPasswordManager()

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
        try:
            # 遅延インポートで循環インポートを回避
            from models.user import UserModel
            user_model = UserModel()
            
            # 既存ユーザーをチェック
            existing_user = user_model.get_user_by_discord_id(str(interaction.user.id))
            if existing_user and existing_user['discord_id'] and existing_user['trust_points']:
                await interaction.response.send_message("あなたはすでに登録されています。", ephemeral=True)
                return
            
            # モーダルを表示
            modal = UserRegistrationModal()
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            self.logger.error(f"Error in register button callback: {e}")
            await interaction.response.send_message(
                "登録処理中にエラーが発生しました。管理者にお問い合わせください。", 
                ephemeral=True
            )

class UserRegistrationModal(Modal):
    """ユーザー登録用のモーダル"""
    
    def __init__(self):
        super().__init__(title="ユーザー登録")
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.username_input = InputText(
            label="ゲーム内で使用している名前",
            placeholder="12文字以内で入力してください（後で1回変更可能）",
            max_length=12,
            required=True
        )
        self.add_item(self.username_input)
        
        self.shadowverse_id_input = InputText(
            label="SHADOWVERSE_ID",
            placeholder="12桁の数字を入力してください",
            min_length=12,
            max_length=12,
            required=True
        )
        self.add_item(self.shadowverse_id_input)
    
    async def callback(self, interaction: discord.Interaction):
        """ユーザー登録の処理"""
        username = self.username_input.value.strip()
        shadowverse_id = self.shadowverse_id_input.value.strip()
        user_id = interaction.user.id
        
        # 入力値検証
        if not username:
            await interaction.response.send_message("名前が入力されていません。", ephemeral=True)
            return
        
        if count_characters(username) > 12:
            await interaction.response.send_message("名前は12文字以内にしてください。", ephemeral=True)
            return
        
        if not shadowverse_id.isdigit() or len(shadowverse_id) != 13:
            await interaction.response.send_message(
                "SHADOWVERSE_IDは13桁の数字である必要があります。", 
                ephemeral=True
            )
            return
        
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            # ユーザーを作成
            user = user_model.create_user(str(user_id), username, shadowverse_id)
            
            if user:
                # サーバーニックネームを変更
                try:
                    await interaction.user.edit(nick=username)
                    await interaction.response.send_message(
                        f"✅ **ユーザー {username} の登録が完了しました。**\n\n"
                        f"📝 名前変更権: 1回利用可能\n"
                        f"💡 名前変更は プロフィールチャンネルの「名前変更」ボタンで行えます。\n"
                        f"⚠️ 権限は使用後、毎月1日に復活します。\n"
                        f"🎮 サーバーニックネームも更新されました。",
                        ephemeral=True
                    )
                except discord.Forbidden:
                    await interaction.response.send_message(
                        f"✅ **ユーザー {username} の登録が完了しました。**\n\n"
                        f"📝 名前変更権: 1回利用可能\n"
                        f"💡 名前変更は プロフィールチャンネルの「名前変更」ボタンで行えます。\n"
                        f"⚠️ 権限は使用後、毎月1日に復活します。\n"
                        f"🔧 サーバーニックネームの変更に失敗しました（権限不足）。",
                        ephemeral=True
                    )
                except Exception as e:
                    self.logger.error(f"Error changing nickname for user {user_id}: {e}")
                    await interaction.response.send_message(
                        f"✅ **ユーザー {username} の登録が完了しました。**\n\n"
                        f"📝 名前変更権: 1回利用可能\n"
                        f"💡 名前変更は プロフィールチャンネルの「名前変更」ボタンで行えます。\n"
                        f"⚠️ 権限は使用後、毎月1日に復活します。\n"
                        f"🔧 サーバーニックネームの変更でエラーが発生しました。",
                        ephemeral=True
                    )
                
                self.logger.info(f"User {username} (ID: {user_id}) registered successfully via modal")
            else:
                await interaction.response.send_message(
                    "❌ 登録に失敗しました。管理者にお問い合わせください。", 
                    ephemeral=True
                )
        
        except ValueError as e:
            await interaction.response.send_message(f"❌ 登録エラー: {str(e)}", ephemeral=True)
            self.logger.error(f"Registration error for user {user_id}: {e}")
        except Exception as e:
            await interaction.response.send_message(
                "❌ 予期しないエラーが発生しました。管理者にお問い合わせください。", 
                ephemeral=True
            )
            self.logger.error(f"Unexpected error during registration for user {user_id}: {e}")

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
                        f"🎮 サーバーニックネームも更新されました。\n"
                        f"📅 名前変更権を使用したため、次回は来月1日から利用可能です。",
                        ephemeral=True
                    )
                    self.logger.info(f"User {interaction.user.id} changed name to {new_name}")
                except discord.Forbidden:
                    await interaction.response.send_message(
                        f"✅ データベースの名前を **{new_name}** に変更しました。\n"
                        f"⚠️ サーバーニックネームの変更に失敗しました（権限不足）。\n"
                        f"📅 名前変更権を使用したため、次回は来月1日から利用可能です。",
                        ephemeral=True
                    )
                except Exception as e:
                    self.logger.error(f"Error changing nickname for user {interaction.user.id}: {e}")
                    await interaction.response.send_message(
                        f"✅ データベースの名前を **{new_name}** に変更しました。\n"
                        f"⚠️ サーバーニックネームの変更でエラーが発生しました。\n"
                        f"📅 名前変更権を使用したため、次回は来月1日から利用可能です。",
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message(f"❌ {result['message']}", ephemeral=True)
                
        except Exception as e:
            self.logger.error(f"Error in name change for user {interaction.user.id}: {e}")
            await interaction.response.send_message(
                "❌ 名前変更中にエラーが発生しました。管理者にお問い合わせください。",
                ephemeral=True
            )

class PremiumModal(Modal):
    """Premium機能解放用のモーダル"""
    
    def __init__(self):
        super().__init__(title="Premium機能を解放する")
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.password_input = InputText(
            label="合言葉を入力してください",
            placeholder="Premium機能の合言葉を入力",
            required=True
        )
        self.add_item(self.password_input)
    
    async def callback(self, interaction: discord.Interaction):
        """Premium機能解放の処理"""
        password = self.password_input.value.strip()
        user_id = str(interaction.user.id)
        
        # 合言葉をチェック
        days = password_manager.get_days_for_password(password)
        if days is None:
            await interaction.response.send_message(
                "❌ 合言葉が正しくありません。", 
                ephemeral=True
            )
            return
        
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            # 現在のPremium残日数を取得
            current_days = user_model.get_premium_days(user_id)
            
            # 既にPremium日数がある場合の処理
            if current_days > 0:
                confirm_view = PremiumExtendConfirmView(days, current_days)
                await interaction.response.send_message(
                    f"⚠️ あなたは既にPremium機能を利用中です（残り{current_days}日）。\n"
                    f"新しい合言葉を使用すると{days}日が追加されます。\n"
                    f"合計で{current_days + days}日になります。続行しますか？",
                    view=confirm_view,
                    ephemeral=True
                )
                return
            
            # Premiumロールを取得または作成
            premium_role = discord.utils.get(interaction.guild.roles, name=PREMIUM_ROLE_NAME)
            if not premium_role:
                try:
                    premium_role = await interaction.guild.create_role(
                        name=PREMIUM_ROLE_NAME,
                        color=discord.Color.gold(),
                        reason="Premium機能用ロール"
                    )
                    self.logger.info(f"Created premium role in guild {interaction.guild.id}")
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "❌ Premiumロールの作成に失敗しました。管理者にお問い合わせください。",
                        ephemeral=True
                    )
                    return
            
            # Premium日数を追加
            success = user_model.add_premium_days(user_id, days)
            if not success:
                await interaction.response.send_message(
                    "❌ Premium機能の追加に失敗しました。", 
                    ephemeral=True
                )
                return
            
            # ロールを付与
            await assign_role(interaction.user, PREMIUM_ROLE_NAME)
            
            # 成功メッセージ
            period_text = f"{days}日間"
            await interaction.response.send_message(
                f"🎉 **Premium機能が解放されました！**\n\n"
                f"⏰ 追加期間: {period_text}\n"
                f"📅 総残日数: {days}日\n"
                f"✨ Premium機能をお楽しみください！",
                ephemeral=True
            )
            
            self.logger.info(f"Premium access granted to user {user_id} for {days} days")
            
        except Exception as e:
            self.logger.error(f"Error in premium activation for user {user_id}: {e}")
            await interaction.response.send_message(
                "❌ Premium機能の解放中にエラーが発生しました。管理者にお問い合わせください。",
                ephemeral=True
            )

class PremiumExtendConfirmView(View):
    """Premium期間延長確認View"""
    
    def __init__(self, add_days: int, current_days: int):
        super().__init__(timeout=60)
        self.add_days = add_days
        self.current_days = current_days
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="はい", style=discord.ButtonStyle.success)
    async def confirm(self, button: Button, interaction: discord.Interaction):
        """確認ボタンのコールバック"""
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            user_id = str(interaction.user.id)
            
            # Premium日数を追加
            success = user_model.add_premium_days(user_id, self.add_days)
            if not success:
                await interaction.response.edit_message(
                    content="❌ Premium機能の追加に失敗しました。", 
                    view=None
                )
                return
            
            total_days = self.current_days + self.add_days
            
            await interaction.response.edit_message(
                content=f"✅ Premium期間を{self.add_days}日延長しました！\n"
                        f"📅 総残日数: {total_days}日",
                view=None
            )
            
            self.logger.info(f"Premium extended for user {user_id}: +{self.add_days} days")
            
        except Exception as e:
            self.logger.error(f"Error extending premium for user {interaction.user.id}: {e}")
            await interaction.response.edit_message(
                content="❌ Premium期間延長中にエラーが発生しました。",
                view=None
            )
    
    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.danger)
    async def cancel(self, button: Button, interaction: discord.Interaction):
        """キャンセルボタンのコールバック"""
        await interaction.response.edit_message(
            content="Premium期間延長をキャンセルしました。",
            view=None
        )

class ProfileView(View):
    """プロフィール表示View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProfileButton())

class NameChangeView(View):
    """名前変更専用View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(NameChangeButton())

class StayFunctionView(View):
    """Stay機能専用View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(StayFunctionButton())

class PremiumView(View):
    """Premium機能専用View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PremiumButton())

class NameChangeButton(Button):
    """名前変更専用ボタン"""
    
    def __init__(self):
        super().__init__(label="名前を変更する", style=discord.ButtonStyle.secondary)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        """名前変更ボタンのコールバック"""
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            # ユーザーの存在確認
            user = user_model.get_user_by_discord_id(str(interaction.user.id))
            if not user:
                await interaction.response.send_message("ユーザー登録を行ってください。", ephemeral=True)
                return
            
            # 名前変更権の確認
            if not user.get('name_change_available', True):
                await interaction.response.send_message("❌ 名前変更権は来月1日まで利用できません。", ephemeral=True)
                return
            
            # モーダルを表示
            modal = NameChangeModal()
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            self.logger.error(f"Error in name change button: {e}")
            await interaction.response.send_message("名前変更処理中にエラーが発生しました。", ephemeral=True)

class StayFunctionButton(Button):
    """Stay機能専用ボタン"""
    
    def __init__(self):
        super().__init__(label="Stay機能を使用する", style=discord.ButtonStyle.secondary)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        """Stay機能ボタンのコールバック"""
        user_id = str(interaction.user.id)
        
        try:
            from models.user import UserModel
            user_model = UserModel()
            
            user_instance = user_model.get_user_by_discord_id(user_id)
            
            if not user_instance:
                await interaction.response.send_message("ユーザー情報が見つかりません。", ephemeral=True)
                return
            
            # ロール確認
            ongoing_match_role = discord.utils.get(interaction.guild.roles, name='試合中')
            if ongoing_match_role in interaction.user.roles:
                await interaction.response.send_message(
                    "現在、試合中のためレートを切り替えることはできません。", 
                    ephemeral=True
                )
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
            self.logger.error(f"Error in stay function button callback: {e}")
            await interaction.response.send_message(
                "エラーが発生しました。", 
                ephemeral=True
            )

class ProfileButton(Button):
    """プロフィール表示ボタン"""
    
    def __init__(self):
        super().__init__(label="プロフィールを確認する", style=discord.ButtonStyle.primary)
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
                
                # Premium状態の確認
                premium_days = user_model.get_premium_days(user_id)
                if premium_days > 0:
                    premium_status = f"✨ Premium（残り{premium_days}日）"
                else:
                    premium_status = "❌ 未解放"
                
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
                    f"Premium状態 : {premium_status}\n"
                )
                
                # シンプルなプロフィール表示のみ
                await interaction.response.send_message(profile_message, ephemeral=True)
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

class UserActionView(View):
    """ユーザーアクション用の統合View"""
    
    def __init__(self, user_instance, interaction, is_premium: bool):
        super().__init__()
        self.user_instance = user_instance
        
        # '試合中' ロールを持っているか確認
        ongoing_match_role = discord.utils.get(interaction.guild.roles, name='試合中')
        is_in_match = ongoing_match_role in interaction.user.roles
        
        # Stay機能ボタン
        if self.user_instance['stay_flag'] == 0 and self.user_instance['stayed_rating'] == 1500:
            stay_label = "stay機能を使用する"
            stay_disabled = is_in_match
        elif self.user_instance['stay_flag'] == 1:
            stay_label = "stayを元に戻す"
            stay_disabled = is_in_match
        else:
            stay_label = "stay機能は使用できません"
            stay_disabled = True
        
        stay_button = StayButton(user_instance, interaction, stay_label, stay_disabled)
        self.add_item(stay_button)
        
        # Premium機能ボタン
        if is_premium:
            premium_button = Button(
                label="Premium機能解放済み",
                style=discord.ButtonStyle.success,
                disabled=False  # 追加可能なので有効
            )
            premium_button.callback = self.show_premium_extend_modal
        else:
            premium_button = PremiumButton()
        
        self.add_item(premium_button)
    
    async def show_premium_extend_modal(self, interaction: discord.Interaction):
        """Premium期間延長モーダルを表示"""
        modal = PremiumModal()
        await interaction.response.send_modal(modal)

class PremiumButton(Button):
    """Premium機能解放ボタン"""
    
    def __init__(self):
        super().__init__(
            label="Premium機能を解放する", 
            style=discord.ButtonStyle.secondary,
            emoji="✨"
        )
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        """Premium機能解放のコールバック"""
        try:
            # モーダルを表示
            modal = PremiumModal()
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            self.logger.error(f"Error in premium button callback: {e}")
            await interaction.response.send_message(
                "❌ Premium機能の処理中にエラーが発生しました。",
                ephemeral=True
            )

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
        super().__init__(style=discord.ButtonStyle.primary, label="実績を確認する")
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

# Premium機能の定期チェック関数（bot_config.pyに追加する用）
async def check_premium_expiry(bot):
    """Premium期限をチェックしてロールを削除"""
    try:
        from models.user import UserModel
        user_model = UserModel()
        
        # Premium期限チェックと日数減算
        expired_users = user_model.reduce_premium_days_and_get_expired()
        
        for user_id in expired_users:
            # ユーザーを取得
            user = bot.get_user(int(user_id))
            if user:
                # 全ギルドでロールを削除
                for guild in bot.guilds:
                    member = guild.get_member(int(user_id))
                    if member:
                        premium_role = discord.utils.get(guild.roles, name=PREMIUM_ROLE_NAME)
                        if premium_role and premium_role in member.roles:
                            await remove_role(member, PREMIUM_ROLE_NAME)
                            logging.info(f"Removed premium role from user {user_id} in guild {guild.id}")
        
        if expired_users:
            logging.info(f"Premium subscription expired for {len(expired_users)} users")
        
    except Exception as e:
        logging.error(f"Error in premium expiry check: {e}")