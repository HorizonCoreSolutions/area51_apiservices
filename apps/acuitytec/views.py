from rest_framework.response import Response
from rest_framework import status
from apps.acuitytec.models import AcuitytecUser
from apps.users.models import Users
from django.conf import settings
from apps.acuitytec.acuitytec import AcuityTecAPI

from rest_framework.views import APIView
# Create your views here.

class GetVerificationLinkView(APIView):
    http_method_names = ["post"]
    def post(self, request):
        try:
            if not request.user.is_authenticated:
                return Response({"message": "The user must be authenticated"}, status.HTTP_400_BAD_REQUEST)
                
            user = Users.objects.get(id = request.user.id)
            
            document = request.data.get('document')
            language = request.data.get('language')
            print('ping')
            
            if document is None or language is None:
                print('bping')
                return Response({"message": "language or document must not be None"}, status.HTTP_400_BAD_REQUEST)
            
            if not language in ('es', 'en', 'fr'):
                return Response({"message": "language must be one of the following us, es, fr"}, status.HTTP_400_BAD_REQUEST)
                 
            
            ac = AcuityTecAPI(user=user)
            
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            
            print('cping')
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
                    
                    
            print('dping')
                
            link = ac.getLink(document=document, language=language)
            print(link)
            print('eping')
            if link.startswith('error'):
                return Response({"message": link[5:]}, status.HTTP_400_BAD_REQUEST)
                
            return Response({'url' : link}, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)