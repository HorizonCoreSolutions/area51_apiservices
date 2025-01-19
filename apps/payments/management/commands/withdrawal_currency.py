import json
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from apps.users.models import Users
from requests.auth import HTTPBasicAuth
from django.http.response import HttpResponse
import time
import requests
from django.conf import settings
from apps.payments.models import WithdrawalCurrency


class Command(BaseCommand):
    
    def handle(self, *args, **kwargs):
        try:
            while True:
                api_key = settings.NOWPAYMENTS_API_KEY 
                url = settings.NOWPAYMENTS_API_URL+"full-currencies"
                coin_url = settings.NOWPAYMENTS_API_URL+"merchant/coins"

                headers = {
                    'x-api-key': api_key,
                }

                response = requests.get(url, headers=headers)
                available_currencies = requests.get(coin_url, headers=headers)
                response_content = available_currencies.content.decode('utf-8')
                response_data = json.loads(response_content)

                selected_currencies = response_data.get('selectedCurrencies', [])
                
                if((response.status_code == 200) and (available_currencies.status_code == 200)):
                    currencies = response.json().get('currencies', [])

                    for currency_data in currencies:
                        currency = WithdrawalCurrency.objects.filter(code=currency_data.get('code')).first()
                        if currency and currency.code not in selected_currencies:
                            currency.delete()
                        elif currency and currency.code in selected_currencies:
                            pass
                        elif currency_data.get('code') and currency_data.get('code') in selected_currencies:
                            code = currency_data.get('code')
                            name = currency_data.get('name')
                            enabled = currency_data.get('enable', False)
                            wallet_regex = currency_data.get('wallet_regex')
                            priority = currency_data.get('priority')
                            extra_id_exists = currency_data.get('extra_id_exists', False)
                            extra_id_regex = currency_data.get('extra_id_regex')
                            logo_url = currency_data.get('logo_url')
                            track = currency_data.get('track', False)
                            cg_id = currency_data.get('cg_id')
                            is_maxlimit = currency_data.get('is_maxlimit', False)
                            network = currency_data.get('network')
                            smart_contract = currency_data.get('smart_contract')
                            network_precision = currency_data.get('network_precision')

                            # Create or update the currency in the database
                            WithdrawalCurrency.objects.update_or_create(
                                code=code,
                                defaults={
                                    'name': name,
                                    'enabled': enabled,
                                    'wallet_regex': wallet_regex,
                                    'priority': priority,
                                    'extra_id_exists': extra_id_exists,
                                    'extra_id_regex': extra_id_regex,
                                    'logo_url': logo_url,
                                    'track': track,
                                    'cg_id': cg_id,
                                    'is_maxlimit': is_maxlimit,
                                    'network': network,
                                    'smart_contract': smart_contract,
                                    'network_precision': network_precision,
                                }
                            )
                    
                else:
                    print(f"Error fetching currencies: {response.status_code} - {response.text}")
                print(datetime.now())
                print('Sleep for 12 hours')
                time.sleep(43200)
        except Exception as e:
            print(e)        