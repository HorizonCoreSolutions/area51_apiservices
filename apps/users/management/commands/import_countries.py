import requests
import json
from django.core.management.base import BaseCommand
from apps.users.models import Country

API_URL = "https://restcountries.com/v3.1/all"  # Replace with actual API URL if needed

LANGUAGE_MAP = {
    "zho" : "cn",  # Chinese
    "spa" : "es",  # Spanish
    "deu" : "de",  # German
    "fra" : "fr",  # French
    "hat" : "ht",  # Haitian Creole
    "kor" : "ko",  # Korean
    "nld" : "nl",  # Dutch
    "por" : "pt",  # Portuguese
    "rus" : "ru",  # Russian
    "tur" : "tr",  # Turkish
}

class Command(BaseCommand):
    help = "Fetch and populate country data from API"

    def handle(self, *args, **kwargs):
        response = requests.get(API_URL)
        if response.status_code != 200:
            self.stderr.write("Failed to fetch data from API")
            return

        countries_data = json.loads(response.content.decode("UTF-8"))

        for country_data in countries_data:
            try:
                name = country_data.get("name", {}).get("common", "Unknown")


                translations = country_data.get("translations", {})
                translated_names = {
                    LANGUAGE_MAP[lang]: trans.get("common", "")
                    for lang, trans in translations.items()
                    if lang in LANGUAGE_MAP.keys()
                }

                code_cca2 = country_data.get("cca2", "")
                code_ccn3 = country_data.get("ccn3", "")
                code_cca3 = country_data.get("cca3", "")
                flag = country_data.get("flag", "")
                flag_url = "static/countries_flags/" + code_cca2 + ".webp"
                timezone = country_data.get("timezones", [""])[0]  # First timezone
                currency_info = list(country_data.get("currencies", {}).values())[0] if country_data.get("currencies") else {}
                currency_code = list(country_data.get("currencies", {}).keys())[0] if country_data.get("currencies") else ""
                currency_name = currency_info.get("name", "")
                currency_symbol = currency_info.get("symbol", "")

                # Save country data to the database
                country, created = Country.objects.update_or_create(
                    code_cca2=code_cca2,
                    defaults={
                        "name": name,
                        "code_ccn3": code_ccn3,
                        "code_cca3": code_cca3,
                        "flag": flag,
                        "flag_url": flag_url,
                        "timezone": timezone,
                        "currency_code": currency_code,
                        "currency_name": currency_name,
                        "currency_symbol": currency_symbol,
                        "translated_name": translated_names,
                        "enabled": True,
                    },
                )

                if created:
                    self.stdout.write(f"Added: {name} ({code_cca2})")
                else:
                    self.stdout.write(f"Updated: {name} ({code_cca2})")

            except Exception as e:
                self.stderr.write(f"Error processing country: {e}")

