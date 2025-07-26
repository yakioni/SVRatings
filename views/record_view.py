import discord
from discord.ui import View, Button, Select, Modal, InputText
import asyncio
from typing import List, Optional, Dict
from sqlalchemy import desc
from models.user import UserModel
from models.season import SeasonModel
from models.match import MatchModel
import logging

class CurrentSeasonRecordView(View):
    """現在シーズンの戦績表示View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        
        # 既存の現在シーズンボタン
        current_season_button = Button(label="現在のシーズン", style=discord.ButtonStyle.primary)
        async def current_season_callback(interaction):
            await self.show_class_select(interaction)
        current_season_button.callback = current_season_callback
        self.add_item(current_season_button)
        
        # 新しいユーザー検索ボタンを追加
        user_search_button = Button(label="ユーザーとの対戦成績", style=discord.ButtonStyle.secondary, emoji="🔍")
        async def user_search_callback(interaction):
            await self.show_user_search(interaction)
        user_search_button.callback = user_search_callback
        self.add_item(user_search_button)
    
    async def show_class_select(self, interaction: discord.Interaction):
        """通常のクラス選択を表示"""
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
                content="クラスを選択してください：", 
                view=ClassSelectView(season_id=season.id), 
                ephemeral=True
            )
        else:
            await interaction.response.send_message("シーズンが見つかりません。", ephemeral=True)
    
    async def show_user_search(self, interaction: discord.Interaction):
        """ユーザー検索モーダルを表示"""
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        if not user:
            await interaction.response.send_message("ユーザー登録を行ってください。", ephemeral=True)
            return
        
        # ユーザー検索モーダルを表示
        modal = UserSearchModal()
        await interaction.response.send_modal(modal)

class UserSearchModal(Modal):
    """ユーザー検索用のモーダル"""
    
    def __init__(self):
        super().__init__(title="ユーザー検索")
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.user_input = InputText(
            label="検索するユーザー名を入力してください",
            placeholder="完全一致または部分一致で検索します",
            required=True,
            max_length=50
        )
        self.add_item(self.user_input)
    
    async def callback(self, interaction: discord.Interaction):
        """ユーザー検索の処理"""
        search_query = self.user_input.value.strip()
        
        if not search_query:
            await interaction.response.send_message("検索クエリが入力されていません。", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 検索実行者の情報を取得
            user_model = UserModel()
            searcher = user_model.get_user_by_discord_id(str(interaction.user.id))
            
            if not searcher:
                await interaction.followup.send("ユーザー登録を行ってください。", ephemeral=True)
                return
            
            # ユーザー検索を実行
            search_results = user_model.search_users(search_query)
            
            if not search_results:
                await interaction.followup.send(
                    f"「{search_query}」に一致するユーザーが見つかりませんでした。", 
                    ephemeral=True
                )
                return
            
            # 自分自身を検索結果から除外
            search_results = [user for user in search_results if user['id'] != searcher['id']]
            
            if not search_results:
                await interaction.followup.send(
                    "自分以外に一致するユーザーが見つかりませんでした。", 
                    ephemeral=True
                )
                return
            
            if len(search_results) == 1:
                # 1人だけ見つかった場合、直接対戦成績を表示
                target_user = search_results[0]
                await self.show_vs_stats(interaction, searcher, target_user)
            else:
                # 複数見つかった場合、選択肢を表示
                await self.show_user_selection(interaction, searcher, search_results, search_query)
                
        except Exception as e:
            self.logger.error(f"Error in user search: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send("検索中にエラーが発生しました。", ephemeral=True)
    
    async def show_user_selection(self, interaction: discord.Interaction, searcher: dict, 
                                 search_results: List[dict], search_query: str):
        """複数ユーザーが見つかった場合の選択画面"""
        if len(search_results) > 25:
            # 選択肢が多すぎる場合は最初の25人のみ表示
            search_results = search_results[:25]
            note = f"\n\n（検索結果が多いため、最初の25人のみ表示しています）"
        else:
            note = ""
        
        options = []
        for user in search_results:
            # Discordのユーザー情報も取得を試行
            discord_user = interaction.guild.get_member(int(user['discord_id']))
            display_name = discord_user.display_name if discord_user else "不明"
            
            option_label = f"{user['user_name']} ({display_name})"
            if len(option_label) > 100:  # Discordの制限
                option_label = option_label[:97] + "..."
            
            options.append(discord.SelectOption(
                label=option_label,
                value=str(user['id']),
                description=f"ID： {user['shadowverse_id'][:8]}..."
            ))
        
        select = UserSelectionSelect(searcher, search_results)
        view = View()
        view.add_item(select)
        
        await interaction.followup.send(
            f"「{search_query}」の検索結果：{len(search_results)}人が見つかりました。\n"
            f"対戦成績を表示したいユーザーを選択してください。{note}",
            view=view,
            ephemeral=True
        )
    
    async def show_vs_stats(self, interaction: discord.Interaction, searcher: dict, target_user: dict):
        """対戦成績を表示"""
        try:
            # 対戦履歴を取得
            match_model = MatchModel()
            vs_matches = match_model.get_user_vs_user_history(searcher['id'], target_user['id'])
            
            # user_dataが辞書かオブジェクトかを判定して適切にアクセス
            def get_attr(data, attr_name, default=None):
                if isinstance(data, dict):
                    return data.get(attr_name, default)
                else:
                    return getattr(data, attr_name, default)
            
            searcher_name = get_attr(searcher, 'user_name', 'Unknown')
            target_name = get_attr(target_user, 'user_name', 'Unknown')
            
            if not vs_matches:
                await interaction.followup.send(
                    f"**{searcher_name}** vs **{target_name}** の対戦履歴はありません。",
                    ephemeral=True
                )
                return
            
            # 勝敗を集計
            searcher_wins = 0
            target_wins = 0
            
            for match in vs_matches:
                if match['winner_user_id'] == searcher['id']:
                    searcher_wins += 1
                elif match['winner_user_id'] == target_user['id']:
                    target_wins += 1
            
            total_matches = searcher_wins + target_wins
            if total_matches == 0:
                await interaction.followup.send(
                    f"**{searcher_name}** vs **{target_name}** の完了した対戦はありません。",
                    ephemeral=True
                )
                return
            
            # 勝率と割合を計算
            searcher_win_rate = (searcher_wins / total_matches) * 100
            target_win_rate = (target_wins / total_matches) * 100
            
            # Discordのユーザー情報を取得
            discord_target = interaction.guild.get_member(int(target_user['discord_id']))
            target_display_name = discord_target.display_name if discord_target else "不明"
            
            # 対戦成績メッセージを作成
            stats_message = (
                f"**🆚 対戦成績**\n"
                f"**{searcher_name}** vs **{target_name}** ({target_display_name})\n\n"
                f"📊 **総対戦数：** {total_matches}戦\n"
                f"🏆 **{searcher_name}：** {searcher_wins}勝 ({searcher_win_rate:.1f}%)\n"
                f"🏆 **{target_name}：** {target_wins}勝 ({target_win_rate:.1f}%)\n\n"
                f"📈 **勝率比較：**\n"
                f"├ あなた： {searcher_win_rate:.1f}%\n"
                f"└ 相手： {target_win_rate:.1f}%"
            )
            
            # 対戦履歴表示用のビューを作成
            view = UserVsUserHistoryView(searcher, target_user, vs_matches)
            
            await interaction.followup.send(
                stats_message,
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error showing vs stats: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send("対戦成績の取得中にエラーが発生しました。", ephemeral=True)

class UserSelectionSelect(Select):
    """ユーザー選択用のセレクト"""
    
    def __init__(self, searcher: dict, search_results: List[dict]):
        self.searcher = searcher
        self.search_results = search_results
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 選択肢を作成
        options = []
        for user in search_results:
            option_label = user['user_name']
            if len(option_label) > 100:
                option_label = option_label[:97] + "..."
            
            options.append(discord.SelectOption(
                label=option_label,
                value=str(user['id']),
                description=f"ID： {user['shadowverse_id'][:8]}..."
            ))
        
        super().__init__(
            placeholder="ユーザーを選択してください...",
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """ユーザー選択のコールバック"""
        selected_user_id = int(self.values[0])
        
        # 選択されたユーザーを取得
        target_user = None
        for user in self.search_results:
            if user['id'] == selected_user_id:
                target_user = user
                break
        
        if not target_user:
            await interaction.response.send_message("選択されたユーザーが見つかりません。", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # 対戦成績を表示
        modal = UserSearchModal()
        await modal.show_vs_stats(interaction, self.searcher, target_user)

class UserVsUserHistoryView(View):
    """ユーザー間対戦履歴表示View"""
    
    def __init__(self, searcher: dict, target_user: dict, vs_matches: List[dict]):
        super().__init__(timeout=600)
        self.searcher = searcher
        self.target_user = target_user
        self.vs_matches = vs_matches
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 対戦履歴表示ボタンを追加
        history_button = Button(
            label="📖 対戦履歴を表示", 
            style=discord.ButtonStyle.primary
        )
        history_button.callback = self.show_match_history
        self.add_item(history_button)
    
    async def show_match_history(self, interaction: discord.Interaction):
        """対戦履歴を表示"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # user_dataが辞書かオブジェクトかを判定して適切にアクセス
            def get_attr(data, attr_name, default=None):
                if isinstance(data, dict):
                    return data.get(attr_name, default)
                else:
                    return getattr(data, attr_name, default)
            
            searcher_name = get_attr(self.searcher, 'user_name', 'Unknown')
            target_name = get_attr(self.target_user, 'user_name', 'Unknown')
            searcher_id = get_attr(self.searcher, 'id')
            target_id = get_attr(self.target_user, 'id')
            
            # 完了した試合のみフィルタリング
            completed_matches = []
            for match in self.vs_matches:
                if (match.get('winner_user_id') is not None and 
                    match.get('after_user1_rating') is not None and 
                    match.get('after_user2_rating') is not None):
                    completed_matches.append(match)
            
            if not completed_matches:
                await interaction.followup.send(
                    f"**{searcher_name}** vs **{target_name}** の完了した対戦履歴はありません。",
                    ephemeral=True
                )
                return
            
            # Embedを作成して対戦履歴を表示
            embeds = []
            current_embed = None
            matches_per_embed = 8  # 詳細情報があるので少なめに設定
            
            for i, match in enumerate(completed_matches):
                # 8試合ごとに新しいEmbedを作成
                if i % matches_per_embed == 0:
                    page_num = i // matches_per_embed + 1
                    total_pages = (len(completed_matches) + matches_per_embed - 1) // matches_per_embed
                    current_embed = discord.Embed(
                        title=f"{searcher_name} vs {target_name} 対戦履歴 (Page {page_num}/{total_pages})",
                        description=f"総対戦数： {len(completed_matches)}試合",
                        color=discord.Color.purple()
                    )
                    embeds.append(current_embed)
                
                # 検索者の視点で情報を整理
                if match['user1_id'] == searcher_id:
                    # 検索者がuser1
                    searcher_rating_change = match.get('user1_rating_change', 0)
                    target_rating_change = match.get('user2_rating_change', 0)
                    searcher_after_rating = match.get('after_user1_rating')
                    target_after_rating = match.get('after_user2_rating')
                    searcher_won = match['winner_user_id'] == searcher_id
                    searcher_selected_class = match.get('user1_selected_class', 'Unknown')
                    target_selected_class = match.get('user2_selected_class', 'Unknown')
                else:
                    # 検索者がuser2
                    searcher_rating_change = match.get('user2_rating_change', 0)
                    target_rating_change = match.get('user1_rating_change', 0)
                    searcher_after_rating = match.get('after_user2_rating')
                    target_after_rating = match.get('after_user1_rating')
                    searcher_won = match['winner_user_id'] == searcher_id
                    searcher_selected_class = match.get('user2_selected_class', 'Unknown')
                    target_selected_class = match.get('user1_selected_class', 'Unknown')
                
                # None値チェックとデフォルト値設定
                if searcher_rating_change is None:
                    searcher_rating_change = 0
                if target_rating_change is None:
                    target_rating_change = 0
                if searcher_after_rating is None:
                    searcher_after_rating = 0
                if target_after_rating is None:
                    target_after_rating = 0
                
                # クラス情報の整理
                if not searcher_selected_class:
                    searcher_selected_class = 'Unknown'
                if not target_selected_class:
                    target_selected_class = 'Unknown'
                
                # 試合結果の表示
                result_emoji = "🔵" if searcher_won else "🔴"
                result_text = "勝利" if searcher_won else "敗北"
                searcher_rating_change_str = f"{searcher_rating_change:+.0f}" if searcher_rating_change != 0 else "±0"
                target_rating_change_str = f"{target_rating_change:+.0f}" if target_rating_change != 0 else "±0"
                
                # 日付のフォーマット
                match_date = match.get('match_date', '')
                if match_date:
                    match_date = match_date[:16]
                else:
                    match_date = 'Unknown'
                
                # シーズン情報
                season_name = match.get('season_name', 'Unknown')
                
                field_value = (
                    f"**結果：** {result_text}\n"
                    f"**シーズン：** {season_name}\n"
                    f"**あなたのクラス：** {searcher_selected_class}\n"
                    f"**相手のクラス：** {target_selected_class}\n"
                    f"**レート変動：**\n"
                    f"├ あなた： {searcher_rating_change_str} (→ {searcher_after_rating:.0f})\n"
                    f"└ 相手： {target_rating_change_str} (→ {target_after_rating:.0f})"
                )
                
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
                    view = UserVsUserHistoryPaginatorView(embeds)
                    await message.edit(view=view)
            
        except Exception as e:
            self.logger.error(f"Error displaying vs user match history: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send("対戦履歴の取得中にエラーが発生しました。", ephemeral=True)

class UserVsUserHistoryPaginatorView(View):
    """ユーザー間対戦履歴のページネーションView"""
    
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=600)
        self.embeds = embeds
        self.current = 0
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="⬅️ 前へ", style=discord.ButtonStyle.primary)
    async def previous(self, button: Button, interaction: discord.Interaction):
        """前のページへ"""
        if self.current > 0:
            self.current -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="➡️ 次へ", style=discord.ButtonStyle.primary)
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
            for item in self.children:
                item.disabled = True
        except Exception as e:
            self.logger.error(f"Error in on_timeout: {e}")

class DetailedRecordView(View):
    """詳細戦績表示View（レーティング更新チャンネル用）"""
    
    def __init__(self):
        super().__init__(timeout=None)
        
        # 詳細な戦績ボタン
        detailed_record_button = Button(label="詳細な戦績", style=discord.ButtonStyle.success)
        async def detailed_record_callback(interaction):
            await self.show_detailed_season_select(interaction)
        detailed_record_button.callback = detailed_record_callback
        self.add_item(detailed_record_button)
    
    async def show_detailed_season_select(self, interaction: discord.Interaction):
        """詳細戦績のシーズン選択を表示"""
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        if not user:
            await interaction.response.send_message("ユーザーが見つかりません。", ephemeral=True)
            return
        
        # 詳細戦績用のシーズン選択を表示
        await interaction.response.send_message(
            content="詳細戦績のシーズンを選択してください:", 
            view=DetailedSeasonSelectView(), 
            ephemeral=True
        )

class DetailedMatchHistoryView(View):
    """詳細な全対戦履歴表示View（レーティング更新チャンネル用）"""
    
    def __init__(self):
        super().__init__(timeout=None)
        
        # 詳細な全対戦履歴ボタン
        detailed_match_history_button = Button(label="詳細な全対戦履歴", style=discord.ButtonStyle.secondary)
        async def detailed_match_history_callback(interaction):
            await self.show_detailed_match_history(interaction)
        detailed_match_history_button.callback = detailed_match_history_callback
        self.add_item(detailed_match_history_button)
    
    async def show_detailed_match_history(self, interaction: discord.Interaction):
        """詳細な全対戦履歴を表示"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # ユーザー情報を取得
            user_model = UserModel()
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
            
            # 全試合履歴を取得
            match_model = MatchModel()
            matches = match_model.get_user_match_history(user_id, limit=None)  # 全履歴
            
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
            
            # Embedを作成して詳細な試合履歴を表示
            embeds = []
            current_embed = None
            matches_per_embed = 8  # クラス情報が多いので1ページあたりの試合数を減らす
            
            for i, match in enumerate(completed_matches):
                # 8試合ごとに新しいEmbedを作成
                if i % matches_per_embed == 0:
                    page_num = i // matches_per_embed + 1
                    total_pages = (len(completed_matches) + matches_per_embed - 1) // matches_per_embed
                    current_embed = discord.Embed(
                        title=f"{user_name} の全対戦履歴 (Page {page_num}/{total_pages})",
                        description=f"総試合数: {len(completed_matches)}試合",
                        color=discord.Color.green()
                    )
                    embeds.append(current_embed)
                
                # 対戦相手と自分の情報を取得
                if match['user1_id'] == user_id:
                    # 自分がuser1
                    opponent_data = user_model.get_user_by_id(match['user2_id'])
                    user_rating_change = match.get('user1_rating_change', 0)
                    after_rating = match.get('after_user1_rating')
                    user_won = match['winner_user_id'] == user_id
                    
                    # クラス情報
                    my_class_a = match.get('user1_class_a', 'Unknown')
                    my_class_b = match.get('user1_class_b', 'Unknown')
                    my_selected_class = match.get('user1_selected_class', 'Unknown')
                    opp_class_a = match.get('user2_class_a', 'Unknown')
                    opp_class_b = match.get('user2_class_b', 'Unknown')
                    opp_selected_class = match.get('user2_selected_class', 'Unknown')
                else:
                    # 自分がuser2
                    opponent_data = user_model.get_user_by_id(match['user1_id'])
                    user_rating_change = match.get('user2_rating_change', 0)
                    after_rating = match.get('after_user2_rating')
                    user_won = match['winner_user_id'] == user_id
                    
                    # クラス情報
                    my_class_a = match.get('user2_class_a', 'Unknown')
                    my_class_b = match.get('user2_class_b', 'Unknown')
                    my_selected_class = match.get('user2_selected_class', 'Unknown')
                    opp_class_a = match.get('user1_class_a', 'Unknown')
                    opp_class_b = match.get('user1_class_b', 'Unknown')
                    opp_selected_class = match.get('user1_selected_class', 'Unknown')
                
                opponent_name = get_attr(opponent_data, 'user_name', 'Unknown') if opponent_data else 'Unknown'
                
                # None値チェックとデフォルト値設定
                if user_rating_change is None:
                    user_rating_change = 0
                if after_rating is None:
                    after_rating = 0
                
                # 試合結果の表示
                result_emoji = "🔵" if user_won else "🔴"
                result_text = "勝利" if user_won else "敗北"
                rating_change_str = f"{user_rating_change:+.0f}" if user_rating_change != 0 else "±0"
                
                # クラス情報の整理
                my_classes = f"{my_class_a or 'Unknown'} / {my_class_b or 'Unknown'}"
                opp_classes = f"{opp_class_a or 'Unknown'} / {opp_class_b or 'Unknown'}"
                
                # 選択クラスの表示（Noneや空文字列の場合はUnknown）
                my_selected = my_selected_class if my_selected_class else 'Unknown'
                opp_selected = opp_selected_class if opp_selected_class else 'Unknown'
                
                # 日付のフォーマット
                match_date = match.get('match_date', '')
                if match_date:
                    match_date = match_date[:16]
                else:
                    match_date = 'Unknown'
                
                # シーズン情報
                season_name = match.get('season_name', 'Unknown')
                
                field_value = (
                    f"**対戦相手:** {opponent_name}\n"
                    f"**結果:** {result_text}\n"
                    f"**レート変動:** {rating_change_str} (→ {after_rating:.0f})\n"
                    f"**シーズン:** {season_name}\n"
                    f"**あなたの登録クラス:** {my_classes}\n"
                    f"**あなたの選択クラス:** {my_selected}\n"
                    f"**相手の登録クラス:** {opp_classes}\n"
                    f"**相手の選択クラス:** {opp_selected}"
                )
                
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
                    view = DetailedMatchHistoryPaginatorView(embeds)
                    await message.edit(view=view)
            
        except Exception as e:
            logging.getLogger(self.__class__.__name__).error(f"Error displaying detailed match history: {e}")
            import traceback
            logging.getLogger(self.__class__.__name__).error(traceback.format_exc())
            await interaction.followup.send("詳細対戦履歴の取得中にエラーが発生しました。", ephemeral=True)

class DetailedSeasonSelectView(View):
    """詳細戦績用のシーズン選択View"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(DetailedSeasonSelect())

class DetailedSeasonSelect(Select):
    """詳細戦績用のシーズン選択セレクト"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 現在のシーズンと過去のシーズンを取得
        season_model = SeasonModel()
        current_season = season_model.get_current_season()
        past_seasons = season_model.get_past_seasons()
        
        # 全シーズンオプションを一番上に
        options = [discord.SelectOption(label="全シーズン", value="all")]
        
        # 現在のシーズンを追加（「現在：」プレフィックスなし）
        if current_season:
            options.append(discord.SelectOption(
                label=current_season.season_name, 
                value=f"current_{current_season.id}"
            ))
        
        # 過去のシーズンを追加
        for season in past_seasons:
            options.append(discord.SelectOption(
                label=season['season_name'], 
                value=f"past_{season['id']}"
            ))
        
        # 日付で絞り込むオプションを一番下に追加
        options.append(discord.SelectOption(
            label="日付で絞り込む", 
            value="date_range",
            emoji="📅"
        ))
        
        super().__init__(
            placeholder="シーズンを選択してください...", 
            options=options if options else [discord.SelectOption(label="シーズンなし", value="none")]
        )
    
    async def callback(self, interaction: discord.Interaction):
        """シーズン選択のコールバック"""
        selected_value = self.values[0]
        
        if selected_value == "none":
            await interaction.response.send_message("利用可能なシーズンがありません。", ephemeral=True)
            return
        
        if selected_value == "date_range":
            # 日付範囲入力モーダルを表示
            modal = DateRangeInputModal()
            await interaction.response.send_modal(modal)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # 選択された値を解析
        if selected_value == "all":
            season_id = None
            season_type = "all"
        elif selected_value.startswith("current_"):
            season_id = int(selected_value.split("_")[1])
            season_type = "current"
        elif selected_value.startswith("past_"):
            season_id = int(selected_value.split("_")[1])
            season_type = "past"
        else:
            await interaction.followup.send("無効な選択です。", ephemeral=True)
            return
        
        # ユーザーがそのシーズンに参加しているかチェック
        if season_id is not None and season_type == "past":
            user_model = UserModel()
            user = user_model.get_user_by_discord_id(str(interaction.user.id))
            
            if not user:
                await interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
                return
            
            season_model = SeasonModel()
            user_record = season_model.get_user_season_record(user['id'], season_id)
            
            if user_record is None:
                await interaction.followup.send("そのシーズンには参加していません。", ephemeral=True)
                return
        elif season_id is not None and season_type == "current":
            user_model = UserModel()
            user = user_model.get_user_by_discord_id(str(interaction.user.id))
            
            if user and not user['latest_season_matched']:
                await interaction.followup.send("現在のシーズンには参加していません。", ephemeral=True)
                return
        
        # クラス選択を表示
        await interaction.followup.send(
            content="詳細戦績のクラスを選択してください:", 
            view=DetailedClassSelectView(season_id=season_id),
            ephemeral=True
        )

class DateRangeInputModal(discord.ui.Modal):
    """日付範囲入力用のモーダル"""
    
    def __init__(self):
        super().__init__(title="日付範囲を入力してください")
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 現在の日付を取得してヒントとして使用
        from datetime import datetime, timedelta
        from config.settings import JST
        
        today = datetime.now(JST)
        today_str = today.strftime('%Y-%m-%d')
        week_ago_str = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        
        self.start_date_input = discord.ui.InputText(
            label="開始日",
            placeholder=f"例: {week_ago_str} (YYYY-MM-DD形式)",
            required=True,
            max_length=10
        )
        self.add_item(self.start_date_input)
        
        self.end_date_input = discord.ui.InputText(
            label="終了日", 
            placeholder=f"例: {today_str} (YYYY-MM-DD形式)",
            required=True,
            max_length=10
        )
        self.add_item(self.end_date_input)
    
    async def callback(self, interaction: discord.Interaction):
        """モーダル送信のコールバック"""
        start_date_str = self.start_date_input.value.strip()
        end_date_str = self.end_date_input.value.strip()
        
        self.logger.info(f"Date range input: {start_date_str} to {end_date_str} by user {interaction.user.id}")
        
        # 日付形式のバリデーション
        try:
            from datetime import datetime
            
            # 日付のパース
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            # 開始日が終了日より後でないかチェック
            if start_date > end_date:
                await interaction.response.send_message(
                    "❌ **エラー:** 開始日は終了日より前の日付を指定してください。\n"
                    f"入力された値: 開始日 `{start_date_str}`, 終了日 `{end_date_str}`",
                    ephemeral=True
                )
                return
            
            # 未来の日付でないかチェック
            from config.settings import JST
            now = datetime.now(JST).replace(tzinfo=None)  # タイムゾーン情報を削除
            
            if end_date > now:
                await interaction.response.send_message(
                    "❌ **エラー:** 終了日は今日以前の日付を指定してください。\n"
                    f"今日の日付: `{now.strftime('%Y-%m-%d')}`",
                    ephemeral=True
                )
                return
            
            # 日数を計算
            days_diff = (end_date - start_date).days
            
            # ISO形式の文字列に変換（時刻情報を追加）
            start_date_iso = f"{start_date_str} 00:00:00"
            end_date_iso = f"{end_date_str} 23:59:59"
            
            date_range = (start_date_iso, end_date_iso)
            range_description = f"{start_date_str} ～ {end_date_str}"
            
            self.logger.info(f"Valid date range processed: {range_description} ({days_diff + 1}日間)")
            
            # クラス選択を表示
            await interaction.response.send_message(
                content=f"✅ **日付範囲設定完了**\n"
                        f"📅 対象期間: **{range_description}** ({days_diff + 1}日間)\n"
                        f"🎯 次に詳細戦績のクラスを選択してください:",
                view=DetailedClassSelectView(season_id=None, date_range=date_range),
                ephemeral=True
            )
            
        except ValueError as e:
            self.logger.warning(f"Invalid date format from user {interaction.user.id}: {start_date_str}, {end_date_str}")
            await interaction.response.send_message(
                "❌ **エラー:** 日付の形式が正しくありません。\n\n"
                "**正しい形式:** `YYYY-MM-DD`\n"
                "**例:** `2024-01-01`\n"
                f"**入力された値:** 開始日 `{start_date_str}`, 終了日 `{end_date_str}`\n\n"
                "年は4桁、月と日は2桁で入力してください。",
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error in date range input from user {interaction.user.id}: {e}")
            await interaction.response.send_message(
                "❌ 日付の処理中にエラーが発生しました。\n"
                "入力形式を確認して再度お試しください。",
                ephemeral=True
            )

class DetailedClassSelectView(View):
    """詳細戦績用のクラス選択View"""
    
    def __init__(self, season_id: Optional[int] = None, date_range: Optional[tuple] = None):
        super().__init__(timeout=None)
        self.add_item(DetailedClassSelect(season_id, date_range))

class DetailedClassSelect(Select):
    """詳細戦績用のクラス選択セレクト（1つまたは2つ選択可能）"""
    
    def __init__(self, season_id: Optional[int] = None, date_range: Optional[tuple] = None):
        self.season_id = season_id
        self.date_range = date_range
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # データベースからクラス名を取得
        user_model = UserModel()
        valid_classes = user_model.get_valid_classes()
        
        # 全クラスを一番上に置く
        options = [discord.SelectOption(label="全クラス", value="all_classes")]
        options.extend([discord.SelectOption(label=cls, value=cls) for cls in valid_classes])
        
        super().__init__(
            placeholder="クラスを選択してください（1つまたは2つ）...", 
            min_values=1, 
            max_values=min(2, len(options)),  # 最大2つまで選択可能
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """詳細クラス選択のコールバック"""
        selected_classes = self.values
        user_id = interaction.user.id
        
        # インタラクションのレスポンスを一度行う
        await interaction.response.defer(ephemeral=True)
        
        try:
            # RecordViewModelを遅延インポート
            from viewmodels.record_vm import RecordViewModel
            record_vm = RecordViewModel()
            
            if "all_classes" in selected_classes:
                # 全クラスを選択した場合
                if self.season_id:
                    await record_vm.show_season_stats(interaction, user_id, self.season_id)
                elif self.date_range:
                    await record_vm.show_date_range_stats(interaction, user_id, self.date_range)
                else:
                    await record_vm.show_all_time_stats(interaction, user_id)
            else:
                # 特定のクラスを選択した場合（詳細戦績モード）
                await record_vm.show_detailed_class_stats(interaction, user_id, selected_classes, self.season_id, self.date_range)
        
        except Exception as e:
            self.logger.error(f"Error in detailed class selection callback: {e}")
            await interaction.followup.send("エラーが発生しました。", ephemeral=True)
        
        # インタラクションメッセージを削除する
        try:
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            pass

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
        
        # 全クラスを一番上に置く
        options = [discord.SelectOption(label="全クラス", value="all_classes")]
        options.extend([discord.SelectOption(label=cls, value=cls) for cls in valid_classes])
        
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

class DetailedMatchHistoryPaginatorView(View):
    """詳細対戦履歴のページネーションView"""
    
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=600)
        self.embeds = embeds
        self.current = 0
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="⬅️ 前へ", style=discord.ButtonStyle.primary)
    async def previous(self, button: Button, interaction: discord.Interaction):
        """前のページへ"""
        if self.current > 0:
            self.current -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="➡️ 次へ", style=discord.ButtonStyle.primary)
    async def next(self, button: Button, interaction: discord.Interaction):
        """次のページへ"""
        if self.current < len(self.embeds) - 1:
            self.current += 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="🔢 ページ情報", style=discord.ButtonStyle.secondary)
    async def page_info(self, button: Button, interaction: discord.Interaction):
        """現在のページ情報を表示"""
        await interaction.response.send_message(
            f"現在のページ: {self.current + 1} / {len(self.embeds)}", 
            ephemeral=True
        )
    
    async def on_timeout(self):
        """タイムアウト時の処理"""
        try:
            # ボタンを無効化
            for item in self.children:
                item.disabled = True
        except Exception as e:
            self.logger.error(f"Error in on_timeout: {e}")

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

# views/record_view.py に追加するコード

class OpponentClassAnalysisView(View):
    """対戦相手クラス分析表示View（レーティング更新チャンネル用）"""
    
    def __init__(self):
        super().__init__(timeout=None)
        
        # 対戦相手クラス分析ボタン（勝利数順）
        analysis_wins_button = Button(
            label="対戦相手クラス分析（勝利数順）", 
            style=discord.ButtonStyle.success,
            emoji="🏆"
        )
        async def analysis_wins_callback(interaction):
            await self.show_analysis_season_select(interaction, "wins")
        analysis_wins_button.callback = analysis_wins_callback
        self.add_item(analysis_wins_button)
        
        # 対戦相手クラス分析ボタン（勝率順）
        analysis_rate_button = Button(
            label="対戦相手クラス分析（勝率順）", 
            style=discord.ButtonStyle.primary,
            emoji="📊"
        )
        async def analysis_rate_callback(interaction):
            await self.show_analysis_season_select(interaction, "rate")
        analysis_rate_button.callback = analysis_rate_callback
        self.add_item(analysis_rate_button)
    
    async def show_analysis_season_select(self, interaction: discord.Interaction, sort_type: str):
        """対戦相手クラス分析のシーズン選択を表示"""
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        if not user:
            await interaction.response.send_message("ユーザーが見つかりません。", ephemeral=True)
            return
        
        # 対戦相手クラス分析用のシーズン選択を表示
        await interaction.response.send_message(
            content="対戦相手クラス分析のシーズンを選択してください:", 
            view=OpponentAnalysisSeasonSelectView(sort_type), 
            ephemeral=True
        )

class OpponentAnalysisSeasonSelectView(View):
    """対戦相手クラス分析用のシーズン選択View"""
    
    def __init__(self, sort_type: str):
        super().__init__(timeout=None)
        self.sort_type = sort_type
        self.add_item(OpponentAnalysisSeasonSelect(sort_type))

class OpponentAnalysisSeasonSelect(Select):
    """対戦相手クラス分析用のシーズン選択セレクト"""
    
    def __init__(self, sort_type: str):
        self.sort_type = sort_type
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 現在のシーズンと過去のシーズンを取得
        season_model = SeasonModel()
        current_season = season_model.get_current_season()
        past_seasons = season_model.get_past_seasons()
        
        # 全シーズンオプションを一番上に
        options = [discord.SelectOption(label="全シーズン", value="all")]
        
        # 現在のシーズンを追加
        if current_season:
            options.append(discord.SelectOption(
                label=current_season.season_name, 
                value=f"current_{current_season.id}"
            ))
        
        # 過去のシーズンを追加
        for season in past_seasons:
            options.append(discord.SelectOption(
                label=season['season_name'], 
                value=f"past_{season['id']}"
            ))
        
        # 日付で絞り込むオプションを一番下に追加
        options.append(discord.SelectOption(
            label="日付で絞り込む", 
            value="date_range",
            emoji="📅"
        ))
        
        super().__init__(
            placeholder="シーズンを選択してください...", 
            options=options if options else [discord.SelectOption(label="シーズンなし", value="none")]
        )
    
    async def callback(self, interaction: discord.Interaction):
        """シーズン選択のコールバック"""
        selected_value = self.values[0]
        
        if selected_value == "none":
            await interaction.response.send_message("利用可能なシーズンがありません。", ephemeral=True)
            return
        
        if selected_value == "date_range":
            # 日付範囲入力モーダルを表示
            modal = OpponentAnalysisDateRangeModal(self.sort_type)
            await interaction.response.send_modal(modal)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # 選択された値を解析
        if selected_value == "all":
            season_id = None
            season_name = None
        elif selected_value.startswith("current_"):
            season_id = int(selected_value.split("_")[1])
            season_model = SeasonModel()
            season_data = season_model.get_season_by_id(season_id)
            season_name = season_data['season_name'] if season_data else None
        elif selected_value.startswith("past_"):
            season_id = int(selected_value.split("_")[1])
            season_model = SeasonModel()
            season_data = season_model.get_season_by_id(season_id)
            season_name = season_data['season_name'] if season_data else None
        else:
            await interaction.followup.send("無効な選択です。", ephemeral=True)
            return
        
        # クラス選択を表示
        await interaction.followup.send(
            content="分析対象のクラス組み合わせを選択してください（1つまたは2つ）:", 
            view=OpponentAnalysisClassSelectView(self.sort_type, season_id, season_name),
            ephemeral=True
        )

class OpponentAnalysisDateRangeModal(discord.ui.Modal):
    """対戦相手クラス分析用の日付範囲入力モーダル"""
    
    def __init__(self, sort_type: str):
        super().__init__(title="日付範囲を入力してください")
        self.sort_type = sort_type
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 現在の日付を取得してヒントとして使用
        from datetime import datetime, timedelta
        from config.settings import JST
        
        today = datetime.now(JST)
        today_str = today.strftime('%Y-%m-%d')
        week_ago_str = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        
        self.start_date_input = discord.ui.InputText(
            label="開始日",
            placeholder=f"例: {week_ago_str} (YYYY-MM-DD形式)",
            required=True,
            max_length=10
        )
        self.add_item(self.start_date_input)
        
        self.end_date_input = discord.ui.InputText(
            label="終了日", 
            placeholder=f"例: {today_str} (YYYY-MM-DD形式)",
            required=True,
            max_length=10
        )
        self.add_item(self.end_date_input)
    
    async def callback(self, interaction: discord.Interaction):
        """モーダル送信のコールバック"""
        start_date_str = self.start_date_input.value.strip()
        end_date_str = self.end_date_input.value.strip()
        
        # 日付形式のバリデーション
        try:
            from datetime import datetime
            
            # 日付のパース
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            # 開始日が終了日より後でないかチェック
            if start_date > end_date:
                await interaction.response.send_message(
                    "❌ **エラー:** 開始日は終了日より前の日付を指定してください。",
                    ephemeral=True
                )
                return
            
            # ISO形式の文字列に変換
            start_date_iso = f"{start_date_str} 00:00:00"
            end_date_iso = f"{end_date_str} 23:59:59"
            date_range = (start_date_iso, end_date_iso)
            
            # クラス選択を表示
            await interaction.response.send_message(
                content=f"📅 対象期間: **{start_date_str} ～ {end_date_str}**\n"
                        f"分析対象のクラス組み合わせを選択してください（1つまたは2つ）:",
                view=OpponentAnalysisClassSelectView(self.sort_type, None, None, date_range),
                ephemeral=True
            )
            
        except ValueError:
            await interaction.response.send_message(
                "❌ **エラー:** 日付の形式が正しくありません。YYYY-MM-DD形式で入力してください。",
                ephemeral=True
            )

class OpponentAnalysisClassSelectView(View):
    """対戦相手クラス分析用のクラス選択View"""
    
    def __init__(self, sort_type: str, season_id: Optional[int] = None, 
                 season_name: Optional[str] = None, date_range: Optional[tuple] = None):
        super().__init__(timeout=None)
        self.add_item(OpponentAnalysisClassSelect(sort_type, season_id, season_name, date_range))

class OpponentAnalysisClassSelect(Select):
    """対戦相手クラス分析用のクラス選択セレクト"""
    
    def __init__(self, sort_type: str, season_id: Optional[int] = None, 
                 season_name: Optional[str] = None, date_range: Optional[tuple] = None):
        self.sort_type = sort_type
        self.season_id = season_id
        self.season_name = season_name
        self.date_range = date_range
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # データベースからクラス名を取得
        user_model = UserModel()
        valid_classes = user_model.get_valid_classes()
        
        options = [discord.SelectOption(label=cls, value=cls) for cls in valid_classes]
        
        super().__init__(
            placeholder="クラスを選択してください（1つまたは2つ）...", 
            min_values=1, 
            max_values=min(2, len(options)),
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """クラス選択のコールバック"""
        selected_classes = self.values
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 対戦相手クラス分析を実行
            from viewmodels.record_vm import RecordViewModel
            record_vm = RecordViewModel()
            
            await self.show_opponent_class_analysis(
                interaction, selected_classes, self.sort_type, 
                self.season_id, self.season_name, self.date_range
            )
            
        except Exception as e:
            self.logger.error(f"Error in opponent class analysis: {e}")
            await interaction.followup.send("エラーが発生しました。", ephemeral=True)
    
    async def show_opponent_class_analysis(self, interaction: discord.Interaction, 
                                         selected_classes: List[str], sort_type: str,
                                         season_id: Optional[int], season_name: Optional[str],
                                         date_range: Optional[tuple]):
        """対戦相手クラス分析を表示"""
        try:
            # 分析データを取得
            analysis_data = await self.get_opponent_class_analysis_data(
                selected_classes, season_id, season_name, date_range
            )
            
            if not analysis_data:
                await interaction.followup.send(
                    "指定した条件での対戦データが見つかりませんでした。", 
                    ephemeral=True
                )
                return
            
            # ソート
            if sort_type == "wins":
                # 勝利数順（多い順）
                sorted_data = sorted(analysis_data, key=lambda x: x['opponent_wins'], reverse=True)
            else:  # rate
                # 勝率順（高い順）
                sorted_data = sorted(analysis_data, key=lambda x: x['win_rate'], reverse=True)
            
            # 条件説明を作成
            if len(selected_classes) == 1:
                class_desc = f"{selected_classes[0]}単体"
            else:
                class_desc = f"{selected_classes[0]} + {selected_classes[1]}"
            
            if season_name:
                period_desc = f"シーズン {season_name}"
            elif date_range:
                start_date = date_range[0][:10]
                end_date = date_range[1][:10]
                period_desc = f"{start_date} ～ {end_date}"
            else:
                period_desc = "全シーズン"
            
            sort_desc = "勝利数順" if sort_type == "wins" else "勝率順"
            
            # ページ分割して表示
            embeds = self.create_analysis_embeds(
                sorted_data, class_desc, period_desc, sort_desc
            )
            
            if embeds:
                message = await interaction.followup.send(embed=embeds[0], ephemeral=True)
                
                if len(embeds) > 1:
                    view = OpponentAnalysisPaginatorView(embeds)
                    await message.edit(view=view)
            
        except Exception as e:
            self.logger.error(f"Error showing opponent class analysis: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send("分析の実行中にエラーが発生しました。", ephemeral=True)
    
    async def get_opponent_class_analysis_data(self, selected_classes: List[str], 
                                             season_id: Optional[int], season_name: Optional[str],
                                             date_range: Optional[tuple]) -> List[Dict]:
        """対戦相手クラス分析データを取得"""
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
            
            # 対戦相手クラス分析
            opponent_stats = {}
            
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
                
                if len(selected_classes) == 1:
                    class_name = selected_classes[0]
                    if match.user1_selected_class == class_name:
                        my_user_id = match.user1_id
                        opponent_user_id = match.user2_id
                        if match.user2_class_a and match.user2_class_b:
                            opponent_class_combo = tuple(sorted([match.user2_class_a, match.user2_class_b]))
                            opponent_selected_class = match.user2_selected_class
                    elif match.user2_selected_class == class_name:
                        my_user_id = match.user2_id
                        opponent_user_id = match.user1_id
                        if match.user1_class_a and match.user1_class_b:
                            opponent_class_combo = tuple(sorted([match.user1_class_a, match.user1_class_b]))
                            opponent_selected_class = match.user1_selected_class
                else:
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
                        
                        # 勝敗判定
                        if match.winner_user_id == opponent_user_id:
                            opponent_stats[key]['opponent_wins'] += 1
                        else:
                            opponent_stats[key]['my_wins'] += 1
            
            # 結果を整理（試合数0でも表示）
            result = []
            for (combo, selected_class), stats in opponent_stats.items():
                win_rate = (stats['opponent_wins'] / stats['total_matches'] * 100) if stats['total_matches'] > 0 else 0
                
                result.append({
                    'opponent_class_combo': f"{combo[0]} + {combo[1]}",
                    'opponent_selected_class': selected_class,
                    'total_matches': stats['total_matches'],
                    'opponent_wins': stats['opponent_wins'],
                    'my_wins': stats['my_wins'],
                    'win_rate': win_rate
                })
            
            return result
        
        # データベースアクセス
        from models.match import MatchModel
        match_model = MatchModel()
        return match_model.safe_execute(_get_analysis_data) or []
    
    def create_analysis_embeds(self, analysis_data: List[Dict], class_desc: str, 
                             period_desc: str, sort_desc: str) -> List[discord.Embed]:
        """分析結果のEmbedを作成"""
        try:
            from config.settings import get_class_emoji, VALID_CLASSES
        except ImportError:
            # インポートに失敗した場合のフォールバック
            def get_class_emoji(class_name: str) -> str:
                emoji_map = {
                    "エルフ": "🧝",
                    "ロイヤル": "👑", 
                    "ウィッチ": "🧙",
                    "ドラゴン": "🐉",
                    "ナイトメア": "😈",
                    "ビショップ": "⛪",
                    "ネメシス": "🤖"
                }
                return emoji_map.get(class_name, "🎯")
            
            VALID_CLASSES = ['エルフ', 'ロイヤル', 'ウィッチ', 'ドラゴン', 'ナイトメア', 'ビショップ', 'ネメシス']
        
        from itertools import combinations
        
        embeds = []
        
        # 全クラス組み合わせを生成
        all_combinations = []
        for combo in combinations(VALID_CLASSES, 2):
            combo_key = tuple(sorted(combo))
            all_combinations.append(combo_key)
        
        # 完全なデータセットを作成（すべての組み合わせ × すべての選択クラス）
        complete_data = []
        
        # 既存データをマップに変換
        existing_data_map = {}
        for item in analysis_data:
            combo_tuple = tuple(sorted(item['opponent_class_combo'].split(' + ')))
            selected_class = item['opponent_selected_class']
            key = (combo_tuple, selected_class)
            existing_data_map[key] = item
        
        # 全組み合わせに対して完全なデータを作成
        for combo_tuple in all_combinations:
            combo_str = f"{combo_tuple[0]} + {combo_tuple[1]}"
            
            # 組み合わせの合計戦数をチェック
            combo_total_matches = 0
            combo_data = []
            
            # 各組み合わせの2つのクラス選択を確実に作成
            for selected_class in combo_tuple:
                key = (combo_tuple, selected_class)
                
                if key in existing_data_map:
                    # 既存データがある場合
                    item_data = existing_data_map[key]
                    combo_data.append(item_data)
                    combo_total_matches += item_data['total_matches']
                else:
                    # 既存データがない場合、0のデータを作成
                    combo_data.append({
                        'opponent_class_combo': combo_str,
                        'opponent_selected_class': selected_class,
                        'total_matches': 0,
                        'opponent_wins': 0,
                        'my_wins': 0,
                        'win_rate': 0.0
                    })
            
            # 組み合わせ単位で対戦合計が0戦でない場合のみ追加
            if combo_total_matches > 0:
                complete_data.extend(combo_data)
        
        # データが空の場合の処理
        if not complete_data:
            embed = discord.Embed(
                title=f"対戦相手クラス分析 ({sort_desc})",
                description=f"**分析対象:** {class_desc}\n**期間:** {period_desc}\n\n該当するデータがありませんでした。",
                color=discord.Color.orange()
            )
            return [embed]
        
        # ソート（元のソート基準を維持）
        if sort_desc == "勝利数順":
            complete_data.sort(key=lambda x: (x['opponent_wins'], x['win_rate']), reverse=True)
        else:  # 勝率順
            complete_data.sort(key=lambda x: (x['win_rate'], x['opponent_wins']), reverse=True)
        
        # ページごとに処理（11組合せ = 22個のデータ per page）
        items_per_page = 22  # 11組合せ × 2選択 = 22個
        
        for page_start in range(0, len(complete_data), items_per_page):
            page_num = (page_start // items_per_page) + 1
            total_pages = (len(complete_data) + items_per_page - 1) // items_per_page
            
            embed = discord.Embed(
                title=f"対戦相手クラス分析 ({sort_desc}) - Page {page_num}/{total_pages}",
                description=f"**分析対象:** {class_desc}\n**期間:** {period_desc}",
                color=discord.Color.green()
            )
            
            # 現在のページのデータを取得
            page_data = complete_data[page_start:page_start + items_per_page]
            
            # 組み合わせごとにグループ化
            page_combo_groups = {}
            for item in page_data:
                combo = item['opponent_class_combo']
                if combo not in page_combo_groups:
                    page_combo_groups[combo] = []
                page_combo_groups[combo].append(item)
            
            # 組み合わせを名前順でソート
            sorted_combos = sorted(page_combo_groups.keys())
            
            # 各組み合わせを表示
            for combo in sorted_combos:
                items = page_combo_groups[combo]
                
                # 組み合わせ合計を計算
                combo_total_matches = sum(item['total_matches'] for item in items)
                combo_opponent_wins = sum(item['opponent_wins'] for item in items)
                combo_my_wins = sum(item['my_wins'] for item in items)
                combo_win_rate = (combo_opponent_wins / combo_total_matches * 100) if combo_total_matches > 0 else 0
                
                # 組み合わせ合計が0戦の場合はスキップ（二重チェック）
                if combo_total_matches == 0:
                    continue
                
                field_value = f"**組み合わせ合計：** {combo_opponent_wins}勝 - {combo_my_wins}敗 ({combo_win_rate:.1f}%)\n\n"
                
                # クラス選択を名前順でソート
                items.sort(key=lambda x: x['opponent_selected_class'])
                
                # 各クラス選択を表示
                for item in items:
                    class_emoji = get_class_emoji(item['opponent_selected_class'])
                    field_value += (
                        f"└ {class_emoji}**{item['opponent_selected_class']}選択：** "
                        f"{item['opponent_wins']}勝 - {item['my_wins']}敗 "
                        f"({item['win_rate']:.1f}%)\n"
                    )
                
                embed.add_field(
                    name=f"・{combo}",
                    value=field_value,
                    inline=False
                )
            
            embeds.append(embed)
        
        return embeds

class OpponentAnalysisPaginatorView(View):
    """対戦相手クラス分析のページネーションView"""
    
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=600)
        self.embeds = embeds
        self.current = 0
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="⬅️ 前へ", style=discord.ButtonStyle.primary)
    async def previous(self, button: Button, interaction: discord.Interaction):
        """前のページへ"""
        if self.current > 0:
            self.current -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="➡️ 次へ", style=discord.ButtonStyle.primary)
    async def next(self, button: Button, interaction: discord.Interaction):
        """次のページへ"""
        if self.current < len(self.embeds) - 1:
            self.current += 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="🔢 ページ情報", style=discord.ButtonStyle.secondary)
    async def page_info(self, button: Button, interaction: discord.Interaction):
        """現在のページ情報を表示"""
        await interaction.response.send_message(
            f"現在のページ: {self.current + 1} / {len(self.embeds)}", 
            ephemeral=True
        )
    
    async def on_timeout(self):
        """タイムアウト時の処理"""
        try:
            for item in self.children:
                item.disabled = True
        except Exception as e:
            self.logger.error(f"Error in on_timeout: {e}")


# DetailedRecordView クラスに追加するメソッド
class DetailedRecordView(View):
    """詳細戦績表示View（レーティング更新チャンネル用）"""
    
    def __init__(self):
        super().__init__(timeout=None)
        
        # 既存の詳細な戦績ボタン
        detailed_record_button = Button(label="詳細な戦績", style=discord.ButtonStyle.success)
        async def detailed_record_callback(interaction):
            await self.show_detailed_season_select(interaction)
        detailed_record_button.callback = detailed_record_callback
        self.add_item(detailed_record_button)
        
        # 新しい対戦相手クラス分析ボタン（勝利数順）
        analysis_wins_button = Button(
            label="対戦相手クラス分析（勝利数順）", 
            style=discord.ButtonStyle.primary,
            emoji="🏆"
        )
        async def analysis_wins_callback(interaction):
            await self.show_analysis_season_select(interaction, "wins")
        analysis_wins_button.callback = analysis_wins_callback
        self.add_item(analysis_wins_button)
        
        # 新しい対戦相手クラス分析ボタン（勝率順）
        analysis_rate_button = Button(
            label="対戦相手クラス分析（勝率順）", 
            style=discord.ButtonStyle.secondary,
            emoji="📊"
        )
        async def analysis_rate_callback(interaction):
            await self.show_analysis_season_select(interaction, "rate")
        analysis_rate_button.callback = analysis_rate_callback
        self.add_item(analysis_rate_button)
    
    async def show_detailed_season_select(self, interaction: discord.Interaction):
        """詳細戦績のシーズン選択を表示"""
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        if not user:
            await interaction.response.send_message("ユーザーが見つかりません。", ephemeral=True)
            return
        
        # 詳細戦績用のシーズン選択を表示
        await interaction.response.send_message(
            content="詳細戦績のシーズンを選択してください:", 
            view=DetailedSeasonSelectView(), 
            ephemeral=True
        )
    
    async def show_analysis_season_select(self, interaction: discord.Interaction, sort_type: str):
        """対戦相手クラス分析のシーズン選択を表示"""
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        if not user:
            await interaction.response.send_message("ユーザーが見つかりません。", ephemeral=True)
            return
        
        sort_desc = "勝利数順" if sort_type == "wins" else "勝率順"
        # 対戦相手クラス分析用のシーズン選択を表示
        await interaction.response.send_message(
            content=f"対戦相手クラス分析（{sort_desc}）のシーズンを選択してください:", 
            view=OpponentAnalysisSeasonSelectView(sort_type), 
            ephemeral=True
        )