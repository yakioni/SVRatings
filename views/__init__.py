<<<<<<< HEAD
# views/__init__.py（更新版）
=======
# views/__init__.py（正しい版）
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
"""ビュー関連のモジュール"""

from .user_view import RegisterView, ProfileView, AchievementButtonView
from .matchmaking_view import MatchmakingView, ClassSelectView, ResultView, RateDisplayView, CancelConfirmationView
<<<<<<< HEAD
from .ranking_view import RankingView, RankingUpdateView, PastRankingButtonView
from .record_view import CurrentSeasonRecordView, PastSeasonRecordView, Last50RecordView, MatchHistoryPaginatorView

__all__ = [
    'RegisterView', 'ProfileView', 'AchievementButtonView',
    'MatchmakingView', 'ClassSelectView', 'ResultView', 'RateDisplayView', 'CancelConfirmationView',
    'RankingView', 'RankingUpdateView', 'PastRankingButtonView',
    'CurrentSeasonRecordView', 'PastSeasonRecordView', 'Last50RecordView', 'MatchHistoryPaginatorView'
=======
from .ranking_view import RankingView, PastRankingButtonView
from .record_view import CurrentSeasonRecordView, PastSeasonRecordView, Last50RecordView, MatchHistoryPaginatorView
__all__ = [
    'RegisterView', 'ProfileView', 'AchievementButtonView',
    'MatchmakingView', 'ClassSelectView', 'ResultView', 'RateDisplayView', 'CancelConfirmationView',
    'RankingView', 'PastRankingButtonView','PreviousRankingView'
    'CurrentSeasonRecordView', 'PastSeasonRecordView', 'Last50RecordView', 'PreviousSeasonRecordView', 'MatchHistoryPaginatorView'
>>>>>>> 5fe978043b8548aa18d399cf55751f786e839b02
]