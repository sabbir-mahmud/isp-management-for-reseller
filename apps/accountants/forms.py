# imports
from django.forms import ModelForm
from .models import Month, Year, Invest, Earn, Commission

# -----------------------------------#
# Month create form
# -----------------------------------#


class MonthForm(ModelForm):
    class Meta:
        model = Month
        fields = '__all__'


# -----------------------------------#
# Year create form
# -----------------------------------#
class YearForm(ModelForm):
    class Meta:
        model = Year
        fields = '__all__'


# -----------------------------------#
# Invest create form
# -----------------------------------#
class InvestForm(ModelForm):
    class Meta:
        model = Invest
        fields = '__all__'


# -----------------------------------#
# Earn create form
# -----------------------------------#
class EarnForm(ModelForm):
    class Meta:
        model = Earn
        fields = '__all__'


# -----------------------------------#
# Commission create form
# -----------------------------------#
class CommissionForm(ModelForm):
    class Meta:
        model = Commission
        fields = '__all__'
