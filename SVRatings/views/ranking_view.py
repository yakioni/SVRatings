import discord
from discord.ui import View, Button, Select
import asyncio
from typing import List, Dict, Any
from sqlalchemy import desc
from viewmodels.ranking_vm import RankingViewModel
from models.season import SeasonModel
from utils.helpers import create_embed_pages
import logging

class RankingView(View):
    """現在シーズンのランキング表示View"""
    
    def __init__(self, ranking_vm: RankingViewModel):
        super().__init__(timeout=None)
        self.ranking_vm = ranking_vm
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # リクエストキューと処理タスク
        self.request_queue = asyncio.Queue()
        self.processing_task = asyncio.create_task(self.process_queue())
        
        # セマフォで同時リクエストを制限
        self.semaphore = asyncio.Semaphore(5)
    
    async def process_queue(self):
        """リクエストキューを処理するタスク"""
        while True:
            try:
                requests = []
                while not self.request_queue.empty():
                    requests.append(await self.request_queue.get())
                if requests:
                    await asyncio.gather(*(self.handle_request(interaction) for interaction in requests))
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in process_queue: {e}")
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """インタラクションチェック"""
        await interaction.response.defer(ephemeral=True)
        await self.request_queue.put(interaction)
        return True
    
    async def handle_request(self, interaction: discord.Interaction):
        """リクエストを処理"""
        async with self.semaphore:
            try:
                custom_id = interaction.data.get('custom_id')
                if custom_id == "win_streak_ranking":
                    await self.show_win_streak_ranking(interaction)
                elif custom_id == "win_rate_ranking":
                    await self.show_win_rate_ranking(interaction)
                elif custom_id == "rating_ranking":
                    await self.show_rating_ranking(interaction)
            except Exception as e:
                self.logger.error(f"Error handling request: {e}")
    
    @discord.ui.button(label="連勝数ランキング", style=discord.ButtonStyle.primary, custom_id="win_streak_ranking")
    async def win_streak_button(self, button: Button, interaction: discord.Interaction):
        pass  # 実際の処理はhandle_requestで行う
    
    @discord.ui.button(label="勝率ランキング", style=discord.ButtonStyle.primary, custom_id="win_rate_ranking")
    async def win_rate_button(self, button: Button, interaction: discord.Interaction):
        pass  # 実際の処理はhandle_requestで行う
    
    @discord.ui.button(label="レーティングランキング", style=discord.ButtonStyle.primary, custom_id="rating_ranking")
    async def rating_button(self, button: Button, interaction: discord.Interaction):
        pass  # 実際の処理はhandle_requestで行う
    
    async def show_win_streak_ranking(self, interaction: discord.Interaction):
        """連勝数ランキングを表示"""
        ranking = await self.ranking_vm.get_cached_ranking("win_streak")
        from models.season import SeasonModel
        season_model = SeasonModel()
        current_season_name = season_model.get_current_season_name()
        
        embed = discord.Embed(
            title=f"【{current_season_name or '現在'}】連勝数ランキング", 
            color=discord.Color.red()
        )
        
        await self.send_ranking_embed(embed, ranking, interaction, "win_streak")
    
    async def show_win_rate_ranking(self, interaction: discord.Interaction):
        """勝率ランキングを表示"""
        ranking = await self.ranking_vm.get_cached_ranking("win_rate")
        from models.season import SeasonModel
        season_model = SeasonModel()
        current_season_name = season_model.get_current_season_name()
        
        embed = discord.Embed(
            title=f"【{current_season_name or '現在'}】勝率ランキングTOP16", 
            color=discord.Color.green()
        )
        
        await self.send_ranking_embed(embed, ranking, interaction, "win_rate")
    
    async def show_rating_ranking(self, interaction: discord.Interaction):
        """レーティングランキングを表示"""
        ranking = await self.ranking_vm.get_cached_ranking("rating")
        from models.season import SeasonModel
        season_model = SeasonModel()
        current_season_name = season_model.get_current_season_name()
        
        embed = discord.Embed(
            title=f"【{current_season_name or '現在'}】レーティングランキング", 
            color=discord.Color.blue()
        )
        
        await self.send_ranking_embed(embed, ranking, interaction, "rating")
    
    async def send_ranking_embed(self, embed: discord.Embed, ranking: List[Dict], 
                               interaction: discord.Interaction, ranking_type: str):
        """ランキングEmbedを送信"""
        messages = []
        
        for i, record in enumerate(ranking, start=1):
            if ranking_type == "win_streak":
                embed.add_field(
                    name=f"**``` {i}位 ```**", 
                    value=f"{record['user_name']} - 連勝数 : {record['max_win_streak']}", 
                    inline=False
                )
            elif ranking_type == "win_rate":
                stayed_text = " (stayed)" if record['used_stayed'] else ""
                embed.add_field(
                    name=f"**``` {i}位 ```**",
                    value=f"{record['user_name']} - 勝率 : {record['win_rate']:.2f}% "
                          f"({record['win_count']}勝 {record['loss_count']}敗){stayed_text}",
                    inline=False
                )
            elif ranking_type == "rating":
                stayed_text = " (stayed)" if record['is_stayed'] else ""
                embed.add_field(
                    name=f"**``` {i}位 ```**",
                    value=f"{record['user_name']} - レート : {record['rating']}{stayed_text}",
                    inline=False
                )
            
            # Embed1メッセージあたり25フィールド制限
            if len(embed.fields) == 25:
                message = await interaction.followup.send(embed=embed, ephemeral=True)
                messages.append(message)
                embed.clear_fields()
        
        if len(embed.fields) > 0:
            message = await interaction.followup.send(embed=embed, ephemeral=True)
            messages.append(message)
        
        # メッセージを一定時間後に削除
        asyncio.create_task(self.delete_messages_after_delay(messages))
    
    async def delete_messages_after_delay(self, messages: List[discord.Message]):
        """メッセージを一定時間後に削除"""
        await asyncio.sleep(300)  # 5分後
        for msg in messages:
            try:
                await msg.delete()
            except discord.errors.NotFound:
                pass

class RankingButtonView(View):
    """過去シーズンランキング選択View"""
    
    def __init__(self, ranking_vm: RankingViewModel):
        super().__init__(timeout=None)
        self.ranking_vm = ranking_vm
        # レーティング、連勝数、勝率のボタンを追加
        self.add_item(RankingButton(ranking_vm, "レーティングランキング", "rate"))
        self.add_item(RankingButton(ranking_vm, "連勝数ランキング", "win_streak"))
        self.add_item(RankingButton(ranking_vm, "勝率ランキング", "win_rate"))

class RankingButton(Button):
    """ランキングタイプ選択ボタン"""
    
    def __init__(self, ranking_vm: RankingViewModel, label: str, ranking_type: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.ranking_type = ranking_type
        self.ranking_vm = ranking_vm
    
    async def callback(self, interaction: discord.Interaction):
        """ボタンコールバック"""
        # ユーザーがボタンを押したらシーズン選択ビューを表示
        view = PastRankingSelectView(self.ranking_vm, self.ranking_type)
        await interaction.response.send_message("シーズンを選択してください:", view=view, ephemeral=True)

class PastRankingSelectView(View):
    """過去シーズン選択View"""
    
    def __init__(self, ranking_vm: RankingViewModel, ranking_type: str):
        super().__init__(timeout=None)
        self.ranking_vm = ranking_vm
        self.add_item(PastRankingSelect(ranking_vm, ranking_type))

class PastRankingSelect(Select):
    """過去シーズン選択セレクト"""
    
    def __init__(self, ranking_vm: RankingViewModel, ranking_type: str):
        self.ranking_vm = ranking_vm
        self.ranking_type = ranking_type
        
        # 過去のシーズンを取得
        season_model = SeasonModel()
        seasons = season_model.get_past_seasons()
        
        # 選択肢を作成
        if seasons:
            options = [
                discord.SelectOption(label=season.season_name, value=str(season.id)) 
                for season in seasons
            ]
            placeholder = "過去のシーズンを選択してください..."
            disabled = False
        else:
            options = [
                discord.SelectOption(label="過去のシーズンはありません", value="no_season")
            ]
            placeholder = "過去のシーズンはありません"
            disabled = True
        
        super().__init__(placeholder=placeholder, options=options, disabled=disabled)
    
    async def callback(self, interaction: discord.Interaction):
        """シーズン選択のコールバック"""
        if self.values[0] == "no_season":
            await interaction.response.send_message("過去のシーズンはありません。", ephemeral=True)
            return
        
        season_id = int(self.values[0])
        season_model = SeasonModel()
        season = season_model.get_season_by_id(season_id)
        season_name = season.season_name if season else "Unknown"
        
        await interaction.response.defer(ephemeral=True)
        
        # 選択されたシーズンのランキングを表示
        if self.ranking_type == "rate":
            await self.show_rate_ranking(interaction, season_id, season_name)
        elif self.ranking_type == "win_streak":
            await self.show_win_streak_ranking(interaction, season_id, season_name)
        elif self.ranking_type == "win_rate":
            await self.show_win_rate_ranking(interaction, season_id, season_name)
        
        # メッセージを削除
        await asyncio.sleep(10)
        try:
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            pass
    
    async def show_rate_ranking(self, interaction: discord.Interaction, season_id: int, season_name: str):
        """過去シーズンのレーティングランキングを表示"""
        ranking = self.ranking_vm.get_past_season_rating_ranking(season_id)
        embed = discord.Embed(title=f"【{season_name}】レーティングランキング", color=discord.Color.blue())
        await self.send_ranking_embed(embed, ranking, interaction, "rating")
    
    async def show_win_rate_ranking(self, interaction: discord.Interaction, season_id: int, season_name: str):
        """過去シーズンの勝率ランキングを表示"""
        ranking = self.ranking_vm.get_past_season_win_rate_ranking(season_id)
        embed = discord.Embed(title=f"【{season_name}】勝率ランキング", color=discord.Color.green())
        await self.send_ranking_embed(embed, ranking, interaction, "win_rate")
    
    async def show_win_streak_ranking(self, interaction: discord.Interaction, season_id: int, season_name: str):
        """過去シーズンの連勝数ランキングを表示"""
        ranking = self.ranking_vm.get_past_season_win_streak_ranking(season_id)
        embed = discord.Embed(title=f"【{season_name}】連勝数ランキング", color=discord.Color.red())
        await self.send_ranking_embed(embed, ranking, interaction, "win_streak")
    
    async def send_ranking_embed(self, embed: discord.Embed, ranking: List[Dict], 
                               interaction: discord.Interaction, ranking_type: str):
        """ランキングをEmbedで表示し、25人ずつ送信する"""
        messages = []
        
        for i, record in enumerate(ranking, start=1):
            if ranking_type == "rating":
                embed.add_field(
                    name=f"**``` {i}位 ```**",
                    value=f"{record['user_name']} - レート : {record['rating']}",
                    inline=False
                )
            elif ranking_type == "win_rate":
                embed.add_field(
                    name=f"**``` {i}位 ```**",
                    value=f"{record['user_name']} - 勝率 : {record['win_rate']:.2f}% "
                          f"({record['total_matches']}戦 {record['win_count']}勝-{record['loss_count']}敗)",
                    inline=False
                )
            elif ranking_type == "win_streak":
                embed.add_field(
                    name=f"**``` {i}位 ```**",
                    value=f"{record['user_name']} - 連勝数 : {record['max_win_streak']}",
                    inline=False
                )
            
            # Embedのフィールドが25個になったら送信
            if len(embed.fields) == 25:
                message = await interaction.followup.send(embed=embed, ephemeral=True)
                messages.append(message)
                embed.clear_fields()
        
        # 残りのフィールドがある場合送信
        if len(embed.fields) > 0:
            message = await interaction.followup.send(embed=embed, ephemeral=True)
            messages.append(message)
        
        # 5分後にすべてのメッセージを削除
        await asyncio.sleep(300)
        for msg in messages:
            try:
                await msg.delete()
            except discord.errors.NotFound:
                pass

class PastSeasonRatingView(View):
    """前作シーズンのレーティングランキングView"""
    
    def __init__(self, ranking_vm: RankingViewModel):
        super().__init__(timeout=None)
        self.add_item(PastSeasonRatingSelect(ranking_vm))

class PastSeasonRatingSelect(Select):
    """前作シーズンのレーティング選択"""
    
    def __init__(self, ranking_vm: RankingViewModel):
        self.ranking_vm = ranking_vm
        
        # 前作のシーズンを取得（旧システムのテーブルから）
        from config.database import get_session, OldSeason
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
        
        super().__init__(placeholder="前作シーズンを選択してください…", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        """前作シーズン選択のコールバック"""
        if self.values[0] == "no_data":
            await interaction.response.send_message("前作のデータがありません。", ephemeral=True)
            return
        
        season_id = int(self.values[0])
        
        # 前作のデータを取得（実装が必要）
        from config.database import get_session, OldSeason, OldUserSeasonRecord, User
        session = get_session()
        try:
            season = session.query(OldSeason).get(season_id)
            season_name = season.season_name if season else "Unknown"
            
            # TOP100のレーティング順取得
            records = session.query(OldUserSeasonRecord).filter_by(
                season_id=season_id
            ).order_by(desc(OldUserSeasonRecord.rating)).limit(100).all()
            
            embed = discord.Embed(
                title=f"【{season_name}】レーティングランキング",
                color=discord.Color.blue()
            )
            
            for i, rec in enumerate(records, start=1):
                user = session.query(User).get(rec.user_id)
                if user:
                    embed.add_field(
                        name=f"**``` {i}位 ```**",
                        value=f"{user.user_name} - レート : {int(rec.rating)}",
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message("データの取得に失敗しました。", ephemeral=True)
            logging.error(f"Error in PastSeasonRatingSelect callback: {e}")
        finally:
            session.close()