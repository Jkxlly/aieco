"""
Management command: python manage.py seed_demo_data
Creates demo users, prompt sessions, hardware runs and forum posts.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from calculator.models import UserProfile, PromptSession, HardwareRun, ForumPost


DEMO_USERS = [
    {'username': 'alice_dev',       'email': 'alice@example.com',   'password': 'Demo1234!'},
    {'username': 'jordi_ml',        'email': 'jordi@example.com',   'password': 'Demo1234!'},
    {'username': 'carbon_watcher',  'email': 'carbon@example.com',  'password': 'Demo1234!'},
]

DEMO_SESSIONS = [
    {'title': 'Draft marketing email',         'prompt_text': 'Write a professional marketing email for our new AI carbon calculator product launch targeting enterprise clients in the technology sector.', 'model': 'claude-sonnet', 'region': '0.2'},
    {'title': 'Explain transformer architecture', 'prompt_text': 'Explain the transformer architecture in detail including attention mechanisms, positional encoding, encoder decoder structure and why it revolutionised natural language processing.', 'model': 'gpt4o', 'region': '0.4'},
    {'title': 'Python data pipeline code',     'prompt_text': 'Write a Python script that reads CSV files from a directory, cleans the data by removing duplicates and null values, calculates summary statistics, and outputs results to a new CSV file.', 'model': 'claude-haiku', 'region': '0.2'},
    {'title': 'Summarise quarterly report',    'prompt_text': 'Summarise the following quarterly financial report highlighting key revenue figures, year on year growth, operational costs, and strategic outlook for investors.', 'model': 'gpt35', 'region': '0.3'},
    {'title': 'LLM fine-tuning strategy',      'prompt_text': 'What is the best strategy for fine-tuning a large language model on a domain-specific dataset with limited compute budget, covering LoRA, QLoRA, and full fine-tuning tradeoffs?', 'model': 'claude-opus', 'region': '0.2'},
]

DEMO_HW_RUNS = [
    {'title': 'GPT-4 inference cluster', 'hardware': 'h100', 'operation': 'inference', 'precision': 'fp16', 'gpu_count': 8,  'duration_h': 24, 'region': '0.4'},
    {'title': 'LLaMA fine-tune run',     'hardware': 'a100', 'operation': 'finetuning','precision': 'bf16', 'gpu_count': 4,  'duration_h': 12, 'region': '0.2'},
    {'title': 'Training experiment',     'hardware': 'v100', 'operation': 'training',  'precision': 'fp32', 'gpu_count': 16, 'duration_h': 48, 'region': '0.7'},
]

DEMO_POSTS = [
    {'title': 'Claude Haiku vs GPT-3.5 — huge difference in footprint!', 'body': 'I ran the same 200-token prompt through both models. Claude Haiku uses roughly 60% less energy per token. For high-volume inference this is a massive difference compounded over a month of usage.', 'tag': 'results'},
    {'title': '💡 Tip: Use INT8 precision to cut energy by up to 60%', 'body': 'If you are self-hosting, switching from FP16 to INT8 quantisation with bitsandbytes or GPTQ can dramatically reduce energy. I went from 320Wh to 130Wh on a 24h training run.', 'tag': 'tip'},
    {'title': 'Does model size always correlate with emissions?', 'body': 'Surprisingly no — Gemini 1.5 Flash is more efficient per token than LLaMA 3 8B in my tests, even though it is larger by parameter count. Architecture matters as much as size.', 'tag': 'question'},
    {'title': 'My weekly AI usage — honest breakdown', 'body': '340 prompts across GPT-4o and Claude Sonnet last week. Total estimated footprint: ~14.2mg CO₂. That is about 0.07 Google searches worth. Still adds up at enterprise scale.', 'tag': 'discussion'},
]


class Command(BaseCommand):
    help = 'Seed the database with demo users, sessions, hardware runs and forum posts.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding demo data…')

        # Admin superuser
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@aieco.local', 'Admin1234!')
            self.stdout.write('  ✓ Created superuser: admin / Admin1234!')

        users = []
        for ud in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=ud['username'],
                defaults={'email': ud['email']}
            )
            if created:
                user.set_password(ud['password'])
                user.save()
                UserProfile.objects.get_or_create(user=user)
                self.stdout.write(f"  ✓ Created user: {ud['username']}")
            users.append(user)

        # Prompt sessions for first user
        primary = users[0]
        for sd in DEMO_SESSIONS:
            if not PromptSession.objects.filter(user=primary, title=sd['title']).exists():
                PromptSession.objects.create(user=primary, **sd)
                self.stdout.write(f"  ✓ Session: {sd['title'][:40]}")

        # Hardware runs
        for hd in DEMO_HW_RUNS:
            if not HardwareRun.objects.filter(user=primary, title=hd['title']).exists():
                HardwareRun.objects.create(user=primary, **hd)
                self.stdout.write(f"  ✓ HW run: {hd['title']}")

        # Forum posts spread across users
        for i, pd in enumerate(DEMO_POSTS):
            author = users[i % len(users)]
            if not ForumPost.objects.filter(title=pd['title']).exists():
                ForumPost.objects.create(author=author, **pd)
                self.stdout.write(f"  ✓ Forum post: {pd['title'][:40]}")

        self.stdout.write(self.style.SUCCESS('\nDemo data seeded successfully!'))
        self.stdout.write('  Login: admin / Admin1234!')
        self.stdout.write('  Or:    alice_dev / Demo1234!')
