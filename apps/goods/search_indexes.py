from haystack import indexes
from apps.goods.models import GoodsSKU  # 指定对于某个类的某些数据建立索引


class GoodsSKUIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)  # 索引字段

    # 获取模型类
    def get_model(self):
        # 返回模型类
        return GoodsSKU

    # 建立索引数据
    def index_queryset(self, using=None):
        # 返回该模型的所有数据
        return self.get_model().objects.all()