import discord
from discord.ext import commands, tasks
import asyncio
import logging
from config.settings import (
    BOT_TOKEN_1, BOT_TOKEN_2, validate_config,
    BATTLE_CHANNEL_ID, BATTLE_GUIDE_TEXT,
    WELCOME_CHANNEL_ID, PROFILE_CHANNEL_ID, RANKING_CHANNEL_ID,
    PAST_RANKING_CHANNEL_ID, RECORD_CHANNEL_ID, PAST_RECORD_CHANNEL_ID,
    LAST_50_MATCHES_RECORD_CHANNEL_ID, MATCHING_CHANNEL_ID,
    PREVIOUS_RANKING_CHANNEL_ID, PREVIOUS_RECORD_CHANNEL_ID,
    COMMAND_CHANNEL_ID
)
from viewmodels.matchmaking_vm import MatchmakingViewModel, ResultViewModel, CancelViewModel
from viewmodels.ranking_vm import RankingViewModel
from views.matchmaking_view import MatchmakingView, ClassSelectView, ResultView, RateDisplayView
from views.ranking_view import RankingView, RankingButtonView
from views.user_view import RegisterView, ProfileView, AchievementButtonView
from views.record_view import CurrentSeasonRecordView, PastSeasonRecordView, Last50RecordView
from models.base import db_manager
from utils.helpers import safe_purge_channel, safe_send_message
from utils.helpers import safe_create_thread, safe_add_user_to_thread, assign_role

def create_bot_1():
    """Bot1（マッチング・ユーザー管理担当）を作成"""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    
    bot = commands.Bot(command_prefix='$', intents=intents)
    bot.token = BOT_TOKEN_1
    
    # ViewModelの初期化
    matchmaking_vm = MatchmakingViewModel()
    
    # グローバル変数
    active_result_views = {}
    
    @bot.event
    async def on_ready():
        """Bot1の起動時処理"""
        logging.info(f'🤖 Bot1 logged in as {bot.user}')
        
        try:
            await bot.sync_commands()
            logging.info("✅ Commands synced successfully")
        except Exception as e:
            logging.error(f"❌ Failed to sync commands: {e}")
        
        # データベースの初期化確認
        if not db_manager.create_tables_if_not_exist():
            logging.error("❌ Database initialization failed for Bot1")
            return
        
        logging.info("✅ Database initialization completed")
        
        # マッチ作成コールバック関数を定義（on_ready内で定義）
        async def create_battle_thread(user1, user2):
            """マッチが成立した時にスレッドを作成"""
            try:
                logging.info(f"🎯 Starting battle thread creation for: {user1.display_name} vs {user2.display_name}")
                
                battle_channel = bot.get_channel(BATTLE_CHANNEL_ID)
                if not battle_channel:
                    logging.error(f"❌ Battle channel {BATTLE_CHANNEL_ID} not found")
                    return
                
                # スレッドを作成
                thread = await safe_create_thread(battle_channel, user1, user2)
                if not thread:
                    logging.error(f"❌ Failed to create battle thread for {user1.display_name} vs {user2.display_name}")
                    return
                
                logging.info(f"✅ Thread created successfully: {thread.name} (ID: {thread.id})")
                
                # ユーザーをスレッドに追加
                await safe_add_user_to_thread(thread, user1)
                await safe_add_user_to_thread(thread, user2)
                logging.info(f"👥 Added users to thread: {user1.display_name}, {user2.display_name}")
                
                # 試合中ロールを付与
                await assign_role(user1, "試合中")
                await assign_role(user2, "試合中")
                logging.info(f"🏷️ Assigned '試合中' role to both users")
                
                # マッチデータを作成
                match_data = await matchmaking_vm.create_match_data(user1, user2)
                logging.info(f"📊 Match data created for {user1.display_name} vs {user2.display_name}")
                
                # user_dataが辞書かオブジェクトかを判定して適切にアクセス
                def get_attr(data, attr_name, default=None):
                    if isinstance(data, dict):
                        return data.get(attr_name, default)
                    else:
                        return getattr(data, attr_name, default)
                
                # スレッドに初期メッセージを送信
                user1_class1 = get_attr(match_data['user1_data'], 'class1', 'Unknown')
                user1_class2 = get_attr(match_data['user1_data'], 'class2', 'Unknown')
                user2_class1 = get_attr(match_data['user2_data'], 'class1', 'Unknown')
                user2_class2 = get_attr(match_data['user2_data'], 'class2', 'Unknown')
                
                user1_classes = f"{user1_class1} と {user1_class2}"
                user2_classes = f"{user2_class1} と {user2_class2}"
                
                content = (
                    f"**マッチング成立！**\n\n"
                    f"{user1.mention} ({user1_classes}) vs {user2.mention} ({user2_classes})\n\n"
                    f"{BATTLE_GUIDE_TEXT}"
                )
                
                # レート表示ビューも追加
                user1_rating = get_attr(match_data['user1_data'], 'rating', 1500)
                user2_rating = get_attr(match_data['user2_data'], 'rating', 1500)
                
                rate_view = RateDisplayView(
                    str(user1.id), str(user2.id),
                    user1.display_name, user2.display_name,
                    user1_rating, user2_rating
                )
                
                await thread.send(content, view=rate_view)
                logging.info(f"📝 Initial message sent to thread")
                
                # 結果入力ビューを作成
                result_view = ResultView(
                    user1.id, user2.id, 
                    match_data['matching_classes'],
                    thread, matchmaking_vm,
                    active_result_views  # active_result_viewsを渡す
                )
                
                # active_result_viewsに追加
                active_result_views[thread.id] = result_view
                logging.info(f"📋 Result view created and registered for thread {thread.id}")
                
                await thread.send(
                    "試合が終わったら下のボタンを押して勝利数を入力してください。",
                    view=result_view
                )
                
                logging.info(f"🎉 Battle thread setup completed: {user1.display_name} vs {user2.display_name}")
                
            except Exception as e:
                logging.error(f"❌ Error creating battle thread for {user1.display_name if 'user1' in locals() else 'Unknown'} vs {user2.display_name if 'user2' in locals() else 'Unknown'}: {e}")
                import traceback
                logging.error(traceback.format_exc())
        
        # マッチングビューモデルにコールバックを設定
        try:
            if hasattr(matchmaking_vm, 'set_match_creation_callback'):
                matchmaking_vm.set_match_creation_callback(create_battle_thread)
                logging.info("🔗 Match creation callback configured")
            else:
                # メソッドが存在しない場合は手動で設定
                matchmaking_vm.match_creation_callback = create_battle_thread
                logging.warning("⚠️ set_match_creation_callback method not found, setting callback manually")
                logging.info("🔗 Match creation callback configured manually")
        except Exception as e:
            logging.error(f"❌ Failed to set match creation callback: {e}")
            # それでも手動で設定を試行
            try:
                matchmaking_vm.match_creation_callback = create_battle_thread
                logging.info("🔗 Match creation callback set as fallback")
            except Exception as e2:
                logging.error(f"❌ Failed to set callback as fallback: {e2}")
                return
        
        # バックグラウンドタスクの開始
        logging.info("🚀 Starting background tasks...")
        matchmaking_vm.start_background_tasks()
        
        # チャンネルの初期化
        logging.info("🏗️ Setting up channels...")
        await setup_bot1_channels(bot, matchmaking_vm)
        
        logging.info("🎉 Bot1 initialization completed successfully!")
    
    @bot.event
    async def on_member_join(member: discord.Member):
        """メンバー参加時の処理"""
        from models.user import UserModel
        user_model = UserModel()
        
        user_instance = user_model.get_user_by_discord_id(str(member.id))
        if user_instance:
            try:
                await member.edit(nick=user_instance.user_name)
                logging.info(f"Updated nickname for user {member.id} to {user_instance.user_name}")
            except discord.Forbidden:
                logging.warning(f"Failed to update nickname for user {member.id}. Permission denied.")
            except Exception as e:
                logging.error(f"Error updating nickname for user {member.id}: {e}")
    
    # スラッシュコマンドの登録
    @bot.slash_command(
        name="debug_user_data",
        description="ユーザーデータの型と内容を確認します",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    @commands.has_permissions(administrator=True)
    async def debug_user_data(ctx: discord.ApplicationContext, user: discord.Member):
        """デバッグ用：ユーザーデータの型と内容を確認"""
        from models.user import UserModel
        user_model = UserModel()
        
        try:
            user_data = user_model.get_user_by_discord_id(str(user.id))
            
            if not user_data:
                await ctx.respond(f"❌ User {user.display_name} not found in database", ephemeral=True)
                return
            
            # データの型と内容をログ出力
            logging.info(f"🔍 User data for {user.display_name}:")
            logging.info(f"  Type: {type(user_data)}")
            logging.info(f"  Data: {user_data}")
            
            # user_dataが辞書かオブジェクトかを判定して適切にアクセス
            def get_attr(data, attr_name, default='N/A'):
                try:
                    if isinstance(data, dict):
                        return data.get(attr_name, default)
                    else:
                        return getattr(data, attr_name, default)
                except Exception as e:
                    return f"Error: {e}"
            
            debug_info = (
                f"**🔍 User Data Debug for {user.display_name}:**\n"
                f"Data Type: {type(user_data).__name__}\n"
                f"Is Dict: {isinstance(user_data, dict)}\n"
                f"Has __dict__: {hasattr(user_data, '__dict__')}\n\n"
                f"**Attributes:**\n"
                f"ID: {get_attr(user_data, 'id')}\n"
                f"User Name: {get_attr(user_data, 'user_name')}\n"
                f"Discord ID: {get_attr(user_data, 'discord_id')}\n"
                f"Class1: {get_attr(user_data, 'class1')}\n"
                f"Class2: {get_attr(user_data, 'class2')}\n"
                f"Rating: {get_attr(user_data, 'rating')}\n"
                f"Trust Points: {get_attr(user_data, 'trust_points')}\n"
            )
            
            if isinstance(user_data, dict):
                debug_info += f"\n**Dict Keys:** {list(user_data.keys())}"
            elif hasattr(user_data, '__dict__'):
                debug_info += f"\n**Object Attributes:** {list(user_data.__dict__.keys())}"
            
            await ctx.respond(debug_info, ephemeral=True)
            
        except Exception as e:
            await ctx.respond(f"❌ Error debugging user data: {e}", ephemeral=True)
            logging.error(f"Error in debug_user_data: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    @bot.slash_command(
        name="manual_result", 
        description="二人のユーザーの間で勝者を手動で決定します。",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    @commands.has_permissions(administrator=True)
    async def manual_result(ctx: discord.ApplicationContext, 
                          player1: discord.Member, player1_wins: int,
                          player2: discord.Member, player2_wins: int):
        """手動で試合結果を設定"""
        from viewmodels.matchmaking_vm import ResultViewModel
        from models.user import UserModel
        from utils.helpers import remove_role
        
        user_model = UserModel()
        result_vm = ResultViewModel()
        
        # データベースからユーザー情報を取得
        user1_data = user_model.get_user_by_discord_id(str(player1.id))
        user2_data = user_model.get_user_by_discord_id(str(player2.id))
        
        if not user1_data or not user2_data:
            await ctx.respond("指定されたユーザーがデータベースに見つかりませんでした。", ephemeral=True)
            return
        
        # user_dataが辞書かオブジェクトかを判定して適切にアクセス
        def get_attr(data, attr_name, default=None):
            if isinstance(data, dict):
                return data.get(attr_name, default)
            else:
                return getattr(data, attr_name, default)
        
        user1_id = get_attr(user1_data, 'id')
        user2_id = get_attr(user2_data, 'id')
        user1_rating = get_attr(user1_data, 'rating', 1500)
        user2_rating = get_attr(user2_data, 'rating', 1500)
        
        # 結果の妥当性チェック
        is_valid, message = result_vm.validate_result(player1_wins, player2_wins)
        if not is_valid:
            await ctx.respond(f"入力エラー: {message}", ephemeral=True)
            return
        
        # 試合結果を確定
        result = result_vm.finalize_match(
            user1_id, user2_id, player1_wins, player2_wins,
            user1_rating, user2_rating
        )
        
        if result['success']:
            # ロールを削除
            await remove_role(player1, "試合中")
            await remove_role(player2, "試合中")
            
            # レート変動を表示
            user1_change_sign = "+" if result['user1_rating_change'] > 0 else ""
            user2_change_sign = "+" if result['user2_rating_change'] > 0 else ""
            
            await ctx.respond(
                f"{player1.mention} vs {player2.mention} の試合結果:\n"
                f"{player1.display_name}のレート: "
                f"{user1_rating:.0f} -> {result['after_user1_rating']:.0f} "
                f"({user1_change_sign}{result['user1_rating_change']:.0f})\n"
                f"{player2.display_name}のレート: "
                f"{user2_rating:.0f} -> {result['after_user2_rating']:.0f} "
                f"({user2_change_sign}{result['user2_rating_change']:.0f})"
            )
        else:
            await ctx.respond(f"エラー: {result['message']}", ephemeral=True)
    
    @bot.slash_command(name="cancel", description="試合の中止の提案をします。")
    async def cancel(ctx: discord.ApplicationContext):
        """試合中止コマンド"""
        from views.matchmaking_view import CancelConfirmationView
        from utils.helpers import remove_role
        
        if isinstance(ctx.channel, discord.Thread) and ctx.channel.parent_id == BATTLE_CHANNEL_ID:
            user1 = ctx.author
            thread_id = ctx.channel.id
            
            # active_result_viewsからResultViewを取得
            result_view = active_result_views.get(thread_id)
            
            if result_view:
                # 試合中ロールを削除
                await remove_role(user1, "試合中")
                
                # ResultViewのタイマータスクをキャンセル
                result_view.cancel_timeout()
                
                # 対戦相手を取得
                user2_id = result_view.player1_id if result_view.player2_id == user1.id else result_view.player2_id
                user2 = ctx.guild.get_member(user2_id)
                if user2 is None:
                    user2 = await ctx.guild.fetch_member(user2_id)
                
                await ctx.respond(
                    f"対戦中止のリクエストを送信しました。{user1.mention}は次の試合を開始できます。", 
                    ephemeral=True
                )
                
                await ctx.channel.send(
                    f"{user1.mention}により対戦が中止されました。{user2.mention}は中止を受け入れるか回答してください。"
                    f"回答するまで次の試合を開始することはできません。問題がない場合は「はい」を押してください。"
                    f"問題がある場合は「いいえ」を押してスタッフに説明してください。回答期限は48時間です。",
                    view=CancelConfirmationView(user1, user2, ctx.channel)
                )
            else:
                await ctx.respond("このスレッドでは試合が行われていません。", ephemeral=True)
        else:
            await ctx.respond("このコマンドは対戦スレッド内でのみ使用できます。", ephemeral=True)
    
    @bot.slash_command(name="report", description="対戦中に問題が発生した際に報告します。")
    async def report(ctx: discord.ApplicationContext):
        """問題報告コマンド"""
        from utils.helpers import remove_role
        
        if isinstance(ctx.channel, discord.Thread) and ctx.channel.parent_id == BATTLE_CHANNEL_ID:
            user1 = ctx.author
            thread_id = ctx.channel.id
            
            result_view = active_result_views.get(thread_id)
            
            if result_view:
                # 両方のユーザーから「試合中」ロールを削除
                await remove_role(user1, "試合中")
                user2_id = result_view.player1_id if result_view.player2_id == user1.id else result_view.player2_id
                user2 = ctx.guild.get_member(user2_id)
                if user2 is None:
                    user2 = await ctx.guild.fetch_member(user2_id)
                await remove_role(user2, "試合中")
                
                # ResultViewのタイマータスクをキャンセル
                result_view.cancel_timeout()
                
                await ctx.respond("報告を受け付けました。スタッフが対応します。", ephemeral=True)
                
                # スタッフに通知
                staff_role = discord.utils.get(ctx.guild.roles, name="staff")
                await ctx.channel.send(
                    f"報告が提出されました。状況を説明し、必要であれば画像をアップロードしてください。"
                    f"{staff_role.mention if staff_role else ''}に通知しました。"
                )
            else:
                await ctx.respond("このスレッドでは試合が行われていません。", ephemeral=True)
        else:
            await ctx.respond("このコマンドは対戦スレッド内でのみ使用できます。", ephemeral=True)
    
    @bot.slash_command(
        name="settings",
        description="マッチング設定を変更します（相手のレートを表示/非表示）"
    )
    async def settings(ctx: discord.ApplicationContext, display_opponent_rating: bool = True):
        """ユーザー設定コマンド"""
        if ctx.channel_id != COMMAND_CHANNEL_ID:
            await ctx.respond(f"このコマンドは <#{COMMAND_CHANNEL_ID}> で実行してください。", ephemeral=True)
            return
        
        from models.user import UserModel
        user_model = UserModel()
        
        user = user_model.get_user_by_discord_id(str(ctx.user.id))
        if not user:
            await ctx.respond("ユーザーが見つかりません。まず登録を行ってください。", ephemeral=True)
            return
        
        # 設定を更新（UserModelに追加が必要）
        status = "表示する" if display_opponent_rating else "表示しない"
        await ctx.respond(f"マッチング時に相手のレートを**{status}**ように設定しました。", ephemeral=True)
    
    @bot.slash_command(
        name="trust_report", 
        description="ユーザーの信用ポイントを減点します",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    @commands.has_permissions(administrator=True)
    async def trust_report(ctx: discord.ApplicationContext, user: discord.Member, points: int):
        """信用ポイント減点コマンド"""
        from models.user import UserModel
        user_model = UserModel()
        
        user_instance = user_model.get_user_by_discord_id(str(user.id))
        if not user_instance:
            await ctx.respond(f"ユーザー {user.display_name} がデータベースに見つかりませんでした。", ephemeral=True)
            return
        
        # 信用ポイントを減点
        new_points = user_model.update_trust_points(str(user.id), -points)
        if new_points is not None:
            await ctx.respond(f"{user.display_name} さんに {points} ポイントの減点が適用されました。現在の信用ポイント: {new_points}")
            
            if new_points < 60:
                await ctx.followup.send(f"{user.display_name} さんの信用ポイントが60未満です。必要な対応を行ってください。")
        else:
            await ctx.respond("エラーが発生しました。", ephemeral=True)
    
    @bot.slash_command(
        name="debug_queue",
        description="マッチング待機キューの状態を確認します",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    @commands.has_permissions(administrator=True)
    async def debug_queue(ctx: discord.ApplicationContext):
        """デバッグ用：待機キューの状態を確認"""
        queue_status = matchmaking_vm.get_waiting_users()
        
        # 詳細情報を取得
        callback_status = "✅ SET" if matchmaking_vm.match_creation_callback else "❌ NOT SET"
        background_task_status = "✅ RUNNING" if matchmaking_vm.background_task and not matchmaking_vm.background_task.done() else "❌ NOT RUNNING"
        processing_task_status = "✅ RUNNING" if matchmaking_vm.processing_task and not matchmaking_vm.processing_task.done() else "❌ NOT RUNNING"
        
        from config.settings import MAX_RATING_DIFF_FOR_MATCH
        debug_info = (
            f"**🔍 マッチングシステム状態:**\n"
            f"Match Callback: {callback_status}\n"
            f"Background Task: {background_task_status}\n"
            f"Processing Task: {processing_task_status}\n"
            f"Queue Size: {len(queue_status)}\n"
            f"Max Rating Diff: {MAX_RATING_DIFF_FOR_MATCH}\n\n"
        )
        
        if not queue_status:
            debug_info += "**📭 待機キューは空です。**"
        else:
            debug_info += "**👥 現在の待機キュー:**\n"
            for i, user_info in enumerate(queue_status, 1):
                battle_role = "🔴 試合中" if user_info.get('has_battle_role', False) else "🟢 待機中"
                debug_info += f"{i}. {user_info['display_name']} ({user_info.get('user_name', 'Unknown')}) - Rating: {user_info['rating']} - {battle_role}\n"
        
        # タスクの状態詳細
        if matchmaking_vm.background_task:
            if matchmaking_vm.background_task.done():
                try:
                    exception = matchmaking_vm.background_task.exception()
                    if exception:
                        debug_info += f"\n⚠️ Background Task Error: {exception}"
                except:
                    debug_info += f"\n⚠️ Background Task completed unexpectedly"
        
        await ctx.respond(debug_info, ephemeral=True)
    
    @bot.slash_command(
        name="force_match_check",
        description="強制的にマッチングチェックを実行します",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    @commands.has_permissions(administrator=True)
    async def force_match_check(ctx: discord.ApplicationContext):
        """デバッグ用：強制的にマッチングチェックを実行"""
        await ctx.response.defer(ephemeral=True)
        
        queue_size = len(matchmaking_vm.waiting_queue)
        await ctx.followup.send(f"🔍 Force checking matches for {queue_size} users in queue...", ephemeral=True)
        
        try:
            matches = await matchmaking_vm.find_and_create_matches()
            if matches:
                result_msg = f"✅ Found {len(matches)} matches:\n"
                for user1, user2 in matches:
                    result_msg += f"- {user1.display_name} vs {user2.display_name}\n"
                
                # コールバックを実行
                if matchmaking_vm.match_creation_callback:
                    for user1, user2 in matches:
                        asyncio.create_task(matchmaking_vm.match_creation_callback(user1, user2))
                    result_msg += "\n🎯 Match creation tasks started!"
                else:
                    result_msg += "\n❌ No callback set - matches found but not created!"
            else:
                result_msg = f"❌ No matches found for {queue_size} users in queue"
                
                # なぜマッチしなかったかの理由を表示
                if queue_size >= 2:
                    result_msg += "\n\n**Possible reasons:**\n"
                    queue_users = matchmaking_vm.get_waiting_users()
                    for i in range(len(queue_users)):
                        for j in range(i + 1, len(queue_users)):
                            user1 = queue_users[i]
                            user2 = queue_users[j]
            
            await ctx.followup.send(result_msg, ephemeral=True)
            
        except Exception as e:
            await ctx.followup.send(f"❌ Error during force match check: {e}", ephemeral=True)
            logging.error(f"Error in force_match_check: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    @bot.slash_command(
        name="debug_user_data",
        description="ユーザーデータの型と内容を確認します",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    @commands.has_permissions(administrator=True)
    async def debug_user_data(ctx: discord.ApplicationContext, user: discord.Member):
        """デバッグ用：ユーザーデータの型と内容を確認"""
        from models.user import UserModel
        user_model = UserModel()
        
        try:
            user_data = user_model.get_user_by_discord_id(str(user.id))
            
            if not user_data:
                await ctx.respond(f"❌ User {user.display_name} not found in database", ephemeral=True)
                return
            
            # データの型と内容をログ出力
            logging.info(f"🔍 User data for {user.display_name}:")
            logging.info(f"  Type: {type(user_data)}")
            logging.info(f"  Data: {user_data}")
            
            # user_dataが辞書かオブジェクトかを判定して適切にアクセス
            def get_attr(data, attr_name, default='N/A'):
                try:
                    if isinstance(data, dict):
                        return data.get(attr_name, default)
                    else:
                        return getattr(data, attr_name, default)
                except Exception as e:
                    return f"Error: {e}"
            
            debug_info = (
                f"**🔍 User Data Debug for {user.display_name}:**\n"
                f"Data Type: {type(user_data).__name__}\n"
                f"Is Dict: {isinstance(user_data, dict)}\n"
                f"Has __dict__: {hasattr(user_data, '__dict__')}\n\n"
                f"**Attributes:**\n"
                f"ID: {get_attr(user_data, 'id')}\n"
                f"User Name: {get_attr(user_data, 'user_name')}\n"
                f"Discord ID: {get_attr(user_data, 'discord_id')}\n"
                f"Class1: {get_attr(user_data, 'class1')}\n"
                f"Class2: {get_attr(user_data, 'class2')}\n"
                f"Rating: {get_attr(user_data, 'rating')}\n"
                f"Trust Points: {get_attr(user_data, 'trust_points')}\n"
            )
            
            if isinstance(user_data, dict):
                debug_info += f"\n**Dict Keys:** {list(user_data.keys())}"
            elif hasattr(user_data, '__dict__'):
                debug_info += f"\n**Object Attributes:** {list(user_data.__dict__.keys())}"
            
            await ctx.respond(debug_info, ephemeral=True)
            
        except Exception as e:
            await ctx.respond(f"❌ Error debugging user data: {e}", ephemeral=True)
            logging.error(f"Error in debug_user_data: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    @bot.command()
    @commands.has_permissions(administrator=True)
    async def start_season(ctx, season_name: str):
        """新しいシーズンを開始するコマンド"""
        from models.season import SeasonModel
        season_model = SeasonModel()
        
        try:
            new_season = season_model.create_season(season_name)
            if new_season:
                await ctx.send(f"'{season_name}' が開始されました！")
                
                # マッチングボタンの表示
                matching_channel = bot.get_channel(MATCHING_CHANNEL_ID)
                if matching_channel:
                    await safe_purge_channel(matching_channel)
                    await safe_send_message(matching_channel, "使用するクラスを選択してください。", view=ClassSelectView())
                    await setup_matchmaking_channel(matching_channel, matchmaking_vm)
            else:
                await ctx.send("シーズンの開始に失敗しました。")
        except ValueError as e:
            await ctx.send(f"エラー: {e}")
    
    @bot.command()
    @commands.has_permissions(administrator=True)
    async def end_season(ctx):
        """現在のシーズンを終了するコマンド"""
        from models.season import SeasonModel
        from models.user import UserModel
        season_model = SeasonModel()
        user_model = UserModel()
        
        try:
            # シーズンを終了
            ended_season = season_model.end_season()
            if ended_season:
                # シーズン統計を確定
                finalize_result = season_model.finalize_season(ended_season.id)
                
                # 全ユーザーをリセット
                reset_count = user_model.reset_users_for_new_season()
                
                await ctx.send(f"シーズン '{ended_season.season_name}' が終了しました。{reset_count}人のユーザーをリセットしました。")
                
                # マッチングボタンの削除
                matching_channel = bot.get_channel(MATCHING_CHANNEL_ID)
                if matching_channel:
                    await safe_purge_channel(matching_channel)
                    await safe_send_message(matching_channel, "シーズン開始前のため対戦できません")
            else:
                await ctx.send("終了するシーズンが見つかりません。")
        except ValueError as e:
            await ctx.send(f"エラー: {e}")
    
    return bot

def create_bot_2():
    """Bot2（ランキング・戦績担当）を作成"""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    bot.token = BOT_TOKEN_2
    
    # ViewModelの初期化
    ranking_vm = RankingViewModel()
    
    @bot.event
    async def on_ready():
        """Bot2の起動時処理"""
        logging.info(f'🤖 Bot2 logged in as {bot.user}')
        
        try:
            await bot.sync_commands()
            logging.info("✅ Bot2 commands synced successfully")
        except Exception as e:
            logging.error(f"❌ Failed to sync Bot2 commands: {e}")
        
        # チャンネルの初期化
        await setup_bot2_channels(bot, ranking_vm)
        
        # 定期更新タスクの開始
        update_stats_periodically.start()
        
        logging.info("🎉 Bot2 initialization completed successfully!")
    
    @tasks.loop(hours=1)
    async def update_stats_periodically():
        """統計情報の定期更新"""
        try:
            record_channel = bot.get_channel(RECORD_CHANNEL_ID)
            past_record_channel = bot.get_channel(PAST_RECORD_CHANNEL_ID)
            last50_record_channel = bot.get_channel(LAST_50_MATCHES_RECORD_CHANNEL_ID)
            
            if record_channel:
                await safe_purge_channel(record_channel)
                await safe_send_message(record_channel, "現在シーズンの戦績を確認できます。", view=CurrentSeasonRecordView())
            
            if past_record_channel:
                await safe_purge_channel(past_record_channel)
                await safe_send_message(past_record_channel, "過去シーズンの戦績を確認できます。", view=PastSeasonRecordView())
            
            if last50_record_channel:
                await safe_purge_channel(last50_record_channel)
                await safe_send_message(last50_record_channel, "直近50戦の戦績を確認できます。", view=Last50RecordView())
            
            # ランキングキャッシュをクリア
            ranking_vm.clear_cache()
            
        except Exception as e:
            logging.error(f"Error in update_stats_periodically: {e}")
    
    return bot

async def setup_bot1_channels(bot, matchmaking_vm: MatchmakingViewModel):
    """Bot1のチャンネル初期化"""
    try:
        # ウェルカムチャンネル
        welcome_channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if welcome_channel:
            await safe_purge_channel(welcome_channel)
            await safe_send_message(
                welcome_channel,
                "**SV Ratingsへようこそ！**\n以下のボタンを押してユーザー登録を行ってください。詳しくは☑┊quick-startを参照してください。",
                view=RegisterView()
            )
            logging.info("✅ Welcome channel setup completed")
        
        # プロフィールチャンネル
        profile_channel = bot.get_channel(PROFILE_CHANNEL_ID)
        if profile_channel:
            await safe_purge_channel(profile_channel)
            await safe_send_message(profile_channel, "プロフィールを確認するにはボタンを押してください。", view=ProfileView())
            await safe_send_message(profile_channel, "実績を確認するにはボタンを押してください。", view=AchievementButtonView())
            logging.info("✅ Profile channel setup completed")
        
        # マッチングチャンネル
        matching_channel = bot.get_channel(MATCHING_CHANNEL_ID)
        if matching_channel:
            await safe_purge_channel(matching_channel)
            await safe_send_message(matching_channel, "使用するクラスを選択してください。", view=ClassSelectView())
            await setup_matchmaking_channel(matching_channel, matchmaking_vm)
            logging.info("✅ Matching channel setup completed")
        
    except Exception as e:
        logging.error(f"❌ Error setting up Bot1 channels: {e}")

async def setup_bot2_channels(bot, ranking_vm: RankingViewModel):
    """Bot2のチャンネル初期化"""
    try:
        # ランキングチャンネル
        ranking_channel = bot.get_channel(RANKING_CHANNEL_ID)
        if ranking_channel:
            await safe_purge_channel(ranking_channel)
            await safe_send_message(
                ranking_channel,
                "ランキングを閲覧するにはボタンを押してください。レーティングランキングは1時間ごとに更新されます。",
                view=RankingView(ranking_vm)
            )
            logging.info("✅ Ranking channel setup completed")
        
        # 過去ランキングチャンネル
        past_ranking_channel = bot.get_channel(PAST_RANKING_CHANNEL_ID)
        if past_ranking_channel:
            await safe_purge_channel(past_ranking_channel)
            await safe_send_message(past_ranking_channel, "過去のランキングを表示します。", view=RankingButtonView(ranking_vm))
            logging.info("✅ Past ranking channel setup completed")
        
    except Exception as e:
        logging.error(f"❌ Error setting up Bot2 channels: {e}")

async def setup_matchmaking_channel(channel, matchmaking_vm: MatchmakingViewModel):
    """マッチングチャンネルの設定"""
    view = MatchmakingView(matchmaking_vm)
    content = (
        "マッチングを開始するにはボタンをクリックしてください。\n"
        "マッチングが成功したらbattleチャンネルにスレッドが作成されます。 "
        "そちらで対戦を行ってください。\n\n"
        "・マッチング可能時間は以下の通りです。\n"
        "平日: 20:00～25:00\n"
        "土日祝日: 13:00～25:00\n\n"
        f"・問題が発生した場合は<#{WELCOME_CHANNEL_ID}>を参照して下さい。"
        f"解決しない場合、<#{RECORD_CHANNEL_ID}>に問題の内容を書いてください。"
    )
    await safe_send_message(channel, content, view=view)

def create_bots():
    """2つのBotインスタンスを作成して返す"""
    # 設定の検証
    validate_config()
    logging.info("🔧 Configuration validated successfully")
    
    bot1 = create_bot_1()
    bot2 = create_bot_2()
    
    logging.info("🤖 Both bots created successfully")
    return bot1, bot2