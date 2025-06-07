import discord
import asyncio
import logging
from typing import Optional
from config.settings import API_CALL_SEMAPHORE_LIMIT

# API制限用のセマフォ
api_call_semaphore = asyncio.Semaphore(API_CALL_SEMAPHORE_LIMIT)

logger = logging.getLogger(__name__)

async def safe_create_thread(channel: discord.TextChannel, user1: discord.Member, 
                           user2: discord.Member) -> Optional[discord.Thread]:
    """安全にスレッドを作成"""
    retries = 5
    for attempt in range(retries):
        try:
            async with api_call_semaphore:
                game_thread = await channel.create_thread(
                    name=f"{user1.display_name}_vs_{user2.display_name}",
                    type=discord.ChannelType.private_thread,
                    invitable=False
                )
            return game_thread
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                if retry_after is None:
                    retry_after = 5
                else:
                    retry_after += 1
                logger.warning(f"Rate limited while creating thread. Retrying after {retry_after} seconds.")
                await asyncio.sleep(retry_after)
            else:
                logger.error(f"Thread creation failed: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
    return None

async def safe_add_user_to_thread(thread: discord.Thread, user: discord.Member) -> bool:
    """安全にユーザーをスレッドに追加"""
    retries = 5
    for attempt in range(retries):
        try:
            async with api_call_semaphore:
                await thread.add_user(user)
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                if retry_after is None:
                    retry_after = 5
                else:
                    retry_after += 1
                logger.warning(f"Rate limited while adding user to thread. Retrying after {retry_after} seconds.")
                await asyncio.sleep(retry_after)
            else:
                logger.error(f"Failed to add user {user.display_name} to thread: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
    return False

async def safe_send_message(channel, content: str, **kwargs) -> Optional[discord.Message]:
    """安全にメッセージを送信"""
    retries = 5
    for attempt in range(retries):
        try:
            async with api_call_semaphore:
                message = await channel.send(content, **kwargs)
            return message
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                if retry_after is None:
                    retry_after = 5
                else:
                    retry_after += 1
                logger.warning(f"Rate limited. Retrying after {retry_after} seconds.")
                await asyncio.sleep(retry_after)
            else:
                logger.error(f"Failed to send message: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
    return None

async def assign_role(user: discord.Member, role_name: str) -> bool:
    """ユーザーに特定のロールを安全に付与"""
    retries = 5
    for attempt in range(retries):
        try:
            role = discord.utils.get(user.guild.roles, name=role_name)
            if role and role not in user.roles:
                async with api_call_semaphore:
                    await user.add_roles(role)
                    logger.info(f"ロール {role_name} を {user.display_name} に付与しました。")
            else:
                logger.info(f"ロール {role_name} が見つからないか、{user.display_name} は既にそのロールを持っています。")
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                if retry_after is None:
                    retry_after = 5
                else:
                    retry_after += 1
                logger.warning(f"Rate limited while assigning role. Retrying after {retry_after} seconds.")
                await asyncio.sleep(retry_after)
            else:
                logger.error(f"Failed to assign role {role_name} to {user.display_name}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
    return False

async def remove_role(user: discord.Member, role_name: str) -> bool:
    """ユーザーから特定のロールを安全に削除"""
    retries = 5
    for attempt in range(retries):
        try:
            role = discord.utils.get(user.guild.roles, name=role_name)
            if role and role in user.roles:
                async with api_call_semaphore:
                    await user.remove_roles(role)
                    logger.info(f"ロール {role_name} を {user.display_name} から削除しました。")
            else:
                logger.info(f"ロール {role_name} が見つからないか、{user.display_name} はそのロールを持っていません。")
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                if retry_after is None:
                    retry_after = 5
                else:
                    retry_after += 1
                logger.warning(f"Rate limited while removing role. Retrying after {retry_after} seconds.")
                await asyncio.sleep(retry_after)
            else:
                logger.error(f"Failed to remove role {role_name} from {user.display_name}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
    return False

async def safe_edit_message(message: discord.Message, content: str = None, 
                          embed: discord.Embed = None, view: discord.ui.View = None) -> bool:
    """安全にメッセージを編集"""
    retries = 3
    for attempt in range(retries):
        try:
            async with api_call_semaphore:
                await message.edit(content=content, embed=embed, view=view)
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None) or 5
                logger.warning(f"Rate limited while editing message. Retrying after {retry_after} seconds.")
                await asyncio.sleep(retry_after)
            else:
                logger.error(f"Failed to edit message: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return False
    return False

async def safe_delete_message(message: discord.Message, delay: float = 0) -> bool:
    """安全にメッセージを削除"""
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        
        async with api_call_semaphore:
            await message.delete()
        return True
    except (discord.errors.NotFound, discord.errors.Forbidden):
        # メッセージが見つからないか権限がない場合は正常とみなす
        return True
    except discord.HTTPException as e:
        logger.error(f"Failed to delete message: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error while deleting message: {e}")
        return False

async def safe_purge_channel(channel: discord.TextChannel, limit: int = 100) -> int:
    """安全にチャンネルをクリア"""
    try:
        async with api_call_semaphore:
            deleted = await channel.purge(limit=limit)
        logger.info(f"Purged {len(deleted)} messages from {channel.name}")
        return len(deleted)
    except discord.HTTPException as e:
        logger.error(f"Failed to purge channel {channel.name}: {e}")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error while purging channel {channel.name}: {e}")
        return 0

def count_characters(text: str) -> int:
    """全角・半角を区別せずに文字数をカウント"""
    import unicodedata
    count = 0
    for char in text:
        if unicodedata.east_asian_width(char) in ('F', 'W', 'A'):
            count += 1
        else:
            count += 1
    return count

def format_rating_change(rating_change: float) -> str:
    """レーティング変動をフォーマット"""
    sign = "+" if rating_change > 0 else ""
    return f"({sign}{rating_change:.0f})"

def format_win_rate(wins: int, total: int) -> str:
    """勝率をフォーマット"""
    if total == 0:
        return "0.00%"
    rate = (wins / total) * 100
    return f"{rate:.2f}%"

def get_class_abbreviation(class_name: str) -> str:
    """クラス名の略称を取得"""
    from config.settings import CLASS_ABBREVIATIONS
    return CLASS_ABBREVIATIONS.get(class_name, class_name[:2])

async def create_embed_pages(items: list, items_per_page: int = 10, 
                           title_template: str = "Page {page}/{total_pages}") -> list:
    """アイテムリストをページ分割してEmbedリストを作成"""
    if not items:
        return []
    
    pages = [items[i:i+items_per_page] for i in range(0, len(items), items_per_page)]
    embeds = []
    
    for page_num, page_items in enumerate(pages, 1):
        embed = discord.Embed(
            title=title_template.format(page=page_num, total_pages=len(pages)),
            color=discord.Color.blue()
        )
        embeds.append((embed, page_items))
    
    return embeds

class MessageCollector:
    """メッセージ収集とログ保存のヘルパークラス"""
    
    def __init__(self, log_file: str = 'messagelog.txt'):
        self.log_file = log_file
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def collect_thread_messages(self, thread: discord.Thread, 
                                    target_user_ids: list = None) -> list:
        """スレッドからメッセージを収集"""
        messages = []
        try:
            async for message in thread.history(limit=None, oldest_first=True):
                if target_user_ids is None or message.author.id in target_user_ids:
                    messages.append({
                        'timestamp': message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        'author_id': message.author.id,
                        'author_name': message.author.display_name,
                        'content': message.content,
                        'thread_id': thread.id,
                        'thread_name': thread.name
                    })
        except Exception as e:
            self.logger.error(f"Failed to collect messages from thread {thread.id}: {e}")
        
        return messages
    
    def save_messages_to_log(self, messages: list, additional_info: dict = None):
        """メッセージをログファイルに保存"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                for msg in messages:
                    log_line = (
                        f"Timestamp: {msg['timestamp']}, "
                        f"Author: {msg['author_name']} ({msg['author_id']}), "
                        f"Thread: {msg['thread_name']} ({msg['thread_id']}), "
                        f"Content: {msg['content']}"
                    )
                    
                    if additional_info:
                        info_str = ", ".join([f"{k}: {v}" for k, v in additional_info.items()])
                        log_line += f", {info_str}"
                    
                    f.write(log_line + "\n")
                    
            self.logger.info(f"Saved {len(messages)} messages to {self.log_file}")
        except Exception as e:
            self.logger.error(f"Failed to save messages to log: {e}")

# グローバルなメッセージコレクターインスタンス
message_collector = MessageCollector()