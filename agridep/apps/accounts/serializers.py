from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, ConsentRecord, OTPToken

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'phone_number', 'role', 'is_phone_verified', 'state', 'lga']
        read_only_fields = ['id', 'is_phone_verified']

class OTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=32)

class OTPVerifySerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=32)
    code = serializers.CharField(max_length=6)

class ConsentRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentRecord
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'reference_code']
