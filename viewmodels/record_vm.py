import discord
import asyncio
import matplotlib.pyplot as plt
import io
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import logging

class RecordViewModel:
    """戦績関連のビジネスロジック"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 遅延初期化用の変数
        self._user_model = None
        self._season_model = None
        self._match_model = None
    
    @property
    def user_model(self):
        """UserModelの遅延ロード"""
        if self._user_model is None:
            from models.user import UserModel
            self._user_model = UserModel()
        return self._user_model
    
    @property
    def season_model(self):
        """SeasonModelの遅延ロード"""
        if self._season_model is None:
            from models.season import SeasonModel
            self._season_model = SeasonModel()
        return self._season_model
    
    @property
    def match_model(self):
        """MatchModelの遅延ロード"""
        if self._match_model is None:
            from models.match import MatchModel
            self._match_model = MatchModel()
        return self._match_model
    
    async def show_all_time_stats(self, interaction: discord.Interaction, user_id: int):
        """全シーズン累計の統計を表示"""
        user = self.user_model.get_user_by_discord_id(str(user_id))
        if not user:
            message = await interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
            await self._delete_message_after_delay(message, 10)
            return
        
        # user_season_recordから全シーズンの勝敗数を集計
        records = self.season_model.get_user_all_season_records(user['id'])
        total_win_count = sum(record.win_count for record in records)
        total_loss_count = sum(record.loss_count for record in records)
        total_count = total_win_count + total_loss_count
        win_rate = (total_win_count / total_count) * 100 if total_count > 0 else 0
        
        message = await interaction.followup.send(
            f"{user['user_name']} の全シーズン勝率: {win_rate:.2f}%\n"
            f"{total_count}戦   {total_win_count}勝-{total_loss_count}敗",
            ephemeral=True
        )
        await self._delete_message_after_delay(message, 10)
    
    async def show_season_stats(self, interaction: discord.Interaction, user_id: int, season_id: int):
        """指定されたシーズンの統計を表示"""
        user = self.user_model.get_user_by_discord_id(str(user_id))
        if not user:
            message = await interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
            await self._delete_message_after_delay(message, 10)
            return
        
        # シーズン情報を取得
        season_data = self.season_model.get_season_by_id(season_id)
        if not season_data:
            await interaction.followup.send("指定されたシーズンが見つかりません。", ephemeral=True)
            return
        
        season_name = season_data['season_name']
        
        # 最新シーズンかどうかを判定
        current_season_name = self.season_model.get_current_season_name()
        is_latest_season = (season_name == current_season_name if current_season_name else False)
        
        if is_latest_season:
            # 最新シーズンの場合、userテーブルからデータを取得
            win_count = user['win_count']
            loss_count = user['loss_count']
            total_count = win_count + loss_count
            win_rate = (win_count / total_count) * 100 if total_count > 0 else 0
            
            # 最新シーズンのレートと順位
            final_rating = user['rating']
            rank = self.user_model.get_user_rank(str(user_id))
        else:
            # 過去シーズンの場合、UserSeasonRecordからデータを取得
            past_record = self.season_model.get_user_season_record(user['id'], season_id)
            if not past_record:
                await interaction.followup.send("過去シーズンのレコードが見つかりません。", ephemeral=True)
                return
            
            final_rating = past_record.rating
            rank = past_record.rank
            win_count = past_record.win_count
            loss_count = past_record.loss_count
            total_count = win_count + loss_count
            win_rate = (win_count / total_count) * 100 if total_count > 0 else 0
        
        message = await interaction.followup.send(
            f"{user['user_name']} のシーズン {season_name} 統計:\n"
            f"勝率: {win_rate:.2f}% ({total_count}戦 {win_count}勝-{loss_count}敗)\n"
            f"レート: {final_rating:.2f}\n"
            f"順位: {rank}位",
            ephemeral=True
        )
        await self._delete_message_after_delay(message, 10)
    
    async def show_class_stats(self, interaction: discord.Interaction, user_id: int, 
                             selected_classes, season_id: Optional[int] = None):
        """指定されたクラスでの戦績を表示"""
        user = self.user_model.get_user_by_discord_id(str(user_id))
        if not user:
            message = await interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
            await self._delete_message_after_delay(message, 300)
            return
        
        # シーズン名を取得
        season_name = None
        if season_id is not None:
            season_data = self.season_model.get_season_by_id(season_id)
            season_name = season_data['season_name'] if season_data else None
        
        # クラスの処理に応じて適切なメソッドを呼び出す
        if isinstance(selected_classes, list) and len(selected_classes) == 2:
            # 2つのクラスの組み合わせ - レガシーメソッドを使用
            matches = self.match_model.get_user_class_matches_legacy(user['id'], selected_classes, season_name)
            selected_class_str = f"{selected_classes[0]} と {selected_classes[1]}"
        elif isinstance(selected_classes, list) and len(selected_classes) == 1:
            # 単一クラス（リスト形式）- 新しいメソッドを使用
            selected_class = selected_classes[0]
            matches = self.match_model.get_user_class_matches(user['id'], selected_class, season_name)
            selected_class_str = selected_class
        else:
            # 単一クラス（文字列形式）- 新しいメソッドを使用
            selected_class = selected_classes
            matches = self.match_model.get_user_class_matches(user['id'], selected_class, season_name)
            selected_class_str = selected_class
        
        # 勝敗数の計算 - 辞書形式のデータなので辞書のキーでアクセス
        win_count = sum(1 for match in matches if match['winner_user_id'] == user['id'])
        total_count = len(matches)
        loss_count = total_count - win_count
        win_rate = (win_count / total_count) * 100 if total_count > 0 else 0
        
        message = await interaction.followup.send(
            f"{user['user_name']} の {selected_class_str} クラスでの戦績:\n"
            f"勝率: {win_rate:.2f}%\n"
            f"{total_count}戦   {win_count}勝-{loss_count}敗", 
            ephemeral=True
        )
        await self._delete_message_after_delay(message, 300)
    
    def totalize_season(self, season_id: int) -> Dict[str, Any]:
        """シーズン終了時に全ユーザーのシーズン統計を保存"""
        return self.season_model.finalize_season(season_id)
    
    async def _delete_message_after_delay(self, message: discord.Message, delay: int):
        """指定時間後にメッセージを削除"""
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except discord.errors.NotFound:
            pass
        except Exception as e:
            self.logger.error(f"Error deleting message: {e}")