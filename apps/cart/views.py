from django.views import View
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from apps.goods.models import *
from django_redis import get_redis_connection
from db.base_model import BaseModel
from utils.Mixin import LoginRequiredMixin


class CartAddView(View):
    '''购物车添加'''
    def post(self, request):

        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'errno': 0, 'error_msg': '请先登录'})

        # 获取参数
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 检验参数是否完整
        if not all([sku_id, count]):
            return JsonResponse({'errno': 1, 'error_msg': '参数不完整'})

        # 检验商品数量count是否合法
        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'errno': 2, 'error_msg': '商品数量合法'})

        # 检验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'errno': 3, 'error_msg': '商品不存在'})

        # 购物车添加商品
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        cart_count = conn.hget(cart_key, sku_id)
        # 在redis中查询到该sku_id键存在，则添加该键的商品数量
        if cart_count:
            count += int(cart_count)

        # 判断该商品库存是否大于用户添加商品的数量
        if count > sku.stock:
            return JsonResponse({'errno': 4, 'error_msg': '商品库存不足'})

        # 添加商品数目，没有查到则设置新的sku_id以及商品数量，hset方法有数据则更新，无则新增
        conn.hset(cart_key, sku_id, count)

        # 计算用户购物车商品的总数目，最后返回添加成功响应
        total_count = conn.hlen(cart_key)
        return JsonResponse({'errno': 'ok', 'total_count': total_count, 'error_msg': '添加成功'})


class CartInfoView(LoginRequiredMixin, View):
    '''我的购物车'''
    def get(self, request):
        # 获取登录的用户
        user = request.user

        # 获取用户购物车商品信息
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        cart_dict = conn.hgetall(cart_key)

        skus = []  # 存放查出来的商品信息对象
        # 用于保存我的购物车中商品总件数以及总价格
        total_count = 0
        total_price = 0

        # 获取商品id和商品数量
        for sku_id, count in cart_dict.items():
            # 根据sku_id获取商品信息
            sku = GoodsSKU.objects.get(id=sku_id)
            # 计算小计
            amount = sku.price*int(count)
            # 动态给sku对象添加属性，保存遍历获取的小计以及商品数量
            sku.amount = amount
            sku.count = int(count)
            # 将查询出来的商品信息对象保存到列表中
            skus.append(sku)
            # 累加计算商品总件数和总价格
            total_count += int(count)
            total_price += amount


        context = {
            'skus': skus,
            'total_count': total_count,
            'total_price': total_price
        }

        return render(request, 'cart.html', context)


class CartUpdateView(View):
    """购物车列表更新商品的数量"""
    def post(self, request):
        # 接受数据
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 数据验证
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目格式错误'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist as e:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 更新购物车数量
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 验证商品的库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        # sku_id存在即更新，不存在则新建
        conn.hset(cart_key, sku_id, count)

        # 返回应答
        return JsonResponse({'res': 5, 'errmsg': '更新成功'})


class CartDeleteView(View):
    """购物车记录删除"""
    def post(self, request):
        # 接受数据
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        sku_id = request.POST.get('sku_id')

        # 数据验证
        if not sku_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的商品id'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist as e:
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 更新购物车数量
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # sku_id存在即更新，不存在则新建
        conn.hdel(cart_key, sku_id)

        # 返回应答
        return JsonResponse({'res': 3, 'message': '删除成功'})