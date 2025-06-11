from datetime import timedelta
import json
from rest_framework.response import Response
from rest_framework import status
from apps.acuitytec.models import AcuitytecUser, VerifycationItem, VerificationStateChoise
from apps.acuitytec.utils import generate_qr_code_url
from apps.users.models import VERIFICATION_APPROVED, VERIFICATION_EXPIRED, VERIFICATION_FAILED, Users
from django.conf import settings
from django.utils import timezone
from apps.acuitytec.acuitytec import AcuityTecAPI

from rest_framework.views import APIView
# Create your views here.

class GetVerificationLinkView(APIView):
    http_method_names = ["post"]
    def post(self, request):
        try:
            if not request.user.is_authenticated:
                return Response({"message": "The user must be authenticated"}, status.HTTP_400_BAD_REQUEST)

            user = Users.objects.get(id=request.user.id)

            document = request.data.get('document')
            language = request.data.get('language')

            if document is None or language is None:
                return Response({"message": "language or document must not be None"}, status.HTTP_400_BAD_REQUEST)

            if not language in ('es', 'en', 'fr'):
                return Response({"message": "language must be one of the following us, es, fr"}, status.HTTP_400_BAD_REQUEST)

            ac = AcuityTecAPI(user=user)

            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

            if x_forwarded_for:
                print(x_forwarded_for)
                ip = x_forwarded_for.split(',')[0].strip()  # client’s real IP
            else:
                ip = request.META.get('REMOTE_ADDR')

            if not hasattr(user, 'acuitytec_account'):
                res = ac.register_customer(ip)
                print(res)
                if res['status'] == 0:
                    AcuitytecUser.objects.create(
                        user=user,
                        login_ip=ip
                        )
                if res['status'] == -1:
                    return Response({"message": res['message']}, status.HTTP_400_BAD_REQUEST)

            link = ac.getLink(document=document, language=language)
            if link.startswith('error'):
                return Response({"message": link[5:]}, status.HTTP_400_BAD_REQUEST)

            return Response({'url' : link}, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class CallbackAcuitytecView(APIView):

    def post(self, request):
        AcuityTecAPI.save_request(request=request)
        
        reference_id = request.data.get('reference_id')
        
        if reference_id is None:
            print("Someone tried to catch something")
            return Response({"message": "status updated", "status": 1}, status.HTTP_200_OK)
        
        qs = VerifycationItem.objects.filter(
            reference_id=reference_id,
            status=VerificationStateChoise.pending,
            # created__gte=timezone.now() - timedelta(days=7)
        )
        if not qs.exists():
            print("Someone tried to catch something")
            return Response({"message": "status updated", "status": 1}, status.HTTP_200_OK)
        
        vi = qs.first()
        if vi is None:
            print("Someone tried to catch something")
            return Response({"message": "status updated", "status": 1}, status.HTTP_200_OK)
        
        data = json.loads(request.data.get('scrubber_response', '{}'))
        result = data.get('event', 'verification.pending')
        
        transformer = {
            "verification.declined" : VerificationStateChoise.declined,
            "verification.accepted" : VerificationStateChoise.accepted,
            "verification.pending"  : VerificationStateChoise.pending,
            "request.timeout" : VerificationStateChoise.expired
        }
        
        vi.status = transformer.get(result, VerificationStateChoise.pending)
        vi.save()
        
        user = vi.user
        newer_exists = VerifycationItem.objects.filter(user=vi.user, created__gte=vi.created).exclude(id=vi.id).exists()
        
        if newer_exists and result in ["verification.declined", 'request.timeout']:
            return Response({"message": "status updated", "status": 1}, status=status.HTTP_200_OK)
        
        if result == "verification.declined":
            user.document_verified = VERIFICATION_FAILED
        elif result == 'verification.accepted':
            user.document_verified = VERIFICATION_APPROVED
        elif result == 'request.timeout':
            user.document_verified = VERIFICATION_EXPIRED
        
        user.save()
        data = {"message": "status updated", "status": 1}
        AcuityTecAPI.save_request(request=data, is_response=True)
        return Response({"message": "status updated", "status": 1}, status=status.HTTP_200_OK)
    
    
class GetVerifycationStatus(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response(AcuityTecAPI.format_response('401: You have not been authenticated', 'Please login to use this function', 401, -1), status.HTTP_401_UNAUTHORIZED)
        
        
        user: Users = request.user
        
        qs = VerifycationItem.objects.filter(
            user=request.user,
            created__gte=timezone.now() - timedelta(days=7)
        ).order_by('-created')
        if not qs.exists():
            status_msg = "You are already verified" if user.document_verified else "Please go to your account settings to request this verification"
            return Response(AcuityTecAPI.format_response('404: This operation does not exist', status_msg, 404, -1), status.HTTP_404_NOT_FOUND)
        
        res = qs.first()
        if res is None:
            return Response(AcuityTecAPI.format_response("Something really unlucky happend", "Are you lost? want to call the UFO to save you?", 500, -1), status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        value = res.status
        if value == VerificationStateChoise.accepted:
            return Response(AcuityTecAPI.format_response("You are verified", "Please go back to play on our many games.", 1, -1), status.HTTP_200_OK)
        
        if value == VerificationStateChoise.pending:
            url = generate_qr_code_url(res.url) if res.url else ''
            return Response(
                {**AcuityTecAPI.format_response("Just a few steps more", "Please finish your recognition steps.", 0, int((res.created + timedelta(hours=24)).timestamp() * 1000)),
                 "url" : url}, status.HTTP_200_OK)
            
        if value == VerificationStateChoise.declined:
            return Response(
                AcuityTecAPI.format_response("This try has been rejected", "Please try again later or change your account information.", -1, -1), status.HTTP_200_OK)
            
        return Response(AcuityTecAPI.format_response("Something really unlucky happend", "Please try again  later", 400, -1), status.HTTP_400_BAD_REQUEST)
