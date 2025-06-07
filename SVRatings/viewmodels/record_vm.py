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
        records = self.season_model.get_user_all_season_records(user.id)
        total_win_count = sum(record.win_count for record in records)
        total_loss_count = sum(record.loss_count for record in records)
        total_count = total_win_count + total_loss_count
        win_rate = (total_win_count / total_count) * 100 if total_count > 0 else 0
        
        message = await interaction.followup.send(
            f"{user.user_name} の全シーズン勝率: {win_rate:.2f}%\n"
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
            win_count = user.win_count
            loss_count = user.loss_count
            total_count = win_count + loss_count
            win_rate = (win_count / total_count) * 100 if total_count > 0 else 0
            
            # 最新シーズンのレートと順位
            final_rating = user.rating
            rank = self.user_model.get_user_rank(str(user_id))
        else:
            # 過去シーズンの場合、UserSeasonRecordからデータを取得
            past_record = self.season_model.get_user_season_record(user.id, season_id)
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
            f"{user.user_name} のシーズン {season_name} 統計:\n"
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
        
        # クラスの処理
        if isinstance(selected_classes, list) and len(selected_classes) == 2:
            # 2つのクラスの組み合わせ
            matches = self.match_model.get_user_class_matches(user.id, selected_classes, season_name)
            selected_class_str = f"{selected_classes[0]} と {selected_classes[1]}"
        else:
            # 単一クラス
            selected_class = selected_classes[0] if isinstance(selected_classes, list) else selected_classes
            matches = self.match_model.get_user_class_matches(user.id, [selected_class], season_name)
            selected_class_str = selected_class
        
        # 勝敗数の計算
        win_count = sum(1 for match in matches if match.winner_user_id == user.id)
        total_count = len(matches)
        loss_count = total_count - win_count
        win_rate = (win_count / total_count) * 100 if total_count > 0 else 0
        
        message = await interaction.followup.send(
            f"{user.user_name} の {selected_class_str} クラスでの戦績:\n"
            f"勝率: {win_rate:.2f}%\n"
            f"{total_count}戦   {win_count}勝-{loss_count}敗", 
            ephemeral=True
        )
        await self._delete_message_after_delay(message, 300)
    
    async def show_recent50_stats(self, interaction: discord.Interaction, user_id: int):
        """最新のシーズンの直近50戦のレート推移のグラフと統計を表示"""
        # ユーザー情報の取得
        user = self.user_model.get_user_by_discord_id(str(user_id))
        if not user:
            await interaction.response.send_message("ユーザーが見つかりません。", ephemeral=True)
            return
        
        # 最新シーズンの取得
        latest_season = self.season_model.get_current_season()
        if not latest_season:
            await interaction.response.send_message("最新のシーズンが見つかりません。", ephemeral=True)
            return
        
        if not user.latest_season_matched:
            await interaction.response.send_message("未参加です", ephemeral=True)
            return
        
        # 自分のstay_flagと一致する試合のみ抽出
        matches = self.match_model.get_user_season_matches(
            user.id, latest_season.season_name, user.stay_flag
        )
        
        total_matches = len(matches)
        
        if total_matches >= 50:
            # 最新50戦を取得（降順→グラフ用に昇順に変換）
            latest_50_matches = matches[:50]
            matches_for_graph = list(reversed(latest_50_matches))
            matches_for_embed = latest_50_matches
            title_suffix = " (最新50戦)"
        else:
            # 試合数が50未満の場合
            matches_for_graph = list(reversed(matches))
            matches_for_embed = matches
            title_suffix = f" (最新{total_matches}戦)" if total_matches > 0 else ""
        
        # 初期レートの計算
        if total_matches < 50:
            initial_rating = 1500
        else:
            # 現在のレートから各試合の変動分を差し引く
            total_change = sum(
                match.user1_rating_change if match.user1_id == user.id else match.user2_rating_change
                for match in matches_for_graph
            )
            initial_rating = user.rating - total_change
        
        # レート推移と統計の計算
        ratings = [initial_rating]
        win_count = 0
        loss_count = 0
        class_stats = {}
        
        # deck_classテーブルからクラス名とIDのマッピングを取得
        valid_classes = self.user_model.get_valid_classes()
        
        for match in matches_for_graph:
            # 勝敗判定
            if match.winner_user_id == user.id:
                result = "WIN"
                win_count += 1
            else:
                result = "LOSE"
                loss_count += 1
            
            # レート変動
            rating_change = match.user1_rating_change if match.user1_id == user.id else match.user2_rating_change
            current_rating = ratings[-1] + rating_change
            ratings.append(current_rating)
            
            # 使用クラスの統計
            if match.user1_id == user.id:
                user_classes = (match.user1_class_a, match.user1_class_b)
            else:
                user_classes = (match.user2_class_a, match.user2_class_b)
            
            # クラス略称の取得
            from config.settings import CLASS_ABBREVIATIONS
            user_class_abbrs = []
            for class_name in user_classes:
                if class_name and class_name in valid_classes:
                    abbr = CLASS_ABBREVIATIONS.get(class_name, class_name)
                    user_class_abbrs.append(abbr)
            
            key = ','.join(sorted(user_class_abbrs))
            
            if key not in class_stats:
                class_stats[key] = {'win': 0, 'loss': 0}
            
            if result == "WIN":
                class_stats[key]['win'] += 1
            else:
                class_stats[key]['loss'] += 1
        
        total_count = win_count + loss_count
        win_rate = (win_count / total_count) * 100 if total_count > 0 else 0
        rank = self.user_model.get_user_rank(str(user_id))
        
        # グラフの作成
        try:
            # フォントの設定（環境に応じて調整）
            plt.rcParams['font.family'] = ['DejaVu Sans', 'Arial Unicode MS', 'Noto Sans CJK JP']
        except:
            pass  # フォント設定に失敗しても続行
        
        plt.figure(figsize=(10, 6))
        plt.plot(range(len(ratings)), ratings, marker='o')
        plt.title(f"レーティンググラフ{title_suffix}", fontsize=16)
        plt.xlabel("試合数", fontsize=12)
        plt.ylabel("レーティング", fontsize=12)
        
        min_rating = min(ratings)
        max_rating = max(ratings)
        y_min = (min_rating // 100) * 100 - 50
        y_max = ((max_rating + 99) // 100) * 100 + 50
        plt.ylim(y_min, y_max)
        plt.grid(True)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        # クラス統計メッセージの作成
        if class_stats:
            class_stats_message = "\n".join([
                f"{cls}　{stats['win']}勝-{stats['loss']}敗　"
                f"{(stats['win'] / (stats['win'] + stats['loss']) * 100):.2f}%"
                for cls, stats in class_stats.items()
            ])
        else:
            class_stats_message = "クラスごとの戦績はありません。"
        
        # 統計メッセージの作成
        stats_message = (
            f"最新シーズンの試合履歴{title_suffix}\n"
            f"{total_count}戦　{win_count}勝-{loss_count}敗　勝率: {win_rate:.2f}%\n\n"
            f"現在のレーティング: {ratings[-1]:.2f}\n\n"
            f"現在の順位: {rank}位\n\n"
            f"{class_stats_message}"
        )
        
        # 対戦履歴のエントリを作成（Embed用）
        match_entries = []
        for idx, match in enumerate(matches_for_embed, start=1):
            if match.winner_user_id == user.id:
                result = "**```WIN```**"
                spacing = "　"
            else:
                result = "**```LOSE```**"
                spacing = "  "
            
            # 対戦相手と使用クラスの情報
            if match.user1_id == user.id:
                opponent_id = match.user2_id
                rating_change = match.user1_rating_change
                user_classes = (match.user1_class_a, match.user1_class_b)
                opponent_classes = (match.user2_class_a, match.user2_class_b)
            else:
                opponent_id = match.user1_id
                rating_change = match.user2_rating_change
                user_classes = (match.user2_class_a, match.user2_class_b)
                opponent_classes = (match.user1_class_a, match.user1_class_b)
            
            opponent = self.user_model.get_user_by_id(opponent_id)
            opponent_name = opponent.user_name if opponent else "Unknown"
            
            from config.settings import CLASS_ABBREVIATIONS
            user_class_abbr = ','.join([
                CLASS_ABBREVIATIONS.get(c, c) for c in user_classes if c
            ])
            opponent_class_abbr = ','.join([
                CLASS_ABBREVIATIONS.get(c, c) for c in opponent_classes if c
            ])
            
            field_name = f"{result}{spacing}{opponent_name}"
            field_value = f"{user_class_abbr} vs {opponent_class_abbr} {rating_change:+.2f}"
            match_entries.append((field_name, field_value))
        
        # ページ分割
        pages = [match_entries[i:i+10] for i in range(0, len(match_entries), 10)]
        embeds = []
        
        for page_num, page_entries in enumerate(pages, start=1):
            embed = discord.Embed(
                title=f"{user.user_name} の直近の対戦履歴 - ページ {page_num}/{len(pages)}",
                color=discord.Color.blue()
            )
            for field_name, field_value in page_entries:
                embed.add_field(name=field_name, value=field_value, inline=False)
            embeds.append(embed)
        
        # メッセージの送信
        await interaction.response.send_message(stats_message, ephemeral=True)
        
        if embeds:
            from views.record_view import MatchHistoryPaginatorView
            view = MatchHistoryPaginatorView(embeds)
            graph_message = await interaction.followup.send(file=discord.File(buf, 'recent50.png'), ephemeral=True)
            history_message = await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)
            
            # 10分後にメッセージを削除
            await asyncio.sleep(600)
            try:
                await history_message.delete()
                await graph_message.delete()
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                pass
        else:
            graph_message = await interaction.followup.send(file=discord.File(buf, 'recent50.png'), ephemeral=True)
            await asyncio.sleep(600)
            try:
                await graph_message.delete()
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                pass
    
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