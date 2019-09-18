from django.urls import path, re_path
from apps.order.views import *

app_name = 'order'

urlpatterns = [
    path('place/', OrderPlaceView.as_view(), name='place'),
    path('commit/', OrderCommitView.as_view(), name='commit'),
    path('pay/', OrderPayView.as_view(), name='pay'),
    path('check/', OrderCheckView.as_view(), name='check'),
    path('comment/<order_id>', OrderCommentView.as_view(), name='comment'),
]
