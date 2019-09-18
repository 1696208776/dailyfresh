from django.shortcuts import render, redirect, reverse
from utils.Mixin import LoginRequiredMixin
from django.views import View
from django_redis import get_redis_connection
from apps.goods.models import *
from apps.user.models import *
from apps.order.models import *
from django.db import transaction
from django.http import JsonResponse
from datetime import datetime
from alipay import AliPay
import os
from django.conf import settings


'''订单页面'''
class OrderPlaceView(LoginRequiredMixin, View):
    '''订单提交页面'''
    def post(self, request):
        user = request.user

        # 获取订单商品的id
        sku_ids = request.POST.getlist('sku_ids')
        #  验证sku_ids
        if not sku_ids:
            return redirect(reverse('cart:cart_info'))

        conn = get_redis_connection('default')
        cart_key = 'cart_%s' % user.id
        skus = []
        total_count = 0
        total_price = 0
        for sku_id in sku_ids:
            #  获取商品的信息和数量
            sku = GoodsSKU.objects.get(id=sku_id)
            count = conn.hget(cart_key, sku_id)
            amount = sku.price * int(count)

            # 动态添加数量和小计
            sku.count = int(count)
            sku.amount = int(amount)
            skus.append(sku)

            total_price += int(amount)
            total_count += int(count)

        # 写死运费
        transit_price = int(10)

        # 实付款
        total_pay = total_price + transit_price

        # 获取用户的收件地址
        addrs = Address.objects.filter(user=user)
        sku_ids = ''.join(sku_ids)

        # 组织上下文
        context = {
            'skus': skus,
            'total_count': total_count,
            'total_price': total_price,
            'transit_price': transit_price,
            'total_pay': total_pay,
            'addrs': addrs,
            'sku_ids': sku_ids,
        }

        return render(request , 'place_order.html', context=context)


'''订单提交：悲观锁'''
class OrderCommitView(View):
    '''订单提交：悲观锁'''

    @transaction.atomic
    def post(self, request):

        # 验证用户
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1 , 'errmsg': '参数不完整'})

        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法支付方式'})

        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist as e:
            return JsonResponse({'res': 3, 'errmsg': '地址不存在'})

        # 创建订单核心业务
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 总数目和总金额
        total_count = 0
        total_price = 0

        # 设置事务保存点
        save_id = transaction.savepoint()
        try:
            order = OrderInfo.objects.create(order_id=order_id,user=user,addr=addr,pay_method=pay_method,total_count=total_count,total_price=total_price,transit_price=transit_price)

            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            for sku_id in sku_ids:
                #  获取商品的信息
                try:
                    '''
                        悲观锁在查询的时候就加锁。
                        乐观锁不在查询的时候加锁，而是在判断更新库存的时候和之前查到的库存是不是相等，不相等的话说明期间别人把库存进行了修改。
                    '''
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except:
                    # 商品不存在
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                # 从redis中获取用户所要购买的商品的数量
                count = conn.hget(cart_key, sku_id)

                # 判断商品的库存
                if int(count) > sku.stock:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})

                # 向order_goods 表中添加一条记录
                OrderGoods.objects.create(order=order,sku=sku,count=count,price=sku.price)

                # 更新商品的库存和销量
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()

                # 累加计算订单商品的总数量和总价格
                amount = sku.price * int(count)
                total_count += int(count)
                total_price += amount
            
            # 更新订单信息表中的商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单失败'})
        
        # 提交事务，否则不会提交
        transaction.savepoint_commit(save_id)
        
        # 清除用户购物车中对应的记录
        conn.hdel(cart_key, *sku_ids)
        
        # 返回应答
        return JsonResponse({'res': 5, 'errmsg': '创建成功'})


'''订单提交：乐观锁'''
class OrderCommitView1(View):
    '''
    订单提交：乐观锁
    需要在mysql的配置文件中添加mysql的事务隔离级别为read-commited只读提交的内容
    防止读取不到另一个事务提交后的更新数据
    '''

    @transaction.atomic
    def post(self, request):

        # 验证用户
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '参数不完整'})

        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法支付方式'})

        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist as e:
            return JsonResponse({'res': 3, 'errmsg': '地址不存在'})

        # 创建订单核心业务
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 总数目和总金额
        total_count = 0
        total_price = 0

        # 设置事务保存点
        save_id = transaction.savepoint()
        try:
            order = OrderInfo.objects.create(order_id=order_id, user=user, addr=addr, pay_method=pay_method,
                                             total_count=total_count, total_price=total_price,
                                             transit_price=transit_price)

            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id


            for sku_id in sku_ids:
                #  获取商品的信息
                for i in range(3):
                    try:
                        '''
                            悲观锁在查询的时候就加锁。
                            乐观锁不在查询的时候加锁，而是在判断更新库存的时候和之前查到的库存是不是相等，不相等的话说明期间别人把库存进行了修改。
                        '''
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except:
                        # 商品不存在
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                    # 从redis中获取用户所要购买的商品的数量
                    count = conn.hget(cart_key, sku_id)

                    # 判断商品的库存
                    if int(count) > sku.stock:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})

                    print('user:%d stock:%d' % (user.id, sku.stock))
                    import time
                    time.sleep(10)

                    # 向order_goods 表中添加一条记录
                    OrderGoods.objects.create(order=order, sku=sku, count=count, price=sku.price)

                    # 更新商品的库存和销量
                    orgin_stock = sku.stock
                    new_stock = orgin_stock - int(count)
                    new_sales = sku.sales + int(count)

                    # 返回受影响的行数，表示1更新成功，返回0表示更新失败
                    res = GoodsSKU.objects.filter(id=sku_id, stock=orgin_stock).update(stock=new_stock, sales=new_sales)

                    if res == 0:
                        if i == 2:
                            # 尝试到第3次
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'res': 7, 'errmsg': '下单失败'})
                        else:
                            continue

                    # 向df_order_goods表中添加一条记录
                    OrderGoods.objects.create(order=order,sku=sku,count=count,price=sku.price)

                    # 累加计算订单商品的总数量和总价格
                    amount = sku.price * int(count)
                    total_count += int(count)
                    total_price += amount

                    break

            # 更新订单信息表中的商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单失败'})

        # 提交事务，否则不会提交
        transaction.savepoint_commit(save_id)

        # 清除用户购物车中对应的记录
        conn.hdel(cart_key, *sku_ids)

        # 返回应答
        return JsonResponse({'res': 5, 'errmsg': '创建成功'})


'''订单支付'''
class OrderPayView(View):
    '''订单支付'''

    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        order_id = request.POST.get('order_id')

        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user, pay_method=3, order_status=1)
        except OrderInfo.DoesNotExist as e:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # 调用支付宝接口
        alipay = AliPay(
            appid="2016101400683195",
            app_notify_url=None,
            app_private_key_string=open('apps/order/app_private_key.pem').read(),
            alipay_public_key_string=open('apps/order/alipay_public_key.pem').read(),
            sign_type="RSA2",
            debug=True
        )

        # 电脑网站支付 需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        total_pay = order.total_price + order.transit_price
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,
            total_amount=str(total_pay),
            subject='天天生鲜%s' % order_id,
            return_url="https://example.com",
            notify_url="https://example.com/notify"
        )
        
        # 返回应答，引导html页面跳转去接受支付的页面
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'res': 3, 'pay_url':pay_url})


'''检查订单'''
class OrderCheckView(View):

    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        order_id = request.POST.get('order_id')

        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user, pay_method=3, order_status=1)
        except OrderInfo.DoesNotExist as e:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # 调用支付宝接口
        alipay = AliPay(
            appid="2016101400683195",
            app_notify_url=None,
            app_private_key_string=open('apps/order/app_private_key.pem').read(),
            alipay_public_key_string=open('apps/order/alipay_public_key.pem').read(),
            sign_type="RSA2",
            debug=True
        )

        while True:
            response = alipay.api_alipay_trade_query(order_id)
            '''
            response = {
              "alipay_trade_query_response": {
                "trade_no": "2017032121001004070200176844",
                "code": "10000",
                "invoice_amount": "20.00",
                "open_id": "20880072506750308812798160715407",
                "fund_bill_list": [
                  {
                    "amount": "20.00",
                    "fund_channel": "ALIPAYACCOUNT"
                  }
                ],
                "buyer_logon_id": "csq***@sandbox.com",
                "send_pay_date": "2017-03-21 13:29:17",
                "receipt_amount": "20.00",
                "out_trade_no": "out_trade_no15",
                "buyer_pay_amount": "20.00",
                "buyer_user_id": "2088102169481075",
                "msg": "Success",
                "point_amount": "0.00",
                "trade_status": "TRADE_SUCCESS",
                "total_amount": "20.00"
              }
            '''
            code = response.get('code')
            if code == "10000" and response.get('trade_status') == "TRADE_SUCCESS":
                # 支付成功
                trade_no = response.get('trade_no')  # 获取支付宝交易号
                order.trade_no = trade_no  
                order.order_status = 4  #待评价
                order.save()
                return JsonResponse({'res': 3, 'errmsg': '支付成功'})

            elif code == '40004' or (code == '10000' and response.get('trade_status') == 'WAIT_BUYER_PAY'):
                # 等待买家付款
                # 业务处理失败，可能一会就会成功
                import time
                time.sleep(5)
                continue
                
            else:
                # 支付出错
                print(code)
                return JsonResponse({'res': 4, 'errmsg': '支付失败'})
                

'''订单评论'''
class OrderCommentView(View):

    def get(self, request, order_id):
        '''评论页面'''
        user = request.user

        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist as e:
            return redirect(reverse('user:order'))

        # 根据订单的状态获取订单的状态标题
        order.status_name = OrderInfo.ORDER_STATUS[order.order_status]

        # 获取订单商品信息
        order_skus = OrderGoods.objects.filter(order_id=order_id)
        for order_sku in order_skus:
            # 计算商品的小计
            amount = order_sku.count * order_sku.price
            # 动态给order_sku增加属性amount，保存商品小计
            order_sku.amount = amount
        # 动态给order增加order_skus，保存订单商品信息
        order.order_skus = order_skus

        return render(request, 'order_comment.html', {'order': order})

    def post(self, request, order_id):
        '''处理评论内容'''
        user = request.user

        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist as e:
            return redirect(reverse('user:order'))

        # 获取评论条数
        total_count = request.POST.get('total_count')
        total_count = int(total_count)

        # 循环获取订单中商品的评论内容
        for i in range(1, total_count+1):
            # 获取评论的商品id
            sku_id = request.POST.get("sku_%d" % i)
            # 获取评论的商品的内容
            content = request.POST.get('content_%d' % i, '')
            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue

            order_goods.comment = content
            order_goods.save()

        order.order_status = 5
        order.save()
        return redirect(reverse("user:order",  kwargs={"page": 1}))


