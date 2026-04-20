from django.core.management.base import BaseCommand
from calculator.models import (
    AIModel, CarbonRegion, HardwareSpec, OperationType, PrecisionType
)

class HardwareSpec(models.Model):
    name         = models.CharField(max_length=100, unique=True)
    manufacturer = models.CharField(max_length=100)
    tdp_watts    = models.IntegerField()

class OperationType(models.Model):
    name        = models.CharField(max_length=100, unique=True)
    energy_mult = models.FloatField()

class PrecisionType(models.Model):
    name          = models.CharField(max_length=100, unique=True)
    energy_factor = models.FloatField()

class Command(BaseCommand):
    help = "Seed all reference data from academic literature and mlco2 datasets"

    def handle(self, *args, **kwargs):
        self._seed_regions()
        self._seed_hardware()
        self._seed_operations()
        self._seed_precision()
        self._seed_models()
        self.stdout.write(self.style.SUCCESS("All reference data seeded!"))

    # ── Carbon Regions ──────────────────────────────────────────────────
    def _seed_regions(self):
        """
        Sources: National Grid ESO (UK), EPA eGRID (US), EEA, IEA,
                 mlco2 impact dataset (github.com/mlco2/impact)
        """
        regions = [
            # (name, code, kg_co2_per_kwh, source, year, country)
            ("Norway",             "NO", 0.017, "Nordic grid / IEA 2024", 2024, "NOR"),
            ("France",             "FR", 0.052, "RTE France 2024",        2024, "FRA"),
            ("Sweden",             "SE", 0.045, "Svenska Kraftnät 2024",  2024, "SWE"),
            ("Switzerland",        "CH", 0.128, "IEA 2024",               2024, "CHE"),
            ("Austria",            "AT", 0.158, "IEA 2024",               2024, "AUT"),
            ("United Kingdom",     "UK", 0.207, "National Grid ESO 2024", 2024, "GBR"),
            ("Germany",            "DE", 0.364, "Bundesnetzagentur 2024", 2024, "DEU"),
            ("Europe (avg)",       "EU", 0.276, "EEA 2024",               2024, "EU" ),
            ("Canada",             "CA", 0.130, "Environment Canada 2024",2024, "CAN"),
            ("United States",      "US", 0.386, "EPA eGRID 2024",         2024, "USA"),
            ("US — Virginia",      "US-VA",0.576,"EPA eGRID PJM 2024",    2024, "USA"),
            ("US — California",    "US-CA",0.251,"EPA eGRID CISO 2024",   2024, "USA"),
            ("US — Texas",         "US-TX",0.432,"EPA eGRID ERCO 2024",   2024, "USA"),
            ("Brazil",             "BR", 0.074, "ONS Brazil 2024",        2024, "BRA"),
            ("Australia",          "AU", 0.510, "AEMO 2024",              2024, "AUS"),
            ("Japan",              "JP", 0.474, "IEA 2024",               2024, "JPN"),
            ("South Korea",        "KR", 0.415, "IEA 2024",               2024, "KOR"),
            ("China",              "CN", 0.581, "IEA 2024",               2024, "CHN"),
            ("India",              "IN", 0.708, "CEA India 2024",         2024, "IND"),
            ("South Africa",       "ZA", 0.928, "IEA 2024",               2024, "ZAF"),
        ]
        created = 0
        for name, code, ci, source, year, country in regions:
            _, c = CarbonRegion.objects.get_or_create(
                region_code=code,
                defaults=dict(region_name=name, carbon_intensity_kg_kwh=ci,
                              source=source, year_recorded=year, country_code=country)
            )
            if c: created += 1
        self.stdout.write(f"  Regions: {created} created / {len(regions)} total")

    # ── Hardware ─────────────────────────────────────────────────────────
    def _seed_hardware(self):
        """
        TDP figures from manufacturer spec sheets.
        Embodied CO2 from Faiz et al. (2024) LLMCarbon Table 3.
        """
        hw = [
            # (name, mfr, tdp_w, fp16_tflops, int8_tflops, mem_gb, embodied_kg, year, type)
            ("NVIDIA H100 SXM5",    "NVIDIA",  700,  1979,  3958, 80,  1.8*814/10000, 2022, "GPU"),
            ("NVIDIA H100 PCIe",    "NVIDIA",  350,   756,  1513, 80,  1.8*814/10000, 2022, "GPU"),
            ("NVIDIA A100 SXM4",    "NVIDIA",  400,   312,   624, 80,  1.2*826/10000, 2020, "GPU"),
            ("NVIDIA A100 PCIe",    "NVIDIA",  250,   312,   624, 80,  1.2*826/10000, 2020, "GPU"),
            ("NVIDIA V100 SXM2",    "NVIDIA",  300,   125,   None,16,  1.2*815/10000, 2017, "GPU"),
            ("NVIDIA RTX 4090",     "NVIDIA",  450,   165,   330, 24,  None,          2022, "GPU"),
            ("NVIDIA RTX 3090",     "NVIDIA",  350,    71,   None,24,  None,          2020, "GPU"),
            ("NVIDIA L40S",         "NVIDIA",  350,   733,  1457, 48,  None,          2023, "GPU"),
            ("Google TPU v4",       "Google",  170,   275,   None,32,  1.6*400/10000, 2021, "TPU"),
            ("Google TPU v3",       "Google",  450,   123,   None,32,  1.0*700/10000, 2018, "TPU"),
            ("AMD MI300X",          "AMD",     750,  1307,  2614,192,  None,          2023, "GPU"),
            ("AMD MI250X",          "AMD",     560,   383,   None,128, None,          2021, "GPU"),
            ("Intel Gaudi 2",       "Intel",   600,   865,  1730, 96,  None,          2022, "GPU"),
        ]
        created = 0
        for name, mfr, tdp, fp16, int8, mem, emb, year, htype in hw:
            _, c = HardwareSpec.objects.get_or_create(
                name=name,
                defaults=dict(manufacturer=mfr, tdp_watts=tdp, fp16_tflops=fp16,
                              int8_tflops=int8, memory_gb=mem,
                              embodied_co2_kg=emb or 0,
                              released_year=year, hardware_type=htype)
            )
            if c: created += 1
        self.stdout.write(f"  Hardware: {created} created / {len(hw)} total")

    # ── Operations ───────────────────────────────────────────────────────
    def _seed_operations(self):
        """Energy multipliers vs baseline inference.
        Source: Faiz et al. (2024), Strubell et al. (2019)"""
        ops = [
            ("Inference",       "inference",   1.0,  "Single forward pass"),
            ("Training",        "training",    3.2,  "Forward + backward pass + gradient update"),
            ("Fine-tuning",     "finetuning",  1.8,  "Partial training on pre-trained model"),
            ("Data Processing", "dataproc",    0.7,  "Tokenisation, embedding, preprocessing"),
            ("Evaluation",      "evaluation",  1.05, "Inference over evaluation dataset"),
            ("RLHF",            "rlhf",        4.5,  "Reinforcement learning from human feedback"),
        ]
        created = 0
        for name, slug, mult, desc in ops:
            _, c = OperationType.objects.get_or_create(
                slug=slug,
                defaults=dict(name=name, energy_mult=mult, description=desc)
            )
            if c: created += 1
        self.stdout.write(f"  Operations: {created} created / {len(ops)} total")

    # ── Precision ────────────────────────────────────────────────────────
    def _seed_precision(self):
        """Energy factors vs FP32 baseline.
        Source: Faiz et al. (2024), NVIDIA documentation"""
        precs = [
            ("FP32 (Full precision)", "fp32", 1.00, "32-bit float — highest accuracy, highest energy"),
            ("BF16 (Brain float)",    "bf16", 0.62, "16-bit brain float — similar to FP16, better training stability"),
            ("FP16 (Half precision)", "fp16", 0.60, "16-bit float — standard for modern inference"),
            ("INT8 (8-bit integer)",  "int8", 0.35, "8-bit integer — quantised, ~65% energy reduction"),
            ("INT4 (4-bit integer)",  "int4", 0.22, "4-bit quantisation — maximum efficiency, slight quality loss"),
        ]
        created = 0
        for name, slug, factor, desc in precs:
            _, c = PrecisionType.objects.get_or_create(
                slug=slug,
                defaults=dict(name=name, energy_factor=factor, description=desc)
            )
            if c: created += 1
        self.stdout.write(f"  Precision: {created} created / {len(precs)} total")

    # ── AI Models ────────────────────────────────────────────────────────
    def _seed_models(self):
        """
        wh_per_token: Samsi et al. (2023)
        training_co2_kg: Sharma (2025), Patterson et al. (2021), Faiz et al. (2024)
        """
        models = [
            # (name, provider, wh/tok, ctx, year, params_B, train_co2_kg, type)
            ("Claude Opus 4.6",   "Anthropic", 0.0000090, 200000, 2025, None, None,    "dense"),
            ("Claude Sonnet 4.6", "Anthropic", 0.0000025, 200000, 2025, None, None,    "dense"),
            ("Claude Haiku 4.5",  "Anthropic", 0.0000008, 200000, 2025, None, None,    "dense"),
            ("Claude 2",          "Anthropic", 0.0000030, 100000, 2023, None, 320000,  "dense"),
            ("GPT-4o",            "OpenAI",    0.0000030, 128000, 2024, None, None,    "dense"),
            ("GPT-4",             "OpenAI",    0.0000100, 128000, 2023, None, 502000,  "dense"),
            ("GPT-3.5 Turbo",     "OpenAI",    0.0000005, 16385,  2022, 175,  553870,  "dense"),
            ("Gemini 1.5 Pro",    "Google",    0.0000040,1000000, 2024, None, None,    "moe"),
            ("Gemini 1.5 Flash",  "Google",    0.0000010,1000000, 2024, None, None,    "moe"),
            ("LLaMA 3 70B",       "Meta",      0.0000060,   8000, 2024, 70,   None,    "dense"),
            ("LLaMA 3 8B",        "Meta",      0.0000008,   8000, 2024,  8,   None,    "dense"),
            ("LLaMA 2 70B",       "Meta",      0.0000055,   4096, 2023, 70,   350000,  "dense"),
            ("Mistral Large",     "Mistral",   0.0000045,  32000, 2024, None, None,    "dense"),
            ("Mistral 7B",        "Mistral",   0.0000009,  32000, 2023,   7,  120000,  "dense"),
            ("Falcon 40B",        "TII",       0.0000040,   2048, 2023, 40,   180000,  "dense"),
            ("PaLM 2",            "Google",    0.0000035, 32000,  2023, None, 440000,  "dense"),
            ("Grok-1",            "xAI",       0.0000050,  8192,  2024, 314,  280000,  "moe"),
            ("DeepSeek-V2",       "DeepSeek",  0.0000020, 128000, 2024, 236,  200000,  "moe"),
            ("Copilot (GPT-4o)",  "Microsoft", 0.0000030, 128000, 2024, None, None,    "dense"),
        ]
        created = 0
        for name, provider, wh, ctx, year, params, train_co2, mtype in models:
            _, c = AIModel.objects.get_or_create(
                model_name=name,
                defaults=dict(provider=provider, wh_per_token=wh,
                              context_window=ctx, released_year=year,
                              params_billions=params, training_co2_kg=train_co2,
                              model_type=mtype)
            )
            if c: created += 1
        self.stdout.write(f"  AI Models: {created} created / {len(models)} total")
