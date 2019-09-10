from django.urls import path
from apps.cart.views import *

app_name = 'cart'

urlpatterns = [
    path('add/', CartAddView.as_view(), name='add'),
    path('update/', CartUpdateView.as_view(), name='update'),
    path('delete/', CartDeleteView.as_view(), name='delete'),
    path('', CartInfoView.as_view(), name='show'),
]
