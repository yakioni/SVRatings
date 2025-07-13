import discord
from discord.ui import View, Button, Select
import asyncio
from typing import List, Optional
from sqlalchemy import desc
from models.user import UserModel
from models.season import SeasonModel
from models.match import MatchModel
import logging

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
        if user and not user['latest_season_matched']:
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
            value = str(season['id'])
            if value in used_values:
                # 重複を避けるためにユニークな値を生成
                value = f"{season['id']}_{season['season_name']}"
            options.append(discord.SelectOption(label=season['season_name'], value=value))
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
                user_record = season_model.get_user_season_record(user['id'], selected_season_id)
                
                # user_recordが存在するかどうかのみチェック（属性にはアクセスしない）
                if user_record is None:
                    message = await select_interaction.followup.send("未参加です。", ephemeral=True)
                    await asyncio.sleep(10)
                    try:
                        await message.delete()
                    except discord.errors.NotFound:
                        pass
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

class ClassSelectView(View):
    """クラス選択View（単一クラスまたは全クラスのみ選択可能）"""
    
    def __init__(self, season_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.add_item(ClassSelect(season_id))

class ClassSelect(Select):
    """クラス選択セレクト（単一クラスまたは全クラスのみ選択可能）"""
    
    def __init__(self, season_id: Optional[int] = None):
        self.season_id = season_id
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # データベースからクラス名を取得
        user_model = UserModel()
        valid_classes = user_model.get_valid_classes()
        
        options = [
            discord.SelectOption(label="全クラス", value="all_classes")
        ] + [discord.SelectOption(label=cls, value=cls) for cls in valid_classes]
        
        super().__init__(
            placeholder="クラスを選択してください...", 
            min_values=1, 
            max_values=1,  # 1つのみ選択可能に変更
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """クラス選択のコールバック"""
        selected_class = self.values[0]
        user_id = interaction.user.id
        
        # インタラクションのレスポンスを一度行う
        await interaction.response.defer(ephemeral=True)
        
        try:
            # RecordViewModelを遅延インポート
            from viewmodels.record_vm import RecordViewModel
            record_vm = RecordViewModel()
            
            if selected_class == "all_classes":
                if self.season_id:
                    await record_vm.show_season_stats(interaction, user_id, self.season_id)
                else:
                    await record_vm.show_all_time_stats(interaction, user_id)
            else:
                # 単一クラスを選択した場合
                await record_vm.show_class_stats(interaction, user_id, selected_class, self.season_id)
        
        except Exception as e:
            self.logger.error(f"Error in class selection callback: {e}")
            await interaction.followup.send("エラーが発生しました。", ephemeral=True)
        
        # インタラクションメッセージを削除する
        try:
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            pass

class Last50RecordView(View):
    """直近50戦の戦績表示View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Last50RecordButton())

class Last50RecordButton(Button):
    """直近50戦戦績表示ボタン"""
    
    def __init__(self):
        super().__init__(label="直近50戦の戦績", style=discord.ButtonStyle.primary)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        """直近50戦戦績表示のコールバック"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # MatchModelを使用して直近50戦のデータを取得
            from models.match import MatchModel
            from models.user import UserModel
            
            user_model = UserModel()
            match_model = MatchModel()
            
            # ユーザー情報を取得
            user_data = user_model.get_user_by_discord_id(str(interaction.user.id))
            if not user_data:
                await interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
                return
            
            # user_dataが辞書かオブジェクトかを判定して適切にアクセス
            def get_attr(data, attr_name, default=None):
                if isinstance(data, dict):
                    return data.get(attr_name, default)
                else:
                    return getattr(data, attr_name, default)
            
            user_id = get_attr(user_data, 'id')
            user_name = get_attr(user_data, 'user_name')
            
            # 試合履歴を取得（50戦のみ）
            matches = match_model.get_user_match_history(user_id, 50)
            
            # 完了した試合のみフィルタリング
            completed_matches = []
            for match in matches:
                if (match.get('winner_user_id') is not None and 
                    match.get('after_user1_rating') is not None and 
                    match.get('after_user2_rating') is not None):
                    completed_matches.append(match)
            
            if not completed_matches:
                await interaction.followup.send("完了した試合履歴が見つかりません。", ephemeral=True)
                return
            
            # Embedを作成して試合履歴を表示
            embeds = []
            current_embed = None
            matches_per_embed = 10
            
            for i, match in enumerate(completed_matches):
                # 10試合ごとに新しいEmbedを作成
                if i % matches_per_embed == 0:
                    current_embed = discord.Embed(
                        title=f"{user_name} の直近50戦 (Page {i//matches_per_embed + 1})",
                        color=discord.Color.blue()
                    )
                    embeds.append(current_embed)
                
                # 対戦相手名を取得
                if match['user1_id'] == user_id:
                    opponent_data = user_model.get_user_by_id(match['user2_id'])
                    user_rating_change = match.get('user1_rating_change', 0)
                    after_rating = match.get('after_user1_rating')
                    before_rating = match.get('before_user1_rating')
                    user_won = match['winner_user_id'] == user_id
                else:
                    opponent_data = user_model.get_user_by_id(match['user1_id'])
                    user_rating_change = match.get('user2_rating_change', 0)
                    after_rating = match.get('after_user2_rating')
                    before_rating = match.get('before_user2_rating')
                    user_won = match['winner_user_id'] == user_id
                
                opponent_name = get_attr(opponent_data, 'user_name', 'Unknown') if opponent_data else 'Unknown'
                
                # None値チェックとデフォルト値設定
                if user_rating_change is None:
                    user_rating_change = 0
                if after_rating is None:
                    after_rating = 0
                if before_rating is None:
                    before_rating = 0
                
                # 試合結果の表示
                result_emoji = "🔵" if user_won else "🔴"
                result_text = "勝利" if user_won else "敗北"
                rating_change_str = f"{user_rating_change:+.0f}" if user_rating_change != 0 else "±0"
                
                # 使用クラス情報を取得（新しいデータベース構造対応）
                if match['user1_id'] == user_id:
                    user_class = match.get('user1_selected_class', 'Unknown')
                else:
                    user_class = match.get('user2_selected_class', 'Unknown')
                
                # Noneや空文字列の場合はUnknownに設定
                if not user_class:
                    user_class = 'Unknown'
                
                field_value = (
                    f"vs {opponent_name}\n"
                    f"結果: {result_text}\n"
                    f"使用クラス: {user_class}\n"
                    f"レート変動: {rating_change_str}\n"
                    f"試合後レート: {after_rating:.0f}"
                )
                
                # 日付のフォーマット
                match_date = match.get('match_date', '')
                if match_date:
                    match_date = match_date[:16]
                else:
                    match_date = 'Unknown'
                
                current_embed.add_field(
                    name=f"{result_emoji} {match_date}",
                    value=field_value,
                    inline=False
                )
            
            # 最初のEmbedを送信
            if embeds:
                message = await interaction.followup.send(embed=embeds[0], ephemeral=True)
                
                # 複数ページがある場合はページネーションを追加
                if len(embeds) > 1:
                    view = MatchHistoryPaginatorView(embeds)
                    await message.edit(view=view)
            
        except Exception as e:
            self.logger.error(f"Error displaying last 50 matches: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send("戦績の取得中にエラーが発生しました。", ephemeral=True)

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