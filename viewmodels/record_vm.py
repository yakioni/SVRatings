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
        
        # user_season_recordから全シーズンの勝敗数を集計（セッション管理対応）
        def _get_all_season_records(session):
            from config.database import UserSeasonRecord
            records = session.query(UserSeasonRecord).filter_by(
                user_id=user['id']
            ).all()
            
            return [
                {
                    'win_count': record.win_count,
                    'loss_count': record.loss_count,
                    'total_matches': record.total_matches
                }
                for record in records
            ]
        
        records_data = self.season_model.safe_execute(_get_all_season_records)
        if not records_data:
            records_data = []
        
        total_win_count = sum(record['win_count'] for record in records_data)
        total_loss_count = sum(record['loss_count'] for record in records_data)
        total_count = total_win_count + total_loss_count
        win_rate = (total_win_count / total_count) * 100 if total_count > 0 else 0
        
        message = await interaction.followup.send(
            f"{user['user_name']} の全シーズン勝率: {win_rate:.2f}%\n"
            f"{total_count}戦   {total_win_count}勝-{total_loss_count}敗",
            ephemeral=True
        )
        await self._delete_message_after_delay(message, 10)
    
    async def show_date_range_stats(self, interaction: discord.Interaction, user_id: int, date_range: tuple):
        """指定された日付範囲の統計を表示"""
        user = self.user_model.get_user_by_discord_id(str(user_id))
        if not user:
            message = await interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
            await self._delete_message_after_delay(message, 10)
            return
        
        start_date, end_date = date_range
        
        # 日付範囲での試合を取得
        matches = self._get_matches_by_date_range(user['id'], start_date, end_date)
        
        # 勝敗数の計算
        win_count = sum(1 for match in matches if match['winner_user_id'] == user['id'])
        total_count = len(matches)
        loss_count = total_count - win_count
        win_rate = (win_count / total_count) * 100 if total_count > 0 else 0
        
        # 日付範囲の説明（時刻部分を除去）
        start_date_str = start_date[:10] if start_date else "開始日不明"
        end_date_str = end_date[:10] if end_date else "終了日不明"
        range_desc = f"{start_date_str} ～ {end_date_str}"
        
        # より詳細な統計情報
        if total_count > 0:
            # 最初と最後の試合日
            first_match_date = matches[-1]['match_date'][:10] if matches else "不明"
            last_match_date = matches[0]['match_date'][:10] if matches else "不明"
            
            stats_message = (
                f"**{user['user_name']} の期間戦績**\n"
                f" **期間:** {range_desc}\n"
                f" **総試合数:** {total_count}戦\n"
                f" **勝率:** {win_rate:.2f}% ({win_count}勝-{loss_count}敗)\n"
                f"**実際の試合期間:** {first_match_date} ～ {last_match_date}"
            )
        else:
            stats_message = (
                f"**{user['user_name']} の期間戦績**\n"
                f" **期間:** {range_desc}\n"
                f" **総試合数:** 0戦\n"
                f" この期間に試合記録はありません。"
            )
        
        message = await interaction.followup.send(stats_message, ephemeral=True)
        await self._delete_message_after_delay(message, 300)  # 5分後に削除
    
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
            # 過去シーズンの場合、UserSeasonRecordからデータを取得（セッション管理対応）
            def _get_past_record(session):
                from config.database import UserSeasonRecord
                record = session.query(UserSeasonRecord).filter_by(
                    user_id=user['id'], season_id=season_id
                ).first()
                
                if record:
                    return {
                        'rating': record.rating,
                        'rank': record.rank,
                        'win_count': record.win_count,
                        'loss_count': record.loss_count,
                        'total_matches': record.total_matches
                    }
                return None
            
            past_record = self.season_model.safe_execute(_get_past_record)
            if not past_record:
                await interaction.followup.send("過去シーズンのレコードが見つかりません。", ephemeral=True)
                return
            
            final_rating = past_record['rating']
            rank = past_record['rank']
            win_count = past_record['win_count']
            loss_count = past_record['loss_count']
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
    
    async def show_detailed_class_stats(self, interaction: discord.Interaction, user_id: int, 
                                    selected_classes: List[str], season_id: Optional[int] = None, 
                                    date_range: Optional[tuple] = None):
        """詳細なクラス戦績を表示（user_class、selected_classを考慮）"""
        user = self.user_model.get_user_by_discord_id(str(user_id))
        if not user:
            message = await interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
            await self._delete_message_after_delay(message, 300)
            return
        
        # シーズン名または日付範囲を取得
        filter_desc = None
        if season_id is not None:
            season_data = self.season_model.get_season_by_id(season_id)
            season_name = season_data['season_name'] if season_data else None
            filter_desc = f"シーズン {season_name}" if season_name else "指定シーズン"
        elif date_range is not None:
            start_date, end_date = date_range
            start_date_str = start_date[:10] if start_date else "開始日不明"
            end_date_str = end_date[:10] if end_date else "終了日不明"
            filter_desc = f"{start_date_str} ～ {end_date_str}"
            season_name = None
        else:
            season_name = None
            filter_desc = "全シーズン"
        
        # 単一クラスの場合の処理
        if len(selected_classes) == 1:
            # 分析データの取得（対戦相手のクラス別）- 専用メソッドを使用
            analysis_data = self._get_single_class_analysis_data(user['id'], selected_classes[0], season_id, date_range)
            
            if not analysis_data:
                message = await interaction.followup.send(
                    f"指定した条件での {selected_classes[0]} クラスの対戦データが見つかりませんでした。", 
                    ephemeral=True
                )
                await self._delete_message_after_delay(message, 300)
                return
            
            # 全体の統計を計算
            total_matches = sum(data['total_matches'] for data in analysis_data)
            total_wins = sum(data['my_wins'] for data in analysis_data)
            total_losses = sum(data['opponent_wins'] for data in analysis_data)
            overall_win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0
            
            # 勝率順にソート
            sorted_data = sorted(analysis_data, key=lambda x: (x['win_rate'], x['my_wins']), reverse=True)
            
            # メッセージの作成
            embed = discord.Embed(
                title=f"{user['user_name']} の {selected_classes[0]} 単体での詳細戦績",
                description=f"**対象:** {filter_desc}\n"
                        f"**使用クラス:** {selected_classes[0]}\n"
                        f"**総戦績:**{total_wins}勝-{total_losses}敗 {overall_win_rate:.2f}%",
                color=discord.Color.green()
            )
            
            # 対戦相手のクラス別戦績
            embed.add_field(name="", value="**【対戦相手のクラス別戦績】**", inline=False)
            
            for data in sorted_data:
                if data['total_matches'] > 0:  # 対戦がある場合のみ表示
                    embed.add_field(
                        name=f"vs {data['opponent_class']}",  # キー名を修正
                        value=(
                            f"{data['my_wins']}勝-{data['opponent_wins']}敗 ({data['win_rate']:.1f}%)"
                        ),
                        inline=True
                    )
            
            message = await interaction.followup.send(embed=embed, ephemeral=True)
            await self._delete_message_after_delay(message, 300)
        
        # 2クラス組合せの場合の処理（拡張版）
        elif len(selected_classes) == 2:
            # 分析データの取得（投げられたクラスの組合せと選択クラス別）
            analysis_data = self._get_analysis_data(selected_classes, season_name, date_range)
            
            if not analysis_data:
                message = await interaction.followup.send(
                    f"指定した条件での {selected_classes[0]} + {selected_classes[1]} の対戦データが見つかりませんでした。", 
                    ephemeral=True
                )
                await self._delete_message_after_delay(message, 300)
                return
            
            # 詳細戦績の取得
            if date_range is not None:
                matches = self._get_detailed_class_matches_by_date(user['id'], selected_classes, date_range[0], date_range[1])
            else:
                matches = self._get_detailed_class_matches(user['id'], selected_classes, season_name)
            
            # 全体の統計
            win_count = sum(1 for match in matches if match['winner_user_id'] == user['id'])
            total_count = len(matches)
            loss_count = total_count - win_count
            overall_win_rate = (win_count / total_count) * 100 if total_count > 0 else 0
            
            # 相手のクラス組合せごとに集計
            opponent_combo_stats = {}
            
            for data in analysis_data:
                combo_key = data['opponent_class_combo']
                if combo_key not in opponent_combo_stats:
                    opponent_combo_stats[combo_key] = {
                        'total_matches': 0,
                        'total_wins': 0,
                        'total_losses': 0,
                        'class_selection': {}  # 各クラスの選択回数と戦績
                    }
                
                stats = opponent_combo_stats[combo_key]
                stats['total_matches'] += data['total_matches']
                stats['total_wins'] += data['my_wins']
                stats['total_losses'] += data['opponent_wins']
                
                # 選択されたクラスごとの戦績
                selected = data['opponent_selected_class']
                if selected not in stats['class_selection']:
                    stats['class_selection'][selected] = {
                        'times_selected': 0,
                        'wins': 0,
                        'losses': 0
                    }
                
                stats['class_selection'][selected]['times_selected'] += data['total_matches']
                stats['class_selection'][selected]['wins'] += data['my_wins']
                stats['class_selection'][selected]['losses'] += data['opponent_wins']
            
            # 勝率順にソート
            sorted_combos = sorted(
                opponent_combo_stats.items(), 
                key=lambda x: (x[1]['total_wins'] / x[1]['total_matches'] if x[1]['total_matches'] > 0 else 0, x[1]['total_wins']), 
                reverse=True
            )
            
            # エンベッドの作成
            embeds = []
            embed = discord.Embed(
                title=f"{user['user_name']} の詳細戦績",
                description=(
                    f"**対象:** {filter_desc}\n"
                    f"**使用クラス組合せ:** {selected_classes[0]} + {selected_classes[1]}\n"
                    f"**全体勝率:** {overall_win_rate:.2f}%\n"
                    f"**総戦績:** {total_count}戦 {win_count}勝-{loss_count}敗"
                ),
                color=discord.Color.blue()
            )
            
            # 相手のクラス組合せごとに表示
            current_embed = embed
            field_count = 0
            
            for combo_tuple, stats in sorted_combos:
                if field_count >= 15:  # Embedの制限に近づいたら新しいページ
                    embeds.append(current_embed)
                    current_embed = discord.Embed(
                        title=f"{user['user_name']} の詳細戦績（続き）",
                        color=discord.Color.blue()
                    )
                    field_count = 0
                
                # クラス組合せの表示
                if isinstance(combo_tuple, tuple) and len(combo_tuple) == 2:
                    combo_str = f"{combo_tuple[0]} + {combo_tuple[1]}"
                else:
                    combo_str = str(combo_tuple)
                
                combo_win_rate = (stats['total_wins'] / stats['total_matches'] * 100) if stats['total_matches'] > 0 else 0
                win_rate_emoji = "🔥" if combo_win_rate >= 60 else "✅" if combo_win_rate >= 50 else "⚠️"
                
                # フィールドの値を構築
                field_value = (
                    f"{win_rate_emoji} **総合勝率:** {combo_win_rate:.1f}%\n"
                    f" **総戦績:** {stats['total_matches']}戦 {stats['total_wins']}勝-{stats['total_losses']}敗\n"
                )
                
                # 各クラスの選択詳細
                field_value += "\n**投げられたクラス内訳:**\n"
                for class_name, class_stats in stats['class_selection'].items():
                    selection_rate = (class_stats['times_selected'] / stats['total_matches'] * 100) if stats['total_matches'] > 0 else 0
                    class_win_rate = (class_stats['wins'] / class_stats['times_selected'] * 100) if class_stats['times_selected'] > 0 else 0
                    
                    field_value += (
                        f"🎲 **{class_name}**: {class_stats['times_selected']}回 ({selection_rate:.1f}%)\n"
                        f"　 → {class_stats['wins']}勝{class_stats['losses']}敗 (勝率{class_win_rate:.1f}%)\n"
                    )
                
                current_embed.add_field(
                    name=f"vs {combo_str}",
                    value=field_value.strip(),
                    inline=False
                )
                field_count += 1
            
            embeds.append(current_embed)
            
            # ページネーション付きで送信
            if len(embeds) == 1:
                message = await interaction.followup.send(embed=embeds[0], ephemeral=True)
                await self._delete_message_after_delay(message, 300)
            else:
                # 複数ページの場合はページネーションビューを使用
                from views.record_view import DetailedMatchHistoryPaginatorView
                view = DetailedMatchHistoryPaginatorView(embeds)
                message = await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)
                await self._delete_message_after_delay(message, 600)  # ページネーション付きは長めに
        
        else:
            # 3つ以上のクラスが選択された場合（通常は発生しない）
            message = await interaction.followup.send(
                "クラスは1つまたは2つまで選択できます。", 
                ephemeral=True
            )
            await self._delete_message_after_delay(message, 30)

    def _get_detailed_analysis_data_for_user(self, user_id: int, selected_classes: List[str], 
                                       season_id: Optional[int], season_name: Optional[str],
                                       date_range: Optional[tuple]) -> Dict[str, Dict[str, int]]:
        """ユーザー個人の詳細分析データを取得（投げられたクラス分析と同じロジック）"""
        def _get_analysis_data(session):
            from config.database import MatchHistory
            from sqlalchemy import or_, and_
            from config.settings import VALID_CLASSES
            
            # ベースクエリ：完了した試合のみ
            query = session.query(MatchHistory).filter(
                MatchHistory.winner_user_id.isnot(None)
            )
            
            # 期間フィルター
            if season_name:
                query = query.filter(MatchHistory.season_name == season_name)
            elif date_range:
                start_date, end_date = date_range
                query = query.filter(
                    and_(
                        MatchHistory.match_date >= start_date,
                        MatchHistory.match_date <= end_date
                    )
                )
            
            # 指定クラスを選択した試合のみ
            class_name = selected_classes[0]
            query = query.filter(
                or_(
                    # user1が指定クラスを選択
                    and_(
                        MatchHistory.user1_id == user_id,
                        MatchHistory.user1_selected_class == class_name
                    ),
                    # user2が指定クラスを選択  
                    and_(
                        MatchHistory.user2_id == user_id,
                        MatchHistory.user2_selected_class == class_name
                    )
                )
            )
            
            matches = query.all()
            
            # 各クラスに対して統計を初期化
            opponent_stats = {cls: {'wins': 0, 'total': 0} for cls in VALID_CLASSES}
            
            # 各試合を分析
            for match in matches:
                if match.user1_id == user_id:
                    # user1がターゲットユーザー
                    opponent_selected = match.user2_selected_class
                    won = match.winner_user_id == user_id
                else:
                    # user2がターゲットユーザー
                    opponent_selected = match.user1_selected_class
                    won = match.winner_user_id == user_id
                
                if opponent_selected and opponent_selected in opponent_stats:
                    opponent_stats[opponent_selected]['total'] += 1
                    if won:
                        opponent_stats[opponent_selected]['wins'] += 1
            
            # 戦績があるクラスのみ返す
            return {cls: stats for cls, stats in opponent_stats.items() if stats['total'] > 0}
        
        return self.match_model.safe_execute(_get_analysis_data) or {}
    
    def _get_matches_by_date_range(self, user_id: int, start_date: Optional[str], end_date: str) -> List[Dict[str, Any]]:
        """日付範囲で試合を取得"""
        def _get_matches(session):
            from config.database import MatchHistory
            from sqlalchemy import or_, and_
            
            # ベースクエリ
            query = session.query(MatchHistory).filter(
                or_(
                    MatchHistory.user1_id == user_id,
                    MatchHistory.user2_id == user_id
                )
            )
            
            # 日付範囲フィルター
            if start_date:
                query = query.filter(MatchHistory.match_date >= start_date)
            query = query.filter(MatchHistory.match_date <= end_date)
            
            # 完了した試合のみ取得
            query = query.filter(MatchHistory.winner_user_id.isnot(None))
            
            # 日付の降順でソート
            query = query.order_by(MatchHistory.match_date.desc())
            
            matches = query.all()
            
            # セッション内で辞書に変換
            return [
                {
                    'id': match.id,
                    'user1_id': match.user1_id,
                    'user2_id': match.user2_id,
                    'match_date': match.match_date,
                    'season_name': match.season_name,
                    'winner_user_id': match.winner_user_id,
                    'loser_user_id': match.loser_user_id,
                    'user1_selected_class': getattr(match, 'user1_selected_class', None),
                    'user2_selected_class': getattr(match, 'user2_selected_class', None)
                }
                for match in matches
            ]
        
        return self.match_model.safe_execute(_get_matches) or []
    
    def _get_detailed_class_matches_by_date(self, user_id: int, selected_classes: List[str], 
                                        start_date: Optional[str], end_date: str) -> List[Dict[str, Any]]:
        """日付範囲で詳細なクラス戦績を取得（修正版）"""
        def _get_matches(session):
            from config.database import MatchHistory
            from sqlalchemy import or_, and_
            
            # ベースクエリ
            query = session.query(MatchHistory).filter(
                or_(
                    MatchHistory.user1_id == user_id,
                    MatchHistory.user2_id == user_id
                )
            )
            
            # 日付範囲フィルター
            if start_date:
                query = query.filter(MatchHistory.match_date >= start_date)
            query = query.filter(MatchHistory.match_date <= end_date)
            
            # クラスフィルター
            if len(selected_classes) == 1:
                # 単一クラスの場合：選択クラスまたは登録クラスのいずれかが該当
                class_name = selected_classes[0]
                query = query.filter(
                    or_(
                        # user1が指定クラスを選択または登録
                        and_(
                            MatchHistory.user1_id == user_id,
                            or_(
                                MatchHistory.user1_selected_class == class_name,
                                MatchHistory.user1_class_a == class_name,
                                MatchHistory.user1_class_b == class_name
                            )
                        ),
                        # user2が指定クラスを選択または登録
                        and_(
                            MatchHistory.user2_id == user_id,
                            or_(
                                MatchHistory.user2_selected_class == class_name,
                                MatchHistory.user2_class_a == class_name,
                                MatchHistory.user2_class_b == class_name
                            )
                        )
                    )
                )
            elif len(selected_classes) == 2:
                # 2つのクラス組み合わせ（既存のロジック）
                class1, class2 = selected_classes
                query = query.filter(
                    or_(
                        # user1が指定クラス組み合わせを登録
                        and_(
                            MatchHistory.user1_id == user_id,
                            or_(
                                and_(MatchHistory.user1_class_a == class1, MatchHistory.user1_class_b == class2),
                                and_(MatchHistory.user1_class_a == class2, MatchHistory.user1_class_b == class1)
                            )
                        ),
                        # user2が指定クラス組み合わせを登録
                        and_(
                            MatchHistory.user2_id == user_id,
                            or_(
                                and_(MatchHistory.user2_class_a == class1, MatchHistory.user2_class_b == class2),
                                and_(MatchHistory.user2_class_a == class2, MatchHistory.user2_class_b == class1)
                            )
                        )
                    )
                )
            
            # 完了した試合のみ取得
            query = query.filter(MatchHistory.winner_user_id.isnot(None))
            
            # 日付の降順でソート
            query = query.order_by(MatchHistory.match_date.desc())
            
            matches = query.all()
            
            # セッション内で辞書に変換
            return [
                {
                    'id': match.id,
                    'user1_id': match.user1_id,
                    'user2_id': match.user2_id,
                    'match_date': match.match_date,
                    'season_name': match.season_name,
                    'user1_class_a': match.user1_class_a,
                    'user1_class_b': match.user1_class_b,
                    'user2_class_a': match.user2_class_a,
                    'user2_class_b': match.user2_class_b,
                    'user1_rating_change': match.user1_rating_change,
                    'user2_rating_change': match.user2_rating_change,
                    'winner_user_id': match.winner_user_id,
                    'loser_user_id': match.loser_user_id,
                    'before_user1_rating': match.before_user1_rating,
                    'before_user2_rating': match.before_user2_rating,
                    'after_user1_rating': match.after_user1_rating,
                    'after_user2_rating': match.after_user2_rating,
                    'user1_stay_flag': match.user1_stay_flag,
                    'user2_stay_flag': match.user2_stay_flag,
                    'user1_selected_class': getattr(match, 'user1_selected_class', None),
                    'user2_selected_class': getattr(match, 'user2_selected_class', None)
                }
                for match in matches
            ]
        
        return self.match_model.safe_execute(_get_matches) or []

    def _get_detailed_class_matches(self, user_id: int, selected_classes: List[str], 
                                season_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """詳細なクラス戦績を取得（user_class、selected_classを考慮）"""
        def _get_matches(session):
            from config.database import MatchHistory
            from sqlalchemy import or_, and_
            
            # ベースクエリ
            query = session.query(MatchHistory).filter(
                or_(
                    MatchHistory.user1_id == user_id,
                    MatchHistory.user2_id == user_id
                )
            )
            
            # シーズンフィルター（修正：全シーズンの場合はフィルターしない）
            if season_name is not None:
                query = query.filter(MatchHistory.season_name == season_name)
            # season_name が None の場合は全シーズンのデータを取得
            
            # クラスフィルター
            if len(selected_classes) == 1:
                # 単一クラスの場合：選択クラスまたは登録クラスのいずれかが該当
                class_name = selected_classes[0]
                query = query.filter(
                    or_(
                        # user1が指定クラスを選択または登録
                        and_(
                            MatchHistory.user1_id == user_id,
                            or_(
                                MatchHistory.user1_selected_class == class_name,
                                MatchHistory.user1_class_a == class_name,
                                MatchHistory.user1_class_b == class_name
                            )
                        ),
                        # user2が指定クラスを選択または登録
                        and_(
                            MatchHistory.user2_id == user_id,
                            or_(
                                MatchHistory.user2_selected_class == class_name,
                                MatchHistory.user2_class_a == class_name,
                                MatchHistory.user2_class_b == class_name
                            )
                        )
                    )
                )
            elif len(selected_classes) == 2:
                # 2つのクラス組み合わせ（既存のロジック）
                class1, class2 = selected_classes
                query = query.filter(
                    or_(
                        # user1が指定クラス組み合わせを登録
                        and_(
                            MatchHistory.user1_id == user_id,
                            or_(
                                and_(MatchHistory.user1_class_a == class1, MatchHistory.user1_class_b == class2),
                                and_(MatchHistory.user1_class_a == class2, MatchHistory.user1_class_b == class1)
                            )
                        ),
                        # user2が指定クラス組み合わせを登録
                        and_(
                            MatchHistory.user2_id == user_id,
                            or_(
                                and_(MatchHistory.user2_class_a == class1, MatchHistory.user2_class_b == class2),
                                and_(MatchHistory.user2_class_a == class2, MatchHistory.user2_class_b == class1)
                            )
                        )
                    )
                )
            
            # 完了した試合のみ取得
            query = query.filter(MatchHistory.winner_user_id.isnot(None))
            
            # 日付の降順でソート
            query = query.order_by(MatchHistory.match_date.desc())
            
            matches = query.all()
            
            # セッション内で辞書に変換
            return [
                {
                    'id': match.id,
                    'user1_id': match.user1_id,
                    'user2_id': match.user2_id,
                    'match_date': match.match_date,
                    'season_name': match.season_name,
                    'user1_class_a': match.user1_class_a,
                    'user1_class_b': match.user1_class_b,
                    'user2_class_a': match.user2_class_a,
                    'user2_class_b': match.user2_class_b,
                    'user1_rating_change': match.user1_rating_change,
                    'user2_rating_change': match.user2_rating_change,
                    'winner_user_id': match.winner_user_id,
                    'loser_user_id': match.loser_user_id,
                    'before_user1_rating': match.before_user1_rating,
                    'before_user2_rating': match.before_user2_rating,
                    'after_user1_rating': match.after_user1_rating,
                    'after_user2_rating': match.after_user2_rating,
                    'user1_stay_flag': match.user1_stay_flag,
                    'user2_stay_flag': match.user2_stay_flag,
                    'user1_selected_class': getattr(match, 'user1_selected_class', None),
                    'user2_selected_class': getattr(match, 'user2_selected_class', None)
                }
                for match in matches
            ]
        
        return self.match_model.safe_execute(_get_matches) or []
    
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

    async def show_detailed_single_class_stats(self, interaction: discord.Interaction, user_id: int, 
                                            selected_class: str, season_id: Optional[int] = None, 
                                            date_range: Optional[tuple] = None):
        """単一クラスの詳細戦績を表示（対戦相手のクラス別に集計）"""
        user = self.user_model.get_user_by_discord_id(str(user_id))
        if not user:
            message = await interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
            await self._delete_message_after_delay(message, 300)
            return
        
        # フィルター条件の説明
        filter_desc = self._get_filter_description(season_id, date_range)
        
        # 分析データの取得
        analysis_data = self._get_single_class_analysis_data(
            user['id'], selected_class, season_id, date_range
        )
        
        if not analysis_data:
            message = await interaction.followup.send(
                f"指定した条件での {selected_class} クラスの対戦データが見つかりませんでした。", 
                ephemeral=True
            )
            await self._delete_message_after_delay(message, 300)
            return
        
        # 全体の統計
        total_matches = sum(data['total_matches'] for data in analysis_data)
        total_wins = sum(data['my_wins'] for data in analysis_data)
        total_losses = sum(data['opponent_wins'] for data in analysis_data)
        overall_win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0
        
        # 勝率順にソート
        sorted_data = sorted(analysis_data, key=lambda x: (x['win_rate'], x['my_wins']), reverse=True)
        
        # メッセージの作成
        embed = discord.Embed(
            title=f"{user['user_name']} の {selected_class} 単体での詳細戦績",
            description=f" **対象:** {filter_desc}\n"
                    f" **使用クラス:** {selected_class}\n"
                    f" **全体勝率:** {overall_win_rate:.2f}%\n"
                    f" **総戦績:** {total_matches}戦 {total_wins}勝-{total_losses}敗",
            color=discord.Color.green()
        )
        
        # 対戦相手のクラス別戦績
        embed.add_field(name="", value="**【対戦相手のクラス別戦績】**", inline=False)
        
        for data in sorted_data:
            win_rate_emoji = "🔥" if data['win_rate'] >= 60 else "✅" if data['win_rate'] >= 50 else "⚠️"
            
            embed.add_field(
                name=f"vs {data['opponent_class']}",
                value=(
                    f"{win_rate_emoji} 勝率: {data['win_rate']:.1f}%\n"
                    f" 戦績: {data['total_matches']}戦 {data['my_wins']}勝-{data['opponent_wins']}敗"
                ),
                inline=True
            )
        
        message = await interaction.followup.send(embed=embed, ephemeral=True)
        await self._delete_message_after_delay(message, 300)


    async def show_detailed_dual_class_stats(self, interaction: discord.Interaction, user_id: int, 
                                        selected_classes: List[str], season_id: Optional[int] = None, 
                                        date_range: Optional[tuple] = None):
        """2クラス組合せの詳細戦績を表示（投げられたクラスの組合せと選択率を含む）"""
        user = self.user_model.get_user_by_discord_id(str(user_id))
        if not user:
            message = await interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
            await self._delete_message_after_delay(message, 300)
            return
        
        # フィルター条件の説明
        filter_desc = self._get_filter_description(season_id, date_range)
        
        # 分析データの取得（投げられたクラスの組合せと選択クラス別）
        analysis_data = self._get_dual_class_analysis_data(
            user['id'], selected_classes, season_id, date_range
        )
        
        if not analysis_data:
            message = await interaction.followup.send(
                f"指定した条件での {selected_classes[0]} + {selected_classes[1]} の対戦データが見つかりませんでした。", 
                ephemeral=True
            )
            await self._delete_message_after_delay(message, 300)
            return
        
        # 全体の統計
        total_matches = sum(data['total_matches'] for data in analysis_data)
        total_wins = sum(data['my_wins'] for data in analysis_data)
        total_losses = sum(data['opponent_wins'] for data in analysis_data)
        overall_win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0
        
        # 勝率順にソート
        sorted_data = sorted(analysis_data, key=lambda x: (x['win_rate'], x['my_wins']), reverse=True)
        
        # エンベッドの作成（複数ページになる可能性があるため）
        embeds = []
        embed = discord.Embed(
            title=f"{user['user_name']} の詳細戦績",
            description=(
                f" **対象:** {filter_desc}\n"
                f" **使用クラス組合せ:** {selected_classes[0]} + {selected_classes[1]}\n"
                f" **全体勝率:** {overall_win_rate:.2f}%\n"
                f" **総戦績:** {total_matches}戦 {total_wins}勝-{total_losses}敗"
            ),
            color=discord.Color.blue()
        )
        
        # 投げられたクラスの組合せごとに表示
        current_embed = embed
        field_count = 0
        
        for data in sorted_data:
            if field_count >= 20:  # Embedの制限に近づいたら新しいページ
                embeds.append(current_embed)
                current_embed = discord.Embed(
                    title=f"{user['user_name']} の詳細戦績（続き）",
                    color=discord.Color.blue()
                )
                field_count = 0
            
            combo_str = f"{data['opponent_class_combo'][0]} + {data['opponent_class_combo'][1]}"
            win_rate_emoji = "🔥" if data['win_rate'] >= 60 else "✅" if data['win_rate'] >= 50 else "⚠️"
            
            # 選択クラスの表示（どちらが投げられたか）
            if data['opponent_selected_class']:
                selected_emoji = "🎲"
                selected_info = f"{selected_emoji} 投げられたクラス: {data['opponent_selected_class']}"
            else:
                selected_info = ""
            
            current_embed.add_field(
                name=f"vs {combo_str}",
                value=(
                    f"{win_rate_emoji} 勝率: {data['win_rate']:.1f}%\n"
                    f" 戦績: {data['total_matches']}戦 {data['my_wins']}勝-{data['opponent_wins']}敗\n"
                    f"{selected_info}"
                ).strip(),
                inline=True
            )
            field_count += 1
        
        embeds.append(current_embed)
        
        # ページネーション付きで送信
        if len(embeds) == 1:
            message = await interaction.followup.send(embed=embeds[0], ephemeral=True)
            await self._delete_message_after_delay(message, 300)
        else:
            # 複数ページの場合はページネーションビューを使用
            from views.record_view import DetailedMatchHistoryPaginatorView
            view = DetailedMatchHistoryPaginatorView(embeds)
            message = await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)
            await self._delete_message_after_delay(message, 600)  # ページネーション付きは長めに


    def _get_filter_description(self, season_id: Optional[int], date_range: Optional[tuple]) -> str:
        """フィルター条件の説明文を生成"""
        if season_id is not None:
            season_data = self.season_model.get_season_by_id(season_id)
            return f"シーズン {season_data['season_name']}" if season_data else "指定シーズン"
        elif date_range is not None:
            start_date = date_range[0][:10] if date_range[0] else "開始日不明"
            end_date = date_range[1][:10] if date_range[1] else "終了日不明"
            return f"{start_date} ～ {end_date}"
        else:
            return "全シーズン"


    def _get_single_class_analysis_data(self, user_id: int, selected_class: str, 
                                    season_id: Optional[int] = None, 
                                    date_range: Optional[tuple] = None) -> List[Dict]:
        """単一クラスの分析データを取得（対戦相手のクラス別）"""
        def _get_analysis_data(session):
            from config.database import MatchHistory
            from sqlalchemy import or_, and_
            from config.settings import VALID_CLASSES
            
            # ベースクエリ
            query = session.query(MatchHistory).filter(
                MatchHistory.winner_user_id.isnot(None)
            )
            
            # 期間フィルター
            if season_id:
                season = self.season_model.get_season_by_id(season_id)
                if season:
                    query = query.filter(MatchHistory.season_name == season['season_name'])
            elif date_range:
                start_date, end_date = date_range
                query = query.filter(
                    and_(
                        MatchHistory.match_date >= start_date,
                        MatchHistory.match_date <= end_date
                    )
                )
            
            # 指定クラスを使用した試合のみ
            query = query.filter(
                or_(
                    MatchHistory.user1_selected_class == selected_class,
                    MatchHistory.user2_selected_class == selected_class
                )
            )
            
            matches = query.all()
            
            # 対戦相手のクラス別に集計
            opponent_stats = {}
            for cls in VALID_CLASSES:
                opponent_stats[cls] = {
                    'total_matches': 0,
                    'opponent_wins': 0,
                    'my_wins': 0
                }
            
            for match in matches:
                if match.user1_selected_class == selected_class and match.user1_id == user_id:
                    # user1が自分
                    opponent_class = match.user2_selected_class
                    if match.winner_user_id == user_id:
                        opponent_stats[opponent_class]['my_wins'] += 1
                    else:
                        opponent_stats[opponent_class]['opponent_wins'] += 1
                    opponent_stats[opponent_class]['total_matches'] += 1
                elif match.user2_selected_class == selected_class and match.user2_id == user_id:
                    # user2が自分
                    opponent_class = match.user1_selected_class
                    if match.winner_user_id == user_id:
                        opponent_stats[opponent_class]['my_wins'] += 1
                    else:
                        opponent_stats[opponent_class]['opponent_wins'] += 1
                    opponent_stats[opponent_class]['total_matches'] += 1
            
            # 結果を整形
            result = []
            for opponent_class, stats in opponent_stats.items():
                if stats['total_matches'] > 0:
                    win_rate = (stats['my_wins'] / stats['total_matches']) * 100
                    result.append({
                        'opponent_class': opponent_class,
                        'total_matches': stats['total_matches'],
                        'opponent_wins': stats['opponent_wins'],
                        'my_wins': stats['my_wins'],
                        'win_rate': win_rate
                    })
            
            return result
        
        return self.match_model.safe_execute(_get_analysis_data) or []


    def _get_analysis_data(self, selected_classes: List[str], season_name: Optional[str] = None, 
                        date_range: Optional[tuple] = None) -> List[Dict]:
        """投げられたクラスの分析データを取得"""
        def _get_analysis_data(session):
            from config.database import MatchHistory
            from sqlalchemy import or_, and_
            from itertools import combinations
            
            # ベースクエリ：完了した試合のみ
            query = session.query(MatchHistory).filter(
                MatchHistory.winner_user_id.isnot(None)
            )
            
            # 期間フィルター
            if season_name:
                query = query.filter(MatchHistory.season_name == season_name)
            elif date_range:
                start_date, end_date = date_range
                query = query.filter(
                    and_(
                        MatchHistory.match_date >= start_date,
                        MatchHistory.match_date <= end_date
                    )
                )
            
            # 指定クラス組み合わせに関する対戦のみ
            if len(selected_classes) == 1:
                # 単体クラス
                class_name = selected_classes[0]
                query = query.filter(
                    or_(
                        # user1が指定クラスを選択
                        MatchHistory.user1_selected_class == class_name,
                        # user2が指定クラスを選択
                        MatchHistory.user2_selected_class == class_name
                    )
                )
            else:
                # 2つのクラス組み合わせ
                class1, class2 = selected_classes
                query = query.filter(
                    or_(
                        # user1が指定クラス組み合わせを登録
                        and_(
                            or_(
                                and_(MatchHistory.user1_class_a == class1, MatchHistory.user1_class_b == class2),
                                and_(MatchHistory.user1_class_a == class2, MatchHistory.user1_class_b == class1)
                            )
                        ),
                        # user2が指定クラス組み合わせを登録
                        and_(
                            or_(
                                and_(MatchHistory.user2_class_a == class1, MatchHistory.user2_class_b == class2),
                                and_(MatchHistory.user2_class_a == class2, MatchHistory.user2_class_b == class1)
                            )
                        )
                    )
                )
            
            matches = query.all()
            
            opponent_stats = {}
            
            if len(selected_classes) == 1:
                # 単一クラス選択時：7種類のクラスそれぞれとの戦績を集計
                from config.settings import VALID_CLASSES
                class_name = selected_classes[0]
                
                # 各クラスに対して統計を初期化
                for opponent_class in VALID_CLASSES:
                    opponent_stats[opponent_class] = {
                        'total_matches': 0,
                        'opponent_wins': 0,
                        'my_wins': 0
                    }
                
                # マッチデータを分析
                for match in matches:
                    # 指定クラス使用者を特定
                    my_user_id = None
                    opponent_user_id = None
                    opponent_selected_class = None
                    
                    if match.user1_selected_class == class_name:
                        my_user_id = match.user1_id
                        opponent_user_id = match.user2_id
                        opponent_selected_class = match.user2_selected_class
                    elif match.user2_selected_class == class_name:
                        my_user_id = match.user2_id
                        opponent_user_id = match.user1_id
                        opponent_selected_class = match.user1_selected_class
                    
                    # 統計を更新
                    if opponent_selected_class and opponent_selected_class in opponent_stats:
                        opponent_stats[opponent_selected_class]['total_matches'] += 1
                        
                        if match.winner_user_id == my_user_id:
                            opponent_stats[opponent_selected_class]['my_wins'] += 1
                        else:
                            opponent_stats[opponent_selected_class]['opponent_wins'] += 1
                
                # 結果を整形
                result = []
                for opponent_class, stats in opponent_stats.items():
                    if stats['total_matches'] > 0:  # 対戦があったクラスのみ
                        win_rate = (stats['my_wins'] / stats['total_matches']) * 100
                        result.append({
                            'opponent_class_combo': opponent_class,  # 単一クラス名
                            'opponent_selected_class': opponent_class,
                            'total_matches': stats['total_matches'],
                            'opponent_wins': stats['opponent_wins'],
                            'my_wins': stats['my_wins'],
                            'win_rate': win_rate
                        })
                
                return result
                
            else:
                # 2つのクラス組み合わせ
                # 全クラス組み合わせを生成
                from config.settings import VALID_CLASSES
                all_combinations = []
                
                # 2つのクラスの組み合わせ（C(7,2) = 21通り）
                for combo in combinations(VALID_CLASSES, 2):
                    combo_key = tuple(sorted(combo))
                    all_combinations.append(combo_key)
                
                # 各組み合わせに対して、どちらを選択したかで分ける
                for combo in all_combinations:
                    for selected_class in combo:
                        key = (combo, selected_class)
                        opponent_stats[key] = {
                            'total_matches': 0,
                            'opponent_wins': 0,
                            'my_wins': 0
                        }
                
                # マッチデータを分析
                for match in matches:
                    # 指定クラス使用者を特定
                    my_user_id = None
                    opponent_user_id = None
                    opponent_class_combo = None
                    opponent_selected_class = None
                    
                    class1, class2 = selected_classes
                    class_set = {class1, class2}
                    
                    if match.user1_class_a and match.user1_class_b:
                        user1_class_set = {match.user1_class_a, match.user1_class_b}
                    else:
                        user1_class_set = set()
                    
                    if match.user2_class_a and match.user2_class_b:
                        user2_class_set = {match.user2_class_a, match.user2_class_b}
                    else:
                        user2_class_set = set()
                    
                    if user1_class_set == class_set:
                        my_user_id = match.user1_id
                        opponent_user_id = match.user2_id
                        if match.user2_class_a and match.user2_class_b:
                            opponent_class_combo = tuple(sorted([match.user2_class_a, match.user2_class_b]))
                            opponent_selected_class = match.user2_selected_class
                    elif user2_class_set == class_set:
                        my_user_id = match.user2_id
                        opponent_user_id = match.user1_id
                        if match.user1_class_a and match.user1_class_b:
                            opponent_class_combo = tuple(sorted([match.user1_class_a, match.user1_class_b]))
                            opponent_selected_class = match.user1_selected_class
                    
                    # 統計を更新
                    if (opponent_class_combo and opponent_selected_class and 
                        opponent_class_combo in [combo for combo, _ in opponent_stats.keys()]):
                        
                        key = (opponent_class_combo, opponent_selected_class)
                        if key in opponent_stats:
                            opponent_stats[key]['total_matches'] += 1
                            
                            if match.winner_user_id == my_user_id:
                                opponent_stats[key]['my_wins'] += 1
                            else:
                                opponent_stats[key]['opponent_wins'] += 1
                
                # 結果を整形
                result = []
                for (combo, selected_class), stats in opponent_stats.items():
                    if stats['total_matches'] > 0:
                        combo_str = f"{combo[0]} + {combo[1]}"
                        win_rate = (stats['my_wins'] / stats['total_matches']) * 100
                        result.append({
                            'opponent_class_combo': combo,  # タプル形式で保持
                            'opponent_selected_class': selected_class,
                            'total_matches': stats['total_matches'],
                            'opponent_wins': stats['opponent_wins'],
                            'my_wins': stats['my_wins'],
                            'win_rate': win_rate
                        })
                
                return result
        
        return self.match_model.safe_execute(_get_analysis_data) or []