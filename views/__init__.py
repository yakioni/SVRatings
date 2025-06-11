# views/__init__.py（正しい版）
"""ビュー関連のモジュール"""

from .user_view import RegisterView, ProfileView, AchievementButtonView
from .matchmaking_view import MatchmakingView, ClassSelectView, ResultView, RateDisplayView, CancelConfirmationView
from .ranking_view import RankingView, RankingButtonView, PastRankingSelectView
from .record_view import CurrentSeasonRecordView, PastSeasonRecordView, Last50RecordView, MatchHistoryPaginatorView

__all__ = [
    'RegisterView', 'ProfileView', 'AchievementButtonView',
    'MatchmakingView', 'ClassSelectView', 'ResultView', 'RateDisplayView', 'CancelConfirmationView',
    'RankingView', 'RankingButtonView', 'PastRankingSelectView',
    'CurrentSeasonRecordView', 'PastSeasonRecordView', 'Last50RecordView', 'MatchHistoryPaginatorView'
]