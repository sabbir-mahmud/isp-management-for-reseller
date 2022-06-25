from django.contrib import admin
from .models import Month, Year, Invest, Earn, Commission

# Register your models here.
admin.site.register(Month)
admin.site.register(Year)
admin.site.register(Invest)
admin.site.register(Earn)
admin.site.register(Commission)
