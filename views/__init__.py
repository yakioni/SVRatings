# views/__init__.py
# 既存のインポートはそのまま残し、以下を追加してください

from .user_view import (
    RegisterView, ProfileView, NameChangeView, StayFunctionView, PremiumView,
    AchievementButtonView, NameChangeModal, PremiumModal, PremiumExtendConfirmView, 
    UserActionView, PremiumButton, password_manager, check_premium_expiry
)
from .matchmaking_view import (
    MatchmakingView, ClassSelectView, ResultView, RateDisplayView, 
    CancelConfirmationView, ResultConfirmationView
)
from .ranking_view import RankingView, RankingUpdateView, PastRankingButtonView
from .record_view import (
    CurrentSeasonRecordView, PastSeasonRecordView, Last50RecordView, MatchHistoryPaginatorView,
    DetailedSeasonSelectView, DetailedClassSelectView, DetailedRecordView,
    DetailedMatchHistoryView, DetailedMatchHistoryPaginatorView, DateRangeInputModal,
    # 新しく追加するクラス
    OpponentClassAnalysisView, OpponentAnalysisSeasonSelectView, OpponentAnalysisSeasonSelect,
    OpponentAnalysisDateRangeModal, OpponentAnalysisClassSelectView, OpponentAnalysisClassSelect,
    OpponentAnalysisPaginatorView
)

__all__ = [
    # User関連
    'RegisterView', 'ProfileView', 'NameChangeView', 'StayFunctionView', 'PremiumView',
    'AchievementButtonView', 'NameChangeModal', 'PremiumModal', 'PremiumExtendConfirmView', 
    'UserActionView', 'PremiumButton', 'password_manager', 'check_premium_expiry',
    
    # Matchmaking関連
    'MatchmakingView', 'ClassSelectView', 'ResultView', 'RateDisplayView', 
    'CancelConfirmationView', 'ResultConfirmationView',
    
    # Ranking関連
    'RankingView', 'RankingUpdateView', 'PastRankingButtonView',
    
    # Record関連
    'CurrentSeasonRecordView', 'PastSeasonRecordView', 'Last50RecordView', 'MatchHistoryPaginatorView',
    'DetailedSeasonSelectView', 'DetailedClassSelectView', 'DetailedRecordView',
    'DetailedMatchHistoryView', 'DetailedMatchHistoryPaginatorView', 'DateRangeInputModal',
    # 新しく追加するクラス
    'OpponentClassAnalysisView', 'OpponentAnalysisSeasonSelectView', 'OpponentAnalysisSeasonSelect',
    'OpponentAnalysisDateRangeModal', 'OpponentAnalysisClassSelectView', 'OpponentAnalysisClassSelect',
    'OpponentAnalysisPaginatorView'
]