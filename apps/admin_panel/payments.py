from django.conf import settings
# Mercado Pago SDK
import mercadopago
# Add Your credentials


# Create a preference item
def get_preference(unit_price, access_token):
    sdk = mercadopago.SDK(access_token)
    preference_data = {
        "items": [
            {
                "title": "Deposit Amount",
                "quantity": 1,
                "unit_price": unit_price,
            }
        ],
        "back_urls": {
            "success": f"{settings.BASE_URL}admin/notification",
            "failure": f"{settings.BASE_URL}admin/notification",
            "pending": f"{settings.BASE_URL}admin/notification"
        },
        "auto_return": "approved"
    }

    preference_response = sdk.preference().create(preference_data)
    preference = preference_response["response"]
    print(preference)
    return preference


def get_payment_qr_code(amount, access_token, user):
    sdk = mercadopago.SDK(access_token)
    payment_data = {
        "transaction_amount": amount,
        "description": "Payment Deposit To Seller",
        "payment_method_id": "pix",
        "payer": {
            "email": f"{user.username}@pixbet.com",
            "first_name": f"{user.username}",
            "last_name": f"{user.username}",
            "identification": {
                "type": "USER",
                "number": f"{user.id}"
            },
        },
        "notification_url":f"{settings.BASE_URL}admin/notification",
    }

    payment_response = sdk.payment().create(payment_data)
    payment = payment_response["response"]
    print(payment)
    qr_code = None
    if ('point_of_interaction' in payment) and 'transaction_data' in payment['point_of_interaction']:
        qr_code = payment['point_of_interaction']['transaction_data'].get('qr_code_base64')
    else:
        return False
    return qr_code
