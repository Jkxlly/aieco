from django.contrib import admin
from .models import UserProfile, AIModel, CarbonRegion, PromptSession, PromptEmissions, ForumPost, ForumComment

@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ['model_name', 'provider', 'wh_per_token', 'context_window', 'released_year']
    list_filter  = ['provider']
    search_fields = ['model_name']

@admin.register(CarbonRegion)
class CarbonRegionAdmin(admin.ModelAdmin):
    list_display = ['region_name', 'region_code', 'carbon_intensity_kg_kwh', 'source', 'year_recorded']

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'location', 'monthly_budget_g', 'created_at']

@admin.register(PromptSession)
class PromptSessionAdmin(admin.ModelAdmin):
    list_display  = ['title', 'user', 'ai_model', 'region', 'created_at']
    list_filter   = ['ai_model', 'region']
    search_fields = ['title', 'user__username']
    raw_id_fields = ['user']

@admin.register(PromptEmissions)
class PromptEmissionsAdmin(admin.ModelAdmin):
    list_display = ['session', 'token_count', 'energy_wh', 'co2_grams', 'co2_mg']

@admin.register(ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display  = ['title', 'user', 'tag', 'likes', 'created_at']
    list_filter   = ['tag']
    search_fields = ['title', 'user__username']

@admin.register(ForumComment)
class ForumCommentAdmin(admin.ModelAdmin):
    list_display = ['post', 'user', 'created_at']
