"""
戦績表示用のView（前作データベース対応も含む）
"""
import discord
from discord.ui import View, Button, Select
import asyncio
import logging
from typing import Dict, List, Optional
from viewmodels.record_vm import RecordViewModel

class CurrentSeasonRecordView(View):
    """現在シーズンの戦績表示用のView"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.viewmodel = RecordViewModel()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="現在シーズンの戦績を見る", style=discord.ButtonStyle.primary)
    async def show_current_record(self, button: Button, interaction: discord.Interaction):
        """現在シーズン戦績表示ボタン"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            discord_id = str(interaction.user.id)
            record = self.viewmodel.get_current_season_record(discord_id)
            
            if not record:
                await interaction.followup.send(
                    "現在シーズンの戦績が見つかりませんでした。まず登録を行ってください。", 
                    ephemeral=True
                )
                return
            
            message = self.viewmodel.format_current_season_record_message(record)
            await interaction.followup.send(message, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in show_current_record: {e}")
            await interaction.followup.send(
                "エラーが発生しました。時間をおいて再試行してください。", 
                ephemeral=True
            )

class PastSeasonRecordView(View):
    """今作の過去シーズン戦績表示用のView（beyond_user_season_recordテーブル）"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="今作の過去シーズン戦績を見る", style=discord.ButtonStyle.secondary)
    async def show_past_record(self, button: Button, interaction: discord.Interaction):
        """今作過去シーズン戦績表示ボタン"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # TODO: 今作の過去シーズン戦績機能を実装
            # beyond_user_season_record テーブルを参照する
            await interaction.followup.send(
                "今作の過去シーズン戦績機能は実装予定です。", 
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error in show_past_record: {e}")
            await interaction.followup.send(
                "エラーが発生しました。時間をおいて再試行してください。", 
                ephemeral=True
            )

class LegacyRecordView(View):
    """前作戦績表示用のView（user_season_recordテーブル）"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.viewmodel = RecordViewModel()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="前作戦績を見る", style=discord.ButtonStyle.secondary)
    async def show_legacy_record(self, button: Button, interaction: discord.Interaction):
        """前作戦績表示ボタン"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            discord_id = str(interaction.user.id)
            
            # 前作のシーズン戦績を取得
            records = self.viewmodel.get_legacy_user_season_records(discord_id)
            
            if not records:
                await interaction.followup.send(
                    "前作のシーズン戦績が見つかりませんでした。", 
                    ephemeral=True
                )
                return
            
            # 戦績一覧メッセージを作成（現在シーズンと同じ構成）
            user_name = records[0]['user_name'] if records else interaction.user.display_name
            message = self.viewmodel.format_legacy_season_records_message(records, user_name)
            
            await interaction.followup.send(message, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in show_legacy_record: {e}")
            await interaction.followup.send(
                "エラーが発生しました。時間をおいて再試行してください。", 
                ephemeral=True
            )



# ===== 前作データベース対応のViewクラス =====

class LegacyRankingView(View):
    """前作ランキング表示用のView"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.viewmodel = RecordViewModel()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="前作ランキングを見る", style=discord.ButtonStyle.primary)
    async def show_legacy_ranking(self, button: Button, interaction: discord.Interaction):
        """前作ランキング表示ボタン"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 利用可能なシーズンを取得
            seasons = self.viewmodel.get_legacy_available_seasons()
            
            if not seasons:
                await interaction.followup.send(
                    "前作のシーズンデータが見つかりませんでした。", 
                    ephemeral=True
                )
                return
            
            # シーズン選択用のSelectを作成
            select_view = LegacyRankingSeasonSelectView(seasons)
            await interaction.followup.send(
                "表示したいシーズンを選択してください：", 
                view=select_view, 
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error in show_legacy_ranking: {e}")
            await interaction.followup.send(
                "エラーが発生しました。時間をおいて再試行してください。", 
                ephemeral=True
            )

class LegacyRankingSeasonSelectView(View):
    """前作ランキング用シーズン選択View"""
    
    def __init__(self, seasons: List[Dict]):
        super().__init__(timeout=300)  # 5分でタイムアウト
        self.seasons = seasons
        self.viewmodel = RecordViewModel()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # シーズン選択用のSelectを追加
        if seasons:
            self.add_item(LegacyRankingSeasonSelect(seasons))
    
    async def on_timeout(self):
        """タイムアウト時の処理"""
        for item in self.children:
            item.disabled = True

class LegacyRankingSeasonSelect(Select):
    """前作ランキング用シーズン選択Select"""
    
    def __init__(self, seasons: List[Dict]):
        self.seasons = seasons
        self.viewmodel = RecordViewModel()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Selectのオプションを作成
        options = []
        for season in seasons[:25]:  # Discordの制限により最大25個
            options.append(
                discord.SelectOption(
                    label=season['season_name'],
                    value=str(season['id']),
                    description=f"シーズンID: {season['id']}"
                )
            )
        
        super().__init__(
            placeholder="シーズンを選択...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """シーズン選択時の処理"""
        try:
            await interaction.response.defer()
            
            season_id = int(self.values[0])
            
            # TOP100ランキングを取得
            ranking, _ = self.viewmodel.get_legacy_season_ranking(season_id, page=1, per_page=100)
            
            # シーズン情報を取得
            season_info = None
            for season in self.seasons:
                if season['id'] == season_id:
                    season_info = season
                    break
            
            if not season_info:
                await interaction.followup.send("シーズン情報が見つかりませんでした。", ephemeral=True)
                return
            
            # ランキングメッセージを作成
            message = self.viewmodel.format_legacy_ranking_message(ranking, season_info)
            await interaction.followup.send(message, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error in ranking season select callback: {e}")
            await interaction.followup.send("エラーが発生しました。", ephemeral=True)