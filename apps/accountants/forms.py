# imports
from django.forms import ModelForm

from .models import Commission, Earn, Invest, Month, Year

# -----------------------------------#
# Month create form
# -----------------------------------#


class MonthForm(ModelForm):
    class Meta:
        model = Month
        fields = ['name', 'active']


# -----------------------------------#
# Year create form
# -----------------------------------#
class YearForm(ModelForm):
    class Meta:
        model = Year
        fields = ['name', 'active']


# -----------------------------------#
# Invest create form
# -----------------------------------#
class InvestForm(ModelForm):
    class Meta:
        model = Invest
        fields = ['invest_details', 'invest_amount', 'month', 'year']


# -----------------------------------#
# Earn create form
# -----------------------------------#
class EarnForm(ModelForm):
    class Meta:
        model = Earn
        fields = ['earn_details', 'earn_amount', 'month', 'year']


# -----------------------------------#
# Commission create form
# -----------------------------------#
class CommissionForm(ModelForm):
    class Meta:
        model = Commission
        fields = ['commission']
