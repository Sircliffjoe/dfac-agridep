from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiResponse
from .models import User, ConsentRecord, OTPToken
from .serializers import (
    UserSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    ConsentRecordSerializer
)

class RequestOTPView(APIView):
    permission_classes = [AllowAny]
    serializer_class = OTPRequestSerializer

    @extend_schema(
        request=OTPRequestSerializer,
        responses={200: OpenApiResponse(description="OTP dispatched via SMS")}
    )
    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone_number'].strip()
        otp = OTPToken.generate_otp(phone)
        
        return Response({
            "message": "OTP sent successfully",
            "phone_number": phone,
            "dev_otp": otp.code
        }, status=status.HTTP_200_OK)

class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    serializer_class = OTPVerifySerializer

    @extend_schema(
        request=OTPVerifySerializer,
        responses={200: OpenApiResponse(description="Tokens returned")}
    )
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone_number'].strip()
        code = serializer.validated_data['code'].strip()

        token = OTPToken.objects.filter(phone_number=phone, is_used=False).order_by('-created_at').first()
        if not token or not token.is_valid(code):
            return Response({"error": "Invalid or expired OTP code"}, status=status.HTTP_400_BAD_REQUEST)

        user, created = User.objects.get_or_create(
            phone_number=phone,
            defaults={
                'username': f"farmer_{phone[-6:]}",
                'role': 'FARMER',
                'is_phone_verified': True
            }
        )
        if not user.is_phone_verified:
            user.is_phone_verified = True
            user.save(update_fields=['is_phone_verified'])

        refresh = RefreshToken.for_user(user)
        return Response({
            "message": "Verification successful",
            "user": UserSerializer(user).data,
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
        }, status=status.HTTP_200_OK)

class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user).data)

class ConsentRecordViewSet(viewsets.ModelViewSet):
    queryset = ConsentRecord.objects.all()
    serializer_class = ConsentRecordSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(captured_by=self.request.user)
