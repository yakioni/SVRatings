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
                                      selected_classes: List[str], season_id: Optional[int] = None):
        """詳細なクラス戦績を表示（user_class、selected_classを考慮）"""
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
        
        # 詳細戦績の取得
        matches = self._get_detailed_class_matches(user['id'], selected_classes, season_name)
        
        # 勝敗数の計算
        win_count = sum(1 for match in matches if match['winner_user_id'] == user['id'])
        total_count = len(matches)
        loss_count = total_count - win_count
        win_rate = (win_count / total_count) * 100 if total_count > 0 else 0
        
        # クラス表示文字列を作成
        if len(selected_classes) == 1:
            selected_class_str = f"{selected_classes[0]}（選択クラス基準）"
        elif len(selected_classes) == 2:
            selected_class_str = f"{selected_classes[0]} + {selected_classes[1]}（登録クラス基準）"
        else:
            selected_class_str = "複数クラス"
        
        # シーズン情報を表示に含める
        season_info = f"シーズン {season_name}" if season_name else "全シーズン"
        
        # 詳細戦績メッセージ
        detailed_message = (
            f"**{user['user_name']} の詳細戦績**\n"
            f"対象: {season_info}\n"
            f"クラス: {selected_class_str}\n"
            f"勝率: {win_rate:.2f}%\n"
            f"{total_count}戦   {win_count}勝-{loss_count}敗"
        )
        
        # 最近の試合履歴も表示（最大10試合）
        if matches:
            detailed_message += "\n\n**最近の試合履歴（最大10戦）:**"
            recent_matches = matches[:10]  # 最新10試合
            
            for i, match in enumerate(recent_matches, 1):
                # 対戦相手名を取得
                if match['user1_id'] == user['id']:
                    opponent_data = self.user_model.get_user_by_id(match['user2_id'])
                    user_won = match['winner_user_id'] == user['id']
                    user_selected_class = match.get('user1_selected_class', 'Unknown')
                else:
                    opponent_data = self.user_model.get_user_by_id(match['user1_id'])
                    user_won = match['winner_user_id'] == user['id']
                    user_selected_class = match.get('user2_selected_class', 'Unknown')
                
                # user_dataが辞書かオブジェクトかを判定して適切にアクセス
                def get_attr(data, attr_name, default=None):
                    if isinstance(data, dict):
                        return data.get(attr_name, default)
                    else:
                        return getattr(data, attr_name, default)
                
                opponent_name = get_attr(opponent_data, 'user_name', 'Unknown') if opponent_data else 'Unknown'
                
                result_emoji = "🔵" if user_won else "🔴"
                result_text = "勝利" if user_won else "敗北"
                
                match_date = match.get('match_date', '')[:10] if match.get('match_date') else 'Unknown'
                
                detailed_message += f"\n{i}. {result_emoji} vs {opponent_name} ({user_selected_class}) - {result_text} ({match_date})"
        
        message = await interaction.followup.send(detailed_message, ephemeral=True)
        await self._delete_message_after_delay(message, 300)
    
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
            
            # シーズンフィルター
            if season_name:
                query = query.filter(MatchHistory.season_name == season_name)
            
            # クラスフィルター
            if len(selected_classes) == 1:
                # 1つのクラスを選択：selected_classがそのクラスの試合
                class_name = selected_classes[0]
                query = query.filter(
                    or_(
                        and_(MatchHistory.user1_id == user_id,
                             MatchHistory.user1_selected_class == class_name),
                        and_(MatchHistory.user2_id == user_id,
                             MatchHistory.user2_selected_class == class_name)
                    )
                )
            elif len(selected_classes) == 2:
                # 2つのクラスを選択：class_a/class_bがその組み合わせの試合
                class1, class2 = selected_classes
                query = query.filter(
                    or_(
                        and_(MatchHistory.user1_id == user_id,
                             or_(
                                 and_(MatchHistory.user1_class_a == class1,
                                      MatchHistory.user1_class_b == class2),
                                 and_(MatchHistory.user1_class_a == class2,
                                      MatchHistory.user1_class_b == class1)
                             )),
                        and_(MatchHistory.user2_id == user_id,
                             or_(
                                 and_(MatchHistory.user2_class_a == class1,
                                      MatchHistory.user2_class_b == class2),
                                 and_(MatchHistory.user2_class_a == class2,
                                      MatchHistory.user2_class_b == class1)
                             ))
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