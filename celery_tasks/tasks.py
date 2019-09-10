from celery import Celery
from django.core.mail import send_mail
from django.conf import settings
from django.template import loader

import time
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE','item01.settings')
django.setup()

# 创建一个celery对象，并且明明name
app = Celery("celery_tasks.tasks", broker="redis://127.0.0.1:6379/4")

# 装饰函数使用app
@app.task
def send_active_email(email,username,token):
    """发送用户激活邮件"""
    subject = "天天生鲜欢迎您"
    message = ''  # 邮件正文
    sender = settings.EMAIL_FROM  # 发件人
    receiver = [email]  # 收件人
    html_message = """ 
        <h1>%s 恭喜您成为天天生鲜注册会员</h1>
        <br/>
        <h3>请您在1小时内点击以下活</h3>
        <a href="http://127.0.0.1:8000/user/active/%s">
        http://127.0.0.1:8000/user/active/%s</a>
        """ % (username, token, token)
    send_mail(subject, message, sender, receiver, html_message=html_message)


# 类的导入卸载celery配置完成的下方
from apps.goods.models import *

@app.task
def generate_static_index_html():
    '''产生首页静态化页面'''

    # 获取商品的种类信息
    types = GoodsType.objects.all()

    # 获取轮播图信息
    banners = IndexGoodsBanner.objects.all().order_by('index')

    # 获取促销信息
    promotion_banner = IndexPromotionBanner.objects.all().order_by('index')

    # 获取首页分类商品展示信息
    for type in types:
        image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')
        title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')

        type.image_banners = image_banners
        type.title_banners = title_banners

        context = {
            'types': types,
            'goods_banners': banners,
            'promotion_banners': promotion_banner,
        }

        # 产生静态页面
        temp = loader.get_template('static_index.html')
        static_index_html = temp.render(context)

        save_path = os.path.join(settings.BASE_DIR, 'static/index.html')

        with open(save_path, 'w') as f:
            f.write(static_index_html)
