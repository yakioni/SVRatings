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
        
        # 既存の現在シーズンボタンのみ
        current_season_button = Button(label="現在のシーズン", style=discord.ButtonStyle.primary)
        async def current_season_callback(interaction):
            await self.show_class_select(interaction)
        current_season_button.callback = current_season_callback
        self.add_item(current_season_button)
    
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
                content="クラスを選択してください:", 
                view=ClassSelectView(season_id=season.id), 
                ephemeral=True
            )
        else:
            await interaction.response.send_message("シーズンが見つかりません。", ephemeral=True)

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