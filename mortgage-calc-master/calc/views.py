from django.shortcuts import render
from django.views import View
from django.http import HttpResponse, JsonResponse
from calc.forms import InvestmentForm
from calc.house import House
from calc.mortgage import Mortgage
from calc.investment import Investment
from decimal import Decimal
import copy
from django.conf import settings

class AboutView(View):
	"""Return About and Methodology page."""
	
	template_name = 'calc/about.html'
	
	def get(self, request, *args, **kwargs):
		return render(request, self.template_name)

	
class IndexView(View): 
	"""Return home page."""
	
	template_name = 'calc/index.html'
	form_class = InvestmentForm
	
	def get(self, request, *args, **kwargs):
		"""Return rendered page with form pre-filled if params provided.
		
		Args:
			request (HttpRequest): Django request object including GET params 
				which, if provided, are used to pre-fill the form.
			
		Returns:
			HttpResponse: Rendered page.
		
		"""
			
		float_parameters = ['closing_cost', 'maintenance_cost', 'property_tax', 'down_payment', 'interest_rate', 'yearly_appreciation', 'realtor_cost', 'federal_tax_bracket', 'state_tax_bracket', 'insurance']
		
		context_dict = {}
		
		# Collects GET parameters from URL to add to pre-fill form fields
		for parameter in float_parameters:
			if parameter in request.GET:
				try:
					context_dict[parameter] = float(request.GET[parameter])
				except:
					pass
				
		int_parameters = ['price', 'alternative_rent']
		
		for parameter in int_parameters:
			if parameter in request.GET:
				try:
					context_dict[parameter] = int(request.GET[parameter])
				except:
					pass
		
		return render(request, self.template_name, context_dict)
	

class InvestmentView(View): 
	"""Endpoint returning dict of cash flows and IRRs."""
	
	# Dicts for modified values of each scenario
	no_leverage = {
		'yearly_interest_rate': 0,
		'down_payment_percent': 1,
		'name': 'mortgage_driver_irr'
	}

	no_alternative_rent = {
		'alternative_rent': 0,
		'name': 'alternative_rent_driver_irr'
	}

	no_tax_shield = {
		'state_tax_rate': 0,
		'federal_tax_rate': 0,
		'name': 'tax_shield_driver_irr'
	}

	no_appreciation = {
		'yearly_appreciation_rate': 0,
		'name': 'appreciation_driver_irr'
	}

	no_expenses = {
		'yearly_property_tax_rate': 0,
		'yearly_maintenance_as_percent_of_value': 0, 
		'insurance': 0,
		'closing_cost_as_percent_of_value': 0,
		'name': 'expenses_driver_irr'
	}

	other_scenarios = [
		no_leverage,
		no_alternative_rent,
		no_tax_shield,
		no_appreciation,
		no_expenses
	]
	
	@staticmethod
	def _build_investment(scenario):
		
		house = House(
			scenario['price'], 
			scenario['yearly_appreciation_rate'], 
			scenario['yearly_property_tax_rate'], 
			scenario['yearly_maintenance_as_percent_of_value'], 
			scenario['insurance']
		)
		
		mortgage = Mortgage(
			house, 
			scenario['yearly_interest_rate'], 
			settings.TERM_IN_YEARS, 
			scenario['down_payment_percent']
		)	
		
		investment = Investment(
			house, 
			mortgage, 
			scenario['closing_cost_as_percent_of_value'], 
			scenario['alternative_rent'], 
			scenario['realtor_cost'], 
			scenario['federal_tax_rate'], 
			scenario['state_tax_rate']
		)
		
		return investment
	
	@staticmethod
	def _get_unified_scenario(comprehensive_scenario, modified_scenario):
		unified_scenario = copy.deepcopy(comprehensive_scenario)
		unified_scenario.update(modified_scenario)
			
		return unified_scenario

	@staticmethod
	def _get_irr_delta(base_irr, alternative_irr):
		irr_delta = []
		for year in range(1, len(base_irr)):
			# Handles case where one of the IRRs is null due to no positive cash flows
			try:
				delta =  base_irr[year] - alternative_irr[year]
				irr_delta.append(round(delta,2))
			except TypeError:
				irr_delta.append(None)
		
		return irr_delta
		
	
	def get(self, request, *args, **kwargs):
		"""Return JSON object of base case cash flows and alternate case IRRs.
		
		Args:
			request (HttpRequest): Django request object including GET params 
				which are used to calculate return.
			
		Returns:
			JsonResponse: Dict containing IRRs, cash stream, and base yearly 
				mortgage payment
		
		"""
		
		form = InvestmentForm(request.GET)
		if form.is_valid():				
			
			standard_investment = {
				'price': form.cleaned_data['price'],
				'yearly_appreciation_rate': form.cleaned_data['yearly_appreciation'],
				'yearly_property_tax_rate': form.cleaned_data['property_tax'],
				'yearly_maintenance_as_percent_of_value': form.cleaned_data['maintenance_cost'],
				'insurance': form.cleaned_data['insurance'],
				'yearly_interest_rate': form.cleaned_data['interest_rate'],
				'down_payment_percent': form.cleaned_data['down_payment'],
				'closing_cost_as_percent_of_value': form.cleaned_data['closing_cost'],
				'alternative_rent': form.cleaned_data['alternative_rent'] * 12,
				'realtor_cost': form.cleaned_data['realtor_cost'],
				'federal_tax_rate': form.cleaned_data['federal_tax_bracket'],
				'state_tax_rate': form.cleaned_data['state_tax_bracket'],		
			}

			# Base stream
			investment = self._build_investment(standard_investment)
			base_irr, cash_stream = investment.get_yearly_cash_flows_and_irr()
			mortgage_payment = int(round(investment.mortgage.monthly_payment))
			context_dict = {
				'base_irr': base_irr,
				'cash_stream': cash_stream,
				'mortgage_payment': mortgage_payment
			}

			high_appreciation = {
				'yearly_appreciation_rate': standard_investment['yearly_appreciation_rate'] + Decimal(.01),
			}
			
			low_appreciation = {
				'yearly_appreciation_rate': standard_investment['yearly_appreciation_rate'] - Decimal(.01),
			}
			
			scenario = self._get_unified_scenario(standard_investment, high_appreciation)
			investment = self._build_investment(scenario)
			high_irr, _ = investment.get_yearly_cash_flows_and_irr()
			context_dict['high_irr'] = high_irr
			
			scenario = self._get_unified_scenario(standard_investment, low_appreciation)
			investment = self._build_investment(scenario)
			low_irr, _ = investment.get_yearly_cash_flows_and_irr()
			context_dict['low_irr'] = low_irr
			
			for scenario in self.other_scenarios:
				unified_scenario = self._get_unified_scenario(standard_investment, scenario)
				investment = self._build_investment(unified_scenario)
				scenario_irr, _ = investment.get_yearly_cash_flows_and_irr()
				irr_delta = self._get_irr_delta(base_irr, scenario_irr)
				context_dict[scenario['name']] = irr_delta
			
			return JsonResponse(context_dict)
		else:
			print(form.errors)
		
		return JsonResponse(form.errors, status=400)