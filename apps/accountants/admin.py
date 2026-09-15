from django.contrib import admin

from .models import Commission, Earn, Invest, Month, Year

# Register your models here.
admin.site.register(Month)
admin.site.register(Year)
admin.site.register(Invest)
admin.site.register(Earn)
admin.site.register(Commission)
