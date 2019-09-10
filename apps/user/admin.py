from django.contrib import admin
from apps.user.models import *

admin.site.register([User,Address])

