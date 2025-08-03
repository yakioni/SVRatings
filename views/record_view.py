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
        current_season_button = Button(label="BO1単位戦績", style=discord.ButtonStyle.primary)
        async def current_season_callback(interaction):
            await self.show_class_select(interaction)
        current_season_button.callback = current_season_callback
        self.add_item(current_season_button)
        
        # 新しい直近50戦ボタンを追加（ユーザー検索ボタンと置き換え）
        last50_button = Button(label="直近50戦", style=discord.ButtonStyle.secondary, emoji="📋")
        async def last50_callback(interaction):
            await self.show_last50_matches(interaction)
        last50_button.callback = last50_callback
        self.add_item(last50_button)
    
    async def show_class_select(self, interaction: discord.Interaction):
        """通常のクラス選択を表示"""
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        if user and not user['latest_season_matched']:
            await interaction.response.send_message("未参加です", ephemeral=True)
            return
        
        season_model = SeasonModel()
        season = season_model.get_current_season()
        
        if season:
            await interaction.response.send_message(
                content="クラスを選択してください：", 
                view=RecordClassSelectView(season_id=season.id), 
                ephemeral=True
            )
        else:
            await interaction.response.send_message("シーズンが見つかりません。", ephemeral=True)
    
    async def show_last50_matches(self, interaction: discord.Interaction):
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
            
            # 試合履歴を取得
            match_model = MatchModel()
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
            
            # 最初の10戦を表示
            await self.display_matches_page(interaction, completed_matches, 0, user_data)
            
        except Exception as e:
            logging.error(f"Error showing last 50 matches: {e}")
            await interaction.followup.send("直近50戦の取得中にエラーが発生しました。", ephemeral=True)
    
    async def display_matches_page(self, interaction: discord.Interaction, matches: List[dict], 
                                  page: int, user_data: dict):
        user_model = UserModel()
        
        def get_attr(data, attr_name, default=None):
            if isinstance(data, dict):
                return data.get(attr_name, default)
            else:
                return getattr(data, attr_name, default)
        
        user_id = get_attr(user_data, 'id')
        user_name = get_attr(user_data, 'user_name')
        
        # ページング設定
        matches_per_page = 10
        start_idx = page * matches_per_page
        end_idx = min(start_idx + matches_per_page, len(matches))
        page_matches = matches[start_idx:end_idx]
        
        # Embedを作成
        total_pages = (len(matches) + matches_per_page - 1) // matches_per_page
        embed = discord.Embed(
            title=f"{user_name} の直近50戦 (Page {page + 1}/{total_pages})",
            description="各試合のボタンを押すとその相手との全対戦履歴が表示されます",
            color=discord.Color.blue()
        )
        
        # Viewを作成（ページネーションとマッチボタン）
        view = Last50MatchesView(matches, page, user_data, page_matches)
        
        # 各試合の情報を表示
        for i, match in enumerate(page_matches):
            if match['user1_id'] == user_id:
                opponent_data = user_model.get_user_by_id(match['user2_id'])
                user_rating_change = match.get('user1_rating_change', 0)
                after_rating = match.get('after_user1_rating')
                user_won = match['winner_user_id'] == user_id
                user_selected_class = match.get('user1_selected_class', 'Unknown')
            else:
                opponent_data = user_model.get_user_by_id(match['user1_id'])
                user_rating_change = match.get('user2_rating_change', 0)
                after_rating = match.get('after_user2_rating')
                user_won = match['winner_user_id'] == user_id
                user_selected_class = match.get('user2_selected_class', 'Unknown')
            
            if opponent_data:
                opponent_name = get_attr(opponent_data, 'user_name', 'Unknown')
                opponent_discord_id = get_attr(opponent_data, 'discord_id', None)
                
                # Discord Username を取得
                opponent_username = None
                if opponent_discord_id:
                    try:
                        discord_member = interaction.guild.get_member(int(opponent_discord_id))
                        if discord_member:
                            opponent_username = discord_member.name  # @username の username部分
                    except (ValueError, AttributeError):
                        pass
                
                if opponent_username:
                    opponent_display = f"{opponent_name} (@{opponent_username})"
                else:
                    opponent_display = opponent_name
            else:
                opponent_display = 'Unknown'
            
            # 試合結果の表示
            result_emoji = "🔵" if user_won else "🔴"
            result_text = "勝利" if user_won else "敗北"
            rating_change_str = f"{user_rating_change:+.0f}" if user_rating_change != 0 else "±0"
            
            # 日付のフォーマット
            match_date = match.get('match_date', '')
            if match_date:
                match_date = match_date[:16]
            else:
                match_date = 'Unknown'
            
            field_value = (
                f"**対戦相手:** {opponent_display}\n"
                f"**結果:** {result_text}\n"
                f"**使用クラス:** {user_selected_class}\n"
                f"**レート変動:** {rating_change_str} (→ {after_rating:.0f})\n"
                f"**ボタン番号:** {start_idx + i + 1}"
            )
            
            embed.add_field(
                name=f"{result_emoji} {match_date}",
                value=field_value,
                inline=True
            )
        
        # メッセージを送信または編集
        if page == 0:
            # 初回送信
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            # ページ更新
            await interaction.edit_original_response(embed=embed, view=view)

class Last50MatchesView(View):
    
    def __init__(self, all_matches: List[dict], current_page: int, user_data: dict, page_matches: List[dict]):
        super().__init__(timeout=600)
        self.all_matches = all_matches
        self.current_page = current_page
        self.user_data = user_data
        self.page_matches = page_matches
        
        # ページネーションボタン
        matches_per_page = 10
        total_pages = (len(all_matches) + matches_per_page - 1) // matches_per_page
        
        if current_page > 0:
            prev_button = Button(label="⬅️ 前へ", style=discord.ButtonStyle.secondary, row=0)
            prev_button.callback = self.previous_page
            self.add_item(prev_button)
        
        if current_page < total_pages - 1:
            next_button = Button(label="➡️ 次へ", style=discord.ButtonStyle.secondary, row=0)
            next_button.callback = self.next_page
            self.add_item(next_button)
        
        # 各試合のボタンを追加（最大10個）
        start_idx = current_page * matches_per_page
        for i, match in enumerate(page_matches):
            button_num = start_idx + i + 1
            button = MatchOpponentButton(
                label=f"{button_num}番",
                match_data=match,
                user_data=user_data,
                row=1 + (i // 5)  # 5個ずつ行を分ける
            )
            self.add_item(button)
    
    async def previous_page(self, interaction: discord.Interaction):
        """前のページへ"""
        if self.current_page > 0:
            await interaction.response.defer()
            view = CurrentSeasonRecordView()
            await view.display_matches_page(interaction, self.all_matches, self.current_page - 1, self.user_data)
    
    async def next_page(self, interaction: discord.Interaction):
        """次のページへ"""
        matches_per_page = 10
        total_pages = (len(self.all_matches) + matches_per_page - 1) // matches_per_page
        if self.current_page < total_pages - 1:
            await interaction.response.defer()
            view = CurrentSeasonRecordView()
            await view.display_matches_page(interaction, self.all_matches, self.current_page + 1, self.user_data)

class MatchOpponentButton(Button):
    
    def __init__(self, label: str, match_data: dict, user_data: dict, row: int):
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=row)
        self.match_data = match_data
        self.user_data = user_data
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            def get_attr(data, attr_name, default=None):
                if isinstance(data, dict):
                    return data.get(attr_name, default)
                else:
                    return getattr(data, attr_name, default)
            
            user_id = get_attr(self.user_data, 'id')
            user_name = get_attr(self.user_data, 'user_name')
            
            # 対戦相手のIDを取得
            if self.match_data['user1_id'] == user_id:
                opponent_id = self.match_data['user2_id']
            else:
                opponent_id = self.match_data['user1_id']
            
            # 対戦相手の情報を取得
            user_model = UserModel()
            opponent_data = user_model.get_user_by_id(opponent_id)
            
            if not opponent_data:
                await interaction.followup.send("対戦相手の情報が見つかりません。", ephemeral=True)
                return
            
            opponent_name = get_attr(opponent_data, 'user_name', 'Unknown')
            opponent_discord_id = get_attr(opponent_data, 'discord_id', None)

            # Discord Username を取得
            opponent_username = None
            if opponent_discord_id:
                try:
                    discord_member = interaction.guild.get_member(int(opponent_discord_id))
                    if discord_member:
                        opponent_username = discord_member.name
                except (ValueError, AttributeError):
                    pass

            if opponent_username:
                opponent_display = f"{opponent_name} (@{opponent_username})"
                # タイトルでも使用
                title = f"{user_name} vs {opponent_display}"
            else:
                opponent_display = opponent_name
                title = f"{user_name} vs {opponent_display}"

            # 全シーズンの対戦履歴を取得
            match_model = MatchModel()
            vs_matches = match_model.get_user_vs_user_history(user_id, opponent_id)
            
            if not vs_matches:
                await interaction.followup.send(
                    f"**{user_name}** vs **{opponent_name}** の対戦履歴はありません。",
                    ephemeral=True
                )
                return
            
            # 完了した試合のみフィルタリング
            completed_matches = []
            for match in vs_matches:
                if (match.get('winner_user_id') is not None and 
                    match.get('after_user1_rating') is not None and 
                    match.get('after_user2_rating') is not None):
                    completed_matches.append(match)
            
            if not completed_matches:
                await interaction.followup.send(
                    f"**{user_name}** vs **{opponent_name}** の完了した対戦はありません。",
                    ephemeral=True
                )
                return
            
            # 勝敗を集計
            user_wins = 0
            opponent_wins = 0
            
            for match in completed_matches:
                if match['winner_user_id'] == user_id:
                    user_wins += 1
                elif match['winner_user_id'] == opponent_id:
                    opponent_wins += 1
            
            total_matches = user_wins + opponent_wins
            user_win_rate = (user_wins / total_matches) * 100
            
            # 対戦履歴をEmbedで表示
            embeds = []
            current_embed = None
            matches_per_embed = 8
            
            for i, match in enumerate(completed_matches):
                if i % matches_per_embed == 0:
                    page_num = i // matches_per_embed + 1
                    total_pages = (len(completed_matches) + matches_per_embed - 1) // matches_per_embed
                    
                    description = f"{user_wins}勝{opponent_wins}敗(勝率{user_win_rate:.0f}%) | Page {page_num}/{total_pages}"
                    
                    current_embed = discord.Embed(
                        title=title,
                        description=description,
                        color=discord.Color.purple()
                    )
                    embeds.append(current_embed)
                
                # ユーザーの視点で情報を整理
                if match['user1_id'] == user_id:
                    # ユーザーがuser1
                    user_rating_change = match.get('user1_rating_change', 0)
                    opponent_rating_change = match.get('user2_rating_change', 0)
                    user_after_rating = match.get('after_user1_rating')
                    opponent_after_rating = match.get('after_user2_rating')
                    user_won = match['winner_user_id'] == user_id
                    user_selected_class = match.get('user1_selected_class', 'Unknown')
                    opponent_selected_class = match.get('user2_selected_class', 'Unknown')
                else:
                    # ユーザーがuser2
                    user_rating_change = match.get('user2_rating_change', 0)
                    opponent_rating_change = match.get('user1_rating_change', 0)
                    user_after_rating = match.get('after_user2_rating')
                    opponent_after_rating = match.get('after_user1_rating')
                    user_won = match['winner_user_id'] == user_id
                    user_selected_class = match.get('user2_selected_class', 'Unknown')
                    opponent_selected_class = match.get('user1_selected_class', 'Unknown')
                
                # None値チェックとデフォルト値設定
                if user_rating_change is None:
                    user_rating_change = 0
                if opponent_rating_change is None:
                    opponent_rating_change = 0
                if user_after_rating is None:
                    user_after_rating = 0
                if opponent_after_rating is None:
                    opponent_after_rating = 0
                
                # クラス情報の整理
                if not user_selected_class:
                    user_selected_class = 'Unknown'
                if not opponent_selected_class:
                    opponent_selected_class = 'Unknown'
                
                # 試合結果の表示
                result_emoji = "🔵" if user_won else "🔴"
                result_text = "勝利" if user_won else "敗北"
                user_rating_change_str = f"{user_rating_change:+.0f}" if user_rating_change != 0 else "±0"
                opponent_rating_change_str = f"{opponent_rating_change:+.0f}" if opponent_rating_change != 0 else "±0"
                
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
                    f"**あなたのクラス：** {user_selected_class}\n"
                    f"**相手のクラス：** {opponent_selected_class}\n"
                    f"**レート変動：**\n"
                    f"├ あなた： {user_rating_change_str} (→ {user_after_rating:.0f})\n"
                    f"└ 相手： {opponent_rating_change_str} (→ {opponent_after_rating:.0f})"
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
                    view = MatchHistoryPaginatorView(embeds)
                    await message.edit(view=view)
            
        except Exception as e:
            self.logger.error(f"Error showing opponent history: {e}")
            await interaction.followup.send("対戦履歴の取得中にエラーが発生しました。", ephemeral=True)

class MatchHistoryPaginatorView(View):
    
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=600)
        self.embeds = embeds
        self.current = 0
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @discord.ui.button(label="⬅️ 前へ", style=discord.ButtonStyle.primary)
    async def previous(self, button: Button, interaction: discord.Interaction):
        if self.current > 0:
            self.current -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="➡️ 次へ", style=discord.ButtonStyle.primary)
    async def next(self, button: Button, interaction: discord.Interaction):
        if self.current < len(self.embeds) - 1:
            self.current += 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)
        else:
            await interaction.response.defer()
    
    async def on_timeout(self):
        try:
            for item in self.children:
                item.disabled = True
        except Exception as e:
            self.logger.error(f"Error in on_timeout: {e}")

class DetailedMatchHistoryView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # 詳細な全対戦履歴ボタン
        detailed_match_history_button = Button(label="詳細な全対戦履歴", style=discord.ButtonStyle.secondary)
        async def detailed_match_history_callback(interaction):
            await self.show_detailed_match_history(interaction)
        detailed_match_history_button.callback = detailed_match_history_callback
        self.add_item(detailed_match_history_button)
    
    async def show_detailed_match_history(self, interaction: discord.Interaction):
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

# views/record_view.py の DetailedSeasonSelect クラスの修正版

class DetailedSeasonSelect(Select):
    """詳細戦績用のシーズン選択セレクト"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        season_model = SeasonModel()
        current_season = season_model.get_current_season()
        past_seasons = season_model.get_past_seasons()
        
        options = [discord.SelectOption(label="全シーズン", value="all")]

        options.append(discord.SelectOption(
            label="日付で絞り込む", 
            value="date_range",
        ))
        
        # 現在のシーズンを追加（修正）
        if current_season:
            options.append(discord.SelectOption(
                label=f"{current_season.season_name} (現在)", 
                value=f"season_{current_season.id}",
                emoji="🌟"
            ))
        
        # 過去のシーズンを追加
        if past_seasons:
            for season in past_seasons:
                options.append(discord.SelectOption(
                    label=season['season_name'], 
                    value=f"season_{season['id']}"
                ))
        
        super().__init__(
            placeholder="シーズンを選択してください...", 
            options=options if options else [discord.SelectOption(label="シーズンなし", value="none")]
        )

    async def callback(self, interaction: discord.Interaction):
        """詳細シーズン選択のコールバック"""
        selection = self.values[0]
        
        if selection == "all":
            # 全シーズンを選択した場合
            await interaction.response.send_message(
                content="クラスを選択してください：",
                view=DetailedClassSelectView(season_id=None, date_range=None),
                ephemeral=True
            )
        elif selection == "date_range":
            # 日付範囲を選択した場合
            modal = DateRangeInputModal()
            await interaction.response.send_modal(modal)
        elif selection.startswith("season_"):
            # 特定のシーズンを選択した場合
            season_id = int(selection.split("_")[1])
            season_model = SeasonModel()
            season_data = season_model.get_season_by_id(season_id)
            season_name = season_data['season_name'] if season_data else "不明"
            
            await interaction.response.send_message(
                content=f"クラスを選択してください：",
                view=DetailedClassSelectView(season_id=season_id, date_range=None),
                ephemeral=True
            )
        else:
            await interaction.response.send_message("無効な選択です。", ephemeral=True)

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
        """詳細クラス選択のコールバック（修正版）"""
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
                # 特定のクラス（1つまたは2つ）を選択した場合（修正：必ず詳細戦績を表示）
                await record_vm.show_detailed_class_stats(interaction, user_id, selected_classes, self.season_id, self.date_range)
        
        except Exception as e:
            self.logger.error(f"Error in detailed class selection callback: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send("エラーが発生しました。", ephemeral=True)
        
        # インタラクションメッセージを削除する
        try:
            await interaction.delete_original_response()
        except discord.errors.NotFound:
            pass

class RecordClassSelectView(View):
    """戦績用クラス選択View（単一クラスまたは全クラスのみ選択可能）"""
    
    def __init__(self, season_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.add_item(RecordClassSelect(season_id))

class RecordClassSelect(Select):
    """戦績用クラス選択セレクト（単一クラスまたは全クラスのみ選択可能）"""
    
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
            max_values=1, 
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
                await record_vm.show_class_stats(interaction, user_id, selected_class, self.season_id)

        except Exception as e:
            self.logger.error(f"Error in class selection callback: {e}")
            await interaction.followup.send("エラーが発生しました。", ephemeral=True)

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
                value = f"{season['id']}_{season['season_name']}"
            options.append(discord.SelectOption(label=season['season_name'], value=value))
            used_values.add(value)

        select = Select(placeholder="シーズンを選択してください...", options=options)

        async def select_callback(select_interaction):
            if not select_interaction.response.is_done():
                await select_interaction.response.defer(ephemeral=True)

            selected_season_id = select_interaction.data['values'][0]

            if selected_season_id == "all":
                await select_interaction.followup.send(
                    content="クラスを選択してください:", 
                    view=RecordClassSelectView(season_id=None),  # 修正: RecordClassSelectViewを使用
                    ephemeral=True
                )
            else:
                selected_season_id = int(selected_season_id.split('_')[0])
                user_model = UserModel()
                user = user_model.get_user_by_discord_id(str(select_interaction.user.id))
                
                if not user:
                    await select_interaction.followup.send("ユーザーが見つかりません。", ephemeral=True)
                    return

                season_model = SeasonModel()
                user_record = season_model.get_user_season_record(user['id'], selected_season_id)

                if user_record is None:
                    message = await select_interaction.followup.send("未参加です。", ephemeral=True)
                    await asyncio.sleep(10)
                    try:
                        await message.delete()
                    except discord.errors.NotFound:
                        pass
                    return

                await select_interaction.followup.send(
                    content="クラスを選択してください:", 
                    view=RecordClassSelectView(season_id=selected_season_id),  # 修正: RecordClassSelectViewを使用
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
                
                if opponent_data:
                    opponent_name = get_attr(opponent_data, 'user_name', 'Unknown')
                    opponent_discord_id = get_attr(opponent_data, 'discord_id', None)
                    
                    # Discord Username を取得
                    opponent_username = None
                    if opponent_discord_id:
                        try:
                            discord_member = interaction.guild.get_member(int(opponent_discord_id))
                            if discord_member:
                                opponent_username = discord_member.name
                        except (ValueError, AttributeError):
                            pass
                    
                    if opponent_username:
                        opponent_display = f"{opponent_name} (@{opponent_username})"
                    else:
                        opponent_display = opponent_name
                else:
                    opponent_display = 'Unknown'
                
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
                    f"vs {opponent_display}\n"
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

class OpponentClassAnalysisView(View):
    
    def __init__(self):
        super().__init__(timeout=None)
        
        analysis_wins_button = Button(
            label="投げられたクラス分析（勝利数順）", 
            style=discord.ButtonStyle.success,
            emoji="🏆"
        )
        async def analysis_wins_callback(interaction):
            await self.show_analysis_season_select(interaction, "wins")
        analysis_wins_button.callback = analysis_wins_callback
        self.add_item(analysis_wins_button)
        
        analysis_rate_button = Button(
            label="投げられたクラス分析（勝率順）", 
            style=discord.ButtonStyle.primary,
            emoji="📊"
        )
        async def analysis_rate_callback(interaction):
            await self.show_analysis_season_select(interaction, "rate")
        analysis_rate_button.callback = analysis_rate_callback
        self.add_item(analysis_rate_button)
    
    async def show_analysis_season_select(self, interaction: discord.Interaction, sort_type: str):
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        if not user:
            await interaction.response.send_message("ユーザーが見つかりません。", ephemeral=True)
            return
        
        await interaction.response.send_message(
            content="投げられたクラス分析のシーズンを選択してください:", 
            view=OpponentAnalysisSeasonSelectView(sort_type), 
            ephemeral=True
        )

class OpponentAnalysisSeasonSelectView(View):
    
    def __init__(self, sort_type: str):
        super().__init__(timeout=None)
        self.sort_type = sort_type
        self.add_item(OpponentAnalysisSeasonSelect(sort_type))

class OpponentAnalysisSeasonSelect(Select):
    
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
            content="自分の使用クラスを選択してください。1つのみ選んだ場合、そのクラスを含むすべての対戦を集計します", 
            view=OpponentAnalysisClassSelectView(self.sort_type, season_id, season_name),
            ephemeral=True
        )

class OpponentAnalysisDateRangeModal(discord.ui.Modal):
    
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
                        f"自分の使用クラスを選択してください。1つのみ選んだ場合、そのクラスを含むすべての対戦を集計します",
                view=OpponentAnalysisClassSelectView(self.sort_type, None, None, date_range),
                ephemeral=True
            )
            
        except ValueError:
            await interaction.response.send_message(
                "❌ **エラー:** 日付の形式が正しくありません。YYYY-MM-DD形式で入力してください。",
                ephemeral=True
            )

class OpponentAnalysisClassSelectView(View):
    
    def __init__(self, sort_type: str, season_id: Optional[int] = None, 
                 season_name: Optional[str] = None, date_range: Optional[tuple] = None):
        super().__init__(timeout=None)
        self.add_item(OpponentAnalysisClassSelect(sort_type, season_id, season_name, date_range))

class OpponentAnalysisClassSelect(Select):
    
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
            # 分析データを取得
            analysis_data = await self.get_opponent_class_analysis_data(
                selected_classes, self.season_id, self.season_name, self.date_range
            )
            
            if not analysis_data:
                await interaction.followup.send(
                    "指定した条件での対戦データが見つかりませんでした。", 
                    ephemeral=True
                )
                return
            
            # ソート修正
            if self.sort_type == "wins":
                # 勝利数順（自分の勝利数で多い順）
                sorted_data = sorted(analysis_data, key=lambda x: (x['my_wins'], x['win_rate']), reverse=True)
            else:  # rate
                # 勝率順（高い順、同率時は勝利数で）
                sorted_data = sorted(analysis_data, key=lambda x: (x['win_rate'], x['my_wins']), reverse=True)
            
            # 条件説明を作成
            if len(selected_classes) == 1:
                class_desc = f"{selected_classes[0]}単体"
            else:
                class_desc = f"{selected_classes[0]} + {selected_classes[1]}"
            
            if self.season_name:
                period_desc = f"シーズン {self.season_name}"
            elif self.date_range:
                start_date = self.date_range[0][:10]
                end_date = self.date_range[1][:10]
                period_desc = f"{start_date} ～ {end_date}"
            else:
                period_desc = "全シーズン"
            
            sort_desc = "勝利数順" if self.sort_type == "wins" else "勝率順"
            
            # ページ分割して表示
            embeds = self.create_analysis_embeds(
                sorted_data, class_desc, period_desc, sort_desc
            )
            
            if embeds:
                message = await interaction.followup.send(embed=embeds[0], ephemeral=True)
                
                if len(embeds) > 1:
                    from views.record_view import OpponentAnalysisPaginatorView
                    view = OpponentAnalysisPaginatorView(embeds)
                    await message.edit(view=view)
            
        except Exception as e:
            self.logger.error(f"Error in opponent class analysis: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            await interaction.followup.send("エラーが発生しました。", ephemeral=True)
    
    async def get_opponent_class_analysis_data(self, selected_classes: List[str], 
                                             season_id: Optional[int], season_name: Optional[str],
                                             date_range: Optional[tuple]) -> List[Dict]:
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
                # 単体クラス - 修正版
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
                # 2つのクラス組み合わせ（既存のまま）
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
                # 2つのクラス組み合わせ（既存の処理をそのまま維持）
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
                
                # マッチデータを分析（既存の処理）
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
                
                # 結果を整形（既存の処理）
                result = []
                for (combo, selected_class), stats in opponent_stats.items():
                    if stats['total_matches'] > 0:
                        combo_str = f"{combo[0]} + {combo[1]}"
                        win_rate = (stats['my_wins'] / stats['total_matches']) * 100
                        result.append({
                            'opponent_class_combo': combo_str,
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
        
        embeds = []
        
        # 単一クラス選択時と組み合わせ選択時で処理を分ける
        if "単体" in class_desc:
            # 単一クラス選択時：7種類のクラス個別表示（既存処理のまま）
            if not analysis_data:
                embed = discord.Embed(
                    title=f"投げられたクラス分析 ({sort_desc})",
                    description=f"**分析対象:** {class_desc}\n**期間:** {period_desc}\n\n該当するデータがありませんでした。",
                    color=discord.Color.orange()
                )
                return [embed]
            
            # 1ページあたり7クラス表示
            items_per_page = 7
            
            for page_start in range(0, len(analysis_data), items_per_page):
                page_num = (page_start // items_per_page) + 1
                total_pages = (len(analysis_data) + items_per_page - 1) // items_per_page
                
                embed = discord.Embed(
                    title=f"投げられたクラス分析 ({sort_desc}) - Page {page_num}/{total_pages}",
                    description=f"**分析対象:** {class_desc}\n**期間:** {period_desc}",
                    color=discord.Color.green()
                )
                
                # 現在のページのデータを取得
                page_data = analysis_data[page_start:page_start + items_per_page]
                
                # 各クラスの戦績を表示
                for item in page_data:
                    opponent_class = item['opponent_class_combo']  # 単一クラス名
                    total_matches = item['total_matches']
                    opponent_wins = item['opponent_wins']
                    my_wins = item['my_wins']
                    win_rate = item['win_rate']
                    
                    # クラス絵文字を取得
                    class_emoji = get_class_emoji(opponent_class)
                    
                    # シンプルな1行表示: "3勝 - 2敗 (60.0%)"
                    field_value = f"{my_wins}勝 - {opponent_wins}敗 ({win_rate:.1f}%)"
                    
                    embed.add_field(
                        name=f"{class_emoji} {opponent_class}",
                        value=field_value,
                        inline=True
                    )
                
                embeds.append(embed)
            
            return embeds
        
        else:
            # 2つのクラス組み合わせ選択時：修正版
            from itertools import combinations
            
            # 全クラス組み合わせを生成
            all_combinations = []
            for combo in combinations(VALID_CLASSES, 2):
                combo_key = tuple(sorted(combo))
                all_combinations.append(combo_key)
            
            # 組み合わせレベルでのデータを作成
            combo_summary = {}
            
            # 既存データをマップに変換
            existing_data_map = {}
            for item in analysis_data:
                combo_tuple = tuple(sorted(item['opponent_class_combo'].split(' + ')))
                selected_class = item['opponent_selected_class']
                key = (combo_tuple, selected_class)
                existing_data_map[key] = item
            
            # 組み合わせごとの合計を計算
            for combo_tuple in all_combinations:
                combo_str = f"{combo_tuple[0]} + {combo_tuple[1]}"
                
                # 組み合わせの合計データを計算
                total_my_wins = 0
                total_opponent_wins = 0
                total_matches = 0
                combo_class_data = []
                
                # 各クラス選択のデータを収集
                for selected_class in combo_tuple:
                    key = (combo_tuple, selected_class)
                    
                    if key in existing_data_map:
                        item_data = existing_data_map[key]
                        total_my_wins += item_data['my_wins']
                        total_opponent_wins += item_data['opponent_wins']
                        total_matches += item_data['total_matches']
                        combo_class_data.append(item_data)
                    else:
                        # データがない場合は0データを作成
                        zero_data = {
                            'opponent_class_combo': combo_str,
                            'opponent_selected_class': selected_class,
                            'total_matches': 0,
                            'opponent_wins': 0,
                            'my_wins': 0,
                            'win_rate': 0.0
                        }
                        combo_class_data.append(zero_data)
                
                # 組み合わせに試合があった場合のみ追加
                if total_matches > 0:
                    combo_win_rate = (total_my_wins / total_matches) * 100
                    
                    # 各クラス選択を勝率順でソート
                    combo_class_data.sort(key=lambda x: (x['win_rate'], x['my_wins']), reverse=True)
                    
                    combo_summary[combo_tuple] = {
                        'combo_str': combo_str,
                        'total_my_wins': total_my_wins,
                        'total_opponent_wins': total_opponent_wins,
                        'total_matches': total_matches,
                        'combo_win_rate': combo_win_rate,
                        'class_data': combo_class_data
                    }
            
            # データが空の場合の処理
            if not combo_summary:
                embed = discord.Embed(
                    title=f"投げられたクラス分析 ({sort_desc})",
                    description=f"**分析対象:** {class_desc}\n**期間:** {period_desc}\n\n該当するデータがありませんでした。",
                    color=discord.Color.orange()
                )
                return [embed]
            
            # 組み合わせをソート
            combo_list = list(combo_summary.values())
            if sort_desc == "勝利数順":
                # 自分の勝利数順（多い順、同数時は勝率順）
                combo_list.sort(key=lambda x: (x['total_my_wins'], x['combo_win_rate']), reverse=True)
            else:  # 勝率順
                # 勝率順（高い順、同率時は勝利数順）
                combo_list.sort(key=lambda x: (x['combo_win_rate'], x['total_my_wins']), reverse=True)
            
            # ページごとに処理（6組合せ per page）
            items_per_page = 6
            
            for page_start in range(0, len(combo_list), items_per_page):
                page_num = (page_start // items_per_page) + 1
                total_pages = (len(combo_list) + items_per_page - 1) // items_per_page
                
                embed = discord.Embed(
                    title=f"投げられたクラス分析 ({sort_desc}) - Page {page_num}/{total_pages}",
                    description=f"**分析対象:** {class_desc}\n**期間:** {period_desc}",
                    color=discord.Color.green()
                )
                
                # 現在のページのデータを取得
                page_combos = combo_list[page_start:page_start + items_per_page]
                
                # 各組み合わせを表示
                for combo_data in page_combos:
                    combo_str = combo_data['combo_str']
                    total_my_wins = combo_data['total_my_wins']
                    total_opponent_wins = combo_data['total_opponent_wins']
                    combo_win_rate = combo_data['combo_win_rate']
                    class_data = combo_data['class_data']
                    
                    # タイトル用の絵文字を組み合わせの順番で取得
                    combo_parts = combo_str.split(' + ')
                    title_emoji1 = get_class_emoji(combo_parts[0])
                    title_emoji2 = get_class_emoji(combo_parts[1])
                    
                    # 組み合わせのタイトル
                    combo_title = f"{title_emoji1} {combo_str} (合計：{total_my_wins}勝-{total_opponent_wins}敗 {combo_win_rate:.1f}%)"
                    
                    # 各クラス選択の詳細
                    class_details = []
                    for class_item in class_data:
                        selected_class = class_item['opponent_selected_class']
                        my_wins = class_item['my_wins']
                        opponent_wins = class_item['opponent_wins']
                        win_rate = class_item['win_rate']
                        
                        class_details.append(f"{selected_class}選択: {my_wins}勝-{opponent_wins}敗 {win_rate:.1f}%")
                    
                    field_value = "・" + " ・".join(class_details)
                    
                    embed.add_field(
                        name=combo_title,
                        value=field_value,
                        inline=False
                    )
                
                embeds.append(embed)
            
            return embeds

class OpponentAnalysisPaginatorView(View):
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
        try:
            for item in self.children:
                item.disabled = True
        except Exception as e:
            self.logger.error(f"Error in on_timeout: {e}")


class DetailedRecordView(View):
    
    def __init__(self):
        super().__init__(timeout=None)
        
        # 既存の詳細な戦績ボタン
        detailed_record_button = Button(label="詳細な戦績", style=discord.ButtonStyle.success)
        async def detailed_record_callback(interaction):
            await self.show_detailed_season_select(interaction)
        detailed_record_button.callback = detailed_record_callback
        self.add_item(detailed_record_button)
        
        analysis_wins_button = Button(
            label="投げられたクラス分析（勝利数順）", 
            style=discord.ButtonStyle.primary,
            emoji="🏆"
        )
        async def analysis_wins_callback(interaction):
            await self.show_analysis_season_select(interaction, "wins")
        analysis_wins_button.callback = analysis_wins_callback
        self.add_item(analysis_wins_button)
        
        analysis_rate_button = Button(
            label="投げられたクラス分析（勝率順）", 
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
        user_model = UserModel()
        user = user_model.get_user_by_discord_id(str(interaction.user.id))
        
        if not user:
            await interaction.response.send_message("ユーザーが見つかりません。", ephemeral=True)
            return
        
        sort_desc = "勝利数順" if sort_type == "wins" else "勝率順"
        await interaction.response.send_message(
            content=f"投げられたクラス分析（{sort_desc}）のシーズンを選択してください:", 
            view=OpponentAnalysisSeasonSelectView(sort_type), 
            ephemeral=True
        )