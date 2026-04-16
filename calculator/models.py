from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    monthly_budget_g = models.FloatField(default=10.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s profile"

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


class HardwareSpec(models.Model):
    """GPU/TPU hardware with real power specs"""
    name           = models.CharField(max_length=100, unique=True)
    manufacturer   = models.CharField(max_length=50)
    tdp_watts      = models.FloatField(help_text="Thermal Design Power in Watts")
    fp16_tflops    = models.FloatField(null=True, blank=True)
    int8_tflops    = models.FloatField(null=True, blank=True)
    memory_gb      = models.FloatField(null=True, blank=True)
    embodied_co2_kg= models.FloatField(default=0, help_text="Manufacturing CO2e (Faiz et al 2024)")
    released_year  = models.IntegerField(null=True, blank=True)
    hardware_type  = models.CharField(max_length=20, default='GPU',
                        choices=[('GPU','GPU'),('TPU','TPU'),('CPU','CPU')])

    def __str__(self):
        return f"{self.name} ({self.tdp_watts}W)"

    class Meta:
        ordering = ['manufacturer', 'name']


class OperationType(models.Model):
    name        = models.CharField(max_length=100, unique=True)
    slug        = models.CharField(max_length=50, unique=True)
    energy_mult = models.FloatField(default=1.0,
                    help_text="Multiplier vs baseline inference")
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class PrecisionType(models.Model):
    name        = models.CharField(max_length=20, unique=True)
    slug        = models.CharField(max_length=10, unique=True)
    energy_factor = models.FloatField(default=1.0,
                    help_text="Energy factor vs FP32 baseline")
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class AIModel(models.Model):
    model_name     = models.CharField(max_length=100, unique=True)
    provider       = models.CharField(max_length=100)
    wh_per_token   = models.FloatField(help_text="Wh per token (Samsi et al 2023)")
    context_window = models.IntegerField(default=128000)
    released_year  = models.IntegerField(null=True, blank=True)
    params_billions= models.FloatField(null=True, blank=True,
                        help_text="Parameter count in billions")
    training_co2_kg= models.FloatField(null=True, blank=True,
                        help_text="Training CO2e kg (Patterson et al 2021 / Sharma 2025)")
    model_type     = models.CharField(max_length=20, default='dense',
                        choices=[('dense','Dense'),('moe','MoE'),('other','Other')])

    def __str__(self):
        return f"{self.model_name} ({self.provider})"

    class Meta:
        ordering = ['provider', 'model_name']


class CarbonRegion(models.Model):
    region_name             = models.CharField(max_length=100, unique=True)
    region_code             = models.CharField(max_length=10, unique=True)
    carbon_intensity_kg_kwh = models.FloatField()
    source                  = models.CharField(max_length=200, blank=True)
    year_recorded           = models.IntegerField(null=True, blank=True)
    country_code            = models.CharField(max_length=5, blank=True)

    def __str__(self):
        return f"{self.region_name} ({self.carbon_intensity_kg_kwh} kg/kWh)"

    class Meta:
        ordering = ['carbon_intensity_kg_kwh']


class HardwareCalculation(models.Model):
    """Records of hardware-level calculations"""
    user        = models.ForeignKey(User, on_delete=models.CASCADE,
                    related_name='hw_calcs', null=True, blank=True)
    ai_model    = models.ForeignKey(AIModel, on_delete=models.PROTECT)
    hardware    = models.ForeignKey(HardwareSpec, on_delete=models.PROTECT)
    operation   = models.ForeignKey(OperationType, on_delete=models.PROTECT)
    precision   = models.ForeignKey(PrecisionType, on_delete=models.PROTECT)
    region      = models.ForeignKey(CarbonRegion, on_delete=models.PROTECT)
    num_gpus    = models.IntegerField(default=1)
    duration_hrs= models.FloatField(default=1.0)
    energy_kwh  = models.FloatField(default=0)
    co2_kg      = models.FloatField(default=0)
    cost_gbp    = models.FloatField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        w = (self.hardware.tdp_watts * self.num_gpus *
             self.operation.energy_mult * self.precision.energy_factor)
        self.energy_kwh = (w * self.duration_hrs) / 1000
        self.co2_kg     = self.energy_kwh * self.region.carbon_intensity_kg_kwh
        self.cost_gbp   = self.energy_kwh * 0.28
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ai_model} | {self.hardware} | {self.co2_kg:.4f} kg CO2"


class PromptSession(models.Model):
    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    ai_model = models.ForeignKey(AIModel, on_delete=models.PROTECT)
    region   = models.ForeignKey(CarbonRegion, on_delete=models.PROTECT)
    title       = models.CharField(max_length=200)
    prompt_text = models.TextField()
    notes       = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.title}"

    class Meta:
        ordering = ['-created_at']


class PromptEmissions(models.Model):
    session     = models.OneToOneField(PromptSession, on_delete=models.CASCADE,
                    related_name='emissions')
    token_count = models.IntegerField(default=0)
    energy_wh   = models.FloatField(default=0)
    co2_grams   = models.FloatField(default=0)
    co2_mg      = models.FloatField(default=0)

    def save(self, *args, **kwargs):
        session          = self.session
        model            = session.ai_model
        region           = session.region
        word_count       = len(session.prompt_text.split())
        self.token_count = int(word_count * 1.33)
        self.energy_wh   = self.token_count * model.wh_per_token
        self.co2_grams   = (self.energy_wh * region.carbon_intensity_kg_kwh) / 1000
        self.co2_mg      = self.co2_grams * 1000
        super().save(*args, **kwargs)


class ForumPost(models.Model):
    TAG_CHOICES = [
        ('results','Results'),('question','Question'),
        ('tip','Tip'),('discussion','Discussion'),
    ]
    user    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_posts')
    title   = models.CharField(max_length=200)
    body    = models.TextField()
    tag     = models.CharField(max_length=20, choices=TAG_CHOICES, default='discussion')
    likes   = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class ForumComment(models.Model):
    post    = models.ForeignKey(ForumPost, on_delete=models.CASCADE, related_name='comments')
    user    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_comments')
    text    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
