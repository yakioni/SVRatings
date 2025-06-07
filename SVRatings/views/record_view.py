import discord
from discord.ui import View, Button, Select
import asyncio
from typing import List, Optional
from sqlalchemy import desc
from models.user import UserModel
from models.season import SeasonModel
from models.match import MatchModel
import logging

# RecordViewModelは循環インポートを避けるため、必要な時にインポート

class CurrentSeasonRecordView(View):
    """現在シーズンの戦績表示View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        button = Button(label="現在のシーズン", style=discord.ButtonStyle.primary)
        
        async def button_callback(interaction):
            await self.show_class_select(interaction)
        
        button.callback = button_callback
        self.add_item(button)
    
    async def show_class_select(self, interaction: discord.Interaction):
        """クラス選択を表示"""
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        # latest_season_matched が False なら "未参加です" と返して終了
        if user and not user.latest_season_matched:
            await interaction.response.send_message("未参加です", ephemeral=True)
            return
        
        season_model = SeasonModel()
        season = season_model.get_current_season()
        
        if season:
            await interaction.response.send_message(
                content="クラスを選択してください:", 
                view=ClassSelectView(season_id=season.id), 
                ephemeral=True
            )
        else:
            await interaction.response.send_message("シーズンが見つかりません。", ephemeral=True)

class PastSeasonRecordView(View):
    """過去シーズンの戦績表示View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        button = Button(label="過去のシーズン", style=discord.ButtonStyle.secondary)
        
        async def button_callback(interaction):
            await self.show_season_select(interaction)
        
        button.callback = button_callback
        self.add_item(button)
    
    async def show_season_select(self, interaction: discord.Interaction):
        """シーズン選択を表示"""
        season_model = SeasonModel()
        seasons = season_model.get_past_seasons()
        
        options = [
            discord.SelectOption(label="全シーズン", value="all")
        ]
        
        used_values = set()
        for season in seasons:
            value = str(season.id)
            if value in used_values:
                # 重複を避けるためにユニークな値を生成
                value = f"{season.id}_{season.season_name}"
            options.append(discord.SelectOption(label=season.season_name, value=value))
            used_values.add(value)
        
        select = Select(placeholder="シーズンを選択してください...", options=options)
        
        async def select_callback(select_interaction):
            if not select_interaction.response.is_done():
                await select_interaction.response.defer(ephemeral=True)
            
            selected_season_id = select_interaction.data['values'][0]
            
            if selected_season_id == "all":
                # 全シーズンを選択した場合
                await select_interaction.followup.send(
                    content="クラスを選択してください:", 
                    view=ClassSelectView(season_id=None),
                    ephemeral=True
                )
            else:
                selected_season_id = int(selected_season_id.split('_')[0])
                user_model = UserModel()
                user = user_model.get_user_by_discord_id(str(select_interaction.user.id))
                
                if not user:
                    await select_interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
                    return
                
                # ユーザーが選択したシーズンに参加しているか確認
                season_model = SeasonModel()
                user_record = season_model.get_user_season_record(user.id, selected_season_id)
                
                if not user_record:
                    message = await select_interaction.followup.send("未参加です。", ephemeral=True)
                    await asyncio.sleep(10)
                    await message.delete()
                    return
                
                # ユーザーがシーズンに参加している場合、クラスを選択させる
                await select_interaction.followup.send(
                    content="クラスを選択してください:", 
                    view=ClassSelectView(season_id=selected_season_id),
                    ephemeral=True
                )
        
        select.callback = select_callback
        view = View()
        view.add_item(select)
        
        await interaction.response.send_message("シーズンを選択してください:", view=view, ephemeral=True)
        
        await asyncio.sleep(15)
        try:
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            pass

class Last50RecordView(View):
    """直近50戦の戦績表示View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        button = Button(label="直近50戦", style=discord.ButtonStyle.primary)
        
        async def button_callback(button_interaction):
            # RecordViewModelを遅延インポート
            from viewmodels.record_vm import RecordViewModel
            record_vm = RecordViewModel()
            await record_vm.show_recent50_stats(button_interaction, button_interaction.user.id)
        
        button.callback = button_callback
        self.add_item(button)

class ClassSelectView(View):
    """クラス選択View"""
    
    def __init__(self, season_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.add_item(ClassSelect(season_id))

class ClassSelect(Select):
    """クラス選択セレクト"""
    
    def __init__(self, season_id: Optional[int] = None):
        self.season_id = season_id
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # データベースからクラス名を取得
        user_model = UserModel()
        valid_classes = user_model.get_valid_classes()
        
        options = [
            discord.SelectOption(label="全クラス", value="all_classes")
        ] + [discord.SelectOption(label=cls) for cls in valid_classes]
        
        super().__init__(
            placeholder="クラスを選択してください...", 
            min_values=1, 
            max_values=2, 
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """クラス選択のコールバック"""
        selected_classes = self.values
        user_id = interaction.user.id
        
        # 全クラスと他のクラスが選ばれている場合のチェック
        if "all_classes" in selected_classes and len(selected_classes) > 1:
            await interaction.response.send_message(
                "全クラスと他のクラスを同時に選択することはできません。", 
                ephemeral=True
            )
            return
        
        # インタラクションのレスポンスを一度行う
        await interaction.response.defer(ephemeral=True)
        
        try:
            # RecordViewModelを遅延インポート
            from viewmodels.record_vm import RecordViewModel
            record_vm = RecordViewModel()
            
            if "all_classes" in selected_classes:
                if self.season_id:
                    await record_vm.show_season_stats(interaction, user_id, self.season_id)
                else:
                    await record_vm.show_all_time_stats(interaction, user_id)
            else:
                if len(selected_classes) == 2:
                    # 2つのクラスを選択した場合、クラスの組み合わせに完全一致する試合を取得
                    await record_vm.show_class_stats(interaction, user_id, selected_classes, self.season_id)
                else:
                    # 1つのクラスのみ選択した場合、そのクラスに関連する試合を取得
                    await record_vm.show_class_stats(interaction, user_id, selected_classes[0], self.season_id)
        
        except Exception as e:
            self.logger.error(f"Error in class selection callback: {e}")
            await interaction.followup.send("エラーが発生しました。", ephemeral=True)
        
        # インタラクションメッセージを削除する
        try:
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            pass

class PreviousSeasonRecordView(View):
    """前作シーズンの戦績表示View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        
        # 前作シーズンの選択肢を作成
        from config.database import get_session, OldSeason
        from sqlalchemy import desc
        
        session = get_session()
        try:
            seasons = session.query(OldSeason).filter(
                OldSeason.end_date.isnot(None)
            ).order_by(desc(OldSeason.id)).all()
            
            options = [
                discord.SelectOption(label=s.season_name, value=str(s.id))
                for s in seasons
            ]
        except Exception:
            options = [discord.SelectOption(label="データなし", value="no_data")]
        finally:
            session.close()
        
        self.add_item(PreviousRecordSeasonSelect(options))

class PreviousRecordSeasonSelect(Select):
    """前作シーズン選択セレクト"""
    
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(placeholder="前作シーズンを選択してください…", options=options)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        """前作シーズン選択のコールバック"""
        if self.values[0] == "no_data":
            await interaction.response.send_message("前作のデータがありません。", ephemeral=True)
            return
        
        season_id = int(self.values[0])
        
        # 過去シーズン用のクラス選択ビューへバトンタッチ
        await interaction.response.send_message(
            "クラスを1つまたは2つ選択してください:",
            view=ClassSelectView(season_id),
            ephemeral=True
        )

class MatchHistoryPaginatorView(View):
    """試合履歴のページネーションView"""
    
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=600)
        self.embeds = embeds
        self.current = 0
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="前へ", style=discord.ButtonStyle.primary)
    async def previous(self, button: Button, interaction: discord.Interaction):
        """前のページへ"""
        if self.current > 0:
            self.current -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="次へ", style=discord.ButtonStyle.primary)
    async def next(self, button: Button, interaction: discord.Interaction):
        """次のページへ"""
        if self.current < len(self.embeds) - 1:
            self.current += 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()
    
    async def on_timeout(self):
        """タイムアウト時の処理"""
        try:
            # ボタンを無効化
            for item in self.children:
                item.disabled = True
        except Exception as e:
            self.logger.error(f"Error in on_timeout: {e}")

class UserStatsDisplayView(View):
    """ユーザー統計表示View"""
    
    def __init__(self, user_data: dict, stats_data: dict):
        super().__init__(timeout=300)
        self.user_data = user_data
        self.stats_data = stats_data
    
    @discord.ui.button(label="詳細統計", style=discord.ButtonStyle.secondary)
    async def detailed_stats(self, button: Button, interaction: discord.Interaction):
        """詳細統計を表示"""
        embed = discord.Embed(
            title=f"{self.user_data['user_name']} の詳細統計",
            color=discord.Color.blue()
        )
        
        # 詳細な統計情報をEmbedに追加
        embed.add_field(
            name="基本情報",
            value=f"レート: {self.stats_data.get('rating', 'N/A')}\n"
                  f"順位: {self.stats_data.get('rank', 'N/A')}\n"
                  f"勝率: {self.stats_data.get('win_rate', 'N/A')}%",
            inline=True
        )
        
        embed.add_field(
            name="試合統計",
            value=f"総試合数: {self.stats_data.get('total_matches', 0)}\n"
                  f"勝利数: {self.stats_data.get('win_count', 0)}\n"
                  f"敗北数: {self.stats_data.get('loss_count', 0)}",
            inline=True
        )
        
        embed.add_field(
            name="連勝記録",
            value=f"現在の連勝: {self.stats_data.get('current_streak', 0)}\n"
                  f"最大連勝: {self.stats_data.get('max_streak', 0)}",
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="クラス別統計", style=discord.ButtonStyle.secondary)
    async def class_stats(self, button: Button, interaction: discord.Interaction):
        """クラス別統計を表示"""
        # クラス別統計の実装（必要に応じて）
        await interaction.response.send_message(
            "クラス別統計は実装予定です。", 
            ephemeral=True
        )