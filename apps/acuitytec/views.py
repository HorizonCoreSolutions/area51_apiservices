import json
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from apps.acuitytec.logger import logger
from apps.core.rate_limiter import limiter
from rest_framework.response import Response
from apps.users.tasks import redeam_user_event
from apps.acuitytec.utils import generate_qr_code_url
from apps.acuitytec.acuitytec import sync_names, AcuityTecAPI
from apps.core.permissions import IsAdmin, IsAgent, IsDealer, IsManager, IsPlayer, IsSuperAdmin

from apps.acuitytec.models import (
                AcuitytecUser,
                DocumentTypeChoise,
                VerificationItem,
                VerificationStateChoise)

from apps.users.models import (
        VERIFICATION_APPROVED,
        VERIFICATION_EXPIRED,
        VERIFICATION_FAILED,
        Country,
        Users,
        EVENT_KYC)
# Create your views here.


class GetVerificationLinkView(APIView):
    http_method_names = ["post"]

    def post(self, request, **kwargs):
        try:
            if not request.user.is_authenticated:
                return Response({"message": "The user must be authenticated"}, status.HTTP_400_BAD_REQUEST)

            is_player = request.user.role.lower() == "player"
            #           request.user.role == "player"
            if is_player:
                id = request.user.id
            else:
                id = request.data.get("user_id")
                if not id:
                    return Response({"message": "A user_id must be provided"}, status.HTTP_400_BAD_REQUEST)

            user = Users.objects.get(id=id)

            language = request.data.get('language')

            if language is None:
                return Response({"message": "language must not be None"}, status.HTTP_400_BAD_REQUEST)

            if language not in ('es', 'en', 'fr'):
                return Response({"message": "language must be one of the following us, es, fr"}, status.HTTP_400_BAD_REQUEST)

            ac = AcuityTecAPI(user=user)

            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

            if x_forwarded_for:
                print(x_forwarded_for)
                ip = x_forwarded_for.split(',')[0].strip()  # client’s real IP
            else:
                ip = request.META.get('REMOTE_ADDR')

            if not is_player:
                ip = "0.0.0.0"

            ONE_DAY = 86400
            is_allowed = limiter.allow(
                    key=f"user:{request.user.id}:ac:link_endpoint",
                    limit=10,  # 3 request / (window)
                    window=ONE_DAY,  # 5 seconds
                    sliding=True
                    )

            if not is_allowed:
                logger.warning(f"user:{request.user.id}:{request.user.username} "
                            "has reached register_customer r/s limit.")
                return Response(data={"message" : "You have reach you limit. Please try again tomorrow."})

            is_user_register = AcuitytecUser.objects.filter(user=user).exists()
            # Consulta el registro local, para ver si el usuario existe
            if not is_user_register:
                res = ac.register_customer(ip, check_info=True)
                if res['status'] == 0:
                    # si si se registro,
                    # se crea el registro local
                    AcuitytecUser.objects.create(
                        user=user,
                        login_ip=ip
                        )
                elif res['status'] == -4:
                    return Response({"message": res.get("message", "This service is down. Please try again in a few minuts.")}, status.HTTP_400_BAD_REQUEST)
                else:
                    return Response({"message": "This service is down. Please try again in a few minuts."}, status.HTTP_400_BAD_REQUEST)
            user.refresh_from_db()
            if user.document_verified == VERIFICATION_APPROVED:
                return Response({'url': "", 'is_verified': True}, status=status.HTTP_200_OK)
            link = ac.getLink(language=language)
            if link.startswith('error'):
                return Response({"message": link[5:]}, status.HTTP_400_BAD_REQUEST)

            return Response({'url': link, 'is_verified': False}, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class CallbackAcuitytecView(APIView):

    def post(self, request):
        AcuityTecAPI.save_request(request=request)
        
        reference_id = str(request.data.get('reference_id', '')).strip()
        
        if reference_id is None:
            data = {"message": "The reference is not valid", "reallity": {"message": "status updated", "status": 1}, "status": -1}
            AcuityTecAPI.save_request(request=data, is_response=True)
            return Response({"message": "status updated", "status": 1}, status.HTTP_200_OK)
        
        qs = VerificationItem.objects.filter(
            reference_id=reference_id,
            status=VerificationStateChoise.pending,
            # created__gte=timezone.now() - timedelta(days=7)
        )
        if not qs.exists():
            data = {"message": "Verification Item does not exist", "reallity": {"message": "status updated", "status": 1}, "status": -1}
            AcuityTecAPI.save_request(request=data, is_response=True)
            return Response({"message": "status updated", "status": 1}, status.HTTP_200_OK)
        
        vi = qs.first()
        if vi is None:
            data = {"message": "VI existed but qs.first() is None", "reallity": {"message": "status updated", "status": 1}, "status": -1}
            AcuityTecAPI.save_request(request=data, is_response=True)
            return Response({"message": "status updated", "status": 1}, status.HTTP_200_OK)
        
        try:
            data = json.loads(request.data.get('scrubber_response', '{}'))
        except json.JSONDecodeError:
            return Response({"message": "Invalid scrubber response", "status": 0}, status=status.HTTP_400_BAD_REQUEST)

        result = data.get('event', 'verification.pending').strip().lower()

        status_map = {
            "verification.declined": VerificationStateChoise.declined,
            "verification.accepted": VerificationStateChoise.accepted,
            "verification.pending": VerificationStateChoise.pending,
            "request.timeout": VerificationStateChoise.expired
        }

        vi.status = status_map.get(result, VerificationStateChoise.pending)
        user = vi.user
        # update user information
        if result == "verification.accepted":
            document = data.get('verification_data', {}).get('document', {})
            document_number = data.get('additional_data', {}).get('document',{}).get('proof', {}).get("document_number", None)
            names = document.get('name', {})
            country = data.get('country', user.country_obj.code_cca2 if user.country_obj else (user.country if user.country else 'US'))
            first_name = (names.get('first_name') or user.first_name or '').strip().title()
            last_name = (names.get('last_name') or user.last_name or '').strip().title()
            full_name = (names.get('full_name') or '').strip().title()

            first_name = None if first_name == '' else first_name
            last_name = None if last_name == '' else last_name

            names, full_name = sync_names(first_name=first_name, last_name=last_name, full_name=full_name)
            
            doc_type = document.get('selected_type', ['id_card'])[0]
            
            user.country = country
            user.first_name = names[0]
            user.last_name = names[1]
            user.full_name = full_name
            
            if document_number:
                user.document_number = document_number
            
            if country:
                qs = Country.objects.filter(code_cca2=country).first()
                if qs:
                    user.country_obj = qs # type: ignore
                    
            map_types = {
                "passport" : DocumentTypeChoise.passport,
                "id_card" : DocumentTypeChoise.id_card,
                "driving_license" : DocumentTypeChoise.driving_license
            }
            vi.document_type = map_types.get(doc_type, 'id_card')

        vi.save()
        newer_exists = VerificationItem.objects.filter(user=vi.user, created__gte=vi.created).exclude(id=vi.id).exists()
        
        if newer_exists and result in ["verification.declined", 'request.timeout']:
            data = {"message": "has been declined or time out and a newer request has been made", "reallity": {"message": "status updated", "status": 1}, "status": -1}
            AcuityTecAPI.save_request(request=data, is_response=True)
            return Response({"message": "status updated", "status": 1}, status=status.HTTP_200_OK)
        
        if result == "verification.declined":
            user.document_verified = VERIFICATION_FAILED
        elif result == 'verification.accepted':
            user.document_verified = VERIFICATION_APPROVED
            redeam_user_event.apply_async(args=(EVENT_KYC, user.id),countdown=10)  # type: ignore
        elif result == 'request.timeout':
            user.document_verified = VERIFICATION_EXPIRED
        
        user.save()
        data = {"message": "status updated", "status": 1}
        AcuityTecAPI.save_request(request=data, is_response=True)
        return Response({"message": "status updated", "status": 1}, status=status.HTTP_200_OK)
    
    
class GetVerificationStatus(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response(AcuityTecAPI.format_response('401: You have not been authenticated', 'Please login to use this function', 401, -1), status.HTTP_401_UNAUTHORIZED)
        
        
        user: Users = request.user
        
        qs = VerificationItem.objects.filter(
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
