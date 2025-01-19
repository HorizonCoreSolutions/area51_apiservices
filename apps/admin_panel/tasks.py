import datetime
import traceback

from celery import Celery, shared_task
from compat import render_to_string
from django.conf import settings
from django.utils import timezone
from apps.payments.models import NowPaymentsTransactions, WithdrawalRequests
from apps.users.models import (CrmDetails, CsrQueries, EmailTemplateDetails, OffMarketGames,
    OffmarketWithdrawalRequests, SMSDetails, Users)
from .utils import textify

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from twilio.rest import Client
# client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

# celery configurations
app = Celery("api_services")
app.config_from_object("django.conf:settings", namespace="CELERY")

@app.task(bind=True, queue="email_queue")
def email_template_crm(self, template_id):
    try:
        crm_obj = CrmDetails.objects.filter(id=template_id).first()
        users_emails = []
        current_time = timezone.now()
        if crm_obj.category == "Active User Notification":
            users_emails = list(Users.objects.filter(role="player", modified__gte=current_time - datetime.timedelta(days=90)).values_list('email'))
        elif crm_obj.category == "Inactive User Notification":
            users_emails = list(Users.objects.filter(role="player", modified__lte=current_time - datetime.timedelta(days=90)).values_list('email'))
        else:
            users_emails = list(Users.objects.filter(role="player").values_list('email'))
        for user_email in users_emails:
            message = Mail(
                from_email=settings.SENDGRID_EMAIL,
                to_emails=user_email[0],
                subject=crm_obj.subject,
                html_content=crm_obj.get_crm_content())

            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            sg.send(message)

    except Exception as e:
        print("Error in Processing")
        print(e)


@app.task(bind=True, queue="sms_queue")
def send_sms_crm(self, template_id):
    try:
        sms_obj = SMSDetails.objects.filter(id=template_id).first()
        phone_numbers = sms_obj.phone_number
        message_body = sms_obj.content
        phone_number_list = list()
    
        for number in phone_numbers.split(','):
            phone_number_list.append(number)
            print("Phone_numbers list--->>>>>>>>>>>>>>>>>>>>>>.", phone_number_list)
            # message = client.messages.create(
            #                     body = textify(message_body),
            #                     from_= settings.TWILIO_PHONE_NUMBER,
            #                     to=number
            #                     )
            # print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>", message.sid)

    except Exception as e:
        print("Error in Processing")
        print(e)


@app.task(bind=True, queue="transaction_email_queue")
def transaction_mail(self,id):
    try:
        withdrawal = WithdrawalRequests.objects.filter(id = id).first()
        
        if withdrawal.user.email:
            user = withdrawal.user
            subject = "Transaction Alert!"
            current_date = timezone.now().strftime("%d/%m/%Y")
            date_created = withdrawal.created.strftime("%d/%m/%Y")
            withdrawal_status = withdrawal.status

            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            mail = Mail( 
                from_email=settings.SENDGRID_EMAIL,
                to_emails=user.email
            )
            data = {
                "amount":str(abs(float(withdrawal.amount))),
                "receiver_role":str(user.role),
                "receiver_username": str(user.username),
                "type":str(withdrawal.status),
                "date": str(current_date),
                "msg":"",
                "status":str(withdrawal.status),
                "created":str(date_created),
                "fe_url": settings.FE_DOMAIN,
            }
            
            if withdrawal_status == "approved":
                category = "withdrawal_approved_mail"
                status = "Withdrawal Approved"
            elif withdrawal_status == "cancelled":
                category = "withdrawal_cancelled_mail"
                status = "Cancelled"
            elif withdrawal_status == "REJECTED":
                category = "withdrawal_rejected_mail"
                status = "Rejected"
            elif withdrawal_status == "pending":
                category = "withdrawal_pending_mail"
                status = "Pending"
            else:
                category = "withdrawal_failed_mail"
                status = "Failed"

            mail_template = EmailTemplateDetails.objects.filter(category=category).first()
            if mail_template and mail_template.template_id:
                data.update({"status": status})
                mail.template_id = mail_template.template_id
                mail.dynamic_template_data = data
                sg.send(mail)
            else:
                content = render_to_string("admin/email/transaction_mail.html", data)
                
                emails = [user.email]
                mail = Mail(
                    from_email=settings.SENDGRID_EMAIL,
                    to_emails=emails,
                    subject=subject,
                    html_content=content
                )
                sg.send(mail)
            
    except Exception as e:
        print(e)
        print("Error in Processing Transaction Mail - ", e)

    
@app.task(bind=True, queue="ipn_transaction_email_queue")
def ipn_status_transaction_mail(self,id):

    try:
        withdrawal = NowPaymentsTransactions.objects.filter(payment_id=id).first()
        if withdrawal.transaction_type == 'WITHDRAWAL':
            withdrawal_req = WithdrawalRequests.objects.filter(transaction__id=withdrawal.id).first()
            amount = withdrawal_req.amount
        else:
            amount = withdrawal.price_amount    
        if(withdrawal.user.email):
            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            category = None
            user = withdrawal.user
            subject = "Transaction Alert!"
            current_date = timezone.now().strftime("%d/%m/%Y")
            date_created = withdrawal.created.strftime("%d/%m/%Y")
            payment_status = withdrawal.payment_status
            data = {
                "amount": str(abs(float(amount))),
                "receiver_role": str(user.role),
                "receiver_username":  str(user.username),
                "type": str(withdrawal.transaction_type),
                "date":  str(current_date),
                "msg": "",
                "status": str((withdrawal.payment_status).lower()),
                "created": str(date_created),
                "fe_url": settings.FE_DOMAIN,
            }

            if payment_status == "finished":
                category = "nowpayment_finished_mail"
                status = "Done"
            elif payment_status == "failed":
                category = "nowpayment_failed_mail"
                status = "Failed"
            elif payment_status == "expired":
                category = "nowpayment_expired_mail"
                status = "Expired"
            # elif payment_status == "confirmed":
            #     category = "nowpayment_confirmed_mail"
            #     status = "Confirmed"
            elif payment_status == "partially_paid":
                category = "nowpayment_partially_paid_mail"
                status = "Partially Paid"
            else:
                category = "nowpayment_in_progress_mail"
                status = "In Progress"

            mail_template = EmailTemplateDetails.objects.filter(category=category).first() if category else None
            if mail_template and mail_template.template_id:
                mail = Mail( 
                    from_email= settings.SENDGRID_EMAIL,
                    to_emails= [user.email]
                )
                transaction_type = "Withdrawal of" if payment_status == "WITHDRAWAL" else "Payment transfer of",
                data.update({"type":transaction_type, "status":status})
                mail.dynamic_template_data = data
                mail.template_id = mail_template.template_id
                sg.send(mail)
            else:
                content = render_to_string("admin/email/now_payments_ipn_mail.html", data)                                
                emails = [user.email]
                message = Mail(
                    from_email=settings.SENDGRID_EMAIL,
                    to_emails=emails,
                    subject=subject,
                    html_content=content
                )
                sg.send(message)


    except Exception as e:
        print(e)
        print("Error in Processing")
        
        
@app.task(bind=True, queue="newuser_email_queue")
def newuser_email(self,username,email):

    try:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        mail_template = EmailTemplateDetails.objects.filter(category='welcome_mail').first()
        if mail_template:
            mail = Mail( 
                from_email=settings.SENDGRID_EMAIL,
                to_emails= [email]
            )
            mail.template_id = mail_template.template_id
            mail.dynamic_template_data = {
                "username": username,
                "fe_url": settings.FE_DOMAIN,
            }
            sg.send(mail)
            return
        
        subject = "Welcome to Area51!"
        data = {"username":username}
        content = render_to_string("admin/email/signup_mail.html", data)
          
        emails = [email]
        message = Mail(
            from_email=settings.SENDGRID_EMAIL,
            to_emails=emails,
            subject=subject,
            html_content=content)

        sg.send(message)


    except Exception as e:
        print(e)
        print("Error in Processing")
    
    
@app.task(bind=True, queue="queries_email_queue")
def queries_email(self,id):
    try:    
        query = CsrQueries.objects.filter(id=id).first()
        user_email = query.user.email
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        mail_template = EmailTemplateDetails.objects.filter(category='customer_query_mail').first()
        
        if user_email and mail_template:
            mail = Mail( 
                from_email=settings.SENDGRID_EMAIL,
                to_emails= [user_email]
            )
            mail.template_id = mail_template.template_id
            mail.dynamic_template_data = {
                "subject":query.subject,
                "text":query.text,
                "fe_url": settings.FE_DOMAIN,
            }
            sg.send(mail)
            return
        
        data = {
            "query": {
                "subject":query.subject,
                "text":query.text,
            }
        }
        content = render_to_string("admin/email/query_mail.html", data)
        if user_email: 
            message = Mail(
                    from_email=settings.SENDGRID_EMAIL,
                    to_emails=user_email,
                    subject=query.subject,
                    html_content=content)
            sg.send(message) 


    except Exception as e:
        print("Error in Processing")
        print(e)
        
        
@app.task(bind=True, queue="offmarket_email_queue")
def rejection_mail(self,id):

    try:
        withdrawal = OffmarketWithdrawalRequests.objects.filter(id=id).first()
        game_name = OffMarketGames.objects.filter(code=withdrawal.code).first() 
        if(withdrawal.user.email):
            user = withdrawal.user
            subject = "Transaction Alert!"
            current_date = timezone.now().strftime("%d/%m/%Y")
            date_created = withdrawal.created.strftime("%d/%m/%Y")
            data = {"amount":str(abs(float(withdrawal.amount))), "receiver_role":str(user.role), "receiver_username": str(user.username),
                    "name":str(game_name.title),
                        "date": str(current_date),"msg":"","created":str(date_created), "fe_url": settings.FE_DOMAIN,}
            
            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            mail_template = EmailTemplateDetails.objects.filter(category='offmarket_withdraw_rejection_mail').first()
            if mail_template:
                mail = Mail( 
                    from_email=settings.SENDGRID_EMAIL,
                    to_emails= [user.email]
                )
                mail.template_id = mail_template.template_id
                mail.dynamic_template_data = data
                sg.send(mail)
                return
            
            content = render_to_string("offmarkets/rejection_mail.html", data)                              
            emails = [user.email]
            message = Mail(
                from_email=settings.SENDGRID_EMAIL,
                to_emails=emails,
                subject=subject,
                html_content=content)
            sg.send(message)


    except Exception as e:
        print(e)
        print("Error in Processing")