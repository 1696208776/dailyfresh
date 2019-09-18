from django.contrib import admin
from apps.goods.models import *




class BaseModelAdmin(admin.ModelAdmin):
    """重写父类中的save_model方法，该方法在后台管理页面对数据修改时时会调用此方法"""

    def save_model(self, request, obj, form, change):
        # 调用父类中的save_model方法让数据完成更新
        super(BaseModelAdmin, self).save_model(request, obj, form, change)
        # 向worker发出任务，重新生成更新数据后的页面
        from celery_tasks.tasks import generate_static_index_html
        generate_static_index_html.delay()

    def delete_model(self, request, obj):
        """对数据进行删除时会调用"""
        super(BaseModelAdmin, self).delete_model(request, obj)
        # 向worker发出任务，重新生成更新数据后的页面
        from celery_tasks.tasks import generate_static_index_html
        generate_static_index_html.delay()


class GoodsTypeAdmin(BaseModelAdmin):
    pass


class GoodsSKUAdmin(BaseModelAdmin):
    pass


class GoodsAdmin(BaseModelAdmin):
    pass


class IndexGoodsBannerAdmin(BaseModelAdmin):
    pass


class IndexPromotionBannerAdmin(BaseModelAdmin):
    pass


class IndexTypeGoodsBannerAdmin(BaseModelAdmin):
    pass


# 注册商品类型模型类
admin.site.register(GoodsType, GoodsTypeAdmin)

# 注册商品SKU模型类
admin.site.register(GoodsSKU, GoodsSKUAdmin)

# 注册商品SPU模型类
admin.site.register(Goods, GoodsAdmin)

# 注册首页幻灯片展示模型类
admin.site.register(IndexGoodsBanner, IndexGoodsBannerAdmin)

# 注册首页促销活动模型类
admin.site.register(IndexPromotionBanner, IndexPromotionBannerAdmin)

# 注册分类商品展示模型类
admin.site.register(IndexTypeGoodsBanner, IndexTypeGoodsBannerAdmin)

# admin.site.register([GoodsType,GoodsSKU,Goods,GoodsImage,IndexGoodsBanner,IndexTypeGoodsBanner,IndexPromotionBanner,IndexPromotionBannerAdmin])