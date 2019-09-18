from django.urls import path, re_path
from apps.goods.views import *

app_name = 'goods'

urlpatterns = [
    path('', IndexView.as_view(), name='index'),
    # re_path(r'^goods/(?P<goods_id>\d+)$', DetailView.as_view(), name='detail'),
    path('goods/<goods_id>', DetailView.as_view(), name='detail'),
    path('list/<type_id>/<page>', ListView.as_view(), name='list'),
]