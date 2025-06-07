# viewmodels/__init__.py
"""ビューモデル関連のモジュール"""

# 循環インポートを避けるため、必要な時にのみインポートするように変更
# 直接的なインポートは行わない

__all__ = [
    'MatchmakingViewModel', 'ResultViewModel', 'CancelViewModel',
    'RankingViewModel', 'RecordViewModel', 'UserViewModel'
]

def get_matchmaking_view_model():
    """MatchmakingViewModelを遅延取得"""
    from .matchmaking_vm import MatchmakingViewModel
    return MatchmakingViewModel

def get_result_view_model():
    """ResultViewModelを遅延取得"""
    from .matchmaking_vm import ResultViewModel
    return ResultViewModel

def get_cancel_view_model():
    """CancelViewModelを遅延取得"""
    from .matchmaking_vm import CancelViewModel
    return CancelViewModel

def get_ranking_view_model():
    """RankingViewModelを遅延取得"""
    from .ranking_vm import RankingViewModel
    return RankingViewModel

def get_record_view_model():
    """RecordViewModelを遅延取得"""
    from .record_vm import RecordViewModel
    return RecordViewModel

def get_user_view_model():
    """UserViewModelを遅延取得"""
    from .user_vm import UserViewModel
    return UserViewModel