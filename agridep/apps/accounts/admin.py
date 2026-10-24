from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, ConsentRecord, OTPToken

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'phone_number', 'role', 'is_phone_verified', 'state', 'lga', 'is_staff')
    list_filter = ('role', 'is_phone_verified', 'state', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'phone_number')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('AgriDEP Profile', {'fields': ('role', 'phone_number', 'is_phone_verified', 'state', 'lga')}),
    )

@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ('farmer_reference', 'stakeholder_category', 'consent_given', 'channel', 'created_at')
    list_filter = ('stakeholder_category', 'consent_given', 'channel')
    search_fields = ('farmer_reference', 'consent_scope')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(OTPToken)
class OTPTokenAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'code', 'created_at', 'expires_at', 'is_used', 'attempts')
    list_filter = ('is_used',)
    search_fields = ('phone_number',)
